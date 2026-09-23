"""Avaliação da correspondência num conjunto de pares rotulados (T-11; D-64, D-65).

Usada pelo teste do repositório e pelo próprio sistema antes de salvar uma mudança
no vocabulário ou no catálogo de atributos: nenhuma mudança pode criar um 🟢 errado.
"""

import csv
import io
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources

from orca.correspondencia.comparar import Anuncio, Especificacao, comparar
from orca.correspondencia.vocabulario import Vocabulario


@dataclass(frozen=True)
class Par:
    """Dois produtos e o rótulo dado por uma pessoa (ou pelo código de barras igual)."""

    titulo_a: str
    titulo_b: str
    rotulo: str  # "mesmo" | "diferente"
    categoria: str | None = None
    marca_a: str | None = None
    marca_b: str | None = None
    ean_a: str | None = None
    ean_b: str | None = None
    origem: str = "sistema"  # sistema | decisao | ean | usuario
    id: str = ""


@dataclass(frozen=True)
class Avaliacao:
    contagem: dict[str, int]  # "diferente:verde", "mesmo:vermelho"…
    falsos_verdes: tuple[Par, ...]  # diferente → 🟢 (proibido)
    iguais_recusados: tuple[Par, ...]  # mesmo → 🔴
    total: int = 0
    resultados: dict[str, str] = field(default_factory=dict)  # id do par → status

    @property
    def aprovada(self) -> bool:
        return not self.falsos_verdes

    def taxa(self, rotulo: str, status: str) -> float:
        base = sum(n for chave, n in self.contagem.items() if chave.startswith(rotulo + ":"))
        return self.contagem.get(f"{rotulo}:{status}", 0) / base if base else 0.0


def pares_do_sistema() -> list[Par]:
    """O conjunto de referência distribuído com o programa (364 pares reais em 23/09/2026)."""
    texto = resources.files("orca.correspondencia").joinpath("referencia/pares_referencia.csv").read_text(encoding="utf-8")
    return [
        Par(r["titulo_a"], r["titulo_b"], r["rotulo"], r["categoria"] or None, r["marca_a"] or None, r["marca_b"] or None,
            r["ean_a"] or None, r["ean_b"] or None, "sistema", f"sistema:{r['id']}")
        for r in csv.DictReader(io.StringIO(texto))
    ]


def avaliar(pares: Iterable[Par], vocabulario: Vocabulario, com_ean: bool = False) -> Avaliacao:
    """Compara cada par. Sem código de barras (padrão), mede só os atributos: é o caso mais difícil."""
    contagem: Counter[str] = Counter()
    falsos, recusados, resultados = [], [], {}
    n = 0
    for par in pares:
        n += 1
        item = Especificacao(par.titulo_a, par.categoria, par.marca_a, ean=par.ean_a if com_ean else None)
        anuncio = Anuncio(par.titulo_b, par.marca_b, par.ean_b if com_ean else None)
        status = comparar(item, anuncio, vocabulario).status.value
        contagem[f"{par.rotulo}:{status}"] += 1
        resultados[par.id] = status
        if par.rotulo == "diferente" and status == "verde":
            falsos.append(par)
        if par.rotulo == "mesmo" and status == "vermelho":
            recusados.append(par)
    return Avaliacao(dict(contagem), tuple(falsos), tuple(recusados), n, resultados)
