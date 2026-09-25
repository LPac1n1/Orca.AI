"""Fechar o lote (D-72): pesquisa tudo, mostra o que falta e sugere outra marca que existe nas 3 lojas."""

import json
from datetime import date
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, LOJAS, abrir_navegador_falso, cliente_cnpj, cnpj_de_teste, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.coleta import Captura
from orca.dominio import formatar_cnpj

CNPJ = {"kalunga.com.br": LOJAS["kalunga.com.br"][0], "lepok.com.br": LOJAS["lepok.com.br"][0],
        "artpel.com.br": cnpj_de_teste(800), "gimba.com.br": LOJAS["gimba.com.br"][0]}
PAPEL = ("papel", "Papel Sulfite A4 75g 500 folhas Chamex", "Chamex", "7891173023001")
GOLLER = ("goller", "Grampeador de Mesa Goller 26/6 até 20 Folhas GE-309", "Goller", "7896001300309")
SPIRAL = ("spiral", "Grampeador de Mesa Spiral 26/6 até 20 Folhas 2933A", "Spiral", "7908727610263")
PRODUTOS = {  # o que cada loja vende: (produto, preço) — o Goller só existe na Lepok
    "kalunga.com.br": [(PAPEL, 3450), (SPIRAL, 2990)],
    "lepok.com.br": [(PAPEL, 3390), (GOLLER, 1869), (SPIRAL, 3100)],
    "artpel.com.br": [(PAPEL, 3500), (SPIRAL, 2850)],
    "gimba.com.br": [(PAPEL, 3300), (GOLLER, 1800)],  # só com janela (robots.txt): entra colando o link
}


def _reais(centavos: int) -> str:
    return f"R$ {centavos // 100},{centavos % 100:02d}"


class Lojas:
    def __init__(self):
        self.buscas: list[str] = []
        self.capturas: list[str] = []

    def resultados_de_busca(self, url: str, padrao: str, seletor: str | None = None):
        termo = unquote(url).lower()
        self.buscas.append(unquote(url))
        dominio = url.split("/")[2].removeprefix("www.")
        consulta = termo.split("=")[-1] if "=" in termo else termo.rsplit("/", 1)[-1].replace("-", " ")  # Lepok: /busca/a-b
        palavras = [p for p in consulta.replace("+", " ").split() if len(p) > 2]
        cartoes = []
        for (slug, titulo, marca, _), preco in PRODUTOS[dominio]:
            if all(p in titulo.lower() for p in palavras if not p[0].isdigit()):  # busca exige as palavras
                cartoes.append({"href": f"https://www.{dominio}/p/{slug}", "titulo": titulo,
                                "texto": f"{titulo} {_reais(preco)}"})
        return 200, cartoes

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        self.capturas.append(url)
        dominio = url.split("/")[2].removeprefix("www.")
        if "/p/" not in url:  # página da busca: prova do "não encontrado"
            return Captura(url, url, COLETA, "Busca", 200, "", (), "Nenhum resultado", pdf_valido(url), b"PNG",
                           b"MHTML-" + url.encode(), None, "C1", None)
        slug = url.rsplit("/", 1)[-1]
        (_, titulo, marca, ean), preco = next(x for x in PRODUTOS[dominio] if x[0][0] == slug)
        produto = {"@type": "Product", "name": titulo, "brand": marca, "gtin13": ean, "image": f"https://img/{slug}.jpg",
                   "offers": {"price": f"{preco // 100}.{preco % 100:02d}", "priceCurrency": "BRL"}}
        html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
        texto = f"{titulo} por {_reais(preco)} · CNPJ {formatar_cnpj(CNPJ[dominio])}"
        return Captura(url, url, COLETA, titulo, 200, html, (), texto, pdf_valido(url), b"PNG", b"MHTML-" + url.encode(),
                       None, "C1", None)


@pytest.fixture
def ambiente(tmp_path):
    lojas = Lojas()
    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir_navegador_falso(lojas), cliente_http=cliente_cnpj,
                               hoje=lambda: date(2026, 9, 25), intervalo_busca_s=0)
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, lojas


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _lote(api) -> dict:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 200_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "Escritório"}), 201)
    ids = {"projeto": projeto["id"], "lote": lote["id"]}
    for nome, descricao, categoria, marca in (("papel", "Papel sulfite A4 75g 500 folhas", "papel", "Chamex"),
                                              ("grampeador", "Grampeador de mesa 26/6", "papelaria", "Goller")):
        ids[nome] = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
            "descricao": descricao, "categoria": categoria, "marca": marca, "qtd_planejada": 1, "mes_fim": 12}), 201)["id"]
    return ids


def test_fechar_o_lote_sugere_outra_marca_que_existe_nas_3_lojas(ambiente):
    api, app, lojas = ambiente
    ids = _lote(api)
    [tarefa] = _ok(api.post(f"/api/lotes/{ids['lote']}/fechar",
                            json={"lojas": ["kalunga", "lepok", "artpel"]}), 202)["tarefas"]
    assert tarefa["tipo"] == "fechar_lote"
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida", feita
    r = feita["resultado"]

    # D-68 (revista): nas lojas sem o grampeador Goller, o papel foi pesquisado e achado do mesmo jeito
    resumo = {x["loja"]: x for x in r["resumo"]}
    assert resumo["Kalunga"]["nao_encontrados"] == ["Grampeador de mesa 26/6"] and resumo["Kalunga"]["encontrados"] == 1
    assert resumo["Art Pel"]["nao_encontrados"] == ["Grampeador de mesa 26/6"] and resumo["Art Pel"]["encontrados"] == 1
    # o nome da loja vem da consulta do CNPJ (aqui, simulada)
    assert list(r["faltando"]) == [ids["grampeador"]] and len(r["faltando"][ids["grampeador"]]) == 2

    # outra marca que existe nas 3 lojas, com a soma da prévia
    [opcao] = r["alternativas"][ids["grampeador"]]
    assert opcao["marca"] is None and "Spiral" in opcao["titulo"] and opcao["situacao"] == "completa"
    assert opcao["soma_centavos"] == 2990 + 3100 + 2850
    assert all(l["url"].endswith("/p/spiral") for l in opcao["lojas"])
    assert "com sugestão de outra marca" in r["mensagem"]

    # a situação ao vivo mostra o que falta e as sugestões
    situacao = _ok(api.get(f"/api/lotes/{ids['lote']}/fechamento"))
    assert situacao["itens"] == 2 and len(situacao["melhores"]) == 3
    assert [f["item"] for f in situacao["faltando"]] == ["Grampeador de mesa 26/6"]
    assert situacao["ultima"]["alternativas"][ids["grampeador"]][0]["titulo"] == opcao["titulo"]

    # a pessoa aceita a sugestão: o produto é trocado e as páginas das 3 lojas vão para a fila como prova
    usada = _ok(api.post(f"/api/itens/{ids['grampeador']}/usar-alternativa", json={
        "tarefa_id": tarefa["id"], "indice": 0, "descricao": "Grampeador de mesa 26/6", "marca": "Spiral",
        "justificativa": "D-72: o Goller não existe nas 3 lojas; o Spiral existe"}), 201)
    assert usada["item"]["substitui_item_id"] == ids["grampeador"] and len(usada["tarefas"]) == 3
    app.state.servico.fila.processar_todas()
    situacao = _ok(api.get(f"/api/lotes/{ids['lote']}/fechamento"))
    assert situacao["faltando"] == []  # agora as 3 lojas têm os 2 itens
    assert situacao["ultima"]["alternativas"] == {}  # a sugestão era do item antigo


def test_sugestao_de_outro_lote_nao_vale(ambiente):
    api, app, _ = ambiente
    a, b = _lote(api), _lote(api)
    [tarefa] = _ok(api.post(f"/api/lotes/{a['lote']}/fechar", json={"lojas": ["kalunga", "lepok", "artpel"]}),
                   202)["tarefas"]
    app.state.servico.fila.processar_proxima("principal")
    resposta = api.post(f"/api/itens/{b['grampeador']}/usar-alternativa", json={
        "tarefa_id": tarefa["id"], "indice": 0, "descricao": "x", "marca": "y", "justificativa": "z"})
    assert resposta.status_code == 409


def test_sugestoes_mesmo_com_a_loja_mais_completa_so_na_janela(ambiente):
    """Rodada 2 do piloto: a Gimba (só com janela) era a mais completa e as sugestões não eram procuradas."""
    api, app, _ = ambiente
    ids = _lote(api)
    for slug, item in (("papel", ids["papel"]), ("goller", ids["grampeador"])):
        _ok(api.post(f"/api/itens/{item}/coletas", json={"url": f"https://www.gimba.com.br/p/{slug}"}), 202)
    app.state.servico.fila.processar_todas()
    [tarefa] = _ok(api.post(f"/api/lotes/{ids['lote']}/fechar",
                            json={"lojas": ["kalunga", "lepok", "artpel"]}), 202)["tarefas"]
    app.state.servico.fila.processar_proxima("principal")
    r = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))["resultado"]
    [opcao] = r["alternativas"][ids["grampeador"]]
    assert "Spiral" in opcao["titulo"] and len(opcao["lojas"]) == 3
    assert any("sem busca automática" in a for a in r["avisos"])

