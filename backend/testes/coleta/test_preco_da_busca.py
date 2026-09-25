"""Página sem o preço nos dados (WooCommerce, produto com variações): vale o preço da busca, se estiver na página.

Piloto da Fase 2, rodada 2 (25/09/2026): a Pedagógica e a Papel Mais Cia acharam a caneta e o lápis, mas a
página não traz o preço nos dados estruturados; o preço aparece no resultado da busca e na página.
"""

import json

from apoio_coleta import USUARIO, captura_falsa
from orca.banco import Item, sessao_como
from orca.coleta import ler_catalogo, registrar_captura, registrar_observacao_item

CATALOGO = ler_catalogo()
TEXTO = "Caneta Bic Cristal Azul Caixa c/50 Ponta 1.0mm R$ 48,98 · CNPJ 45.403.243/0001-09"


def _registrar(fabrica, armazem, ids, texto, preco_da_busca):
    captura = captura_falsa(url="https://pedagogica.com.br/produto/caneta-cristal-cx50un-azul/",
                            html="<html><body>sem dados do produto</body></html>", texto=texto)
    with sessao_como(fabrica, USUARIO) as s:
        evidencia = registrar_captura(s, armazem, captura)
        r = registrar_observacao_item(s, s.get(Item, ids["item"]), captura, evidencia, catalogo=CATALOGO,
                                      preco_da_busca=preco_da_busca)
        s.flush()
        return r.observacao.preco_centavos, r.observacao.preco_no_html, r.avisos, json.loads(r.observacao.dados_brutos)


def test_preco_da_busca_escrito_na_pagina_vale(fabrica, armazem, ids):
    preco, conferido, avisos, brutos = _registrar(fabrica, armazem, ids, TEXTO, 4898)
    assert (preco, conferido) == (4898, True)
    assert any("mostrado pela busca da loja e está escrito na página" in a for a in avisos)
    assert brutos["preco_da_busca"] == 4898


def test_preco_da_busca_que_nao_esta_na_pagina_nao_vale(fabrica, armazem, ids):
    preco, _, avisos, _ = _registrar(fabrica, armazem, ids, TEXTO.replace("48,98", "52,00"), 4898)
    assert preco is None  # princípio 5: o preço é o da prova, nunca o da busca sozinho
    assert any("preço não encontrado na página" in a for a in avisos)


def test_produto_em_falta_na_loja(fabrica, armazem, ids):
    """Piloto, 25/09/2026: o suco existia no Atacadão, mas em falta; o sistema mandava abrir na janela."""
    captura = captura_falsa(url="https://www.atacadao.com.br/suco-del-valle-100--uva-62894/p",
                            html="<html><body>sem dados</body></html>",
                            texto="Suco Del Valle 100% Uva 1L · Produto indisponível · Avise-me quando chegar")
    with sessao_como(fabrica, USUARIO) as s:
        evidencia = registrar_captura(s, armazem, captura)
        r = registrar_observacao_item(s, s.get(Item, ids["item"]), captura, evidencia, catalogo=CATALOGO)
        assert r.observacao.disponivel is False and r.observacao.preco_centavos is None
        assert "o produto está indisponível (em falta) nesta loja" in r.avisos
        assert not any("informe o preço" in a for a in r.avisos)
