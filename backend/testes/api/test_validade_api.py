"""Validade das pesquisas (D-12; Fase 2, etapa 12): o que venceu e "pesquisar de novo" em um clique."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from apoio_api import PAPEL, VAGAS, cliente_cnpj, pagina_produto, pagina_vaga
from orca.api import Configuracao, contexto_padrao, criar_app

HOJE = date(2027, 4, 1)  # as pesquisas simuladas são de 23/09/2026: mais de 180 dias depois


class Navegador:
    """Primeira leitura com a data das páginas simuladas; as seguintes, "hoje"."""

    def __init__(self):
        self.pedidas: list[str] = []
        self.agora: datetime | None = None

    def capturar(self, url: str, cep: str | None = None):
        self.pedidas.append(url)
        captura = pagina_vaga(url) if url in VAGAS else pagina_produto(url)
        return replace(captura, capturado_em=self.agora) if self.agora else captura


@pytest.fixture
def ambiente(tmp_path):
    navegador = Navegador()

    @contextmanager
    def abrir():
        yield navegador

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir, cliente_http=cliente_cnpj, hoje=lambda: HOJE)
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, navegador


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def test_pesquisas_vencidas_e_pesquisar_de_novo(ambiente):
    api, app, navegador = ambiente
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 100_000,
                                                   "duracao_meses": 12}), 201)["id"]
    orc = _ok(api.post(f"/api/projetos/{projeto}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orc['id']}/lotes", json={"nome": "L"}), 201)
    item = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Papel sulfite A4 75g 500 folhas", "categoria": "papel", "marca": "Chamex", "ean": PAPEL,
        "qtd_planejada": 1, "mes_fim": 12}), 201)["id"]
    for loja in ("kalunga", "gimba"):
        _ok(api.post(f"/api/itens/{item}/coletas", json={"url": f"https://www.{loja}.com.br/p/{PAPEL}"}), 202)
    app.state.servico.fila.processar_todas()

    vencidas = _ok(api.get(f"/api/projetos/{projeto}/validade"))["pesquisas"]
    assert [(p["loja"], p["situacao"], p["como"]) for p in vencidas] == [
        ("Kalunga", "vencida", "coletar_item"), ("Gimba (Supricorp Suprimentos)", "vencida", "coletar_item")]
    assert any("2 pesquisa(s) vencida(s)" in a for a in _ok(api.get(f"/api/projetos/{projeto}/painel"))["alertas"])

    # uma só, depois todas
    navegador.agora = datetime(2027, 3, 31, 15, 0, tzinfo=UTC)
    uma = _ok(api.post(f"/api/projetos/{projeto}/pesquisar-de-novo",
                       json={"observacoes": [vencidas[0]["observacao_id"]]}), 202)
    assert len(uma["tarefas"]) == 1 and uma["tarefas"][0]["parametros"]["url"] == vencidas[0]["url"]
    app.state.servico.fila.processar_todas()
    restantes = _ok(api.get(f"/api/projetos/{projeto}/validade"))["pesquisas"]
    assert [p["loja"] for p in restantes] == ["Gimba (Supricorp Suprimentos)"]
    todas = _ok(api.post(f"/api/projetos/{projeto}/pesquisar-de-novo", json={}), 202)
    assert len(todas["tarefas"]) == 1
    app.state.servico.fila.processar_todas()
    assert _ok(api.get(f"/api/projetos/{projeto}/validade"))["pesquisas"] == []
    assert len(_ok(api.get(f"/api/itens/{item}/observacoes"))) == 4  # as pesquisas antigas continuam no histórico


def test_pdf_enviado_so_a_pessoa_refaz(ambiente):
    from apoio_api import pdf_com_texto

    api, _, _ = ambiente
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 100_000,
                                                   "duracao_meses": 12}), 201)["id"]
    orc = _ok(api.post(f"/api/projetos/{projeto}/orcamentos", json={"nome": "M", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{orc['id']}/lotes", json={"nome": "L"}), 201)
    item = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={"descricao": "Papel", "qtd_planejada": 1, "mes_fim": 12}), 201)["id"]
    url = "https://www.extramercado.com.br/p/1"
    _ok(api.post(f"/api/itens/{item}/pdf", data={"url": url, "preco_centavos": "2890"},
                 files={"arquivo": ("p.pdf", pdf_com_texto([url, "Papel R$ 28,90"]), "application/pdf")}), 201)
    pesquisas = _ok(api.get(f"/api/projetos/{projeto}/validade"))["pesquisas"]
    assert [p["como"] for p in pesquisas] == ["pdf"]
    resposta = _ok(api.post(f"/api/projetos/{projeto}/pesquisar-de-novo", json={}), 202)
    assert resposta["tarefas"] == [] and len(resposta["so_pela_pessoa"]) == 1
    assert resposta["so_pela_pessoa"][0].startswith("Papel (")
