"""O comprovante de um preço é a PÁGINA DO PRODUTO (decisão da OSC, 06/10/2026): um PDF por produto, em todas as lojas. O carrinho da loja
só entra quando é a única maneira — a página não mostra o preço que vale para a quantidade do plano (atacado "a partir de 3 un.", promoção,
limite por pedido: adendo de 08/10/2026), a página deu problema ou a loja barrou a página mas tem carrinho."""
import asyncio

import pytest

PDF = b'%PDF-1.4 comprovante de teste'


class Ctx:
    id = 0

    def __init__(self):
        self.avisos, self.fontes = [], []

    def progresso(self, *a, **k): pass
    def etapa(self, *a, **k): pass
    def fonte(self, *a, **k): self.fontes.append(a)
    def aviso(self, m): self.avisos.append(m)


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Banco numa pasta temporária e as lojas trocadas por dublês: `chamadas` guarda o que o sistema pediu a elas."""
    import orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    monkeypatch.setattr(dbm, 'PASTA_LOCAL', str(tmp_path / 'local'))
    from orcamento import servico
    from orcamento.produtos import evidencia as EV, lojas as L
    monkeypatch.setattr(servico, '_sem_preco', lambda pdf, centavos: None)          # (o PDF de teste não tem texto para conferir o preço)
    chamadas = dict(paginas=[], carrinhos=[], quantidades=[], pagina={}, na_quantidade={})

    async def pagina_produto(br, loja, url, rotulo, cep, preco=None, qtd=None):
        chamadas['paginas'].append((loja, url, rotulo, qtd))
        problema = chamadas['pagina'].get(url)
        return (None if problema == EV.BLOQUEIO else PDF), dict(capturado_em='2026-10-08T10:00:00-03:00', url=url, problema=problema, preco_pagina=None)

    async def carrinhos_vtex(br, loja, itens, cep, max_carrinhos=6):
        chamadas['carrinhos'].append((loja, [(i['sku'], i['qtd']) for i in itens]))
        return [dict(pdf=PDF, url=f'https://{loja}.exemplo/checkout/#/cart', capturado_em='2026-10-08T10:00:00-03:00', skus=[i['sku'] for i in itens],
                     precos={i['sku']: 1290 for i in itens}, problema=None)], {}

    async def na_quantidade(c, loja, x, qtd, cep):
        chamadas['quantidades'].append((loja, x['sku'], qtd))
        return chamadas['na_quantidade'].get(x['sku'], (x['preco'], qtd))
    monkeypatch.setattr(EV, 'pagina_produto', pagina_produto)
    monkeypatch.setattr(EV, 'carrinhos_vtex', carrinhos_vtex)
    monkeypatch.setattr(L, 'na_quantidade', na_quantidade)
    return chamadas


def _of(loja, sku, preco=1390):
    return dict(loja=loja, nome=f'Suco de Uva 1L {sku}', url=f'https://{loja}.exemplo/{sku}/p', sku=sku, seller='1', preco=preco)


def _comprovar(loja, pares, modo='pagina', bloqueadas=None):
    from orcamento import servico
    ctx = Ctx()
    return asyncio.run(servico._comprovar(None, 1, 10, loja, pares, '01001-000', ctx, bloqueadas=bloqueadas, modo=modo)), ctx


def test_comprovante_e_a_pagina_do_produto_em_loja_que_tem_carrinho(base):
    a, b = _of('atacadao', 'A'), _of('atacadao', 'B')
    out, _ = _comprovar('atacadao', [(dict(desc='Suco de Uva 1L', qtd=1), a), (dict(desc='Leite 1L', qtd=1), b)])
    assert base['carrinhos'] == [] and base['quantidades'] == []                       # 1 unidade: a página mostra o total; ninguém vai ao carrinho
    assert [(p[0], p[2], p[3]) for p in base['paginas']] == [('atacadao', 'Suco de Uva 1L', 1), ('atacadao', 'Leite 1L', 1)]
    for x in (a, b):
        r = out[('atacadao', x['url'])]
        assert r['problema'] is None and r['ev'].arquivo and r['ev'].url == x['url'] and r['ev'].origem == 'navegador' and not r.get('carrinho')


def test_carrinho_so_quando_o_preco_muda_com_a_quantidade(base):
    """20 sucos de uva: a loja cobra 12,90 a partir de 3 unidades e a página mostra 13,90 — o total da quantidade não pode ser visto na página."""
    atacado, normal, limite = _of('atacadao', 'ATACADO'), _of('atacadao', 'NORMAL'), _of('atacadao', 'LIMITE')
    base['na_quantidade'] = {'ATACADO': (1290, 20), 'LIMITE': (1390, 5)}                # a 3ª só vende 5 por pedido
    out, _ = _comprovar('atacadao', [(dict(desc='Suco de Uva 1L', qtd=20), atacado), (dict(desc='Suco de Maçã 1L', qtd=20), normal),
                                     (dict(desc='Suco de Laranja 1L', qtd=20), limite)])
    assert sorted(base['quantidades']) == [('atacadao', 'ATACADO', 20), ('atacadao', 'LIMITE', 20), ('atacadao', 'NORMAL', 20)]
    assert base['carrinhos'] == [('atacadao', [('ATACADO', 20), ('LIMITE', 20)])]       # só os dois em que a página não mostra o que vale
    assert [p[1] for p in base['paginas']] == [normal['url']] and base['paginas'][0][3] == 20   # o outro: página, com a quantidade na faixa
    r = out[('atacadao', atacado['url'])]
    assert r['carrinho'] and r['preco'] == 1290 and r['pelo_carrinho'] == 'o preço da loja muda com a quantidade' and r['ev'].url == atacado['url']
    assert not out[('atacadao', normal['url'])].get('carrinho') and out[('atacadao', normal['url'])]['problema'] is None


def test_pagina_com_problema_cai_no_carrinho_e_loja_barrada_na_pagina_nao_e_descartada(base):
    from orcamento import db
    from orcamento.produtos import evidencia as EV
    ruim, boa = _of('americanas', 'RUIM'), _of('americanas', 'BOA')
    base['pagina'] = {ruim['url']: 'o preço da pesquisa (R$ 13,90) não aparece na página'}
    out, _ = _comprovar('americanas', [(dict(desc='Suco', qtd=1), ruim), (dict(desc='Leite', qtd=1), boa)])
    assert base['carrinhos'] == [('americanas', [('RUIM', 1)])]                          # último recurso, só para o que a página não comprovou
    assert out[('americanas', ruim['url'])]['carrinho'] and out[('americanas', ruim['url'])]['problema'] is None
    assert not out[('americanas', boa['url'])].get('carrinho')
    # a loja pede verificação humana na PÁGINA, mas tem carrinho (que não passa por isso): não é descartada; hoje, vai direto ao carrinho
    base['carrinhos'].clear(); base['paginas'].clear()
    x1, x2 = _of('coop', 'X1'), _of('coop', 'X2')
    base['pagina'] = {x1['url']: EV.BLOQUEIO}
    bloqueadas = {}
    out, ctx = _comprovar('coop', [(dict(desc='Suco', qtd=1), x1), (dict(desc='Leite', qtd=1), x2)], bloqueadas=bloqueadas)
    assert bloqueadas == {} and 'coop' not in db.lojas_bloqueadas() and not ctx.avisos
    assert len(base['paginas']) == 1 and base['carrinhos'] == [('coop', [('X1', 1), ('X2', 1)])]
    assert all(out[('coop', x['url'])]['carrinho'] and out[('coop', x['url'])]['problema'] is None for x in (x1, x2))
    base['carrinhos'].clear(); base['paginas'].clear()
    _comprovar('coop', [(dict(desc='Café', qtd=1), _of('coop', 'X3'))])
    assert base['paginas'] == [] and base['carrinhos'] == [('coop', [('X3', 1)])]         # no mesmo dia: direto ao carrinho
    # loja SEM carrinho que pede verificação humana: descartada, como sempre (decisão da OSC: o sistema não resolve CAPTCHA)
    g = dict(loja='gimba', nome='Caneta', url='https://gimba.exemplo/caneta', preco=119)
    base['pagina'] = {g['url']: EV.BLOQUEIO}
    bloqueadas = {}
    out, ctx = _comprovar('gimba', [(dict(desc='Caneta', qtd=3), g)], bloqueadas=bloqueadas)
    assert bloqueadas == {'gimba': EV.BLOQUEIO} and 'gimba' in db.lojas_bloqueadas() and out[('gimba', g['url'])]['ev'] is None and 'verificação humana' in ctx.avisos[0]


def test_projeto_pode_preferir_o_carrinho_e_a_faixa_diz_a_quantidade_e_o_total(base):
    from orcamento.modelo import Config
    from orcamento.produtos import evidencia as EV
    assert Config().comprovante == 'pagina'
    x = _of('atacadao', 'A')
    out, _ = _comprovar('atacadao', [(dict(desc='Suco de Uva 1L', qtd=20), x)], modo='carrinho')
    assert base['carrinhos'] == [('atacadao', [('A', 20)])] and base['paginas'] == [] and out[('atacadao', x['url'])]['carrinho']
    # a faixa do alto do PDF: a página da loja mostra o preço de uma unidade; a quantidade do plano e o total ficam escritos na faixa
    f = EV.faixa_do_produto('atacadao', 'Suco de Uva 1L', '01001-000', '2026-10-08T10:00:00-03:00', 'https://loja.exemplo/p', 899, 20)
    assert f == 'PESQUISA DE PREÇO | Atacadão | Suco de Uva 1L | quantidade 20 × R$ 8,99 = R$ 179,80 | CEP 01001-000 | 2026-10-08T10:00:00-03:00 | https://loja.exemplo/p'
    assert '| quantidade 3 |' in EV.faixa_do_produto('gimba', 'Caneta', '01001-000', 'agora', 'u', None, 3) and 'quantidade' not in EV.faixa_do_produto('gimba', 'Caneta', '01001-000', 'agora', 'u')
    # "Exibir itens esgotados" é o rótulo de um filtro, não o estado do produto
    longa = 'Caneta Esferográfica Faber-Castell Trilux A partir de: R$ 2,50 Selecione a quantidade de cada um dos itens abaixo. Exibir itens esgotados. ' + 'descrição ' * 40
    assert EV.conferir_pagina(longa, [250]) is None and EV.conferir_pagina(longa.replace('Exibir itens esgotados', 'PRODUTO ESGOTADO'), [250]) == 'a página diz que o produto está indisponível'
