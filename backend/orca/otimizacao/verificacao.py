"""Verificação independente (docs/03 §4.6).

Recalcula tudo do zero a partir das quantidades e horas encontradas, com o módulo de
cálculo (sem o OR-Tools): arredondamentos, totais, teto, C3, C4 e limites. Se algo
não bater, a solução não pode ser usada.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from orca.calculo import arredondar_centavos, formatar
from orca.otimizacao.modelo import ProblemaTeto


@dataclass(frozen=True)
class ResultadoVerificacao:
    totais: dict[str, int]
    valores_mensais: dict[str, int]
    total_centavos: int
    problemas: list[str]


def verificar(p: ProblemaTeto, quantidades: Mapping[str, int], horas: Mapping[str, int]) -> ResultadoVerificacao:
    problemas: list[str] = []
    totais: dict[str, int] = {}
    mensais: dict[str, int] = {}

    for l in p.materiais:
        q = quantidades[l.id]
        if not l.qtd_min <= q <= l.qtd_max:
            problemas.append(f"{l.nome}: quantidade {q} fora dos limites {l.qtd_min}–{l.qtd_max}")
        totais[l.id] = l.preco_centavos * q * l.meses

    for l in p.mao_de_obra:
        h = horas[l.id]
        if not l.horas_min_centesimos <= h <= l.horas_max_centesimos:
            problemas.append(f"{l.nome}: horas {h / 100:.2f} fora dos limites")
        if h > l.horas_legais_centesimos:
            problemas.append(f"{l.nome}: horas acima da jornada legal")
        mensais[l.id] = arredondar_centavos(Fraction(l.valor_hora_centavos * h, 100))
        totais[l.id] = mensais[l.id] * l.meses * l.postos

    total = sum(totais.values()) + p.fixos_centavos
    if total != p.teto_centavos:
        problemas.append(f"O total {formatar(total)} é diferente do teto {formatar(p.teto_centavos)}")

    meses = {l.id: l.meses for l in p.materiais}
    for lote in p.lotes:
        def total_loja(loja: str, lote=lote) -> int:
            return sum(quantidades[i] * preco * meses[i] for i, preco in lote.precos[loja].items())

        escolhida = total_loja(lote.escolhida)
        if lote.manter_escolhida:
            for outra in lote.outras_do_trio:
                if escolhida > total_loja(outra):
                    problemas.append(f"Lote {lote.lote}: a loja escolhida deixou de ter o menor total (C3)")
        if lote.manter_classificacao:
            referencia = lote.outras_do_trio or (lote.escolhida,)
            for fora in lote.fora_do_trio:
                if any(total_loja(fora) < total_loja(dentro) for dentro in referencia):
                    problemas.append(f"Lote {lote.lote}: uma loja fora do trio ficou mais barata (C4)")

    for limite in p.limites:
        soma = sum(v for l, v in totais.items() if _orcamento(p, l) == limite.orcamento)
        if limite.min_centavos is not None and soma < limite.min_centavos:
            problemas.append(f"Rubrica {limite.orcamento}: {formatar(soma)} abaixo do mínimo")
        if limite.max_centavos is not None and soma > limite.max_centavos:
            problemas.append(f"Rubrica {limite.orcamento}: {formatar(soma)} acima do máximo")

    return ResultadoVerificacao(totais, mensais, total, problemas)


def _orcamento(p: ProblemaTeto, linha: str) -> str:
    for l in (*p.materiais, *p.mao_de_obra):
        if l.id == linha:
            return l.orcamento
    raise KeyError(linha)
