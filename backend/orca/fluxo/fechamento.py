"""Fechar o lote (D-72): o que falta para as 3 lojas terem todos os itens, a partir do estado gravado.

Uma loja "tem" o item quando há página dele que não foi recusada (🔴): as 🟡 contam, porque
podem ser confirmadas. Os itens a confirmar são os que ainda não têm produto de referência
(D-71) e têm alguma página 🟡 (ou 🟢 que o perfil manda confirmar). Nada é gravado aqui.
"""

from dataclasses import dataclass

from orca.banco import vale_como_verde
from orca.fluxo.estado import EstadoLote
from orca.regras import PerfilRegras

LOJAS_DA_COTACAO = 3


@dataclass(frozen=True)
class LojaNoLote:
    id: str
    nome: str
    tem: tuple[str, ...]  # itens com página não recusada
    faltam: tuple[str, ...]


@dataclass(frozen=True)
class Fechamento:
    lojas: tuple[LojaNoLote, ...]  # da mais completa para a menos
    melhores: tuple[LojaNoLote, ...]  # as 3 mais completas
    faltando: dict[str, tuple[str, ...]]  # item → lojas (entre as melhores) que não o têm
    a_confirmar: tuple[str, ...]  # itens sem produto de referência, com página a confirmar


def _status(estado: EstadoLote, loja_id: str, item_id: str):
    obs = estado.observacoes.get((loja_id, item_id))
    return estado.correspondencias.get((item_id, obs.id)) if obs is not None else None


def fechamento(estado: EstadoLote, regras: PerfilRegras, quantas: int = LOJAS_DA_COTACAO) -> Fechamento:
    itens = [i.id for i in estado.itens]
    lojas = []
    for loja in estado.lojas:
        if loja.id in estado.retiradas:
            continue
        tem = tuple(i for i in itens if i in loja.ofertas
                    and ((c := _status(estado, loja.id, i)) is None or c.status != "vermelho"))
        lojas.append(LojaNoLote(loja.id, loja.nome, tem, tuple(i for i in itens if i not in tem)))
    lojas.sort(key=lambda l: (-len(l.tem), l.nome, l.id))
    melhores = tuple(lojas[:quantas])
    faltando = {i: tuple(l.nome for l in melhores if i in l.faltam) for i in itens}
    faltando = {i: nomes for i, nomes in faltando.items() if nomes}
    a_confirmar = []
    for i in itens:
        if i in estado.referencias:
            continue
        for loja in estado.lojas:
            c = _status(estado, loja.id, i) if i in loja.ofertas else None
            if c is not None and (c.status == "amarelo" or (c.status == "verde" and not vale_como_verde(c, regras))):
                a_confirmar.append(i)
                break
    return Fechamento(tuple(lojas), melhores, faltando, tuple(a_confirmar))
