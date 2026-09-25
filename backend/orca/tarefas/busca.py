"""Tarefa de busca automática de um lote nas lojas (Fase 2, etapa 10; D-68).

Para cada loja escolhida, os itens são pesquisados do mais difícil ao mais fácil. O melhor
candidato de cada busca tem a página capturada e registrada como se a pessoa tivesse colado
o link (prova, preço, CNPJ, correspondência). Se um item não existe na loja, fica registrado
"não encontrado" (com a página da busca como prova) e a busca continua nos outros itens (D-68,
revista em 25/09/2026: com todos os preços na tela, o item que falta pode ser trocado, D-72).
Achado o código de barras, as lojas seguintes são pesquisadas por ele quando a busca da loja aceita.
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
    algum_do_mesmo_tipo,
    avaliar_candidatos,
    bom_o_bastante,
    buscar_na_pagina,
    buscar_vtex,
    buscar_vtex_is,
    buscar_woocommerce,
    lojas_de_busca,
    ordem_dos_itens,
    termo_curto,
    termo_de_busca,
    termo_minimo,
)
from orca.coleta import ErroCaptura, dominio_da_url, registrar_captura, registrar_nao_encontrado
from orca.coleta.pendencias import vigentes
from orca.fluxo.catalogos import catalogo_da_organizacao, lojas_da_organizacao, vocabulario_da_organizacao
from orca.tarefas.executores import registrar_item
from orca.tarefas.fila import ErroTarefa, Fila, TarefaCancelada, tarefa

TENTATIVAS_POR_ITEM = 2  # páginas de produto capturadas, no máximo, para cada item em cada loja
SEM_CANDIDATOS_SEGUIDOS = 3  # buscas seguidas sem nenhum produto do tipo: a loja não vende o lote (ou a busca mudou)


def _buscar(fila: Fila, cliente: httpx.Client, ritmo: Ritmo, loja: LojaDeBusca, consulta: Consulta):
    ritmo.esperar(dominio_da_url("https://" + loja.dominio))
    if loja.modo == "api_vtex":
        return buscar_vtex(cliente, loja, consulta)
    if loja.modo == "api_vtex_is":
        return buscar_vtex_is(cliente, loja, consulta)
    if loja.modo == "api_woocommerce":
        return buscar_woocommerce(cliente, loja, Consulta(consulta.texto))
    return buscar_na_pagina(fila.navegador(), loja, Consulta(consulta.texto))  # a página de busca não recebe EAN


@tarefa("buscar_lote")
def buscar_lote(fila: Fila, tarefa_id: str, p: dict) -> dict:
    resumo, n_itens = pesquisar_lote(fila, tarefa_id, p["lote_id"], p["lojas"])
    return {"resumo": resumo, "mensagem": _mensagem(resumo, n_itens)}


def pesquisar_lote(fila: Fila, tarefa_id: str, lote_id: str, lojas_escolhidas: list[str],
                   progresso: tuple[int, int] = (0, 99)) -> tuple[list[dict], int]:
    """Pesquisa todos os itens do lote nas lojas escolhidas; devolve o resumo por loja e o número de itens."""
    ctx = fila.contexto
    ritmo = Ritmo(ctx.intervalo_busca_s)
    cancelamento = fila.cancelamento(tarefa_id)
    with sessao_como(ctx.fabrica, "sistema:busca") as s:
        lote = s.get(Lote, lote_id)
        if lote is None or lote.excluido_em is not None:
            raise ErroTarefa("O lote não existe mais.")
        organizacao_id = lote.orcamento.projeto.organizacao_id
        escolhidas = set(lojas_escolhidas)
        lojas = [l for l in lojas_de_busca(lojas_da_organizacao(s, organizacao_id)) if l.id in escolhidas and l.automatica]
        if not lojas:
            raise ErroTarefa("Nenhuma das lojas escolhidas tem busca automática.")
        lojas.sort(key=lambda l: l.aceita_ean)  # por último as que buscam pelo código de barras achado nas outras
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
            r = {"loja": loja.nome, "loja_id": loja.id, "encontrados": 0, "sem_preco": [], "nao_encontrados": [],
                 "erro": None}
            vazias = 0  # buscas seguidas sem nenhum candidato do tipo do item
            resumo.append(r)
            for item_id in ordem:
                passo += 1
                if cancelamento.is_set():
                    raise TarefaCancelada()
                inicio, fim = progresso
                fila.progresso(tarefa_id, min(fim, inicio + int((fim - inicio) * passo / total)),
                               f"{loja.nome}: {nomes[item_id]}")
                if (item_id, dominio) in ja_pesquisados:
                    r["encontrados"] += 1
                    continue
                termo = termo_de_busca(especificacoes[item_id])
                try:
                    candidatos = _candidatos(fila, cliente, ritmo, loja, item_id, termo, especificacoes[item_id],
                                             vocabulario, eans, recusadas)
                except (ErroBusca, ErroCaptura) as erro:
                    r["erro"] = _curto(str(erro))
                    break
                vazias = 0 if algum_do_mesmo_tipo(especificacoes[item_id], candidatos) else vazias + 1
                if vazias >= SEM_CANDIDATOS_SEGUIDOS:
                    r["erro"] = (f"a busca não trouxe nenhum produto parecido em {vazias} itens seguidos: "
                                 "a loja não parece vender este tipo de produto; os outros itens nela foram poupados")
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
                    r["nao_encontrados"].append(nomes[item_id])  # D-68 (revista): a busca segue nos outros itens
    finally:
        cliente.close()
    return resumo, len(ordem)


def _candidatos(fila, cliente, ritmo, loja, item_id, termo, especificacao, vocabulario, eans, recusadas):
    """Pelo código de barras (se a loja aceita), pelo termo e, se não bastar, por um termo mais curto."""
    candidatos = _buscar(fila, cliente, ritmo, loja, Consulta(termo, eans.get(item_id)))
    if not candidatos and eans.get(item_id) and loja.aceita_ean:
        candidatos = _buscar(fila, cliente, ritmo, loja, Consulta(termo))  # sem resultado pelo código: texto
    candidatos = [c for c in candidatos if (item_id, c.url) not in recusadas]
    tentados = {termo}
    for outro in (termo_curto(especificacao), termo_minimo(especificacao)):  # buscas mais abertas, se preciso
        if not outro or outro in tentados or bom_o_bastante(avaliar_candidatos(especificacao, candidatos, vocabulario)):
            continue
        tentados.add(outro)
        vistos = {c.url for c in candidatos}
        candidatos += [c for c in _buscar(fila, cliente, ritmo, loja, Consulta(outro))
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
                                   avisos_extras=(f"achado pela busca automática na {loja.nome} (termo: “{termo}”)",),
                                   preco_da_busca=avaliado.candidato.preco_centavos)
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


def _curto(erro: str) -> str:
    """A primeira linha do erro (sem o registro técnico do navegador)."""
    return erro.split("\n")[0][:200]


def _mensagem(resumo: list[dict], n_itens: int) -> str:
    partes = []
    for r in resumo:
        if r["erro"]:
            partes.append(f"{r['loja']}: {r['erro']}")
            continue
        texto = f"{r['loja']}: {r['encontrados']} de {n_itens}"
        if r["nao_encontrados"]:
            texto += " (não tem " + ", ".join(f"“{n}”" for n in r["nao_encontrados"]) + ")"
        if r["sem_preco"]:
            texto += f" ({len(r['sem_preco'])} sem preço na página: use a captura com janela)"
        partes.append(texto)
    return "; ".join(partes)
