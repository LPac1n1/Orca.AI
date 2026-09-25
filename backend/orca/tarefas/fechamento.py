"""Tarefa "Fechar o lote" (D-72): pesquisa tudo e sugere a troca dos itens que faltam nas 3 lojas.

1. Pesquisa todos os itens nas lojas escolhidas (D-68: sem parar quando falta um).
2. Vê quais itens faltam nas 3 lojas mais completas (`orca.fluxo.fechamento`).
3. Para cada um, procura o item sem a marca nessas 3 lojas e lista os produtos de outra marca
   que aparecem nas 3, do menor preço somado (prévia da busca) para o maior.

Nada é trocado aqui: a troca é da pessoa (princípio 8), pela rota `usar-alternativa`, e as
provas vêm das páginas capturadas depois.
"""

import httpx

from orca.banco import Lote, especificacao_do_item, sessao_como
from orca.busca import ErroBusca, Ritmo, lojas_de_busca, termo_de_busca
from orca.busca.alternativas import especificacao_sem_marca, produtos_nas_lojas
from orca.coleta import ErroCaptura, dominio_da_url
from orca.fluxo.catalogos import lojas_da_organizacao, vocabulario_da_organizacao
from orca.fluxo.estado import estado_do_projeto
from orca.fluxo.fechamento import fechamento
from orca.tarefas.alternativas import _preco_da_previa
from orca.tarefas.busca import _candidatos, _mensagem, pesquisar_lote
from orca.tarefas.fila import Fila, TarefaCancelada, tarefa

ITENS_PARA_TROCAR = 5  # itens com busca de outra marca por tarefa, no máximo (poucas requisições)
OPCOES_POR_ITEM = 5


def _estado_do_lote(ctx, s, lote_id: str):
    lote = s.get(Lote, lote_id)
    estado = estado_do_projeto(s, lote.orcamento.projeto, ctx.jornadas, ctx.hoje())
    return next((o, l) for o, l in estado.lotes() if l.lote.id == lote_id)


@tarefa("fechar_lote")
def fechar_lote(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    resumo, n_itens = pesquisar_lote(fila, tarefa_id, p["lote_id"], p["lojas"], progresso=(0, 70))
    cancelamento = fila.cancelamento(tarefa_id)

    with sessao_como(ctx.fabrica, "sistema:busca") as s:
        orcamento, estado_lote = _estado_do_lote(ctx, s, p["lote_id"])
        f = fechamento(estado_lote, orcamento.perfil.regras)
        organizacao_id = estado_lote.lote.orcamento.projeto.organizacao_id
        buscas = {dominio_da_url("https://" + l.dominio): l
                  for l in lojas_de_busca(lojas_da_organizacao(s, organizacao_id)) if l.automatica}
        busca_da_loja = {}
        for loja in f.melhores:
            obs = next((estado_lote.observacoes[(loja.id, i)] for i in loja.tem
                        if (loja.id, i) in estado_lote.observacoes), None)
            busca_da_loja[loja.id] = buscas.get(dominio_da_url(obs.url)) if obs else None
        especificacoes = {i.id: especificacao_do_item(i) for i in estado_lote.itens}
        nomes = {i.id: i.descricao for i in estado_lote.itens}
        vocabulario = vocabulario_da_organizacao(s, organizacao_id)

    alternativas: dict[str, list[dict]] = {}
    avisos = []
    faltando = list(f.faltando)[:ITENS_PARA_TROCAR]
    sem_busca = [l.nome for l in f.melhores if busca_da_loja.get(l.id) is None]
    if faltando and len(f.melhores) < 3:
        avisos.append("ainda não há 3 lojas com itens do lote: pesquise mais lojas")
    elif faltando and sem_busca:
        avisos.append("sem busca automática em " + ", ".join(sem_busca)
                      + ": procure lá, na janela, um produto de outra marca para os itens que faltam")
    elif faltando:
        ritmo = Ritmo(ctx.intervalo_busca_s)
        cliente = ctx.cliente_http() if ctx.cliente_http else httpx.Client()
        try:
            for n, item_id in enumerate(faltando):
                if cancelamento.is_set():
                    raise TarefaCancelada()
                fila.progresso(tarefa_id, 70 + int(29 * n / len(faltando)), f"outra marca: {nomes[item_id]}")
                alternativas[item_id] = _outras_marcas(fila, cliente, ritmo, f.melhores, busca_da_loja, item_id,
                                                        especificacoes[item_id], vocabulario, avisos)
        finally:
            cliente.close()

    resultado_lojas = [{"loja_id": l.id, "loja": l.nome, "tem": len(l.tem),
                        "faltam": [nomes[i] for i in l.faltam]} for l in f.lojas]
    com_opcao = sum(1 for opcoes in alternativas.values() if opcoes)
    partes = [_mensagem(resumo, n_itens)]
    if f.faltando:
        partes.append(f"{len(f.faltando)} item(ns) faltam nas 3 lojas mais completas; "
                      f"{com_opcao} com sugestão de outra marca")
    if f.a_confirmar:
        partes.append(f"{len(f.a_confirmar)} item(ns) para você confirmar o produto")
    return {"resumo": resumo, "lojas": resultado_lojas, "melhores": [l.id for l in f.melhores],
            "faltando": {i: list(lojas) for i, lojas in f.faltando.items()}, "alternativas": alternativas,
            "a_confirmar": list(f.a_confirmar), "avisos": avisos, "mensagem": " — ".join(partes)}


def _outras_marcas(fila, cliente, ritmo, melhores, busca_da_loja, item_id, especificacao, vocabulario,
                   avisos) -> list[dict]:
    """Produtos de outra marca que aparecem nas 3 lojas, do menor preço somado para o maior (D-72)."""
    generico = especificacao_sem_marca(especificacao)
    termo = termo_de_busca(generico)
    candidatos = {}
    for loja in melhores:
        try:
            achados = _candidatos(fila, cliente, ritmo, busca_da_loja[loja.id], item_id, termo, generico, vocabulario,
                                  {}, set())
        except (ErroBusca, ErroCaptura) as erro:
            avisos.append(f"{loja.nome}: {erro}")
            return []
        candidatos[loja.id] = [_preco_da_previa(c) for c in achados]
    opcoes = []
    for produto in produtos_nas_lojas(especificacao, melhores[0].id, candidatos, vocabulario, limite=12):
        if len(produto.urls) < len(melhores):
            continue  # só o que aparece nas 3
        precos = [produto.precos.get(l.id) for l in melhores]
        soma = sum(precos) if all(precos) else None
        opcoes.append({
            "titulo": produto.titulo, "marca": produto.marca, "soma_centavos": soma,
            "situacao": "completa" if soma is not None else "sem_preco",
            "motivo": "aparece nas 3 lojas" if soma is not None else "a busca não mostrou o preço em alguma loja",
            "lojas": [{"loja_id": l.id, "loja": l.nome, "url": produto.urls[l.id],
                       "preco_centavos": produto.precos.get(l.id)} for l in melhores],
        })
    opcoes.sort(key=lambda o: (o["soma_centavos"] is None, o["soma_centavos"] or 0))  # princípio 7: critério objetivo
    return opcoes[:OPCOES_POR_ITEM]
