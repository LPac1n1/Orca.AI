"""Cotação: médias, Regra A, conferência da Regra B (docs/03 §2)."""

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from orca.calculo import ComparacaoMedia, Cotacao


def test_media_exata_e_exibida():
    c = Cotacao((795, 860, 690))  # R$ 7,95 · R$ 8,60 · R$ 6,90
    assert c.soma == 2345
    assert c.media_exata == Fraction(2345, 3)  # 7,8166…
    assert c.media_exibida == 782  # 7,82
    assert c.preco_regra_a() == 782


def test_media_dos_totais_difere_de_quantidade_vezes_media():
    """Exemplo de docs/03 §2: 2 × 7,82 = 15,64, mas a média dos totais é 15,63."""
    c = Cotacao((795, 860, 690))
    assert c.totais(2) == (1590, 1720, 1380)
    assert c.media_dos_totais(2) == 1563
    assert 2 * c.media_exibida == 1564


@pytest.mark.parametrize(
    ("precos", "preco_escolhido", "dentro"),
    [
        # Números reais de uma grade comparativa (só preços)
        ((3450, 3450, 3390), 3450, False),  # folha sulfite: 34,50 > média 34,30
        ((3450, 3450, 3390), 3390, True),
        ((1120, 990, 959), 1120, False),  # grampo: 11,20 > média 10,23
        ((11640, 10990, 13669), 11640, True),  # perfurador: 116,40 ≤ média 121,00
        ((919, 849, 990), 919, True),  # álcool: 9,19 ≤ média 9,1933…
        ((949, 799, 879), 949, False),  # suco de uva: 9,49 > média 8,7566…
    ],
)
def test_regra_b_media_exata(precos, preco_escolhido, dentro):
    assert Cotacao(precos).dentro_da_media(preco_escolhido) is dentro


def test_media_exata_e_mais_rigorosa_que_a_exibida():
    """7,82 é igual à média exibida, mas passa da média exata 7,8166… (P-02)."""
    c = Cotacao((795, 860, 690))
    assert c.dentro_da_media(782, ComparacaoMedia.EXIBIDA) is True
    assert c.dentro_da_media(782, ComparacaoMedia.EXATA) is False
    assert c.dentro_da_media(781) is True


@pytest.mark.parametrize("precos", [(), (100, 0, 200), (100, -5, 200), (100, 1.5, 200), [100, 200, 300]])
def test_recusa_precos_invalidos(precos):
    with pytest.raises((ValueError, TypeError)):
        Cotacao(precos)


precos3 = st.tuples(*(st.integers(min_value=1, max_value=10**8),) * 3)


@given(precos3)
def test_menor_preco_sempre_dentro_da_media(precos):
    assert Cotacao(precos).dentro_da_media(min(precos)) is True


@given(precos3, st.integers(min_value=1, max_value=10**8))
def test_exata_implica_exibida(precos, preco):
    c = Cotacao(precos)
    if c.dentro_da_media(preco, ComparacaoMedia.EXATA):
        assert c.dentro_da_media(preco, ComparacaoMedia.EXIBIDA)


@given(precos3, st.integers(min_value=0, max_value=10**4))
def test_media_dos_totais_perto_de_quantidade_vezes_media(precos, qtd):
    c = Cotacao(precos)
    assert abs(c.media_dos_totais(qtd) - qtd * c.media_exata) <= Fraction(1, 2)
