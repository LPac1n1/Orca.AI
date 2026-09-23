"""T-13: Regra A num orçamento e Regra B em outro, no mesmo projeto, com teto exato."""

from orca.calculo import calcular_mao_de_obra
from orca.otimizacao import ProblemaTeto, SolucaoTeto, fechar_teto, linha_de_cargo, linhas_do_lote
from orca.regras import camada_padrao, resolver
from orca.selecao import ItemLote, Loja, Oferta, ParametrosSelecao, analisar_lote

REGRAS = resolver([camada_padrao()]).regras
CNPJS = ["43283811000150", "45543915000181", "03645949000137"]


def _lojas(precos):
    return [Loja(f"L{n}", f"Loja {n}", CNPJS[n], {k: Oferta(v) for k, v in p.items()}) for n, p in enumerate(precos)]


def test_regra_a_e_regra_b_no_mesmo_projeto():
    itens_a = [ItemLote("pa", "Papel", 20), ItemLote("ca", "Caneta", 10)]
    lojas_a = _lojas([{"pa": 3450, "ca": 3950}, {"pa": 3450, "ca": 4680}, {"pa": 3390, "ca": 3990}])
    analise_a = analisar_lote(itens_a, lojas_a, ParametrosSelecao(base_preco_final="A"))
    itens_b = [ItemLote("su", "Suco", 20), ItemLote("le", "Leite", 20)]
    lojas_b = _lojas([{"su": 799, "le": 589}, {"su": 879, "le": 659}, {"su": 949, "le": 729}])
    analise_b = analisar_lote(itens_b, lojas_b, ParametrosSelecao(base_preco_final="B"))

    # Regra A: preço final = média arredondada; Regra B: preço da loja de menor total
    assert {l.item.id: l.preco_final_centavos for l in analise_a.linhas} == {"pa": 3430, "ca": 4207}
    assert {l.item.id: l.preco_final_centavos for l in analise_b.linhas} == {"su": 799, "le": 589}

    linhas_a, restricao_a = linhas_do_lote(analise_a, REGRAS, "Material", "Papelaria")
    linhas_b, restricao_b = linhas_do_lote(analise_b, REGRAS, "Alimentação", "Principal")
    assert restricao_a is None and restricao_b is not None
    calculo = calcular_mao_de_obra((400100, 500000, 600100), 44, 9150, meses=12)
    coordenador = linha_de_cargo("co", "Coordenador", "Recursos Humanos", calculo, REGRAS)

    # Teto montado a partir de uma solução conhecida: Caneta 11, Suco 21, 91,43 h
    teto = 3430 * 20 + 4207 * 11 + 799 * 21 + 589 * 20 + 12 * ((2273 * 9143 + 50) // 100)
    r = fechar_teto(ProblemaTeto(teto, materiais=(*linhas_a, *linhas_b), mao_de_obra=(coordenador,), lotes=(restricao_b,)))
    assert isinstance(r, SolucaoTeto), getattr(r, "mensagem", "")
    assert r.total_centavos == teto and r.verificacao_ok
