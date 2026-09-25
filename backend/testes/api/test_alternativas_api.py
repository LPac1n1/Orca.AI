"""Saída 1 com busca (D-23; Fase 2, etapa 14): alternativa nas 3 lojas do trio, escolha e provas."""

import json
from datetime import date
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from apoio_api import COLETA, LEITE, LOJAS, PAPEL, abrir_navegador_falso, cliente_cnpj, cnpj_de_teste, pdf_valido
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.coleta import Captura
from orca.dominio import formatar_cnpj

# Três lojas com busca automática: (CNPJ, preço do papel, preço do leite). A Lepok tem o menor total e o
# leite dela passa da média (R$ 11,00 > R$ 10,50).
TRIO = {
    "lepok.com.br": (LOJAS["lepok.com.br"][0], 3400, 1100),
    "kalunga.com.br": (LOJAS["kalunga.com.br"][0], 3450, 1050),
    "artpel.com.br": (cnpj_de_teste(800), 3500, 1000),
}
ALTERNATIVAS = {  # domínio: [(endereço, título, preço)] — o que a busca de cada loja do trio mostra
    "lepok.com.br": [("moca", "Leite Condensado Moça 395g", 1100), ("italac", "Leite Condensado Italac 395g", 950),
                     ("pira", "Leite Condensado Piracanjuba 395g", 1080)],
    "kalunga.com.br": [("pira", "Leite Condensado Piracanjuba 395g", 1000),
                       ("italac", "Leite Condensado Italac 395g", 1000)],
    "artpel.com.br": [("italac", "Leite condensado Italac 395 g", 1020), ("pira", "Leite Condensado Piracanjuba 395g", 990)],
}
EAN = {"italac": "7898080640611", "pira": "7896279600512", "moca": LEITE}


def _reais(centavos: int) -> str:
    return f"R$ {centavos // 100},{centavos % 100:02d}"


def _pagina(url: str, titulo: str, marca: str, ean: str, preco: int, cnpj: str) -> Captura:
    produto = {"@type": "Product", "name": titulo, "brand": marca, "gtin13": ean,
               "offers": {"price": f"{preco // 100}.{preco % 100:02d}", "priceCurrency": "BRL"}}
    html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
    texto = f"{titulo} por {_reais(preco)} · Loja CNPJ {formatar_cnpj(cnpj)}"
    return Captura(url, url, COLETA, titulo, 200, html, (), texto, pdf_valido(url), b"PNG-" + url.encode(),
                   b"MHTML-" + url.encode(), None, "C1", None)


class NavegadorComBusca:
    def __init__(self):
        self.pedidas: list[str] = []
        self.buscas: list[str] = []

    def resultados_de_busca(self, url: str, padrao: str, seletor: str | None = None):
        self.buscas.append(unquote(url))
        dominio = url.split("/")[2].removeprefix("www.")
        return 200, [{"href": f"https://www.{dominio}/produto/{slug}?PID=1", "titulo": titulo,
                      "texto": f"{titulo} {_reais(preco)}"} for slug, titulo, preco in ALTERNATIVAS.get(dominio, [])]

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        self.pedidas.append(url)
        dominio = url.split("/")[2].removeprefix("www.")
        cnpj, preco_papel, preco_leite = TRIO[dominio]
        if "/produto/" not in url:  # as páginas do lote: /p/<ean>
            ean = url.rstrip("/").split("/")[-1]
            if ean == PAPEL:
                return _pagina(url, "Papel Sulfite A4 75g 500 folhas", "Chamex", ean, preco_papel, cnpj)
            return _pagina(url, "Leite Condensado Moça 395g", "Moça", ean, preco_leite, cnpj)
        slug = url.split("/produto/")[1].split("?")[0]
        _, titulo, preco = next(a for a in ALTERNATIVAS[dominio] if a[0] == slug)
        return _pagina(url, titulo, titulo.split()[2], EAN[slug], preco, cnpj)


@pytest.fixture
def ambiente(tmp_path):
    navegador = NavegadorComBusca()
    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir_navegador_falso(navegador), cliente_http=cliente_cnpj,
                               hoje=lambda: date(2026, 9, 24), intervalo_busca_s=0)
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, navegador


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _lote_com_leite_acima_da_media(api, app) -> dict:
    """A Lepok é a escolhida e o leite dela passa da média (R$ 11,00 > R$ 10,50)."""
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 600_000,
                                                   "duracao_meses": 12}), 201)
    orcamento = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orcamento['id']}/lotes", json={"nome": "Copa e escritório"}), 201)
    ids = {"projeto": projeto["id"], "lote": lote["id"]}
    for nome, descricao, categoria, marca, ean, qtd in (("papel", "Papel sulfite A4 75g 500 folhas", "papel", "Chamex", PAPEL, 10),
                                                        ("leite", "Leite condensado 395g", "alimento", "Moça", LEITE, 5)):
        ids[nome] = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
            "descricao": descricao, "categoria": categoria, "marca": marca, "ean": ean, "qtd_planejada": qtd,
            "mes_fim": 12}), 201)["id"]
        for dominio in TRIO:
            _ok(api.post(f"/api/itens/{ids[nome]}/coletas", json={"url": f"https://www.{dominio}/p/{ean}"}), 202)
    app.state.servico.fila.processar_todas()
    return ids


def _lote_da_revisao(api, ids) -> dict:
    return _ok(api.get(f"/api/projetos/{ids['projeto']}/revisao"))["orcamentos"][0]["lotes"][0]


def test_saida_1_com_busca_de_ponta_a_ponta(ambiente):
    api, app, navegador = ambiente
    ids = _lote_com_leite_acima_da_media(api, app)
    lote = _lote_da_revisao(api, ids)
    leite = next(i for i in lote["itens"] if i["id"] == ids["leite"])
    assert leite["dentro_da_media"] is False

    tarefa = _ok(api.post(f"/api/itens/{ids['leite']}/alternativas"), 202)
    assert tarefa["tipo"] == "buscar_alternativas"
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida", feita
    r = feita["resultado"]
    assert r["termo"] == "Leite condensado 395g"  # sem a marca
    assert all("Moça" not in b and "Moca" not in b for b in navegador.buscas)
    assert [l["busca"] for l in r["lojas"]] == ["Lepok", "Kalunga", "Art Pel"]  # o trio
    assert len(navegador.buscas) == 3 and r["avisos"] == []
    opcoes = {o["titulo"]: o for o in r["opcoes"]}
    assert set(opcoes) == {"Leite Condensado Italac 395g", "Leite Condensado Piracanjuba 395g"}  # a Moça não é alternativa
    italac, pira = opcoes["Leite Condensado Italac 395g"], opcoes["Leite Condensado Piracanjuba 395g"]
    assert r["opcoes"][0]["titulo"] == italac["titulo"]  # as que resolvem primeiro
    assert italac["situacao"] == "resolve" and italac["impacto_centavos"] == (950 - 1100) * 5 * 12
    assert [l["preco_centavos"] for l in italac["lojas"]] == [950, 1000, 1020] and italac["media"] == "R$ 9,90"
    assert pira["situacao"] == "nao_resolve" and "passa da média" in pira["motivo"]
    assert "1 de 2" in r["mensagem"]
    # só mostra: nada foi trocado
    assert _ok(api.get(f"/api/itens/{ids['leite']}/observacoes"))

    # a escolha da pessoa: troca o produto e captura as 3 páginas como prova
    resposta = api.post(f"/api/itens/{ids['papel']}/usar-alternativa", json={
        "tarefa_id": tarefa["id"], "indice": 0, "descricao": "Leite condensado 395g", "marca": "Italac",
        "justificativa": "Saída 1"})
    assert resposta.status_code == 409  # a busca não é deste item
    usada = _ok(api.post(f"/api/itens/{ids['leite']}/usar-alternativa", json={
        "tarefa_id": tarefa["id"], "indice": 0, "descricao": "Leite condensado 395g", "marca": "Italac",
        "justificativa": "Saída 1 (D-23): Moça acima da média na Lepok"}), 201)
    novo = usada["item"]
    assert novo["substitui_item_id"] == ids["leite"] and novo["marca"] == "Italac" and novo["ean"] is None
    assert sorted(t["parametros"]["url"] for t in usada["tarefas"]) == sorted(l["url"] for l in italac["lojas"])
    app.state.servico.fila.processar_todas()
    observacoes = _ok(api.get(f"/api/itens/{novo['id']}/observacoes"))
    assert sorted(o["preco_centavos"] for o in observacoes) == [950, 1000, 1020]

    # 🟢 por atributos espera a confirmação da pessoa, como em qualquer produto; depois o lote fecha (T-04)
    assert _lote_da_revisao(api, ids)["situacao"] != "ok"
    for o in observacoes:
        assert o["correspondencia"]["status"] == "verde"
        _ok(api.post("/api/correspondencias", json={"item_id": novo["id"], "observacao_id": o["id"], "status": "verde",
                                                    "justificativa": "mesmo produto"}), 201)
    lote = _lote_da_revisao(api, ids)
    assert lote["situacao"] == "ok"
    italac_na_grade = next(i for i in lote["itens"] if i["id"] == novo["id"])
    assert italac_na_grade["dentro_da_media"] is True
    assert next(l for l in lote["lojas"] if l["posicao"] == 1)["cnpj"] == LOJAS["lepok.com.br"][0]  # continua a escolhida

    historico = _ok(api.get(f"/api/projetos/{ids['projeto']}/historico"))
    assert any(e["entidade"] == "decisao" and e["autor"] == "usuario:Leonardo" for e in historico)


def test_item_dentro_da_media_nao_tem_o_que_resolver(ambiente):
    api, app, _ = ambiente
    ids = _lote_com_leite_acima_da_media(api, app)
    tarefa = _ok(api.post(f"/api/itens/{ids['papel']}/alternativas"), 202)
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "falhou" and "não está acima da média" in feita["mensagem"]
    resposta = api.post(f"/api/itens/{ids['papel']}/usar-alternativa", json={
        "tarefa_id": tarefa["id"], "indice": 0, "descricao": "x", "marca": "y", "justificativa": "z"})
    assert resposta.status_code == 409
