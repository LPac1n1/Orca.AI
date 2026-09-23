"""Cascata de correspondência 🟢🟡🔴 (docs/02 §7): regras uma a uma."""

import pytest

from orca.coleta import ler_vocabulario
from orca.correspondencia import Anuncio, Especificacao, Situacao, Vocabulario, comparar
from orca.dominio import OrigemCorrespondencia, StatusCorrespondencia

VERDE, AMARELO, VERMELHO = StatusCorrespondencia.VERDE, StatusCorrespondencia.AMARELO, StatusCorrespondencia.VERMELHO
EAN = "7891173023001"


@pytest.fixture(scope="module")
def vocabulario():
    return ler_vocabulario()


def _papel(**kw):
    return Especificacao("Papel sulfite A4 75g", "papel", "Chamex", apresentacao="pacote com 500 folhas", **kw)


def test_diferencas_so_de_texto_nao_impedem_verde(vocabulario):
    """Exemplo de docs/02 §7."""
    item = Especificacao("Chamex Papel Sulfite A4 75g – 500 fls", "papel", "Chamex")
    r = comparar(item, Anuncio("Papel Sulfite A4 75g Chamex 500 folhas"), vocabulario)
    assert r.status is VERDE and r.origem is OrigemCorrespondencia.ATRIBUTOS
    r = comparar(_papel(), Anuncio("Papel Sulfite A4, 75g, 210mmx297mm, Chamex - PT 500 FL", "Chamex"), vocabulario)
    assert r.status is VERDE


def test_mesmo_codigo_de_barras(vocabulario):
    r = comparar(_papel(ean=EAN), Anuncio("Resma Chamex", ean=EAN), vocabulario)
    assert (r.status, r.origem, r.motivos) == (VERDE, OrigemCorrespondencia.EAN, ("mesmo código de barras",))
    # GTIN-14 com zero à esquerda é o mesmo código
    assert comparar(_papel(ean=EAN), Anuncio("Resma", ean="0" + EAN), vocabulario).status is VERDE


def test_mesmo_codigo_mas_pagina_contradiz(vocabulario):
    r = comparar(_papel(ean=EAN), Anuncio("Papel Sulfite A4 75g Chamex 300 folhas", ean=EAN), vocabulario)
    assert r.status is AMARELO and "contradiz" in r.motivos[0] and "300 folhas" in r.motivos[0]


def test_codigos_diferentes_nunca_dao_verde(vocabulario):
    r = comparar(_papel(ean=EAN), Anuncio("Papel Sulfite A4 75g Chamex 500 folhas", ean="7891000100103"), vocabulario)
    assert r.status is AMARELO and "códigos de barras diferentes" in r.motivos[0]
    r = comparar(_papel(ean=EAN), Anuncio("Papel Sulfite A4 75g Chamex 300 folhas", ean="7891000100103"), vocabulario)
    assert r.status is VERMELHO


def test_marca(vocabulario):
    sem_marca = Especificacao("Papel sulfite A4 75g 500 folhas", "papel")
    r = comparar(sem_marca, Anuncio("Papel Sulfite A4 75g Chamex 500 folhas"), vocabulario)
    assert r.status is AMARELO and "o item não define a marca (D-17)" in r.motivos
    r = comparar(_papel(), Anuncio("Papel Sulfite A4 75g 500 folhas", marca="Report"), vocabulario)
    assert r.status is VERMELHO and "marca diferente: Chamex × Report" in r.motivos
    r = comparar(_papel(), Anuncio("Papel Sulfite A4 75g 500 folhas"), vocabulario)
    assert r.status is AMARELO and "a página não mostra a marca Chamex" in r.motivos
    tres = Especificacao("Café Três Corações Tradicional 500g", "alimento", "Três Corações")
    assert comparar(tres, Anuncio("Café 3 Corações Tradicional 500g"), vocabulario).status is VERDE


def test_medida_ausente_ou_so_na_pagina(vocabulario):
    r = comparar(_papel(), Anuncio("Papel Sulfite A4 Chamex 500 folhas"), vocabulario)
    assert r.status is AMARELO and "a página não informa: gramatura (75 g/m²)" in r.motivos
    r = comparar(Especificacao("Café Pilão Tradicional", "alimento", "Pilão"), Anuncio("Café Pilão Tradicional 500g"), vocabulario)
    assert r.status is AMARELO and "a página diz 500 g (conteúdo) e o item não define" in r.motivos


def test_mesmo_total_com_embalagem_diferente_fica_amarelo(vocabulario):
    item = Especificacao("Biscoito Marilan Leite 300g", "alimento", "Marilan")
    r = comparar(item, Anuncio("Biscoito Marilan Leite 3 x 100g"), vocabulario)
    assert r.status is AMARELO and any("mesmo total" in m for m in r.motivos)


def test_variantes_do_vocabulario(vocabulario):
    item = Especificacao("Café Pilão Tradicional Almofada 500g", "alimento", "Pilão")
    r = comparar(item, Anuncio("Café Pilão Extra Forte Vácuo 500g"), vocabulario)
    assert r.status is VERMELHO
    assert "variante diferente: “tradicional” × “extra forte”" in r.motivos
    assert "variante diferente: “almofada” × “vacuo”" in r.motivos
    r = comparar(item, Anuncio("Café Pilão Tradicional 500g"), vocabulario)
    assert r.status is AMARELO and "a página não diz se é almofada" in r.motivos


def test_valor_comum_nao_esconde_a_diferenca(vocabulario):
    """ "leite" aparece nos dois (é o produto), mas morango × ameixa decide."""
    item = Especificacao("Leite Fermentado Activia Morango 800g", "alimento", "Activia")
    r = comparar(item, Anuncio("Leite Fermentado Activia Ameixa 800g"), vocabulario)
    assert r.status is VERMELHO and "variante diferente: “morango” × “ameixa”" in r.motivos
    r = comparar(Especificacao("Suco Morango 1L", "bebida", "Del Valle"), Anuncio("Suco Del Valle Morango e Manga 1L"), vocabulario)
    assert r.status is AMARELO  # a página cita um sabor a mais: pode ser outro produto


def test_palavras_e_numeros_que_sobram(vocabulario):
    item = Especificacao("Café Pilão Tradicional 500g", "alimento", "Pilão")
    r = comparar(item, Anuncio("Café Pilão Tradicional Orgânico Premium 500g"), vocabulario)
    assert r.status is AMARELO
    item = Especificacao("Café Pilão 252 Graus 500g", "alimento", "Pilão")
    r = comparar(item, Anuncio("Café Pilão 500g"), vocabulario)
    assert r.status is AMARELO and any("252" in m for m in r.motivos)


def test_categoria_desconhecida_ou_servico(vocabulario):
    r = comparar(Especificacao("Coleira nylon", None, "Furacão"), Anuncio("Coleira Nylon Furacão"), vocabulario)
    assert r.status is AMARELO and "o item não tem categoria" in r.motivos[0]
    r = comparar(Especificacao("Coleira", "pet", "Furacão"), Anuncio("Coleira Furacão"), vocabulario)
    assert r.status is AMARELO and "sem atributos no catálogo" in r.motivos[0]
    servico = Especificacao("Sistema de gestão plano Prata", "servico", "OngFácil")
    r = comparar(servico, Anuncio("OngFácil Sistema de gestão plano Prata"), vocabulario)
    assert r.status is AMARELO and any("precisa ser conferido por uma pessoa" in m for m in r.motivos)
    com_escopo = Especificacao(
        "Sistema de gestão plano Prata", "servico", "OngFácil",
        atributos={"escopo": "sistema de gestão", "periodicidade": "mensal", "unidade_de_cobranca": "mensalidade"},
    )
    r = comparar(com_escopo, Anuncio("OngFácil Sistema de gestão plano Prata mensal, mensalidade"), vocabulario)
    assert r.status is VERDE


def test_modelo(vocabulario):
    item = Especificacao("Caneta esferográfica azul 1.0mm", "caneta", "BIC", modelo="Cristal", apresentacao="caixa com 50 un")
    r = comparar(item, Anuncio("Caneta Esferográfica BIC Cristal Azul 1.0mm Caixa com 50 un"), vocabulario)
    assert r.status is VERDE
    r = comparar(item, Anuncio("Caneta Esferográfica BIC Azul 1.0mm Caixa com 50 un"), vocabulario)
    assert r.status is AMARELO and "a página não mostra o modelo “Cristal”" in r.motivos
    r = comparar(item, Anuncio("Caneta Esferográfica BIC Cristal Preta 1.0mm Caixa com 50 un"), vocabulario)
    assert r.status is VERMELHO


def test_detalhe_de_cada_atributo(vocabulario):
    r = comparar(_papel(), Anuncio("Papel Sulfite A4, 75g, Chamex, 500 folhas"), vocabulario)
    situacoes = {c.atributo: c.situacao for c in r.atributos}
    assert situacoes["marca"] is Situacao.IGUAL and situacoes["gramatura"] is Situacao.IGUAL
    assert situacoes["folhas_por_pacote"] is Situacao.IGUAL and situacoes["formato"] is Situacao.IGUAL
    assert situacoes["modelo"] is Situacao.NAO_SE_APLICA


def test_vocabulario_de_dados_sem_sinonimos_usa_o_nome():
    v = Vocabulario.de_dados({
        "sempre": ["marca"], "categorias": {"teste": ["cor"]},
        "vocabulario": {"cor": {"cores": {"azul": None, "verde_agua": [], "preto": ["preto", "preta"]}}},
    })
    grupo = v.grupos_de("cor")[0]
    assert grupo.valores == {"azul": ("azul",), "verde_agua": ("verde agua",), "preto": ("preto", "preta")}
    assert v.atributos_da_categoria("Teste") == ("marca", "cor")
    assert v.atributos_da_categoria("outra") is None and v.atributos_da_categoria(None) is None
