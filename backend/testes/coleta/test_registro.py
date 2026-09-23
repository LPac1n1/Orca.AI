"""Gravação da coleta no banco (T-10, T-12), com capturas sintéticas (sem navegador e sem rede)."""

import json
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import select

from apoio_coleta import EAN, USUARIO, NavegadorFalso, captura_falsa, pagina_produto
from orca.auditoria import ErroAuditoria, historico_do_projeto
from orca.banco import Alerta, Arquivo, Cargo, ConsultaCnpj, Evidencia, Fonte, Item, Observacao, Projeto, sessao_como
from orca.coleta import (
    cnpjs_do_projeto,
    coletar_cargo,
    coletar_item,
    comprovantes_pendentes,
    conferir_validade,
    ler_catalogo,
    refazer_pesquisa,
    registrar_captura,
    registrar_comprovante,
    registrar_observacao_item,
    ultima_consulta,
    validar_cnpj,
)

CATALOGO = ler_catalogo()
KALUNGA = "43283811000150"


def _coletar(fabrica, armazem, ids, captura, **kwargs):
    with sessao_como(fabrica, USUARIO) as s:
        r = coletar_item(s, armazem, NavegadorFalso(captura), s.get(Item, ids["item"]), captura.url_pedida, catalogo=CATALOGO, **kwargs)
        s.flush()
        return r.observacao.id, r.avisos


def test_coleta_completa_grava_evidencia_fonte_e_observacao(fabrica, armazem, ids):
    obs_id, avisos = _coletar(fabrica, armazem, ids, captura_falsa())
    assert avisos == ()
    with sessao_como(fabrica, USUARIO) as s:
        obs = s.get(Observacao, obs_id)
        assert (obs.preco_centavos, obs.preco_no_html, obs.encontrado) == (2529, True, True)
        assert (obs.ean, obs.marca, obs.cnpj_vendedor, obs.disponivel) == (EAN, "Chamex", KALUNGA, True)
        assert obs.titulo == "Papel Sulfite A4 Chamex 500 folhas" and obs.metodo == "C1" and obs.autor == USUARIO
        assert (obs.fonte.nome, obs.fonte.catalogo_id, obs.fonte.dominio) == ("Kalunga", "kalunga", "kalunga.com.br")
        ev = obs.evidencia
        assert ev.url == obs.url and ev.capturado_em == obs.coletado_em
        for arquivo, tipo in ((ev.pdf, "application/pdf"), (ev.png, "image/png"), (ev.html, "multipart/related")):
            assert arquivo.tipo_mime == tipo
            assert armazem.ler(arquivo.caminho)  # confere a impressão digital
        brutos = json.loads(obs.dados_brutos)
        assert brutos["cnpjs_na_pagina"] == [KALUNGA] and brutos["precos_visiveis"] == [2529]
        entidades = {e.entidade for e in historico_do_projeto(s, ids["projeto"])}
        assert "observacao" in entidades


def test_observacao_nao_pode_ser_alterada(fabrica, armazem, ids):
    obs_id, _ = _coletar(fabrica, armazem, ids, captura_falsa())
    with pytest.raises(ErroAuditoria, match="imutável"):
        with sessao_como(fabrica, USUARIO) as s:
            s.get(Observacao, obs_id).preco_centavos = 2000  # princípio 5


def test_preco_que_nao_aparece_na_pagina_nao_e_validado(fabrica, armazem, ids):
    captura = captura_falsa(texto="Papel Sulfite A4 Chamex por R$ 24,99 — CNPJ 43.283.811/0001-50")
    obs_id, avisos = _coletar(fabrica, armazem, ids, captura)
    assert any(a.startswith("Não foi possível validar automaticamente: o preço R$ 25,29") for a in avisos)
    with sessao_como(fabrica, USUARIO) as s:
        assert s.get(Observacao, obs_id).preco_no_html is False


def test_pagina_sem_preco_e_preco_informado_na_captura_assistida(fabrica, armazem, ids):
    sem_preco = captura_falsa(html="<html><body>Papel</body></html>", texto="Papel A4 R$ 26,90 CNPJ 43.283.811/0001-50")
    obs_id, avisos = _coletar(fabrica, armazem, ids, sem_preco)
    assert "preço não encontrado na página" in avisos[0]
    with sessao_como(fabrica, USUARIO) as s:
        obs = s.get(Observacao, obs_id)
        assert obs.encontrado is False and obs.preco_centavos is None and obs.preco_no_html is None
        # captura assistida: o usuário informa o preço que vê; o sistema confere na página
        assistida = captura_falsa(html="<html></html>", texto=sem_preco.texto_visivel, metodo="C4", semente="2")
        evidencia = registrar_captura(s, armazem, assistida)
        r = registrar_observacao_item(s, s.get(Item, ids["item"]), assistida, evidencia, preco_informado=2690, catalogo=CATALOGO)
        assert r.observacao.preco_centavos == 2690 and r.observacao.preco_no_html is True and r.observacao.metodo == "C4"
        assert json.loads(r.observacao.dados_brutos)["preco_informado"] == 2690


def test_varios_precos_avisam_qual_usar_na_loja(fabrica, armazem, ids):
    captura = captura_falsa(
        url="https://www.gimba.com.br/papel-a4",
        html=pagina_produto("24.53"),
        texto="R$ 24,53 no Pix · R$ 25,29 · Supricorp CNPJ 54.651.716/0011-50",
    )
    _, avisos = _coletar(fabrica, armazem, ids, captura)
    assert any("outros valores (R$ 25,29)" in a and "nesta loja: preco_normal" in a for a in avisos)


def test_marketplace_exige_cnpj_do_vendedor(fabrica, armazem, ids):
    """T-12: o CNPJ no rodapé do marketplace é da plataforma, não do vendedor."""
    pagina = "https://www.mercadolivre.com.br/papel-a4/p/MLB1"
    texto = "Papel A4 R$ 25,29 · Ebazar.com.br LTDA CNPJ 03.007.331/0001-41"
    obs_id, avisos = _coletar(fabrica, armazem, ids, captura_falsa(url=pagina, texto=texto))
    assert any("marketplace: informe o CNPJ do vendedor" in a for a in avisos)
    with sessao_como(fabrica, USUARIO) as s:
        assert s.get(Observacao, obs_id).cnpj_vendedor is None
    obs_id, avisos = _coletar(
        fabrica, armazem, ids, captura_falsa(url=pagina, texto=texto, semente="2"), cnpj_vendedor="54.651.716/0011-50"
    )
    assert not any("CNPJ" in a for a in avisos)
    with sessao_como(fabrica, USUARIO) as s:
        assert s.get(Observacao, obs_id).cnpj_vendedor == "54651716001150"


def test_dois_cnpjs_na_pagina_e_bloqueio(fabrica, armazem, ids):
    captura = captura_falsa(
        url="https://mercado.carrefour.com.br/papel",
        texto="R$ 25,29 · CNPJ 45.543.915/0736-50 · CNPJ 45.543.915/0846-95",
        bloqueio="o site respondeu com o código 403",
    )
    _, avisos = _coletar(fabrica, armazem, ids, captura)
    assert any("mostra 2 CNPJs" in a for a in avisos)
    assert any("possível bloqueio" in a and "captura assistida" in a for a in avisos)
    assert any("depende do CEP" in a for a in avisos)  # Carrefour: preço por região


def test_mesmos_arquivos_nao_duplicam_e_fonte_e_reaproveitada(fabrica, armazem, ids):
    captura = captura_falsa()
    with sessao_como(fabrica, USUARIO) as s:
        registrar_captura(s, armazem, captura)
        registrar_captura(s, armazem, captura)
        item = s.get(Item, ids["item"])
        coletar_item(s, armazem, NavegadorFalso(captura_falsa(semente="a")), item, captura.url_pedida, catalogo=CATALOGO)
        coletar_item(s, armazem, NavegadorFalso(captura_falsa(semente="b")), item, captura.url_pedida, catalogo=CATALOGO)
    with sessao_como(fabrica, USUARIO) as s:
        assert len(s.scalars(select(Evidencia)).all()) == 4
        assert len(s.scalars(select(Arquivo)).all()) == 9
        assert len(s.scalars(select(Fonte)).all()) == 1


# --- Vagas ------------------------------------------------------------------------------


def _pagina_vaga(salario):
    vaga = {"@type": "JobPosting", "title": "Educador Social", "baseSalary": salario,
            "jobLocation": {"address": {"addressLocality": "São Paulo", "addressRegion": "SP"}}}
    return f'<script type="application/ld+json">{json.dumps(vaga)}</script>'


def test_vaga_com_faixa_e_empresa_identificada(fabrica, armazem, ids):
    captura = captura_falsa(
        url="https://www.catho.com.br/vagas/educador-social/1",
        html=_pagina_vaga({"currency": "BRL", "value": {"minValue": "2500.00", "maxValue": 3000, "unitText": "MONTH"}}),
        texto="Educador Social · R$ 2.500,00 a R$ 3.000,00 · Instituto (CNPJ 43.283.811/0001-50)",
    )
    with sessao_como(fabrica, USUARIO) as s:
        r = coletar_cargo(s, armazem, NavegadorFalso(captura), s.get(Cargo, ids["cargo"]), captura.url_pedida)
        obs = r.observacao
        assert r.avisos == ()
        assert (obs.salario_min_centavos, obs.salario_max_centavos, obs.preco_no_html) == (250000, 300000, True)
        assert obs.cnpj_vendedor == KALUNGA and obs.alvo_tipo == "cargo" and obs.fonte.tipo == "empresa"


def test_vaga_sem_salario_e_sem_empresa(fabrica, armazem, ids):
    captura = captura_falsa(url="https://www.indeed.com.br/vaga/2", html=_pagina_vaga(None), texto="Educador Social · Confidencial")
    with sessao_como(fabrica, USUARIO) as s:
        r = coletar_cargo(s, armazem, NavegadorFalso(captura), s.get(Cargo, ids["cargo"]), captura.url_pedida)
        assert r.observacao.encontrado is False
        assert any("sem salário" in a for a in r.avisos) and any("empresa não identificada" in a for a in r.avisos)


# --- Validade (T-10) --------------------------------------------------------------------------


def _alertas(s, projeto_id):
    return s.scalars(select(Alerta).where(Alerta.projeto_id == projeto_id).order_by(Alerta.criado_em)).all()


def test_t10_validade_alerta_e_nova_pesquisa_mantem_a_antiga(fabrica, armazem, ids):
    """Coleta em 23/09/2026 vale até 21/03/2027, antes da entrega (30/06/2027)."""
    antiga_id, _ = _coletar(fabrica, armazem, ids, captura_falsa())
    with sessao_como(fabrica, USUARIO) as s:
        projeto = s.get(Projeto, ids["projeto"])
        novos = conferir_validade(s, projeto, hoje=date(2026, 9, 24))
        assert [(a.tipo, a.severidade, a.alvo_id) for a in novos] == [("pesquisa_vence_antes_da_entrega", "problema", antiga_id)]
        assert "21/03/2027" in novos[0].mensagem and "30/06/2027" in novos[0].mensagem
    with sessao_como(fabrica, USUARIO) as s:  # conferir de novo não repete o alerta
        assert conferir_validade(s, s.get(Projeto, ids["projeto"]), hoje=date(2026, 9, 25)) == []
    with sessao_como(fabrica, USUARIO) as s:  # passou da validade: vira "vencida"
        novos = conferir_validade(s, s.get(Projeto, ids["projeto"]), hoje=date(2027, 3, 22))
        assert [a.tipo for a in novos] == ["pesquisa_vencida"]
        assert "venceu em 21/03/2027" in novos[0].mensagem

    # Nova pesquisa com um clique: mesma página, mesmo item; a antiga fica no histórico
    nova = captura_falsa(momento=datetime(2027, 3, 22, 13, 0, tzinfo=UTC), texto="por R$ 26,49 CNPJ 43.283.811/0001-50",
                         html=pagina_produto("26.49"))
    navegador = NavegadorFalso(nova)
    with sessao_como(fabrica, "usuario:Leonardo") as s:
        r = refazer_pesquisa(s, armazem, navegador, s.get(Observacao, antiga_id), catalogo=CATALOGO)
        assert r.observacao.id != antiga_id and r.observacao.preco_centavos == 2649
        assert navegador.pedidas == [(nova.url_pedida, None)]
    with sessao_como(fabrica, USUARIO) as s:
        assert conferir_validade(s, s.get(Projeto, ids["projeto"]), hoje=date(2027, 3, 22)) == []
        alertas = _alertas(s, ids["projeto"])
        assert len(alertas) == 2 and all(a.resolvido_em is not None for a in alertas)
        antiga = s.get(Observacao, antiga_id)
        assert antiga.preco_centavos == 2529  # intacta
        precos = sorted(o.preco_centavos for o in s.scalars(select(Observacao)))
        assert precos == [2529, 2649]


# --- CNPJ e comprovantes ------------------------------------------------------------------------


def test_validar_cnpj_guarda_a_consulta(fabrica):
    resposta = {"razao_social": "KALUNGA S.A.", "situacao_cadastral": "Ativa", "uf": "SP", "municipio": "São Paulo",
                "QSA": [{"nome_socio": "FULANO"}]}
    cliente = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=resposta)))
    with sessao_como(fabrica, "sistema:coleta") as s:
        validar_cnpj(s, "43.283.811/0001-50", ["opencnpj"], cliente)
    with sessao_como(fabrica, USUARIO) as s:
        consulta = ultima_consulta(s, KALUNGA)
        assert (consulta.situacao, consulta.provedor, consulta.uf) == ("ATIVA", "opencnpj", "SP")
        assert "FULANO" not in consulta.dados_brutos
        assert ultima_consulta(s, "54.651.716/0011-50") is None
        assert len(s.scalars(select(ConsultaCnpj)).all()) == 1


def test_fila_de_comprovantes_reaproveita_por_30_dias(fabrica, armazem, ids):
    _coletar(fabrica, armazem, ids, captura_falsa())
    gimba = "54651716001150"
    with sessao_como(fabrica, USUARIO) as s:
        cnpjs = cnpjs_do_projeto(s, s.get(Projeto, ids["projeto"])) + [gimba, "54.651.716/0011-50"]
        assert comprovantes_pendentes(s, cnpjs, hoje=date(2026, 9, 23)) == [KALUNGA, gimba]
        comprovante = captura_falsa(
            url="https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpjreva_Comprovante.asp",
            metodo="C4", semente="receita",
        )
        registrar_comprovante(s, armazem, KALUNGA, comprovante)
    with sessao_como(fabrica, USUARIO) as s:
        assert comprovantes_pendentes(s, cnpjs, hoje=date(2026, 10, 22)) == [gimba]
        assert comprovantes_pendentes(s, cnpjs, hoje=date(2026, 10, 23)) == [KALUNGA, gimba]
