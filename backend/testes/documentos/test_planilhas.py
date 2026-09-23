"""Planilhas com fórmulas vivas: as fórmulas dão exatamente os valores do dossiê (caso real, R$ 150.000,00)."""

import pytest

from avaliador_planilhas import Planilha, centavos
from caso_documentos import GRADE, montar
from orca.documentos import grade_comparativa, plano_de_aplicacao
from orca.documentos.planilhas import nome_de_aba


@pytest.fixture(scope="module")
def dossie():
    return montar()[0]


def test_grade_comparativa_formulas_batem_com_o_sistema(dossie):
    acima = []
    for orcamento in dossie.orcamentos:
        if not orcamento.lotes:
            continue
        planilha = Planilha(grade_comparativa(orcamento, dossie))
        assert planilha.livro.sheetnames == [l.nome for l in orcamento.lotes]
        for lote in orcamento.lotes:
            n = len(lote.lojas)
            col = lambda c: planilha.livro[lote.nome].cell(1, c).column_letter  # noqa: E731
            for i, linha in enumerate(lote.linhas):
                r = 9 + i
                v = lambda c: planilha.valor(lote.nome, f"{col(c)}{r}")  # noqa: E731
                assert [centavos(v(5 + 2 * k)) for k in range(n)] == list(linha.totais)
                assert centavos(v(4 + 2 * n)) == linha.media_exibida
                assert centavos(v(5 + 2 * n)) == linha.media_dos_totais
                assert centavos(v(6 + 2 * n)) == linha.preco_final_centavos
                assert centavos(v(7 + 2 * n)) == linha.total_final
                situacao = v(8 + 2 * n)
                assert situacao == ("dentro da média" if linha.dentro_da_media else "ACIMA DA MÉDIA")
                if not linha.dentro_da_media:
                    acima.append(linha.nome)
            total = 9 + len(lote.linhas)
            for k, loja in enumerate(lote.lojas):
                assert centavos(planilha.valor(lote.nome, f"{col(5 + 2 * k)}{total}")) == loja.total_centavos
            assert centavos(planilha.valor(lote.nome, f"{col(7 + 2 * n)}{total}")) == lote.total_final
    assert sorted(acima) == sorted(GRADE["diligencia"])  # T-03: os 14 itens da diligência


def test_orcamento_1_e_a_loja_de_menor_total(dossie):
    for o in dossie.orcamentos:
        for lote in o.lotes:
            totais = [l.total_centavos for l in lote.lojas]
            assert totais[0] == min(totais)
            assert all(l.preco_final_centavos == l.fontes[0].preco_centavos for l in lote.linhas)  # regra B


def test_plano_de_aplicacao_fecha_o_teto_nas_formulas(dossie):
    planilha = Planilha(plano_de_aplicacao(dossie))
    aba = planilha.livro["Aplicação"]
    linhas = [r for r in range(4, aba.max_row + 1) if aba.cell(r, 2).value == "Total do projeto"]
    assert len(linhas) == 1
    total = linhas[0]
    assert centavos(planilha.valor("Aplicação", f"G{total}")) == dossie.total_centavos == 15_000_000
    assert centavos(planilha.valor("Aplicação", f"G{total + 2}")) == 0  # diferença para o teto
    assert centavos(planilha.valor("Recursos", "B3")) == 15_000_000
    assert centavos(planilha.valor("Recursos", "B5")) == 15_000_000  # sem contrapartida

    subtotais = {aba.cell(r, 1).value: centavos(planilha.valor("Aplicação", f"G{r}"))
                 for r in range(4, total) if str(aba.cell(r, 2).value or "").startswith("Subtotal")}
    assert subtotais == {o.nome: o.total_no_projeto for o in dossie.orcamentos}

    crono = planilha.livro["Cronograma físico-financeiro"]
    meses = dossie.projeto.duracao_meses
    ultima_linha = max(r for r in range(4, crono.max_row + 1) if crono.cell(r, 2).value == "Total do mês")
    total_meses = [centavos(planilha.valor("Cronograma físico-financeiro", f"{crono.cell(1, 2 + m).column_letter}{ultima_linha}"))
                   for m in range(1, meses + 1)]
    assert sum(total_meses) == 15_000_000
    acumulado = centavos(planilha.valor("Cronograma físico-financeiro", f"{crono.cell(1, 2 + meses).column_letter}{ultima_linha + 1}"))
    assert acumulado == 15_000_000
    for r in range(4, ultima_linha):  # cada linha soma o total do plano
        linha_plano = int(crono.cell(r, 1).value.split("A")[-1])
        assert (planilha.valor("Cronograma físico-financeiro", f"{crono.cell(1, 3 + meses).column_letter}{r}")
                == planilha.valor("Aplicação", f"G{linha_plano}"))

    desembolso = planilha.livro["Cronograma de desembolso"]
    assert centavos(planilha.valor("Cronograma de desembolso", "B4")) == 15_000_000  # parcela única no 1º mês (P-06)
    assert centavos(planilha.valor("Cronograma de desembolso", f"B{4 + meses}")) == 15_000_000
    assert desembolso["B5"].value == 0


def test_desembolso_conforme_cronograma():
    from dataclasses import replace

    dossie = montar()[0]
    dossie = replace(dossie, projeto=replace(dossie.projeto, desembolso="conforme_cronograma"))
    planilha = Planilha(plano_de_aplicacao(dossie))
    meses = dossie.projeto.duracao_meses
    parcelas = [centavos(planilha.valor("Cronograma de desembolso", f"B{3 + m}")) for m in range(1, meses + 1)]
    assert sum(parcelas) == 15_000_000 and parcelas[0] < 15_000_000 and parcelas[-1] > 0


def test_nome_de_aba():
    usados: set[str] = set()
    assert nome_de_aba("Limpeza + utensílios / cozinha [x]", usados) == "Limpeza + utensílios - cozin"
    assert nome_de_aba("Limpeza + utensílios / cozinha [x]", usados) == "Limpeza + utensílios - co (2)"
