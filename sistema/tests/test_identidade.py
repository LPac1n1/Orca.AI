"""Casos-armadilha reais da Fase 1: o motor de identidade de produto precisa decidir igual ao protótipo validado."""
import pytest
from orcamento.produtos.identidade import compativel, nivel, identidade_nome, identidade, familia_padrao, unidades_emb, modelos

LIMPEZA = ['Água sanitária 5L', 'Desinfetante 5L', 'Sabão em pó 1,6Kg', 'Detergente 500mL', 'Álcool 1L', 'Sacos de Lixo 50L 50 Unidades']
PAPELARIA = ['Bloco de notas adesivas 4 Cores', 'Pasta sanfonada 12 Divisórias', 'Papel sulfite A4 500 Folhas', 'Grampeador de mesa 26/6',
             'Grampo 26/6 5000 Unidades', 'Perfurador 4 Furos', 'Lápis preto 4 Unidades', 'Clips 100 Unidades', 'Caneta esferográfica 50 Unidades']
ALIMENTACAO = ['Suco de uva 1L', 'Suco de laranja 900ml', 'Leite 1L', 'Café 500g', 'Café solúvel 100g', 'Água de coco 1L', 'Pão de forma 480g',
               'Pão de forma integral 400g', 'Bisnaguinha 300g', 'Manteiga com sal 200g', 'Geleia de morango 320g', 'Maionese 250g',
               'Sardinha com tomate 125g', 'Banana chips 100g']


@pytest.mark.parametrize('desc, nome, nv, esperado', [
    ('Manteiga com sal 200g', 'Manteiga President Com Sal 200g', 0, True),
    ('Manteiga com sal 200g', 'Manteiga Extra sem Sal Président 200g', 1, False),
    ('Álcool 1L', 'Enxaguante Bucal Listerine Sem Álcool 1L', 1, False),
    ('Caneta esferográfica 50 Unidades', 'Caneta esferográfica Cristal 1.0mm Azul caixa com 50 unidades - Bic', 0, True),
    ('Grampo 26/6 5000 Unidades', 'Grampo Galvanizado Bacchi 26/6 Caixa 5000 UN', 0, True),
    ('Pão de forma 480g', 'Pão de Forma Wickbold 500g', 1, True),
    ('Pão de forma integral 400g', 'Pão de Forma Tradicional Visconti 400g', 1, False),
    ('Banana chips 100g', 'Iogurte Maçã Banana 100g', 2, False),
    ('Banana chips 100g', 'Chips de Mandioca Yoki 50g', 2, True),
    ('Detergente 500mL', 'Detergente Ypê Neutro 500ml', 0, True),
    ('Sardinha com tomate 125g', 'Sardinha Gomes da Costa com Tomate 250g', 1, True),
    ('Água sanitária 5L', 'Kit 3 Água Sanitária Ypê 2L', 1, False),
    ('Sabão em pó 1,6Kg', 'Sabão Líquido Omo 3L', 1, False),
])
def test_compativel(desc, nome, nv, esperado):
    assert compativel(desc, nome, nv) == esperado


@pytest.mark.parametrize('desc, nome, cesta, esperado', [
    ('Café 500g', 'Café Solúvel 3 Corações 100g', ALIMENTACAO, None),            # é OUTRO item da cesta
    ('Café solúvel 100g', 'Café Solúvel 3 Corações 100g', ALIMENTACAO, 0),
    ('Pão de forma 480g', 'Pão de Forma Integral Wickbold 400g', ALIMENTACAO, None),
    ('Café 500g', 'Café Torrado e Moído Pilão 250g', ALIMENTACAO, 1),
    ('Clips 100 Unidades', 'Porta Objetos, Canetas, Clips e Lembrete Home Office', PAPELARIA, None),
    ('Grampo 26/6 5000 Unidades', 'Grampo trilho metalizado 80mm Acc PT 50 UN', PAPELARIA, None),
    ('Grampo 26/6 5000 Unidades', 'Grampo 26/6 Galvanizado Bacchi 3500 Unidades', PAPELARIA, 1),
    ('Grampo 26/6 5000 Unidades', 'Grampo p/grampeador 26/8 galvanizado Acc CX 5000 UN', PAPELARIA, None),   # 26/8 não serve no grampeador 26/6
    ('Detergente 500mL', 'Detergente Líquido Galão Limpol Neutro 5L', LIMPEZA, None),                        # 10 vezes o tamanho
    ('Caneta esferográfica 50 Unidades', 'Caneta Esferográfica Retrátil BIC 4 Cores Clássica', PAPELARIA, None),
    ('Lápis preto 4 Unidades', 'Lápis de Cor Sextavado BIC Evolution, 12 Cores', PAPELARIA, None),
    ('Suco de uva 1L', 'Suco Integral de Maçã Refrigerado Natural One 900ml', ALIMENTACAO, 2),
    ('Perfurador 4 Furos', 'Perfurador 2 Furos Tilibra 20 Folhas', PAPELARIA, 2),
    ('Álcool 1L', 'Enxaguante Bucal Zero Álcool Melancia Listerine 1L', LIMPEZA, None),
    ('Álcool 1L', 'Álcool Líquido 70% Tupi 1L', LIMPEZA, 0),
    ('Álcool 1L', 'Álcool em Gel Higienizante Giovanna Baby 60g', LIMPEZA, None),                            # outra forma (g × mL)
    ('Manteiga com sal 200g', 'Manteiga Aviação sem Sal 200g', ALIMENTACAO, None),
    ('Sacos de Lixo 50L 50 Unidades', 'Saco para Lixo Dover Roll 50L 50 Unidades', LIMPEZA, 0),
])
def test_nivel_na_cesta(desc, nome, cesta, esperado):
    assert nivel(desc, nome, cesta) == esperado


@pytest.mark.parametrize('a, b, esperado', [
    ('Clips galvanizado NR 1/0 (0) com 100 unidades - Bacchi', 'Clips Galvanizado Bacchi Nº0 CX C/100 UN', 'Y'),
    ('Clips galvanizado NR 1 com 100 unidades - Bacchi', 'Clips Galvanizado Bacchi Nº2 CX C/100 UN', 'R'),
    ('Clips para Papel 2/0 Bacchi 100 Unidades', 'Clips Colorido Bacchi Nº2/0 CX C/100 UN', 'R'),
    ('Clips galvanizado NR 2/0 (00) com 100 unidades - Bacchi', 'Clips Bacchi Nº2/0 Galvanizado Linha Leve CX C/100 UN', 'R'),
    ('Manteiga com Sal Aviação 200g', 'Manteiga Aviação Com sal 200g', 'Y'),
    ('Detergente Ypê Neutro 500ml', 'Detergente Ypê 500ml', 'R'),
    ('Grampo 26/6 Galvanizado Cx 5000 un Bacchi', 'Grampo Galvanizado 26/6 5000 Unidades - Bacchi', 'Y'),
    ('Caneta esferográfica Cristal 1.0mm Azul caixa com 50 unidades - BIC', 'Caneta Esferográfica BIC Cristal Azul CX C/50 UN', 'Y'),
    ('Pasta Sanfonada A4 12 Divisórias Cristal Dello', 'Pasta Sanfonada Ofício 12 Divisórias Fumê Dello', 'R'),
    ('Clips galvanizado NR 1 com 100 unidades - Bacchi', 'Clips galvanizado NR 1 com 100 unidades - ACC', 'R'),     # marca diferente
])
def test_mesmo_produto_pela_descricao(a, b, esperado):
    assert identidade_nome(dict(nome=a), dict(nome=b), 'x') == esperado


def test_titulo_completo_resolve_variante_omitida():
    tenda = dict(nome='Saco Lixo Reforçado Rolo Preto Embalixo 50L 5', titulo='Saco para Lixo Reforçado 50 Litros Embalixo 50 unidades')
    assert identidade_nome(tenda, dict(nome='Saco de Lixo Embalixo Reforçado 50L 50 un'), 'Sacos de Lixo 50L 50 Unidades') == 'Y'
    assert identidade_nome(tenda, dict(nome='Saco de Lixo Embalixo 50L 50 un'), 'Sacos de Lixo 50L 50 Unidades') == 'R'


def test_ean_igual_com_embalagem_diferente():
    avulsa = dict(nome='Caneta Esferográfica BIC Escrita Média Cristal', ean='70330143395')
    pacote = dict(nome='Caneta esferográfica Cristal 1.0 Azul com 4 unidades', ean='070330143395')
    assert identidade(avulsa, pacote, 'x') == 'R'
    assert identidade(dict(nome='Papel Sulfite A4 Chamex PT 500 FL', ean='7891173023001'),
                      dict(nome='Papel Sulfite Chamex A4 Resma 500 Folhas', ean='7891173023001'), 'x') == 'G'


def test_unidades_e_modelos():
    assert unidades_emb('Papel sulfite caixa com 500 folhas') is None
    assert unidades_emb('Caneta C/ 50') == 50 and unidades_emb('Grampo cx 5000 un') == 5000
    assert modelos('Clips NR 1/0 (0)') == {'1/0'} and modelos('Clips Nº0') == {'1/0'}


def test_descricoes_do_plano_real():
    # textos exatos do Plano de Trabalho do Parecer 8
    assert familia_padrao('Folha sulfite 500 Folhas') == 'papel sulfite'
    assert compativel('Folha sulfite 500 Folhas', 'Papel Sulfite Chamex A4 Resma 500 Folhas', 0)
    assert compativel('Sucos de laranja 900ml', 'Suco Natural One Refrigerado Laranja 900ml', 0)


def test_mesmo_ean_com_variante_em_conflito_nao_vale():
    a = dict(nome='Detergente Líquido Limpol Limão 500ml', ean='7891022638004')
    b = dict(nome='Detergente Líquido Limpol Neutro 500ml', ean='7891022638004')
    assert identidade(a, b, 'Detergente 500mL') == 'R'
    c = dict(nome='Detergente Líquido com Glicerina Neutro Limpol Squeeze 500ml', ean='7891022638004')
    assert identidade(b, c, 'Detergente 500mL') == 'G'


def test_perda_de_4_cores_fica_registrada():
    from orcamento.produtos.identidade import distancia
    of = lambda n, ean=None: dict(nome=n, ean=ean, preco=100)
    g = dict(por_loja=dict(a=of('Bloco Post-It 45 Folhas Rosa', '7891040120000'), b=of('Bloco De Notas Adesivas Post-it 3M Rosa 76mm X 76mm 45 Folhas'),
                           c=of('Bloco De Notas Adesivas Post-it 3M Rosa 76mm X 76mm 45 Folhas')))
    d, perdidos = distancia('Bloco de notas 4 Cores', g, 2, ('a', 'b', 'c'))
    assert perdidos == ['4 cores']                    # "notas" está nos outros anúncios do mesmo produto
    g4 = dict(por_loja={k: dict(v, nome=v['nome'].replace('Rosa', '4 Cores')) for k, v in g['por_loja'].items()})
    assert distancia('Bloco de notas 4 Cores', g4, 0, ('a', 'b', 'c'))[1] == []


def test_tamanho_do_grampo_faz_parte_da_identidade():
    """O plano real pede "Grampo 5000 Unidades" (sem o tamanho): anúncios de tamanhos diferentes não podem virar o mesmo produto."""
    from orcamento.produtos.identidade import tamanhos
    assert tamanhos('Grampo Galvanizado Bacchi Enak 08 23/08 Caixa 5000 UN') == {'23/8'} and tamanhos('Clips 2/0 Bacchi') == set()
    a = dict(nome='Grampo galvanizado 26/6 - com 5000 unidades - Bacchi')
    assert identidade_nome(a, dict(nome='Grampo Galvanizado Bacchi 26/6 Caixa 5000 UN'), 'Grampo 5000 Unidades') == 'Y'
    assert identidade_nome(a, dict(nome='Grampo 26/6 Galvanizado Bacchi 5000 Unidades', marca='Bacchi'), 'Grampo 5000 Unidades') == 'Y'
    assert identidade_nome(a, dict(nome='Grampo Galvanizado Bacchi 24/6 Caixa 5000 UN'), 'Grampo 5000 Unidades') == 'R'
    assert identidade_nome(a, dict(nome='Grampo Galvanizado Bacchi 9/14 Caixa 5000 UN'), 'Grampo 5000 Unidades') == 'R'
    assert identidade_nome(a, dict(nome='Grampo Galvanizado Bacchi Caixa 5000 UN'), 'Grampo 5000 Unidades') == 'R'      # sem o tamanho: não confirma
