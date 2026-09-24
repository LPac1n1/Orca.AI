"""Tarefa de busca automática de um lote nas lojas (Fase 2, etapa 10; D-68).

Para cada loja escolhida, os itens são pesquisados do mais difícil ao mais fácil. O melhor
candidato de cada busca tem a página capturada e registrada como se a pessoa tivesse colado
o link (prova, preço, CNPJ, correspondência). Se um item não existe na loja, a loja não
completa o lote: fica registrado "não encontrado" (com a página da busca como prova) e as
outras buscas nela são poupadas. Achado o código de barras, as lojas seguintes são
pesquisadas por ele quando a busca da loja aceita.
"""

from collections import Counter

import httpx
from sqlalchemy import select

from orca.banco import Item, Lote, Observacao, correspondencia_vigente, especificacao_do_item, sessao_como
from orca.busca import (
    Consulta,
    ErroBusca,
    LojaDeBusca,
    Ritmo,
    avaliar_candidatos,
    bom_o_bastante,
    buscar_na_pagina,
    buscar_vtex,
    lojas_de_busca,
    ordem_dos_itens,
    termo_curto,
    termo_de_busca,
)
from orca.coleta import ErroCaptura, dominio_da_url, registrar_captura, registrar_nao_encontrado
from orca.coleta.pendencias import vigentes
from orca.fluxo.catalogos import catalogo_da_organizacao, lojas_da_organizacao, vocabulario_da_organizacao
from orca.tarefas.executores import registrar_item
from orca.tarefas.fila import ErroTarefa, Fila, TarefaCancelada, tarefa

TENTATIVAS_POR_ITEM = 2  # páginas de produto capturadas, no máximo, para cada item em cada loja


def _buscar(fila: Fila, cliente: httpx.Client, ritmo: Ritmo, loja: LojaDeBusca, consulta: Consulta):
    ritmo.esperar(dominio_da_url("https://" + loja.dominio))
    if loja.modo == "api_vtex":
        return buscar_vtex(cliente, loja, consulta)
    return buscar_na_pagina(fila.navegador(), loja, Consulta(consulta.texto))  # a página de busca não recebe EAN


@tarefa("buscar_lote")
def buscar_lote(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    ritmo = Ritmo(ctx.intervalo_busca_s)
    cancelamento = fila.cancelamento(tarefa_id)
    with sessao_como(ctx.fabrica, "sistema:busca") as s:
        lote = s.get(Lote, p["lote_id"])
        if lote is None or lote.excluido_em is not None:
            raise ErroTarefa("O lote não existe mais.")
        organizacao_id = lote.orcamento.projeto.organizacao_id
        escolhidas = set(p["lojas"])
        lojas = [l for l in lojas_de_busca(lojas_da_organizacao(s, organizacao_id)) if l.id in escolhidas and l.automatica]
        if not lojas:
            raise ErroTarefa("Nenhuma das lojas escolhidas tem busca automática.")
        lojas.sort(key=lambda l: l.modo == "api_vtex")  # por último as que buscam pelo código de barras achado nas outras
        vocabulario = vocabulario_da_organizacao(s, organizacao_id)
        catalogo = catalogo_da_organizacao(s, organizacao_id)
        itens = [i for i in lote.itens if i.excluido_em is None]
        especificacoes = {i.id: especificacao_do_item(i) for i in itens}
        nomes = {i.id: i.descricao for i in itens}
        eans = {i.id: i.ean for i in itens if i.ean}
        observacoes = vigentes(s.scalars(select(Observacao).where(Observacao.item_id.in_(list(especificacoes)))))
        status = {o.id: (c.status if (c := correspondencia_vigente(s, o.item_id, o.id)) else None) for o in observacoes}
        # página recusada (🔴) não conta: a loja é pesquisada de novo, sem voltar à mesma página
        recusadas = {(o.item_id, o.url) for o in observacoes if status[o.id] == "vermelho"}
        ja_pesquisados = {(o.item_id, dominio_da_url(o.url)) for o in observacoes
                          if o.encontrado and status[o.id] != "vermelho"}
        cobertura = Counter(o.item_id for o in observacoes if o.encontrado and o.preco_centavos)
        for o in observacoes:  # código de barras de uma página já confirmada como o mesmo produto
            if o.ean and status[o.id] == "verde":
                eans.setdefault(o.item_id, o.ean)

    ordem = ordem_dos_itens([(i, i in eans) for i in especificacoes], cobertura)
    total = max(1, len(lojas) * len(ordem))
    passo = 0
    resumo = []
    cliente = ctx.cliente_http() if ctx.cliente_http else httpx.Client()
    try:
        for loja in lojas:
            dominio = dominio_da_url("https://" + loja.dominio)
            r = {"loja": loja.nome, "encontrados": 0, "sem_preco": [], "nao_encontrado": None, "erro": None}
            resumo.append(r)
            for item_id in ordem:
                passo += 1
                if cancelamento.is_set():
                    raise TarefaCancelada()
                fila.progresso(tarefa_id, min(99, int(100 * passo / total)), f"{loja.nome}: {nomes[item_id]}")
                if (item_id, dominio) in ja_pesquisados:
                    r["encontrados"] += 1
                    continue
                termo = termo_de_busca(especificacoes[item_id])
                try:
                    candidatos = _candidatos(fila, cliente, ritmo, loja, item_id, termo, especificacoes[item_id],
                                             vocabulario, eans, recusadas)
                except (ErroBusca, ErroCaptura) as erro:
                    r["erro"] = str(erro)
                    break
                try:
                    situacao = _capturar_melhor(fila, ritmo, dominio, loja, item_id, termo, candidatos,
                                                especificacoes[item_id], vocabulario, eans)
                except TarefaCancelada:
                    raise
                except Exception as erro:  # noqa: BLE001 — um problema numa loja não para as outras
                    r["erro"] = f"erro ao registrar “{nomes[item_id]}”: {erro}"
                    break
                if situacao == "encontrado":
                    r["encontrados"] += 1
                elif situacao == "sem_preco":
                    r["sem_preco"].append(nomes[item_id])
                else:
                    _registrar_nao_encontrado(fila, ritmo, dominio, loja, item_id, termo, candidatos, catalogo)
                    r["nao_encontrado"] = nomes[item_id]
                    break  # D-68: sem esse item a loja não completa o lote; as outras buscas nela são poupadas
    finally:
        cliente.close()
    return {"resumo": resumo, "mensagem": _mensagem(resumo, len(ordem))}


def _candidatos(fila, cliente, ritmo, loja, item_id, termo, especificacao, vocabulario, eans, recusadas):
    """Pelo código de barras (se a loja aceita), pelo termo e, se não bastar, por um termo mais curto."""
    candidatos = _buscar(fila, cliente, ritmo, loja, Consulta(termo, eans.get(item_id)))
    if not candidatos and eans.get(item_id) and loja.modo == "api_vtex":
        candidatos = _buscar(fila, cliente, ritmo, loja, Consulta(termo))  # sem resultado pelo código: texto
    candidatos = [c for c in candidatos if (item_id, c.url) not in recusadas]
    curto = termo_curto(especificacao)
    if curto and curto != termo and not bom_o_bastante(avaliar_candidatos(especificacao, candidatos, vocabulario)):
        vistos = {c.url for c in candidatos}
        candidatos += [c for c in _buscar(fila, cliente, ritmo, loja, Consulta(curto))
                       if c.url not in vistos and (item_id, c.url) not in recusadas]
    return candidatos


def _capturar_melhor(fila, ritmo, dominio, loja, item_id, termo, candidatos, especificacao, vocabulario, eans) -> str:
    """Captura o melhor candidato (e o seguinte, se a página mostrar outro produto)."""
    ctx = fila.contexto
    sem_preco = False
    for avaliado in avaliar_candidatos(especificacao, candidatos, vocabulario)[:TENTATIVAS_POR_ITEM]:
        ritmo.esperar(dominio)
        try:
            captura = fila.navegador().capturar(avaliado.candidato.url)
        except ErroCaptura:
            continue
        resultado = registrar_item(ctx, {"item_id": item_id}, captura, autor="sistema:busca",
                                   avisos_extras=(f"achado pela busca automática na {loja.nome} (termo: “{termo}”)",))
        if resultado["correspondencia"] not in ("verde", "amarelo"):
            if resultado["preco_centavos"] is None and resultado["correspondencia"] is None:
                sem_preco = True  # a página abriu, mas sem preço (ex.: a loja pede CEP)
            continue
        if resultado["correspondencia"] == "verde":
            with sessao_como(ctx.fabrica, "sistema:busca") as s:
                ean = s.get(Observacao, resultado["observacao_id"]).ean
            if ean:
                eans.setdefault(item_id, ean)
        return "encontrado"
    return "sem_preco" if sem_preco else "nao_encontrado"


def _registrar_nao_encontrado(fila, ritmo, dominio, loja, item_id, termo, candidatos, catalogo) -> None:
    ctx = fila.contexto
    ritmo.esperar(dominio)
    try:
        captura = fila.navegador().capturar(loja.endereco(termo))
    except ErroCaptura:
        return
    with sessao_como(ctx.fabrica, "sistema:busca") as s:
        evidencia = registrar_captura(s, ctx.armazem, captura)
        registrar_nao_encontrado(s, s.get(Item, item_id), captura, evidencia, termo,
                                 [c.titulo for c in candidatos if c.titulo], catalogo)


def _mensagem(resumo: list[dict], n_itens: int) -> str:
    partes = []
    for r in resumo:
        if r["erro"]:
            partes.append(f"{r['loja']}: {r['erro']}")
        elif r["nao_encontrado"]:
            partes.append(f"{r['loja']}: não tem “{r['nao_encontrado']}”")
        else:
            texto = f"{r['loja']}: {r['encontrados']} de {n_itens}"
            if r["sem_preco"]:
                texto += f" ({len(r['sem_preco'])} sem preço na página: use a captura com janela)"
            partes.append(texto)
    return "; ".join(partes)
