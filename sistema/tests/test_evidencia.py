"""Conferência dos comprovantes (casos reais do teste da v0.3) e estoque do Tenda por filial."""
from orcamento.produtos.evidencia import conferir_pagina, preco_na_pagina, reais, _linha_tenda, preco_unitario_tenda
from orcamento.produtos.lojas import _tenda_disp

MENU = 'Departamentos Produtos Carrefour Bulnez Cupons Despensa ' * 10


def test_reais_e_preco_na_pagina():
    assert reais(1859) == '18,59' and reais(123456) == '1.234,56' and reais(5) == '0,05'
    assert preco_na_pagina('Sabão em Pó Tixan R$\xa018,59 un', 1859)
    assert not preco_na_pagina('R$ 118,59', 1859) and not preco_na_pagina('R$ 18,591', 1859)


def test_pagina_de_erro_do_carrefour_nao_vale():
    oops = MENU + 'Oops! Houve um problema inesperado. Tente recarregar a página para continuar. Voltar à Home' + ' rodapé' * 50
    assert conferir_pagina(oops, [229]) == 'a loja mostrou uma página de erro'


def test_preco_ausente_e_indisponivel():
    pagina = MENU + 'Detergente Líquido Limpol Neutro 500ml R$ 2,29 Adicionar ao carrinho' + ' descrição' * 40
    assert conferir_pagina(pagina, [229]) is None
    assert 'não aparece' in conferir_pagina(pagina, [249])
    tenda = MENU + 'Sabão em Pó Tixan Ypê Maciez 1,6Kg R$ 18,59 un Produto indisponível Adicionar a lista' + ' descrição' * 40
    assert 'indisponível' in conferir_pagina(tenda, [1859])
    carrinho = MENU + 'Subtotal R$ 106,20 Produtos Indisponíveis 1 de 1 INDISPONÍVEL Desinfetante Bak Ypê Lavanda 5L R$ 21,30' + ' x' * 200
    assert 'indisponível' in conferir_pagina(carrinho, [2130])


def test_tenda_estoque_da_filial_do_cep():
    maciez = dict(isAvailable=True, inventory=[dict(branchId='48', totalAvailable=0), dict(branchId='12', totalAvailable=400)])
    primavera = dict(isAvailable=True, inventory=[dict(branchId='48', totalAvailable=223)])
    assert _tenda_disp(maciez, '48') is False and _tenda_disp(primavera, '48') is True
    assert _tenda_disp(maciez, None) is True                                   # filial desconhecida: vale o "disponível" do site
    assert _tenda_disp(dict(isAvailable=False, inventory=[dict(branchId='48', totalAvailable=9)]), '48') is False


def test_linha_do_carrinho_do_tenda():
    linhas = [['Água Sanitária Ypê 5L', '1', 'Água Sanitária Ypê 5L R$ 15,49 un _ + R$ 15,49'],
              ['Sabão em Pó Tixan Ypê Primavera 1,6Kg', '1', 'Sabão em Pó Tixan Ypê Primavera 1,6Kg R$ 18,59 un _ + R$ 18,59']]
    assert _linha_tenda(linhas, 'Sabao em Po Tixan Ype Primavera 1,6Kg') is linhas[1]
    assert _linha_tenda(linhas, 'Detergente Ypê 500ml') is None


def test_preco_de_atacado_no_carrinho_do_tenda():
    assert preco_unitario_tenda('Sabão em Pó Tixan Ypê Primavera 1,6Kg R$ 18,59 un R$ 16,59 un _ 3 + R$ 49,77', 3) == 1659
    assert preco_unitario_tenda('Água Sanitária Ypê 5L R$ 15,49 un _ 5 + R$ 77,45', 5) == 1549
    assert preco_unitario_tenda('Água Sanitária Ypê 5L R$ 15,49 un _ 1 + R$ 15,49', 1) == 1549
    assert preco_unitario_tenda('Produto R$ 10,00 un _ 3 + R$ 31,00', 3) is None      # subtotal não fecha: não inventa preço


def test_bloqueio_da_loja():
    import pytest
    from orcamento.produtos.lojas import conferir_bloqueio, Bloqueada
    from orcamento.produtos.evidencia import BLOQUEIO
    desafio = 'Verificando se você é humano. Isso pode levar alguns segundos IP: 191.8.92.189 Ray ID: a41ad07ef8d3caf8'
    with pytest.raises(Bloqueada):
        conferir_bloqueio(desafio)
    with pytest.raises(Bloqueada):
        conferir_bloqueio('', 429)
    conferir_bloqueio('Nenhum produto encontrado para a sua busca')                     # busca vazia de verdade: não é bloqueio
    assert conferir_pagina(desafio, [2449]) == BLOQUEIO
    normal = MENU + 'Detergente R$ 2,29 Adicionar <script src="https://www.google.com/recaptcha/api.js"></script>' + ' x' * 200
    assert conferir_pagina(normal, [229]) is None                                       # reCAPTCHA de formulário não é bloqueio


def test_loja_bloqueada_sai_da_pesquisa(monkeypatch):
    import asyncio
    from orcamento import db
    from orcamento.produtos import cesta, lojas as L
    chamadas = []

    async def bloqueia(br, loja, q):
        chamadas.append(q)
        raise L.Bloqueada('a loja pediu verificação humana (CAPTCHA/anti-robô)')
    monkeypatch.setattr(L, 'render', bloqueia)
    monkeypatch.setattr(db, 'cache_ler', lambda k: None)
    monkeypatch.setattr(db, 'cache_gravar', lambda k, v: None)
    bloqueios = []
    monkeypatch.setattr(db, 'loja_bloquear', lambda l, m: bloqueios.append(l))
    m = cesta.Motor([dict(desc='Detergente 500mL', qtd=1)], ['carrefour', 'kalunga'], '03977-015')
    m.sem, m.br, m.c = asyncio.Semaphore(3), None, None

    async def duas():
        return await m._buscar('carrefour', 'detergente'), await m._buscar('carrefour', 'detergente 500ml')
    assert asyncio.run(duas()) == ([], [])
    assert chamadas == ['detergente']                      # depois do bloqueio, a loja não é mais acessada
    assert 'carrefour' in m.bloqueadas and bloqueios == ['carrefour']      # descartada por 30 dias (decisão da OSC)


def test_resposta_da_ia_dentro_de_lista():
    from orcamento.ia import _objeto
    assert _objeto([{'mesmo_produto': True, 'motivo': 'x'}]) == {'mesmo_produto': True, 'motivo': 'x'}
    assert _objeto([{'a': 1}, {'a': 2}]) == [{'a': 1}, {'a': 2}]          # várias respostas: não escolhe uma
    assert _objeto({'mesmo_produto': False}) == {'mesmo_produto': False}


def test_anuncio_indisponivel_hoje_nao_volta(monkeypatch, tmp_path):
    from orcamento import db
    from orcamento.produtos import cesta
    monkeypatch.setattr(db, 'PASTA_LOCAL', str(tmp_path))
    db.cache_gravar('indisp|tenda|https://t/produto/alcool', 'o produto não pôde ser adicionado')
    db.cache_gravar('busca|tenda|alcool', [])
    assert list(db.cache_prefixo('indisp|')) == ['indisp|tenda|https://t/produto/alcool']
    m = cesta.Motor([dict(desc='Álcool 1L', qtd=1)], ['tenda'], '03977-015')
    m.indisp_hoje = {k.split('|', 1)[1] for k in db.cache_prefixo('indisp|')}
    m._classificar('tenda', dict(nome='Álcool Líquido 46 Coperalcool 1L', preco=1230, disp=True, url='https://t/produto/alcool'))
    m._classificar('tenda', dict(nome='Álcool Líquido 46 Zulu 1L', preco=990, disp=True, url='https://t/produto/zulu'))
    assert [x['url'] for v in m.ofertas.values() for x in v] == ['https://t/produto/zulu']


def test_alternativa_usa_reserva_no_lugar_da_loja_bloqueada():
    from orcamento.servico import _lojas_utilizaveis
    of = lambda l: dict(loja=l, url=f'https://{l}/p', preco=100)
    alt = dict(ofertas=[of('carrefour'), of('tenda'), of('kalunga')], reservas=[of('gimba'), of('atacadao')])
    assert [x['loja'] for x in _lojas_utilizaveis(alt, {'carrefour': 'BLOQUEIO'}, {})] == ['tenda', 'kalunga', 'gimba']
    falhou = {('gimba', 'https://gimba/p'): dict(problema='página de erro')}
    assert [x['loja'] for x in _lojas_utilizaveis(alt, {'carrefour': 'BLOQUEIO'}, falhou)] == ['tenda', 'kalunga', 'atacadao']
    assert _lojas_utilizaveis(dict(alt, reservas=[]), {'carrefour': 'BLOQUEIO'}, {}) is None


def test_rubrica_de_servico_nao_vai_para_as_lojas():
    from orcamento.produtos.lojas import setor_da_rubrica
    assert setor_da_rubrica('Sistema de gestão de dados') == 'servico'
    assert setor_da_rubrica('Locação de equipamento de som') == 'servico'
    assert setor_da_rubrica('Material Pedagógico e Escritório') == 'papelaria'
    assert setor_da_rubrica('Limpeza + utensílios') == 'limpeza'
    assert setor_da_rubrica('Material esportivo') is None          # material sem setor: procura em todas as lojas


def test_carrinho_separa_item_com_limite_de_quantidade(monkeypatch):
    """Americanas no teste de 27/09: um item com limite por cliente invalidava o carrinho inteiro."""
    import asyncio
    from orcamento.produtos import evidencia as EV
    limite = {'agua': 12}

    async def carrinho(dom, itens, end):
        return 'of', {'items': [dict(id=i['sku'], availability='available', quantity=min(i['qtd'], limite.get(i['sku'], 99)), sellingPrice=100)
                                for i in itens]}

    async def pdf(br, loja, ofid, cep, precos):
        return b'%PDF', 'agora', 'url', None

    async def endereco(c, dom, cep):
        return {}
    monkeypatch.setattr(EV, '_um_carrinho_vtex', carrinho)
    monkeypatch.setattr(EV, '_pdf_carrinho_vtex', pdf)
    monkeypatch.setattr(EV, '_endereco_vtex', endereco)
    itens = [dict(sku='agua', seller='1', qtd=20, nome='Água de coco'), dict(sku='pao', seller='1', qtd=10, nome='Pão integral'),
             dict(sku='sabao', seller='1', qtd=3, nome='Sabão')]
    cs, indisp = asyncio.run(EV.carrinhos_vtex(None, 'americanas', itens, '03977-015'))
    assert [c['skus'] for c in cs] == [['pao', 'sabao']] and all(c['problema'] is None for c in cs)
    assert indisp == {'agua': 'a loja aceita no máximo 12 unidade(s) (plano: 20)'}


def test_consulta_sem_simbolos_que_as_lojas_recusam():
    from orcamento.produtos.lojas import consulta
    assert consulta('chips malu (malu chips)') == 'chips malu malu chips'
    assert consulta('Sabão em pó 1,6Kg') == 'Sabão em pó 1,6Kg' and consulta('grampo 26/6') == 'grampo 26/6'
    assert consulta("Hellmann's \"Tradicional\"") == "Hellmann's Tradicional"
