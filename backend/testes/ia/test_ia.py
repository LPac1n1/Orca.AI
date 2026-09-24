"""IA opcional (D-50 a D-52; Fase 2, etapa 15): provedores e o julgamento dos 🟡, com serviços simulados."""

import json

import httpx
import pytest

from orca.cofre import CofreEmMemoria
from orca.correspondencia import Anuncio, Especificacao
from orca.ia import (
    ConfigIA,
    ErroFormatoIA,
    ErroIA,
    Gemini,
    ModeloLocal,
    dados_enviados,
    julgar_correspondencia,
    provedor_configurado,
)

ITEM = Especificacao("Leite condensado 395g", "alimento", "Moça", atributos={"tipo": "integral"})
ANUNCIO = Anuncio("Leite Condensado Semidesnatado 395g", None, "7891000100103")


def _cliente(responder):
    return httpx.Client(transport=httpx.MockTransport(responder))


def _gemini_respondendo(texto: str, pedidos: list):
    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": texto}]}}]})
    return responder


def test_gemini_chave_no_cabecalho_e_json():
    pedidos = []
    with _cliente(_gemini_respondendo('{"mesmo_produto": "não", "motivo": "semidesnatado × integral"}', pedidos)) as c:
        julgamento = julgar_correspondencia(Gemini(c, "chave-secreta"), ITEM, ANUNCIO)
    assert julgamento.rebaixar and julgamento.resposta == "nao" and julgamento.motivo == "semidesnatado × integral"
    [pedido] = pedidos
    assert pedido.url.path == "/v1beta/models/gemini-2.5-flash:generateContent"
    assert pedido.headers["x-goog-api-key"] == "chave-secreta" and "chave-secreta" not in str(pedido.url)
    corpo = json.loads(pedido.content)
    assert corpo["generationConfig"]["responseMimeType"] == "application/json"
    texto = corpo["contents"][0]["parts"][0]["text"]
    assert "Leite Condensado Semidesnatado 395g" in texto and "Moça" in texto


def test_so_dados_publicos_do_produto():
    enviado = dados_enviados(ITEM, ANUNCIO)
    assert enviado == {"produto_pedido": {"descricao": "Leite condensado 395g", "marca": "Moça",
                                          "atributos": {"tipo": "integral"}},
                       "anuncio": {"titulo": "Leite Condensado Semidesnatado 395g", "codigo_de_barras": "7891000100103"}}


@pytest.mark.parametrize(("resposta", "rebaixar"), [
    ('{"mesmo_produto": "sim", "motivo": "igual"}', False),  # "sim" nunca vira 🟢: quem aprova é a pessoa
    ('{"mesmo_produto": "incerto", "motivo": "falta a marca"}', False),
    ('```json\n{"mesmo_produto": "NAO", "motivo": "outro tamanho"}\n```', True),
])
def test_respostas(resposta, rebaixar):
    with _cliente(_gemini_respondendo(resposta, [])) as c:
        assert julgar_correspondencia(Gemini(c, "k"), ITEM, ANUNCIO).rebaixar is rebaixar


@pytest.mark.parametrize("resposta", ['{"mesmo_produto": "talvez", "motivo": "x"}', '{"motivo": "x"}',
                                      '{"mesmo_produto": "nao", "motivo": "  "}', "não sei", "[1, 2]"])
def test_resposta_fora_do_formato_e_ignorada(resposta):
    with _cliente(_gemini_respondendo(resposta, [])) as c, pytest.raises(ErroFormatoIA):
        julgar_correspondencia(Gemini(c, "k"), ITEM, ANUNCIO)


@pytest.mark.parametrize(("status", "texto", "mensagem"), [
    (429, "quota", "limite de pedidos"),
    (400, "API key not valid. Please pass a valid API key.", "recusou a chave"),
    (403, "", "recusou a chave"),
    (404, "", "não tem o modelo"),
    (500, "", "código 500"),
])
def test_erros_do_gemini(status, texto, mensagem):
    with _cliente(lambda _: httpx.Response(status, text=texto)) as c, pytest.raises(ErroIA, match=mensagem) as erro:
        Gemini(c, "k").responder_json("{}")
    assert not isinstance(erro.value, ErroFormatoIA)  # esses param a tarefa


def test_modelo_local():
    pedidos = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, json={"message": {"content": '{"mesmo_produto": "sim", "motivo": "igual"}'}})

    with _cliente(responder) as c:
        julgamento = julgar_correspondencia(ModeloLocal(c, "", "qwen2.5:7b"), ITEM, ANUNCIO)
    assert julgamento.resposta == "sim"
    corpo = json.loads(pedidos[0].content)
    assert str(pedidos[0].url) == "http://localhost:11434/api/chat"
    assert corpo["model"] == "qwen2.5:7b" and corpo["format"] == "json" and corpo["stream"] is False


def test_modelo_local_desligado():
    def recusar(pedido):
        raise httpx.ConnectError("recusado", request=pedido)
    with _cliente(recusar) as c, pytest.raises(ErroIA, match="Ollama está aberto"):
        ModeloLocal(c, "http://localhost:11434", "x").responder_json("{}")


def test_provedor_configurado():
    with httpx.Client() as c:
        assert provedor_configurado(ConfigIA(), CofreEmMemoria(), c) is None  # padrão: sem IA
        with pytest.raises(ErroIA, match="chave do Gemini"):
            provedor_configurado(ConfigIA("gemini"), CofreEmMemoria(), c)
        gemini = provedor_configurado(ConfigIA("gemini", "gemini-x"), CofreEmMemoria(gemini="k"), c)
        assert gemini.nome == "gemini" and gemini.modelo == "gemini-x"
        with pytest.raises(ErroIA, match="nome do modelo local"):
            provedor_configurado(ConfigIA("local"), CofreEmMemoria(), c)
        assert provedor_configurado(ConfigIA("local", "llama3.1"), CofreEmMemoria(), c).endereco == "http://localhost:11434"
