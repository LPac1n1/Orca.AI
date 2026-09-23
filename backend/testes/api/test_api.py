"""API local de ponta a ponta: cadastro, coleta pela fila, CNPJ, revisão, decisões, teto e exportação."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from apoio_api import LEITE, LOJAS, PAPEL, VAGAS, NavegadorFalso, abrir_navegador_falso, cliente_cnpj
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.documentos import Renderizador

HOJE = date(2026, 9, 24)


@pytest.fixture
def navegador():
    return NavegadorFalso()


@pytest.fixture
def app(tmp_path, navegador):
    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir_navegador_falso(navegador),
                               cliente_http=cliente_cnpj, hoje=lambda: HOJE)
    return criar_app(config, contexto, iniciar_trabalhador=False)


@pytest.fixture
def api(app):
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as cliente:
        yield cliente


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _processar(app):
    return app.state.servico.fila.processar_todas()


def _projeto(api) -> dict:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC Exemplo"}), 201)
    projeto = _ok(api.post("/api/projetos", json={
        "organizacao_id": org["id"], "nome": "Projeto Exemplo", "teto_centavos": 1_611_720, "duracao_meses": 12,
        "data_entrega": "2026-12-15"}), 201)
    materiais = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "Material de consumo", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{materiais['id']}/lotes", json={"nome": "Copa e escritório"}), 201)
    papel = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Papel sulfite A4 75g 500 folhas", "categoria": "papel", "marca": "Chamex", "ean": PAPEL,
        "qtd_planejada": 10, "mes_fim": 12}), 201)
    leite = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Leite condensado 395g", "categoria": "alimento", "marca": "Moça", "ean": LEITE,
        "qtd_planejada": 5, "mes_fim": 12}), 201)
    pessoal = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "Recursos humanos", "tipo": "mao_de_obra"}), 201)
    cargo = _ok(api.post(f"/api/orcamentos/{pessoal['id']}/cargos", json={
        "nome": "Educador social", "regime": "recibo", "horas_planejadas_centesimos": 8000, "mes_fim": 12}), 201)
    return {"projeto": projeto["id"], "lote": lote["id"], "papel": papel["id"], "leite": leite["id"], "cargo": cargo["id"]}


def test_seguranca_local(app):
    with TestClient(app, base_url="http://localhost:8765") as cliente:
        assert cliente.get("/api/situacao").status_code == 200
        assert cliente.post("/api/organizacoes", json={"nome": "X"}).status_code == 403  # sem X-Orca
    with TestClient(app, base_url="http://site-malicioso.com", headers={"X-Orca": "1"}) as cliente:
        assert cliente.get("/api/situacao").status_code == 400  # DNS rebinding


def test_situacao_e_catalogos(api):
    situacao = _ok(api.get("/api/situacao"))
    assert situacao["usuario"] == "Leonardo" and situacao["hoje"] == "2026-09-24"
    assert any(j["id"] == "regra_geral" and j["divisor"] == 220 for j in _ok(api.get("/api/catalogos/jornadas")))
    assert any(c["id"] == "papel" for c in _ok(api.get("/api/catalogos/categorias")))
    assert any(l["id"] == "kalunga" for l in _ok(api.get("/api/catalogos/lojas")))


def test_fluxo_completo_pela_api(app, api, navegador):
    ids = _projeto(api)
    for dominio in LOJAS:
        for item, ean in ((ids["papel"], PAPEL), (ids["leite"], LEITE)):
            tarefa = _ok(api.post(f"/api/itens/{item}/coletas", json={"url": f"https://www.{dominio}/p/{ean}"}), 202)
            assert tarefa["estado"] == "pendente"
    for url in VAGAS:
        _ok(api.post(f"/api/cargos/{ids['cargo']}/coletas", json={"url": url}), 202)
    feitas = _processar(app)
    assert len(feitas) == 13 and len(navegador.pedidas) == 13
    tarefas = _ok(api.get(f"/api/tarefas?projeto_id={ids['projeto']}"))
    assert {t["estado"] for t in tarefas} == {"concluida"}
    coleta = next(t for t in tarefas if t["tipo"] == "coletar_item")
    assert coleta["resultado"]["correspondencia"] == "verde" and coleta["mensagem"].startswith("preço R$")

    observacoes = _ok(api.get(f"/api/itens/{ids['papel']}/observacoes"))
    assert len(observacoes) == 5 and all(o["correspondencia"]["origem"] == "ean" for o in observacoes)
    pdf = api.get(f"/api/evidencias/{observacoes[0]['evidencia_id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")

    # CNPJs: sem consulta, nenhuma loja entra no trio
    assert _ok(api.get(f"/api/projetos/{ids['projeto']}/revisao"))["orcamentos"][0]["lotes"][0]["situacao"] == "sem_trio"
    _ok(api.post(f"/api/projetos/{ids['projeto']}/consultar-cnpjs"), 202)
    _processar(app)
    painel = _ok(api.get(f"/api/projetos/{ids['projeto']}/painel"))
    assert painel["cnpjs_sem_consulta"] == [LOJAS["loja-x.com.br"][0]]

    revisao = _ok(api.get(f"/api/projetos/{ids['projeto']}/revisao"))
    lote = revisao["orcamentos"][0]["lotes"][0]
    assert lote["situacao"] == "ok"
    escolhida = next(l for l in lote["lojas"] if l["posicao"] == 1)
    assert escolhida["cnpj"] == LOJAS["gimba.com.br"][0]
    leite = next(i for i in lote["itens"] if i["id"] == ids["leite"])
    assert leite["status"] == "vermelho" and leite["dentro_da_media"] is False
    assert next(l for l in lote["lojas"] if l["cnpj"] == LOJAS["loja-x.com.br"][0])["situacao"] == "descartada"
    cargo = revisao["orcamentos"][1]["cargos"][0]
    assert cargo["calculo"]["valor_mensal_centavos"] == 94_560 and sum(v["escolhida"] for v in cargo["vagas"]) == 3

    simulacao = _ok(api.get(f"/api/lotes/{ids['lote']}/simular-troca-de-loja"))
    assert simulacao["sucesso"] and simulacao["tentativas"][0]["loja"] == escolhida["id"]
    _ok(api.post(f"/api/lotes/{ids['lote']}/retirar-loja",
                 json={"loja": escolhida["id"], "justificativa": "leite acima da média (Saída 2)"}), 201)

    _ok(api.post(f"/api/projetos/{ids['projeto']}/fechar-teto"), 202)
    _processar(app)
    otimizacao = _ok(api.get(f"/api/projetos/{ids['projeto']}/otimizacao"))
    assert otimizacao["ultima"]["vigente"] and otimizacao["ultima"]["total_centavos"] == 1_611_720
    painel = _ok(api.get(f"/api/projetos/{ids['projeto']}/painel"))
    assert painel["diferenca_centavos"] == 0 and painel["contagem"]["vermelho"] == 0

    historico = _ok(api.get(f"/api/projetos/{ids['projeto']}/historico"))
    assert any(e["entidade"] == "decisao" for e in historico) and all(e["autor"] for e in historico)
    regras = _ok(api.get(f"/api/projetos/{ids['projeto']}/regras"))
    assert regras["regras"]["fontes"]["validade_dias"] == 180 and regras["origem"]
    assert _ok(api.get(f"/api/projetos/{ids['projeto']}/comprovantes-pendentes"))["pendentes"]


def test_item_pesquisado_so_muda_por_troca_de_produto(app, api):
    ids = _projeto(api)
    _ok(api.patch(f"/api/itens/{ids['papel']}", json={"qtd_planejada": 12}))
    _ok(api.patch(f"/api/itens/{ids['papel']}", json={"marca": "Report"}))  # ainda não pesquisado: pode
    _ok(api.post(f"/api/itens/{ids['papel']}/coletas", json={"url": f"https://www.kalunga.com.br/p/{PAPEL}"}), 202)
    _processar(app)
    resposta = api.patch(f"/api/itens/{ids['papel']}", json={"marca": "Chamex"})
    assert resposta.status_code == 409 and "trocar produto" in resposta.json()["erro"]
    novo = _ok(api.post(f"/api/itens/{ids['papel']}/trocar-produto",
                        json={"marca": "Chamex", "justificativa": "marca errada"}), 201)
    assert novo["substitui_item_id"] == ids["papel"] and novo["marca"] == "Chamex"
    projeto = _ok(api.get(f"/api/projetos/{ids['projeto']}"))
    assert [i["id"] for i in projeto["orcamentos"][0]["lotes"][0]["itens"]] == [ids["leite"], novo["id"]] or \
        {i["id"] for i in projeto["orcamentos"][0]["lotes"][0]["itens"]} == {ids["leite"], novo["id"]}


def test_erros_viram_mensagens(api):
    ids = _projeto(api)
    assert api.get("/api/projetos/nao-existe").status_code == 404
    resposta = api.post(f"/api/lotes/{ids['lote']}/retirar-loja", json={"loja": "x", "justificativa": " "})
    assert resposta.status_code == 400 and "justificativa" in resposta.json()["erro"]
    assert api.post(f"/api/itens/{ids['papel']}/coletas", json={"url": "ftp://x"}).status_code == 422
    _ok(api.post(f"/api/projetos/{ids['projeto']}/excluir"))
    assert api.get(f"/api/projetos/{ids['projeto']}").status_code == 404
    assert _ok(api.get("/api/projetos")) == []


def test_tarefa_com_erro_nao_para_a_fila(app, api, navegador):
    ids = _projeto(api)
    _ok(api.post(f"/api/itens/{ids['papel']}/coletas", json={"url": "https://www.desconhecida.com.br/p/1"}), 202)
    _ok(api.post(f"/api/itens/{ids['papel']}/coletas", json={"url": f"https://www.kalunga.com.br/p/{PAPEL}"}), 202)
    _processar(app)
    estados = sorted(t["estado"] for t in _ok(api.get("/api/tarefas")))
    assert estados == ["concluida", "falhou"]


@pytest.mark.navegador
def test_exportar_pelo_edge(tmp_path, navegador):
    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir_navegador_falso(navegador), cliente_http=cliente_cnpj,
                               hoje=lambda: HOJE, abrir_renderizador=lambda: Renderizador())
    app = criar_app(config, contexto, iniciar_trabalhador=False)
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as api:
        ids = _projeto(api)
        for dominio in LOJAS:
            for item, ean in ((ids["papel"], PAPEL), (ids["leite"], LEITE)):
                api.post(f"/api/itens/{item}/coletas", json={"url": f"https://www.{dominio}/p/{ean}"})
        for url in VAGAS:
            api.post(f"/api/cargos/{ids['cargo']}/coletas", json={"url": url})
        _processar(app)
        api.post(f"/api/projetos/{ids['projeto']}/consultar-cnpjs")  # depois das coletas: agora há CNPJs
        _processar(app)
        revisao = _ok(api.get(f"/api/projetos/{ids['projeto']}/revisao"))
        gimba = next(l for l in revisao["orcamentos"][0]["lotes"][0]["lojas"] if l["posicao"] == 1)
        api.post(f"/api/lotes/{ids['lote']}/retirar-loja", json={"loja": gimba["id"], "justificativa": "Saída 2"})
        api.post(f"/api/projetos/{ids['projeto']}/fechar-teto")
        api.post(f"/api/projetos/{ids['projeto']}/exportar")
        _processar(app)
        app.state.servico.fila.fechar_recursos()
        exportacoes = _ok(api.get(f"/api/projetos/{ids['projeto']}/exportacoes"))
        assert len(exportacoes) == 1 and exportacoes[0]["total_centavos"] == 1_611_720
        zip_ = api.get(f"/api/arquivos/{exportacoes[0]['arquivo']}")
        assert zip_.status_code == 200 and zip_.content[:2] == b"PK"
        assert api.get("/api/arquivos/orcamentos.sqlite").status_code == 404  # só a pasta de exportações
        assert api.get("/api/arquivos/../../segredo.txt").status_code == 404
