"""Vitrine do item (D-75, "código de barras primeiro"): a pessoa escolhe o produto certo entre os achados.

A descrição tem muitas variações; o código de barras é igual em todas as lojas. Então a descrição
serve só para achar o primeiro produto: o sistema pesquisa as lojas que vendem o tipo do item e
mostra os produtos (foto, nome, preço, loja); a pessoa clica no certo. A página dele vira a prova e
o produto de referência (D-71), e o código de barras dela passa a guiar as buscas nas outras lojas.
Nada é gravado aqui: só a lista de produtos (com a prévia do preço) no resultado da tarefa.
"""

import httpx

from orca.banco import Item, especificacao_do_item, sessao_como
from orca.busca import CATEGORIA_DA_LOJA, ErroBusca, Ritmo, avaliar_candidatos, termo_de_busca
from orca.coleta import ErroCaptura
from orca.fluxo.catalogos import lojas_pelo_que_vendem, vocabulario_da_organizacao
from orca.tarefas.busca import _candidatos
from orca.tarefas.fila import ErroTarefa, Fila, TarefaCancelada, tarefa

POR_LOJA = 8  # produtos mostrados de cada loja


@tarefa("vitrine_do_item")
def vitrine_do_item(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    cancelamento = fila.cancelamento(tarefa_id)
    with sessao_como(ctx.fabrica, "sistema:busca") as s:
        item = s.get(Item, p["item_id"])
        if item is None or item.excluido_em is not None:
            raise ErroTarefa("O item não existe mais.")
        organizacao_id = item.lote.orcamento.projeto.organizacao_id
        pedidas = {CATEGORIA_DA_LOJA.get(item.categoria, item.categoria)} if item.categoria else set()
        # as lojas que o sistema pesquisa sozinho e vendem o tipo do item (sem categoria: todas)
        lojas = [l for l, situacao, *_ in lojas_pelo_que_vendem(s, organizacao_id, pedidas)
                 if l.automatica and situacao in ("todas", "itens_sem_categoria")]
        especificacao = especificacao_do_item(item)
        vocabulario = vocabulario_da_organizacao(s, organizacao_id)
        eans = {item.id: item.ean} if item.ean else {}
    if not lojas:
        raise ErroTarefa("Nenhuma loja com busca automática vende este tipo de produto: cole o link da página.")
    lojas.sort(key=lambda l: l.aceita_ean)
    termo = termo_de_busca(especificacao)
    ritmo = Ritmo(ctx.intervalo_busca_s)
    cliente = ctx.cliente_http() if ctx.cliente_http else httpx.Client()
    grupos, avisos = [], []
    try:
        for n, loja in enumerate(lojas):
            if cancelamento.is_set():
                raise TarefaCancelada()
            fila.progresso(tarefa_id, int(95 * n / len(lojas)), f"{loja.nome}: “{termo}”")
            try:
                candidatos = _candidatos(fila, cliente, ritmo, loja, p["item_id"], termo, especificacao, vocabulario,
                                         eans, set())
            except (ErroBusca, ErroCaptura) as erro:
                avisos.append(f"{loja.nome}: {str(erro).splitlines()[0][:150]}")
                continue
            produtos = [{"url": a.candidato.url, "titulo": a.candidato.titulo, "marca": a.candidato.marca,
                         "preco_centavos": a.candidato.preco_centavos, "imagem": a.candidato.imagem,
                         "ean": a.candidato.ean, "status": a.status}
                        for a in avaliar_candidatos(especificacao, candidatos, vocabulario)[:POR_LOJA]]
            grupos.append({"loja_id": loja.id, "loja": loja.nome, "produtos": produtos})
    finally:
        cliente.close()
    total = sum(len(g["produtos"]) for g in grupos)
    com_produto = sum(1 for g in grupos if g["produtos"])
    return {"item_id": p["item_id"], "termo": termo, "lojas": grupos, "avisos": avisos,
            "mensagem": f"{total} produto(s) em {com_produto} de {len(grupos)} loja(s)"}
