"""Vitrine do item (D-75, "código de barras primeiro"), com o caso do piloto (suco de uva Del Valle 1L).

Rodada 3 do piloto (25/09/2026): a Sonda achou o suco certo, mas 🟡; o Atacadão e o Oba não acharam pela
descrição. Com a vitrine, a pessoa escolhe o produto uma vez; o código de barras dele guia as outras buscas.
"""

import json
from contextlib import contextmanager
from datetime import date
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, cliente_cnpj, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.coleta import Captura
from orca.dominio import formatar_cnpj

EAN = "7894900611014"
SONDA, OBA, ATACADAO = "01937635002983", "04972092000122", "75315333000109"


def _vtex(nome, preco, link):
    return {"productName": nome, "brand": "Del Valle", "link": link,
            "items": [{"ean": EAN, "images": [{"imageUrl": f"https://img/{link.strip('/')}.jpg"}],
                       "sellers": [{"commertialOffer": {"Price": preco}}]}]}


class Lojas:
    """Sonda (página de busca), Oba (busca nova da VTEX) e Atacadão (API antiga): o mesmo suco nas três."""

    def __init__(self):
        self.pedidos: list[str] = []

    def responder(self, pedido: httpx.Request) -> httpx.Response:
        host, params = pedido.url.host, dict(pedido.url.params)
        if host == "www.obahortifruti.com.br":
            self.pedidos.append(f"oba:{params.get('query')}")
            achou = params.get("query") == EAN  # o Oba não acha pela descrição, só pelo código
            return httpx.Response(200, json={"products": [_vtex("Suco Uva Del Valle 1L", 21.49, "/suco-uva-dv/p")] if achou else []})
        if host == "www.atacadao.com.br":
            self.pedidos.append(f"atacadao:{params.get('fq') or params.get('ft')}")
            achou = params.get("fq") == f"alternateIds_Ean:{EAN}"
            return httpx.Response(200, text=json.dumps([_vtex("Suco Del Valle 100% Uva 1L", 17.99, "/suco-dv-uva/p")] if achou else []))
        return cliente_cnpj()._transport.handle_request(pedido)

    def cliente(self):
        return httpx.Client(transport=httpx.MockTransport(self.responder))

    def resultados_de_busca(self, url: str, padrao: str, seletor: str | None = None):
        self.pedidos.append(f"sonda:{unquote(url).rsplit('/', 1)[-1]}")
        return 200, [
            {"href": "https://www.sondadelivery.com.br/delivery/produto/suco-100-uva-del-valle-1l/1",
             "titulo": "Suco 100% Uva Del Valle 1l", "texto": "Suco 100% Uva Del Valle 1l R$ 19,90",
             "imagem": "https://img.sonda/suco-uva.jpg"},
            {"href": "https://www.sondadelivery.com.br/delivery/produto/nectar-uva-del-valle-1l/2",
             "titulo": "Néctar de Uva Del Valle 1l", "texto": "Néctar de Uva Del Valle 1l R$ 9,90", "imagem": ""},
        ]

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        if "sondadelivery" in url:
            titulo, preco, cnpj = "Suco 100% Uva Del Valle 1l", 1990, SONDA
        elif "obahortifruti" in url:
            titulo, preco, cnpj = "Suco Uva Del Valle 1L", 2149, OBA
        else:
            titulo, preco, cnpj = "Suco Del Valle 100% Uva 1L", 1799, ATACADAO
        produto = {"@type": "Product", "name": titulo, "gtin13": EAN, "image": "https://img/p.jpg",
                   "offers": {"price": f"{preco // 100}.{preco % 100:02d}", "priceCurrency": "BRL"}}
        html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
        texto = f"{titulo} R$ {preco // 100},{preco % 100:02d} · CNPJ {formatar_cnpj(cnpj)}"
        return Captura(url, url, COLETA, titulo, 200, html, (), texto, pdf_valido(url), b"PNG", b"MHTML-" + url.encode(),
                       None, "C1", None)


@pytest.fixture
def ambiente(tmp_path):
    lojas = Lojas()

    @contextmanager
    def abrir():
        yield lojas

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir, cliente_http=lojas.cliente,
                               hoje=lambda: date(2026, 9, 25), intervalo_busca_s=0)
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, lojas


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _suco(api) -> dict:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 100_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "Alimentação", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "1"}), 201)
    item = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Suco de uva", "categoria": "alimento", "marca": "Del Valle", "apresentacao": "1L",
        "qtd_planejada": 2, "mes_fim": 12}), 201)
    return {"projeto": projeto["id"], "lote": lote["id"], "item": item["id"]}


def test_vitrine_escolha_e_busca_pelo_codigo_de_barras(ambiente):
    api, app, lojas = ambiente
    ids = _suco(api)

    # 1. a vitrine: o que as lojas de alimentos mostram (com a foto)
    tarefa = _ok(api.post(f"/api/itens/{ids['item']}/vitrine"), 202)
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida", feita
    grupos = {g["loja"]: g["produtos"] for g in feita["resultado"]["lojas"]}
    assert set(grupos) == {"Sonda Supermercados", "Oba Hortifruti", "Atacadão"}  # só as que vendem alimentos
    sonda = grupos["Sonda Supermercados"]
    assert sonda[0]["titulo"] == "Suco 100% Uva Del Valle 1l" and sonda[0]["imagem"] == "https://img.sonda/suco-uva.jpg"
    assert grupos["Oba Hortifruti"] == [] and grupos["Atacadão"] == []  # pela descrição não acharam

    # 2. a pessoa clica em "é este": a página vira prova e produto de referência, em nome dela
    coleta = _ok(api.post(f"/api/itens/{ids['item']}/escolher-produto", json={"url": sonda[0]["url"]}), 202)
    app.state.servico.fila.processar_todas()
    feita = _ok(api.get(f"/api/tarefas/{coleta['id']}"))
    assert feita["resultado"]["referencia"] and "produto de referência escolhido por você" in feita["mensagem"]
    [pagina] = _ok(api.get(f"/api/itens/{ids['item']}/observacoes"))
    corr = pagina["correspondencia"]
    assert (corr["status"], corr["origem"], corr["autor"]) == ("verde", "humano", "usuario:Leonardo")
    lote = _ok(api.get(f"/api/projetos/{ids['projeto']}/revisao"))["orcamentos"][0]["lotes"][0]
    assert lote["itens"][0]["referencia"]["ean"] == EAN

    # 3. daí em diante, o código de barras guia a busca nas outras lojas: o Oba e o Atacadão acham o suco
    lojas.pedidos.clear()
    busca = _ok(api.post(f"/api/lotes/{ids['lote']}/busca", json={"lojas": ["oba_hortifruti", "atacadao"]}), 202)["tarefas"][0]
    app.state.servico.fila.processar_todas()
    assert f"oba:{EAN}" in lojas.pedidos and f"atacadao:alternateIds_Ean:{EAN}" in lojas.pedidos
    assert not any(p.startswith("oba:Suco") for p in lojas.pedidos)  # achou pelo código: não buscou pelo texto
    paginas = {p["url"].split("/")[2]: p["correspondencia"] for p in _ok(api.get(f"/api/itens/{ids['item']}/observacoes"))}
    assert paginas["www.obahortifruti.com.br"]["status"] == "verde" and paginas["www.obahortifruti.com.br"]["origem"] == "ean"
    assert paginas["www.atacadao.com.br"]["status"] == "verde"
    assert _ok(api.get(f"/api/tarefas/{busca['id']}"))["estado"] == "concluida"


def test_escolha_sem_preco_nao_vira_referencia(ambiente):
    api, app, lojas = ambiente
    ids = _suco(api)
    lojas.capturar = lambda url, cep=None: Captura(url, url, COLETA, "Suco", 200, "<html></html>", (), "Suco (sem preço)",
                                                   pdf_valido(url), b"PNG", b"M", None, "C1", None)
    coleta = _ok(api.post(f"/api/itens/{ids['item']}/escolher-produto",
                          json={"url": "https://www.sondadelivery.com.br/delivery/produto/x/1"}), 202)
    app.state.servico.fila.processar_todas()
    feita = _ok(api.get(f"/api/tarefas/{coleta['id']}"))
    assert feita["resultado"]["referencia"] is None and "não virou referência" in feita["mensagem"]
