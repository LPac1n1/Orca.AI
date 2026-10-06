"""Lojas da pesquisa de preços (05/10/2026): lojas novas sem bloqueio, só o que a própria loja vende e o balão de CEP fora do comprovante."""
import asyncio

import pytest


def test_toda_loja_tem_cnpj_do_proprio_site():
    """Nenhum CNPJ é inventado: cada loja tem o CNPJ publicado no site dela (ou em grade já aceita), com dígito verificador certo. As lojas de
    05/10/2026 entraram depois de sondagem real: busca aberta, entrega em São Paulo, CNPJ no rodapé e página que abre sem verificação humana."""
    from orcamento.produtos import lojas as L
    from orcamento.regras import cnpj_dv_ok
    for k, v in L.LOJAS.items():
        assert k in L.CNPJ_LOJAS, k
        cnpj, razao, origem = L.CNPJ_LOJAS[k]
        assert cnpj_dv_ok(cnpj) and razao and origem, k
        assert v['setores'] <= {'alimentacao', 'limpeza', 'papelaria'} and v['dominio'] and v['nome'], k
    novas = ['mambo', 'giga', 'casaevideo', 'telhanorte', 'drogal', 'paguemenos']
    assert list(L.LOJAS)[-6:] == novas and all(L.LOJAS[k]['plataforma'] == 'vtex' and L.LOJAS[k]['carrinho'] for k in novas)
    assert 'mambo' in L.lojas_para('alimentacao', bloqueadas={}) and 'giga' in L.lojas_para('papelaria', bloqueadas={}) and 'telhanorte' in L.lojas_para('limpeza', bloqueadas={})
    assert 'telhanorte' not in L.lojas_para('alimentacao', bloqueadas={}) and 'mambo' not in L.lojas_para('alimentacao', bloqueadas={'mambo': 'x'})
    raizes = [L.raiz(k) for k in L.LOJAS]
    assert len(set(raizes)) == len(raizes) - 1 and L.raiz('paodeacucar') == L.raiz('extra')      # só o Pão de Açúcar e o Extra são da mesma empresa


def test_vtex_so_o_que_a_propria_loja_vende_e_link_publico():
    """Em site com marketplace (Americanas, Casa & Video, Pague Menos), a oferta de outro vendedor é de OUTRA empresa: o CNPJ da pesquisa não
    seria o dela. Só entra o que o vendedor "1" (a loja dona do site) vende. E o link do produto é sempre o do domínio público da loja."""
    from orcamento.produtos import lojas as L
    oferta = lambda preco, qtd: dict(Price=preco, AvailableQuantity=qtd)
    produtos = [
        dict(productName='Papel Sulfite A4', brand='Chamex', link='https://casaevideonewio.vtexcommercestable.com.br/papel-sulfite-a4/p', linkText='papel-sulfite-a4',
             items=[dict(itemId='10', ean='7891173023247', name='x', sellers=[dict(sellerId='CV021', sellerName='OUTRA LOJA', sellerDefault=True, commertialOffer=oferta(8.0, 50)),
                                                                             dict(sellerId='1', sellerName='Casa e Video', sellerDefault=False, commertialOffer=oferta(9.99, 3))])]),
        dict(productName='Caneta Azul', brand='Bic', link='https://www.casaevideo.com.br/caneta-azul/p', linkText='caneta-azul',
             items=[dict(itemId='20', ean='70330144125', name='x', sellers=[dict(sellerId='CV260', sellerName='SHOPHUB', sellerDefault=True, commertialOffer=oferta(2.0, 9))])]),
        dict(productName='Lápis', brand='Bic', link='https://www.casaevideo.com.br/lapis/p', linkText='lapis',
             items=[dict(itemId='30', ean='70330428584', name='x', sellers=[dict(sellerId='1', sellerName='Casa e Video', sellerDefault=True, commertialOffer=oferta(10.79, 0))])]),
    ]

    class _Resp:
        status_code, text = 200, '[...]'
        json = staticmethod(lambda: produtos)

    class _Cliente:
        async def get(self, url, **k):
            assert url.startswith('https://www.casaevideo.com.br/api/catalog_system/pub/products/search?ft=papel')
            return _Resp()
    out = asyncio.run(L.vtex(_Cliente(), 'casaevideo', 'papel'))
    assert [(o['nome'], o['seller'], o['vendedor'], o['preco']) for o in out] == [('Papel Sulfite A4', '1', 'Casa e Video', 999), ('Lápis', '1', 'Casa e Video', 1079)]
    assert [o['url'] for o in out] == ['https://www.casaevideo.com.br/papel-sulfite-a4/p', 'https://www.casaevideo.com.br/lapis/p']
    assert L._link_vtex('www.x.com.br', dict(link='https://www.x.com.br/a/p', linkText='a')) == 'https://www.x.com.br/a/p' and L._link_vtex('www.x.com.br', {}) is None


def test_balao_de_cep_e_ocultado_antes_do_pdf():
    """O balão "Informe seu CEP" preso ao cabeçalho cobria o nome do produto no comprovante (Casa & Video). Ele é OCULTADO — nada é clicado —
    e o campo de frete da própria página, que não está por cima de nada, e o bloco com o preço ficam."""
    pw = pytest.importorskip('playwright.async_api')
    from orcamento.produtos import evidencia as EV
    html = '''<body style="margin:0"><header style="height:60px">LOJA</header>
      <div id="balao" style="position:absolute;top:110px;left:250px;width:160px;z-index:9;background:#fff">Informe seu CEP para ver ofertas exclusivas na sua região
        <input placeholder="00000-000"><button>Salvar</button></div>
      <h1>Papel A4 Chamequinho 100 Folhas Rosa Chamex</h1>
      <div id="preco" style="position:absolute;top:300px;left:20px">R$ 9,99 no PIX <input placeholder="Digite seu CEP"></div>
      <div id="frete">Consultar frete e prazo <input placeholder="Digite seu CEP"></div></body>'''

    async def roda():
        async with pw.async_playwright() as p:
            br = await p.chromium.launch(headless=True)
            try:
                pg = await br.new_page(viewport={'width': 1280, 'height': 900})
                await pg.set_content(html)
                await EV.limpar(pg, ['R$ 9,99'])
                return await pg.evaluate("['balao','preco','frete'].map(i => { const e = document.getElementById(i); return !!e && getComputedStyle(e).display !== 'none'; })")
            finally:
                await br.close()
    try:
        visiveis = asyncio.run(roda())
    except Exception as e:   # computador sem o navegador do sistema instalado
        pytest.skip(f'navegador indisponível: {type(e).__name__}')
    assert visiveis == [False, True, True]
