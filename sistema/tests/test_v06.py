"""Pedidos de 03/10/2026: mesmo produto nas 3 lojas (marca, cor, tipo e embalagem), campo de marca, especificação do produto trocado,
nova pesquisa de uma pesquisa só (loja, vaga, cotação), vaga encerrada que virava lista de busca, link com espaço, revisar em lote e
na própria tela, situação dos CNPJs pela base oficial."""
import asyncio
import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv('ORCAMENTO_DADOS', str(tmp_path))
    import importlib, orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    monkeypatch.setattr(dbm, 'PASTA_LOCAL', str(tmp_path / 'local'))
    import app as appmod
    importlib.reload(appmod)
    return TestClient(appmod.app)


def _novo(cliente):
    r = cliente.post('/projetos', data={'nome': 'T', 'teto': '100.000,00', 'cep': '01001-000'}, follow_redirects=False)
    return int(r.headers['location'].rsplit('/', 1)[-1])


class Ctx:
    id = 0

    def __init__(self):
        self.avisos = []

    def progresso(self, *a, **k): pass
    def etapa(self, *a, **k): pass
    def fonte(self, *a, **k): pass
    def aviso(self, m): self.avisos.append(m)


# ---------------------------------------------------------------- mesmo produto: marca, cor, tipo e embalagem
def test_cafe_a_vacuo_nao_e_o_mesmo_produto_do_cafe_em_pouch():
    from orcamento.produtos import identidade as ID
    vacuo = dict(loja='tenda', nome='Café Tradicional a Vácuo 3 Corações 500g', preco=1989)
    atac = dict(loja='atacadao', nome='Café 3 Corações Tradicional 500g', preco=2148, ean='7896005800010')
    sams = dict(loja='samsclub', nome='Café Torrado E Moído 3 Corações Tradicional Pouch 500g', preco=2278, ean='7896005800010')
    almofada = dict(loja='tenda', nome='Café Tradicional 3 Corações Almofada 500g', preco=1989)
    assert ID.identidade(vacuo, atac, 'Café 500g') == 'R' and ID.identidade(vacuo, sams, 'Café 500g') == 'R' and ID.conflito(vacuo, sams)
    assert [sorted(g['por_loja']) for g in ID.agrupar([vacuo, atac, sams], 'Café 500g')] == [['atacadao', 'samsclub'], ['tenda']]   # caso real de 03/10
    assert [sorted(g['por_loja']) for g in ID.agrupar([almofada, atac, sams], 'Café 500g')] == [['atacadao', 'samsclub', 'tenda']]   # pouch = almofada
    # embalagem citada num anúncio só não separa quando não é um tipo exclusivo (vidro, pote)
    g1 = dict(loja='a', nome='Geleia Morango Queensberry Classic Vidro 320g', preco=1, ean='7896214532504')
    g2 = dict(loja='b', nome='Geleia Classic de Morango Queensberry 320g', preco=2)
    g3 = dict(loja='c', nome='Geleia Queensberry Morango 320g', preco=3, ean='7896214532504')
    assert len(ID.agrupar([g1, g2, g3], 'Geléia de Morango 320g')[0]['por_loja']) == 3


def test_marcas_diferentes_nao_valem_mais(cliente, monkeypatch):
    from orcamento import db, servico
    from orcamento.calculo import verificar
    from orcamento.modelo import Config, Fonte, Evidencia, Subitem
    from orcamento.produtos import cesta
    assert Config().marcas_diferentes is False
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Material de escritório', 'regra': 'mercado', 'meses': '10'})
    p = db.carregar(pid)[0]
    fs = [Fonte(nome=n, cnpj=c, data_pesquisa='2026-10-03', plataforma=n, evidencia=Evidencia(arquivo='x.pdf', origem='pdf'))
          for n, c in [('Lepok', '11.111.111/0001-11'), ('Gimba', '22.222.222/0001-22'), ('Papelex', '33.333.333/0001-33')]]
    p.rubricas[0].subitens = [Subitem(descricao='Pasta', especificacao='Aba Elástico', qtd=1, precos=[301, 399, 499], valor_plano=400, fontes=fs,
                                      confirmacao='mesma especificação, marcas diferentes')]
    p.config.marcas_diferentes = True                                         # projeto antigo, com a opção ligada: é ignorada
    db.salvar(pid, p)
    s = p.rubricas[0].subitens[0]
    assert servico.produtos_diferentes(s) and not servico.subitem_pronto(s)   # "Pesquisar tudo" refaz o item
    assert any(a.regra == 'R10' and a.gravidade == 'erro' and 'marcas diferentes' in a.mensagem for a in verificar(p))
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert 'As 3 pesquisas não são do mesmo produto' in pag and 'Buscar outra loja (mesmo produto)' not in pag
    assert 'name="marcas_diferentes"' not in cliente.get(f'/p/{pid}').text
    chamada = {}

    async def pesquisar(itens, lojas, cep, ctx=None, modo='por_item', usar_ia=True, projeto_id=None, setor=None, extras=(), marcas_diferentes=None, **resto):
        chamada.update(marcas=marcas_diferentes, itens=[i['desc'] for i in itens])
        raise ValueError('fim do teste')
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    with pytest.raises(ValueError, match='fim do teste'):
        asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx()))
    assert chamada == dict(marcas=False, itens=['Pasta Aba Elástico'])


# ---------------------------------------------------------------- marca e especificação depois da pesquisa
def _opcao(nivel, nomes):
    return dict(nivel=nivel, ofertas=[dict(loja=l, nome=n, ean=e) for l, n, e in nomes])


def test_marca_e_especificacao_do_produto_orcado():
    from orcamento import servico
    from orcamento.modelo import Subitem, pedido_do_subitem, descricao_completa
    # produto trocado: a descrição é o nome SIMPLES do produto (sem marca, linha, embalagem e medida), a especificação é a medida dele e a marca é a dele
    s = Subitem(descricao='Pão de Forma', especificacao='480g', qtd=20)
    servico.campos_do_produto(s, _opcao(1, [('samsclub', 'Pão de Forma Artesano Pullman Pacote 500g', '7896002302197'),
                                            ('tenda', 'Pão de Forma Artesano Pullman 500g', None), ('paodeacucar', 'Pão de Forma Original Pullman Artesano Pacote 500g', None)]))
    assert (s.descricao, s.marca, s.especificacao) == ('Pão de Forma', 'Pullman', '500g')
    assert pedido_do_subitem(s) == 'Pão de Forma 480g' and descricao_completa(s) == 'Pão de Forma Pullman 500g'
    # produto como pedido: descrição e especificação ficam; a marca em branco é preenchida com a das 3 lojas (e passa a fazer parte do pedido)
    s = Subitem(descricao='Café', especificacao='500g', qtd=10)
    servico.campos_do_produto(s, _opcao(0, [('a', 'Café 3 Corações Tradicional 500g', '1'), ('b', 'Café Torrado 3 CORAÇÕES Pouch 500g', '1'), ('c', 'Café 3 Corações 500g', None)]))
    assert (s.descricao, s.marca, s.especificacao, s.descricao_original) == ('Café', '3 Corações', '500g', None)
    assert pedido_do_subitem(s) == 'Café 3 Corações 500g' == descricao_completa(s)
    # marca escolhida pela OSC não é trocada
    s = Subitem(descricao='Café', marca='Pilão', especificacao='500g', qtd=10)
    servico.campos_do_produto(s, _opcao(0, [('a', 'Café Pilão 500g', None)] * 3))
    assert s.marca == 'Pilão'


def test_item_trocado_antes_e_acertado_e_a_marca_entra_na_tela(cliente):
    from orcamento import db, servico
    from orcamento.modelo import Subitem, pedido_do_subitem
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Alimentação', 'regra': 'mercado', 'meses': '10'})
    cliente.post(f'/p/{pid}/mat/1', data={'descricao': 'Alimentação', 'meses': '10', 'n_sub': '0', 'ndesc': ['Suco de Uva'], 'nmarca': ['Del Valle'], 'nesp': ['1L'], 'nqtd': ['20']})
    p = db.carregar(pid)[0]
    assert (p.rubricas[0].subitens[0].marca, pedido_do_subitem(p.rubricas[0].subitens[0])) == ('Del Valle', 'Suco de Uva Del Valle 1L')
    # item trocado numa pesquisa antiga: descrição do produto com a medida, especificação ainda a pedida
    p.rubricas[0].subitens.append(Subitem(descricao='Pão de Forma Artesano Pullman Pacote 500g', descricao_original='Pão de Forma', especificacao='480g', nivel=1, qtd=20,
                                          produtos=['Pão de Forma Artesano Pullman Pacote 500g', 'Pão de Forma Artesano Pullman 500g', 'Pão de Forma Original Pullman Artesano Pacote 500g']))
    db.salvar(pid, p)
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert 'name="smarca1" type="text" value="Pullman"' in pag and 'name="sesp1" type="text" value="500g"' in pag
    assert 'name="sdesc1" type="text" value="Pão de Forma"' in pag and 'Você pediu <b>Pão de Forma 480g</b>' in pag and 'Desfazer a substituição' in pag
    from test_interface import _campos
    cliente.post(f'/p/{pid}/mat/1', data=_campos(pag))                         # salvar sem mexer: grava o acerto e mantém o pedido original
    s = db.carregar(pid)[0].rubricas[0].subitens[1]
    assert (s.descricao, s.marca, s.especificacao, s.descricao_original, s.nivel) == ('Pão de Forma', 'Pullman', '500g', 'Pão de Forma', 1)
    assert pedido_do_subitem(s) == 'Pão de Forma 480g'
    # a OSC muda a marca: o que ela escreveu passa a ser o novo pedido
    dados = _campos(cliente.get(f'/p/{pid}/mat/1').text); dados['smarca1'] = 'Wickbold'
    cliente.post(f'/p/{pid}/mat/1', data=dados)
    s = db.carregar(pid)[0].rubricas[0].subitens[1]
    assert s.descricao_original is None and s.nivel == 0 and pedido_do_subitem(s) == 'Pão de Forma Wickbold 500g'


# ---------------------------------------------------------------- nova pesquisa de UMA pesquisa do item: outra loja, mesmo produto
def test_outra_loja_so_para_uma_pesquisa(cliente, monkeypatch):
    from orcamento import db, servico
    from orcamento.modelo import Fonte, Evidencia, Subitem
    from orcamento.produtos import lojas as L
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Alimentação', 'regra': 'mercado', 'meses': '10'})
    p = db.carregar(pid)[0]; r = p.rubricas[0]
    lj = [k for k in ('atacadao', 'samsclub', 'paodeacucar', 'tenda', 'oba') if k in L.LOJAS]
    of = lambda k, preco, ean='789': dict(loja=k, nome='Bisnaguinha Seven Boys 300g', titulo=None, marca=None, ean=ean, preco=preco, url=f'https://{k}.exemplo/bisnaguinha/p', sku='1', seller='1')
    fonte = lambda k: Fonte(nome=k.upper(), cnpj='', plataforma=L.LOJAS[k]['nome'], data_pesquisa='2026-10-03',
                            evidencia=Evidencia(arquivo='x.pdf', origem='pdf', url=f'https://{k}.exemplo/bisnaguinha/p'))
    r.subitens = [Subitem(descricao='Bisnaguinha', especificacao='300g', qtd=10, precos=[479, 488, 849], valor_plano=605, fontes=[fonte(k) for k in lj[:3]],
                          eans=['789', '789', '789'], produtos=['Bisnaguinha Seven Boys 300g'] * 3, confirmacao='EAN nas 3 lojas')]
    db.salvar(pid, p)
    opcao = dict(nivel=0, misto=False, ofertas=[of(lj[0], 479), of(lj[1], 488), of(lj[2], 849)], reservas=[of(lj[3], 520), of(lj[4], 990)])
    db.produtos_guardar(pid, 1, 'Bisnaguinha 300g', [opcao])
    pedidos = []

    async def comprovar(br, pid_, item, loja, pares, cep, ctx, sufixo='', bloqueadas=None):
        pedidos.append(loja)
        x = pares[0][1]
        ok = loja != lj[3]                                                      # a reserva mais barata fica sem comprovante: tenta a seguinte
        return {(loja, x['url']): dict(ev=Evidencia(arquivo='novo.pdf', sha256='a' * 64, url=x['url'], origem='navegador') if ok else None, preco=x['preco'],
                                       problema=None if ok else 'página vazia')}
    monkeypatch.setattr(servico, '_comprovar', comprovar)
    s = r.subitens[0]
    assert asyncio.run(servico._nova_pesquisa(None, p, pid, r, s, 2, Ctx(), False, [opcao])) is True
    assert pedidos == [lj[3], lj[4]] and s.fontes[2].plataforma == L.LOJAS[lj[4]]['nome'] and s.precos == [479, 488, 990]
    assert [f.plataforma for f in s.fontes[:2]] == [L.LOJAS[lj[0]]['nome'], L.LOJAS[lj[1]]['nome']]   # as outras duas pesquisas não mudam
    assert s.valor_plano == 605 and 'trocada por' in s.justificativa
    # na tela: o botão por pesquisa existe quando o item tem as 3 pesquisas do mesmo produto
    db.salvar(pid, p)
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert pag.count('>Buscar outra loja<') == 3 and 'value="trocarloja-0-2"' in pag
    assert pag.count('aria-label="Refazer só a pesquisa') == 3 and 'value="pagina-0-2"' in pag and 'value="pagina-0-0"' not in pag   # PDF anexado pela OSC não é trocado


# ---------------------------------------------------------------- vaga encerrada que virava a lista de busca do site
def _pdf(texto):
    import pymupdf
    d = pymupdf.open(); pg = d.new_page()
    pg.insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto, fontsize=9)
    return d.tobytes()


VAGA = ('Designer Gráfico\n{empresa}\nSão Paulo - SP\nSalário R$ {sal}\nRegime CLT\nDescrição da vaga: criação de peças gráficas para redes sociais, '
        'materiais impressos e apresentações institucionais, de segunda a sexta-feira, das 9h às 18h, com experiência em edição de imagens.')
LISTA = ('Busque por um cargo\nSalvar busca\nVagas de emprego de designer grafico\n278 resultados\nVAGA PATROCINADA\nAssistente de Design Gráfico\nRecrutamento e Seleção\n'
         '1 vaga - São Paulo\nR$ 2.777 + 2 benefícios\nQuero me candidatar\nDesigner Grafico\nMIRELLE ACESSÓRIOS\n1 vaga - Barueri\nR$ 5.000 + 1 benefício\nQuero me candidatar')


def test_lista_de_vagas_no_lugar_do_anuncio_nao_vale(cliente):
    from orcamento import db, servico, vagas as V
    from orcamento.calculo import verificar
    assert V.pagina_nao_e_a_vaga(LISTA) and V.pagina_nao_e_a_vaga('Ops! Esta vaga não está mais disponível.')
    assert V.pagina_nao_e_a_vaga(VAGA.format(empresa='Estúdio Alfa', sal='2.000,00')) is None
    assert 'não mostra a empresa' in V.pagina_nao_e_a_vaga(VAGA.format(empresa='Estúdio Alfa', sal='2.000,00'), 'Mychelle de Souza')
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': 'Designer Gráfico', 'horas_mes': '70', 'meses': '10'})
    for emp, cnpj, sal, txt in [('Estúdio Alfa', '11111111000111', 200000, VAGA), ('Estúdio Beta', '22222222000122', 210000, VAGA), ('Estúdio Gama', '33333333000133', 220000, VAGA),
                                ('Estúdio Delta', '44444444000144', 230000, VAGA), ('Fechada', '55555555000155', 190000, LISTA)]:
        v = dict(titulo='Designer Gráfico', empresa=emp, url=f'https://x/{cnpj[:4]}', plataforma='InfoJobs', faixa_min=sal, faixa_max=sal, unidade='MONTH')
        V.guardar_no_banco('Designer Gráfico', v, dict(status='🟢', cnpj=cnpj, razao_social=emp.upper(), motivo='teste'),
                           _pdf(txt.format(empresa=emp, sal=f'{sal // 100:,}'.replace(',', '.') + ',00') if txt is VAGA else txt))
    assert [v['empresa'] for v in V.tres_do_banco('Designer Gráfico')] == ['Estúdio Alfa', 'Estúdio Beta', 'Estúdio Gama']   # a "Fechada" (mais barata) não entra
    # pesquisa já gravada com o PDF da lista: pendência S07 e o cargo não está pronto
    p = db.carregar(pid)[0]; r = p.rubricas[0]
    banco = {v['empresa']: v for v in V.vagas_do_banco('Designer Gráfico')}
    r.pesquisas = [servico._pesquisa_da_vaga(pid, banco[e]) for e in ('Estúdio Alfa', 'Fechada', 'Estúdio Gama')]
    db.salvar(pid, p)
    assert any(a.regra == 'S07' and a.gravidade == 'erro' for a in verificar(p)) and not servico.rh_pronto(r)
    pag = cliente.get(f'/p/{pid}/rh/1').text
    assert 'o PDF guardado não é a página da vaga' in pag and 'Refazer só esta pesquisa' in pag and 'Guardar a página de novo' in pag and 'data-revisar=' not in pag.split('id="t-banco"')[1]
    # nova pesquisa SÓ da pesquisa 2: entra a próxima vaga válida de outra empresa; as outras duas ficam; a vaga trocada sai do banco
    res = asyncio.run(servico.outra_vaga(pid, 1, 1, Ctx()))
    ps = db.carregar(pid)[0].rubricas[0].pesquisas
    assert res['versao'] and [q.nome for q in ps] == ['ESTÚDIO ALFA', 'ESTÚDIO BETA', 'ESTÚDIO GAMA']
    assert 'Fechada' not in [v['empresa'] for v in V.vagas_do_banco('Designer Gráfico', so_verdes=False)]
    assert not any(a.regra == 'S07' for a in verificar(db.carregar(pid)[0]))


# ---------------------------------------------------------------- link com espaço, faixa salarial, revisar em lote e na tela, CNPJ pela base
def test_link_com_espaco_faixa_e_revisao(cliente, monkeypatch):
    import app
    from orcamento import cnpj_base, db, servico
    from orcamento.calculo import chave_alerta
    from orcamento.modelo import PesquisaSalarial, Evidencia
    assert servico.url_limpa(' https://www.gimba.com.br/pasta/pasta-plascony 1-un/?PID=978 ') == 'https://www.gimba.com.br/pasta/pasta-plascony%201-un/?PID=978'
    js = cliente.get('/').text
    assert "v = v.replace(/\\s/g, '%20')" in js                                # a tela aceita o endereço com espaço (vira %20) em vez de recusar
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': 'Orientador Socioeducativo', 'quantidade': '3', 'horas_mes': '60', 'meses': '10'})
    p = db.carregar(pid)[0]; r = p.rubricas[0]
    r.pesquisas = [PesquisaSalarial(nome=n, cnpj=c, plataforma='InfoJobs', data_pesquisa='2026-10-03', faixa_min=mn, faixa_max=mx, valor=mn, evidencia=Evidencia(url=f'https://x/{c[:2]}'))
                   for n, c, mn, mx in [('ABECAL', '05.000.703/0001-33', 217300, 310000), ('CEJA', '15.409.309/0002-98', 217300, 217300), ('FFF', '62.661.251/0001-74', 242100, 242100)]]
    db.salvar(pid, p)
    from orcamento.calculo import media_rh
    assert media_rh(r) == round((217300 + 217300 + 242100) / 3)                 # faixa de 2.173 a 3.100: vale o menor
    pag = cliente.get(f'/p/{pid}/rh/1').text
    assert 'A vaga informa a faixa de R$ 2.173,00 a R$ 3.100,00' in pag and 'o cálculo usa sempre o <b>menor</b>, R$ 2.173,00' in pag
    # CNPJ que está na base oficial deste computador não fica como "ainda não consultado"
    monkeypatch.setattr(cnpj_base, 'por_cnpj', lambda c: None)                  # sem a base neste computador: fica "ainda não consultado"
    ctx = app.contexto(p, pid, 1)
    assert sum('ainda não consultado' in a.mensagem for a in ctx['alertas']) == 3
    monkeypatch.setattr(cnpj_base, 'por_cnpj', lambda c: dict(razao='X', situacao='ATIVA'))
    ctx = app.contexto(p, pid, 1)
    assert not any('ainda não consultado' in a.mensagem for a in ctx['alertas'])
    # os pontos aparecem na própria tela do cargo, com o botão de marcar; e a lista da verificação aceita vários de uma vez
    revisar = [a for a in ctx['alertas'] if a.gravidade == 'atencao']
    assert len(revisar) >= 2
    pag = cliente.get(f'/p/{pid}/rh/1').text
    assert 'O que a verificação aponta neste cargo' in pag and 'data-revisar=' in pag and 'id="f-revisar"' in pag
    proj = cliente.get(f'/p/{pid}').text
    assert 'data-selecionar-todos' in proj and 'Marcar os selecionados como revisados' in proj
    loc = cliente.post(f'/p/{pid}/revisar', data={'chave': [chave_alerta(a) for a in revisar]}, follow_redirects=False).headers['location']
    assert loc.endswith('#verificacao') and len(db.carregar(pid)[0].revisados) == len(revisar)
    assert app.contexto(db.carregar(pid)[0], pid, 2)['res']['atencao'] == 0
    # marcado pela tela do item: volta para a própria tela, no mesmo lugar
    loc = cliente.post(f'/p/{pid}/revisar', data={'uma': chave_alerta(revisar[0]), 'acao': 'desmarcar', 'volta': f'/p/{pid}/rh/1#pesquisa0'}, follow_redirects=False).headers['location']
    assert loc.startswith(f'/p/{pid}/rh/1?ok=1&msg=') and loc.endswith('#pesquisa0')
    loc = cliente.post(f'/p/{pid}/revisar', data={'uma': 'x|y|z', 'volta': 'https://fora.exemplo/'}, follow_redirects=False).headers['location']
    assert loc.startswith(f'/p/{pid}?msg=')                                    # nunca redireciona para fora do sistema


# ---------------------------------------------------------------- apagar de vez: a tela recusava qualquer nome com espaço
def test_apagar_de_vez_aceita_o_nome_com_espacos(cliente):
    """O texto de conferência do campo saía com as aspas escapadas duas vezes (data-igual=&#34;Projeto de…): a tela comparava o nome
    digitado com '"Projeto' e recusava. Agora o atributo sai inteiro; e o servidor não liga para espaços a mais."""
    from orcamento import db
    nome = 'Projeto de Cidadania & Capacitação "Piloto"'
    pid = int(cliente.post('/projetos', data={'nome': nome, 'teto': '1.000,00', 'cep': '01001-000'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    cliente.post(f'/p/{pid}/remover')
    pag = cliente.get('/').text
    campo = re.search(r'<input[^>]*id="conf-%d"[^>]*>' % pid, pag).group(0)
    assert 'data-igual="Projeto de Cidadania &amp; Capacitação &#34;Piloto&#34;"' in campo and 'autocomplete="off"' in campo and '=&#34;' not in campo
    # nome mudado na configuração: a lista mostra o nome novo, e é ele que vale para apagar
    r = cliente.post(f'/p/{pid}/apagar-de-vez', data={'confirmacao': 'outro nome'}, follow_redirects=False)
    assert 'Nada%20foi%20apagado' in r.headers['location'] and db.existe(pid)
    r = cliente.post(f'/p/{pid}/apagar-de-vez', data={'confirmacao': '  Projeto de  Cidadania & Capacitação "Piloto" '}, follow_redirects=False)
    assert 'apagado%20de%20vez' in r.headers['location'] and not db.existe(pid)
    outro = int(cliente.post('/projetos', data={'nome': 'Nome antigo', 'teto': '1.000,00', 'cep': '01001-000'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    cliente.post(f'/p/{outro}/config', data={'nome': 'Nome novo', 'teto': '1.000,00', 'divisor_horas': 'legal', 'cep': '01001-000'})
    assert [x['nome'] for x in db.listar()] == ['Nome novo']


# ---------------------------------------------------------------- "Guardar a página de novo" em materiais e serviços (mesma loja, mesma página)
def test_guardar_a_pagina_de_novo_em_produtos_e_sistema(cliente, monkeypatch):
    from orcamento import db, servico
    from orcamento.modelo import Fonte, Evidencia, Subitem
    from orcamento.produtos import evidencia as EV, lojas as L
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Alimentação', 'regra': 'mercado', 'meses': '10'})
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Sistema de gestão', 'regra': 'sistema', 'meses': '12'})
    p = db.carregar(pid)[0]; r, rs = p.rubricas
    lj = [k for k in ('atacadao', 'samsclub', 'paodeacucar') if k in L.LOJAS]
    fonte = lambda k, origem='navegador': Fonte(nome=k.upper(), cnpj='', plataforma=L.LOJAS[k]['nome'], data_pesquisa='2026-09-01',
                                                evidencia=Evidencia(arquivo=f'velho_{k}.pdf', sha256='b' * 64, origem=origem, url=f'https://{k}.exemplo/leite 1l/p'))
    r.subitens = [Subitem(descricao='Leite', especificacao='1L', qtd=20, precos=[539, 645, 679], valor_plano=581, fontes=[fonte(lj[0]), fonte(lj[1]), fonte(lj[2], 'pdf')],
                          produtos=['Leite Italac 1L'] * 3, confirmacao='descrição')]
    rs.subitens = [Subitem(descricao='Sistema de gestão', qtd=1, precos=[27092, 49900, 32000], valor_plano=27092,
                           fontes=[Fonte(nome='ONGSYS SISTEMAS LTDA', cnpj='29.335.055/0001-34', plataforma='Ongsys', data_pesquisa='2026-09-01',
                                         evidencia=Evidencia(arquivo='velho.pdf', sha256='c' * 64, origem='navegador', url='https://site.ongsys.com.br/precos'))] * 3)]
    db.salvar(pid, p)
    chamadas = []

    async def comprovar(br, pid_, item, loja, pares, cep, ctx, sufixo='', bloqueadas=None):
        x = pares[0][1]; chamadas.append((loja, x['url'], pares[0][0]['qtd']))
        if loja == lj[1]:                                                       # a página desta loja não serve hoje: o comprovante antigo fica
            return {(loja, x['url']): dict(ev=None, preco=None, problema='a página diz que o produto está indisponível')}
        return {(loja, x['url']): dict(ev=Evidencia(arquivo='novo.pdf', sha256='a' * 64, url=x['url'], origem='navegador'), preco=529, problema=None)}
    monkeypatch.setattr(servico, '_comprovar', comprovar)
    s = r.subitens[0]
    ok, msg = asyncio.run(servico._recapturar(None, p, pid, r, s, 0, Ctx()))
    assert ok and chamadas == [(lj[0], f'https://{lj[0]}.exemplo/leite 1l/p', 20)] and 'O preço mudou de R$ 5,39 para R$ 5,29' in msg
    assert s.fontes[0].evidencia.arquivo == 'novo.pdf' and s.fontes[0].evidencia.url.endswith('/leite%201l/p') and s.fontes[0].data_pesquisa != '2026-09-01'
    assert s.precos == [529, 645, 679] and s.fontes[0].plataforma == L.LOJAS[lj[0]]['nome']          # mesma loja; só o preço do comprovante novo
    assert [f.evidencia.arquivo for f in s.fontes[1:]] == [f'velho_{lj[1]}.pdf', f'velho_{lj[2]}.pdf']   # as outras duas não mudam
    ok, msg = asyncio.run(servico._recapturar(None, p, pid, r, s, 1, Ctx()))
    assert not ok and 'indisponível' in msg and 'foi mantido' in msg and s.fontes[1].evidencia.arquivo == f'velho_{lj[1]}.pdf'
    with pytest.raises(ValueError, match='anexado por você'):                   # PDF anexado pela OSC nunca é trocado
        asyncio.run(servico.recapturar_pesquisa(pid, 1, 0, 2, Ctx()))
    # sistema: a página de preços do fornecedor é guardada de novo; o preço tem de continuar na página
    def pdf(texto):
        import pymupdf
        d = pymupdf.open(); d.new_page().insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto, fontsize=9)
        return d.tobytes()
    paginas = {'texto': 'Planos Ongsys\nIniciante R$ 299,00 por mês\nProfissional R$ 499,00 por mês'}

    async def pagina(br, url, faixa, preco=None, completa=False):
        return pdf(paginas['texto']), dict(capturado_em='2026-10-03T15:00:00-03:00', problema=None, texto=paginas['texto'])
    monkeypatch.setattr(EV, 'pagina', pagina)
    ss = rs.subitens[0]
    ok, msg = asyncio.run(servico._recapturar(None, p, pid, rs, ss, 1, Ctx()))
    assert ok and ss.fontes[1].evidencia.arquivo != 'velho.pdf' and ss.precos == [27092, 49900, 32000] and ss.valor_plano == 27092
    paginas['texto'] = 'Planos Ongsys\nProfissional R$ 549,00 por mês'            # o preço da cotação já não está na página: fica o comprovante antigo
    antes = ss.fontes[1].evidencia.arquivo
    ok, msg = asyncio.run(servico._recapturar(None, p, pid, rs, ss, 1, Ctx()))
    assert not ok and 'não aparece na página' in msg and ss.fontes[1].evidencia.arquivo == antes
    # nas telas: o botão aparece em cada pesquisa com link que não foi anexada por você
    db.salvar(pid, p)
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert pag.count('Guardar a página de novo') == 2 and 'value="pagina-0-0"' in pag and 'value="pagina-0-2"' not in pag
    assert cliente.get(f'/p/{pid}/mat/2').text.count('Guardar a página de novo') == 3


# ---------------------------------------------------------------- um item nunca vira o mesmo produto de outro item da rubrica
class _NavegadorFalso:
    """No lugar do Playwright nos testes que só exercitam a gravação (nenhuma página é aberta)."""
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

    class chromium:
        @staticmethod
        async def launch():
            class B:
                async def close(self): pass
            return B()


def test_item_nao_repete_outro_item_da_rubrica(cliente, monkeypatch):
    """Caso real de 03/10/2026: Pasta, Grampeador e Lápis viraram os três a mesma "Régua 30cm Cristal - Dello" (troca pela categoria na
    pesquisa de um item só, que não sabia dos outros itens da rubrica)."""
    from orcamento import db, servico
    from orcamento.calculo import verificar
    from orcamento.modelo import Fonte, Evidencia, Subitem, pedido_do_subitem
    from orcamento.produtos import cesta, lojas as L
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Material de escritório', 'regra': 'mercado', 'meses': '10'})
    p = db.carregar(pid)[0]; r = p.rubricas[0]
    lj = [k for k in ('gimba', 'papelex', 'livrariascuritiba') if k in L.LOJAS]
    regua = lambda orig: Subitem(descricao='Régua 30cm Cristal - Dello', descricao_original=orig, especificacao_original='', marca_original='', nivel=3, qtd=1,
                                 precos=[275, 289, 380], valor_plano=300, confirmacao='descrição', eans=[None, '7897832800617', None],
                                 produtos=['Régua Dello Poliestireno Cristal 30cm'] * 3,
                                 fontes=[Fonte(nome=k.upper(), plataforma=L.LOJAS[k]['nome'], data_pesquisa='2026-10-03',
                                               evidencia=Evidencia(arquivo='x.pdf', origem='pdf', url=f'https://{k}.exemplo/regua-30cm/p')) for k in lj])
    r.subitens = [regua('Pasta'), Subitem(descricao='Folha Sulfite', especificacao='500 Folhas', qtd=2), regua('Grampeador de Mesa'), regua('Lápis Preto')]
    db.salvar(pid, p)
    assert servico.itens_repetidos(r) == {2: 0, 3: 0}                              # o 1º fica; os outros dois repetem o 1º
    assert [pedido_do_subitem(s) for s in servico.subitens_a_pesquisar(r)] == ['Folha Sulfite 500 Folhas', 'Grampeador de Mesa', 'Lápis Preto']
    al = [a for a in verificar(p) if a.regra == 'S08']
    assert len(al) == 2 and all(a.gravidade == 'erro' and 'mesmo produto do item 1' in a.mensagem for a in al)
    assert 'é o mesmo produto do item 1' in cliente.get(f'/p/{pid}/mat/1').text
    # a pesquisa de um item só leva ao motor o resto da rubrica: descrições e produtos já usados
    chamada = {}

    async def pesquisar(itens, lojas, cep, ctx=None, modo='por_item', usar_ia=True, projeto_id=None, setor=None, extras=(), marcas_diferentes=None, outros=(), usados=()):
        chamada.update(itens=[i['desc'] for i in itens], outros=list(outros), usados=set(usados), setor=setor)
        raise ValueError('fim do teste')
    monkeypatch.setattr(cesta, 'pesquisar', pesquisar)
    with pytest.raises(ValueError, match='fim do teste'):
        asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx(), somente=['Grampeador de Mesa']))
    assert chamada['itens'] == ['Grampeador de Mesa'] and 'Régua Dello 30cm Cristal' in chamada['outros'] and 'Folha Sulfite 500 Folhas' in chamada['outros']
    assert (lj[0], f'https://{lj[0]}.exemplo/regua-30cm/p') in chamada['usados'] and '7897832800617' in chamada['usados'] and chamada['setor']
    # o motor: produto já usado não é opção; dois itens não recebem o mesmo tipo de produto da categoria; a categoria não repete item da rubrica
    of = lambda loja, nome, ean=None: dict(loja=loja, nome=nome, url=f'https://{loja}.exemplo/{nome[:8]}/p', ean=ean, preco=300)
    op = lambda sub, nome, ean=None: dict(nivel=3, substituto=sub, distancia=30.0, ofertas=[of(k, nome, ean) for k in lj])
    m = cesta.Motor([dict(desc='Grampeador de Mesa'), dict(desc='Lápis Preto')], lj, '01001-000', outros=chamada['outros'], usados=chamada['usados'])
    opcoes = {'Grampeador de Mesa': [op('Régua 30cm', 'Régua Dello Poliestireno Cristal 30cm', '7897832800617'), op('Borracha branca', 'Borracha Mercur Branca'), op('Cola bastão 10g', 'Cola Bastão Pritt 10g')],
              'Lápis Preto': [op('Borracha branca', 'Borracha Faber Branca'), op('Cola bastão 10g', 'Cola Bastão Pritt 10g')]}
    esc = m.escolher(opcoes, m.itens)
    assert esc['Grampeador de Mesa']['substituto'] != 'Régua 30cm'                  # a régua já é o item 1 da rubrica
    assert {esc['Grampeador de Mesa']['substituto'], esc['Lápis Preto']['substituto']} == {'Borracha branca', 'Cola bastão 10g'}   # tipos diferentes
    from orcamento.produtos import categorias as C
    assert 'Régua 30cm' not in C.candidatos('papelaria', m.descs) and 'Borracha branca' in C.candidatos('papelaria', m.descs)
    # mesmo que uma proposta traga o produto de outro item, ele não é gravado
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: _NavegadorFalso())
    proposta = dict(modo='por_item', teto=None, linhas=[dict(acao='mantido', desc='Grampeador de Mesa', qtd=1, valor=None,
                                                            opcao_dados=dict(op('Régua 30cm', 'Régua Dello Poliestireno Cristal 30cm', '7897832800617'),
                                                                             confirmacao='descrição', lojas_com_o_produto=3, perdidos=[]))])
    proposta['linhas'][0]['opcao_dados']['ofertas'] = [dict(loja=k, nome='Régua Dello Poliestireno Cristal 30cm', url=f'https://{k}.exemplo/regua-30cm/p', ean=None, preco=300) for k in lj]
    c = Ctx()
    asyncio.run(servico.aplicar_proposta(pid, 1, proposta, c))
    assert any('já é outro item desta rubrica' in a for a in c.avisos)
    # o item que repetia outro e não achou nada na nova pesquisa volta a ser o que a OSC pediu, sem as pesquisas da régua
    g = db.carregar(pid)[0].rubricas[0].subitens[2]
    assert (g.descricao, g.descricao_original, g.nivel, g.fontes, g.precos, g.valor_plano) == ('Grampeador de Mesa', None, 0, [], [None, None, None], None)
    assert servico.itens_repetidos(db.carregar(pid)[0].rubricas[0]) == {3: 0}        # só o Lápis continua repetido (ainda não foi pesquisado de novo)
    # opção para não trocar pela categoria: o motor não recebe o setor nem os itens extras
    p = db.carregar(pid)[0]; p.config.trocar_pela_categoria = False; db.salvar(pid, p)
    with pytest.raises(ValueError, match='fim do teste'):
        asyncio.run(servico.pesquisar_rubrica(pid, 1, Ctx(), somente=['Lápis Preto']))
    assert chamada['setor'] is None
    assert 'name="trocar_pela_categoria"' in cliente.get(f'/p/{pid}').text
