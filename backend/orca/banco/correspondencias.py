"""Correspondências gravadas: cada decisão "é o mesmo produto?" vira um registro imutável.

- O programa grava o resultado da cascata (origem `ean` ou `atributos`).
- Uma pessoa pode confirmar (promover 🟡 para 🟢, sempre manual — princípio 4) ou
  recusar; a decisão é um registro novo com origem `humano`, e o anterior fica no histórico.
- A decisão que vale é a mais recente.
- Produto de referência (D-71): a página que uma pessoa confirmou como o item; as outras são
  comparadas também com ela (mesmo código de barras, mesmos atributos).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco.tabelas import Correspondencia, Decisao, Item, Observacao
from orca.correspondencia import (
    Anuncio,
    Especificacao,
    ResultadoCorrespondencia,
    Vocabulario,
    comparar,
    comparar_com_referencia,
)
from orca.dominio import Autor, OrigemCorrespondencia, StatusCorrespondencia
from orca.regras import PerfilRegras as Regras


class ErroCorrespondencia(RuntimeError):
    pass


def especificacao_do_item(item: Item) -> Especificacao:
    return Especificacao(
        descricao=item.descricao,
        categoria=item.categoria,
        marca=item.marca,
        modelo=item.modelo,
        apresentacao=item.apresentacao,
        atributos={k: str(v) for k, v in (item.atributos or {}).items()},
        ean=item.ean,
    )


def anuncio_da_observacao(observacao: Observacao) -> Anuncio:
    complemento = " ".join(p for p in (observacao.modelo, observacao.apresentacao) if p)
    return Anuncio(observacao.titulo or "", observacao.marca, observacao.ean, complemento)


def registrar_correspondencia(
    sessao: Session, item: Item, observacao: Observacao, resultado: ResultadoCorrespondencia
) -> Correspondencia:
    if Autor(sessao.info["autor"]).tipo == "ia" and resultado.status is StatusCorrespondencia.VERDE:
        raise ErroCorrespondencia("A IA nunca promove uma correspondência para 🟢 (princípio 4).")
    correspondencia = Correspondencia(
        item=item,
        observacao=observacao,
        status=resultado.status.value,
        origem=resultado.origem.value,
        motivos=list(resultado.motivos),
        autor=sessao.info["autor"],
    )
    sessao.add(correspondencia)
    return correspondencia


def comparar_observacao(sessao: Session, item: Item, observacao: Observacao,
                        vocabulario: Vocabulario) -> ResultadoCorrespondencia:
    """A cascata, com o produto de referência do item quando há um (D-71). Não grava."""
    referencia = referencia_do_item(sessao, item)
    especificacao, anuncio = especificacao_do_item(item), anuncio_da_observacao(observacao)
    if referencia is not None and referencia.id != observacao.id:
        return comparar_com_referencia(especificacao, anuncio_da_observacao(referencia), anuncio, vocabulario)
    return comparar(especificacao, anuncio, vocabulario)


def corresponder(sessao: Session, item: Item, observacao: Observacao, vocabulario: Vocabulario) -> Correspondencia:
    """Compara o item com a observação (sem IA) e grava o resultado."""
    if observacao.alvo_tipo != "item" or observacao.item is not item:
        raise ErroCorrespondencia("A observação não é deste item.")
    return registrar_correspondencia(sessao, item, observacao, comparar_observacao(sessao, item, observacao, vocabulario))


# --- Produto de referência (D-71) ---------------------------------------------------------------

TIPO_REFERENCIA = "produto_referencia"


def referencia_do_item(sessao: Session, item: Item) -> Observacao | None:
    """A página escolhida como referência, enquanto a decisão vigente dela for 🟢 de uma pessoa."""
    decisao = sessao.scalars(
        select(Decisao)
        .where(Decisao.tipo == TIPO_REFERENCIA, Decisao.alvo_tipo == "item", Decisao.alvo_id == item.id)
        .order_by(Decisao.criado_em.desc(), Decisao.id.desc())
    ).first()
    if decisao is None or not (decisao.valor or {}).get("observacao"):
        return None
    observacao = sessao.get(Observacao, decisao.valor["observacao"])
    if observacao is None or observacao.item_id != item.id:
        return None
    vigente = correspondencia_vigente(sessao, item.id, observacao.id)
    if vigente is None or vigente.status != StatusCorrespondencia.VERDE.value \
            or vigente.origem != OrigemCorrespondencia.HUMANO.value:
        return None
    return observacao


def definir_referencia(sessao: Session, item: Item, observacao: Observacao, justificativa: str) -> Decisao:
    """Escolha de uma pessoa: esta página é o produto de referência do item (D-71)."""
    if Autor(sessao.info["autor"]).tipo != "usuario":
        raise ErroCorrespondencia("Só uma pessoa escolhe o produto de referência.")
    if observacao.item_id != item.id:
        raise ErroCorrespondencia("A observação não é deste item.")
    if not justificativa or not justificativa.strip():
        raise ErroCorrespondencia("Informe a justificativa da decisão.")
    decisao = Decisao(tipo=TIPO_REFERENCIA, alvo_tipo="item", alvo_id=item.id, valor={"observacao": observacao.id},
                      justificativa=justificativa.strip(), autor=sessao.info["autor"])
    sessao.add(decisao)
    return decisao


def decidir_correspondencia(
    sessao: Session, item: Item, observacao: Observacao, status: StatusCorrespondencia | str, justificativa: str
) -> Correspondencia:
    """Decisão de uma pessoa (confirmar 🟢 ou recusar 🔴), com justificativa."""
    if Autor(sessao.info["autor"]).tipo != "usuario":
        raise ErroCorrespondencia("Só uma pessoa decide a correspondência manualmente (princípio 4).")
    if not justificativa or not justificativa.strip():
        raise ErroCorrespondencia("Informe a justificativa da decisão.")
    status = StatusCorrespondencia(status)
    correspondencia = Correspondencia(
        item=item,
        observacao=observacao,
        status=status.value,
        origem=OrigemCorrespondencia.HUMANO.value,
        motivos=[justificativa.strip()],
        autor=sessao.info["autor"],
    )
    sessao.add(correspondencia)
    return correspondencia


def correspondencia_vigente(sessao: Session, item_id: str, observacao_id: str) -> Correspondencia | None:
    """A decisão mais recente para o par (item, observação)."""
    return sessao.scalars(
        select(Correspondencia)
        .where(Correspondencia.item_id == item_id, Correspondencia.observacao_id == observacao_id)
        .order_by(Correspondencia.criado_em.desc(), Correspondencia.id.desc())
    ).first()


def vale_como_verde(correspondencia: Correspondencia | None, regras: Regras) -> bool:
    """🟢 que já pode ser usado na seleção, conforme os níveis de automação do perfil.

    🟢 por código de barras ou por atributos com nível `com_aprovacao` espera a
    confirmação de uma pessoa (decisão `humano`).
    """
    if correspondencia is None or correspondencia.status != StatusCorrespondencia.VERDE.value:
        return False
    if correspondencia.origem == OrigemCorrespondencia.HUMANO.value:
        return True
    niveis = {
        OrigemCorrespondencia.EAN.value: regras.automacao.correspondencia_ean,
        OrigemCorrespondencia.ATRIBUTOS.value: regras.automacao.correspondencia_atributos,
    }
    return niveis.get(correspondencia.origem) == "automatico"
