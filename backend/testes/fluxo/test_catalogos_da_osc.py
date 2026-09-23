"""Camada da OSC nos catálogos: só a diferença é gravada, e a mescla devolve o que a OSC editou (D-66)."""

import copy

from orca.coleta import ler_atributos_dados, ler_catalogo_dados
from orca.fluxo.catalogos import diferenca_de_atributos, diferenca_de_lojas, mesclar_atributos, mesclar_lojas


def test_diferenca_e_mescla_de_atributos_voltam_ao_editado():
    base = ler_atributos_dados()
    editado = copy.deepcopy(base)
    assert diferenca_de_atributos(base, editado) == {}

    editado["categorias"]["brinquedo"] = ["cor"]  # categoria nova
    editado["categorias"].pop("servico")  # categoria retirada
    editado["categorias"]["papel"] = ["formato", "gramatura"]  # lista trocada
    cafe = editado["vocabulario"]["tipo"]["forma_do_cafe"]
    cafe["moido"].append("moidinho")  # sinônimo novo
    cafe.pop("cappuccino")  # valor retirado
    editado["vocabulario"]["tipo"].pop("feijao")  # grupo retirado
    editado["vocabulario"].setdefault("sabor", {})["sabor_do_suco"] = {"uva": ["uva"], "laranja": ["laranja"]}

    mudancas = diferenca_de_atributos(base, editado)
    assert mudancas["categorias"] == {"brinquedo": ["cor"], "servico": None, "papel": ["formato", "gramatura"]}
    assert mudancas["vocabulario"]["tipo"]["forma_do_cafe"] == {
        "moido": ["moido", "moida", "torrado e moido", "moidinho"], "cappuccino": None}
    assert mudancas["vocabulario"]["tipo"]["feijao"] is None
    assert mesclar_atributos(base, mudancas) == editado


def test_sistema_novo_chega_a_osc_no_que_ela_nao_mudou():
    antigo = ler_atributos_dados()
    editado = copy.deepcopy(antigo)
    editado["vocabulario"]["tipo"]["forma_do_cafe"]["moido"].append("moidinho")
    mudancas = diferenca_de_atributos(antigo, editado)
    novo = copy.deepcopy(antigo)  # versão nova do programa com um sinônimo a mais em outro valor
    novo["vocabulario"]["tipo"]["forma_do_cafe"]["graos"].append("grao inteiro")
    mesclado = mesclar_atributos(novo, mudancas)
    assert "moidinho" in mesclado["vocabulario"]["tipo"]["forma_do_cafe"]["moido"]
    assert "grao inteiro" in mesclado["vocabulario"]["tipo"]["forma_do_cafe"]["graos"]


def test_diferenca_de_lojas():
    base = ler_catalogo_dados()
    editado = copy.deepcopy(base)
    assert diferenca_de_lojas(base, editado) == {}
    editado["lojas"][0]["coleta"] = "C4"
    editado["fornecedores_servico"].append({"id": "contador", "nome": "Contador X", "dominio": "contadorx.com.br",
                                            "coleta": "proposta", "observacoes": ""})
    mudancas = diferenca_de_lojas(base, editado)
    assert [(l["id"], l["tipo"]) for l in mudancas["lojas"]] == [(base["lojas"][0]["id"], "loja"), ("contador", "fornecedor")]
    mesclado = mesclar_lojas(base, mudancas)
    assert next(l for l in mesclado["lojas"] if l["id"] == base["lojas"][0]["id"])["coleta"] == "C4"
    assert any(f["id"] == "contador" for f in mesclado["fornecedores_servico"])
