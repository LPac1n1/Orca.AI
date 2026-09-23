"""Vocabulário de atributos de texto (catalogos/atributos.yaml): valores que se excluem.

Cada atributo de texto (tipo, sabor, fragrância, cor, apresentação…) tem grupos de
valores. Dentro de um grupo, os valores se excluem: café "tradicional" não é café
"extra forte". Cada valor tem os seus sinônimos ("extra forte", "extraforte").
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from orca.correspondencia.texto import normalizar


@dataclass(frozen=True)
class Grupo:
    atributo: str
    nome: str
    valores: Mapping[str, tuple[str, ...]]  # valor → sinônimos normalizados


@dataclass(frozen=True)
class Vocabulario:
    sempre: tuple[str, ...]
    categorias: Mapping[str, tuple[str, ...]]
    grupos: tuple[Grupo, ...] = field(default=())

    @classmethod
    def de_dados(cls, dados: Mapping) -> "Vocabulario":
        """A partir do conteúdo de catalogos/atributos.yaml."""
        grupos = []
        for atributo, por_grupo in (dados.get("vocabulario") or {}).items():
            for nome, valores in por_grupo.items():
                normalizados = {}
                for valor, sinonimos in valores.items():
                    lista = sinonimos if isinstance(sinonimos, list) else [sinonimos] if sinonimos else []
                    lista = lista or [valor.replace("_", " ")]  # sem sinônimos: o próprio nome
                    normalizados[valor] = tuple(dict.fromkeys(normalizar(s) for s in lista))
                grupos.append(Grupo(atributo, nome, normalizados))
        return cls(
            sempre=tuple(dados.get("sempre") or ()),
            categorias={k: tuple(v) for k, v in (dados.get("categorias") or {}).items()},
            grupos=tuple(grupos),
        )

    def atributos_da_categoria(self, categoria: str | None) -> tuple[str, ...] | None:
        if categoria is None:
            return None
        chave = normalizar(categoria).replace(" ", "_")
        if chave not in self.categorias:
            return None
        return tuple(dict.fromkeys([*self.sempre, *self.categorias[chave]]))

    def grupos_de(self, atributo: str) -> tuple[Grupo, ...]:
        return tuple(g for g in self.grupos if g.atributo == atributo)


@dataclass(frozen=True)
class ValoresNoTexto:
    valores: frozenset[str]
    trechos: tuple[tuple[int, int], ...]


def valores_no_texto(grupo: Grupo, texto: str) -> ValoresNoTexto:
    """Valores do grupo citados no texto normalizado; o sinônimo mais longo vence ("extra forte" ≠ "forte")."""
    candidatos = sorted(
        ((sinonimo, valor) for valor, sinonimos in grupo.valores.items() for sinonimo in sinonimos),
        key=lambda par: len(par[0]),
        reverse=True,
    )
    ocupado: list[tuple[int, int]] = []
    achados: set[str] = set()
    for sinonimo, valor in candidatos:
        if not sinonimo:
            continue
        padrao = rf"(?<![a-z0-9]){re.escape(sinonimo)}(?![a-z0-9])"
        for m in re.finditer(padrao, texto):
            if any(i < m.end() and m.start() < f for i, f in ocupado):
                continue
            ocupado.append((m.start(), m.end()))
            achados.add(valor)
    return ValoresNoTexto(frozenset(achados), tuple(ocupado))
