"""Piloto (24/09/2026): preço no Pix ou boleto (D-60), correção do preço pela tela e CNPJ consultado na hora."""

import json
from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, PAPEL, cliente_cnpj, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.coleta import Captura
from orca.dominio import formatar_cnpj

LEPOK = "19576717000104"


def pagina_lepok(url: str) -> Captura:
    """Como a página real da Lepok: os dados da página trazem o parcelado; o texto mostra os dois preços."""
    produto = {"@type": "Product", "name": "Papel Sulfite A4 75g 500 folhas", "brand": "Chamex", "gtin13": PAPEL,
               "offers": {"price": "17.10", "priceCurrency": "BRL"}}
    html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
    texto = (f"Papel Sulfite A4 75g 500 folhas Chamex\nR$ 16,59 no boleto ou PIX\nou R$ 17,10 em 1x\nver parcelas\n"
             f"Veja também: Caneta azul R$ 2,50\nLepok CNPJ {formatar_cnpj(LEPOK)}")
    return Captura(url, url, COLETA, "Papel Sulfite", 200, html, (), texto, pdf_valido(url), b"PNG-" + url.encode(),
                   b"MHTML-" + url.encode(), None, "C1", None)


class Navegador:
    def capturar(self, url: str, cep: str | None = None) -> Captura:
        return pagina_lepok(url)


@pytest.fixture
def api(tmp_path):
    @contextmanager
    def abrir():
        yield Navegador()

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir, cliente_http=cliente_cnpj, hoje=lambda: date(2026, 9, 24))
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as cliente:
        cliente.processar = app.state.servico.fila.processar_todas
        yield cliente


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _item(api) -> tuple[str, str]:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 100_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "Materiais", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "Papelaria"}), 201)
    item = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Papel sulfite A4 75g 500 folhas", "categoria": "papel", "marca": "Chamex", "ean": PAPEL,
        "qtd_planejada": 1, "mes_fim": 12}), 201)
    return projeto["id"], item["id"]


def _coletar(api, item_id: str, url: str) -> dict:
    _ok(api.post(f"/api/itens/{item_id}/coletas", json={"url": url}), 202)
    api.processar()
    return next(o for o in _ok(api.get(f"/api/itens/{item_id}/observacoes")) if o["url"] == url)


def test_preco_no_pix_ou_boleto_e_cnpj_consultado_na_hora(api):
    projeto, item = _item(api)
    obs = _coletar(api, item, "https://www.lepok.com.br/p/1")
    assert obs["preco_centavos"] == 1659 and obs["preco_no_html"] and obs["forma_de_pagamento"] == "pix_ou_boleto"
    assert any("no Pix ou boleto (D-60)" in a for a in obs["avisos"])
    formas = {p["centavos"]: p["forma"] for p in obs["precos_da_pagina"]}
    assert (formas[1659], formas[1710]) == ("pix_ou_boleto", "parcelado")
    assert _ok(api.get(f"/api/projetos/{projeto}/painel"))["cnpjs_sem_consulta"] == []  # já consultado

    # a regra é configurável: "ignorar" volta ao preço cheio da página
    _ok(api.put(f"/api/projetos/{projeto}/regras", json={"conteudo": {"preco_referencia": {"desconto_pix": "ignorar"}}}))
    assert _coletar(api, item, "https://www.lepok.com.br/p/2")["preco_centavos"] == 1710


def test_corrigir_o_preco_com_outro_valor_da_mesma_pagina(api):
    projeto, item = _item(api)
    _ok(api.put(f"/api/projetos/{projeto}/regras", json={"conteudo": {"preco_referencia": {"desconto_pix": "ignorar"}}}))
    anterior = _coletar(api, item, "https://www.lepok.com.br/p/1")
    assert anterior["preco_centavos"] == 1710 and anterior["correspondencia"]["origem"] == "ean"
    rota = f"/api/observacoes/{anterior['id']}/corrigir-preco"

    fora = api.post(rota, json={"preco_centavos": 1234, "justificativa": "teste"})
    assert fora.status_code == 400 and "não aparece na página salva" in fora.json()["erro"]
    assert api.post(rota, json={"preco_centavos": 1659, "justificativa": " "}).status_code == 400

    nova = _ok(api.post(rota, json={"preco_centavos": 1659, "justificativa": "preço no Pix (D-60)"}), 201)
    assert nova["preco_centavos"] == 1659 and nova["evidencia_id"] == anterior["evidencia_id"]
    assert nova["correspondencia"]["status"] == "verde" and any("preço corrigido" in a for a in nova["avisos"])
    observacoes = _ok(api.get(f"/api/itens/{item}/observacoes"))
    assert [o["preco_centavos"] for o in observacoes] == [1659, 1710]  # a antiga continua no histórico
    oferta = next(iter(_ok(api.get(f"/api/projetos/{projeto}/revisao"))["orcamentos"][0]["lotes"][0]["itens"][0]["ofertas"].values()))
    assert oferta["preco_centavos"] == 1659 and oferta["observacao_id"] == nova["id"]


def test_decisao_da_pessoa_continua_depois_da_correcao(api):
    projeto, item = _item(api)
    _ok(api.put(f"/api/projetos/{projeto}/regras", json={"conteudo": {"preco_referencia": {"desconto_pix": "ignorar"}}}))
    anterior = _coletar(api, item, "https://www.lepok.com.br/p/1")
    _ok(api.post("/api/correspondencias", json={"item_id": item, "observacao_id": anterior["id"], "status": "vermelho",
                                                "justificativa": "embalagem diferente"}), 201)
    nova = _ok(api.post(f"/api/observacoes/{anterior['id']}/corrigir-preco",
                        json={"preco_centavos": 1659, "justificativa": "preço no Pix"}), 201)
    assert (nova["correspondencia"]["status"], nova["correspondencia"]["origem"]) == ("vermelho", "humano")
