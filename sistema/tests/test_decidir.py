"""O sistema nunca substitui um item sozinho (decisão da OSC, 06/10/2026).

Caso real: "Folha Sulfite 500 Folhas" virou giz de cera, e na pesquisa completa dois itens viraram o mesmo grampeador. A busca ACHAVA a folha
sulfite em 7 lojas, mas o mesmo produto (mesmo código de barras), com estoque e entrega no CEP, só existia em 2 — e o sistema pulava para
"qualquer produto da categoria da rubrica". Agora: só é gravado sozinho o item achado como foi pedido; o resto vira OPÇÃO para a OSC decidir
(substituir, mudar o pedido e pesquisar de novo, ou preencher à mão). E há uma opção nova: a mesma marca e descrição em 3 lojas quando só o
código de barras difere ("Report" × "Report Premium")."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

SULFITE = 'Folha Sulfite 500 Folhas'
# os anúncios lidos de verdade em 06/10/2026 (lojas, preços e códigos de barras públicos)
ANUNCIOS = [('atacadao', 2549, '7898205206418', 'Papel Sulfite Allmax A4 75g 500 folhas'), ('atacadao', 3199, '7891191003733', 'Papel Sulfite Report A4 75g 500 folhas'),
            ('samsclub', 3198, '7891191790008', 'Folha Sulfite A4 Branco Suzano Report Premium Pacote 500 Folhas'),
            ('americanas', 2999, '7891191003733', 'Papel Sulfite A4 Report 500 Folhas Suzano 75g'),
            ('livrariascuritiba', 2822, '7891173023001', 'Papel Sulfite Chamex A4 Resma 500 Folhas'), ('livrariascuritiba', 2670, '7891191790008', 'Papel Sulfite Report 75g A4 500 Folhas Resma'),
            ('livrariascuritiba', 5368, '7891191003764', 'Papel Sulfite Report 210x297mm 90g A4 500fl Resma'),
            ('gimba', 3290, None, 'Papel Sulfite Chamex A4 210x297mm 75g Resma Branco PCT C/500 FL'), ('gimba', 2990, None, 'Papel Sulfite HP A4 Branco Resma 210X297 75g 500 FL')]


class Ctx:
    id = 0

    def __init__(self):
        self.avisos = []

    def progresso(self, *a, **k): pass
    def etapa(self, *a, **k): pass
    def fonte(self, *a, **k): pass
    def aviso(self, m): self.avisos.append(m)


class _NavegadorFalso:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

    class chromium:
        @staticmethod
        async def launch():
            class B:
                async def close(self): pass
            return B()


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv('ORCAMENTO_DADOS', str(tmp_path))
    import importlib, orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    monkeypatch.setattr(dbm, 'PASTA_LOCAL', str(tmp_path / 'local'))
    import app as appmod
    importlib.reload(appmod)
    c = TestClient(appmod.app)
    c.appmod = appmod
    return c


def _ofertas():
    return [dict(loja=l, preco=p, ean=e, nome=n, url=f'https://{l}.exemplo/{i}/p') for i, (l, p, e, n) in enumerate(ANUNCIOS)]


def _motor(extra=()):
    from orcamento.produtos import cesta
    lojas = ['atacadao', 'samsclub', 'americanas', 'livrariascuritiba', 'gimba', 'papelex']
    m = cesta.Motor([dict(desc=SULFITE, qtd=2)], lojas, '01001-000', usar_ia=False)
    m.ofertas[(SULFITE, 0)] = _ofertas() + list(extra)
    return m


def test_mesma_marca_e_descricao_com_codigos_diferentes_e_opcao_para_decidir():
    """O mesmo código de barras só existe em 2 lojas (Chamex: Curitiba e Gimba; Report Premium: Curitiba e Sam's; Report: Americanas e
    Atacadão). Antes, o item caía direto na categoria da rubrica. Agora aparece a opção "Report A4 75g 500 folhas" em 3 lojas — mesma marca e
    descrição, códigos diferentes —, que NÃO é gravada sozinha."""
    from orcamento.produtos import cesta
    m = _motor()
    opcoes = m._opcoes_por_item(m._grupos())[SULFITE]
    assert len(opcoes) == 1
    o = opcoes[0]
    assert o['codigos_diferentes'] and o['confirmacao'] == cesta.CODIGOS_DIFERENTES == 'descrição; códigos de barras diferentes' and o['nivel'] == 0
    assert [(x['loja'], x['preco'], x['ean']) for x in o['ofertas']] == [('livrariascuritiba', 2670, '7891191790008'), ('americanas', 2999, '7891191003733'),
                                                                        ('atacadao', 3199, '7891191003733')]   # as 3 mais baratas, com o código de cada uma
    assert not cesta.atende_o_pedido(o)                                                    # sem a confirmação da IA: fica para a OSC decidir
    assert cesta.atende_o_pedido(dict(o, ia=dict(mesmo_produto=True, motivo='mesmo papel'))) and not cesta.atende_o_pedido(dict(o, ia=dict(mesmo_produto=False, motivo='x')))
    # o papel de 90 g e o "Premium" declarado no anúncio não entram no grupo: a descrição não é a mesma
    assert all('90g' not in x['nome'] and 'Premium' not in x['nome'] for x in o['ofertas'])
    # com o MESMO produto em 3 lojas (o Chamex também na Papelex, mesmo código), essa é a opção que vale — e é a única gravada sozinha
    m = _motor([dict(loja='papelex', preco=3050, ean='7891173023001', nome='Papel Sulfite A4 75g 500 Folhas - Chamex', url='https://papelex.exemplo/chamex/p')])
    opcoes = m._opcoes_por_item(m._grupos())[SULFITE]
    assert cesta.atende_o_pedido(opcoes[0]) and [x['loja'] for x in opcoes[0]['ofertas']] == ['livrariascuritiba', 'papelex', 'gimba']
    assert opcoes[1]['codigos_diferentes'] and m.escolher({SULFITE: opcoes}, m.itens)[SULFITE] is opcoes[0]
    # o que conta como "o item pedido": nada de troca, marcas diferentes, códigos diferentes nem "como pedido, mas sem a caixa"
    base = dict(nivel=0, misto=False, perdidos=[])
    assert cesta.atende_o_pedido(base) and not cesta.atende_o_pedido(None)
    for muda in (dict(nivel=1), dict(nivel=3), dict(misto=True), dict(codigos_diferentes=True), dict(perdidos=['caixa']),
                 dict(nivel=1, ia=dict(mesmo_produto=True)), dict(codigos_diferentes=True, perdidos=['caixa'], ia=dict(mesmo_produto=True))):
        assert not cesta.atende_o_pedido(dict(base, **muda)), muda


def test_ia_so_decide_embalagem_com_varias_unidades_quando_o_pedido_comeca_pela_embalagem(monkeypatch):
    """A IA respondeu "várias unidades" para "Folha Sulfite 500 Folhas" (500 folhas é a medida do pacote, não unidades): toda resma passava a
    constar como "sem: várias unidades". A resposta dela só vale quando o pedido começa pela embalagem ("Caixa Caneta…")."""
    from orcamento import ia
    from orcamento.produtos import cesta, identidade as ID
    resp = lambda d: {d: dict(produto=d.lower(), sinonimos=[], buscas=[], varias_unidades=True)}
    monkeypatch.setattr(ia, 'disponivel', lambda: True)
    monkeypatch.setattr(ID, '_VARIAS', {}); monkeypatch.setattr(ID, '_DINAMICOS', {})   # o que a IA disse fica na memória do motor: aqui, só durante o teste
    for pedido, esperado in ((SULFITE, False), ('Caixa Caneta Esferográfica Azul', True)):
        monkeypatch.setattr(ia, 'entender_pedidos', lambda ds, pid=None: resp(ds[0]))
        m = cesta.Motor([dict(desc=pedido, qtd=1)], ['gimba', 'papelex', 'atacadao'], '01001-000', usar_ia=True)
        m._entender()
        assert ID.quer_varias_unidades(pedido) is esperado, pedido
        assert ('varias_unidades' in m.entendido[pedido]) is esperado


def _projeto(cliente):
    from orcamento import db
    from orcamento.modelo import RubricaMaterial, Subitem
    pid = int(cliente.post('/projetos', data={'nome': 'T', 'teto': '10.000,00', 'cep': '01001-000'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    p = db.carregar(pid)[0]
    p.rubricas = [RubricaMaterial(item=1, descricao='Material de escritório', meses=10, regra='mercado',
                                  subitens=[Subitem(descricao='Folha Sulfite', especificacao='500 Folhas', qtd=2), Subitem(descricao='Clips', especificacao='100 Unidades', qtd=5)])]
    db.salvar(pid, p)
    return pid


def _resultado_do_motor():
    """O que o motor devolveria: o Clips achado como pedido; a folha sulfite só com opções que não são "o mesmo produto como pedido"."""
    from orcamento.produtos import cesta
    of = lambda loja, nome, preco, ean=None: dict(loja=loja, nome=nome, titulo=None, marca=None, ean=ean, preco=preco, url=f'https://{loja}.exemplo/{abs(hash(nome)) % 9999}/p', sku=None, seller=None)
    op = lambda nivel, ofertas, **k: dict(dict(nivel=nivel, distancia=float(nivel), perdidos=[], lojas=[x['loja'] for x in ofertas], ean_em=0, substituto=None, misto=False,
                                               confirmacao='descrição', ofertas=ofertas, reservas=[], lojas_com_o_produto=3), **k)
    report = op(0, [of('livrariascuritiba', 'Papel Sulfite Report 75g A4 500 Folhas Resma', 2670, '7891191790008'), of('americanas', 'Papel Sulfite A4 Report 500 Folhas Suzano 75g', 2999, '7891191003733'),
                    of('atacadao', 'Papel Sulfite Report A4 75g 500 folhas', 3199, '7891191003733')], codigos_diferentes=True, confirmacao=cesta.CODIGOS_DIFERENTES,
                ia=dict(mesmo_produto=False, motivo='um dos anúncios é da linha Premium'))   # a IA ficou em dúvida: não é gravada sozinha
    menor = op(1, [of('americanas', 'Papel Sulfite Chamequinho A4 100 Folhas Chamex', 799), of('gimba', 'Papel Sulfite Chamequinho A4 100 FL', 849), of('papelex', 'Papel Sulfite A4 100 Folhas - Chamequinho', 699)],
               perdidos=['500 folhas'])
    giz = op(3, [of('papelex', 'Giz De Cera Fino 12 Cores - Leo&Leo', 299), of('gimba', 'Giz de Cera Leo&Leo Fino 12 Cores 1 UN', 449), of('americanas', 'Giz de Cera Fino 12 Cores Leo&Leo', 699)],
             substituto='Giz de cera 12 cores', distancia=30.0)
    clips = op(0, [of('papelex', 'Clips 2/0 Niquelado Com 100 Un - Bacchi', 479, '789'), of('gimba', 'Clips Niquelado Bacchi Nº2/0 CX C/100 UN', 499, '789'),
                   of('livrariascuritiba', 'Clips N2 100 Unidades Niquelado Bacchi', 960, '789')], confirmacao='EAN nas 3 lojas')
    return dict(modo='por_item', trio=None, itens=[], escolha={SULFITE: giz, 'Clips 100 Unidades': clips},   # o motor antigo escolhia o giz de cera
                opcoes={SULFITE: [giz, menor, report], 'Clips 100 Unidades': [clips]}, entendido={}, lojas=[], lojas_incompletas={}, rejeitadas_ia={}, buscas=10, falhas=0)


def test_a_pesquisa_nunca_substitui_e_o_item_fica_para_a_osc_decidir(cliente, monkeypatch):
    from orcamento import db, servico
    from orcamento.calculo import verificar
    from orcamento.produtos import cesta
    pid = _projeto(cliente)

    async def pesquisar(itens, *a, **k):
        res = _resultado_do_motor()
        pedidos = [i['desc'] for i in itens]
        return dict(res, escolha={d: o for d, o in res['escolha'].items() if d in pedidos}, opcoes={d: o for d, o in res['opcoes'].items() if d in pedidos})
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: _NavegadorFalso())
    prop = asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))
    sulfite, clips = [next(l for l in prop['linhas'] if l['desc'] == d) for d in (SULFITE, 'Clips 100 Unidades')]
    # a folha sulfite NÃO recebe o giz de cera (nem o papel de 100 folhas, nem o Report de códigos diferentes): fica para decidir, com as 3 opções
    assert sulfite['acao'] == 'RETIRADO' and sulfite['opcao_dados'] is None and sulfite['decidir'] == 3
    assert sulfite['motivo'].startswith(servico.AGUARDA_DECISAO) and 'Nada foi substituído' in sulfite['motivo']
    assert clips['acao'] == 'mantido' and clips['opcao_dados']['confirmacao'] == 'EAN nas 3 lojas'                # o que foi achado como pedido segue normal
    banco = db.produtos_do_banco(pid, 1)
    assert [(o['nivel'], bool(o.get('codigos_diferentes')), o['atende']) for o in banco[SULFITE]['opcoes']] == [(0, True, False), (1, False, False), (3, False, False)]   # do mais perto do pedido para o mais longe
    assert [o['atende'] for o in banco['Clips 100 Unidades']['opcoes']] == [True]
    # (se a IA tivesse CONFIRMADO que os 3 anúncios do Report são o mesmo produto, ele entraria sozinho: é o item pedido, não uma substituição)
    confirmada = _resultado_do_motor()
    confirmada['opcoes'][SULFITE][2]['ia'] = dict(mesmo_produto=True, motivo='mesmo papel, mesma marca')

    async def com_ia(itens, *a, **k):
        return confirmada
    monkeypatch.setattr(cesta, 'pesquisar', com_ia)
    l2 = next(l for l in asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))['linhas'] if l['desc'] == SULFITE)
    assert l2['acao'] == 'mantido' and l2['opcao_dados']['codigos_diferentes'] and not l2.get('decidir') and [x['preco'] for x in l2['opcao_dados']['ofertas']] == [2670, 2999, 3199]
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))                                               # de volta ao caso em dúvida (o banco guarda a última pesquisa)
    banco = db.produtos_do_banco(pid, 1)
    # aplicar a parte da folha sulfite: nada é gravado nela além do motivo (e nenhum comprovante é buscado)
    asyncio.run(servico.aplicar_proposta(pid, 1, dict(prop, linhas=[sulfite]), Ctx()))
    p = db.carregar(pid)[0]
    s = p.rubricas[0].subitens[0]
    assert (s.descricao, s.especificacao, s.descricao_original, s.nivel, s.precos, s.fontes, s.valor_plano) == ('Folha Sulfite', '500 Folhas', None, 0, [None] * 3, [], None)
    assert s.justificativa.startswith('aguardando a sua decisão') and servico.aguarda_decisao(s, banco[SULFITE]['opcoes'])
    assert not servico.aguarda_decisao(p.rubricas[0].subitens[1], banco['Clips 100 Unidades']['opcoes'])
    r10 = [a.mensagem for a in verificar(p) if a.regra == 'R10' and 'Folha Sulfite' in a.item]
    assert r10 and 'o sistema não substituiu nada' in r10[0] and 'escolha uma das opções de substituição' in r10[0]
    # a tela do item pergunta: substituir por uma das opções, ou mudar o pedido e pesquisar de novo
    pag = cliente.get(f'/p/{pid}/mat/1').text
    quadro = pag.split('id="decidir0"')[1].split('id="repesquisar0"')[0]
    for texto in ('O sistema não achou "Folha Sulfite 500 Folhas" igual em 3 lojas', '<b>Nada foi substituído.</b>', '1. Usar uma destas opções',
                  'Mesma marca e descrição; códigos de barras diferentes', 'Papel Sulfite Report 75g A4 500 Folhas Resma', 'R$ 26,70', 'IA acha que NÃO é o mesmo produto',
                  'Parecido: outro tamanho ou variante', 'Sem: 500 folhas', 'Ver também produtos de outro tipo, da categoria da rubrica (1)', 'Giz de cera 12 cores',
                  '2. Não substituir', 'Salvar o que mudei e pesquisar este item de novo', 'value="repesquisar-0"'):
        assert texto in quadro, texto
    assert quadro.count('Usar esta opção') == 1 and quadro.count('Substituir por esta opção') == 1 and quadro.count('Trocar por este') == 1   # mesma marca e descrição não é substituição
    assert quadro.index('Papel Sulfite Report') < quadro.index('Chamequinho') < quadro.index('Giz de cera')   # o mais perto do pedido primeiro; o de outro tipo, por último e recolhido
    assert 'id="decidir1"' not in pag                                                                             # o Clips não tem nada a decidir
    # "Pesquisar de novo só este item": a mesma coisa — nada é substituído, e a tarefa leva de volta ao quadro de decisão
    from test_interface import _campos
    dados = dict(_campos(pag), depois='repesquisar-0', sesp0='A4 500 Folhas')
    tid = int(cliente.post(f'/p/{pid}/mat/1', data=dados, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    for _ in range(80):
        t = cliente.appmod.tarefas.ler(tid)
        if t['estado'] not in ('na fila', 'rodando'):
            break
        time.sleep(0.1)
    assert t['estado'] == 'concluída', t.get('erro')
    # (o pedido mudou para "Folha Sulfite A4 500 Folhas": o motor de teste não tem opções para ele — o item continua como pedido, sem substituição)
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert (s.descricao, s.especificacao, s.nivel, s.precos) == ('Folha Sulfite', 'A4 500 Folhas', 0, [None] * 3)


def test_nova_pesquisa_de_um_item_mostra_as_opcoes_e_pergunta(cliente, monkeypatch):
    from orcamento import db, servico, tarefas

    async def pesquisar(pid_, item, ctx, somente=None, sem_lojas=(), respeitar_teto=True):
        return dict(linhas=[dict(desc=somente[0], acao='RETIRADO', decidir=3, opcao_dados=None, motivo=servico.AGUARDA_DECISAO + ': o item pedido não foi achado igual em 3 lojas')])
    aplicou = []

    async def aplicar(*a, **k):
        aplicou.append(a)
    pid = _projeto(cliente)
    monkeypatch.setattr(servico, 'pesquisar_rubrica', pesquisar)
    monkeypatch.setattr(servico, 'aplicar_proposta', aplicar)
    from test_interface import _campos
    dados = dict(_campos(cliente.get(f'/p/{pid}/mat/1').text), depois='repesquisar-0')
    tid = int(cliente.post(f'/p/{pid}/mat/1', data=dados, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    for _ in range(80):
        t = tarefas.ler(tid)
        if t['estado'] not in ('na fila', 'rodando'):
            break
        time.sleep(0.1)
    assert t['estado'] == 'concluída' and not aplicou                                                  # nada foi aplicado
    assert 'NADA foi substituído' in t['avisos'][0] and '3 opção(ões) de substituição na tela do item' in t['avisos'][0]
    assert t['resultado']['ir_para'].endswith('/mat/1#decidir0')                                       # volta direto ao quadro de decisão do item
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert s.justificativa.startswith('aguardando a sua decisão') and s.precos == [None] * 3 and s.descricao == 'Folha Sulfite'


def test_pesquisa_completa_nunca_substitui(cliente, monkeypatch):
    """"O sistema nunca pode substituir um item na pesquisa completa de tudo": o que não é achado como pedido fica para decidir, e a tarefa diz quais."""
    from orcamento import db, servico, tarefas
    pid = _projeto(cliente)

    async def pesquisar(pid_, item, ctx, somente=None, sem_lojas=(), respeitar_teto=True):
        return dict(linhas=[dict(desc=SULFITE, acao='RETIRADO', decidir=2, opcao_dados=None, motivo=servico.AGUARDA_DECISAO + ': …'),
                            dict(desc='Clips 100 Unidades', acao='mantido', opcao_dados=dict(nivel=0))])
    aplicadas = []

    async def aplicar(pid_, item, prop, ctx):
        aplicadas.append([l['desc'] for l in prop['linhas'] if l.get('opcao_dados')])
        return dict(versao=2)

    async def nada(*a, **k):
        return None
    monkeypatch.setattr(servico, 'pesquisar_rubrica', pesquisar)
    monkeypatch.setattr(servico, 'aplicar_proposta', aplicar)
    monkeypatch.setattr(servico, 'consertar_pendentes', nada)
    monkeypatch.setattr(cliente.appmod, 'consultar_cnpjs_que_faltam', lambda *a, **k: None)
    tid = int(cliente.post(f'/p/{pid}/pesquisar-tudo', follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    for _ in range(100):
        t = tarefas.ler(tid)
        if t['estado'] not in ('na fila', 'rodando'):
            break
        time.sleep(0.1)
    assert t['estado'] == 'concluída', t.get('erro')
    assert aplicadas == [['Clips 100 Unidades']]                                                       # só o que foi achado como pedido
    assert '1 não achado(s) como pedido(s): aguardam a sua decisão (nada foi substituído)' in t['resultado']['resumo']['item 1']
    aviso = next(a for a in t['avisos'] if 'NADA foi substituído' in a)
    assert '1 item(ns) não foram achados iguais em 3 lojas' in aviso and f'item 1: {SULFITE}' in aviso


def test_desfazer_substituicao_antiga(cliente):
    """As pesquisas antigas substituíam sozinhas (folha sulfite → giz de cera; dois itens → o mesmo grampeador). A tela mostra o que está
    substituído e desfaz: o item volta a ser o que foi pedido, sem pesquisas."""
    from orcamento import db
    from orcamento.modelo import Fonte, Evidencia, Subitem, RubricaMaterial
    pid = _projeto(cliente)
    p = db.carregar(pid)[0]
    fs = lambda: [Fonte(nome=f'LOJA {k}', cnpj=c, data_pesquisa='2026-10-06', evidencia=Evidencia(arquivo='x.pdf', origem='navegador', sha256='a' * 64, url=f'https://l{k}.exemplo/p'))
                  for k, c in enumerate(('11.222.333/0001-81', '11.444.777/0001-61', '45.997.418/0001-53'))]
    troca = lambda desc, marca, esp, orig, esp_orig: Subitem(descricao=desc, marca=marca, especificacao=esp, qtd=1, precos=[299, 449, 699], valor_plano=449, nivel=3, confirmacao='descrição',
                                                             descricao_original=orig, marca_original='', especificacao_original=esp_orig, fontes=fs(), produtos=[desc] * 3,
                                                             justificativa='troca por produto da categoria da rubrica')
    p.rubricas[0].subitens = [troca('Giz de Cera', 'Leo&Leo', '12 Cores', 'Folha Sulfite', '500 Folhas'), troca('Grampeador', None, '40 Folhas', 'Bloco de Notas', '4 Cores'),
                              troca('Grampeador', None, '40 Folhas', 'Grampo', '5000 Unidades'), Subitem(descricao='Clips', especificacao='100 Unidades', qtd=5)]
    db.salvar(pid, p)
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert '3 item(ns) desta rubrica estão substituídos' in pag and 'Desfazer as 3 substituições' in pag and pag.count('Este item está substituído') == 3
    assert 'Você pediu <b>Folha Sulfite 500 Folhas</b>; o que está orçado é <b>Giz de Cera Leo&amp;Leo 12 Cores</b>' in pag
    r = cliente.post(f'/p/{pid}/mat/1/desfazer-substituicao', data={'desc': 'Folha Sulfite 500 Folhas'}, follow_redirects=True)   # um item
    assert '1 substituição(ões) desfeita(s)' in r.text
    s = db.carregar(pid)[0].rubricas[0].subitens
    assert (s[0].descricao, s[0].marca, s[0].especificacao, s[0].nivel, s[0].precos, s[0].fontes, s[0].descricao_original) == ('Folha Sulfite', None, '500 Folhas', 0, [None] * 3, [], None)
    assert 'substituição desfeita pela OSC (estava: Giz de Cera Leo&Leo 12 Cores)' in s[0].justificativa and s[1].descricao == 'Grampeador'
    cliente.post(f'/p/{pid}/mat/1/desfazer-substituicao', data={'desc': '*'})                                                       # todos os outros
    s = db.carregar(pid)[0].rubricas[0].subitens
    assert [(x.descricao, x.especificacao, x.precos) for x in s] == [('Folha Sulfite', '500 Folhas', [None] * 3), ('Bloco de Notas', '4 Cores', [None] * 3),
                                                                     ('Grampo', '5000 Unidades', [None] * 3), ('Clips', '100 Unidades', [None] * 3)]
    assert 'desfeita(s) pela OSC' in db.historico(pid)[0][0]['motivo']
    assert 'Não havia substituição para desfazer' in cliente.post(f'/p/{pid}/mat/1/desfazer-substituicao', data={'desc': '*'}, follow_redirects=True).text
    assert 'estão substituídos' not in cliente.get(f'/p/{pid}/mat/1').text


def test_opcao_escolhida_pela_osc_nao_e_trocada_por_outra(cliente, monkeypatch):
    """A OSC escolheu UMA opção de substituição. Se o comprovante dela falhar, o sistema avisa — não põe outra opção no lugar por conta própria.
    E fica registrado que a escolha foi dela."""
    from orcamento import db, servico
    from orcamento.modelo import Evidencia
    pid = _projeto(cliente)
    res = _resultado_do_motor()
    db.produtos_guardar(pid, 1, SULFITE, [dict(o, precos=[x['preco'] for x in o['ofertas']], atende=False) for o in res['opcoes'][SULFITE]])
    chamadas = []

    async def comprovar(br, pid_, item, loja, pares, cep, ctx, sufixo='', bloqueadas=None):
        chamadas.append(loja)
        return {(loja, x['url']): dict(ev=Evidencia(arquivo='x.pdf', sha256='a' * 64, url=x['url'], origem='navegador'), preco=None, problema=None) for _, x in pares}
    monkeypatch.setattr(servico, '_comprovar', comprovar)
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: _NavegadorFalso())
    visto = {}
    original = servico.aplicar_proposta

    async def aplicar(pid_, item, prop, ctx):
        visto.update(alternativas=prop['linhas'][0]['alternativas'], modo=prop['modo'])
        return await original(pid_, item, prop, ctx)
    monkeypatch.setattr(servico, 'aplicar_proposta', aplicar)
    asyncio.run(servico.trocar_produto(pid, 1, SULFITE, 2, Ctx()))                                      # a opção "Report, códigos de barras diferentes"
    assert visto == dict(alternativas=[], modo='escolha da OSC') and sorted(chamadas) == ['americanas', 'atacadao', 'livrariascuritiba']
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert s.precos == [2670, 2999, 3199] and s.confirmacao == 'descrição; códigos de barras diferentes' and s.marca == 'Report' and s.nivel == 0
    assert s.justificativa.startswith('opção escolhida pela OSC em ') and 'códigos de barras diferentes' in s.justificativa
    from orcamento.calculo import verificar
    s03 = [a for a in verificar(db.carregar(pid)[0]) if a.regra == 'S03' and 'Folha Sulfite' in a.item]
    assert len(s03) == 1 and s03[0].gravidade == 'atencao' and 'os códigos de barras não são iguais' in s03[0].mensagem


def test_item_a_espera_de_decisao_nao_faz_o_sistema_acrescentar_itens_extras(cliente, monkeypatch):
    """Com um item à espera de decisão, a rubrica parece ter sobra no teto — mas a sobra é só aparente: nenhum item extra é acrescentado."""
    from orcamento import db, servico
    from orcamento.produtos import cesta
    pid = _projeto(cliente)
    p = db.carregar(pid)[0]
    p.rubricas[0].teto_mensal, p.rubricas[0].extras = 50000, ['Borracha Branca']
    db.salvar(pid, p)
    res = _resultado_do_motor()
    extra = dict(res['opcoes']['Clips 100 Unidades'][0], ofertas=[dict(x, nome='Borracha Branca Mercur', url=x['url'] + 'b') for x in res['opcoes']['Clips 100 Unidades'][0]['ofertas']])

    async def pesquisar(itens, *a, **k):
        if [i['desc'] for i in itens] == ['Borracha Branca']:
            return dict(res, escolha={'Borracha Branca': extra}, opcoes={'Borracha Branca': [extra]})
        return res
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    prop = asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))
    assert [(l['desc'], l['acao']) for l in prop['linhas']] == [(SULFITE, 'RETIRADO'), ('Clips 100 Unidades', 'mantido')] and prop['linhas'][0]['decidir'] == 3



CANETA = 'Caneta Esferográfica Azul'


def _motor_caneta(extra=()):
    """Os anúncios lidos de verdade em 06/10/2026: a mesma caneta (mesmo código de barras) em 2 lojas; a 3ª loja a anuncia com mais detalhes."""
    from orcamento.produtos import cesta
    an = [('bazarhorizonte', 950, '7897424080250', 'Caneta Esferográfica Pilot BPS Grip 1.0 Caneta Esferográfica Pilot BPS Grip 1.0 Azul'),
          ('bazarhorizonte', 950, '7897424080175', 'Caneta Esferográfica Pilot BPS Grip 0.7 Caneta Esferográfica Pilot BPS Grip 0.7 Azul'),
          ('livrariascuritiba', 1121, '7897424080250', 'Caneta Esferográfica Azul Grip'),
          ('gimba', 999, None, 'Caneta Esferográfica Pilot BPS Grip Ponta Média 1.0mm Azul 1 UN'),
          ('gimba', 119, None, 'Caneta Esferográfica BIC Cristal Ponta Média 1mm Azul 1 UN'),
          ('papelex', 99, '7896572013292', 'Caneta Esferográfica Top 2000 Azul - Compactor')]
    m = cesta.Motor([dict(desc=CANETA, qtd=10)], ['bazarhorizonte', 'livrariascuritiba', 'gimba', 'papelex', 'americanas'], '01001-000', usar_ia=False)
    m.ofertas[(CANETA, 0)] = [dict(loja=l, preco=p, ean=e, nome=n, url=f'https://{l}.exemplo/{i}/p') for i, (l, p, e, n) in enumerate(an)] + list(extra)
    return m


def test_mesmo_produto_em_2_lojas_e_a_terceira_com_anuncio_menos_detalhado():
    """A caneta Pilot BPS Grip 1.0 azul estava em 3 lojas, mas o sistema só juntava 2: a 3ª escrevia "Ponta Média 1.0mm", e as outras só "1.0".
    Agora isso vira uma opção à parte — gravada sozinha só com a confirmação da IA; sem ela, fica para a OSC decidir."""
    from orcamento.produtos import cesta, identidade as ID
    m = _motor_caneta()
    opcoes = m._opcoes_por_item(m._grupos())[CANETA]
    assert len(opcoes) == 1
    o = opcoes[0]
    assert o['detalhe_nao_citado'] and o['nivel'] == 0 and o['confirmacao'] == cesta.DETALHE_NAO_CITADO == 'descrição; um anúncio não cita um detalhe' and o['reservas'] == []
    assert [(x['loja'], x['preco']) for x in o['ofertas']] == [('bazarhorizonte', 950), ('gimba', 999), ('livrariascuritiba', 1121)]
    assert 'BPS Grip 1.0 ' in o['ofertas'][0]['nome'] and 'Ponta Média 1.0mm' in o['ofertas'][1]['nome']       # a de 0.7 não entra: o número da ponta é outro
    assert not cesta.atende_o_pedido(o) and cesta.atende_o_pedido(dict(o, ia=dict(mesmo_produto=True, motivo='mesma caneta')))
    assert not cesta.atende_o_pedido(dict(o, ia=dict(mesmo_produto=False, motivo='x')))
    # o que NÃO é "quase o mesmo": outra ponta, outra cor, outra linha, caixa em vez de unidade, outra marca
    g = lambda nome: dict(nome=nome, loja='x', preco=1, ean=None)
    gimba = g('Caneta Esferográfica Pilot BPS Grip Ponta Média 1.0mm Azul 1 UN')
    assert ID.quase_o_mesmo(gimba, g('Caneta Esferográfica Pilot BPS Grip 1.0 Azul'), CANETA) and ID.quase_o_mesmo(gimba, g('Caneta Esferográfica Azul Grip'), CANETA)
    for outro in ('Caneta Esferográfica Pilot BPS Grip 0.7 Azul', 'Caneta Esferográfica Pilot BPS Grip Preta 1.0mm 1 UN', 'Caneta Esferográfica Pilot Super Grip 1.0 Azul',
                  'Caneta Esferográfica Pilot BPS Grip 1.0 Azul Caixa com 12', 'Caneta Esferográfica Top 2000 Azul - Compactor', 'Caneta Esferográfica Pilot BPS Glass 1.0 Azul'):
        assert not ID.quase_o_mesmo(gimba, g(outro), CANETA), outro
    # cor que só um dos anúncios cita (e que o pedido não pede): pode ser outro produto — "branco" é a cor de sempre e não conta
    chamex = 'Folha Sulfite Chamex 500 Folhas'
    assert not ID.quase_o_mesmo(g('Papel Sulfite Chamex A4 210X297mm 75g Resma Rosa PCT C/500 FL'), g('Papel Sulfite Chamex A4 Resma 500 Folhas'), chamex)
    assert ID.quase_o_mesmo(g('Papel Sulfite Chamex A4 210x297mm 75g Resma Branco PCT C/500 FL'), g('Papel Sulfite Chamex A4 Resma 500 Folhas'), chamex)
    # com o MESMO código de barras numa 3ª loja, é essa a opção que vale (a que as regras afirmam vem antes da que depende da IA)
    m = _motor_caneta([dict(loja='papelex', preco=1050, ean='7897424080250', nome='Caneta Esferográfica Bps Grip 1.0 Azul - Pilot', url='https://papelex.exemplo/bps/p')])
    opcoes = m._opcoes_por_item(m._grupos())[CANETA]
    assert cesta.atende_o_pedido(opcoes[0]) and not opcoes[0].get('detalhe_nao_citado') and {x['loja'] for x in opcoes[0]['ofertas']} == {'bazarhorizonte', 'papelex', 'livrariascuritiba'}
    assert m._quase(m._grupos(), {CANETA: opcoes}) == {}                                                     # há opção como pedido: nada a dizer sobre "só 2 lojas"


def test_ia_reprova_a_terceira_loja_e_a_opcao_sai(monkeypatch):
    from orcamento import ia
    from orcamento.produtos import cesta
    m = _motor_caneta()
    m.usar_ia = True
    monkeypatch.setattr(ia, 'disponivel', lambda: True)
    monkeypatch.setattr(ia, 'mesmo_produto', lambda nomes, pid=None: (False, 'a ponta não é a mesma'))
    opcoes = m._opcoes_por_item(m._grupos())
    escolha = m._conferir_com_ia(opcoes, m.escolher(opcoes, m.itens))
    assert escolha[CANETA] is None and opcoes[CANETA] == [] and m.rejeitadas_ia[CANETA][0]['nivel'] == 0
    monkeypatch.setattr(ia, 'mesmo_produto', lambda nomes, pid=None: (True, 'a mesma caneta'))
    m = _motor_caneta()
    m.usar_ia = True
    opcoes = m._opcoes_por_item(m._grupos())
    escolha = m._conferir_com_ia(opcoes, m.escolher(opcoes, m.itens))
    assert cesta.atende_o_pedido(escolha[CANETA]) and escolha[CANETA]['ia']['motivo'] == 'a mesma caneta'


def test_item_sem_nenhuma_opcao_diz_o_que_existe_em_2_lojas(cliente, monkeypatch):
    """Caso real: "Folha Sulfite Chamex 500 Folhas" só existia em 2 lojas e não havia opção de substituição. O item ficava com um motivo que não
    era dele — "1 opção reprovada pela IA: capacidade de folhas diferente (40 × 25 folhas)", de um grampeador da categoria. Agora o motivo diz o
    que aconteceu, o que existe em 2 lojas, e a tela oferece mudar o pedido e pesquisar de novo."""
    from orcamento import db, servico
    from orcamento.calculo import verificar
    from orcamento.produtos import cesta
    pid = _projeto(cliente)
    m = _motor()
    quase = m._quase(m._grupos(), {SULFITE: []})[SULFITE]
    assert len(quase) == 3 and all(len(q['ofertas']) == 2 for q in quase)
    assert [(x['loja'], x['preco']) for x in quase[0]['ofertas']] == [('livrariascuritiba', 2670), ('samsclub', 3198)]   # os mais baratos primeiro
    # par em que uma loja cobra mais que o triplo da outra não é mostrado como "o mesmo produto em 2 lojas" (caso real: lápis de R$ 0,69 × kit de R$ 12,29)
    outra = lambda preco: dict(loja='papelex', preco=preco, ean='7898205206418', nome='Papel Sulfite A4 75g 500 Folhas - Allmax', url='https://papelex.exemplo/allmax/p')
    perto = lambda preco: [q['produto'] for q in _motor([outra(preco)])._quase(_motor([outra(preco)])._grupos(), {SULFITE: []})[SULFITE]]
    assert any('Allmax' in n for n in perto(2600)) and not any('Allmax' in n for n in perto(9000))   # no Atacadão, R$ 25,49
    res = _resultado_do_motor()

    async def pesquisar(itens, *a, **k):
        return dict(res, escolha={SULFITE: None, 'Clips 100 Unidades': res['escolha']['Clips 100 Unidades']}, opcoes={SULFITE: [], 'Clips 100 Unidades': res['opcoes']['Clips 100 Unidades']},
                    quase={SULFITE: quase[:1]},
                    rejeitadas_ia={SULFITE: [dict(produtos=['Grampeador Para 40 Folhas', 'Grampeador CIS C-15', 'Grampeador de Metal CIS'], nivel=3, substituto='Grampeador',
                                                  motivo='Capacidade de folhas diferente (40 folhas vs 25 folhas)')]})
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: _NavegadorFalso())
    prop = asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))
    l = next(x for x in prop['linhas'] if x['desc'] == SULFITE)
    assert l['acao'] == 'RETIRADO' and l['sem_opcao'] and not l.get('decidir') and l['reprovadas_ia'] == [] and l['quase'] == quase[:1]
    assert l['motivo'].startswith(servico.NAO_ACHADO) and 'Nada foi substituído' in l['motivo'] and 'Grampeador' not in l['motivo'] and '40 folhas' not in l['motivo']
    assert 'O mais perto do pedido: "Folha Sulfite A4 Branco Suzano Report Premium Pacote 500 Folhas" em 2 lojas (Livrarias Curitiba R$ 26,70 e Sam\'s Club R$ 31,98) — falta a 3ª loja.' in l['motivo']

    async def com_recusa(itens, *a, **k):   # o trio do PRÓPRIO item que a IA recusou continua sendo dito (é informação sobre o item)
        r = await pesquisar(itens)
        return dict(r, rejeitadas_ia={SULFITE: [dict(produtos=['A', 'B', 'C'], nivel=0, substituto=None, motivo='gramaturas diferentes')]})
    monkeypatch.setattr(cesta, 'pesquisar', com_recusa)
    l2 = next(x for x in asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))['linhas'] if x['desc'] == SULFITE)
    assert '1 conjunto(s) de 3 anúncios foram descartados porque a IA viu produtos diferentes (gramaturas diferentes)' in l2['motivo'] and len(l2['reprovadas_ia']) == 1
    # aplicado: o item fica como foi pedido, com o motivo; a verificação e a tela dizem o que fazer
    asyncio.run(servico.aplicar_proposta(pid, 1, dict(prop, linhas=[l]), Ctx()))
    p = db.carregar(pid)[0]
    s = p.rubricas[0].subitens[0]
    assert (s.descricao, s.especificacao, s.precos, s.fontes) == ('Folha Sulfite', '500 Folhas', [None] * 3, [])
    assert servico.nao_achado(s) and not servico.aguarda_decisao(s, []) and servico.perto_do_pedido(s).startswith('"Folha Sulfite A4 Branco Suzano Report Premium Pacote 500 Folhas" em 2 lojas (')
    r10 = [a.mensagem for a in verificar(p) if a.regra == 'R10' and 'Folha Sulfite' in a.item]
    assert r10 and 'o sistema não substituiu nada' in r10[0] and 'mude o pedido' in r10[0] and 'opções de substituição' not in r10[0]
    pag = cliente.get(f'/p/{pid}/mat/1').text
    quadro = pag.split('id="decidir0"')[1].split('id="repesquisar0"')[0]
    for texto in ('O sistema não achou "Folha Sulfite 500 Folhas" igual em 3 lojas', '<b>Nada foi substituído</b>', 'O produto pedido existe em 2 lojas', 'Livrarias Curitiba:',
                  '<b>R$ 26,70</b>', 'Usar estas 2 lojas e completar a 3ª à mão', 'form="duas0_0"', 'Salvar o que mudei e pesquisar este item de novo', 'value="repesquisar-0"'):
        assert texto in quadro, texto
    assert f'id="duas0_0" method="post" action="/p/{pid}/mat/1/duas-lojas"' in pag
    assert '1. Usar uma destas opções' not in quadro and 'id="decidir1"' not in pag
    # quando a pesquisa só tem produtos de OUTRO tipo (categoria da rubrica), o quadro diz isso em vez de mostrar uma lista vazia
    giz = dict(_resultado_do_motor()['opcoes'][SULFITE][0], atende=False, precos=[299, 449, 699])
    assert giz['nivel'] == 3
    db.produtos_guardar(pid, 1, SULFITE, [giz])
    s.justificativa = servico.AGUARDA_DECISAO + ': o item pedido não foi achado igual em 3 lojas'
    db.salvar(pid, p)
    quadro = cliente.get(f'/p/{pid}/mat/1').text.split('id="decidir0"')[1].split('id="repesquisar0"')[0]
    for texto in ('1. Substituir', 'Só há produtos de outro tipo, da categoria da rubrica', 'Ver também produtos de outro tipo, da categoria da rubrica (1)', 'Trocar por este', '2. Não substituir'):
        assert texto in quadro, texto
    assert '1. Usar uma destas opções' not in quadro and 'Usar esta opção' not in quadro


def test_segunda_etapa_procura_o_mesmo_item_de_outra_marca_e_oferece_como_opcao(cliente, monkeypatch):
    """Pedido da OSC (08/10/2026): item → achou igual em 3 lojas, ótimo → senão, o MESMO item de outra marca ou especificação → senão, itens
    parecidos → tudo o que foi achado vira OPÇÃO, junto, para ela escolher. Caso real: "Folha Sulfite Chamex 500 Folhas" só existia em
    2 lojas e a pesquisa não oferecia nada; sem a marca, o papel Report existia nas 3."""
    from orcamento import db, servico
    from orcamento.modelo import Subitem
    from orcamento.produtos import cesta
    # os pedidos mais largos, do mais perto do pedido para o mais longe
    largos = servico.pedidos_mais_largos(Subitem(descricao='Folha Sulfite', marca='Chamex', especificacao='500 Folhas', qtd=1))
    assert largos == [('Folha Sulfite 500 Folhas', ['a marca Chamex']), ('Folha Sulfite Chamex', ['a especificação 500 Folhas']),
                      ('Folha Sulfite', ['a marca Chamex', 'a especificação 500 Folhas'])]
    assert servico.pedidos_mais_largos(Subitem(descricao='Folha Sulfite Chamex 500 Folhas', qtd=1)) == largos        # a marca e a medida escritas na descrição contam
    assert servico.pedidos_mais_largos(Subitem(descricao='Suco de Uva 1L', qtd=1)) == [('Suco de Uva', ['a especificação 1L'])]
    assert servico.pedidos_mais_largos(Subitem(descricao='Caneta Esferográfica Azul', qtd=1)) == []                   # sem marca nem especificação: não há o que alargar
    pid = _projeto(cliente)
    p = db.carregar(pid)[0]
    p.rubricas[0].subitens[0].marca = 'Chamex'
    db.salvar(pid, p)
    chamex = 'Folha Sulfite Chamex 500 Folhas'
    base = _resultado_do_motor()
    report, giz, clips = base['opcoes'][SULFITE][2], base['opcoes'][SULFITE][0], base['opcoes']['Clips 100 Unidades'][0]
    report = dict(report, codigos_diferentes=False, confirmacao='EAN nas 3 lojas', ia=None)        # sem a marca, o Report existe igual nas 3 lojas
    pedidos = []

    async def pesquisar(itens, *a, **k):
        ds = [i['desc'] for i in itens]
        pedidos.append(ds)
        if chamex in ds:                                                                             # 1ª etapa: o item como foi pedido
            return dict(base, escolha={chamex: giz, 'Clips 100 Unidades': clips}, opcoes={chamex: [giz], 'Clips 100 Unidades': [clips]})
        return dict(base, escolha={}, opcoes={'Folha Sulfite 500 Folhas': [report], 'Folha Sulfite Chamex': [dict(giz, nivel=1)], 'Folha Sulfite': [report]})
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: _NavegadorFalso())
    prop = asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))
    # a 2ª busca só leva o item que faltou, nas 3 formas mais largas (o Clips foi achado como pedido: não é procurado de novo)
    assert pedidos == [[chamex, 'Clips 100 Unidades'], ['Folha Sulfite 500 Folhas', 'Folha Sulfite Chamex', 'Folha Sulfite']]
    l = next(x for x in prop['linhas'] if x['desc'] == chamex)
    assert l['acao'] == 'RETIRADO' and l['opcao_dados'] is None and l['decidir'] == 2                # nada é trocado: o Report é só uma opção
    ops = db.produtos_do_banco(pid, 1)[chamex]['opcoes']
    assert [(o['nivel'], bool(o.get('mais_largo')), o['atende']) for o in ops] == [(1, True, False), (3, False, False)]   # o mesmo item de outra marca antes do produto de outro tipo
    assert ops[0]['mais_largo'] == dict(pedido='Folha Sulfite 500 Folhas', sem=['a marca Chamex']) and ops[0]['perdidos'] == ['a marca Chamex']   # (o mesmo produto achado em "Folha Sulfite" não se repete)
    assert not cesta.atende_o_pedido(ops[0]) and [x['preco'] for x in ops[0]['ofertas']] == [2670, 2999, 3199]
    # a tela do item mostra a opção com o que saiu do pedido
    asyncio.run(servico.aplicar_proposta(pid, 1, dict(prop, linhas=[l]), Ctx()))
    quadro = cliente.get(f'/p/{pid}/mat/1').text.split('id="decidir0"')[1].split('id="repesquisar0"')[0]
    for texto in ('O mesmo item, sem a marca Chamex', 'Achado ao procurar "Folha Sulfite 500 Folhas"', 'Papel Sulfite Report 75g A4 500 Folhas Resma', 'Substituir por esta opção',
                  'primeiro o mesmo item (de outra marca ou especificação)', 'Ver também produtos de outro tipo, da categoria da rubrica (1)'):
        assert texto in quadro, texto


def test_fotos_dos_produtos_vao_junto_com_os_nomes_na_mesma_pergunta(monkeypatch):
    """Pedido da OSC (08/10/2026): conferir também se a IMAGEM dos produtos é igual. A foto de cada anúncio vai com os nomes, na mesma pergunta
    à IA (não gasta uma pergunta a mais). Foto que mostra outro produto derruba a opção; sem fotos, vale a pergunta pelos nomes."""
    from orcamento import ia
    from orcamento.produtos import cesta
    assert ia.foto_pequena('https://loja.vteximg.com.br/arquivos/ids/155678/caneta.jpg?v=1') == 'https://loja.vteximg.com.br/arquivos/ids/155678-400-400/caneta.jpg?v=1'
    assert ia.foto_pequena('https://loja.exemplo/img/caneta.jpg') == 'https://loja.exemplo/img/caneta.jpg'
    perguntas = []

    def perguntar(tipo, instrucao, dados, projeto_id=None, tentativas=4, forte=False, partes=None):
        perguntas.append((tipo, dados, partes, instrucao))
        return dict(mesmo_produto=False, motivo='a foto do anúncio 2 mostra a caneta preta', fotos='diferentes') if partes else dict(mesmo_produto=True, motivo='nomes iguais')
    monkeypatch.setattr(ia, 'disponivel', lambda: True)
    monkeypatch.setattr(ia, 'perguntar', perguntar)
    monkeypatch.setattr(ia, 'foto_da_pagina', lambda url: url.replace('/p', '/foto.jpg') if 'gimba' in url else None)      # a loja que não traz a foto na busca
    monkeypatch.setattr(ia, 'baixar_foto', lambda url: ('image/jpeg', b'JPEG' + url.encode()) if url else None)
    m = _motor_caneta()
    m.usar_ia = True
    for x in m.ofertas[(CANETA, 0)]:
        if x['loja'] != 'gimba':
            x['imagem'] = x['url'].replace('/p', '/foto-da-busca.jpg')
    opcoes = m._opcoes_por_item(m._grupos())
    escolha = m._conferir_com_ia(opcoes, m.escolher(opcoes, m.itens))
    tipo, dados, partes, instrucao = perguntas[0]
    assert tipo == 'mesmo_produto_fotos' and len(partes) == 2 and all(p['inline_data']['mime_type'] == 'image/jpeg' for p in partes)   # 2 anúncios: o de mesmo código de barras entra uma vez só
    assert len(dados['fotos']) == 2 and 'foto.jpg' in ' '.join(dados['fotos']) and 'FOTOS dos anúncios' in instrucao and 'o ângulo' in instrucao
    assert escolha[CANETA] is None and opcoes[CANETA] == [] and m.rejeitadas_ia[CANETA][0]['motivo'].startswith('a foto do anúncio 2')   # a foto derrubou a opção
    # as fotos são iguais: a opção vale, e fica dito que a IA comparou os nomes e as fotos
    perguntas.clear()
    monkeypatch.setattr(ia, 'perguntar', lambda tipo, instrucao, dados, projeto_id=None, tentativas=4, forte=False, partes=None:
                        perguntas.append(tipo) or dict(mesmo_produto=True, motivo='mesma caneta', fotos='iguais'))
    m = _motor_caneta()
    m.usar_ia = True
    for x in m.ofertas[(CANETA, 0)]:
        x['imagem'] = x['url'] + '.jpg'
    opcoes = m._opcoes_por_item(m._grupos())
    o = m._conferir_com_ia(opcoes, m.escolher(opcoes, m.itens))[CANETA]
    assert cesta.atende_o_pedido(o) and o['ia'] == dict(mesmo_produto=True, motivo='mesma caneta', fotos=2, fotos_parecer='iguais') and perguntas == ['mesmo_produto_fotos']
    assert all('imagem' in x for x in o['ofertas'])                                       # o endereço da foto fica guardado na opção
    # nenhuma loja tem foto: a pergunta é só pelos nomes, como antes
    perguntas.clear()
    monkeypatch.setattr(ia, 'foto_da_pagina', lambda url: None)
    m = _motor_caneta()
    m.usar_ia = True
    opcoes = m._opcoes_por_item(m._grupos())
    o = m._conferir_com_ia(opcoes, m.escolher(opcoes, m.itens))[CANETA]
    assert perguntas == ['mesmo_produto'] and o['ia'] == dict(mesmo_produto=True, motivo='mesma caneta')


def test_produto_de_beleza_nao_e_material_de_escritorio():
    """Teste real de 08/10/2026: "Lápis Grafite" recebia "Lápis de Olhos Preto Intenso", de farmácia, como opção."""
    from orcamento.produtos import identidade as ID
    for pedido, anuncio in (('Lápis Grafite', 'Lápis de Olhos Vult Cor Preto Intenso 1,1g'), ('Lápis Preto', 'Lápis Para Olhos Vult Preto Intenso'),
                            ('Tesoura', 'Tesoura para Unhas Curva'), ('Lápis Preto', 'Lápis Labial Pencil')):
        assert ID.nivel(pedido, anuncio, [], None) is None, anuncio
    assert ID.nivel('Lápis Preto', 'Lápis Preto HB nº2 Faber-Castell', [], None) == 0 and ID.nivel('Tesoura', 'Tesoura Escolar 13cm', [], None) == 0
    assert ID.nivel('Lápis para Olhos Preto', 'Lápis Para Olhos Vult Preto Intenso', [], None) == 0        # quando é isso que se pede, vale



def test_usar_as_2_lojas_e_completar_a_terceira_a_mao(cliente, monkeypatch):
    """Pedido da OSC (08/10/2026): quando o produto pedido existe em só 2 lojas, ela pode usar essas 2 — o sistema guarda os comprovantes e grava
    as 2 pesquisas — e completar a 3ª à mão. Nada é inventado: o item só fica pronto com a 3ª preenchida e comprovada por ela."""
    from orcamento import db, servico, zerar
    from orcamento.calculo import verificar
    from orcamento.modelo import Evidencia
    from orcamento.produtos import cesta
    pid = _projeto(cliente)
    m = _motor()
    quase = m._quase(m._grupos(), {SULFITE: []})[SULFITE]
    assert set(quase[0]['ofertas'][0]) >= {'loja', 'nome', 'preco', 'url', 'ean', 'sku', 'seller'}                 # o bastante para guardar o comprovante depois
    res = _resultado_do_motor()

    async def pesquisar(itens, *a, **k):
        return dict(res, escolha={SULFITE: None, 'Clips 100 Unidades': res['escolha']['Clips 100 Unidades']}, opcoes={SULFITE: [], 'Clips 100 Unidades': res['opcoes']['Clips 100 Unidades']},
                    quase={SULFITE: quase[:2]})
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: _NavegadorFalso())
    prop = asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))
    l = next(x for x in prop['linhas'] if x['desc'] == SULFITE)
    asyncio.run(servico.aplicar_proposta(pid, 1, dict(prop, linhas=[l]), Ctx()))
    assert len(servico.em_duas_lojas(pid, 1, SULFITE)) == 2 and servico.em_duas_lojas(pid, 1, 'Clips 100 Unidades') == []   # (o Clips foi achado em 3: nada a guardar)
    pedidos_comprovados = []

    async def comprovar(br, pid_, item, loja, pares, cep, ctx, sufixo='', bloqueadas=None, modo=None):
        pedidos_comprovados.append((loja, [(lin['desc'], lin['qtd']) for lin, _ in pares]))
        sha, rel = db.guardar_arquivo(pid_, f'produto_{loja}{sufixo}.pdf', b'%PDF-1.4 ' + loja.encode())
        return {(loja, x['url']): dict(ev=Evidencia(arquivo=rel, sha256=sha, url=x['url'], capturado_em='2026-10-08T10:00:00-03:00', origem='navegador'), preco=None, problema=None)
                for _, x in pares}
    monkeypatch.setattr(servico, '_comprovar', comprovar)
    ctx = Ctx()
    out = asyncio.run(servico.usar_duas_lojas(pid, 1, SULFITE, 0, ctx))
    assert pedidos_comprovados == [('livrariascuritiba', [(SULFITE, 2)]), ('samsclub', [(SULFITE, 2)])] and out['ir_para'].endswith('#sub0')
    p = db.carregar(pid)[0]
    s = p.rubricas[0].subitens[0]
    assert s.precos == [2670, 3198, None] and [f.plataforma for f in s.fontes[:2]] == ['Livrarias Curitiba', "Sam's Club"] and len(s.fontes) == 3 and not s.fontes[2].nome
    assert all(f.evidencia.arquivo for f in s.fontes[:2]) and s.produtos[2] is None and s.valor_plano is None and (s.descricao, s.especificacao, s.nivel) == ('Folha Sulfite', '500 Folhas', 0)
    assert s.justificativa.startswith(servico.DUAS_LOJAS) and s.confirmacao == 'EAN em 2 lojas; 3ª pesquisa à mão' and not servico.subitem_pronto(s)
    assert 'Falta a 3ª' in ctx.avisos[0] and 'R$ 26,70' in ctx.avisos[0]
    r10 = [a.mensagem for a in verificar(p) if a.regra == 'R10' and 'Folha Sulfite' in a.item]
    assert len(r10) == 1 and r10[0].startswith('falta a 3ª pesquisa') and 'MESMO produto' in r10[0]
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert '<b>Falta a 3ª pesquisa.</b>' in pag and 'id="decidir0"' not in pag and 'form="duas0_0"' not in pag             # o quadro some; fica o aviso do que falta
    # uma nova pesquisa que continua sem achar 3 lojas não desfaz as 2 pesquisas nem o motivo
    asyncio.run(servico.aplicar_proposta(pid, 1, dict(prop, linhas=[l]), Ctx()))
    s = db.carregar(pid)[0].rubricas[0].subitens[0]
    assert s.precos == [2670, 3198, None] and s.justificativa.startswith(servico.DUAS_LOJAS)
    # comprovante que falha: o item fica como estava
    p = db.carregar(pid)[0]
    p.rubricas[0].subitens[0].precos, p.rubricas[0].subitens[0].fontes, p.rubricas[0].subitens[0].justificativa = [None] * 3, [], None
    db.salvar(pid, p)

    async def falha(br, pid_, item, loja, pares, cep, ctx, sufixo='', bloqueadas=None, modo=None):
        return {(loja, x['url']): dict(ev=None, preco=None, problema='a página diz que o produto está indisponível') for _, x in pares}
    monkeypatch.setattr(servico, '_comprovar', falha)
    ctx = Ctx()
    assert asyncio.run(servico.usar_duas_lojas(pid, 1, SULFITE, 1, ctx))['versao'] is None and 'O item ficou como estava' in ctx.avisos[0]
    assert db.carregar(pid)[0].rubricas[0].subitens[0].precos == [None] * 3
    # "apagar e refazer" também tira do banco os produtos guardados em 2 lojas (e eles não contam como "opções de produto")
    antes = set(db.produtos_do_banco(pid, 1))
    assert antes == {SULFITE, 'Clips 100 Unidades', servico.chave_das_duas_lojas(SULFITE), servico.chave_das_duas_lojas('Clips 100 Unidades')}
    assert zerar.contar_bancos(pid, dict(rubricas_inteiras=[1], pedidos=[], chaves_de_vaga=[], com_confirmadas=True))[0] == 2
    zerar.zerar_bancos(pid, dict(rubricas_inteiras=[], pedidos=[(1, SULFITE)], chaves_de_vaga=[], com_confirmadas=True))
    assert set(db.produtos_do_banco(pid, 1)) == {'Clips 100 Unidades', servico.chave_das_duas_lojas('Clips 100 Unidades')}
