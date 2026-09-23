"""Fluxo completo a partir do banco: seleção, Saída 2, vagas, teto, painel e dossiê."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from apoio_fluxo import COLETA, HOJE, LOJAS, USUARIO, criar_projeto, loja, observar_item
from orca.banco import Correspondencia, Decisao, Fonte, Item, Lote, Projeto, abrir_banco, sessao_como
from orca.coleta import ler_jornadas, ler_vocabulario
from orca.documentos import conferir
from orca.evidencias import ArmazemArquivos
from orca.fluxo import (
    AMARELO,
    VERDE,
    VERMELHO,
    ErroAcao,
    ErroDossie,
    corresponder_pendentes,
    devolver_loja,
    dossie_do_projeto,
    estado_do_projeto,
    execucao_vigente,
    fechar_teto_do_projeto,
    montar_problema,
    painel,
    retirar_loja,
    simular_troca_de_loja,
    substituir_item,
)
from orca.selecao import AnaliseLote, ParametrosSelecao, SemTrio

JORNADAS = ler_jornadas()
VOCABULARIO = ler_vocabulario()


@pytest.fixture
def fabrica(tmp_path):
    return abrir_banco(tmp_path / "orca.sqlite")


@pytest.fixture
def armazem(tmp_path):
    return ArmazemArquivos(tmp_path / "dados")


@pytest.fixture
def ids(fabrica, armazem):
    ids = criar_projeto(fabrica, armazem)
    with sessao_como(fabrica, "sistema:correspondencia") as s:
        corresponder_pendentes(s, [s.get(Lote, ids["lote"])], VOCABULARIO)
    return ids


def _estado(s, ids):
    return estado_do_projeto(s, s.get(Projeto, ids["projeto"]), JORNADAS, HOJE)


def test_selecao_a_partir_do_banco(fabrica, ids):
    with sessao_como(fabrica, USUARIO) as s:
        assert {c.origem for c in s.scalars(select(Correspondencia))} == {"ean"}
        estado = _estado(s, ids)
        (_, lote), = estado.lotes()
        analise = lote.analise
        assert isinstance(analise, AnaliseLote)
        assert [lc.loja.id for lc in analise.trio] == [loja(ids, "G"), loja(ids, "T"), loja(ids, "L")]
        assert analise.trio[0].loja.nome == "Loja G"
        assert [v.item.id for v in analise.violacoes] == [ids["leite"]]  # leite condensado acima da média
        descartadas = dict((l.id, motivo) for l, motivo in analise.descartadas)
        assert descartadas[loja(ids, "X")] == "CNPJ não está ativo"  # sem consulta, não dá para confirmar
        status = {l.id: l for l in painel(estado, None).linhas}
        assert status[ids["papel"]].status == VERDE
        assert status[ids["leite"]].status == VERMELHO and "passa da média" in status[ids["leite"]].motivos[0]


def test_saida_2_retirar_a_loja_escolhida(fabrica, ids):
    with sessao_como(fabrica, USUARIO) as s:
        estado = _estado(s, ids)
        (o, lote), = estado.lotes()
        simulacao = simular_troca_de_loja(lote, ParametrosSelecao.de_regras(o.perfil.regras))
        assert simulacao.sucesso and simulacao.final.escolhida.id == loja(ids, "T")
        retirar_loja(s, s.get(Lote, ids["lote"]), loja(ids, "G"), "leite condensado acima da média; Saída 2")
    with sessao_como(fabrica, USUARIO) as s:
        (_, lote), = _estado(s, ids).lotes()
        assert [lc.loja.id for lc in lote.analise.trio] == [loja(ids, "T"), loja(ids, "L"), loja(ids, "K")]
        assert lote.analise.violacoes == () and lote.retiradas == {loja(ids, "G")}
        devolver_loja(s, s.get(Lote, ids["lote"]), loja(ids, "G"), "revendo a decisão")
    with sessao_como(fabrica, USUARIO) as s:
        (_, lote), = _estado(s, ids).lotes()
        assert lote.analise.trio[0].loja.id == loja(ids, "G")
        assert [d.tipo for d in s.scalars(select(Decisao).order_by(Decisao.criado_em))] == ["retirar_loja", "devolver_loja"]


def test_so_pessoas_decidem_e_com_justificativa(fabrica, ids):
    with pytest.raises(ErroAcao, match="Só uma pessoa"):
        with sessao_como(fabrica, "sistema") as s:
            retirar_loja(s, s.get(Lote, ids["lote"]), "x", "motivo")
    with pytest.raises(ErroAcao, match="justificativa"):
        with sessao_como(fabrica, USUARIO) as s:
            retirar_loja(s, s.get(Lote, ids["lote"]), "x", " ")


def test_vagas_do_banco(fabrica, ids):
    with sessao_como(fabrica, USUARIO) as s:
        (_, cargo), = _estado(s, ids).cargos()
        escolhidas = {v.id for v in cargo.selecao.escolhidas}
        assert len(escolhidas) == 3 and ids["vagas"]["v2"] in escolhidas and ids["vagas"]["v3"] in escolhidas
        assert len(escolhidas & {ids["vagas"]["v1"], ids["vagas"]["v4"]}) == 1  # a mesma vaga conta uma vez
        motivos = {v.id: m for v, m in cargo.selecao.descartadas}
        assert "sem salário" in motivos[ids["vagas"]["v5"]]
        assert cargo.calculo.salarios == (250_000, 260_000, 270_000)
        assert (cargo.calculo.divisor, cargo.calculo.valor_hora, cargo.calculo.valor_mensal) == (220, 1182, 94_560)
        assert cargo.calculo.total == 1_134_720


def test_teto_dossie_e_execucao_desatualizada(fabrica, armazem, ids):
    with sessao_como(fabrica, USUARIO) as s:
        retirar_loja(s, s.get(Lote, ids["lote"]), loja(ids, "G"), "Saída 2")
    with sessao_como(fabrica, USUARIO) as s:
        estado = _estado(s, ids)
        execucao, resultado, pendencias = fechar_teto_do_projeto(s, estado)
        assert pendencias == () and execucao.status == "otima" and execucao.verificacao_ok
        assert execucao.total_centavos == 1_611_720 and resultado.alteracoes == ()
        s.flush()
        assert execucao_vigente(s, estado).id == execucao.id
        p = painel(estado, execucao)
        assert p.total_centavos == p.teto_centavos and p.diferenca_centavos == 0
        assert p.contagem == {VERDE: 3, AMARELO: 0, VERMELHO: 0}
        assert p.cnpjs_sem_consulta == (LOJAS["X"][1],)  # a loja X, que ficou de fora

        dossie = dossie_do_projeto(s, estado, execucao, datetime(2026, 9, 24, 13, tzinfo=UTC))
        assert dossie.total_centavos == 1_611_720
        (lote_doc,) = dossie.orcamentos[0].lotes
        assert [l.empresa.nome for l in lote_doc.lojas] == ["Loja T Ltda", "Loja L Ltda", "Loja K Ltda"]
        assert all(f.evidencia and f.evidencia.arquivo("pdf") for linha in lote_doc.linhas for f in linha.fontes)
        (cargo_doc,) = dossie.orcamentos[1].cargos
        assert cargo_doc.valor_mensal_centavos == 94_560 and len(cargo_doc.vagas) == 3
        assert any("sem salário" in motivo for _, motivo in cargo_doc.descartadas)
        conformidade = {c.regra.rsplit(" (", 1)[0]: c.situacao for c in conferir(dossie, HOJE)}
        assert conformidade["Teto exato ao centavo"] == "ok" and conformidade["Preço final dentro da média"] == "ok"
        assert conformidade["Comprovante da Receita de cada empresa"] == "atencao"
        assert len(dossie.eventos) > 10

    # Um preço novo muda o problema: a execução antiga deixa de valer
    with sessao_como(fabrica, USUARIO) as s:
        papel = s.get(Item, ids["papel"])
        fonte = s.get(Fonte, ids["fontes"]["L"])
        observar_item(s, armazem, papel, fonte, LOJAS["L"][1], 3550, datetime(2026, 9, 24, 12, tzinfo=UTC), "nova")
    with sessao_como(fabrica, "sistema:correspondencia") as s:
        corresponder_pendentes(s, [s.get(Lote, ids["lote"])], VOCABULARIO)
    with sessao_como(fabrica, USUARIO) as s:
        estado = _estado(s, ids)
        assert execucao_vigente(s, estado) is None
        assert painel(estado, None).total_centavos is None


def test_pendencias_impedem_teto_e_documentos(fabrica, ids):
    with sessao_como(fabrica, USUARIO) as s:
        lote = s.get(Lote, ids["lote"])
        s.add(Item(lote=lote, descricao="Caneta azul", categoria="caneta", marca="BIC", qtd_planejada=10,
                   mes_inicio=1, mes_fim=12))
    with sessao_como(fabrica, USUARIO) as s:
        estado = _estado(s, ids)
        (_, lote), = estado.lotes()
        assert isinstance(lote.analise, SemTrio)
        montado = montar_problema(estado)
        assert montado.problema is None and "Copa e escritório" in montado.pendencias[0]
        _, _, pendencias = fechar_teto_do_projeto(s, estado)
        assert pendencias == montado.pendencias
        with pytest.raises(ErroDossie, match="Ainda não dá"):
            dossie_do_projeto(s, estado, None)
        status = {l.nome: l.status for l in painel(estado, None).linhas}
        assert status["Caneta azul"] == VERMELHO  # não existe em nenhuma loja válida


def test_trocar_produto_cria_item_novo(fabrica, ids):
    with sessao_como(fabrica, USUARIO) as s:
        antigo = s.get(Item, ids["leite"])
        novo = substituir_item(s, antigo, "leite condensado acima da média; outra marca", marca="Italac",
                               descricao="Leite condensado Italac 395g", ean=None)
        novo_id = novo.id
    with sessao_como(fabrica, USUARIO) as s:
        antigo, novo = s.get(Item, ids["leite"]), s.get(Item, novo_id)
        assert antigo.excluido_em is not None and novo.substitui_item_id == antigo.id and novo.marca == "Italac"
        (_, lote), = _estado(s, ids).lotes()
        assert [i.id for i in lote.itens] == [ids["papel"], novo_id]
        assert isinstance(lote.analise, SemTrio)  # o produto novo ainda precisa ser pesquisado
    with pytest.raises(ErroAcao, match="desconhecidos"):
        with sessao_como(fabrica, USUARIO) as s:
            substituir_item(s, s.get(Item, novo_id), "x", preco=1)


def test_correspondencia_pendente_nao_duplica(fabrica, ids):
    with sessao_como(fabrica, "sistema:correspondencia") as s:
        assert corresponder_pendentes(s, [s.get(Lote, ids["lote"])], VOCABULARIO) == []
        assert len(s.scalars(select(Correspondencia)).all()) == 2 * len(LOJAS)


def test_observacao_vencida_nao_vale(fabrica, ids):
    with sessao_como(fabrica, USUARIO) as s:
        estado = estado_do_projeto(s, s.get(Projeto, ids["projeto"]), JORNADAS, datetime(2027, 4, 1).date())
        (_, lote), = estado.lotes()
        assert isinstance(lote.analise, SemTrio)  # todas as pesquisas de 23/09/2026 venceram (D-12)
        assert COLETA.year == 2026
