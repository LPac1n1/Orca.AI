"""Tarefas dos opcionais (Fase 2, etapa 15): descoberta pela SerpApi (C2), Google Vagas e IA conferindo os 🟡.

O sistema funciona sem os dois (D-50). A descoberta só aponta links: nada é capturado
sem a pessoa escolher. A IA só mantém o 🟡 ou rebaixa para 🔴, com motivo (D-52); cada
resposta fica registrada na correspondência (autor "ia:<provedor>") e na tarefa.
"""

import httpx
from sqlalchemy import select

from orca.banco import (
    Cargo,
    Item,
    Lote,
    Observacao,
    Projeto,
    anuncio_da_observacao,
    correspondencia_vigente,
    especificacao_do_item,
    registrar_correspondencia,
    sessao_como,
)
from orca.busca import (
    ErroBusca,
    Ritmo,
    avaliar_candidatos,
    ler_plataformas,
    plataforma_do_endereco,
    termo_de_busca,
)
from orca.busca.serpapi import buscar_na_web, buscar_vagas_google
from orca.coleta import dominio_da_url
from orca.coleta.pendencias import vigentes
from orca.correspondencia import ResultadoCorrespondencia
from orca.dominio import OrigemCorrespondencia, StatusCorrespondencia
from orca.fluxo.catalogos import catalogo_da_organizacao, vocabulario_da_organizacao
from orca.ia import ErroFormatoIA, ErroIA, julgar_correspondencia, provedor_configurado
from orca.tarefas.executores import registrar_cargo
from orca.tarefas.fila import ErroTarefa, Fila, TarefaCancelada, tarefa

LINKS_POR_ITEM = 8
IA_POR_TAREFA = 40  # pedidos à IA numa tarefa, no máximo (plano grátis)


def _cliente(ctx) -> httpx.Client:
    return ctx.cliente_http() if ctx.cliente_http else httpx.Client()


# --- Descoberta pela SerpApi (C2) ------------------------------------------------------------------


@tarefa("descobrir_na_web")
def descobrir_na_web(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    chave = ctx.cofre.ler("serpapi") if ctx.cofre else None
    if not chave:
        raise ErroTarefa("Falta a chave da SerpApi (em Opcionais).")
    cancelamento = fila.cancelamento(tarefa_id)
    with sessao_como(ctx.fabrica, "sistema:busca") as s:
        lote = s.get(Lote, p["lote_id"])
        if lote is None or lote.excluido_em is not None:
            raise ErroTarefa("O lote não existe mais.")
        organizacao_id = lote.orcamento.projeto.organizacao_id
        escolhidos = set(p.get("itens") or [])
        itens = [i for i in lote.itens if i.excluido_em is None and (not escolhidos or i.id in escolhidos)]
        especificacoes = {i.id: especificacao_do_item(i) for i in itens}
        nomes = {i.id: i.descricao for i in itens}
        vocabulario = vocabulario_da_organizacao(s, organizacao_id)
        lojas = {l.dominio: l.nome for l in catalogo_da_organizacao(s, organizacao_id).values()}
        observacoes = vigentes(s.scalars(select(Observacao).where(Observacao.item_id.in_(list(especificacoes)))))
        pesquisados = {(o.item_id, dominio_da_url(o.url)) for o in observacoes if o.encontrado}

    resultado, avisos = [], []
    cliente = _cliente(ctx)
    try:
        for n, item_id in enumerate(especificacoes):
            if cancelamento.is_set():
                raise TarefaCancelada()
            fila.progresso(tarefa_id, int(100 * n / len(especificacoes)), f"SerpApi: {nomes[item_id]}")
            termo = termo_de_busca(especificacoes[item_id])
            try:
                candidatos = buscar_na_web(cliente, chave, termo)
            except ErroBusca as erro:
                avisos.append(str(erro))
                break  # chave recusada ou buscas do mês acabaram: as outras também falhariam
            links = []
            for a in avaliar_candidatos(especificacoes[item_id], candidatos, vocabulario)[:LINKS_POR_ITEM]:
                dominio = dominio_da_url(a.candidato.url)
                links.append({"url": a.candidato.url, "titulo": a.candidato.titulo, "dominio": dominio,
                              "loja": lojas.get(dominio), "status": a.status, "parecenca": round(a.parecenca, 2),
                              "preco_centavos": a.candidato.preco_centavos,
                              "ja_pesquisada": (item_id, dominio) in pesquisados})
            resultado.append({"item_id": item_id, "item": nomes[item_id], "termo": termo, "links": links})
    finally:
        cliente.close()
    total = sum(len(r["links"]) for r in resultado)
    mensagem = f"{len(resultado)} busca(s) na SerpApi; {total} página(s) de produto parecido"
    if avisos:
        mensagem += f" — {avisos[0]}"
    return {"itens": resultado, "avisos": avisos, "mensagem": mensagem}


# --- IA confere os 🟡 (D-52) -----------------------------------------------------------------------

_TEXTO = {
    "nao": "IA ({p}): produto diferente — {m}",
    "sim": "IA ({p}): parece o mesmo produto, mas quem confirma é você — {m}",
    "incerto": "IA ({p}): não dá para saber — {m}",
}


def _amarelos(s, projeto: Projeto) -> list[dict]:
    """Os 🟡 vigentes do projeto que nem uma pessoa nem a IA já julgaram."""
    pares = []
    for orcamento in projeto.orcamentos:
        if orcamento.excluido_em is not None or orcamento.arquivado_em is not None:
            continue
        for lote in (l for l in orcamento.lotes if l.excluido_em is None):
            for item in (i for i in lote.itens if i.excluido_em is None):
                for obs in vigentes(s.scalars(select(Observacao).where(Observacao.item_id == item.id))):
                    atual = correspondencia_vigente(s, item.id, obs.id) if obs.encontrado else None
                    if atual is None or atual.status != "amarelo" or atual.origem in ("humano", "ia"):
                        continue
                    pares.append({"item_id": item.id, "observacao_id": obs.id, "correspondencia_id": atual.id,
                                  "item": item.descricao, "titulo": obs.titulo or obs.url,
                                  "especificacao": especificacao_do_item(item), "anuncio": anuncio_da_observacao(obs)})
    return pares


@tarefa("julgar_amarelos")
def julgar_amarelos(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    cancelamento = fila.cancelamento(tarefa_id)
    cliente = _cliente(ctx)
    try:
        try:
            provedor = provedor_configurado(ctx.ia, ctx.cofre, cliente) if ctx.cofre else None
        except ErroIA as erro:
            raise ErroTarefa(str(erro)) from erro
        if provedor is None:
            raise ErroTarefa("A IA está desligada (em Opcionais).")
        with sessao_como(ctx.fabrica, "sistema") as s:
            projeto = s.get(Projeto, p["projeto_id"])
            if projeto is None or projeto.excluido_em is not None:
                raise ErroTarefa("O projeto não existe mais.")
            pares = _amarelos(s, projeto)
        limite = int(p.get("limite") or IA_POR_TAREFA)
        ritmo = Ritmo(ctx.intervalo_ia_s)
        autor = f"ia:{provedor.nome}"
        chamadas, contagem, parada = [], {"nao": 0, "sim": 0, "incerto": 0, "falha": 0}, None
        for n, par in enumerate(pares[:limite]):
            if cancelamento.is_set():
                raise TarefaCancelada()
            fila.progresso(tarefa_id, int(100 * n / min(len(pares), limite)), f"IA: {par['item']}")
            ritmo.esperar("ia")
            try:
                julgamento = julgar_correspondencia(provedor, par["especificacao"], par["anuncio"])
            except ErroFormatoIA as erro:
                contagem["falha"] += 1
                chamadas.append({"item": par["item"], "titulo": par["titulo"], "resposta": None, "motivo": str(erro)})
                continue
            except ErroIA as erro:
                parada = str(erro)  # chave recusada, limite do plano grátis, sem conexão: para aqui
                break
            with sessao_como(ctx.fabrica, autor) as s:
                atual = correspondencia_vigente(s, par["item_id"], par["observacao_id"])
                if atual is None or atual.id != par["correspondencia_id"]:
                    continue  # uma pessoa decidiu enquanto a IA respondia: vale a decisão dela
                status = StatusCorrespondencia.VERMELHO if julgamento.rebaixar else StatusCorrespondencia.AMARELO
                texto = _TEXTO[julgamento.resposta].format(p=provedor.nome, m=julgamento.motivo)
                registrar_correspondencia(s, s.get(Item, par["item_id"]), s.get(Observacao, par["observacao_id"]),
                                          ResultadoCorrespondencia(status, OrigemCorrespondencia.IA,
                                                                   (*atual.motivos, texto), ()))
            contagem[julgamento.resposta] += 1
            chamadas.append({"item": par["item"], "titulo": par["titulo"], "resposta": julgamento.resposta,
                             "motivo": julgamento.motivo, "enviado": julgamento.entrada})
    finally:
        cliente.close()
    julgadas = contagem["nao"] + contagem["sim"] + contagem["incerto"]
    mensagem = (f"IA ({provedor.nome}) conferiu {julgadas} 🟡: {contagem['nao']} rebaixado(s) para 🔴, "
                f"{julgadas - contagem['nao']} continua(m) 🟡 para você decidir")
    if contagem["falha"]:
        mensagem += f"; {contagem['falha']} resposta(s) fora do formato, ignorada(s)"
    restantes = max(0, len(pares) - limite)
    if restantes:
        mensagem += f"; faltam {restantes} (peça de novo depois)"
    if parada:
        mensagem += f" — parou: {parada}"
    return {"provedor": provedor.nome, "modelo": provedor.modelo, "rebaixadas": contagem["nao"],
            "mantidas": julgadas - contagem["nao"], "falhas": contagem["falha"], "restantes": restantes,
            "parada": parada, "chamadas": chamadas, "mensagem": mensagem}


# --- Google Vagas (D-69 revista em 25/09/2026) -------------------------------------------------------

VAGAS_AUTOMATICAS = 6  # capturadas sozinhas, no máximo, por busca


def _onde_abrir(vaga, plataformas) -> tuple[str, str | None, str | None]:
    """(como, endereço, plataforma): "sistema" se a plataforma permite programas, "janela" se não, "outro_site"."""
    janela = outro = None
    for _, url in vaga.links:
        plataforma = plataforma_do_endereco(url, plataformas)
        if plataforma is not None and plataforma.abrir_vaga == "sistema":
            return "sistema", url, plataforma.nome
        if plataforma is not None and janela is None:
            janela = (url, plataforma.nome)
        elif plataforma is None and outro is None:
            outro = url
    if janela:
        return "janela", janela[0], janela[1]
    return ("outro_site", outro, None) if outro else ("sem_link", None, None)


@tarefa("descobrir_vagas")
def descobrir_vagas(fila: Fila, tarefa_id: str, p: dict) -> dict:
    """Procura o cargo no Google Vagas; captura as vagas das plataformas que permitem programas.

    Até 6, preferindo as que mostram salário (critério objetivo, princípio 7); as do Indeed, do
    LinkedIn e de outros sites ficam listadas para a pessoa abrir.
    """
    ctx = fila.contexto
    chave = ctx.cofre.ler("serpapi") if ctx.cofre else None
    if not chave:
        raise ErroTarefa("Falta a chave da SerpApi (em Opcionais).")
    cancelamento = fila.cancelamento(tarefa_id)
    with sessao_como(ctx.fabrica, "sistema:vagas") as s:
        cargo = s.get(Cargo, p["cargo_id"])
        if cargo is None or cargo.excluido_em is not None:
            raise ErroTarefa("O cargo não existe mais.")
        nome = cargo.nome
        ja_vistas = set(s.scalars(select(Observacao.url).where(Observacao.cargo_id == cargo.id)))
    fila.progresso(tarefa_id, 5, f"Google Vagas: {nome}")
    cliente = _cliente(ctx)
    try:
        vagas = buscar_vagas_google(cliente, chave, nome, p.get("cidade"), p.get("uf"))
    except ErroBusca as erro:
        raise ErroTarefa(str(erro)) from erro
    finally:
        cliente.close()

    plataformas = ler_plataformas()
    linhas = []
    for v in vagas:
        como, url, plataforma = _onde_abrir(v, plataformas)
        linhas.append({"titulo": v.titulo, "empresa": v.empresa, "local": v.local, "salario": v.salario,
                       "publicada": v.publicada, "plataforma": plataforma, "url": url, "como": como,
                       "situacao": "ja_tinha" if url in ja_vistas else como, "mensagem": None})
    automaticas = [l for l in linhas if l["situacao"] == "sistema"]
    automaticas.sort(key=lambda l: l["salario"] is None)  # as que mostram salário primeiro
    ritmo = Ritmo(ctx.intervalo_busca_s)
    capturadas = 0
    for n, linha in enumerate(automaticas[:VAGAS_AUTOMATICAS]):
        if cancelamento.is_set():
            raise TarefaCancelada()
        fila.progresso(tarefa_id, 10 + int(85 * n / max(1, min(len(automaticas), VAGAS_AUTOMATICAS))),
                       f"{linha['plataforma']}: {linha['empresa'] or linha['titulo']}")
        ritmo.esperar(dominio_da_url(linha["url"]))
        try:
            captura = fila.navegador().capturar(linha["url"])
            r = registrar_cargo(ctx, {"cargo_id": p["cargo_id"]}, captura, autor="sistema:vagas",
                                avisos_extras=("achada no Google Vagas",))
        except TarefaCancelada:
            raise
        except Exception as erro:  # noqa: BLE001 — uma vaga com problema não para as outras
            linha["situacao"], linha["mensagem"] = "erro", str(erro)[:200]
            continue
        linha["situacao"], linha["mensagem"] = "capturada", r["mensagem"]
        capturadas += 1
    na_janela = sum(1 for l in linhas if l["situacao"] in ("janela", "outro_site"))
    mensagem = (f"{len(linhas)} vaga(s) no Google Vagas; {capturadas} capturada(s) sozinha(s); "
                f"{na_janela} para você abrir (Indeed, LinkedIn ou outros sites)")
    return {"termo": " ".join(x for x in (nome, p.get("cidade"), p.get("uf")) if x), "vagas": linhas,
            "capturadas": capturadas, "mensagem": mensagem}

