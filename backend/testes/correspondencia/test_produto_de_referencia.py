"""Produto de referência (D-71): as outras lojas comparadas com a página que uma pessoa confirmou."""

import pytest

from orca.coleta import ler_vocabulario
from orca.correspondencia import Anuncio, Especificacao, comparar, comparar_com_referencia


@pytest.fixture(scope="module")
def vocabulario():
    return ler_vocabulario()


# o caso do piloto (25/09/2026): o item não diz a gramatura; a Kalunga trouxe o de 90 g e a Gimba o de 75 g
ITEM = Especificacao("Folha sulfite 500 Folhas", "papel", "Chamex")
REFERENCIA = Anuncio("Papel Sulfite Chamex A4 Branco 210x297mm 75g Resma 500 FL", "CHAMEX", "7891173023001")


def test_atributo_diferente_do_da_referencia_e_outro_produto(vocabulario):
    pagina = Anuncio("Papel Sulfite Chamex A4 90g, Maior Espessura, 210x297mm, 500 Folhas", "Chamex", "7891173023063")
    assert comparar(ITEM, pagina, vocabulario).status.value == "amarelo"  # só pelo item, não dá para saber
    r = comparar_com_referencia(ITEM, REFERENCIA, pagina, vocabulario)
    assert r.status.value == "vermelho" and "75 g/m² × 90 g/m²" in r.motivos[0]
    assert r.motivos[0].startswith("diferente do produto de referência")


def test_mesmo_codigo_de_barras_da_referencia(vocabulario):
    pagina = Anuncio("Papel Sulfite A4 75g Chamex 500 folhas branco", "Chamex", "7891173023001")
    r = comparar_com_referencia(ITEM, REFERENCIA, pagina, vocabulario)
    assert (r.status.value, r.origem.value) == ("verde", "ean")
    assert r.motivos == ("mesmo código de barras do produto de referência",)


def test_sem_codigo_e_sem_certeza_continua_amarelo(vocabulario):
    pagina = Anuncio("Papel Chamex A4 pacote c/ 500 fl.", None, None)
    assert comparar_com_referencia(ITEM, REFERENCIA, pagina, vocabulario).status.value == "amarelo"


def test_marca_diferente_do_item_continua_vermelho(vocabulario):
    pagina = Anuncio("Papel Sulfite Report A4 75g 500 folhas", "Report", "7891173023001")  # até com o mesmo código
    assert comparar_com_referencia(ITEM, REFERENCIA, pagina, vocabulario).status.value in ("vermelho", "amarelo")
    assert comparar_com_referencia(ITEM, REFERENCIA, pagina, vocabulario).status.value != "verde"


def test_codigo_do_item_vale_mais_que_o_da_referencia(vocabulario):
    item = Especificacao("Papel sulfite A4 75g 500 folhas", "papel", "Chamex", ean="7891173023063")
    pagina = Anuncio("Papel Sulfite A4 75g Chamex 500 folhas", "Chamex", "7891173023001")
    r = comparar_com_referencia(item, REFERENCIA, pagina, vocabulario)
    assert r.status.value != "verde"  # o código escrito no item não bate: quem confirma é a pessoa
