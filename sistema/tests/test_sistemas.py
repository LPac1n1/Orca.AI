"""Rubricas de sistema (decisões da OSC de 27/09 e 01/10/2026): 3 sistemas diferentes; o plano é o que está de acordo com as ferramentas de
referência (não o mais barato); proposta em PDF sem link vale como comprovante. Textos reais das páginas de preços (01/10/2026)."""
import asyncio

import pytest

from orcamento import db, ia, servico, sistemas as S
from orcamento.modelo import Projeto, RubricaMaterial, Subitem, Fonte, Evidencia
from orcamento.sistemas import planos, com_preco_publico, sob_consulta, preco_no_texto, escopo_do_texto

ANY3 = ('Escolha o plano que melhor atende as necessidades da sua instituição! GRÁTIS R$ 0,00 por mês* 50 Associados 0 Filiais 1 Proj '
        'tas a Pagar/Receber por mês 100 MB Espaço em disco Instalação Gratuita CRIAR CONTA BÁSICO R$ 95,00 R$ 79,90 por mês* 100 Associados 0 Fili '
        'CRIAR CONTA AVANÇADO R$ 239,00 R$ 199,90 por mês* 200 Associados 1 Fil CRIAR CONTA PREMIUM R$ 599,00 R$ 499,90 por mês* 1000 Associados')
ECONOMATO = ('Mensal Anual Básico Receita anual de até R$ 1 milhão. R$ 197/mês Conversar sobre o plano Intermediário Receita anual entre R$ 1 milhão e '
             'R$ 4 milhões. R$ 297/mês Conversar Profissional Receita anual entre R$ 4 milhões e R$ 6 milhões. R$ 627/mês Premium Receita anual superior '
             'a R$ 6 milhões. A partir de\nR$ 990/mês Conversar. PIX sem tarifa adicional, boletos de R$ 1,50 a R$ 3,00')
ONGSYS = ('INICIANTE\nIdeal para entidades que precisam organizar o financeiro de seus projetos\nVeja o que está incluso\nR$399 R$299/mês\nContratar\n'
          'RECOMENDADO\nPROFISSIONAL\nPara entidades que precisam de controle, velocidade e automação\nR$590 R$499/mês\nContratar\nAVANÇADO\n'
          'Para Organizações Sociais\na partir de R$899/mês\nContratar')
ONGFACIL = 'Valores de\nAssinatura mensal:\nGRATUITO\nR$ 0,00\n \nPRATA\nR$ 320,00\n/mês\nOURO\nR$ 490,00\n/mês'
PROPOSTA = """N º 0 1 0 5 2 0 2 5
PROPOSTA COMERCIAL
CONFIDENCIAL PARA:
CENTRO DE PROMOÇÃO E INCLUSÃO SOCIAL 26 DE JULHO
03.645.949/0001-37
ESCOPO DO SISTEMA FERRACIO ONG
Módulo: Controle Usuários atendidos
1.1 - Cadastro atendidos e responsáveis; (ficha de cadastro, ficha de saúde, ficha de
prosseguimentos, visita domiciliar);
1.2 - Controle de documentos dos atendidos; (RG, CPF, Certidão Nascimento, etc);
ESCOPO DO SISTEMA FERRACIO ONG
Módulo: Controle Treinamento
2.1 - Controle de frequência por sala;
ESCOPO DO SISTEMA FERRACIO ONG
Módulo: Pesquisa
3.1 - Pesquisa online; (através de link que pode ser enviado por whatsapp)
3.2 - Relatório com gráficos;
ESCOPO DO SISTEMA FERRACIO ONG
Custo para utilização do sistema:
Plano Mensal: R$ 270,92 mês;
F&D SOLUTIONS
CNPJ: 42.274.849/0001-37
"""


def test_planos_das_paginas():
    assert planos(ANY3) == [('Básico', 7990), ('Avançado', 19990), ('Premium', 49990)]       # o plano grátis não conta
    assert planos(ECONOMATO)[:2] == [('Básico', 19700), ('Intermediário', 29700)]
    assert planos(ONGSYS) == [('Iniciante', 29900), ('Profissional', 49900), ('Avançado', 89900)]   # vale o preço atual, não o riscado
    assert planos(ONGFACIL) == [('Prata', 32000), ('Ouro', 49000)]                                    # tabela que fica num quadro da página


def test_plano_a_partir_de_nao_tem_preco_definido():
    assert planos(ONGSYS, a_partir=False) == [('Iniciante', 29900), ('Profissional', 49900)]
    assert [n for n, _ in planos(ECONOMATO, a_partir=False)] == ['Básico', 'Intermediário', 'Profissional']


def test_preco_no_texto():
    assert preco_no_texto('R$399 R$299/mês Contratar', 29900)
    assert preco_no_texto('Plano Mensal: R$ 270,92 mês;', 27092)
    assert preco_no_texto('OURO R$ 490,00 /mês', 49000)
    assert preco_no_texto('R$ 1.250,00', 125000) and preco_no_texto('R$ 1250', 125000)
    assert not preco_no_texto('R$ 1299/mês', 29900) and not preco_no_texto('R$ 299,90', 29900)


def test_ferramentas_de_referencia_lidas_da_proposta():
    esc = escopo_do_texto(PROPOSTA).splitlines()
    assert esc[0] == 'Módulo: Controle Usuários atendidos'
    assert esc[1] == '1.1 - Cadastro atendidos e responsáveis; (ficha de cadastro, ficha de saúde, ficha de prosseguimentos, visita domiciliar);'
    assert 'Módulo: Pesquisa' in esc and '3.2 - Relatório com gráficos;' in esc
    assert not any('270,92' in l or 'CNPJ' in l or 'ESCOPO' in l for l in esc)
    assert escopo_do_texto('Proposta sem módulos nem itens numerados') == ''


def test_fornecedores():
    assert [f['chave'] for f in com_preco_publico()] == ['ongsys', 'ongfacil', 'any3', 'economato']   # primeiro os do último orçamento
    assert all(f['cnpj'] and f['razao'] for f in com_preco_publico())
    assert {'fdsolutions', 'hyb', 'auditus'} == {f['chave'] for f in sob_consulta()}
    assert S.do_cnpj('42.274.849/0001-01')['chave'] == 'fdsolutions'


# ---------------------------------------------------------------- pesquisa sem link (proposta em PDF)
def _pdf(texto):
    import pymupdf
    d = pymupdf.open(); pg = d.new_page()
    pg.insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto, fontsize=9)
    return d.tobytes()


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'PASTA_DADOS', str(tmp_path))
    return tmp_path


def _projeto(digitadas=False):
    """A OSC deixou a cotação 1 (F&D). digitadas=True: deixou também as outras duas, digitadas (sem PDF)."""
    fs = [Fonte(nome='F&D Solutions Ltda', cnpj='42.274.849/0001-01', data_pesquisa='2026-03-26')]
    fs += ([Fonte(nome='Ongsys Sistemas Ltda', cnpj='29.335.055/0001-34', data_pesquisa='2026-03-26'), Fonte(nome='Instituto Ekloos', cnpj='11.285.430/0001-13',
                                                                                                           data_pesquisa='2026-03-26')] if digitadas else [Fonte(), Fonte()])
    r = RubricaMaterial(item=13, descricao='Sistema de gestão de dados', meses=12, fontes=fs,
                        subitens=[Subitem(descricao='Sistema de gestão de dados (mensal)', qtd=1, precos=[27092, 29900, 49000] if digitadas else [27092, None, None],
                                          valor_plano=35331)])
    return Projeto(nome='Teste', teto=10_000_000, rubricas=[r])


def test_comprovante_sem_link_e_aceito():
    ok = servico.comprovante_no_formato
    assert ok(Evidencia(arquivo='projetos/1/evidencias/ab_proposta.pdf', sha256='a' * 64, url=None, origem='pdf'))        # proposta em PDF, sem link
    assert ok(Evidencia(arquivo='projetos/1/evidencias/ab_produto_coop_item9.pdf', sha256='a' * 64, url='https://www.coopsupermercado.com.br/suco/p'))
    assert not ok(Evidencia(arquivo='projetos/1/evidencias/ab_x.pdf', sha256='a' * 64, url='https://www.coopsupermercado.com.br/checkout/#/cart'))   # abre um carrinho vazio
    assert not ok(Evidencia(arquivo='projetos/1/evidencias/ab_carrinho_coop_item9.pdf', sha256='a' * 64, url='https://www.coopsupermercado.com.br/suco/p'))   # PDF antigo: vários itens
    assert not ok(Evidencia(url='https://x'))                                                                               # sem PDF


def test_anexar_pdf_sem_link(dados):
    p = _projeto(); pid = db.criar(p); r = p.rubricas[0]
    with pytest.raises(ValueError):
        servico.anexar_pdf(p, pid, r, 0, 0, 'proposta.docx', b'PK nao e pdf')
    msg = servico.anexar_pdf(p, pid, r, 0, 0, 'F&D Solutions.pdf', _pdf(PROPOSTA))
    s = r.subitens[0]
    ev = s.fontes[0].evidencia
    assert len(s.fontes) == 3 and ev.arquivo and ev.sha256 and ev.url is None and ev.origem == 'pdf'      # o subitem ganhou as suas 3 pesquisas
    assert s.fontes[0].cnpj == '42.274.849/0001-01' and s.precos[0] == 27092                               # nada é mudado pelo PDF
    assert 'sem link' in msg and 'R$ 270,92 aparece no PDF' in msg
    assert '42.274.849/0001-37' in msg and 'dígito verificador inválido' in msg                           # o CNPJ impresso na proposta tem erro
    assert r.referencia.startswith('Módulo: Controle Usuários atendidos') and 'ferramentas de referência lidas' in msg
    assert servico.comprovante_no_formato(ev) and servico.anexada(s.fontes[0])
    assert r.fontes[0].evidencia.arquivo is None                                                           # as fontes da rubrica não mudam


class _Ctx:
    id = None

    def __init__(self):
        self.avisos, self.fontes = [], []

    def progresso(self, *a, **k):
        pass

    def aviso(self, m):
        self.avisos.append(m)

    def fonte(self, *a):
        self.fontes.append(a)


class _PW:
    """Navegador de mentira (a página de preços vem de EV.pagina, trocada no teste)."""
    chromium = None

    async def __aenter__(self):
        class _Br:
            async def close(self):
                pass

        class _Ch:
            async def launch(self):
                return _Br()
        self.chromium = _Ch()
        return self

    async def __aexit__(self, *a):
        return False


PAGINAS = {'https://site.ongsys.com.br/precos': ONGSYS, 'https://www.ongfacil.org.br/registre-se': ONGFACIL,
           'http://www.any3.com.br/Any3-Gestao-Planos.aspx': ANY3, 'https://economato.com.br/planos/': ECONOMATO}


@pytest.fixture
def paginas(monkeypatch):
    import playwright.async_api
    from orcamento import cnpj_base
    from orcamento.produtos import evidencia as EV

    async def pagina(br, url, faixa, preco=None, completa=False):
        assert completa                                                  # página inteira: tabelas que só carregam ao rolar
        return _pdf(PAGINAS[url]), dict(capturado_em='2026-10-01T10:00:00-03:00', problema=None, texto=PAGINAS[url])
    monkeypatch.setattr(EV, 'pagina', pagina)
    monkeypatch.setattr(playwright.async_api, 'async_playwright', lambda: _PW())
    monkeypatch.setattr(cnpj_base, 'por_cnpj', lambda c: dict(situacao='ATIVA'))
    monkeypatch.setattr(ia, 'disponivel', lambda: True)
    # o que a IA responde para cada sistema: {nº da ferramenta de referência: (recurso da página, planos que o incluem)}
    # ferramentas da PROPOSTA de teste: 1 cadastro de atendidos · 2 documentos · 3 frequência · 4 pesquisa online · 5 relatório com gráficos
    mapas = {'Ongsys': {5: ('Dashboards', ['Profissional', 'Avançado'])},
             'OngFácil': {1: ('Doadores e beneficiários', ['Prata', 'Ouro']), 3: ('Doadores e beneficiários (frequência)', ['Prata', 'Ouro']),
                          2: ('Prestação de contas completa', ['Ouro'])},
             'Any3 Gestão': {1: ('Associados', ['Básico', 'Avançado', 'Premium'])}, 'Economato': {}}
    pedidos = []

    def plano(lista, sistema, pagina, planos, projeto_id=None):
        pedidos.append((sistema, lista, [x['plano'] for x in planos]))
        if mapas[sistema] is None:
            return None
        return dict(ferramentas=[dict(n=n, recurso=mapas[sistema].get(n, (None, []))[0], planos=mapas[sistema].get(n, (None, []))[1])
                                 for n in range(1, len(lista) + 1)], resumo='Sistema de gestão para entidades.')
    monkeypatch.setattr(ia, 'plano_do_sistema', plano)
    return mapas, pedidos


def test_plano_de_acordo_com_a_referencia_e_proposta_em_pdf_fica(dados, paginas):
    mapas, pedidos = paginas
    p = _projeto(); pid = db.criar(p); r = p.rubricas[0]
    servico.anexar_pdf(p, pid, r, 0, 0, 'F&D Solutions.pdf', _pdf(PROPOSTA))
    db.salvar(pid, p, motivo='proposta anexada')
    assert not servico.sistema_pronto(r)                                                 # só a proposta tem PDF
    ctx = _Ctx()
    res = asyncio.run(servico.pesquisar_sistema(pid, 13, ctx))
    p2, _ = db.carregar(pid); r2 = p2.rubricas[0]; s = r2.subitens[0]
    assert res['versao'] and res['cotados'] == 4
    assert [f.plataforma or f.nome for f in s.fontes] == ['F&D Solutions Ltda', 'Ongsys', 'OngFácil']   # a proposta fica; depois, a ordem de preferência
    assert s.precos == [27092, 49900, 49000]                                             # Profissional e Ouro: NÃO os planos mais baratos (299 e 320)
    assert s.fontes[0].evidencia.url is None and s.fontes[0].evidencia.origem == 'pdf'   # proposta sem link
    assert s.fontes[1].evidencia.url == 'https://site.ongsys.com.br/precos' and s.fontes[1].cnpj == '29.335.055/0001-34'
    assert s.produtos[0] == 'F&D Solutions Ltda — proposta comercial em PDF' and 'plano Profissional (R$ 499,00/mês)' in s.produtos[1]
    assert 'ferramentas de referência' in s.justificativa and 'não o mais barato' in s.justificativa
    assert 'Relatório com gráficos = Dashboards' in s.justificativa and 'o plano Iniciante, mais barato, tem 0' in s.justificativa
    assert 'menor plano com 3 das 5 ferramentas de referência (o plano Prata, mais barato, tem 2)' in s.justificativa
    assert s.valor_plano == 27092                                                        # sistema: o valor no plano é o menor das 3 cotações (não a média)
    assert all(lista[0].startswith('1.1 - Cadastro atendidos') and len(lista) == 5 for _, lista, _ in pedidos)
    assert ('Ongsys', ['Iniciante', 'Profissional', 'Avançado']) in [(n, pl) for n, _, pl in pedidos]
    assert servico.sistema_pronto(r2) and servico.subitem_pronto(s)
    assert not ctx.avisos


def test_sistema_sem_ferramentas_da_referencia_fica_por_ultimo(dados, paginas):
    mapas, _ = paginas
    mapas['Ongsys'] = {}                                                                 # nenhuma ferramenta da referência
    p = _projeto(); pid = db.criar(p); r = p.rubricas[0]
    servico.anexar_pdf(p, pid, r, 0, 0, 'F&D Solutions.pdf', _pdf(PROPOSTA)); db.salvar(pid, p, motivo='proposta anexada')
    asyncio.run(servico.pesquisar_sistema(pid, 13, _Ctx()))
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert [f.plataforma or f.nome for f in s.fontes] == ['F&D Solutions Ltda', 'OngFácil', 'Any3 Gestão']
    assert s.precos == [27092, 49000, 7990]
    assert 'link do Any3' in s.justificativa                                             # o desconto condicionado fica escrito


def test_plano_sem_preco_definido_ou_sem_ia_nao_entra(dados, paginas, monkeypatch):
    mapas, _ = paginas
    mapas['Ongsys'] = {5: ('Dashboards', ['Avançado'])}                                  # só no plano "a partir de R$ 899": não é preço definido
    mapas['OngFácil'] = None                                                             # a IA não respondeu
    p = _projeto(); pid = db.criar(p); r = p.rubricas[0]
    servico.anexar_pdf(p, pid, r, 0, 0, 'F&D Solutions.pdf', _pdf(PROPOSTA)); db.salvar(pid, p, motivo='proposta anexada')
    ctx = _Ctx()
    asyncio.run(servico.pesquisar_sistema(pid, 13, ctx))
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert [f.plataforma or f.nome for f in s.fontes] == ['F&D Solutions Ltda', 'Any3 Gestão', 'Ongsys']
    assert s.precos == [27092, 7990, 29900] and 'só em plano sem preço definido' in s.justificativa   # nunca entra o "a partir de R$ 899"
    assert [a[0] for a in ctx.fontes if a[1] == 'falhou'] == ['OngFácil']
    monkeypatch.setattr(ia, 'disponivel', lambda: False)                                 # sem IA: nada é cotado e nada muda
    ctx = _Ctx(); antes = db.carregar(pid)[1]
    res = asyncio.run(servico.pesquisar_sistema(pid, 13, ctx))
    assert res['versao'] is None and db.carregar(pid)[1] == antes and 'precisa da IA' in ctx.avisos[-1]


def test_o_que_a_osc_deixou_fica_e_so_o_resto_e_cotado(dados, paginas):
    """Pedido da OSC (03/10/2026): a cotação que ela deixou (anexada ou digitada) fica onde está; só as outras são cotadas."""
    # 1. as 3 digitadas pela OSC: nada é trocado (antes, as digitadas sem PDF eram substituídas)
    p = _projeto(digitadas=True); pid = db.criar(p)
    ctx = _Ctx()
    asyncio.run(servico.pesquisar_sistema(pid, 13, ctx))
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert s.precos == [27092, 29900, 49000] and [f.nome for f in db.carregar(pid)[0].rubricas[0].fontes][:1] == ['F&D Solutions Ltda']
    # 2. proposta anexada SEM nome e SEM CNPJ (como a OSC fez): fica na cotação 1, o nome e o CNPJ vêm do PDF, e só as outras duas são cotadas
    p = _projeto(); pid = db.criar(p); r = p.rubricas[0]
    r.fontes[0].nome, r.fontes[0].cnpj = '', ''
    msg = servico.anexar_pdf(p, pid, r, 0, 0, 'proposta.pdf', _pdf(PROPOSTA)); db.salvar(pid, p)
    assert 'nome e CNPJ preenchidos pelo PDF' in msg and r.subitens[0].fontes[0].cnpj == '42.274.849/0001-01'
    asyncio.run(servico.pesquisar_sistema(pid, 13, _Ctx()))
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert [f.plataforma or f.nome for f in s.fontes] == ['F&D Solutions', 'Ongsys', 'OngFácil'] and s.precos == [27092, 49900, 49000]
    assert s.fontes[0].evidencia.origem == 'pdf' and s.valor_plano == 27092
    # 3. nova cotação de UMA posição só: as outras duas ficam; entra outro fornecedor (não o que estava nem os que já estão)
    asyncio.run(servico.pesquisar_sistema(pid, 13, _Ctx(), somente_k=1))
    s2 = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert [f.plataforma or f.nome for f in s2.fontes] == ['F&D Solutions', 'Any3 Gestão', 'OngFácil'] and s2.precos[0] == 27092 and s2.precos[2] == 49000


def test_regra_fixa_de_escolha_do_plano():
    lista = S.ferramentas(S.escopo_do_texto(PROPOSTA))
    assert len(lista) == 5 and S.sem_numero(lista[2]) == 'Controle de frequência por sala'
    assert S.ferramentas('Cadastro de atendidos\nMódulo: Pesquisa\nPesquisa online') == ['Cadastro de atendidos', 'Pesquisa online']
    planos = [('Prata', 32000), ('Ouro', 49000)]
    m = lambda d: [dict(n=n, recurso=d.get(n, (None, []))[0], planos=d.get(n, (None, []))[1]) for n in range(1, 6)]
    # tudo o que a referência pede já está no Prata: não sobe para o Ouro por recursos que a referência não pede
    e = S.escolher_plano(m({1: ('Beneficiários', ['Prata', 'Ouro']), 3: ('Frequência', ['Prata', 'Ouro'])}), planos, lista)
    assert (e['plano'], e['preco'], e['cobertura']) == ('Prata', 32000, 2) and 'os planos maiores não acrescentam nenhuma' in e['motivo']
    assert e['atende'][0] == 'Cadastro atendidos e responsáveis; (ficha de cadastro, ficha de saúde, ficha de prosseguimentos, visita domiciliar) = Beneficiários'
    assert 'Pesquisa online; (através de link que pode ser enviado por whatsapp)' in e['nao_atende']
    # uma ferramenta de referência só existe no Ouro: sobe
    e = S.escolher_plano(m({1: ('Beneficiários', ['Prata', 'Ouro']), 2: ('Prestação de contas', ['Ouro'])}), planos, lista)
    assert (e['plano'], e['cobertura']) == ('Ouro', 2) and 'o plano Prata, mais barato, tem 1' in e['motivo']
    # nenhuma ferramenta: o plano pago mais simples; nome de plano que não existe e resposta torta não contam
    e = S.escolher_plano(m({1: ('Beneficiários', ['Diamante'])}) + ['lixo', dict(n='x')], planos, lista)
    assert (e['plano'], e['cobertura'], e['atende']) == ('Prata', 0, []) and 'nenhum plano tem as ferramentas' in e['motivo']
    assert S.escolher_plano(m({}), [], lista) is None


def test_comparacao_da_ia_duas_leituras_e_resposta_guardada(dados, monkeypatch):
    """Caso real (01/10/2026): com o mesmo sistema e as mesmas ferramentas, a IA respondeu Ouro numa rodada e Prata na outra (o texto da
    página veio em outra ordem). Agora: duas leituras, só vale o que as duas dizem, e a comparação fica guardada."""
    lista = ['1.1 - Cadastro de atendidos', '2.1 - Controle de frequência', '2.2 - Relatórios personalizados']
    planos = [dict(plano='Prata', preco_mensal='R$ 320,00'), dict(plano='Ouro', preco_mensal='R$ 490,00')]
    chamadas = []
    leituras = [  # 1ª leitura: vê "relatórios personalizados" no Ouro; 2ª leitura (outra ordem): não vê
        [dict(n=1, recurso='Beneficiários', planos=['prata', 'OURO', 'Diamante']), dict(n=2, recurso='null', planos=['Ouro']), dict(n=3, recurso='Prestação de contas', planos=['Ouro'])],
        [dict(n=1, recurso='Cadastro de beneficiários', planos=['Prata', 'Ouro']), dict(n=2, recurso=None, planos=[]), dict(n=3, recurso=None, planos=[])]]

    def perguntar(tipo, instrucao, dados_, projeto_id=None, **k):
        chamadas.append(dados_['pagina'])
        return dict(ferramentas=leituras[(len(chamadas) - 1) % 2], resumo='Gestão de ONG')
    monkeypatch.setattr(ia, 'disponivel', lambda: True)
    monkeypatch.setattr(ia, 'perguntar', perguntar)
    r1 = ia.plano_do_sistema(lista, 'OngFácil', 'bloco A\n\nbloco B\n\nbloco C\n\nbloco D', planos)
    assert chamadas == ['bloco A\n\nbloco B\n\nbloco C\n\nbloco D', 'bloco C\n\nbloco D\n\nbloco A\n\nbloco B']           # 2ª leitura em outra ordem
    assert r1['ferramentas'] == [dict(n=1, recurso='Beneficiários', planos=['Prata', 'Ouro']), dict(n=2, recurso=None, planos=[]),
                                 dict(n=3, recurso=None, planos=[])]                    # a equivalência vista só numa leitura fica de fora
    assert S.escolher_plano(r1['ferramentas'], [('Prata', 32000), ('Ouro', 49000)], lista)['plano'] == 'Prata'
    r2 = ia.plano_do_sistema(lista, 'OngFácil', 'o mesmo texto em OUTRA ordem', planos)
    assert r2 == r1 and len(chamadas) == 2                                               # não pergunta de novo: a resposta não oscila
    ia.plano_do_sistema(lista, 'OngFácil', 'texto', planos[:1] + [dict(plano='Ouro', preco_mensal='R$ 520,00')])
    assert len(chamadas) == 4                                                            # mudou o preço de um plano: compara de novo
    monkeypatch.setattr(ia, 'perguntar', lambda *a, **k: dict(ferramentas=[dict(n=1, recurso='x', planos=['Prata'])]))
    assert ia.plano_do_sistema(lista, 'Outro', 'texto', planos) is None                  # resposta incompleta (faltam ferramentas): não serve


def test_cotacao_automatica_antiga_pelo_mais_barato_e_refeita():
    ev = lambda o, u: Evidencia(arquivo='projetos/1/evidencias/x.pdf', sha256='a' * 64, url=u, origem=o)
    fs = [Fonte(nome='FP2', cnpj='07.931.921/0001-17', evidencia=ev('navegador', 'http://www.any3.com.br/Any3-Gestao-Planos.aspx')),
          Fonte(nome='BH BIT', cnpj='07.609.769/0001-50', evidencia=ev('navegador', 'https://economato.com.br/planos/')),
          Fonte(nome='F&D', cnpj='42.274.849/0001-01', evidencia=ev('pdf', None))]
    s = Subitem(descricao='Sistema', qtd=1, precos=[7990, 19700, 27092], fontes=fs, confirmacao='sistemas diferentes com ferramentas parecidas')
    r = RubricaMaterial(item=13, descricao='Sistema de gestão de dados', meses=12, subitens=[s])
    assert servico.subitem_pronto(s) and not servico.sistema_pronto(r)                   # regra antiga (plano mais barato): "Pesquisar tudo" refaz
    s.confirmacao = servico.CONF_SISTEMA
    assert servico.sistema_pronto(r)
    s.confirmacao = None
    for f in fs:
        f.evidencia.origem = 'pdf'                                                       # 3 propostas anexadas pela OSC: ficam como estão
    assert servico.sistema_pronto(r)


def test_endereco_do_carrinho_vira_o_endereco_do_produto(dados):
    """Reclamação da OSC (01/10/2026): o link do suco de uva da Coop abria um carrinho vazio. O PDF (um item só) fica; o endereço passa a ser
    o da página do produto, tirado do banco de produtos — sem refazer a pesquisa."""
    carrinho = 'https://www.coopsupermercado.com.br/checkout/#/cart'
    ev = lambda arq, url: Evidencia(arquivo=f'projetos/1/evidencias/{arq}', sha256='a' * 64, url=url, origem='api')
    fs = [Fonte(nome='COOP', cnpj='57.508.426/0001-78', plataforma='Coop Supermercado', evidencia=ev('ab_carrinho_coop_item14_Suco_de_uva_1L.pdf', carrinho)),
          Fonte(nome='CBD', cnpj='47.508.411/0001-56', plataforma='Pão de Açúcar', evidencia=ev('ab_produto_paodeacucar_item14_Suco_de_uva_1L.pdf', 'https://www.paodeacucar.com/produto/1/suco')),
          Fonte(nome='ATACADAO', cnpj='75.315.333/0001-09', plataforma='Atacadão', evidencia=ev('ab_carrinho_atacadao_item14_1.pdf', 'https://www.atacadao.com.br/checkout/#/cart'))]
    s = Subitem(descricao='Suco de uva 1L', qtd=20, precos=[1429, 1499, 1899], produtos=['Suco Uva Natural One 900ml', 'Suco uva 900ml', 'Suco Uva 900ml'], fontes=fs)
    p = Projeto(nome='Teste', teto=10_000_000, rubricas=[RubricaMaterial(item=14, descricao='Alimentação', meses=10, subitens=[s])])
    pid = db.criar(p)
    db.produtos_guardar(pid, 14, 'Suco de uva 1L', [dict(nivel=0, ofertas=[
        dict(loja='coop', nome='Suco Uva Natural One 900ml', preco=1429, url='https://www.coopsupermercado.com.br/suco-uva-natural-one-900ml/p'),
        dict(loja='paodeacucar', nome='Suco uva 900ml', preco=1499, url='https://www.paodeacucar.com/produto/1/suco'),
        dict(loja='atacadao', nome='Suco Uva 900ml', preco=1899, url='https://www.atacadao.com.br/suco-uva-900ml/p')])])
    assert not servico.subitem_pronto(s)
    assert servico.consertar_links(p, pid) == 1
    assert fs[0].evidencia.url == 'https://www.coopsupermercado.com.br/suco-uva-natural-one-900ml/p' and fs[0].evidencia.arquivo.endswith('Suco_de_uva_1L.pdf')
    assert fs[2].evidencia.url.endswith('/checkout/#/cart')          # PDF antigo com vários itens: não é consertado, é refeito
    assert servico.comprovante_no_formato(fs[0].evidencia) and not servico.comprovante_no_formato(fs[2].evidencia)
    assert servico.consertar_links(p, pid) == 0
