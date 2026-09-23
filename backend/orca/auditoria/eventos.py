"""Auditoria automática: toda gravação pelo ORM gera um registro em `evento`.

Regras aplicadas antes de cada gravação (princípios 2 e 6):
- a sessão precisa declarar o autor (`sessao.info["autor"]`, ver orca.banco.sessao_como);
- nada é apagado: `sessao.delete(...)` é recusado (use exclusão lógica);
- registros imutáveis não podem ser alterados.
Os gatilhos do banco repetem as duas últimas regras para qualquer outro acesso.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from orca.banco.base import Base, agora
from orca.banco.tabelas import Evento
from orca.dominio import Autor


class ErroAuditoria(RuntimeError):
    """Gravação recusada por violar as regras de histórico."""


def _json(valor: Any) -> Any:
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def _preencher_padroes(obj: Base) -> None:
    """Aplica os valores padrão das colunas já agora (ex.: id), para o evento conhecê-los."""
    for coluna in inspect(obj).mapper.columns:
        chave = inspect(obj).mapper.get_property_by_column(coluna).key
        padrao = coluna.default
        if padrao is None or getattr(obj, chave) is not None:
            continue
        if padrao.is_callable:
            setattr(obj, chave, padrao.arg(None))
        elif padrao.is_scalar:
            setattr(obj, chave, padrao.arg)


def _fotografia(obj: Base) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    return {a.key: _json(getattr(obj, a.key)) for a in mapper.column_attrs}


def _mudancas(obj: Base) -> tuple[dict[str, Any], dict[str, Any]]:
    estado = inspect(obj)
    antes, depois = {}, {}
    for atributo in estado.mapper.column_attrs:
        historico = estado.attrs[atributo.key].history
        if historico.has_changes():
            antes[atributo.key] = _json(historico.deleted[0]) if historico.deleted else None
            depois[atributo.key] = _json(historico.added[0]) if historico.added else None
    return antes, depois


def _identificador(obj: Base) -> str:
    chave = inspect(obj).mapper.primary_key_from_instance(obj)
    return "/".join(str(parte) for parte in chave)


def _projeto(obj: Base) -> str | None:
    metodo = getattr(obj, "_projeto_id", None)
    return metodo() if metodo else None


def _acao(antes: dict, depois: dict) -> str:
    if "excluido_em" in depois and antes.get("excluido_em") is None and depois["excluido_em"] is not None:
        return "excluir"
    if "arquivado_em" in depois and antes.get("arquivado_em") is None and depois["arquivado_em"] is not None:
        return "arquivar"
    return "alterar"


@event.listens_for(Session, "before_flush")
def _auditar(sessao: Session, _contexto, _instancias) -> None:
    novos = [o for o in sessao.new if isinstance(o, Base) and not isinstance(o, Evento)]
    alterados = [
        o
        for o in sessao.dirty
        if isinstance(o, Base) and not isinstance(o, Evento) and sessao.is_modified(o, include_collections=False)
    ]
    if sessao.deleted:
        nomes = sorted({type(o).__tablename__ for o in sessao.deleted})
        raise ErroAuditoria(
            f"Registros nunca são apagados no Orça.AI ({', '.join(nomes)}). "
            "Use a exclusão lógica (preencher excluido_em)."
        )
    if any(isinstance(o, Evento) for o in sessao.dirty if sessao.is_modified(o)):
        raise ErroAuditoria("O histórico (evento) não pode ser alterado.")
    if not (novos or alterados):
        return

    valor_autor = sessao.info.get("autor")
    if not valor_autor:
        raise ErroAuditoria("Toda gravação precisa de autor: abra a sessão com sessao_como(fabrica, autor).")
    autor = str(Autor(valor_autor))
    momento = agora()

    with sessao.no_autoflush:
        for obj in alterados:
            if getattr(type(obj), "__imutavel__", False):
                raise ErroAuditoria(
                    f"{type(obj).__tablename__} é imutável: crie um novo registro em vez de alterar."
                )
        for obj in novos:  # primeiro todos os ids, para os filhos acharem o projeto
            _preencher_padroes(obj)
        for obj in novos:
            imutavel = getattr(type(obj), "__imutavel__", False)
            sessao.add(
                Evento(
                    projeto_id=_projeto(obj),
                    entidade=type(obj).__tablename__,
                    entidade_id=_identificador(obj),
                    acao="criar",
                    antes=None,
                    depois=None if imutavel else _fotografia(obj),
                    autor=autor,
                    criado_em=momento,
                )
            )
        for obj in alterados:
            antes, depois = _mudancas(obj)
            if not depois:
                continue
            sessao.add(
                Evento(
                    projeto_id=_projeto(obj),
                    entidade=type(obj).__tablename__,
                    entidade_id=_identificador(obj),
                    acao=_acao(antes, depois),
                    antes=antes,
                    depois=depois,
                    autor=autor,
                    criado_em=momento,
                )
            )
