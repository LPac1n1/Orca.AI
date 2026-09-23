"""Domínio: CNPJ (inclusive alfanumérico, D-19), código de barras, autor e meses ativos. Caso T-15 (parte do DV)."""

import pytest

from orca.dominio import Autor, MesesAtivos, cnpj_raiz, formatar_cnpj, normalizar_cnpj, normalizar_gtin


@pytest.mark.parametrize(
    ("entrada", "normalizado"),
    [
        ("43.283.811/0001-50", "43283811000150"),  # Kalunga (levantamento de lojas)
        ("45.543.915/0001-81", "45543915000181"),  # Carrefour
        ("03.645.949/0001-37", "03645949000137"),  # CPIS 26 de Julho
        ("12.ABC.345/01DE-35", "12ABC34501DE35"),  # exemplo de CNPJ alfanumérico
        ("12abc34501de35", "12ABC34501DE35"),  # minúsculas são aceitas
    ],
)
def test_cnpj_valido(entrada, normalizado):
    assert normalizar_cnpj(entrada) == normalizado


@pytest.mark.parametrize(
    "entrada",
    ["43.283.811/0001-51", "12.ABC.345/01DE-36", "00.000.000/0000-00", "11111111111111", "1234", "12.ABC.345/01DE-3X", ""],
)
def test_cnpj_invalido(entrada):
    with pytest.raises(ValueError):
        normalizar_cnpj(entrada)


def test_cnpj_formatar_e_raiz():
    assert formatar_cnpj("12ABC34501DE35") == "12.ABC.345/01DE-35"
    assert formatar_cnpj("43283811000150") == "43.283.811/0001-50"
    assert cnpj_raiz("45.543.915/0001-81") == "45543915"


@pytest.mark.parametrize(
    "codigo",
    [
        "7896089012019",  # café (Carrefour e Extra — mesmo EAN)
        "7896089015164",
        "7897042200467",
        "96385074",  # GTIN-8
        "036000291452",  # GTIN-12 (UPC-A)
        "10012345678902",  # GTIN-14
    ],
)
def test_gtin_valido(codigo):
    assert normalizar_gtin(codigo) == codigo


@pytest.mark.parametrize("codigo", ["7896089012018", "789608901201", "abc", "12345", "96385075"])
def test_gtin_invalido(codigo):
    with pytest.raises(ValueError):
        normalizar_gtin(codigo)


@pytest.mark.parametrize("valor", ["usuario:Leonardo", "usuario:Maria da Silva", "sistema", "sistema:coleta", "ia:gemini/flash"])
def test_autor_valido(valor):
    assert str(Autor(valor)) == valor


@pytest.mark.parametrize("valor", ["", "Leonardo", "usuario:", "ia:", "sistema:Coleta Web", "admin:x"])
def test_autor_invalido(valor):
    with pytest.raises(ValueError):
        Autor(valor)


def test_meses_ativos():
    m = MesesAtivos(2, 11)
    assert m.quantidade == 10
    assert str(m) == "2º ao 11º mês"
    assert m.cabe_em(12) and not m.cabe_em(10)
    assert m.contem(2) and m.contem(11) and not m.contem(12)
    assert str(MesesAtivos(1, 1)) == "1º mês"
    for inicio, fim in ((0, 3), (5, 4), (1, True)):
        with pytest.raises(ValueError):
            MesesAtivos(inicio, fim)
