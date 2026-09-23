"""Leitura de medidas e normalização de textos de produtos."""

from fractions import Fraction

from orca.correspondencia.medidas import (
    Quantidade,
    comprimentos,
    concentracoes,
    dimensoes,
    folhas,
    formatos,
    gramaturas,
    numero,
    numeros_de_modelo,
    preparar,
    quantidades,
    tipos_numerados,
    unidades,
    voltagens,
)
from orca.correspondencia.texto import compacto, normalizar, palavras_significativas, raiz


def _valores(achados):
    return [a.valor for a in achados]


def _str(achados):
    return [str(a.valor) for a in achados]


def test_normalizar_e_raiz():
    assert normalizar("Café Pilão – Nº 103, 75 g/m²") == "cafe pilao - n° 103, 75 g/m2"
    assert normalizar(None) == ""
    assert raiz("folhas") == raiz("folha") and raiz(normalizar("moída")) == raiz("moido") == "moid"
    assert palavras_significativas("papel sulfite com 500 folhas pacote") == {"papel", "sulfite", "folh"}


def test_marca_compacta():
    assert compacto("Paper One") == compacto("PAPERONE")
    assert compacto("Três Corações") == compacto("3 CORACOES")


def test_numero_sem_float():
    assert numero("1,5") == Fraction(3, 2)
    assert numero("2.5") == Fraction(5, 2)
    assert numero("1.000") == 1000
    assert numero("5,02") == Fraction(502, 100)


def test_quantidades_em_gramas_e_mililitros():
    assert _valores(quantidades("cafe 1kg")) == _valores(quantidades("cafe 1.000 g"))
    assert _valores(quantidades("agua 1,5 l")) == [Quantidade("volume", 1, Fraction(1500))]
    assert _valores(quantidades("detergente 500ml")) == [Quantidade("volume", 1, Fraction(500))]
    assert _str(quantidades("capsulas 10x5,2g")) == ["10 × 5,2 g"]
    assert _str(quantidades("leite fermentado 6 x 75 g")) == ["6 × 75 g"]
    assert quantidades("papel 75 g/m2") == []  # gramatura não é peso
    assert quantidades("5 graos, 2 lavanda") == []
    assert _valores(quantidades("sabao 4kg", ("volume",))) == []


def test_promocoes_leve_pague():
    assert _str(quantidades(preparar("achocolatado lv 990g pg 900g"))) == ["990 g"]
    assert _valores(unidades(preparar("papel higienico leve 12 pague 11 rolos"))) == _valores(unidades("12 rolos"))
    assert _str(quantidades(preparar("desinfetante leve 1,75l pague 1,25l"))) == ["1750 ml"]
    assert "15" not in preparar("leite condensado 15% gratis 395g")


def test_papel():
    assert _str(gramaturas("papel a4 75g 500 folhas")) == ["75 g/m²"]
    assert _str(gramaturas("75 g/m2")) == _str(gramaturas("75gsm")) == ["75 g/m²"]
    assert _str(folhas("pt 500 fl")) == _str(folhas("500 folhas")) == _str(folhas("500fls")) == ["500 folhas"]
    assert _str(folhas("caixa 5.000 folhas")) == ["5000 folhas"]
    assert [str(v) for v in _valores(formatos("papel sulfite a4"))] == ["A4"]
    assert "A4" in _str(formatos("210mmx297mm")) and "A3" in _str(formatos("297x420mm"))
    assert _str(formatos("oficio")) == ["oficio"]


def test_unidades_na_embalagem():
    assert _str(unidades("copo 180ml 100 un")) == ["100 un"]
    assert _str(unidades("com 26 un")) == ["26 un"]
    assert _str(unidades("kit 2 cafe")) == ["2 un"]
    assert _str(unidades("acucar c/ 400 saches")) == ["400 un"]
    assert _str(unidades("capsulas 10x5,2g")) == ["10 un"]
    assert unidades("cafe com leite 200g") == []
    assert unidades("pacote com 500g") == []


def test_medidas_comprimento_concentracao_voltagem_modelo():
    assert _str(dimensoes("23cmx22cm")) == _str(dimensoes("22 x 23 cm")) == ["220x230 mm"]
    assert _str(dimensoes("30x29,5cm")) == ["295x300 mm"]
    assert _str(comprimentos("folha dupla 30m 12 rolos")) == ["30 m"]
    assert comprimentos("500ml") == [] and comprimentos("30x40m") == []
    assert _str(concentracoes("alcool 70°inpm")) == _str(concentracoes("alcool 70%")) == ["70 %"]
    assert _str(voltagens("ventilador 127v")) == ["127 V"] and _str(voltagens("bivolt")) == ["bivolt"]
    assert _str(numeros_de_modelo("filtro n° 103")) == ["103"]
    assert _str(tipos_numerados("arroz tipo 1 5kg")) == ["1"]
