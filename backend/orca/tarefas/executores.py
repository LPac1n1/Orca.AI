"""O que cada tipo de tarefa faz. Cada executor recebe a fila, o id da tarefa e os parâmetros."""

from orca.banco import Cargo, Item, Observacao, Projeto, corresponder, perfil_do_projeto, sessao_como
from orca.calculo import formatar
from orca.coleta import (
    ErroCnpj,
    registrar_captura,
    registrar_observacao_cargo,
    registrar_observacao_item,
    validar_cnpj,
)
from orca.documentos import gerar_pacote, salvar_pacote
from orca.fluxo import dossie_do_projeto, estado_do_projeto, execucao_vigente, fechar_teto_do_projeto
from orca.otimizacao import SemSolucao
from orca.tarefas.fila import ErroTarefa, Fila, tarefa


@tarefa("coletar_item")
def coletar_item(fila: Fila, tarefa_id: str, p: dict) -> dict:
    """Abre a página (Edge sem janela), guarda a evidência, lê o produto e compara com o item."""
    ctx = fila.contexto
    fila.progresso(tarefa_id, 10, "abrindo a página")
    captura = fila.navegador().capturar(p["url"])
    fila.progresso(tarefa_id, 70, "guardando a evidência")
    with sessao_como(ctx.fabrica, "sistema:coleta") as s:
        item = s.get(Item, p["item_id"])
        if item is None or item.excluido_em is not None:
            raise ErroTarefa("O item não existe mais.")
        evidencia = registrar_captura(s, ctx.armazem, captura)
        r = registrar_observacao_item(s, item, captura, evidencia, cnpj_vendedor=p.get("cnpj_vendedor") or None,
                                      preco_informado=p.get("preco_centavos"), catalogo=ctx.catalogo)
        s.flush()
        observacao_id, preco, avisos = r.observacao.id, r.observacao.preco_centavos, list(r.avisos)
    status = None
    if preco is not None:
        with sessao_como(ctx.fabrica, "sistema:correspondencia") as s:
            status = corresponder(s, s.get(Item, p["item_id"]), s.get(Observacao, observacao_id), ctx.vocabulario).status
    mensagem = f"preço {formatar(preco)}" if preco is not None else "preço não encontrado na página"
    return {"observacao_id": observacao_id, "preco_centavos": preco, "correspondencia": status, "avisos": avisos,
            "bloqueio": captura.bloqueio, "mensagem": mensagem}


@tarefa("coletar_cargo")
def coletar_cargo(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    fila.progresso(tarefa_id, 10, "abrindo a página da vaga")
    captura = fila.navegador().capturar(p["url"])
    with sessao_como(ctx.fabrica, "sistema:coleta") as s:
        cargo = s.get(Cargo, p["cargo_id"])
        if cargo is None or cargo.excluido_em is not None:
            raise ErroTarefa("O cargo não existe mais.")
        evidencia = registrar_captura(s, ctx.armazem, captura)
        r = registrar_observacao_cargo(
            s, cargo, captura, evidencia, cnpj_empresa=p.get("cnpj_empresa") or None,
            salario_min_informado=p.get("salario_min_centavos"), salario_max_informado=p.get("salario_max_centavos"),
        )
        s.flush()
        return {"observacao_id": r.observacao.id, "salario_min_centavos": r.observacao.salario_min_centavos,
                "salario_max_centavos": r.observacao.salario_max_centavos, "avisos": list(r.avisos),
                "bloqueio": captura.bloqueio}


@tarefa("consultar_cnpj")
def consultar_cnpj(fila: Fila, tarefa_id: str, p: dict) -> dict:
    """Situação cadastral em APIs gratuitas (OpenCNPJ, BrasilAPI); um erro não interrompe os outros."""
    ctx = fila.contexto
    cnpjs = list(dict.fromkeys(p["cnpjs"]))
    cliente = ctx.cliente_http() if ctx.cliente_http else None
    consultados, erros = {}, {}
    try:
        for n, cnpj in enumerate(cnpjs, 1):
            fila.progresso(tarefa_id, int(100 * (n - 1) / max(len(cnpjs), 1)), f"consultando {n} de {len(cnpjs)}")
            with sessao_como(ctx.fabrica, "sistema:cnpj") as s:
                provedores = p.get("provedores") or ["opencnpj", "brasilapi"]
                try:
                    consultados[cnpj] = validar_cnpj(s, cnpj, provedores, cliente).situacao
                except (ErroCnpj, ValueError) as e:
                    erros[cnpj] = str(e)
    finally:
        if cliente is not None:
            cliente.close()
    return {"consultados": consultados, "erros": erros,
            "mensagem": f"{len(consultados)} consultado(s), {len(erros)} com erro"}


@tarefa("fechar_teto")
def fechar_teto(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    fila.progresso(tarefa_id, 20, "montando o problema")
    with sessao_como(ctx.fabrica, "sistema:otimizacao") as s:
        projeto = s.get(Projeto, p["projeto_id"])
        estado = estado_do_projeto(s, projeto, ctx.jornadas, ctx.hoje())
        fila.progresso(tarefa_id, 40, "procurando as quantidades e horas que fecham o teto")
        execucao, resultado, pendencias = fechar_teto_do_projeto(s, estado, p.get("tempo_limite_s", 20.0))
        if pendencias:
            return {"pendencias": list(pendencias), "mensagem": "Ainda não dá para fechar o teto"}
        s.flush()
        if isinstance(resultado, SemSolucao):
            return {"execucao_id": execucao.id, "status": "sem_solucao", "motivo": resultado.motivo,
                    "diagnostico": resultado.mensagem,
                    "sugestoes": [{"tipo": sg.tipo, "alvo": sg.alvo, "mensagem": sg.mensagem} for sg in resultado.sugestoes],
                    "mensagem": resultado.mensagem}
        return {"execucao_id": execucao.id, "status": execucao.status, "total_centavos": execucao.total_centavos,
                "alteracoes": len(resultado.alteracoes), "verificacao_ok": execucao.verificacao_ok,
                "mensagem": f"teto fechado: {formatar(execucao.total_centavos)}"}


@tarefa("exportar")
def exportar(fila: Fila, tarefa_id: str, p: dict) -> dict:
    """Gera o pacote completo (documentos, planilhas, evidências, manifesto) e grava em exportacoes/."""
    ctx = fila.contexto
    fila.progresso(tarefa_id, 10, "montando o dossiê")
    with sessao_como(ctx.fabrica, "sistema:exportacao") as s:
        projeto = s.get(Projeto, p["projeto_id"])
        estado = estado_do_projeto(s, projeto, ctx.jornadas, ctx.hoje())
        dossie = dossie_do_projeto(s, estado, execucao_vigente(s, estado))
        impressao = perfil_do_projeto(s, projeto).impressao
    fila.progresso(tarefa_id, 30, "gerando os documentos")
    conteudo = gerar_pacote(dossie, ctx.armazem, fila.renderizador(), ctx.hoje())
    destino = salvar_pacote(conteudo, ctx.pasta_dados / "exportacoes", dossie)
    return {"arquivo": destino.relative_to(ctx.pasta_dados).as_posix(), "bytes": len(conteudo),
            "total_centavos": dossie.total_centavos, "impressao_regras": impressao,
            "mensagem": f"pacote gerado: {destino.name}"}
