"""Auditoria: histórico automático, autor obrigatório, nada apagado, imutáveis (princípios 2, 5 e 6)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from orca.auditoria import ErroAuditoria, historico, historico_do_projeto
from orca.banco import (
    Arquivo,
    Correspondencia,
    Evidencia,
    Fonte,
    Item,
    Lote,
    Observacao,
    Projeto,
    agora,
    sessao_como,
)

USUARIO = "usuario:Leonardo"


def _novo_item(s, projeto_id, **campos):
    lote = s.scalars(select(Lote)).first()
    item = Item(lote=lote, descricao="Papel sulfite A4", qtd_planejada=2, mes_inicio=2, mes_fim=11, **campos)
    s.add(item)
    s.flush()
    return item


def test_criacao_registra_evento_com_autor_e_fotografia(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        eventos = historico(s, "projeto", projeto_id)
        assert [e.acao for e in eventos] == ["criar", "alterar"]  # alterar = ligação das regras
        criar = eventos[0]
        assert criar.autor == USUARIO
        assert criar.depois["teto_centavos"] == 15_000_000
        assert criar.projeto_id == projeto_id
        assert eventos[1].depois["camadas_regras"] and eventos[1].antes["camadas_regras"] == []


def test_alteracao_registra_so_o_que_mudou(fabrica, projeto_id):
    with sessao_como(fabrica, "usuario:Maria") as s:
        s.get(Projeto, projeto_id).teto_centavos = 14_000_000
    with sessao_como(fabrica, USUARIO) as s:
        ultimo = historico(s, "projeto", projeto_id)[-1]
        assert ultimo.acao == "alterar"
        assert ultimo.antes == {"teto_centavos": 15_000_000}
        assert ultimo.depois == {"teto_centavos": 14_000_000}
        assert ultimo.autor == "usuario:Maria"


def test_exclusao_logica_e_arquivamento(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        item = _novo_item(s, projeto_id)
        item_id = item.id
    with sessao_como(fabrica, USUARIO) as s:
        s.get(Item, item_id).excluido_em = agora()
        s.get(Projeto, projeto_id).arquivado_em = agora()
    with sessao_como(fabrica, USUARIO) as s:
        assert historico(s, "item", item_id)[-1].acao == "excluir"
        assert historico(s, "projeto", projeto_id)[-1].acao == "arquivar"
        assert s.get(Item, item_id) is not None  # o registro continua no banco


def test_eventos_dos_filhos_apontam_o_projeto(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        _novo_item(s, projeto_id)
    with sessao_como(fabrica, USUARIO) as s:
        entidades = {e.entidade for e in historico_do_projeto(s, projeto_id)}
        assert {"projeto", "orcamento", "lote", "item"} <= entidades


def test_apagar_e_recusado(fabrica, projeto_id):
    with pytest.raises(ErroAuditoria, match="nunca são apagados"):
        with sessao_como(fabrica, USUARIO) as s:
            s.delete(s.get(Projeto, projeto_id))


def test_gravar_sem_autor_e_recusado(fabrica, projeto_id):
    s = fabrica()
    try:
        s.get(Projeto, projeto_id).nome = "Sem autor"
        with pytest.raises(ErroAuditoria, match="precisa de autor"):
            s.flush()
    finally:
        s.rollback()
        s.close()


def test_autor_invalido_e_recusado(fabrica):
    with pytest.raises(ValueError, match="Autor inválido"):
        with sessao_como(fabrica, "Leonardo"):
            pass


def test_alterar_registro_imutavel_e_recusado(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        item = _novo_item(s, projeto_id)
        fonte = Fonte(tipo="loja", nome="Kalunga", dominio="www.kalunga.com.br")
        s.add(Arquivo(sha256="a" * 64, caminho="evidencias/aa/aa/a.pdf", tipo_mime="application/pdf", tamanho=10))
        s.flush()
        evidencia = Evidencia(url="https://exemplo", capturado_em=agora(), metodo="C1", pdf_sha256="a" * 64)
        obs = Observacao(
            alvo_tipo="item", item=item, fonte=fonte, url="https://exemplo", preco_centavos=3450,
            encontrado=True, coletado_em=datetime(2026, 9, 23, 12, tzinfo=UTC), metodo="C1",
            evidencia=evidencia, autor="sistema:coleta",
        )
        s.add(obs)
        s.flush()
        obs_id = obs.id
    with pytest.raises(ErroAuditoria, match="imutável"):
        with sessao_como(fabrica, USUARIO) as s:
            s.get(Observacao, obs_id).preco_centavos = 3390  # princípio 5: preço nunca muda


def test_ia_nunca_marca_verde(fabrica, projeto_id):
    """Princípio 4, garantido também pelo banco."""
    with pytest.raises(IntegrityError):
        with sessao_como(fabrica, USUARIO) as s:
            item = _novo_item(s, projeto_id)
            fonte = Fonte(tipo="loja", nome="Loja")
            obs = Observacao(
                alvo_tipo="item", item=item, fonte=fonte, url="https://x", encontrado=True,
                coletado_em=agora(), metodo="C1", autor="sistema",
            )
            s.add(Correspondencia(item=item, observacao=obs, status="verde", origem="ia", autor="ia:gemini"))


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("ean", "7896089012018"), ("cep", "123")],
)
def test_validacoes_na_gravacao(fabrica, projeto_id, campo, valor):
    with pytest.raises(ValueError):
        with sessao_como(fabrica, USUARIO) as s:
            _novo_item(s, projeto_id, **{campo: valor}) if campo == "ean" else setattr(
                s.get(Projeto, projeto_id), campo, valor
            )


def test_valores_normalizados(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        p = s.get(Projeto, projeto_id)
        p.cep = "03977-015"
        assert p.cep == "03977015"
        assert p.organizacao.cnpj == "03645949000137"


def test_data_hora_sem_fuso_e_recusada(fabrica, projeto_id):
    with pytest.raises(Exception, match="fuso"):
        with sessao_como(fabrica, USUARIO) as s:
            s.get(Projeto, projeto_id).arquivado_em = datetime(2026, 9, 23, 12)
