"""Sugestões para o vocabulário a partir dos pares (D-65; Fase 2, etapa 13)."""

from orca.coleta import ler_atributos_dados
from orca.correspondencia import Par, Vocabulario, sugerir

VOCABULARIO = Vocabulario.de_dados(ler_atributos_dados())


def _par(a, b, rotulo, categoria, marca):
    return Par(a, b, rotulo, categoria, marca, marca)


def test_valor_novo_num_grupo_conhecido():
    [s] = sugerir(_par("Café Pilão moído 500g", "Café Pilão pilado 500g", "diferente", "alimento", "Pilão"), VOCABULARIO)
    assert s.tipo == "valor_exclusivo"
    assert s.mudancas == {"vocabulario": {"tipo": {"forma_do_cafe": {"pilado": ["pilado"]}}}}


def test_sinonimo_de_um_valor_conhecido():
    [s] = sugerir(_par("Café Pilão moído 500g", "Café Pilão moidinho 500g", "mesmo", "alimento", "Pilão"), VOCABULARIO)
    assert s.tipo == "sinonimo" and "moidinho" in s.mudancas["vocabulario"]["tipo"]["forma_do_cafe"]["moido"]


def test_atributo_que_a_categoria_nao_conferia():
    [s] = sugerir(_par("Pano de chão Scott azul", "Pano de chão Scott cinza", "diferente", "limpeza", "Scott"), VOCABULARIO)
    assert s.tipo == "atributo_na_categoria" and s.mudancas["categorias"]["limpeza"][-1] == "cor"


def test_grupo_novo_com_duas_palavras_desconhecidas():
    [s] = sugerir(_par("Luva Volk nitrílica M", "Luva Volk látex M", "diferente", "limpeza", "Volk"), VOCABULARIO)
    assert s.tipo == "grupo_novo"
    [(atributo, grupos)] = s.mudancas["vocabulario"].items()
    assert list(grupos.values())[0] == {"nitrilica": ["nitrilica"], "latex": ["latex"]}


def test_sem_sugestao_quando_o_sistema_ja_acerta_ou_o_caso_nao_e_claro():
    acerta = _par("Detergente Ypê neutro 500ml", "Detergente Ypê limão 500ml", "diferente", "limpeza", "Ypê")
    varias = _par("Esponja Scotch dupla face", "Esponja Scotch fibra verde", "diferente", "limpeza", "Scotch")
    sem_sabor = _par("Suco Del Valle 1L", "Suco Del Valle manga 1L", "diferente", "bebida", "Del Valle")
    assert sugerir(acerta, VOCABULARIO) == sugerir(varias, VOCABULARIO) == sugerir(sem_sabor, VOCABULARIO) == []
