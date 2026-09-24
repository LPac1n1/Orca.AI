"""Descoberta pela SerpApi (C2, opcional; Fase 2, etapa 15), com o serviço simulado."""

import httpx
import pytest

from orca.busca import ErroBusca
from orca.busca.serpapi import buscar_na_web

RESPOSTA = {
    "search_metadata": {"status": "Success"},
    "organic_results": [
        {"position": 1, "title": "Papel Sulfite A4 Chamex 75g 500 folhas - Loja Y", "link": "https://www.lojay.com.br/p/123",
         "snippet": "Compre Papel Sulfite A4 Chamex. Por R$ 33,90 no Pix."},
        {"position": 2, "title": "Chamex - Wikipédia", "link": "https://pt.wikipedia.org/wiki/Chamex",
         "snippet": "Chamex é uma marca de papel."},
        {"position": 3, "title": "Papel Chamex A4", "link": "https://www.lojaz.com.br/papel",
         "rich_snippet": {"top": {"extensions": ["R$ 35,00", "Em estoque"]}}},
        {"position": 4, "title": "sem link"},
    ],
}


def test_resultados_viram_candidatos():
    pedidos = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, json=RESPOSTA)

    with httpx.Client(transport=httpx.MockTransport(responder)) as c:
        candidatos = buscar_na_web(c, "chave", "Papel sulfite A4 75g Chamex")
    assert [c.url for c in candidatos] == ["https://www.lojay.com.br/p/123", "https://pt.wikipedia.org/wiki/Chamex",
                                           "https://www.lojaz.com.br/papel"]
    assert [c.preco_centavos for c in candidatos] == [3390, None, 3500]  # só para mostrar; não é evidência
    parametros = pedidos[0].url.params
    assert parametros["engine"] == "google" and parametros["gl"] == "br" and parametros["hl"] == "pt-br"
    assert parametros["q"] == "Papel sulfite A4 75g Chamex"
    assert pedidos[0].headers["user-agent"].startswith("Orca.AI/")


@pytest.mark.parametrize(("status", "corpo", "mensagem"), [
    (401, {"error": "Invalid API key. Your API key should be here: https://serpapi.com/manage-api-key"}, "recusou a chave"),
    (429, {"error": "Your account has run out of searches."}, "acabaram"),
    (500, {}, "código 500"),
])
def test_erros(status, corpo, mensagem):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=corpo))) as c:
        with pytest.raises(ErroBusca, match=mensagem):
            buscar_na_web(c, "chave", "x")


def test_sem_resultados():
    corpo = {"error": "Google hasn't returned any results for this query."}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=corpo))) as c:
        assert buscar_na_web(c, "chave", "xyzw") == []
