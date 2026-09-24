"""Seleção de lojas, resolução e vagas com dados sintéticos (T-04, T-05, T-09, T-12, T-13, T-14)."""

import pytest

from orca.calculo import ComparacaoMedia
from orca.regras import camada_padrao, ler_camada, resolver
from orca.selecao import (
    Alternativa,
    ItemLote,
    Loja,
    Oferta,
    ParametrosSelecao,
    SemTrio,
    Vaga,
    analisar_lote,
    selecionar_vagas,
    trocar_loja,
    trocar_produto,
)

P = ParametrosSelecao()

# CNPJs válidos de empresas diferentes (usados só como identificadores)
CNPJ = {
    "a": "43283811000150",
    "b": "45543915000181",
    "c": "03645949000137",
    "d": "19576717000104",
    "e": "54651716001150",
    "f": "01157555001186",
}
FILIAL_DE_B = "45543915073650"  # filial do Carrefour vista no levantamento; matriz = CNPJ["b"]


def loja(chave, precos, nome=None, **extra):
    """precos: {item_id: centavos | Oferta}."""
    ofertas = {k: v if isinstance(v, Oferta) else Oferta(v) for k, v in precos.items()}
    return Loja(id=chave, nome=nome or f"Loja {chave.upper()}", cnpj=extra.pop("cnpj", CNPJ.get(chave)), ofertas=ofertas, **extra)


ITENS = [ItemLote("x", "Item X", 10), ItemLote("y", "Item Y", 1)]


def test_trio_e_as_tres_de_menor_total_e_justificativa():
    lojas = [
        loja("a", {"x": 100, "y": 1000}),  # 2000
        loja("b", {"x": 90, "y": 1000}),  # 1900
        loja("c", {"x": 120, "y": 900}),  # 2100
        loja("d", {"x": 200, "y": 1000}),  # 3000
        loja("e", {"x": 50}),  # incompleta
    ]
    a = analisar_lote(ITENS, lojas, P)
    assert [lc.loja.id for lc in a.trio] == ["b", "a", "c"]
    assert a.escolhida.id == "b"
    assert "Loja B escolhida para o Orçamento 1: possui os 2 itens" in a.justificativa
    assert "entre as 4 lojas completas" in a.justificativa
    assert ("e", "não tem: Item Y") in [(l.id, m) for l, m in a.descartadas]


def test_desempate_por_qualidade_da_evidencia_e_nome():
    lojas = [loja(k, {"x": 100, "y": 100}, qualidade_evidencia=q) for k, q in (("a", 0), ("b", 5), ("c", 0), ("d", 0))]
    assert [lc.loja.id for lc in analisar_lote(ITENS, lojas, P).trio] == ["b", "a", "c"]


def test_loja_sem_cnpj_inativa_ou_nao_verde_fica_de_fora():  # T-12
    lojas = [
        loja("a", {"x": 1, "y": 1}, cnpj=None),
        loja("b", {"x": 2, "y": 2}, cnpj_ativo=False),
        loja("c", {"x": 3, "y": Oferta(3, verde=False)}),
        loja("d", {"x": 4, "y": Oferta(4, evidencia_valida=False)}),
        loja("e", {"x": 5, "y": 5}),
        loja("f", {"x": 6, "y": 6}),
    ]
    r = analisar_lote(ITENS, lojas, P)
    assert isinstance(r, SemTrio)
    motivos = dict((l.id, m) for l, m in r.descartadas)
    assert "sem CNPJ do vendedor" in motivos["a"]
    assert "CNPJ não está ativo" in motivos["b"]
    assert "não confirmado como idêntico: Item Y" in motivos["c"]
    assert "evidência inválida: Item Y" in motivos["d"]


def test_duas_filiais_da_mesma_empresa_contam_como_uma():  # P-03
    lojas = [
        loja("b", {"x": 100, "y": 100}),
        loja("b2", {"x": 101, "y": 100}, cnpj=FILIAL_DE_B, nome="Loja B (filial)"),
        loja("a", {"x": 102, "y": 100}),
        loja("c", {"x": 103, "y": 100}),
    ]
    a = analisar_lote(ITENS, lojas, P)
    assert [lc.loja.id for lc in a.trio] == ["b", "a", "c"]
    assert ("b2", "mesma empresa (CNPJ) de Loja B (P-03)") in [(l.id, m) for l, m in a.descartadas]


def test_item_bloqueador():  # T-14
    itens = ITENS + [ItemLote("z", "Item Z raro", 1)]
    lojas = [
        loja("a", {"x": 1, "y": 1, "z": 1}),
        loja("b", {"x": 1, "y": 1, "z": 1}),
        loja("c", {"x": 1, "y": 1}),
        loja("d", {"x": 1, "y": 1}),
    ]
    r = analisar_lote(itens, lojas, P)
    assert isinstance(r, SemTrio)
    assert [(i.nome, c) for i, c in r.bloqueadores] == [("Item Z raro", 2)]
    assert r.mensagem == "Não há 3 lojas com todos os itens. Itens que impedem: Item Z raro (em 2 lojas válidas)."
    assert "criar um lote separado para o item, com o seu próprio trio" in r.sugestoes


def test_nenhum_grupo_completo_mesmo_com_cobertura_suficiente():
    itens = [ItemLote("x", "X", 1), ItemLote("y", "Y", 1)]
    lojas = [loja("a", {"x": 1}), loja("b", {"x": 1}), loja("c", {"x": 1, "y": 1}), loja("d", {"y": 1}), loja("e", {"y": 1})]
    r = analisar_lote(itens, lojas, P)
    assert isinstance(r, SemTrio) and not r.bloqueadores
    assert "nenhum grupo de 3 lojas tem todos os itens juntos" in r.mensagem


def test_regra_a_usa_a_media_e_nao_confere():  # T-13 (parte)
    lojas = [loja("a", {"x": 795, "y": 100}), loja("b", {"x": 860, "y": 100}), loja("c", {"x": 690, "y": 100})]
    a = analisar_lote(ITENS, lojas, ParametrosSelecao(base_preco_final="A"))
    linha_x = next(l for l in a.linhas if l.item.id == "x")
    assert linha_x.preco_final_centavos == 782 and linha_x.dentro_da_media is None
    assert a.violacoes == ()


def test_parametros_vindos_das_regras():
    orc = ler_camada("perfil: Orç\ncamada: orcamento\nversao: 1\ncalculo:\n  base_preco_final: A\n  comparar_com: media_exibida\n")
    p = ParametrosSelecao.de_regras(resolver([camada_padrao(), orc]).regras)
    assert p.base_preco_final == "A" and p.comparar_com is ComparacaoMedia.EXIBIDA and p.fontes_por_cotacao == 3


# --- Saída 2: trocar a loja (T-05) -------------------------------------------


def test_trocar_loja_em_cadeia_ate_resolver():
    itens = [ItemLote("x", "Item X", 1), ItemLote("y", "Item Y", 1)]
    lojas = [
        loja("a", {"x": 500, "y": 10}),  # total 510 — X acima da média no trio A, B, C
        loja("b", {"x": 10, "y": 520}),  # 530 — Y acima da média no trio B, C, D
        loja("c", {"x": 110, "y": 450}),  # 560
        loja("d", {"x": 120, "y": 450}),  # 570
        loja("e", {"x": 130, "y": 460}),  # 590
    ]
    resultado = trocar_loja(itens, lojas, P)
    assert resultado.sucesso
    assert [t.removida.id for t in resultado.tentativas] == ["a", "b"]  # só a loja escolhida sai
    assert "Item X: R$ 5,00 na loja Loja A passa da média" in resultado.tentativas[0].motivo
    assert [lc.loja.id for lc in resultado.final.trio] == ["c", "d", "e"]
    assert resultado.final.violacoes == ()
    assert "Resolvido retirando Loja A, Loja B" in resultado.mensagem


def test_trocar_loja_sem_violacao_nao_faz_nada():
    lojas = [loja(k, {"x": 100, "y": 100}) for k in "abc"]
    r = trocar_loja(ITENS, lojas, P)
    assert r.sucesso and r.tentativas == () and "nada a trocar" in r.mensagem


# --- Saída 1: trocar o produto (T-04) ----------------------------------------


def test_trocar_produto_lista_as_validas_primeiro():
    itens = [ItemLote("x", "Café marca 1", 10), ItemLote("y", "Leite", 20)]
    lojas = [
        loja("a", {"x": 3209, "y": 100}),  # 32.090 + 2.000 = 34.090: menor total, café acima da média
        loja("b", {"x": 2699, "y": 659}),  # 26.990 + 13.180 = 40.170
        loja("c", {"x": 2798, "y": 729}),  # 27.980 + 14.580 = 42.560
    ]
    analise = analisar_lote(itens, lojas, P)
    assert analise.escolhida.id == "a"
    assert [v.item.id for v in analise.violacoes] == ["x"]

    alternativas = [
        Alternativa("m2", "Café marca 2", {"a": Oferta(2500), "b": Oferta(2600), "c": Oferta(2700)}),  # válida
        Alternativa("m3", "Café marca 3", {"a": Oferta(3000), "b": Oferta(2500), "c": Oferta(2400)}),  # acima da média
        Alternativa("m4", "Café marca 4", {"a": Oferta(2000), "b": Oferta(2100)}),  # falta na loja C
        Alternativa("m5", "Café marca 5", {"a": Oferta(2400), "b": Oferta(2450), "c": Oferta(2500)}),  # válida, maior impacto
    ]
    opcoes = trocar_produto(itens, analise, "x", alternativas)
    assert [(o.alternativa.id, o.valida) for o in opcoes] == [("m2", True), ("m5", True), ("m3", False), ("m4", False)]
    assert opcoes[0].impacto_centavos == (2500 - 3209) * 10
    assert "passa da média" in opcoes[2].motivo
    assert opcoes[3].motivo == "não encontrado como idêntico em: Loja C"


def test_trocar_produto_recusa_se_a_escolhida_deixar_de_ser_a_mais_barata():
    itens = [ItemLote("x", "X", 10), ItemLote("y", "Y", 1)]
    lojas = [loja("a", {"x": 200, "y": 100}), loja("b", {"x": 150, "y": 700}), loja("c", {"x": 160, "y": 800})]
    analise = analisar_lote(itens, lojas, P)
    assert analise.escolhida.id == "a"
    alt = Alternativa("x2", "X2", {"a": Oferta(260), "b": Oferta(190), "c": Oferta(330)})  # A: 2.700 > B: 2.600
    [opcao] = trocar_produto(itens, analise, "x", [alt])
    assert not opcao.valida and "deixaria de ter o menor total (D-26)" in opcao.motivo


def test_trocar_produto_item_inexistente():
    lojas = [loja(k, {"x": 1, "y": 1}) for k in "abc"]
    with pytest.raises(ValueError, match="não está no lote"):
        trocar_produto(ITENS, analisar_lote(ITENS, lojas, P), "zzz", [])


# --- Vagas (T-09) --------------------------------------------------------------


def test_selecao_de_vagas():
    vagas = [
        Vaga("v1", "Empresa A", CNPJ["a"], 250000, 300000, grupo="g1", plataforma="catho"),  # faixa → 2.500
        Vaga("v2", "Empresa A", CNPJ["a"], 250000, 300000, grupo="g1", plataforma="indeed"),  # mesma vaga
        Vaga("v3", "Empresa B", CNPJ["b"], None, None),  # sem salário
        Vaga("v4", "Confidencial", None, 200000),  # empresa não identificada
        Vaga("v5", "Empresa C", CNPJ["c"], 400100),
        Vaga("v6", "Empresa A", CNPJ["a"], 260000, grupo="g2"),  # outra vaga da mesma empresa
        Vaga("v7", "Empresa D", CNPJ["d"], None, 500000),  # salário único
        Vaga("v8", "Empresa E", CNPJ["e"], 600100),
    ]
    s = selecionar_vagas(vagas)
    assert s.suficiente
    assert [v.id for v in s.escolhidas] == ["v1", "v5", "v7"]
    assert s.cotacao.precos == (250000, 400100, 500000)
    motivos = {v.id: m for v, m in s.descartadas}
    assert "mesma vaga de Empresa A" in motivos["v2"]
    assert "sem salário" in motivos["v3"]
    assert "empresa não identificada" in motivos["v4"]
    assert "empresa já usada" in motivos["v6"]
    assert "v8" not in motivos  # simplesmente não precisou


def test_vagas_insuficientes():
    s = selecionar_vagas([Vaga("v1", "A", CNPJ["a"], 100), Vaga("v2", "B", None, 100)])
    assert not s.suficiente and s.cotacao is None
    assert s.mensagem == "Só 1 de 3 vagas válidas encontradas; pesquise mais vagas."
