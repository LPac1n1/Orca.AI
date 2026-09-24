"""O que cada tipo de tarefa faz. Cada executor recebe a fila, o id da tarefa e os parâmetros."""

from orca.banco import Cargo, Item, Observacao, Projeto, corresponder, perfil_do_projeto, sessao_como
from orca.calculo import formatar
from orca.coleta import (
    Captura,
    ErroCnpj,
    comprovante_na_tela,
    registrar_captura,
    registrar_comprovante,
    registrar_observacao_cargo,
    registrar_observacao_item,
    registrar_pdf_enviado,
    ultima_consulta,
    url_do_comprovante,
    validar_cnpj,
)
from orca.documentos import gerar_pacote, salvar_pacote
from orca.dominio import formatar_cnpj, normalizar_cnpj
from orca.fluxo import dossie_do_projeto, estado_do_projeto, execucao_vigente, fechar_teto_do_projeto
from orca.fluxo.catalogos import catalogo_da_organizacao, sincronizar_pares_de_ean, vocabulario_da_organizacao
from orca.otimizacao import SemSolucao
from orca.tarefas.fila import Contexto, ErroTarefa, Fila, TarefaCancelada, tarefa

ESPERA_MAXIMA_S = 1800  # 30 minutos para a pessoa navegar


def consultar_cnpj_novo(ctx: Contexto, cnpj: str | None, provedores: list[str]) -> str | None:
    """Consulta a situação do CNPJ na hora, se ele ainda não foi consultado (APIs gratuitas).

    Sem a consulta a loja não entra no trio; por isso ela é feita logo depois de ler a página.
    Devolve um aviso se não deu para consultar agora.
    """
    if not cnpj:
        return None
    with sessao_como(ctx.fabrica, "sistema:cnpj") as s:
        if ultima_consulta(s, cnpj) is not None:
            return None
        cliente = ctx.cliente_http() if ctx.cliente_http else None
        try:
            validar_cnpj(s, cnpj, provedores, cliente)
            return None
        except (ErroCnpj, ValueError) as erro:
            return f"não deu para consultar o CNPJ {formatar_cnpj(cnpj)} agora ({erro}); use “Consultar CNPJs” no Painel"
        finally:
            if cliente is not None:
                cliente.close()


def registrar_item(ctx: Contexto, p: dict, captura: Captura, autor: str = "sistema:coleta",
                   avisos_extras: tuple[str, ...] = ()) -> dict:
    """Guarda a evidência, registra a observação e compara com o item (com o vocabulário da OSC)."""
    with sessao_como(ctx.fabrica, autor) as s:
        item = s.get(Item, p["item_id"])
        if item is None or item.excluido_em is not None:
            raise ErroTarefa("O item não existe mais.")
        organizacao_id = item.lote.orcamento.projeto.organizacao_id
        regras = perfil_do_projeto(s, item.lote.orcamento.projeto).regras
        so_pdf = not captura.png and not captura.mhtml  # PDF enviado pelo usuário (D-67)
        evidencia = registrar_pdf_enviado(s, ctx.armazem, captura) if so_pdf else registrar_captura(s, ctx.armazem, captura)
        r = registrar_observacao_item(s, item, captura, evidencia, cnpj_vendedor=p.get("cnpj_vendedor") or None,
                                      preco_informado=p.get("preco_centavos"),
                                      catalogo=catalogo_da_organizacao(s, organizacao_id), avisos_extras=avisos_extras,
                                      preco_no_pix=regras.preco_referencia.desconto_pix == "usar")  # D-60
        s.flush()
        observacao_id, preco, avisos = r.observacao.id, r.observacao.preco_centavos, list(r.avisos)
        tem_ean = r.observacao.ean is not None
        cnpj, provedores = r.observacao.cnpj_vendedor, list(regras.cnpj.provedores)
    if (aviso := consultar_cnpj_novo(ctx, cnpj, provedores)) is not None:
        avisos.append(aviso)
    status = None
    if preco is not None:
        with sessao_como(ctx.fabrica, "sistema:correspondencia") as s:
            vocabulario = vocabulario_da_organizacao(s, organizacao_id)
            status = corresponder(s, s.get(Item, p["item_id"]), s.get(Observacao, observacao_id), vocabulario).status
    if tem_ean:
        with sessao_como(ctx.fabrica, "sistema:pares") as s:
            sincronizar_pares_de_ean(s, organizacao_id)  # D-64: mesmo código de barras em outra loja
    mensagem = f"preço {formatar(preco)}" if preco is not None else "preço não encontrado na página"
    return {"observacao_id": observacao_id, "preco_centavos": preco, "correspondencia": status, "avisos": avisos,
            "bloqueio": captura.bloqueio, "mensagem": mensagem}


def registrar_cargo(ctx: Contexto, p: dict, captura: Captura, autor: str = "sistema:coleta",
                    avisos_extras: tuple[str, ...] = ()) -> dict:
    with sessao_como(ctx.fabrica, autor) as s:
        cargo = s.get(Cargo, p["cargo_id"])
        if cargo is None or cargo.excluido_em is not None:
            raise ErroTarefa("O cargo não existe mais.")
        so_pdf = not captura.png and not captura.mhtml
        evidencia = registrar_pdf_enviado(s, ctx.armazem, captura) if so_pdf else registrar_captura(s, ctx.armazem, captura)
        r = registrar_observacao_cargo(
            s, cargo, captura, evidencia, cnpj_empresa=p.get("cnpj_empresa") or None,
            salario_min_informado=p.get("salario_min_centavos"), salario_max_informado=p.get("salario_max_centavos"),
            avisos_extras=avisos_extras,
        )
        s.flush()
        referencia = r.observacao.salario_min_centavos or r.observacao.salario_max_centavos
        resultado = {"observacao_id": r.observacao.id, "salario_min_centavos": r.observacao.salario_min_centavos,
                     "salario_max_centavos": r.observacao.salario_max_centavos, "avisos": list(r.avisos),
                     "bloqueio": captura.bloqueio,
                     "mensagem": f"salário {formatar(referencia)}" if referencia else "salário não encontrado na página"}
        cnpj = r.observacao.cnpj_vendedor
        provedores = list(perfil_do_projeto(s, cargo.orcamento.projeto).regras.cnpj.provedores)
    if (aviso := consultar_cnpj_novo(ctx, cnpj, provedores)) is not None:
        resultado["avisos"].append(aviso)
    return resultado


@tarefa("coletar_item")
def coletar_item(fila: Fila, tarefa_id: str, p: dict) -> dict:
    """Abre a página (Edge sem janela), guarda a evidência, lê o produto e compara com o item."""
    fila.progresso(tarefa_id, 10, "abrindo a página")
    captura = fila.navegador().capturar(p["url"])
    fila.progresso(tarefa_id, 70, "guardando a evidência")
    return registrar_item(fila.contexto, p, captura)


@tarefa("coletar_cargo")
def coletar_cargo(fila: Fila, tarefa_id: str, p: dict) -> dict:
    fila.progresso(tarefa_id, 10, "abrindo a página da vaga")
    return registrar_cargo(fila.contexto, p, fila.navegador().capturar(p["url"]))


def _esperar(fila: Fila, tarefa_id: str, condicao):
    """Função `pronto` da captura assistida: termina quando `condicao` for verdadeira ou o usuário cancelar."""
    cancelamento = fila.cancelamento(tarefa_id)

    def pronto(pagina) -> bool:
        if cancelamento.is_set():
            raise TarefaCancelada()
        return condicao(pagina)
    return pronto


@tarefa("captura_assistida")
def captura_assistida(fila: Fila, tarefa_id: str, p: dict) -> dict:
    """Captura assistida (C4, D-67): o usuário navega na janela do sistema e clica em “Capturar agora”."""
    fila.esperar_usuario(tarefa_id, "Abri uma janela do navegador. Navegue nela, na mesma aba, até a página (resolva CEP ou "
                                    "verificação, se pedir; não entre com a sua conta para ver preço de cliente) e clique em "
                                    "“Capturar agora” aqui no Orça.AI.")
    sinal = fila.sinal(tarefa_id)
    captura = fila.navegador_visivel().capturar_assistido(
        p["url"], _esperar(fila, tarefa_id, lambda _pagina: sinal.is_set()),
        tempo_maximo_s=p.get("tempo_maximo_s", ESPERA_MAXIMA_S))
    fila.progresso(tarefa_id, 70, "guardando a evidência")
    return (registrar_item if p.get("item_id") else registrar_cargo)(fila.contexto, p, captura)


@tarefa("comprovante")
def comprovante(fila: Fila, tarefa_id: str, p: dict) -> dict:
    """Comprovante da Receita (D-13, D-14): o usuário resolve a verificação; o sistema salva o comprovante sozinho."""
    ctx = fila.contexto
    cnpj = normalizar_cnpj(p["cnpj"])
    fila.esperar_usuario(tarefa_id, f"Abri a página da Receita com o CNPJ {formatar_cnpj(cnpj)} preenchido. Resolva a "
                                    "verificação e clique em “Consultar”: o comprovante é salvo sozinho.")

    def comprovante_apareceu(pagina) -> bool:
        return comprovante_na_tela(pagina.url, pagina.evaluate("document.body ? document.body.innerText : ''"), cnpj)

    captura = fila.navegador_visivel().capturar_assistido(
        url_do_comprovante(cnpj), _esperar(fila, tarefa_id, comprovante_apareceu),
        tempo_maximo_s=p.get("tempo_maximo_s", ESPERA_MAXIMA_S))
    with sessao_como(ctx.fabrica, "sistema:comprovante") as s:
        registro = registrar_comprovante(s, ctx.armazem, cnpj, captura)
        s.flush()
        return {"comprovante_id": registro.id, "cnpj": cnpj, "mensagem": f"comprovante de {formatar_cnpj(cnpj)} salvo"}


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
