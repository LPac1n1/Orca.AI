"""Correspondências gravadas: cada decisão "é o mesmo produto?" vira um registro imutável.

- O programa grava o resultado da cascata (origem `ean` ou `atributos`).
- Uma pessoa pode confirmar (promover 🟡 para 🟢, sempre manual — princípio 4) ou
  recusar; a decisão é um registro novo com origem `humano`, e o anterior fica no histórico.
- A decisão que vale é a mais recente.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco.tabelas import Correspondencia, Item, Observacao
from orca.correspondencia import Anuncio, Especificacao, ResultadoCorrespondencia, Vocabulario, comparar
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


def corresponder(sessao: Session, item: Item, observacao: Observacao, vocabulario: Vocabulario) -> Correspondencia:
    """Compara o item com a observação (sem IA) e grava o resultado."""
    if observacao.alvo_tipo != "item" or observacao.item is not item:
        raise ErroCorrespondencia("A observação não é deste item.")
    resultado = comparar(especificacao_do_item(item), anuncio_da_observacao(observacao), vocabulario)
    return registrar_correspondencia(sessao, item, observacao, resultado)


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
