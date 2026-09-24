"""Etapa 9.4: captura assistida, PDF enviado, comprovante da Receita, catálogos, pares e regras editáveis."""

import threading
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from apoio_api import (
    LOJAS,
    PAPEL,
    NavegadorFalso,
    NavegadorVisivelFalso,
    PaginaFalsa,
    abrir_navegador_falso,
    cliente_cnpj,
    pdf_com_texto,
)
from orca.api import Configuracao, contexto_padrao, criar_app
from orca.dominio import formatar_cnpj

HOJE = date(2026, 9, 24)


@pytest.fixture
def janela():
    return NavegadorVisivelFalso()


@pytest.fixture
def app(tmp_path, janela):
    @contextmanager
    def abrir_janela():
        yield janela

    config = Configuracao(str(tmp_path / "dados"), "Leonardo")
    contexto = contexto_padrao(config, abrir_navegador=abrir_navegador_falso(NavegadorFalso()),
                               abrir_navegador_visivel=abrir_janela, cliente_http=cliente_cnpj, hoje=lambda: HOJE)
    return criar_app(config, contexto, iniciar_trabalhador=False)


@pytest.fixture
def api(app):
    with TestClient(app, base_url="http://localhost:8765", headers={"X-Orca": "1"}) as cliente:
        yield cliente


def _ok(resposta, status=200):
    assert resposta.status_code == status, resposta.text
    return resposta.json()


def _projeto(api) -> dict:
    org = _ok(api.post("/api/organizacoes", json={"nome": "OSC Exemplo"}), 201)
    projeto = _ok(api.post("/api/projetos", json={
        "organizacao_id": org["id"], "nome": "Projeto Exemplo", "teto_centavos": 1_000_000, "duracao_meses": 12}), 201)
    materiais = _ok(api.post(f"/api/projetos/{projeto['id']}/orcamentos", json={"nome": "Materiais", "tipo": "materiais"}), 201)
    lote = _ok(api.post(f"/api/orcamentos/{materiais['id']}/lotes", json={"nome": "Escritório"}), 201)
    papel = _ok(api.post(f"/api/lotes/{lote['id']}/itens", json={
        "descricao": "Papel sulfite A4 75g 500 folhas", "categoria": "papel", "marca": "Chamex", "ean": PAPEL,
        "qtd_planejada": 10, "mes_fim": 12}), 201)
    return {"org": org["id"], "projeto": projeto["id"], "orcamento": materiais["id"], "papel": papel["id"]}


def _na_pista_assistida(app):
    """Roda a pista da janela visível em outra thread, como o programa faz."""
    fila = app.state.servico.fila
    trabalhador = threading.Thread(target=fila.processar_proxima, args=("assistida",))
    trabalhador.start()
    return trabalhador


def _esperar_estado(api, tarefa_id: str, estado: str) -> dict:
    limite = time.monotonic() + 5
    while time.monotonic() < limite:
        tarefa = _ok(api.get(f"/api/tarefas/{tarefa_id}"))
        if tarefa["estado"] == estado:
            return tarefa
        time.sleep(0.02)
    raise AssertionError(f"a tarefa não chegou a “{estado}”: {tarefa}")


# --- Captura assistida (D-67) ------------------------------------------------------------------------------


def test_captura_assistida_espera_a_pessoa_e_captura_quando_ela_manda(app, api, janela):
    ids = _projeto(api)
    url = f"https://www.kalunga.com.br/p/{PAPEL}"
    tarefa = _ok(api.post(f"/api/itens/{ids['papel']}/captura-assistida", json={"url": url}), 202)
    assert app.state.servico.fila.processar_proxima("principal") is None  # não é da pista sem janela
    assert api.post(f"/api/tarefas/{tarefa['id']}/capturar-agora").status_code == 409  # ainda não está esperando
    trabalhador = _na_pista_assistida(app)
    esperando = _esperar_estado(api, tarefa["id"], "esperando_usuario")
    assert "Capturar agora" in esperando["mensagem"] and janela.abertas == [url]
    time.sleep(0.05)
    assert trabalhador.is_alive()  # sem o clique, continua esperando
    _ok(api.post(f"/api/tarefas/{tarefa['id']}/capturar-agora"))
    trabalhador.join(timeout=5)
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida", feita
    assert feita["resultado"]["preco_centavos"] == LOJAS["kalunga.com.br"][1]
    observacao = _ok(api.get(f"/api/itens/{ids['papel']}/observacoes"))[0]
    assert observacao["metodo"] == "C4"


def test_cancelar_captura_assistida(app, api, janela):
    ids = _projeto(api)
    tarefa = _ok(api.post(f"/api/itens/{ids['papel']}/captura-assistida",
                          json={"url": f"https://www.kalunga.com.br/p/{PAPEL}"}), 202)
    trabalhador = _na_pista_assistida(app)
    _esperar_estado(api, tarefa["id"], "esperando_usuario")
    _ok(api.post(f"/api/tarefas/{tarefa['id']}/cancelar"))
    trabalhador.join(timeout=5)
    assert _ok(api.get(f"/api/tarefas/{tarefa['id']}"))["estado"] == "cancelada"
    assert _ok(api.get(f"/api/itens/{ids['papel']}/observacoes")) == []
    assert api.post(f"/api/tarefas/{tarefa['id']}/cancelar").status_code == 400  # já terminou

    pendente = _ok(api.post(f"/api/itens/{ids['papel']}/captura-assistida",
                            json={"url": f"https://www.gimba.com.br/p/{PAPEL}"}), 202)
    assert _ok(api.post(f"/api/tarefas/{pendente['id']}/cancelar"))["estado"] == "cancelada"


def test_comprovante_da_receita_salvo_quando_aparece(app, api, janela):
    ids = _projeto(api)
    cnpj = LOJAS["kalunga.com.br"][0]
    tarefa = _ok(api.post("/api/comprovantes", json={"cnpj": formatar_cnpj(cnpj), "projeto_id": ids["projeto"]}), 202)
    repetida = _ok(api.post("/api/comprovantes", json={"cnpj": cnpj}), 202)
    assert repetida["id"] == tarefa["id"]  # o mesmo CNPJ não abre duas janelas
    trabalhador = _na_pista_assistida(app)
    _esperar_estado(api, tarefa["id"], "esperando_usuario")
    assert "Cnpjreva_Solicitacao" in janela.abertas[0] or "solicitacao" in janela.abertas[0].lower()
    # a pessoa resolve a verificação e clica em Consultar: a página do comprovante aparece
    janela.pagina = PaginaFalsa("https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpjreva_Comprovante.asp",
                                f"NÚMERO DE INSCRIÇÃO {formatar_cnpj(cnpj)} SITUAÇÃO CADASTRAL ATIVA")
    trabalhador.join(timeout=5)
    feita = _ok(api.get(f"/api/tarefas/{tarefa['id']}"))
    assert feita["estado"] == "concluida" and feita["resultado"]["cnpj"] == cnpj


# --- PDF salvo pelo usuário (D-67) ------------------------------------------------------------------------


def test_pdf_enviado_vira_observacao_com_aviso(api):
    ids = _projeto(api)
    url = "https://mercado.carrefour.com.br/papel-sulfite-chamex/p"
    pdf = pdf_com_texto([f"23/09/2026 14:00  {url}", "Papel Sulfite A4 75g 500 folhas Chamex",
                         "R$ 28,90", "CNPJ 45.543.915/0736-50"])
    resposta = _ok(api.post(f"/api/itens/{ids['papel']}/pdf", files={"arquivo": ("pagina.pdf", pdf, "application/pdf")},
                            data={"url": url, "preco_centavos": "2890",
                                  "titulo": "Papel Sulfite A4 75g 500 folhas Chamex"}), 201)
    assert resposta["preco_centavos"] == 2890 and resposta["correspondencia"] in ("verde", "amarelo")
    assert any("PDF salvo e enviado pelo usuário" in a for a in resposta["avisos"])
    assert not any("não aparece" in a for a in resposta["avisos"])  # endereço, nome e preço estão no PDF
    observacao = _ok(api.get(f"/api/itens/{ids['papel']}/observacoes"))[0]
    assert observacao["metodo"] == "C4" and observacao["cnpj_vendedor"] == "45543915073650"
    assert api.get(f"/api/evidencias/{observacao['evidencia_id']}/pdf").content == pdf
    assert api.get(f"/api/evidencias/{observacao['evidencia_id']}/png").status_code == 404

    sem_endereco = _ok(api.post(f"/api/itens/{ids['papel']}/pdf",
                                files={"arquivo": ("p.pdf", pdf_com_texto(["R$ 28,90"]), "application/pdf")},
                                data={"url": "https://www.extramercado.com.br/p/1", "preco_centavos": "2890"}), 201)
    assert any("não aparece no PDF" in a for a in sem_endereco["avisos"])

    invalido = api.post(f"/api/itens/{ids['papel']}/pdf", files={"arquivo": ("x.pdf", b"nada", "application/pdf")},
                        data={"url": url})
    assert invalido.status_code == 400 and "PDF válido" in invalido.json()["erro"]


# --- Catálogos, vocabulário e pares (D-64 a D-66) ---------------------------------------------------------


def test_vocabulario_editado_com_trava_contra_verde_errado(api):
    ids = _projeto(api)
    rota = f"/api/organizacoes/{ids['org']}/catalogos/atributos"
    atual = _ok(api.get(rota))
    assert atual["versao"] == 0 and atual["mudancas"] == {} and "papel" in atual["vigente"]["categorias"]

    # um sinônimo novo: passa no teste e só a diferença fica gravada
    editado = atual["vigente"]
    editado["vocabulario"]["tipo"]["forma_do_cafe"]["moido"].append("moidinho")
    conferido = _ok(api.post(rota + "/conferir", json={"conteudo": editado}))
    assert conferido["aprovada"] and conferido["novos_falsos_verdes"] == []
    salvo = _ok(api.put(rota, json={"conteudo": editado, "resumo": "moidinho"}))
    assert salvo["versao"] == 1
    assert salvo["mudancas"] == {"vocabulario": {"tipo": {"forma_do_cafe": {
        "moido": ["moido", "moida", "torrado e moido", "moidinho"]}}}}
    assert _ok(api.put(rota, json={"conteudo": editado}))["versao"] == 1  # nada mudou: sem versão nova
    assert _ok(api.get(rota))["historico"][0]["resumo"] == "moidinho"

    # a OSC ensinou que moído e em grãos são produtos diferentes; juntar os dois criaria um 🟢 errado
    _ok(api.post(f"/api/organizacoes/{ids['org']}/pares", json={
        "titulo_a": "Cafe Pilao moido 500g", "titulo_b": "Cafe Pilao em graos 500g", "rotulo": "diferente",
        "categoria": "alimento", "marca_a": "Pilao", "marca_b": "Pilao"}), 201)
    ruim = _ok(api.get(rota))["vigente"]
    grupo = ruim["vocabulario"]["tipo"]["forma_do_cafe"]
    grupo["moido"] += grupo.pop("graos")
    conferido = _ok(api.post(rota + "/conferir", json={"conteudo": ruim}))
    assert not conferido["aprovada"] and len(conferido["novos_falsos_verdes"]) == 1
    assert any(p["antes"] == "vermelho" and p["depois"] == "verde" for p in conferido["pares_que_mudaram"])
    recusada = api.put(rota, json={"conteudo": ruim})
    assert recusada.status_code == 400 and "🟢" in recusada.json()["erro"]
    assert _ok(api.get(rota))["versao"] == 1

    # erros de formato viram mensagem
    confuso = _ok(api.get(rota))["vigente"]
    confuso["vocabulario"]["tipo"]["forma_do_cafe"]["soluvel"].append("moida")
    assert "mais de um valor" in api.put(rota, json={"conteudo": confuso}).json()["erro"]
    desconhecido = _ok(api.get(rota))["vigente"]
    desconhecido["categorias"]["brinquedo"] = ["cor", "tamanho_inventado"]
    assert "desconhecido" in api.put(rota, json={"conteudo": desconhecido}).json()["erro"]


def test_categoria_nova_da_osc_aparece_no_cadastro(api):
    ids = _projeto(api)
    rota = f"/api/organizacoes/{ids['org']}/catalogos/atributos"
    editado = _ok(api.get(rota))["vigente"]
    editado["categorias"]["brinquedo"] = ["cor", "unidades_por_embalagem"]
    _ok(api.put(rota, json={"conteudo": editado}))
    categorias = _ok(api.get(f"/api/catalogos/categorias?organizacao_id={ids['org']}"))
    assert {"id": "brinquedo", "atributos": ["marca", "modelo", "apresentacao", "cor", "unidades_por_embalagem"]} \
        in categorias
    assert not any(c["id"] == "brinquedo" for c in _ok(api.get("/api/catalogos/categorias")))  # só desta OSC


def test_lojas_da_osc(api):
    ids = _projeto(api)
    rota = f"/api/organizacoes/{ids['org']}/catalogos/lojas"
    atual = _ok(api.get(rota))
    lojas = atual["vigente"]
    lojas["lojas"].append({"id": "papelaria_bairro", "nome": "Papelaria do Bairro", "dominio": "www.papelariabairro.com.br",
                           "coleta": "C4"})
    next(l for l in lojas["lojas"] if l["id"] == "kalunga")["observacoes"] = "entrega só na capital"
    salvo = _ok(api.put(rota, json={"conteudo": lojas}))
    assert {l["id"] for l in salvo["mudancas"]["lojas"]} == {"kalunga", "papelaria_bairro"}
    catalogo = _ok(api.get(f"/api/catalogos/lojas?organizacao_id={ids['org']}"))
    assert any(l["id"] == "papelaria_bairro" and l["coleta"] == "C4" for l in catalogo)
    lojas["lojas"][-1]["coleta"] = "C9"
    assert "coleta deve ser" in api.put(rota, json={"conteudo": lojas}).json()["erro"]


def test_pares_nascem_das_decisoes_e_do_codigo_de_barras(app, api):
    ids = _projeto(api)
    for dominio in ("kalunga.com.br", "gimba.com.br"):
        _ok(api.post(f"/api/itens/{ids['papel']}/coletas", json={"url": f"https://www.{dominio}/p/{PAPEL}"}), 202)
    app.state.servico.fila.processar_todas()
    rota = f"/api/organizacoes/{ids['org']}/pares"
    pares = _ok(api.get(rota))
    assert [p["origem"] for p in pares["pares"]] == ["ean"] and pares["pares"][0]["rotulo"] == "mesmo"
    assert pares["resumo_sistema"]["total"] == 364 and pares["resumo_sistema"]["falsos_verdes"] == 0

    observacao = _ok(api.get(f"/api/itens/{ids['papel']}/observacoes"))[0]
    decisao = {"item_id": ids["papel"], "observacao_id": observacao["id"]}
    _ok(api.post("/api/correspondencias", json={**decisao, "status": "vermelho", "justificativa": "é outra gramatura"}), 201)
    da_decisao = [p for p in _ok(api.get(rota))["pares"] if p["origem"] == "decisao"]
    assert len(da_decisao) == 1 and da_decisao[0]["rotulo"] == "diferente"
    _ok(api.post("/api/correspondencias", json={**decisao, "status": "verde", "justificativa": "conferi: é o mesmo"}), 201)
    da_decisao = [p for p in _ok(api.get(rota))["pares"] if p["origem"] == "decisao"]
    assert len(da_decisao) == 1 and da_decisao[0]["rotulo"] == "mesmo"  # o par antigo saiu

    manual = _ok(api.post(rota, json={"titulo_a": "Detergente Ype neutro 500ml", "titulo_b": "Detergente Ype limao 500ml",
                                      "rotulo": "diferente", "categoria": "limpeza", "marca_a": "Ype", "marca_b": "Ype"}), 201)
    assert manual["origem"] == "usuario" and manual["status_atual"] in ("vermelho", "amarelo")
    _ok(api.post(f"/api/pares/{manual['id']}/retirar"))
    assert all(p["id"] != manual["id"] for p in _ok(api.get(rota))["pares"])

    ean = next(p for p in _ok(api.get(rota))["pares"] if p["origem"] == "ean")
    _ok(api.post(f"/api/pares/{ean['id']}/retirar"))
    _ok(api.post(f"/api/itens/{ids['papel']}/coletas", json={"url": f"https://www.lepok.com.br/p/{PAPEL}"}), 202)
    app.state.servico.fila.processar_todas()
    pares_ean = [p for p in _ok(api.get(rota))["pares"] if p["origem"] == "ean"]
    assert len(pares_ean) == 1  # o retirado não volta; o novo (gimba × lepok) entra


# --- Regras editáveis -------------------------------------------------------------------------------------


def test_regras_do_projeto_e_do_orcamento(api):
    ids = _projeto(api)
    rota = f"/api/projetos/{ids['projeto']}/regras"
    inicio = _ok(api.get(rota))
    assert inicio["proprias"] == {} and inicio["regras"]["calculo"]["base_preco_final"] == "B"

    _ok(api.put(rota, json={"conteudo": {"calculo": {"base_preco_final": "A"}, "fontes": {"validade_dias": 90}}}))
    regras = _ok(api.get(rota))
    assert regras["regras"]["calculo"]["base_preco_final"] == "A" and regras["regras"]["fontes"]["validade_dias"] == 90
    assert regras["proprias"]["fontes"] == {"validade_dias": 90}
    assert [c["nivel"] for c in regras["cadeia"]] == ["sistema", "projeto"] and regras["cadeia"][1]["versao"] == 1
    _ok(api.put(rota, json={"conteudo": {"calculo": {"base_preco_final": "A"}}}))
    assert _ok(api.get(rota))["cadeia"][1]["versao"] == 2  # versão nova; a anterior fica no banco

    _ok(api.put(f"/api/orcamentos/{ids['orcamento']}/regras", json={"conteudo": {"calculo": {"base_preco_final": "B"}}}))
    orcamento = _ok(api.get(rota))["orcamentos"][0]
    assert orcamento["proprias"] == {"calculo": {"base_preco_final": "B"}}
    assert orcamento["impressao"] != _ok(api.get(rota))["impressao"]

    invalida = api.put(rota, json={"conteudo": {"calculo": {"base_preco_final": "C"}}})
    assert invalida.status_code == 400
    trava = api.put(rota, json={"conteudo": {"automacao": {"promover_amarelo_para_verde": "automatico"}}})
    assert trava.status_code == 400
    _ok(api.put(f"/api/orcamentos/{ids['orcamento']}/regras", json={"conteudo": {}}))
    assert _ok(api.get(rota))["orcamentos"][0]["proprias"] == {}


def test_comprovante_emitido_no_navegador_e_enviado_em_pdf(app, api):
    """A Receita recusa a verificação na janela do sistema (piloto, 24/09/2026): a pessoa emite e envia o PDF."""
    ids = _projeto(api)
    _ok(api.post(f"/api/itens/{ids['papel']}/coletas", json={"url": f"https://www.kalunga.com.br/p/{PAPEL}"}), 202)
    app.state.servico.fila.processar_todas()
    kalunga = LOJAS["kalunga.com.br"][0]
    rota = f"/api/projetos/{ids['projeto']}/comprovantes-pendentes"
    pendentes = _ok(api.get(rota))
    assert kalunga in pendentes["pendentes"] and pendentes["paginas"][kalunga].endswith(f"cnpj={kalunga}")

    def enviar(linhas, cnpj=kalunga):
        return api.post("/api/comprovantes/pdf", data={"cnpj": cnpj},
                        files={"arquivo": ("comprovante.pdf", pdf_com_texto(linhas), "application/pdf")})

    comprovante = ["https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpjreva_Comprovante.asp",
                   "COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL", f"NUMERO DE INSCRICAO {formatar_cnpj(kalunga)}",
                   "SITUACAO CADASTRAL ATIVA", "Emitido no dia 24/09/2026 as 10:15:30 (data e hora de Brasilia)."]
    outro = enviar(comprovante, cnpj=LOJAS["gimba.com.br"][0])
    assert outro.status_code == 400 and "não é do CNPJ" in outro.json()["erro"]
    assert "não é o “Comprovante" in enviar(["Nota fiscal", formatar_cnpj(kalunga)]).json()["erro"]
    recebido = _ok(enviar(comprovante), 201)
    emitido = datetime.fromisoformat(recebido["emitido_em"])
    assert emitido == datetime(2026, 9, 24, 13, 15, 30, tzinfo=UTC) and recebido["avisos"] == []
    assert kalunga not in _ok(api.get(rota))["pendentes"]
    sem_data = _ok(enviar(comprovante[:4]), 201)
    assert any("data de emissão não aparece" in a for a in sem_data["avisos"])


# --- Vagas pela janela (Fase 2, etapa 11; D-69) ---------------------------------------------------------


def _cargo(api, ids) -> str:
    pessoal = _ok(api.post(f"/api/projetos/{ids['projeto']}/orcamentos", json={"nome": "RH", "tipo": "mao_de_obra"}), 201)
    return _ok(api.post(f"/api/orcamentos/{pessoal['id']}/cargos", json={
        "nome": "Educador Social", "regime": "recibo", "horas_planejadas_centesimos": 8000, "mes_fim": 12}), 201)["id"]


def test_busca_de_vagas_abre_a_janela_na_plataforma(app, api, janela):
    ids = _projeto(api)
    cargo = _cargo(api, ids)
    assert len(_ok(api.get("/api/plataformas-de-vagas"))) == 5
    tarefas = _ok(api.post(f"/api/cargos/{cargo}/busca-de-vagas",
                           json={"plataformas": ["catho", "indeed"], "cidade": "São Paulo", "uf": "SP"}), 202)["tarefas"]
    assert [t["parametros"]["url"] for t in tarefas] == [
        "https://www.catho.com.br/vagas/educador-social/sao-paulo-sp/", "https://br.indeed.com/jobs?q=Educador+Social&l=S%C3%A3o+Paulo"]
    trabalhador = _na_pista_assistida(app)
    _esperar_estado(api, tarefas[0]["id"], "esperando_usuario")
    janela.pagina = PaginaFalsa("https://www.catho.com.br/vagas/1")  # a pessoa clicou numa vaga da lista
    _ok(api.post(f"/api/tarefas/{tarefas[0]['id']}/capturar-agora"))
    trabalhador.join(timeout=5)
    feita = _ok(api.get(f"/api/tarefas/{tarefas[0]['id']}"))
    assert feita["estado"] == "concluida" and feita["resultado"]["salario_min_centavos"] == 250_000
    vaga = _ok(api.get(f"/api/cargos/{cargo}/observacoes"))[0]
    assert vaga["url"] == "https://www.catho.com.br/vagas/1" and vaga["metodo"] == "C4"
    _ok(api.post(f"/api/tarefas/{tarefas[1]['id']}/cancelar"))


def test_link_de_vaga_do_indeed_vai_para_a_janela(api):
    ids = _projeto(api)
    cargo = _cargo(api, ids)
    indeed = _ok(api.post(f"/api/cargos/{cargo}/coletas", json={"url": "https://br.indeed.com/viewjob?jk=abc"}), 202)
    catho = _ok(api.post(f"/api/cargos/{cargo}/coletas", json={"url": "https://www.catho.com.br/vagas/2"}), 202)
    assert (indeed["tipo"], catho["tipo"]) == ("captura_assistida", "coletar_cargo")
