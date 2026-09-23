"""Otimização do teto exato: T-06, T-07, T-08, conflitos, verificação e determinismo (docs/03 §4)."""

import pytest

from orca.otimizacao import (
    LimiteRubrica,
    LinhaMaoDeObra,
    LinhaMaterial,
    ProblemaTeto,
    RestricaoLote,
    SemSolucao,
    SolucaoTeto,
    faixa,
    fechar_teto,
    verificar,
)


def material(id, preco, qtd, meses=1, faixa_qtd=None, orcamento="mat", nome=None):
    qmin, qmax = faixa_qtd or faixa(qtd, -20, 20)
    return LinhaMaterial(id, nome or f"Item {id.upper()}", orcamento, preco, qtd, meses, qmin, qmax)


def cargo(id, valor_hora, horas, meses=12, postos=1, legais=22000, orcamento="mo"):
    hmin, hmax = faixa(horas, -20, 20)
    return LinhaMaoDeObra(id, f"Cargo {id.upper()}", orcamento, valor_hora, horas, meses, postos, hmin, min(hmax, legais), legais)


@pytest.mark.parametrize(
    ("planejado", "margem", "travado", "esperado"),
    [(20, (-20, 20), False, (16, 24)), (1, (-20, 20), False, (1, 1)), (7, (-20, 20), False, (6, 8)), (7, (-20, 20), True, (7, 7)), (0, (-20, 20), False, (0, 0))],
)
def test_faixa(planejado, margem, travado, esperado):
    assert faixa(planejado, *margem, travado) == esperado


# --- T-06: teto exato viável ---------------------------------------------------


# Teto montado a partir de uma solução conhecida: X = 21, Y = 10, 91,43 h → R$ 25.746,20.
# Planejado (X = 20, Y = 10, 91,50 h) dá R$ 25.731,50: o otimizador precisa ajustar.
TETO_MISTO = 3390 * 21 + 959 * 10 + 12 * ((2273 * 9143 + 50) // 100)


def _problema_misto():
    x = material("x", 3390, 20, orcamento="materiais")
    y = material("y", 959, 10, orcamento="materiais")
    lote = RestricaoLote(
        lote="Papelaria",
        escolhida="E",
        outras_do_trio=("A", "B"),
        fora_do_trio=("D",),
        precos={
            "E": {"x": 3390, "y": 959},
            "A": {"x": 3450, "y": 990},
            "B": {"x": 3450, "y": 1120},
            "D": {"x": 3600, "y": 900},  # D só fica atrás de B enquanto 150·x ≥ 220·y (C4)
        },
    )
    return ProblemaTeto(TETO_MISTO, materiais=(x, y), mao_de_obra=(cargo("c", 2273, 9150),), lotes=(lote,))


def test_fecha_o_teto_exato_ao_centavo():
    p = _problema_misto()
    r = fechar_teto(p)
    assert isinstance(r, SolucaoTeto), getattr(r, "mensagem", "")
    assert TETO_MISTO == 2_574_620
    assert r.total_centavos == TETO_MISTO
    assert r.verificacao_ok, r.verificacao
    assert r.otima
    # O valor mensal do cargo é o arredondamento comercial de valor-hora × horas (D-43)
    assert r.valores_mensais["c"] == (2273 * r.horas_centesimos["c"] + 50) // 100
    assert 1 <= len(r.alteracoes) <= 3


def test_mesma_entrada_mesma_saida():
    a, b = fechar_teto(_problema_misto()), fechar_teto(_problema_misto())
    assert (a.quantidades, a.horas_centesimos) == (b.quantidades, b.horas_centesimos)


def test_nada_muda_se_o_planejado_ja_fecha():
    p = ProblemaTeto(975_00, materiais=(material("a", 1250, 20), material("b", 750, 50), material("c", 2500, 14)))
    r = fechar_teto(p)
    assert r.total_centavos == 97_500 and r.alteracoes == ()


def test_muda_o_menor_numero_de_linhas():
    p = ProblemaTeto(1_000_00, materiais=(material("a", 1250, 20), material("b", 750, 50), material("c", 2500, 14)))
    r = fechar_teto(p)
    assert [(a.linha, a.de, a.para) for a in r.alteracoes] == [("c", 14, 15)]


def test_custo_de_alteracao_desvia_para_outra_linha():
    caro = LinhaMaterial("c", "Item C", "mat", 2500, 14, 1, 11, 16, custo_alteracao=10)
    p = ProblemaTeto(1_000_00, materiais=(material("a", 1250, 20), material("b", 750, 50), caro))
    assert "c" not in {a.linha for a in fechar_teto(p).alteracoes}


def test_c3_e_c4_respeitados():
    r = fechar_teto(_problema_misto())
    q = r.quantidades
    total = {loja: sum(q[i] * preco for i, preco in precos.items()) for loja, precos in _problema_misto().lotes[0].precos.items()}
    assert total["E"] <= total["A"] and total["E"] <= total["B"]  # C3
    assert total["D"] >= total["A"] and total["D"] >= total["B"]  # C4


# --- Verificação independente ---------------------------------------------------


def test_verificacao_aponta_teto_limites_e_regras():
    p = _problema_misto()
    resultado = verificar(p, {"x": 16, "y": 12}, {"c": 9150})
    texto = " | ".join(resultado.problemas)
    assert "quantidade" not in texto  # 16 e 12 estão nas margens
    assert "diferente do teto" in texto
    assert "(C4)" in texto


# --- T-07: sem solução por divisibilidade --------------------------------------


def test_divisibilidade():
    p = ProblemaTeto(1_001_00, materiais=(material("a", 1250, 20), material("b", 750, 50), material("c", 2500, 14)))
    r = fechar_teto(p)
    assert isinstance(r, SemSolucao) and r.motivo == "divisibilidade"
    assert r.mensagem == (
        "As linhas ajustáveis só mudam o total em múltiplos de R$ 2,50; do mínimo até o teto faltam R$ 201,00, "
        "que não é múltiplo de R$ 2,50."
    )
    assert any("Trocar algum produto" in s.mensagem for s in r.sugestoes)


def test_mao_de_obra_ajustavel_quebra_a_divisibilidade():
    """Materiais em passos de R$ 2,50: com as horas travadas, R$ 3.000,00 é impossível;
    liberando as horas (passos de ~R$ 0,23), fecha (solução conferida por força bruta)."""
    materiais = (material("a", 1250, 20), material("b", 750, 50), material("c", 2500, 14))
    travado = LinhaMaoDeObra("h", "Cargo H", "mo", 2273, 9150, 1, 1, 9150, 9150, 22000)
    r = fechar_teto(ProblemaTeto(300_000, materiais=materiais, mao_de_obra=(travado,)))
    assert isinstance(r, SemSolucao) and r.motivo == "divisibilidade"
    r = fechar_teto(ProblemaTeto(300_000, materiais=materiais, mao_de_obra=(cargo("h", 2273, 9150, meses=1),)))
    assert isinstance(r, SolucaoTeto) and r.total_centavos == 300_000 and r.verificacao_ok
    assert r.horas_centesimos["h"] != 9150


# --- T-08: sem solução por limites ----------------------------------------------


def test_limites():
    p = ProblemaTeto(2_000_00, materiais=(material("a", 1250, 20), material("b", 750, 50)))
    r = fechar_teto(p)
    assert isinstance(r, SemSolucao) and r.motivo == "limites"
    # máximo: 24 × 12,50 + 60 × 7,50 = 750,00
    assert r.mensagem == "Mesmo com todas as quantidades e horas no máximo, o total é R$ 750,00, R$ 1.250,00 abaixo do teto."
    assert r.sugestoes and all(s.tipo == "margem" for s in r.sugestoes)
    assert "Item A: permitir" in r.sugestoes[0].mensagem or "Item B: permitir" in r.sugestoes[0].mensagem


# --- Conflitos de regras --------------------------------------------------------


def test_conflito_com_limite_de_rubrica():
    # A rubrica "mat" pode ir até R$ 3.000,00 e a mão de obra até ~R$ 272,76: não chega a R$ 3.500,00.
    # Conferido por força bruta: sem o limite, ou com as horas livres, existe solução exata.
    p = ProblemaTeto(
        3_500_00,
        materiais=(material("a", 1299, 100, orcamento="mat"), material("b", 757, 200, orcamento="mat")),
        mao_de_obra=(cargo("h", 2273, 1000, meses=1, orcamento="mo"),),
        limites=(LimiteRubrica("mat", max_centavos=3_000_00),),
    )
    r = fechar_teto(p)
    assert isinstance(r, SemSolucao) and r.motivo == "conflito"
    assert "limite da rubrica mat" in r.conflitos and "limites de Cargo H" in r.conflitos
    limite = next(s for s in r.sugestoes if s.tipo == "limite_rubrica")
    assert limite.mensagem.startswith("Rubrica mat: precisaria de R$ ") and "(limite atual — a R$ 3.000,00)" in limite.mensagem
    horas = next(s for s in r.sugestoes if s.tipo == "margem" and s.alvo == "h")
    assert horas.mensagem.startswith("Cargo H: permitir ") and "h por mês" in horas.mensagem


def test_conflito_com_a_loja_escolhida():
    x = material("x", 100, 10, faixa_qtd=(10, 10))  # travado
    y = material("y", 500, 1, faixa_qtd=(0, 10))
    lote = RestricaoLote(
        "L", "E", ("A", "B"), (),
        {"E": {"x": 100, "y": 500}, "A": {"x": 150, "y": 300}, "B": {"x": 160, "y": 310}},
    )
    r = fechar_teto(ProblemaTeto(3_500, materiais=(x, y), lotes=(lote,)))
    assert isinstance(r, SemSolucao) and r.motivo == "conflito"
    assert "loja escolhida continua a mais barata no lote L (C3)" in r.conflitos
    tipos = {s.tipo for s in r.sugestoes}
    assert "trio" in tipos and "margem" in tipos
    destravar = next(s for s in r.sugestoes if s.tipo == "margem" and s.alvo == "x")
    assert destravar.mensagem.startswith("Destravar a linha — Item X: permitir")


def test_problema_invalido():
    with pytest.raises(ValueError):
        ProblemaTeto(100)  # sem linhas
    with pytest.raises(ValueError):
        ProblemaTeto(100, materiais=(material("a", 100, 1), material("a", 100, 1)))
    with pytest.raises(ValueError):
        LinhaMaoDeObra("h", "H", "mo", 2273, 9150, 12, 1, 9000, 23000, 22000)  # acima da jornada legal
