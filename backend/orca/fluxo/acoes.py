"""Ações do usuário que mudam o orçamento. Cada uma é uma decisão gravada (princípios 2 e 8).

Nada é apagado: retirar uma loja é uma decisão (que pode ser desfeita por outra),
trocar um produto cria um item novo que substitui o anterior (o antigo fica no histórico).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco import Cargo, Correspondencia, Decisao, Item, Lote, Observacao, agora, corresponder
from orca.correspondencia import Vocabulario
from orca.dominio import Autor
from orca.fluxo.estado import EstadoLote
from orca.selecao import ParametrosSelecao, ResultadoTrocaLoja, trocar_loja


class ErroAcao(RuntimeError):
    pass


def _exigir_pessoa(sessao: Session, acao: str) -> None:
    if Autor(sessao.info["autor"]).tipo != "usuario":
        raise ErroAcao(f"Só uma pessoa pode {acao}.")


def _exigir_justificativa(justificativa: str) -> str:
    if not justificativa or not justificativa.strip():
        raise ErroAcao("Informe a justificativa.")
    return justificativa.strip()


def _decidir(sessao: Session, tipo: str, alvo_tipo: str, alvo_id: str, valor: dict, justificativa: str) -> Decisao:
    decisao = Decisao(tipo=tipo, alvo_tipo=alvo_tipo, alvo_id=alvo_id, valor=valor, justificativa=justificativa,
                      autor=sessao.info["autor"])
    sessao.add(decisao)
    return decisao


def simular_troca_de_loja(estado_lote: EstadoLote, parametros: ParametrosSelecao) -> ResultadoTrocaLoja:
    """Saída 2 (D-23): o que acontece retirando a loja escolhida, uma de cada vez. Só mostra; não grava."""
    lojas = [l for l in estado_lote.lojas if l.id not in estado_lote.retiradas]
    return trocar_loja(estado_lote.itens_lote, lojas, parametros)


def retirar_loja(sessao: Session, lote: Lote, loja_id: str, justificativa: str) -> Decisao:
    """Retira a loja do lote (ex.: loja escolhida com item acima da média, Saída 2). Escolha do usuário (D-23)."""
    _exigir_pessoa(sessao, "retirar uma loja do lote")
    return _decidir(sessao, "retirar_loja", "lote", lote.id, {"loja": loja_id}, _exigir_justificativa(justificativa))


def devolver_loja(sessao: Session, lote: Lote, loja_id: str, justificativa: str) -> Decisao:
    _exigir_pessoa(sessao, "devolver uma loja ao lote")
    return _decidir(sessao, "devolver_loja", "lote", lote.id, {"loja": loja_id}, _exigir_justificativa(justificativa))


def marcar_mesma_vaga(sessao: Session, cargo: Cargo, vaga_a: str, vaga_b: str, justificativa: str) -> Decisao:
    """Caso 🟡 de duplicidade: o usuário confirma que as duas vagas são a mesma (D-49)."""
    _exigir_pessoa(sessao, "confirmar vagas repetidas")
    return _decidir(sessao, "mesma_vaga", "cargo", cargo.id, {"a": vaga_a, "b": vaga_b}, _exigir_justificativa(justificativa))


CAMPOS_DO_ITEM = ("descricao", "categoria", "marca", "modelo", "apresentacao", "atributos", "ean", "catmat", "unidade",
                  "qtd_planejada", "mes_inicio", "mes_fim", "margem_min_percentual", "margem_max_percentual", "travado")


def substituir_item(sessao: Session, item: Item, justificativa: str, **mudancas) -> Item:
    """Saída 1 (D-23): troca o produto. Cria um item novo; o antigo sai do orçamento e fica no histórico."""
    _exigir_pessoa(sessao, "trocar o produto de um item")
    desconhecidos = set(mudancas) - set(CAMPOS_DO_ITEM)
    if desconhecidos:
        raise ErroAcao(f"Campos desconhecidos: {', '.join(sorted(desconhecidos))}")
    dados = {campo: getattr(item, campo) for campo in CAMPOS_DO_ITEM} | mudancas
    novo = Item(lote=item.lote, substitui_item_id=item.id, **dados)
    item.excluido_em = agora()
    sessao.add(novo)
    sessao.flush()
    _decidir(sessao, "trocar_produto", "item", item.id, {"novo_item": novo.id}, _exigir_justificativa(justificativa))
    return novo


def corresponder_pendentes(sessao: Session, lotes: list[Lote], vocabulario: Vocabulario) -> list[Correspondencia]:
    """Compara (sem IA) as observações que ainda não têm correspondência. Grava com o autor da sessão."""
    itens = [i for l in lotes for i in l.itens if i.excluido_em is None]
    if not itens:
        return []
    ja_decididas = set(sessao.scalars(select(Correspondencia.observacao_id).where(
        Correspondencia.item_id.in_([i.id for i in itens]))))
    novas = []
    por_id = {i.id: i for i in itens}
    for obs in sessao.scalars(select(Observacao).where(
        Observacao.item_id.in_(list(por_id)), Observacao.encontrado.is_(True)
    ).order_by(Observacao.coletado_em, Observacao.id)):
        if obs.id not in ja_decididas:
            novas.append(corresponder(sessao, por_id[obs.item_id], obs, vocabulario))
    return novas
