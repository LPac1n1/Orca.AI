"""Conformidade e montagem do dossiê (caso real e casos pequenos)."""

from dataclasses import replace
from datetime import date

import pytest

from caso_documentos import GRADE, montar
from orca.calculo import calcular_mao_de_obra
from orca.documentos import (
    ATENCAO,
    OK,
    PROBLEMA,
    Empresa,
    OtimizacaoDoc,
    VagaDoc,
    cargo_doc,
    conferir,
    lote_doc,
    otimizacao_doc,
    resumo_da_conformidade,
)
from orca.evidencias import ArmazemArquivos
from orca.regras import camada_padrao, resolver
from orca.selecao import ItemLote, Loja, Oferta, ParametrosSelecao, analisar_lote

HOJE = date(2026, 9, 24)


def _por_regra(conferencias):
    return {c.regra.rsplit(" (", 1)[0]: c for c in conferencias}


@pytest.fixture(scope="module")
def com_evidencias(tmp_path_factory):
    return montar(ArmazemArquivos(tmp_path_factory.mktemp("dados")))


def test_conformidade_do_caso_real(com_evidencias):
    dossie, _ = com_evidencias
    c = _por_regra(conferir(dossie, HOJE))
    assert c["Teto exato ao centavo"].situacao == OK
    assert c["3 fontes por cotação"].situacao == OK
    media = c["Preço final dentro da média"]
    assert media.situacao == PROBLEMA and len(media.detalhes) == 14
    assert {d.split(" — ")[1].split(":")[0] for d in media.detalhes} == set(GRADE["diligencia"])
    assert c["Empresas diferentes em cada cotação"].situacao == OK
    assert c["CNPJ ativo em todas as fontes"].situacao == ATENCAO  # as empresas das vagas não foram consultadas
    comprovantes = c["Comprovante da Receita de cada empresa"]
    assert comprovantes.situacao == ATENCAO and not any("Kalunga" in d for d in comprovantes.detalhes)
    assert c["Evidência (PDF) de cada preço e salário"].situacao == OK
    assert c["Validade das pesquisas: 180 dias"].situacao == OK
    assert c["Otimização e verificação independente"].situacao == OK
    assert resumo_da_conformidade(conferir(dossie, HOJE))[PROBLEMA] == 1


def test_conformidade_aponta_teto_evidencia_validade_e_otimizacao(com_evidencias):
    dossie, _ = com_evidencias
    sem_evidencia = montar()[0]
    assert _por_regra(conferir(sem_evidencia, HOJE))["Evidência (PDF) de cada preço e salário"].situacao == PROBLEMA
    vencido = _por_regra(conferir(dossie, date(2027, 3, 30)))["Validade das pesquisas: 180 dias"]
    assert vencido.situacao == PROBLEMA and "venceu em 21/03/2027" in vencido.detalhes[0]
    entrega_tarde = replace(dossie, projeto=replace(dossie.projeto, data_entrega=date(2027, 6, 1)))
    assert "antes da entrega" in _por_regra(conferir(entrega_tarde, HOJE))["Validade das pesquisas: 180 dias"].detalhes[0]
    teto_errado = replace(dossie, projeto=replace(dossie.projeto, teto_centavos=15_000_001))
    assert _por_regra(conferir(teto_errado, HOJE))["Teto exato ao centavo"].situacao == PROBLEMA
    falhou = replace(dossie, otimizacao=OtimizacaoDoc("otima", 1, verificacao=("C3 violada no lote X",)))
    assert _por_regra(conferir(falhou, HOJE))["Otimização e verificação independente"].detalhes == ("C3 violada no lote X",)
    sem_otimizacao = replace(dossie, otimizacao=OtimizacaoDoc("sem_otimizacao", 1))
    assert _por_regra(conferir(sem_otimizacao, HOJE))["Otimização e verificação independente"].situacao == ATENCAO
    baixada = dict(dossie.empresas)
    cnpj = next(iter(baixada))
    baixada[cnpj] = replace(baixada[cnpj], situacao="BAIXADA")
    inativo = _por_regra(conferir(replace(dossie, empresas=baixada), HOJE))["CNPJ ativo em todas as fontes"]
    assert inativo.situacao == PROBLEMA and "BAIXADA" in inativo.detalhes[0]


def test_regra_a_reordena_pelo_total_final():
    regras = resolver([camada_padrao()]).regras
    parametros = replace(ParametrosSelecao.de_regras(regras), base_preco_final="A")
    itens = [ItemLote("a", "A", 10), ItemLote("b", "B", 10)]
    lojas = [
        Loja("x", "X", "43283811000150", {"a": Oferta(100), "b": Oferta(300)}),  # 4.000 → 10×100 + 1×300 = 1.300
        Loja("y", "Y", "54651716001150", {"a": Oferta(130), "b": Oferta(200)}),  # 3.300 → 10×130 + 1×200 = 1.500
        Loja("z", "Z", "45543915073650", {"a": Oferta(200), "b": Oferta(250)}),
    ]
    analise = analisar_lote(itens, lojas, parametros)
    assert [lc.loja.id for lc in analise.trio] == ["y", "x", "z"]
    doc = lote_doc(analise, "L", quantidades={"a": 10, "b": 1})
    assert [l.id for l in doc.lojas] == ["x", "y", "z"]  # com as quantidades finais, X fica mais barata (D-26)
    linha_a = doc.linhas[0]
    assert linha_a.preco_final_centavos == linha_a.media_exibida == 143 and linha_a.dentro_da_media is None


def test_cargo_com_horas_finais_refaz_a_memoria():
    planejado = calcular_mao_de_obra([300_000, 310_000, 320_000], 44, 9000, 12)
    vagas = [VagaDoc(Empresa(f"E{k}", None), s) for k, s in enumerate(planejado.salarios)]
    doc = cargo_doc("c", "Educador", "recibo", planejado, vagas, horas_finais_centesimos=10000)
    final = calcular_mao_de_obra([300_000, 310_000, 320_000], 44, 10000, 12)
    assert (doc.valor_mensal_centavos, doc.total_no_projeto) == (final.valor_mensal, final.total)
    assert doc.horas_planejadas_centesimos == 9000 and doc.memoria == tuple(final.memoria())


def test_otimizacao_doc(com_evidencias):
    dossie, problema = com_evidencias
    assert dossie.otimizacao.status == "otima" and dossie.otimizacao.total_centavos == dossie.total_centavos
    assert any(a.para.endswith("h/mês") for a in dossie.otimizacao.alteracoes)
    assert otimizacao_doc(problema, None).status == "sem_otimizacao"
