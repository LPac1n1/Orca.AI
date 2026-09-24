"""Pendências da pesquisa: validade das observações (D-12, T-10) e fila de comprovantes (D-14).

Uma observação é "vigente" enquanto for a mais recente do mesmo item (ou cargo) na
mesma página. Refazer a pesquisa cria outra observação; a antiga continua no
histórico, mas deixa de ser vigente e os alertas dela são encerrados.
"""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco import Alerta, Cargo, Comprovante, Item, Lote, Observacao, Orcamento, Projeto, agora, perfil_do_projeto
from orca.dominio import normalizar_cnpj
from orca.evidencias import SituacaoValidade, comprovante_reaproveitavel, hoje_em_brasilia, validade

TIPO_ALERTA = {
    SituacaoValidade.VENCIDA: ("pesquisa_vencida", "problema"),
    SituacaoValidade.VENCE_ANTES_DA_ENTREGA: ("pesquisa_vence_antes_da_entrega", "problema"),
    SituacaoValidade.VENCE_EM_BREVE: ("pesquisa_vence_em_breve", "atencao"),
}
TIPOS_DE_VALIDADE = tuple(tipo for tipo, _ in TIPO_ALERTA.values())


def observacoes_do_projeto(sessao: Session, projeto: Projeto) -> list[Observacao]:
    """Todas as observações de itens e cargos ativos do projeto (vigentes ou não)."""
    itens = (
        select(Item.id)
        .join(Lote, Item.lote_id == Lote.id)
        .join(Orcamento, Lote.orcamento_id == Orcamento.id)
        .where(
            Orcamento.projeto_id == projeto.id,
            Item.excluido_em.is_(None), Lote.excluido_em.is_(None), Orcamento.excluido_em.is_(None),
        )
    )
    cargos = (
        select(Cargo.id)
        .join(Orcamento, Cargo.orcamento_id == Orcamento.id)
        .where(Orcamento.projeto_id == projeto.id, Cargo.excluido_em.is_(None), Orcamento.excluido_em.is_(None))
    )
    return list(
        sessao.scalars(
            select(Observacao)
            .where(Observacao.item_id.in_(itens) | Observacao.cargo_id.in_(cargos))
            .order_by(Observacao.coletado_em, Observacao.id)
        )
    )


def vigentes(observacoes: Iterable[Observacao]) -> list[Observacao]:
    """A mais recente de cada (item ou cargo, página)."""
    ultima: dict[tuple, Observacao] = {}
    for obs in observacoes:
        chave = (obs.alvo_tipo, obs.item_id or obs.cargo_id, obs.url)
        if chave not in ultima or _ordem(obs) > _ordem(ultima[chave]):
            ultima[chave] = obs
    return sorted(ultima.values(), key=_ordem)


def _ordem(obs: Observacao) -> tuple:
    """Da captura mais antiga para a mais nova; na mesma captura, a gravada por último (preço corrigido)."""
    return (obs.coletado_em, obs.criado_em, obs.id)


def _alertas_abertos(sessao: Session, projeto: Projeto) -> dict[tuple[str, str], Alerta]:
    alertas = sessao.scalars(
        select(Alerta).where(
            Alerta.projeto_id == projeto.id,
            Alerta.alvo_tipo == "observacao",
            Alerta.tipo.in_(TIPOS_DE_VALIDADE),
            Alerta.resolvido_em.is_(None),
        )
    )
    return {(a.alvo_id, a.tipo): a for a in alertas}


def _mensagem(obs: Observacao, situacao: SituacaoValidade, valida_ate: date, entrega: date | None) -> str:
    nome = obs.titulo or obs.url
    ate = valida_ate.strftime("%d/%m/%Y")
    if situacao is SituacaoValidade.VENCIDA:
        return f"A pesquisa de “{nome}” venceu em {ate}. Refaça a pesquisa."
    if situacao is SituacaoValidade.VENCE_ANTES_DA_ENTREGA:
        return (
            f"A pesquisa de “{nome}” vale até {ate}, antes da entrega prevista do projeto "
            f"({entrega.strftime('%d/%m/%Y')}). Refaça a pesquisa perto da entrega."
        )
    return f"A pesquisa de “{nome}” vence em breve ({ate})."


def conferir_validade(sessao: Session, projeto: Projeto, hoje: date | None = None) -> list[Alerta]:
    """Cria os alertas de validade que faltam e encerra os que não valem mais. Devolve os novos."""
    hoje = hoje or hoje_em_brasilia()
    regras = perfil_do_projeto(sessao, projeto).regras.fontes
    abertos = _alertas_abertos(sessao, projeto)
    novos: list[Alerta] = []
    manter: set[tuple[str, str]] = set()
    for obs in vigentes(observacoes_do_projeto(sessao, projeto)):
        v = validade(obs.coletado_em, hoje, regras.validade_dias, regras.aviso_vencimento_dias, projeto.data_entrega)
        if v.situacao is SituacaoValidade.VALIDA:
            continue
        tipo, severidade = TIPO_ALERTA[v.situacao]
        manter.add((obs.id, tipo))
        if (obs.id, tipo) in abertos:
            continue
        alerta = Alerta(
            projeto=projeto,
            tipo=tipo,
            severidade=severidade,
            alvo_tipo="observacao",
            alvo_id=obs.id,
            mensagem=_mensagem(obs, v.situacao, v.valida_ate, projeto.data_entrega),
        )
        sessao.add(alerta)
        novos.append(alerta)
    momento = agora()
    for chave, alerta in abertos.items():
        if chave not in manter:  # pesquisa refeita, ou a situação mudou (ex.: de "em breve" para "vencida")
            alerta.resolvido_em = momento
    return novos


# --- Comprovantes da Receita ----------------------------------------------------------


def comprovante_valido(sessao: Session, cnpj: str, hoje: date, reaproveitar_dias: int) -> Comprovante | None:
    """O comprovante mais recente do CNPJ, se ainda puder ser reaproveitado (D-14)."""
    recente = sessao.scalars(
        select(Comprovante)
        .where(Comprovante.cnpj == normalizar_cnpj(cnpj))
        .order_by(Comprovante.emitido_em.desc())
    ).first()
    if recente and comprovante_reaproveitavel(recente.emitido_em, hoje, reaproveitar_dias):
        return recente
    return None


def comprovantes_pendentes(
    sessao: Session, cnpjs: Iterable[str], hoje: date | None = None, reaproveitar_dias: int = 30
) -> list[str]:
    """Fila de comprovantes a emitir: CNPJs sem comprovante reaproveitável, sem repetição, na ordem dada."""
    hoje = hoje or hoje_em_brasilia()
    fila: list[str] = []
    for bruto in cnpjs:
        cnpj = normalizar_cnpj(bruto)
        if cnpj not in fila and comprovante_valido(sessao, cnpj, hoje, reaproveitar_dias) is None:
            fila.append(cnpj)
    return fila


def cnpjs_do_projeto(sessao: Session, projeto: Projeto) -> list[str]:
    """CNPJs de vendedores e empresas das observações vigentes do projeto."""
    vistos: list[str] = []
    for obs in vigentes(observacoes_do_projeto(sessao, projeto)):
        if obs.cnpj_vendedor and obs.cnpj_vendedor not in vistos:
            vistos.append(obs.cnpj_vendedor)
    return vistos
