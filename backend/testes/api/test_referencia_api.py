"""Produto de referência (D-71) e fotos (D-73) pela API: confirmar uma página muda as outras lojas."""

import json
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, LOJAS, cliente_cnpj, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.coleta import Captura
from orca.dominio import formatar_cnpj

PAGINAS = {  # endereço: (título, marca, código de barras, preço, foto)
    "https://www.kalunga.com.br/p/papel-75": ("Papel Sulfite Chamex A4 Branco 75g 500 Folhas", "Chamex", "7891173023001", 3450,
                                              "https://img.kalunga.com.br/papel-75.jpg"),
    "https://www.lepok.com.br/p/papel-75": ("Papel sulfite A4 75g Chamex resma 500 folhas branco", "Chamex", "7891173023001",
                                            3390, None),
    "https://www.gimba.com.br/p/papel-90": ("Papel Sulfite Chamex A4 90g Maior Espessura 500 Folhas", "Chamex",
                                            "7891173023063", 4820, "/img/papel-90.jpg"),
}


class Navegador:
    def capturar(self, url: str, cep: str | None = None) -> Captura:
        titulo, marca, ean, preco, foto = PAGINAS[url]
        produto = {"@type": "Product", "name": titulo, "brand": marca, "gtin13": ean,
                   "offers": {"price": f"{preco // 100}.{preco % 100:02d}", "priceCurrency": "BRL"}}
        if foto:
            produto["image"] = [foto]
        html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
        if url.startswith("https://www.lepok"):
            html += '<meta property="og:image" content="https://cdn.lepok.com.br/papel.png">'
        cnpj = LOJAS[url.split("/")[2].removeprefix("www.")][0]
        texto = f"{titulo} por R$ {preco // 100},{preco % 100:02d} · CNPJ {formatar_cnpj(cnpj)}"
        return Captura(url, url, COLETA, titulo, 200, html, (), texto, pdf_valido(url), b"PNG", b"MHTML-" + url.encode(),
                       None, "C1", None)


@pytest.fixture
def ambiente(tmp_path):
    @contextmanager
    def abrir():
        yield Navegador()

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir, cliente_http=cliente_cnpj, hoje=lambda: date(2026, 9, 25))
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _papel(api, app) -> dict:
    """O item do piloto: não diz a gramatura (a Kalunga e a Lepok têm o de 75 g; a Gimba, o de 90 g)."""
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 100_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "Escritório"}), 201)
    item = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Folha sulfite 500 Folhas", "categoria": "papel", "marca": "Chamex", "qtd_planejada": 2,
        "mes_fim": 12}), 201)
    for url in PAGINAS:
        _ok(api.post(f"/api/itens/{item['id']}/coletas", json={"url": url}), 202)
    app.state.servico.fila.processar_todas()
    return {"projeto": projeto["id"], "item": item["id"]}


def _paginas(api, item_id) -> dict:
    return {o["url"]: o for o in _ok(api.get(f"/api/itens/{item_id}/observacoes"))}


def _item_da_revisao(api, ids) -> dict:
    lote = _ok(api.get(f"/api/projetos/{ids['projeto']}/revisao"))["orcamentos"][0]["lotes"][0]
    return next(i for i in lote["itens"] if i["id"] == ids["item"])


def test_primeira_confirmacao_vira_referencia_e_muda_as_outras_lojas(ambiente):
    api, app = ambiente
    ids = _papel(api, app)
    paginas = _paginas(api, ids["item"])
    assert {p["correspondencia"]["status"] for p in paginas.values()} == {"amarelo"}  # o item não diz a gramatura
    assert _item_da_revisao(api, ids)["referencia"] is None

    kalunga = paginas["https://www.kalunga.com.br/p/papel-75"]
    resposta = _ok(api.post("/api/correspondencias", json={
        "item_id": ids["item"], "observacao_id": kalunga["id"], "status": "verde",
        "justificativa": "é o papel de 75 g que queremos"}), 201)
    assert resposta["referencia_mudou"] and resposta["recomparadas"] == 2

    paginas = _paginas(api, ids["item"])
    lepok = paginas["https://www.lepok.com.br/p/papel-75"]["correspondencia"]
    gimba = paginas["https://www.gimba.com.br/p/papel-90"]["correspondencia"]
    assert (lepok["status"], lepok["origem"], lepok["autor"]) == ("verde", "ean", "sistema:referencia")
    assert lepok["vale"]  # código de barras: 🟢 automático pelas regras padrão
    assert gimba["status"] == "vermelho" and "75 g/m² × 90 g/m²" in gimba["motivos"][0]

    referencia = _item_da_revisao(api, ids)["referencia"]
    assert referencia["observacao_id"] == kalunga["id"] and referencia["imagem"] == "https://img.kalunga.com.br/papel-75.jpg"

    # a pessoa decide trocar a referência (outra gramatura): as páginas que ela não decidiu são comparadas de novo
    resposta = _ok(api.post(f"/api/itens/{ids['item']}/referencia", json={
        "observacao_id": paginas["https://www.gimba.com.br/p/papel-90"]["id"],
        "justificativa": "o edital pede papel de 90 g"}), 201)
    assert resposta["recomparadas"] == 1
    paginas = _paginas(api, ids["item"])
    assert paginas["https://www.gimba.com.br/p/papel-90"]["correspondencia"]["origem"] == "humano"
    assert paginas["https://www.lepok.com.br/p/papel-75"]["correspondencia"]["status"] == "vermelho"
    assert paginas["https://www.kalunga.com.br/p/papel-75"]["correspondencia"]["status"] == "verde"  # decisão da pessoa

    historico = _ok(api.get(f"/api/projetos/{ids['projeto']}/historico"))
    assert sum(1 for e in historico if e["entidade"] == "decisao") >= 2


def test_fotos_das_paginas(ambiente):
    api, app = ambiente
    ids = _papel(api, app)
    paginas = _paginas(api, ids["item"])
    assert paginas["https://www.kalunga.com.br/p/papel-75"]["imagem"] == "https://img.kalunga.com.br/papel-75.jpg"
    assert paginas["https://www.lepok.com.br/p/papel-75"]["imagem"] == "https://cdn.lepok.com.br/papel.png"  # og:image
    assert paginas["https://www.gimba.com.br/p/papel-90"]["imagem"] == "https://www.gimba.com.br/img/papel-90.jpg"
    ofertas = _item_da_revisao(api, ids)["ofertas"]
    assert {o["imagem"] for o in ofertas.values()} >= {"https://img.kalunga.com.br/papel-75.jpg"}


def test_referencia_so_por_pessoa_e_do_mesmo_item(ambiente):
    api, app = ambiente
    ids = _papel(api, app)
    resposta = api.post(f"/api/itens/{ids['item']}/referencia", json={"observacao_id": "nao-existe", "justificativa": "x"})
    assert resposta.status_code == 404
    resposta = api.post(f"/api/itens/{ids['item']}/referencia", json={"observacao_id": "x", "justificativa": ""})
    assert resposta.status_code == 422
