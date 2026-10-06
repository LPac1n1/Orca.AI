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


def test_caixa_pedida_e_unidade_achada_vira_ponto_para_revisar(tmp_path, monkeypatch):
    """Teste real de 05/10/2026: "Caixa Caneta Esferográfica Azul" foi orçada com uma caneta avulsa (não havia a caixa do mesmo produto em 3
    lojas) e o item ficou "em ordem". Agora a verificação aponta (S10, para revisar) enquanto as pesquisas forem da unidade."""
    from orcamento.calculo import verificar
    from orcamento.modelo import Projeto, RubricaMaterial, Subitem, Fonte, Evidencia
    from orcamento.produtos import identidade as ID
    from orcamento.regras import REGRAS
    avulsas = ['Caneta Esferográfica BPS Grip 1.0 Azul Pilot', 'Caneta Esferográfica Pilot BPS Grip 1.0', 'Caneta Esferográfica Azul Grip']
    caixas = ['Caneta Esferográfica Cristal Azul Caixa com 50 Bic', 'Caneta Bic Cristal Azul cx c/50', 'Caneta Cristal Azul Bic Dura+ Caixa com 50 Unidades']
    assert ID.embalagem_nao_atendida('Caixa Caneta Esferográfica Azul', avulsas) == 'caixa' and ID.embalagem_nao_atendida('Caixa Caneta Esferográfica Azul', caixas) is None
    assert ID.embalagem_nao_atendida('Caixa Caneta Esferográfica Azul', caixas[:2] + avulsas[:1]) == 'caixa'                 # basta um anúncio da unidade
    assert ID.embalagem_nao_atendida('Pacote de Lápis de Cor', ['Lápis de Cor 12 Cores Kit Escolar', 'Lápis de Cor Estojo 12', 'Kit Lápis de Cor']) is None
    assert ID.embalagem_nao_atendida('Caneta Esferográfica Azul', avulsas) is None                                             # não pediu embalagem
    assert ID.embalagem_nao_atendida('Caixa de Leite Integral', ['Leite Integral 1L', 'Leite UHT Integral 1L', 'Leite Integral Tetra Pak 1L']) is None   # por volume: é a embalagem normal
    assert ID.embalagem_nao_atendida('Caixa de Som', ['Caixa de Som JBL', 'Caixa de Som Bluetooth', 'Caixa de Som']) is None   # a "caixa" é o próprio produto
    assert ID.embalagem_nao_atendida('Caixa Caneta Esferográfica Azul', []) is None and 'S10' in REGRAS

    def projeto(produtos, nivel=0, original=None):
        f = lambda k: Fonte(nome=f'LOJA {k}', cnpj=('11.222.333/0001-81', '11.444.777/0001-61', '45.997.418/0001-53')[k], data_pesquisa='2026-10-05',
                            evidencia=Evidencia(arquivo='x.pdf', origem='pdf', sha256='a' * 64))
        s = Subitem(descricao='Caixa Caneta Esferográfica Azul' if not original else 'Caneta Esferográfica', qtd=1, precos=[805, 950, 1121], valor_plano=805, produtos=produtos,
                    fontes=[f(0), f(1), f(2)], nivel=nivel, descricao_original=original, confirmacao='descrição')
        return Projeto(nome='T', teto=100000, rubricas=[RubricaMaterial(item=1, descricao='Material de Escritório', meses=10, subitens=[s])])
    s10 = lambda p: [(a.gravidade, a.mensagem) for a in verificar(p) if a.regra == 'S10']
    achado = s10(projeto(avulsas))
    assert len(achado) == 1 and achado[0][0] == 'atencao' and 'o pedido é de caixa, mas a pesquisa achou a unidade avulsa' in achado[0][1] and 'Caixa com 50 unidades' in achado[0][1]
    assert s10(projeto(caixas)) == [] and s10(projeto([None, None, None])) == []                                              # com a caixa (ou ainda sem pesquisa): nada
    assert s10(projeto(avulsas, nivel=1, original='Caixa Caneta Esferográfica Azul')) == []                                   # troca declarada já é apontada pela S02


def test_valor_no_plano_depois_que_o_carrinho_muda_o_preco():
    """Teste real de 05/10/2026: a busca dizia R$ 5,09 e o carrinho da loja, R$ 5,29. O valor proposto (a média dos preços da busca, R$ 5,66)
    ficou no plano — nem o menor dos 3 preços finais, nem a média deles. Agora ele volta a ser um dos dois."""
    from orcamento.servico import valor_depois_do_comprovante as v
    from orcamento.regras import media, valores_do_plano
    assert media([509, 559, 629]) == 566 and valores_do_plano([529, 559, 629]) == [529, 572]
    assert v(566, [529, 559, 629]) == 572              # era a média da busca: passa a ser a média dos preços comprovados
    assert v(509, [529, 559, 629]) == 529              # era o menor da busca, e o menor subiu: passa a ser o novo menor
    assert v(332, [289, 339, 369]) == 332              # a média caiu para o valor proposto: fica
    assert v(360, [289, 339, 369]) == 332              # nunca acima da média
    assert v(None, [289, 339, 369]) == 332 and v(289, [289, 339, 369]) == 289
    assert v(300, [289, 339, 369]) == 332              # valor do meio do caminho: vai para a média
    assert v(300, [289, 339, 369], menor_ou_media=False) == 300 and v(566, [529, 559, 629], menor_ou_media=False) == 566   # órgão que aceita qualquer valor até a média
