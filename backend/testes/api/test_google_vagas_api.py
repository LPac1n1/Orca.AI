"""Google Vagas pela SerpApi (D-69 revista em 25/09/2026), com o serviço simulado."""

import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from apoio_api import VAGAS, NavegadorFalso, abrir_navegador_falso, cliente_cnpj
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.busca.serpapi import buscar_vagas_google
from orca.cofre import CofreEmMemoria

RESPOSTA = {"jobs_results": [
    {"title": "Educador Social", "company_name": "Instituto A", "location": "São Paulo, SP",
     "detected_extensions": {"salary": "R$ 2.500–R$ 3.000 por mês", "posted_at": "há 3 dias"},
     "apply_options": [{"title": "Indeed", "link": "https://br.indeed.com/viewjob?jk=abc"},
                       {"title": "Catho", "link": "https://www.catho.com.br/vagas/1"}]},
    {"title": "Educador Social", "company_name": "Associação B", "location": "São Paulo, SP",
     "detected_extensions": {"posted_at": "há 1 semana"},
     "apply_options": [{"title": "InfoJobs", "link": "https://www.infojobs.com.br/vaga/3"}]},
    {"title": "Educador(a) Social", "company_name": "ONG C", "location": "São Paulo, SP",
     "detected_extensions": {"salary": "R$ 2.800 por mês"},
     "apply_options": [{"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/1"}]},
    {"title": "Educador Social", "company_name": "Empresa D", "location": "Guarulhos, SP",
     "detected_extensions": {}, "apply_options": [{"title": "Site da empresa", "link": "https://empresa-d.com.br/vagas/9"}]},
]}


class SerpApi:
    def __init__(self):
        self.pedidos: list[httpx.Request] = []

    def responder(self, pedido: httpx.Request) -> httpx.Response:
        if pedido.url.host == "serpapi.com":
            self.pedidos.append(pedido)
            return httpx.Response(200, json=RESPOSTA)
        return cliente_cnpj()._transport.handle_request(pedido)

    def cliente(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.responder))


def test_conector_do_google_vagas():
    serp = SerpApi()
    with serp.cliente() as c:
        vagas = buscar_vagas_google(c, "chave", "Educador social", "São Paulo", "SP")
    assert [v.empresa for v in vagas] == ["Instituto A", "Associação B", "ONG C", "Empresa D"]
    assert vagas[0].salario == "R$ 2.500–R$ 3.000 por mês" and vagas[1].salario is None
    assert vagas[0].links[1] == ("Catho", "https://www.catho.com.br/vagas/1")
    params = serp.pedidos[0].url.params
    assert params["engine"] == "google_jobs" and params["q"] == "Educador social São Paulo SP" and params["gl"] == "br"


@pytest.fixture
def ambiente(tmp_path):
    serp, navegador, cofre = SerpApi(), NavegadorFalso(), CofreEmMemoria(serpapi="serp-123")
    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir_navegador_falso(navegador), cliente_http=serp.cliente,
                               cofre=cofre, hoje=lambda: date(2026, 9, 25), intervalo_busca_s=0)
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        yield api, app, navegador, cofre


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _cargo(api) -> str:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC"}), 201)
    projeto = _ok(api.post("/api/projetos", json={"organizacao_id": org["id"], "nome": "P", "teto_centavos": 900_000,
                                                   "duracao_meses": 12}), 201)
    pessoal = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "RH", "tipo": "mao_de_obra"}), 201)
    return _ok(api.post(f"/api/orcamentos/{pessoal['id']}/cargos", json={
        "nome": "Educador social", "regime": "recibo", "horas_planejadas_centesimos": 8000, "mes_fim": 12}), 201)["id"]


def test_google_vagas_captura_as_que_podem_e_lista_as_outras(ambiente):
    api, app, navegador, _ = ambiente
    cargo = _cargo(api)
    tarefa = _ok(api.post(f"/api/cargos/{cargo}/vagas-google", json={"cidade": "São Paulo", "uf": "SP"}), 202)
    app.state.servico.fila.processar_proxima("principal")
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida", feita
    vagas = {v["empresa"]: v for v in feita["resultado"]["vagas"]}
    # Catho e InfoJobs permitem programas nas páginas de vaga: capturadas (a com salário primeiro)
    assert vagas["Instituto A"]["situacao"] == "capturada" and vagas["Instituto A"]["url"] == "https://www.catho.com.br/vagas/1"
    assert vagas["Associação B"]["situacao"] == "capturada"
    assert navegador.pedidas == ["https://www.catho.com.br/vagas/1", "https://www.infojobs.com.br/vaga/3"]
    # LinkedIn na janela; site da empresa só listado
    assert vagas["ONG C"]["situacao"] == "janela" and vagas["ONG C"]["plataforma"] == "LinkedIn"
    assert vagas["Empresa D"]["situacao"] == "outro_site"
    assert feita["resultado"]["capturadas"] == 2 and "serp-123" not in json.dumps(feita)

    # o salário que vale é o da página da vaga, não o do Google
    observacoes = {o["url"]: o for o in _ok(api.get(f"/api/cargos/{cargo}/observacoes"))}
    assert observacoes["https://www.catho.com.br/vagas/1"]["salario_min_centavos"] == VAGAS["https://www.catho.com.br/vagas/1"][1]
    assert any("Google Vagas" in a for a in observacoes["https://www.catho.com.br/vagas/1"]["avisos"])

    # buscar de novo não captura de novo o que já tem
    tarefa = _ok(api.post(f"/api/cargos/{cargo}/vagas-google", json={}), 202)
    app.state.servico.fila.processar_proxima("principal")
    vagas = {v["empresa"]: v for v in _ok(api.get(f"/api/tarefas/{tarefa['id']}"))["resultado"]["vagas"]}
    assert vagas["Instituto A"]["situacao"] == "ja_tinha" and len(navegador.pedidas) == 2


def test_sem_chave_nao_busca(ambiente):
    api, _, _, cofre = ambiente
    cofre.apagar("serpapi")
    assert api.post(f"/api/cargos/{_cargo(api)}/vagas-google", json={}).status_code == 409
