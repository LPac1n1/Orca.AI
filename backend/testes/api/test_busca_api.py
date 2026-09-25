"""Busca automática de um lote nas lojas (Fase 2, etapa 10; D-68), com lojas simuladas."""

import json
from contextlib import contextmanager
from datetime import date
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, LEITE, LOJAS, PAPEL, cliente_cnpj, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.coleta import Captura
from orca.dominio import formatar_cnpj

ATACADAO = "75315333000109"
PRODUTOS = {  # ean: (nome, marca, preço em centavos)
    PAPEL: ("Papel Sulfite A4 75g 500 folhas", "Chamex", 3490),
    LEITE: ("Leite Condensado 395g", "Moça", 1050),
}


def _pagina(url: str, ean: str, cnpj: str) -> Captura:
    nome, marca, preco = PRODUTOS[ean]
    produto = {"@type": "Product", "name": nome, "brand": marca, "gtin13": ean,
               "offers": {"price": f"{preco // 100}.{preco % 100:02d}", "priceCurrency": "BRL"}}
    html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
    texto = f"{nome} {marca} R$ {preco // 100},{preco % 100:02d} · CNPJ {formatar_cnpj(cnpj)}"
    return Captura(url, url, COLETA, nome, 200, html, (), texto, pdf_valido(url), b"PNG-" + url.encode(),
                   b"MHTML-" + url.encode(), None, "C1", None)


class NavegadorDeBusca:
    """Kalunga tem os dois itens; Lepok só o papel; o Atacadão responde pela API (não usa o navegador)."""

    def __init__(self):
        self.buscas: list[str] = []
        self.capturas: list[str] = []

    def resultados_de_busca(self, url: str, padrao: str, seletor: str | None = None):
        self.buscas.append(unquote(url))
        dominio = url.split("/")[2].removeprefix("www.")
        eans = [PAPEL, PAPEL.replace("0", "9", 1)] if dominio == "lepok.com.br" else [PAPEL, LEITE]
        termo = unquote(url).lower()
        cartoes = []
        for ean in eans:
            nome, marca, preco = PRODUTOS.get(ean, ("Papel Sulfite A4 75g 300 folhas", "Chamex", 2000))
            if any(p in termo for p in nome.lower().split()[:1]):  # a busca devolve só o que tem a ver
                cartoes.append({"href": f"https://www.{dominio}/produto/{ean}?PID=1", "titulo": f"{nome} {marca}",
                                "texto": f"{nome} R$ {preco // 100},{preco % 100:02d}"})
        return 200, cartoes

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        self.capturas.append(url)
        dominio = url.split("/")[2].removeprefix("www.")
        if "/produto/" not in url and "/p/" not in url:  # página da busca: prova de "não encontrado"
            return Captura(url, url, COLETA, "Busca", 200, "", (), "Nenhum resultado", pdf_valido(url), b"PNG",
                           b"MHTML-" + url.encode(), None, "C1", None)
        ean = url.split("/produto/")[-1].split("?")[0] if "/produto/" in url else url.rstrip("/").split("/")[-2]
        cnpj = ATACADAO if dominio == "atacadao.com.br" else LOJAS[dominio][0]
        return _pagina(url, ean, cnpj)


def _cliente():
    """API VTEX do Atacadão (por código de barras) e OpenCNPJ simulados."""
    pedidos = []
    cnpj = cliente_cnpj()

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == "www.atacadao.com.br":
            pedidos.append(dict(pedido.url.params))
            ean = pedido.url.params.get("fq", ":").split(":")[-1]
            if ean not in PRODUTOS:
                return httpx.Response(206, text="[]")
            nome, marca, _ = PRODUTOS[ean]
            return httpx.Response(206, text=json.dumps([{"productName": nome, "brand": marca,
                                                          "link": f"https://secure.atacadao.com.br/p/{ean}/p",
                                                          "items": [{"ean": ean, "sellers": []}]}]))
        return cnpj._transport.handle_request(pedido)

    return pedidos, lambda: httpx.Client(transport=httpx.MockTransport(responder))


@pytest.fixture
def ambiente(tmp_path):
    navegador = NavegadorDeBusca()
    pedidos, cliente = _cliente()

    @contextmanager
    def abrir():
        yield navegador

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir, cliente_http=cliente, hoje=lambda: date(2026, 9, 24),
                               intervalo_busca_s=0)
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, navegador, pedidos


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _lote(api) -> dict:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 500_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "Copa e escritório"}), 201)
    papel = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={  # sem código de barras: é achado na primeira loja
        "descricao": "Papel sulfite A4 75g 500 folhas", "categoria": "papel", "marca": "Chamex",
        "qtd_planejada": 10, "mes_fim": 12}), 201)
    leite = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Leite condensado 395g", "categoria": "alimento", "marca": "Moça", "ean": LEITE,
        "qtd_planejada": 5, "mes_fim": 12}), 201)
    return {"projeto": projeto["id"], "lote": lote["id"], "papel": papel["id"], "leite": leite["id"]}


def test_lojas_sugeridas_para_o_lote(ambiente):
    api, *_ = ambiente
    ids = _lote(api)
    lojas = {l["id"]: l for l in _ok(api.get(f"/api/lotes/{ids['lote']}/lojas-de-busca"))["lojas"]}
    assert lojas["gimba"]["sugerida"] and lojas["atacadao"]["sugerida"]  # papelaria e alimentos
    assert not lojas["kalunga"]["sugerida"]  # não vende alimentos
    assert lojas["extra_mercado"]["modo"] == "assistida" and lojas["gimba"]["faltam"] == 2
    assert "carrefour_mercado" not in lojas  # recusa até a janela (25/09/2026): só o PDF do navegador da pessoa


def test_busca_automatica_do_lote(ambiente):
    api, app, navegador, pedidos = ambiente
    ids = _lote(api)
    tarefas = _ok(api.post(f"/api/lotes/{ids['lote']}/busca",
                           json={"lojas": ["kalunga", "atacadao", "lepok", "gimba"]}), 202)["tarefas"]
    # a Gimba proíbe a busca por programas no robots.txt: uma janela por item (25/09/2026)
    assert [t["tipo"] for t in tarefas] == ["buscar_lote", "captura_assistida", "captura_assistida"]
    assert all(t["parametros"]["url"].startswith("https://www.gimba.com.br/?txt-busca=") for t in tarefas[1:])
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefas[0]['id']}"))
    assert feita["estado"] == "concluida", feita
    resumo = {r["loja"]: r for r in feita["resultado"]["resumo"]}
    assert resumo["Kalunga"]["encontrados"] == 2 and resumo["Atacadão"]["encontrados"] == 2
    assert resumo["Lepok"]["nao_encontrados"] == ["Leite condensado 395g"] and resumo["Lepok"]["encontrados"] == 1

    # o papel não tinha código de barras: achado na Kalunga, o Atacadão foi pesquisado por ele
    assert {"fq": f"alternateIds_Ean:{PAPEL}"} in pedidos and not any("ft" in p for p in pedidos)
    # o item mais difícil (sem código de barras) primeiro; na Lepok, sem o leite, a busca seguiu (D-68 revista)
    assert navegador.buscas[0].startswith("https://www.lepok.com.br/busca/papel-sulfite")
    # a Kalunga acha pelo código de barras: é pesquisada depois, já com o código (e, sem resultado, pelo texto)
    kalunga = [b for b in navegador.buscas if "kalunga" in b]
    assert f"q={LEITE}" in " ".join(kalunga) and any("q=Leite" in b for b in kalunga)

    papel = {o["loja"]: o for o in _ok(api.get(f"/api/itens/{ids['papel']}/observacoes"))}
    assert papel["Atacadão"]["url"] == f"https://www.atacadao.com.br/p/{PAPEL}/p"
    assert papel["Kalunga"]["correspondencia"]["status"] == "verde"
    assert any("achado pela busca automática na Kalunga" in a for a in papel["Kalunga"]["avisos"])
    leite = _ok(api.get(f"/api/itens/{ids['leite']}/observacoes"))
    nao_achado = next(o for o in leite if not o["encontrado"])
    assert "lepok" in nao_achado["url"] and nao_achado["evidencia_id"]
    assert any("não encontrado na busca" in a for a in nao_achado["avisos"])

    # buscar de novo não repete o que já foi achado
    antes = len(navegador.capturas)
    _ok(api.post(f"/api/lotes/{ids['lote']}/busca", json={"lojas": ["kalunga"]}), 202)
    app.state.servico.fila.processar_proxima("principal")
    assert len(navegador.capturas) == antes


def test_pagina_recusada_nao_volta_na_busca_seguinte(ambiente):
    api, app, navegador, _ = ambiente
    ids = _lote(api)
    _ok(api.post(f"/api/lotes/{ids['lote']}/busca", json={"lojas": ["kalunga"]}), 202)
    app.state.servico.fila.processar_proxima("principal")
    papel = next(o for o in _ok(api.get(f"/api/itens/{ids['papel']}/observacoes")) if o["loja"] == "Kalunga")
    _ok(api.post("/api/correspondencias", json={"item_id": ids["papel"], "observacao_id": papel["id"],
                                                "status": "vermelho", "justificativa": "é outra gramatura"}), 201)
    capturas = len(navegador.capturas)
    tarefa = _ok(api.post(f"/api/lotes/{ids['lote']}/busca", json={"lojas": ["kalunga"]}), 202)["tarefas"][0]
    app.state.servico.fila.processar_proxima("principal")
    resumo = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))["resultado"]["resumo"][0]
    assert resumo["nao_encontrados"] == ["Papel sulfite A4 75g 500 folhas"]  # a loja só tinha a página recusada
    assert papel["url"] not in navegador.capturas[capturas:]
