"""Tarefa da Saída 1 com busca (D-23; Fase 2, etapa 14): produto alternativo nas mesmas 3 lojas.

Item acima da média na Regra B: o sistema procura o item sem a marca nas lojas do trio,
junta os produtos que aparecem nelas e faz a conta de sempre (`trocar_produto`) com os
preços da prévia da busca. Nada é gravado aqui: a pessoa escolhe uma alternativa, e só
então o produto é trocado e as páginas são capturadas como prova (rota `usar-alternativa`).
"""

from dataclasses import replace

import httpx

from orca.banco import Item, especificacao_do_item, sessao_como
from orca.busca import Candidato, ErroBusca, Ritmo, lojas_de_busca, termo_de_busca
from orca.busca.alternativas import especificacao_sem_marca, produtos_nas_lojas
from orca.calculo import formatar_exato
from orca.coleta import ErroCaptura, dominio_da_url, preco_a_vista
from orca.fluxo.catalogos import lojas_da_organizacao, vocabulario_da_organizacao
from orca.fluxo.estado import estado_do_projeto
from orca.selecao import AnaliseLote, Alternativa, Oferta, trocar_produto
from orca.tarefas.busca import _candidatos
from orca.tarefas.fila import ErroTarefa, Fila, TarefaCancelada, tarefa


def _preco_da_previa(c: Candidato) -> Candidato:
    """D-60 também na prévia: o preço no Pix ou no boleto, se o cartão da busca mostrar."""
    if c.preco_centavos and c.texto and (escolha := preco_a_vista(c.preco_centavos, c.texto)):
        return replace(c, preco_centavos=escolha.centavos)
    return c


@tarefa("buscar_alternativas")
def buscar_alternativas(fila: Fila, tarefa_id: str, p: dict) -> dict:
    ctx = fila.contexto
    ritmo = Ritmo(ctx.intervalo_busca_s)
    cancelamento = fila.cancelamento(tarefa_id)
    item_id = p["item_id"]
    with sessao_como(ctx.fabrica, "sistema:busca") as s:
        item = s.get(Item, item_id)
        if item is None or item.excluido_em is not None:
            raise ErroTarefa("O item não existe mais (foi trocado ou retirado).")
        projeto = item.lote.orcamento.projeto
        estado = estado_do_projeto(s, projeto, ctx.jornadas, ctx.hoje())
        estado_lote = next(l for _, l in estado.lotes() if l.lote.id == item.lote_id)
        analise = estado_lote.analise
        if not isinstance(analise, AnaliseLote) or item_id not in {v.item.id for v in analise.violacoes}:
            raise ErroTarefa("O item não está acima da média: não há o que resolver.")
        buscas = {dominio_da_url("https://" + l.dominio): l
                  for l in lojas_de_busca(lojas_da_organizacao(s, projeto.organizacao_id)) if l.automatica}
        trio = []  # (loja do trio, busca dessa loja ou None)
        for lc in analise.trio:
            obs = estado_lote.observacoes.get((lc.loja.id, item_id))
            trio.append((lc.loja, buscas.get(dominio_da_url(obs.url)) if obs else None))
        especificacao = especificacao_do_item(item)
        vocabulario = vocabulario_da_organizacao(s, projeto.organizacao_id)
        itens_lote = estado_lote.itens_lote
    escolhida = trio[0][0]
    if trio[0][1] is None:
        raise ErroTarefa(f"A loja {escolhida.nome} não tem busca automática: procure nela um produto de outra marca "
                         "e troque o produto à mão.")

    generico = especificacao_sem_marca(especificacao)
    termo = termo_de_busca(generico)
    candidatos: dict[str, list[Candidato]] = {}
    avisos = []
    cliente = ctx.cliente_http() if ctx.cliente_http else httpx.Client()
    try:
        for n, (loja, busca) in enumerate(trio):
            if cancelamento.is_set():
                raise TarefaCancelada()
            fila.progresso(tarefa_id, int(90 * n / len(trio)), f"{loja.nome}: “{termo}”")
            if busca is None:
                avisos.append(f"{loja.nome} não tem busca automática: confira nela você mesmo")
                continue
            try:
                achados = _candidatos(fila, cliente, ritmo, busca, item_id, termo, generico, vocabulario, {}, set())
            except (ErroBusca, ErroCaptura) as erro:
                avisos.append(f"{loja.nome}: {erro}")
                continue
            candidatos[loja.id] = [_preco_da_previa(c) for c in achados]
    finally:
        cliente.close()

    produtos = produtos_nas_lojas(especificacao, escolhida.id, candidatos, vocabulario)
    alternativas = [Alternativa(str(n), pr.titulo, {l: Oferta(preco) for l, preco in pr.precos.items() if preco})
                    for n, pr in enumerate(produtos)]
    opcoes = []
    for o in trocar_produto(itens_lote, analise, item_id, alternativas):
        produto = produtos[int(o.alternativa.id)]
        faltam = [l.nome for l, _ in trio if l.id not in produto.urls]
        sem_preco = [l.nome for l, _ in trio if l.id in produto.urls and not produto.precos[l.id]]
        if faltam:
            situacao, motivo = "incompleta", "não apareceu na busca de: " + ", ".join(faltam)
        elif sem_preco:
            situacao, motivo = "sem_preco", "a busca não mostrou o preço em: " + ", ".join(sem_preco)
        else:
            situacao, motivo = ("resolve" if o.valida else "nao_resolve"), o.motivo
        opcoes.append({
            "titulo": produto.titulo, "marca": produto.marca, "situacao": situacao, "motivo": motivo,
            "lojas": [{"loja_id": l.id, "loja": l.nome, "url": produto.urls.get(l.id),
                       "preco_centavos": produto.precos.get(l.id)} for l, _ in trio],
            "media": formatar_exato(o.cotacao.media_exata) if o.cotacao and situacao != "incompleta" else None,
            "impacto_centavos": o.impacto_centavos if situacao in ("resolve", "nao_resolve") else None,
        })
    resolvem = sum(1 for o in opcoes if o["situacao"] == "resolve")
    if not opcoes:
        mensagem = f"Nenhum produto de outra marca apareceu na busca da {escolhida.nome} (termo: “{termo}”)."
    else:
        mensagem = (f"{resolvem} de {len(opcoes)} alternativa(s) resolveriam pela prévia da busca" if resolvem
                    else f"Nenhuma das {len(opcoes)} alternativa(s) resolveria pela prévia da busca")
    return {"item_id": item_id, "termo": termo, "escolhida": escolhida.nome,
            "lojas": [{"loja_id": l.id, "loja": l.nome, "busca": b.nome if b else None} for l, b in trio],
            "opcoes": opcoes, "avisos": avisos, "mensagem": mensagem}
