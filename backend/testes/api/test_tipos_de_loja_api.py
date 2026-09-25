"""O que cada loja vende (D-74): separação das lojas por lote, descoberta automática e aprendizado."""

import json
from contextlib import contextmanager
from datetime import date
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, LOJAS, cliente_cnpj, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.busca import Candidato
from orca.busca.classificacao import nomes, vende_o_tipo
from orca.coleta import Captura
from orca.dominio import formatar_cnpj


def _c(*titulos):
    return [Candidato(f"https://x/{n}", t) for n, t in enumerate(titulos)]


@pytest.mark.parametrize(("termo", "titulos", "vende"), [
    ("Caneta esferográfica", ("Caneta Esferográfica Bic Cristal Azul", "Caneta Esferográfica Compactor 07"), True),
    ("Caneta esferográfica", ("Caneta Esferográfica Bic Cristal Azul",), False),  # uma só não basta
    ("Copo descartável", ("Copo on the rocks 270 ml Centra", "Copo long drink 330 ml"), False),  # copo de vidro
    ("Papel sulfite A4", ("Papel Higiênico Neve 30m", "Papel toalha Snob 2 rolos"), False),
    ("Detergente", ("Dispenser para Detergente Smile", "Detergente Ypê 500ml", "Detergente Limpol 500ml"), True),
])
def test_regra_do_tipo(termo, titulos, vende):
    assert vende_o_tipo(termo, _c(*titulos)) is vende


def test_nomes_dos_tipos():
    assert nomes(["papelaria", "escritorio", "limpeza"]) == ["Papelaria e escritório", "Limpeza e higiene"]


class Navegador:
    """A loja nova (papelaria) só tem canetas; a Gimba tem a página de um papel (captura por link)."""

    def __init__(self):
        self.buscas: list[str] = []

    def resultados_de_busca(self, url: str, padrao: str, seletor: str | None = None):
        termo = unquote(url).rsplit("=", 1)[-1].lower()
        self.buscas.append(termo)
        if "caneta" in termo:
            return 200, [{"href": f"https://www.papelarianova.com.br/p/{n}", "titulo": t, "texto": "R$ 2,00"}
                         for n, t in enumerate(("Caneta Esferográfica Bic Cristal Azul", "Caneta Esferográfica Compactor"))]
        return 200, [{"href": "https://www.papelarianova.com.br/p/9", "titulo": "Agenda 2027", "texto": "R$ 30,00"}]

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        produto = {"@type": "Product", "name": "Papel Sulfite A4 75g 500 folhas Chamex", "brand": "Chamex",
                   "gtin13": "7891173023001", "offers": {"price": "33.00", "priceCurrency": "BRL"}}
        html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
        texto = f"Papel Sulfite A4 75g 500 folhas Chamex R$ 33,00 · CNPJ {formatar_cnpj(LOJAS['tendaatacado.com.br'][0])}"
        return Captura(url, url, COLETA, "Papel", 200, html, (), texto, pdf_valido(url), b"PNG", b"MHTML-" + url.encode(),
                       None, "C1", None)


@pytest.fixture
def ambiente(tmp_path):
    navegador = Navegador()

    @contextmanager
    def abrir():
        yield navegador

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir, cliente_http=cliente_cnpj,
                               hoje=lambda: date(2026, 9, 25), intervalo_busca_s=0)
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, navegador


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _lote_de_papelaria(api) -> dict:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 100_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "Escritório"}), 201)
    item = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Papel sulfite A4 75g 500 folhas", "categoria": "papel", "marca": "Chamex", "qtd_planejada": 1,
        "mes_fim": 12}), 201)
    return {"org": org["id"], "lote": lote["id"], "item": item["id"]}


def _lojas(api, lote_id) -> dict:
    return {l["id"]: l for l in _ok(api.get(f"/api/lotes/{lote_id}/lojas-de-busca"))["lojas"]}


def test_lojas_separadas_pelo_que_vendem(ambiente):
    api, _, _ = ambiente
    ids = _lote_de_papelaria(api)
    lojas = _lojas(api, ids["lote"])
    assert lojas["kalunga"]["situacao"] == "todas" and lojas["kalunga"]["sugerida"]
    assert "Papelaria e escritório" in lojas["kalunga"]["tipos"] and lojas["kalunga"]["do_lote"] == ["Papelaria e escritório"]
    assert lojas["oba_hortifruti"]["situacao"] == "nenhuma" and not lojas["oba_hortifruti"]["sugerida"]
    assert lojas["gimba"]["situacao"] == "todas"  # também vende papelaria (com janela)


def test_loja_nova_e_classificada_sozinha(ambiente):
    api, app, navegador = ambiente
    ids = _lote_de_papelaria(api)
    rota = f"/api/organizacoes/{ids['org']}/catalogos/lojas"
    vigente = _ok(api.get(rota))["vigente"]
    vigente["lojas"].append({"id": "papelaria_nova", "nome": "Papelaria Nova", "dominio": "www.papelarianova.com.br",
                             "coleta": "C1", "busca": {"modo": "pagina", "url": "https://www.papelarianova.com.br/b?q={termo}",
                                                       "produto": "/p/"}})
    salvo = _ok(api.put(rota, json={"conteudo": vigente, "resumo": "acrescentou Papelaria Nova"}))
    assert salvo["classificando"] == ["Papelaria Nova"]
    antes = _lojas(api, ids["lote"])["papelaria_nova"]
    assert antes["situacao"] == "desconhecida" and antes["classificando"]

    app.state.servico.fila.processar_proxima("principal")
    tarefa = next(t for t in _ok(api.get("/api/tarefas?limite=5")) if t["tipo"] == "classificar_loja")
    assert tarefa["estado"] == "concluida", tarefa
    assert tarefa["resultado"]["categorias"] == ["papelaria"]  # achou canetas; nada de arroz, detergente…
    assert "caneta esferográfica" in navegador.buscas

    depois = _lojas(api, ids["lote"])["papelaria_nova"]
    assert depois["situacao"] == "todas" and not depois["classificando"]
    entrada = next(e for e in _ok(api.get(rota))["vigente"]["lojas"] if e["id"] == "papelaria_nova")
    assert entrada["categorias_origem"] == "automatica" and entrada["categorias_em"] == "2026-09-25"

    # salvar de novo não descobre de novo
    assert _ok(api.put(rota, json={"conteudo": _ok(api.get(rota))["vigente"], "resumo": "nada"}))["classificando"] == []


def test_loja_aprende_com_as_paginas_confirmadas(ambiente):
    api, app, _ = ambiente
    ids = _lote_de_papelaria(api)
    assert _lojas(api, ids["lote"])["tenda_atacado"]["situacao"] == "nenhuma"  # no catálogo: alimentos, limpeza…
    _ok(api.post(f"/api/itens/{ids['item']}/coletas", json={"url": "https://www.tendaatacado.com.br/produto/papel"}), 202)
    app.state.servico.fila.processar_todas()
    obs = _ok(api.get(f"/api/itens/{ids['item']}/observacoes"))[0]
    _ok(api.post("/api/correspondencias", json={"item_id": ids["item"], "observacao_id": obs["id"], "status": "verde",
                                                "justificativa": "é o papel"}), 201)
    tenda = _lojas(api, ids["lote"])["tenda_atacado"]
    assert tenda["situacao"] == "todas" and tenda["aprendido"] == ["Papelaria e escritório"]


def test_so_loja_com_busca_automatica_e_descoberta(ambiente):
    api, _, _ = ambiente
    ids = _lote_de_papelaria(api)
    resposta = api.post(f"/api/organizacoes/{ids['org']}/lojas/gimba/classificar")
    assert resposta.status_code == 400 and "aprende com as páginas" in resposta.json()["erro"]
