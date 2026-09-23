"""T-02 — Mão de obra (docs/03 §3; D-41 a D-44)."""

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from orca.calculo import calcular_mao_de_obra, centesimos_de_horas, divisor_mensal, formatar_horas


@pytest.mark.parametrize(("jornada", "divisor"), [(44, 220), (40, 200), (36, 180), (30, 150), (24, 120)])
def test_divisor_e_jornada_vezes_cinco(jornada, divisor):
    assert divisor_mensal(jornada) == divisor


def test_exemplo_da_especificacao():
    """Exemplo de docs/03 §3: regra geral (44 h), 91,5 h/mês, 12 meses."""
    r = calcular_mao_de_obra(
        salarios=(400100, 500000, 600100),
        jornada_semanal_horas=44,
        horas_mes_centesimos=9150,
        meses=12,
    )
    assert r.media_exata == Fraction(1500200, 3)
    assert r.media == 500067  # R$ 5.000,67
    assert r.divisor == 220
    assert r.valor_hora == 2273  # R$ 22,73
    assert r.valor_mensal_exato == Fraction(2079795, 10)  # R$ 2.079,795 (empate exato → sobe)
    assert r.valor_mensal == 207980  # R$ 2.079,80
    assert r.total == 2495760  # R$ 24.957,60
    assert r.memoria() == [
        "Média: (R$ 4.001,00 + R$ 5.000,00 + R$ 6.001,00) ÷ 3 = R$ 5.000,6666… → R$ 5.000,67",
        "Divisor: 44 h semanais × 5 = 220 h",
        "Valor-hora: R$ 5.000,67 ÷ 220 = R$ 22,7303… → R$ 22,73",
        "Valor mensal: R$ 22,73 × 91,50 h = R$ 2.079,795 → R$ 2.079,80",
        "Total: R$ 2.079,80 × 12 meses × 1 posto = R$ 24.957,60",
    ]


def test_assistente_social_30h():
    r = calcular_mao_de_obra((200100, 300100, 300100), 30, 4000, meses=10, postos=3)
    assert r.divisor == 150
    assert r.media == 266767  # R$ 2.667,67
    assert r.valor_hora == 1778  # 2.667,67 ÷ 150 = 17,7844… → 17,78
    assert r.valor_mensal == 71120  # 17,78 × 40 h
    assert r.total == 71120 * 10 * 3


@pytest.mark.parametrize(
    ("salarios", "jornada", "horas", "mensal_esperado"),
    [
        # A sequência D-43 reproduz os valores de um plano de aplicação real, aceito
        # pela secretaria, que usava divisores 180 e 120 (jornadas 36 h e 24 h).
        ((400100, 500000, 600100), 36, 9100, 252798),  # 27,78 × 91 h = 2.527,98
        ((200100, 300100, 300100), 24, 4000, 88920),  # 22,23 × 40 h = 889,20
        ((200100, 200100, 300100), 36, 9000, 116730),  # 12,97 × 90 h = 1.167,30
        ((200000, 217361, 232600), 36, 6000, 72240),  # 12,04 × 60 h = 722,40
        ((200100, 200100, 200100), 36, 7000, 77840),  # 11,12 × 70 h = 778,40
    ],
)
def test_reproduz_plano_real(salarios, jornada, horas, mensal_esperado):
    assert calcular_mao_de_obra(salarios, jornada, horas, meses=1).valor_mensal == mensal_esperado


def test_recusa_horas_acima_da_jornada_legal():
    with pytest.raises(ValueError, match="jornada legal"):
        calcular_mao_de_obra((300000,), 30, 15001, meses=1)  # 150,01 h > 150 h
    assert calcular_mao_de_obra((300000,), 30, 15000, meses=1).valor_mensal == 300000


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(salarios=(), jornada_semanal_horas=44, horas_mes_centesimos=100, meses=1),
        dict(salarios=(0,), jornada_semanal_horas=44, horas_mes_centesimos=100, meses=1),
        dict(salarios=(1000.5,), jornada_semanal_horas=44, horas_mes_centesimos=100, meses=1),
        dict(salarios=(1000,), jornada_semanal_horas=0, horas_mes_centesimos=100, meses=1),
        dict(salarios=(1000,), jornada_semanal_horas=44, horas_mes_centesimos=0, meses=1),
        dict(salarios=(1000,), jornada_semanal_horas=44, horas_mes_centesimos=100, meses=0),
        dict(salarios=(1000,), jornada_semanal_horas=44, horas_mes_centesimos=100, meses=1, postos=0),
    ],
)
def test_recusa_entradas_invalidas(kwargs):
    with pytest.raises(ValueError):
        calcular_mao_de_obra(**kwargs)


@pytest.mark.parametrize(("texto", "centesimos"), [("91,5", 9150), ("91,50", 9150), ("91", 9100), ("91.25", 9125), ("0,01", 1)])
def test_horas(texto, centesimos):
    assert centesimos_de_horas(texto) == centesimos


@pytest.mark.parametrize("texto", ["91,555", "-3", "abc", ""])
def test_horas_invalidas(texto):
    with pytest.raises(ValueError):
        centesimos_de_horas(texto)


def test_formatar_horas():
    assert formatar_horas(9150) == "91,50 h"


salarios = st.lists(st.integers(min_value=100_000, max_value=5_000_000), min_size=3, max_size=3)


@given(salarios, st.integers(min_value=1, max_value=22000), st.integers(1, 24), st.integers(1, 10))
def test_total_e_mensal_vezes_meses_vezes_postos(sal, horas, meses, postos):
    r = calcular_mao_de_obra(sal, 44, horas, meses, postos)
    assert r.total == r.valor_mensal * meses * postos


@given(salarios, st.integers(min_value=1, max_value=21999))
def test_mais_horas_nunca_diminui_o_valor(sal, horas):
    menos = calcular_mao_de_obra(sal, 44, horas, 1).valor_mensal
    mais = calcular_mao_de_obra(sal, 44, horas + 1, 1).valor_mensal
    assert mais >= menos
