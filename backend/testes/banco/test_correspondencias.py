"""Correspondências gravadas: resultado do programa, decisão humana, IA nunca promove, nível de automação."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from orca.auditoria import ErroAuditoria
from orca.banco import (
    Correspondencia,
    ErroCorrespondencia,
    Fonte,
    Item,
    Lote,
    Observacao,
    Projeto,
    correspondencia_vigente,
    corresponder,
    decidir_correspondencia,
    perfil_do_projeto,
    registrar_correspondencia,
    sessao_como,
    vale_como_verde,
)
from orca.coleta import ler_vocabulario
from orca.correspondencia import ResultadoCorrespondencia
from orca.dominio import OrigemCorrespondencia, StatusCorrespondencia

USUARIO = "usuario:Leonardo"
VOCABULARIO = ler_vocabulario()


def _item_e_observacao(s, projeto_id, titulo, ean=None):
    lote = s.scalars(select(Lote)).first()
    item = Item(lote=lote, descricao="Papel sulfite A4 75g", categoria="papel", marca="Chamex",
                apresentacao="pacote com 500 folhas", qtd_planejada=10, mes_inicio=1, mes_fim=1)
    obs = Observacao(
        alvo_tipo="item", item=item, fonte=Fonte(tipo="loja", nome="Kalunga", dominio="kalunga.com.br"),
        url="https://www.kalunga.com.br/prod/1", titulo=titulo, ean=ean, preco_centavos=3450, encontrado=True,
        coletado_em=datetime(2026, 9, 23, 15, tzinfo=UTC), metodo="C1", autor=USUARIO,
    )
    s.add_all([item, obs])
    return item, obs


def test_programa_grava_e_pessoa_decide(fabrica, projeto_id):
    with sessao_como(fabrica, "sistema:correspondencia") as s:
        item, obs = _item_e_observacao(s, projeto_id, "Papel Sulfite A4 75g Chamex 500 folhas")
        c = corresponder(s, item, obs, VOCABULARIO)
        assert (c.status, c.origem, c.autor) == ("verde", "atributos", "sistema:correspondencia")
        s.flush()
        ids = (item.id, obs.id)
    with sessao_como(fabrica, USUARIO) as s:
        item, obs = s.get(Item, ids[0]), s.get(Observacao, ids[1])
        regras = perfil_do_projeto(s, s.get(Projeto, projeto_id)).regras
        vigente = correspondencia_vigente(s, *ids)
        assert not vale_como_verde(vigente, regras)  # por atributos: "com aprovação" no perfil padrão
        decidir_correspondencia(s, item, obs, "verde", "conferi a página: mesmo papel")
    with sessao_como(fabrica, USUARIO) as s:
        vigente = correspondencia_vigente(s, *ids)
        assert (vigente.origem, vigente.motivos) == ("humano", ["conferi a página: mesmo papel"])
        assert vale_como_verde(vigente, perfil_do_projeto(s, s.get(Projeto, projeto_id)).regras)
        assert len(s.scalars(select(Correspondencia)).all()) == 2  # a primeira continua no histórico


def test_codigo_de_barras_vale_sem_aprovacao_no_perfil_padrao(fabrica, projeto_id):
    with sessao_como(fabrica, "sistema") as s:
        item, obs = _item_e_observacao(s, projeto_id, "Resma Chamex", ean="7891173023001")
        item.ean = "7891173023001"
        c = corresponder(s, item, obs, VOCABULARIO)
        assert (c.status, c.origem) == ("verde", "ean")
        assert vale_como_verde(c, perfil_do_projeto(s, s.get(Projeto, projeto_id)).regras)
        assert not vale_como_verde(None, perfil_do_projeto(s, s.get(Projeto, projeto_id)).regras)


def test_ia_nunca_promove_para_verde(fabrica, projeto_id):
    verde = ResultadoCorrespondencia(StatusCorrespondencia.VERDE, OrigemCorrespondencia.ATRIBUTOS, ("x",), ())
    with pytest.raises(ErroCorrespondencia, match="nunca promove"):
        with sessao_como(fabrica, "ia:gemini") as s:
            item, obs = _item_e_observacao(s, projeto_id, "Papel")
            registrar_correspondencia(s, item, obs, verde)
    with pytest.raises(ErroCorrespondencia, match="Só uma pessoa"):
        with sessao_como(fabrica, "ia:gemini") as s:
            item, obs = _item_e_observacao(s, projeto_id, "Papel")
            decidir_correspondencia(s, item, obs, "verde", "parece igual")
    with pytest.raises(IntegrityError):  # o banco também recusa
        with sessao_como(fabrica, "ia:gemini") as s:
            item, obs = _item_e_observacao(s, projeto_id, "Papel")
            s.add(Correspondencia(item=item, observacao=obs, status="verde", origem="ia", motivos=[], autor="ia:gemini"))


def test_decisao_exige_justificativa_e_observacao_do_item(fabrica, projeto_id):
    with pytest.raises(ErroCorrespondencia, match="justificativa"):
        with sessao_como(fabrica, USUARIO) as s:
            item, obs = _item_e_observacao(s, projeto_id, "Papel")
            decidir_correspondencia(s, item, obs, "vermelho", "  ")
    with pytest.raises(ErroCorrespondencia, match="não é deste item"):
        with sessao_como(fabrica, USUARIO) as s:
            item, obs = _item_e_observacao(s, projeto_id, "Papel")
            outro, _ = _item_e_observacao(s, projeto_id, "Outro")
            corresponder(s, outro, obs, VOCABULARIO)


def test_correspondencia_e_imutavel(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        item, obs = _item_e_observacao(s, projeto_id, "Papel Sulfite A4 75g Chamex 300 folhas")
        c = corresponder(s, item, obs, VOCABULARIO)
        assert c.status == "vermelho" and "diferença em nº de folhas: 500 folhas × 300 folhas" in c.motivos
        s.flush()
        cid = c.id
    with pytest.raises(ErroAuditoria, match="imutável"):
        with sessao_como(fabrica, USUARIO) as s:
            s.get(Correspondencia, cid).status = "verde"
