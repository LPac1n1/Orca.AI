"""Lojas do levantamento de 25/09/2026 (docs/07 §5): buscas novas, lista de resultados e produto do mesmo tipo."""

import json

import httpx
import pytest

from orca.busca import (
    Candidato,
    Consulta,
    avaliar_candidatos,
    buscar_na_pagina,
    buscar_vtex_is,
    buscar_woocommerce,
    lojas_de_busca,
    termo_minimo,
)
from orca.busca.ranking import mesmo_tipo, parecenca
from orca.coleta import ler_atributos_dados, ler_catalogo_dados
from orca.correspondencia import Especificacao, Vocabulario
from orca.fluxo.catalogos import ErroCatalogo, validar_lojas

VOCABULARIO = Vocabulario.de_dados(ler_atributos_dados())
LOJAS = {l.id: l for l in lojas_de_busca(ler_catalogo_dados())}


def test_robots_txt_respeitado_e_lojas_novas():
    # o robots.txt da Gimba e da Tenda proíbe a busca por programas: só com janela (25/09/2026)
    assert LOJAS["gimba"].modo == "assistida" and LOJAS["tenda_atacado"].modo == "assistida"
    automaticas = {l.id for l in LOJAS.values() if l.automatica}
    por_categoria = {c: {i for i in automaticas if c in LOJAS[i].categorias}
                     for c in ("papelaria", "alimentos", "limpeza", "utensilios")}
    assert all(len(lojas) >= 3 for lojas in por_categoria.values()), por_categoria
    assert LOJAS["artpel"].seletor == ".list-product" and LOJAS["oba_hortifruti"].aceita_ean
    assert not LOJAS["pedagogica"].aceita_ean and LOJAS["pedagogica"].modo == "api_woocommerce"


def _cliente(corpo, pedidos):
    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, text=json.dumps(corpo))
    return httpx.Client(transport=httpx.MockTransport(responder))


def test_busca_nova_da_vtex():
    corpo = {"products": [
        {"productName": "Arroz Branco Tipo 1 Prato Fino 5kg", "brand": "PRATO FINO", "link": "/arroz-prato-fino-5-kg/p",
         "items": [{"ean": "7896290300011", "sellers": [{"commertialOffer": {"Price": 31.99}}]}]},
        {"productName": "Arroz Integral Prato Fino 1kg", "brand": "PRATO FINO", "link": "/arroz-integral/p",
         "items": [{"ean": "7896290300028", "sellers": [{"commertialOffer": {"Price": 0}}]}]},
    ]}
    pedidos = []
    with _cliente(corpo, pedidos) as c:
        por_texto = buscar_vtex_is(c, LOJAS["oba_hortifruti"], Consulta("arroz prato fino 5kg"))
        por_codigo = buscar_vtex_is(c, LOJAS["oba_hortifruti"], Consulta("arroz", "7896290300011"), regiao="v2.ABC")
    assert [x.url for x in por_texto] == ["https://www.obahortifruti.com.br/arroz-prato-fino-5-kg/p",
                                         "https://www.obahortifruti.com.br/arroz-integral/p"]
    assert [x.preco_centavos for x in por_texto] == [3199, None]  # preço 0 = sem preço (loja pede a região)
    assert [x.ean for x in por_codigo] == ["7896290300011"]  # pelo código, só o produto do código
    assert pedidos[0].url.params["query"] == "arroz prato fino 5kg"
    assert pedidos[1].url.params["query"] == "7896290300011" and pedidos[1].url.params["regionId"] == "v2.ABC"
    assert pedidos[0].headers["user-agent"].startswith("Orca.AI/")


def test_api_do_woocommerce():
    corpo = [
        {"name": "Caneta Bic Cristal Azul Caixa c/50 Ponta 1.0mm", "permalink": "https://pedagogica.com.br/produto/caneta/",
         "prices": {"price": "4898", "currency_minor_unit": 2}},
        {"name": "Caneta Bic 4 Cores &#8211; Ponta M", "permalink": "https://pedagogica.com.br/produto/4cores/",
         "prices": {"price": "0", "currency_minor_unit": 2}},
        {"name": "sem link", "permalink": "", "prices": {}},
    ]
    pedidos = []
    with _cliente(corpo, pedidos) as c:
        candidatos = buscar_woocommerce(c, LOJAS["pedagogica"], Consulta("caneta bic"))
    assert [(x.titulo, x.preco_centavos) for x in candidatos] == [
        ("Caneta Bic Cristal Azul Caixa c/50 Ponta 1.0mm", 4898), ("Caneta Bic 4 Cores – Ponta M", None)]
    assert pedidos[0].url.path == "/wp-json/wc/store/v1/products" and pedidos[0].url.params["search"] == "caneta bic"


class NavegadorQueGuarda:
    def __init__(self):
        self.pedidos = []

    def resultados_de_busca(self, url, padrao, seletor=None):
        self.pedidos.append((url, padrao, seletor))
        return 200, [{"href": "https://www.artpel.com.br/escrita/caneta-bic", "titulo": "Caneta Bic Cristal", "texto": "R$ 1,60"}]


def test_pagina_de_busca_so_na_lista_de_resultados():
    navegador = NavegadorQueGuarda()
    [c] = buscar_na_pagina(navegador, LOJAS["artpel"], Consulta("caneta bic"))
    assert navegador.pedidos == [("https://www.artpel.com.br/loja/busca.php?loja=1106500&palavra_busca=caneta%20bic",
                                  "artpel.com.br/", ".list-product")]
    assert c.preco_centavos == 160


# --- produto do mesmo tipo (piloto, 24/09/2026: a busca trouxe louro, acelga e ventilador) ------------

@pytest.mark.parametrize(("descricao", "marca", "titulo", "fica"), [
    ("Perfurador 4 Furos", "Eagle", "Louro em Folhas PQ 60g | Tenda Atacado", False),
    ("Perfurador 4 Furos", "Eagle", "Perfurador Eagle Metal 4 furos até 10 Folhas 9401 1 UN Sertic", True),
    ("Grampo 5000 Unidades", "Bacchi", "Acelga Unidade | Tenda Atacado", False),
    ("Grampo 5000 Unidades", "Bacchi", "Grampo Galvanizado Bacchi 26/6 Caixa 5000 UN", True),
    ("Grampeador de mesa 26/6", "Goller", "Ventilador de Mesa Super Power 110V Mondial", False),
    ("Grampeador de mesa 26/6", "Goller", "Grampos para Grampeador CiS 26/6 5000 Unidades", False),
    ("Grampeador de mesa 26/6", "Goller", "Grampeador de Mesa Goller 26/6 até 20 Folhas GE-309 1 UN", True),
    ("Clips 100 Unidades", "Bacchi", "Hamburgueira EPS Ch02 100 unidades", False),
    ("Pasta sanfonada 12 Divisórias", "Plascony", "Bandeja Retangular com 4 divisórias Rioplastic 1200ml 12 Unid", False),
    ("Folha sulfite 500 Folhas", "Chamex", "Louro em Folhas PQ 60g", False),
    ("Folha sulfite 500 Folhas", "Chamex", "Papel Chamex A4 pacote c/ 500 fl. | Tenda Atacado", True),
    ("Caneta esferográfica 50 Unidades", "Bic", "Bic Caneta Esferográfica Cristal 50 un", True),
    ("Caneta esferográfica 50 Unidades", "Bic", "Refil para caneta Bic", False),
])
def test_so_produto_do_mesmo_tipo(descricao, marca, titulo, fica):
    item = Especificacao(descricao, "papelaria", marca)
    assert mesmo_tipo(item, titulo, parecenca(item, titulo)) is fica


def test_sugestoes_sem_relacao_nao_viram_candidatos():
    item = Especificacao("Perfurador 4 furos até 10 folhas", "papelaria", "Eagle")
    candidatos = [Candidato("https://loja/louro", "Louro em Folhas PQ 60g"),
                  Candidato("https://loja/perfurador", "Perfurador Eagle Metal 4 furos até 10 Folhas")]
    assert [a.candidato.url for a in avaliar_candidatos(item, candidatos, VOCABULARIO)] == ["https://loja/perfurador"]


def test_termo_minimo():
    assert termo_minimo(Especificacao("Caneta esferográfica 50 unidades", "caneta", "Bic")) == "Caneta Bic"
    assert termo_minimo(Especificacao("Bloco de notas 4 cores", "papelaria", "Post-It")) == "Bloco Post-It"
    assert termo_minimo(Especificacao("Balde 10 litros")) == "Balde"


def test_catalogo_aceita_os_modos_novos():
    base = {"id": "x", "nome": "Loja X", "dominio": "www.x.com.br", "coleta": "C1"}
    validar_lojas({"lojas": [base | {"busca": {"modo": "api_vtex_is", "url": "https://www.x.com.br/api/io/_v/api/intelligent-search/product_search/"}}]})
    validar_lojas({"lojas": [base | {"busca": {"modo": "pagina", "url": "https://www.x.com.br/b?q={termo}", "seletor": ".lista"}}]})
    with pytest.raises(ErroCatalogo, match="modo da busca"):
        validar_lojas({"lojas": [base | {"busca": {"modo": "api_magica", "url": "https://www.x.com.br/"}}]})
    with pytest.raises(ErroCatalogo, match="lista de resultados"):
        validar_lojas({"lojas": [base | {"busca": {"modo": "pagina", "url": "https://www.x.com.br/b?q={termo}"}}]})
