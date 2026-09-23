"""T-03 — Caso real: grade de 2026 com 14 itens apontados pela secretaria.

Com a Regra B (preço da loja de menor total, sem misturar lojas), o sistema precisa:
- escolher a mesma loja do Orçamento 1 da grade em cada lote;
- apontar exatamente os 14 itens da diligência;
- ao conferir a grade pronta, achar o erro na média unitária do Álcool 1L.
"""

from pathlib import Path

import pytest
import yaml

from orca.calculo import centavos_de_texto
from orca.dominio import normalizar_cnpj
from orca.selecao import (
    ItemLote,
    LinhaInformada,
    Loja,
    Oferta,
    ParametrosSelecao,
    SemTrio,
    analisar_lote,
    conferir_grade,
    trocar_loja,
)

CASO = yaml.safe_load((Path(__file__).parents[1] / "dados" / "casos" / "grade_real_2026.yaml").read_text(encoding="utf-8"))
REGRA_B = ParametrosSelecao()  # padrão: Regra B, média exata, 3 fontes


def _montar(lote):
    itens = [ItemLote(id=f"i{n}", nome=i["nome"], quantidade=i["qtd"]) for n, i in enumerate(lote["itens"])]
    lojas = []
    for posicao, chave in enumerate(lote["lojas"]):
        dados = CASO["lojas"][chave]
        ofertas = {
            item.id: Oferta(centavos_de_texto(bruto["precos"][posicao]))
            for item, bruto in zip(itens, lote["itens"], strict=True)
        }
        lojas.append(Loja(id=chave, nome=dados["nome"], cnpj=normalizar_cnpj(dados["cnpj"]), ofertas=ofertas))
    return itens, lojas


LOTES = {f"{l['rubrica']} / {l['nome']}": l for l in CASO["lotes"]}


@pytest.mark.parametrize("nome_lote", LOTES)
def test_orcamento_1_e_a_mesma_loja_da_grade(nome_lote):
    lote = LOTES[nome_lote]
    itens, lojas = _montar(lote)
    analise = analisar_lote(itens, lojas, REGRA_B)
    # O Orçamento 1 é a loja de menor total (D-26). A grade não ordenava os Orçamentos 2 e 3.
    assert analise.escolhida.id == lote["lojas"][0]
    assert {lc.loja.id for lc in analise.trio} == set(lote["lojas"])
    if "totais_informados" in lote:
        por_loja = {lc.loja.id: analise.total_do_periodo(k) for k, lc in enumerate(analise.trio)}
        assert [por_loja[chave] for chave in lote["lojas"]] == [centavos_de_texto(t) for t in lote["totais_informados"]]


def test_aponta_exatamente_os_14_itens_da_diligencia():
    apontados = []
    for lote in CASO["lotes"]:
        itens, lojas = _montar(lote)
        apontados += [v.item.nome for v in analisar_lote(itens, lojas, REGRA_B).violacoes]
    assert sorted(apontados) == sorted(CASO["diligencia"])
    assert len(apontados) == 14


def test_mensagem_da_violacao():
    itens, lojas = _montar(LOTES["Limpeza + utensílios / Limpeza"])
    mensagens = [v.mensagem for v in analisar_lote(itens, lojas, REGRA_B).violacoes]
    assert "Desinfetante 5L: R$ 24,49 na loja Carrefour Comércio e Indústria Ltda passa da média R$ 21,7933…" in mensagens


def test_conferencia_da_grade_pronta_acha_o_erro_do_alcool_e_os_14_itens():
    linhas = []
    for lote in CASO["lotes"]:
        for bruto in lote["itens"]:
            precos = tuple(centavos_de_texto(p) for p in bruto["precos"])
            linhas.append(
                LinhaInformada(
                    nome=bruto["nome"],
                    quantidade=bruto["qtd"],
                    precos=precos,
                    media_unitaria=centavos_de_texto(bruto["media_informada"]),
                    media_total=centavos_de_texto(bruto["media_total_informada"]) if "media_total_informada" in bruto else None,
                    preco_no_plano=precos[0],  # o plano usou o Orçamento 1
                )
            )
    divergencias = conferir_grade(linhas)
    erros_de_media = [d for d in divergencias if d.tipo != "acima_da_media"]
    assert [(d.item, d.tipo, d.informado, d.correto) for d in erros_de_media] == [
        ("Álcool 1L", "media_unitaria", 4597, 919)
    ]
    assert erros_de_media[0].mensagem == "Álcool 1L: média unitária informada R$ 45,97, o correto é R$ 9,19"
    assert sorted(d.item for d in divergencias if d.tipo == "acima_da_media") == sorted(CASO["diligencia"])


def test_media_exibida_da_o_mesmo_resultado_neste_caso():
    from orca.calculo import ComparacaoMedia

    p = ParametrosSelecao(comparar_com=ComparacaoMedia.EXIBIDA)
    apontados = []
    for lote in CASO["lotes"]:
        itens, lojas = _montar(lote)
        apontados += [v.item.nome for v in analisar_lote(itens, lojas, p).violacoes]
    assert sorted(apontados) == sorted(CASO["diligencia"])


def test_trocar_loja_sem_quarta_loja_pede_mais_pesquisa():
    """Com só 3 lojas pesquisadas, a Saída 2 não tem para onde ir: o sistema diz o que fazer."""
    itens, lojas = _montar(LOTES["Material Pedagógico e Escritório / Papelaria"])
    resultado = trocar_loja(itens, lojas, REGRA_B)
    assert not resultado.sucesso
    assert resultado.tentativas[0].removida.id == "lepok"
    assert isinstance(resultado.tentativas[0].resultado, SemTrio)
    assert "Pesquise mais lojas ou troque o produto" in resultado.mensagem
