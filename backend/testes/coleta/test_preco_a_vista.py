"""D-60 (revisada no piloto, 24/09/2026): o preço no Pix; sem Pix, o do boleto; nunca o parcelado.

Os textos são das páginas reais capturadas no piloto (só produto e preço).
"""

import pytest

from orca.coleta import preco_a_vista, precos_rotulados

LEPOK = "Informação do Produto | (8) Clique e veja!\nR$ 16,59 no boleto ou PIX\nou R$ 17,10 em 1x\nver parcelas\nComprar"
GIMBA = "Cod. 9558365 Produtos: POST-IT\nPor apenas R$ 19,90\nno PIX (3% desconto)\nDisponível"
GIMBA_VITRINE = "Post-it 38x50mm 100 FL 3 avaliações por apenas R$ 19,90 R$ 19,30 no PIX (3% desc.) Bloco de Notas"
KALUNGA = "(Total de 400 Folhas), 3M - PT 4 UN R$ 19,30 Calcular frete e prazo de entrega"
LEPOK_VITRINE = "Código: 20162 R$ 74,59 3% OFF no boleto ou PIX ou em até 1x de R$ 76,90 Adicionar"


@pytest.mark.parametrize("lido, texto, esperado, forma", [
    (1710, LEPOK, 1659, "pix_ou_boleto"),       # o preço dos dados da página era o parcelado
    (1990, GIMBA, 1990, "pix"),                 # a página só mostra o preço no Pix
    (1990, GIMBA_VITRINE, 1930, "pix"),         # "R$ 19,90 R$ 19,30 no PIX"
    (7690, LEPOK_VITRINE, 7459, "pix_ou_boleto"),
])
def test_preco_no_pix_ou_boleto(lido, texto, esperado, forma):
    escolha = preco_a_vista(lido, texto)
    assert (escolha.centavos, escolha.forma) == (esperado, forma)


def test_sem_rotulo_vale_o_preco_da_pagina():
    assert preco_a_vista(1930, KALUNGA) is None


def test_parcelado_nunca_e_escolhido():
    formas = {r.centavos: r.forma for r in precos_rotulados(1710, LEPOK)}
    assert formas == {1659: "pix_ou_boleto", 1710: "parcelado"}
    assert {r.centavos: r.forma for r in precos_rotulados(7690, LEPOK_VITRINE)}[7690] == "parcelado"
    assert preco_a_vista(1000, "R$ 10,00 em até 3x de R$ 3,33 sem juros") is None


def test_boleto_quando_nao_ha_pix():
    texto = "R$ 50,00 no cartão ou R$ 47,50 no boleto bancário"
    assert (preco_a_vista(5000, texto).centavos, preco_a_vista(5000, texto).forma) == (4750, "boleto")


def test_pix_tem_prioridade_sobre_boleto():
    texto = "R$ 50,00 · R$ 48,00 no boleto · R$ 47,00 no Pix"
    assert preco_a_vista(5000, texto).forma == "pix"


def test_rotulo_antes_do_valor():
    assert preco_a_vista(2000, "Preço R$ 20,00 · No Pix: R$ 19,40").centavos == 1940


def test_valor_de_outro_produto_nao_entra():
    # preço no Pix muito menor que o do produto: é de outro produto da vitrine
    assert preco_a_vista(10000, "R$ 100,00 · Veja também: caneta R$ 5,00 no PIX") is None
