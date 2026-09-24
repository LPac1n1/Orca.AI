"""Opcionais pela API (Fase 2, etapa 15): chaves no cofre, IA conferindo os 🟡 e descoberta pela SerpApi.

Tudo com serviços simulados: nenhuma chave de verdade, nenhum acesso ao Gerenciador de
Credenciais do Windows nem à internet.
"""

import json
from contextlib import contextmanager
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, LOJAS, cliente_cnpj, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.coleta import Captura
from orca.cofre import CofreEmMemoria
from orca.dominio import formatar_cnpj

PAGINAS = {  # endereço: (título, preço) — páginas sem marca e sem código de barras: a correspondência fica 🟡
    "https://www.kalunga.com.br/p/leite-395": ("Leite Condensado 395g", 1090),
    "https://www.gimba.com.br/p/leite-semidesnatado": ("Leite Condensado Semidesnatado 395g", 990),
}
SERPAPI = {"organic_results": [
    {"title": "Leite Condensado Moça 395g", "link": "https://www.lojanova.com.br/leite-moca-395", "snippet": "R$ 10,49 no Pix"},
    {"title": "Leite Condensado Moça 395g | Kalunga", "link": "https://www.kalunga.com.br/p/leite-moca"},
    {"title": "Creme de Leite Nestlé 200g", "link": "https://www.lojanova.com.br/creme"},
]}


class Navegador:
    def capturar(self, url: str, cep: str | None = None) -> Captura:
        titulo, preco = PAGINAS[url]
        cnpj = LOJAS[url.split("/")[2].removeprefix("www.")][0]
        produto = {"@type": "Product", "name": titulo,
                   "offers": {"price": f"{preco // 100}.{preco % 100:02d}", "priceCurrency": "BRL"}}
        html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
        texto = f"{titulo} por R$ {preco // 100},{preco % 100:02d} · CNPJ {formatar_cnpj(cnpj)}"
        return Captura(url, url, COLETA, titulo, 200, html, (), texto, pdf_valido(url), b"PNG", b"MHTML-" + url.encode(),
                       None, "C1", None)


class Servicos:
    """Gemini, SerpApi e o serviço de CNPJ simulados, num só cliente HTTP."""

    def __init__(self):
        self.gemini: list[httpx.Request] = []
        self.serpapi: list[httpx.Request] = []

    def responder(self, pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == "generativelanguage.googleapis.com":
            self.gemini.append(pedido)
            texto = json.loads(pedido.content)["contents"][0]["parts"][0]["text"]
            if '{"ok": true}' in texto:
                resposta = {"ok": True}
            elif "Semidesnatado" in texto:
                resposta = {"mesmo_produto": "nao", "motivo": "semidesnatado não é o integral"}
            else:
                resposta = {"mesmo_produto": "sim", "motivo": "mesmo nome e tamanho"}
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(resposta)}]}}]})
        if pedido.url.host == "serpapi.com":
            self.serpapi.append(pedido)
            return httpx.Response(200, json=SERPAPI)
        return cliente_cnpj()._transport.handle_request(pedido)

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.responder))


@pytest.fixture
def ambiente(tmp_path):
    servicos, cofre, guardadas = Servicos(), CofreEmMemoria(), []

    @contextmanager
    def abrir():
        yield Navegador()

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir, cliente_http=servicos.cliente, cofre=cofre,
                               hoje=lambda: date(2026, 9, 24), intervalo_ia_s=0)
    app = criar_app(config, contexto, iniciar_trabalhador=False, guardar_config=lambda c: guardadas.append(c.ia))
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, servicos, cofre, guardadas


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _projeto_com_amarelos(api, app) -> dict:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 100_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "Copa"}), 201)
    leite = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Leite condensado 395g", "categoria": "alimento", "marca": "Moça", "qtd_planejada": 5,
        "mes_fim": 12}), 201)
    for url in PAGINAS:
        _ok(api.post(f"/api/itens/{leite['id']}/coletas", json={"url": url}), 202)
    app.state.servico.fila.processar_todas()
    return {"projeto": projeto["id"], "lote": lote["id"], "leite": leite["id"]}


def _correspondencias(api, item_id) -> dict:
    return {o["url"]: o["correspondencia"] for o in _ok(api.get(f"/api/itens/{item_id}/observacoes"))}


def test_sem_opcionais_o_sistema_funciona(ambiente):
    api, app, servicos, *_ = ambiente
    estado = _ok(api.get("/api/opcionais"))
    assert estado["ia"]["provedor"] == "nenhum" and not estado["ia"]["ligada"] and not estado["serpapi"]["chave"]
    ids = _projeto_com_amarelos(api, app)
    assert {c["status"] for c in _correspondencias(api, ids["leite"]).values()} == {"amarelo"}
    assert api.post(f"/api/projetos/{ids['projeto']}/julgar-amarelos").status_code == 409
    assert api.post(f"/api/lotes/{ids['lote']}/descobrir", json={}).status_code == 409
    assert api.post("/api/opcionais/testar-ia").status_code == 409
    assert servicos.gemini == [] and servicos.serpapi == []


def test_chaves_ficam_no_cofre_e_nunca_voltam(ambiente):
    api, _, _, cofre, guardadas = ambiente
    resposta = api.put("/api/opcionais", json={"chave_serpapi": "serp-123", "chave_gemini": "gem-456",
                                               "ia_provedor": "gemini", "ia_modelo": "gemini-2.5-flash"})
    estado = _ok(resposta)
    assert "serp-123" not in resposta.text and "gem-456" not in resposta.text
    assert estado["serpapi"]["chave"] and estado["ia"]["chave_gemini"] and estado["ia"]["ligada"]
    assert cofre.chaves == {"serpapi": "serp-123", "gemini": "gem-456"}
    assert guardadas[-1].provedor == "gemini" and not hasattr(guardadas[-1], "chave")  # a configuração não guarda chave
    _ok(api.put("/api/opcionais", json={"chave_serpapi": ""}))  # em branco: apaga
    assert cofre.chaves == {"gemini": "gem-456"}
    assert api.put("/api/opcionais", json={"ia_modelo": "../outro"}).status_code == 422
    assert api.put("/api/opcionais", json={"ia_provedor": "chatgpt"}).status_code == 422
    assert _ok(api.post("/api/opcionais/testar-ia"))["ok"]


def test_ia_confere_os_amarelos(ambiente):
    api, app, servicos, *_ = ambiente
    ids = _projeto_com_amarelos(api, app)
    _ok(api.put("/api/opcionais", json={"ia_provedor": "gemini", "chave_gemini": "gem-456"}))
    tarefa = _ok(api.post(f"/api/projetos/{ids['projeto']}/julgar-amarelos"), 202)
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida", feita
    assert feita["resultado"]["rebaixadas"] == 1 and feita["resultado"]["mantidas"] == 1
    assert len(servicos.gemini) == 2 and all(p.headers["x-goog-api-key"] == "gem-456" for p in servicos.gemini)
    enviado = json.dumps([json.loads(p.content) for p in servicos.gemini], ensure_ascii=False)
    assert "OSC" not in enviado and "Leonardo" not in enviado  # só dados públicos de produto (D-51)

    corr = _correspondencias(api, ids["leite"])
    rebaixada = corr["https://www.gimba.com.br/p/leite-semidesnatado"]
    assert rebaixada["status"] == "vermelho" and rebaixada["origem"] == "ia" and rebaixada["autor"] == "ia:gemini"
    assert any("IA (gemini): produto diferente" in m for m in rebaixada["motivos"])
    mantida = corr["https://www.kalunga.com.br/p/leite-395"]
    assert mantida["status"] == "amarelo"  # "sim" da IA não aprova: quem confirma é a pessoa (D-52)
    assert any("quem confirma é você" in m for m in mantida["motivos"])

    # já julgados: pedir de novo não gasta pedidos
    _ok(api.post(f"/api/projetos/{ids['projeto']}/julgar-amarelos"), 202)
    app.state.servico.fila.processar_proxima("principal")
    assert len(servicos.gemini) == 2

    # a pessoa pode desfazer o 🔴 da IA
    obs = next(o for o in _ok(api.get(f"/api/itens/{ids['leite']}/observacoes")) if "semidesnatado" in o["url"])
    _ok(api.post("/api/correspondencias", json={"item_id": ids["leite"], "observacao_id": obs["id"], "status": "amarelo",
                                                "justificativa": "vou conferir na loja"}), 201)
    assert _correspondencias(api, ids["leite"])[obs["url"]]["status"] == "amarelo"


def test_descoberta_pela_serpapi(ambiente):
    api, app, servicos, *_ = ambiente
    ids = _projeto_com_amarelos(api, app)
    _ok(api.put("/api/opcionais", json={"chave_serpapi": "serp-123"}))
    tarefa = _ok(api.post(f"/api/lotes/{ids['lote']}/descobrir", json={}), 202)
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida", feita
    [item] = feita["resultado"]["itens"]
    links = {l["url"]: l for l in item["links"]}
    assert "https://www.lojanova.com.br/creme" not in links  # 🔴: outro produto
    nova = links["https://www.lojanova.com.br/leite-moca-395"]
    assert nova["loja"] is None and nova["preco_centavos"] == 1049 and not nova["ja_pesquisada"]
    kalunga = links["https://www.kalunga.com.br/p/leite-moca"]
    assert kalunga["loja"] == "Kalunga" and kalunga["ja_pesquisada"]
    assert len(servicos.serpapi) == 1 and servicos.serpapi[0].url.params["q"] == "Leite condensado 395g Moça"
    assert "serp-123" not in json.dumps(feita)  # a chave não fica na tarefa
    # nada foi capturado: a pessoa escolhe os links
    assert len(_ok(api.get(f"/api/itens/{ids['leite']}/observacoes"))) == 2
