"""Pedidos de 02/10/2026 (lista de 17 pontos): quantidade de profissionais, campos sem texto pronto, títulos similares, vários itens de uma vez,
navegação depois de salvar, especificação dos produtos, avisos, nome Orça.AI, vagas (link, em dúvida, posição, parciais), pontos revisados,
nova pesquisa de um item, sistema sem item, cancelar uma vez e uma tela para cada tipo de rubrica."""
import asyncio
import re
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv('ORCAMENTO_DADOS', str(tmp_path))
    import importlib, orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    import app as appmod
    importlib.reload(appmod)
    from conftest import registrar_exemplo
    registrar_exemplo(appmod)
    return TestClient(appmod.app)


def _exemplo(cliente):
    return int(cliente.post('/exemplo', follow_redirects=False).headers['location'].rsplit('/', 1)[-1])


def _novo(cliente, nome='Projeto teste'):
    r = cliente.post('/projetos', data={'nome': nome, 'teto': '100.000,00', 'cep': '01001-000'}, follow_redirects=False)
    return int(r.headers['location'].rsplit('/', 1)[-1])


class Ctx:
    id = 0

    def __init__(self):
        self.avisos = []

    def progresso(self, *a, **k): pass
    def etapa(self, *a, **k): pass
    def fonte(self, *a, **k): pass
    def aviso(self, m): self.avisos.append(m)


# ---------------------------------------------------------------- 1. quantidade de profissionais
def test_quantidade_de_profissionais_no_calculo_e_no_excel(tmp_path):
    from openpyxl import load_workbook
    from orcamento.calculo import total_rubrica, unitario_rubrica, total_projeto, verificar
    from orcamento.exportar import exportar
    from orcamento.modelo import Projeto, RubricaRH
    r = RubricaRH(item=1, cargo='Assistente Social', horas_mes=40, meses=10, quantidade=3, valor_mensal_plano=100000)
    assert total_rubrica(r) == 3_000_000 and unitario_rubrica(r) == 300000
    p = Projeto(nome='T', teto=3_000_000, rubricas=[r])
    assert total_projeto(p) == 3_000_000
    arq = exportar(p, verificar(p), {}, str(tmp_path / 'x.xlsx'))
    wb = load_workbook(arq)
    plano = wb['Plano de Aplicação']
    assert '(3 profissionais x R$1.000,00)' in plano['B3'].value and plano['C3'].value == '=3*1000.0' and plano['D3'].value == '=ROUND(C3*10,2)'
    assert wb['Grade Comparativa']['C4'].value == 3
    assert '3 profissionais' in wb['Memória de Cálculo']['B2'].value and wb['Memória de Cálculo']['K2'].value == 30000


def test_juntar_cargos_repetidos_sem_mudar_o_total(cliente):
    from orcamento import db
    from orcamento.calculo import total_projeto
    from orcamento.modelo import RubricaRH
    pid = _exemplo(cliente)
    antes = db.carregar(pid)[0]
    assert 'Juntar cargos repetidos' in cliente.get(f'/p/{pid}').text
    r = cliente.post(f'/p/{pid}/juntar-cargos', follow_redirects=False)
    assert r.headers['location'].endswith('#mao-de-obra')
    p = db.carregar(pid)[0]
    assert total_projeto(p) == total_projeto(antes)
    rh = [x for x in p.rubricas if isinstance(x, RubricaRH)]
    assert [(x.cargo, x.quantidade) for x in rh if x.quantidade > 1] == [('Assistente Social', 3), ('Orientador socioeducativo', 3)]
    assert [x.item for x in p.rubricas] == list(range(1, len(p.rubricas) + 1)) and len(p.rubricas) == len(antes.rubricas) - 4
    pag = cliente.get(f'/p/{pid}').text
    assert '3 profissionais' in pag and 'Juntar cargos repetidos' not in pag


# ---------------------------------------------------------------- 2. nada escrito dentro dos campos; adicionar cargo/rubrica pelo nome
def test_adicionar_cargo_e_rubrica_pelo_nome_sem_texto_pronto(cliente):
    from orcamento import db
    pid = _novo(cliente)
    pag = cliente.get(f'/p/{pid}').text
    assert 'id="novo-cargo"' in pag and 'id="nova-rubrica"' in pag and 'Novo cargo' not in pag
    r = cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': '', 'horas_mes': '', 'meses': ''}, follow_redirects=False)
    assert 'Nada foi adicionado' in r.headers['location'].replace('%20', ' ') or 'Nada%20foi' in r.headers['location']
    assert db.carregar(pid)[0].rubricas == []
    r = cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': 'Assistente Social', 'quantidade': '3', 'horas_mes': '120', 'meses': '12'}, follow_redirects=False)
    assert r.headers['location'] == f'/p/{pid}/rh/1?novo=1'
    c = db.carregar(pid)[0].rubricas[0]
    assert (c.cargo, c.quantidade, c.horas_mes, c.meses) == ('Assistente Social', 3, 120, 12)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Alimentação', 'regra': 'mercado', 'meses': '12'})
    m = db.carregar(pid)[0].rubricas[1]
    assert (m.descricao, m.regra, m.meses) == ('Alimentação', 'mercado', 12)
    for url in (f'/p/{pid}/rh/1', f'/p/{pid}/mat/2', f'/p/{pid}'):
        assert 'placeholder=' not in cliente.get(url).text, url                 # exemplos ficam na dica, embaixo do campo


# ---------------------------------------------------------------- 3. títulos similares
def _guardar(V, cargo, empresa, cnpj, sal, status='🟢', pdf=True, titulo=None):
    from test_vagas import _pdf_vaga
    v = dict(titulo=titulo or cargo, empresa=empresa, url=f'https://vagas.exemplo/{V._slug(empresa)}', plataforma='Catho', faixa_min=sal, faixa_max=sal,
             unidade='MONTH', cidade='São Paulo', uf='SP')
    V.guardar_no_banco(cargo, v, dict(status=status, cnpj=cnpj, razao_social=empresa.upper(), motivo='teste'),
                       _pdf_vaga('Salário R$ ' + f'{sal / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')) if pdf else None)
    return v['url']


def test_titulos_similares_sao_grupos_que_nao_se_misturam(cliente):
    """Decisão da OSC (06/10/2026): vagas de títulos diferentes, mesmo similares, não vão juntas para o orçamento — ou um título, ou outro.
    As vagas do título do cargo ficam gravadas (mesmo sendo 1 ou 2); os títulos similares com 3 vagas viram OPÇÃO, e a troca é das 3 de uma vez."""
    from orcamento import vagas as V
    assert 'Educador social' in V.sugestoes_similares('Orientadora Socioeducativa')
    _guardar(V, 'Orientador socioeducativo', 'Alfa', '11111111000111', 240000)
    _guardar(V, 'Educador social', 'Beta', '22222222000122', 210000)
    _guardar(V, 'Educador social', 'Gama', '33333333000133', 220000)
    _guardar(V, 'Educador social', 'Alfa Filial', '11111111000292', 200000)          # outra filial da Alfa: no grupo "Educador social" ela conta como empresa
    _guardar(V, 'Agente social', 'Delta', '44444444000144', 190000)                  # título similar com 1 vaga só: não vira opção
    assert [v['empresa'] for v in V.tres_do_banco('Orientador socioeducativo')] == ['Alfa']
    grupos = V.grupos_de_titulos('Orientador socioeducativo', ['Educador social', 'Agente social'])
    assert [(g['titulo'], g['similar'], g['completo'], [v['empresa'] for v in g['vagas']]) for g in grupos] == [
        ('Orientador socioeducativo', False, False, ['Alfa']), ('Educador social', True, True, ['Alfa Filial', 'Beta', 'Gama']), ('Agente social', True, False, ['Delta'])]
    assert V.grupo_do_titulo('Educadora Social - Zona Sul', 'Orientador socioeducativo', ['Educador social']) == 'Educador social'
    assert V.grupo_do_titulo('Orientador(a) Socioeducativo | SP', 'Orientador socioeducativo', ['Educador social']) == 'Orientador socioeducativo'
    assert V.grupo_do_titulo('Psicólogo', 'Orientador socioeducativo', ['Educador social']) is None
    from orcamento import db, servico
    from orcamento.calculo import verificar
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': 'Orientador socioeducativo', 'quantidade': '3', 'horas_mes': '60', 'meses': '10'})
    pag = cliente.get(f'/p/{pid}/rh/1').text
    assert 'título similar' in pag and 'value="Educador social" checked' in pag
    # o quadro "Títulos com vagas": o título do cargo (1 de 3, em uso), a opção com 3 vagas e, à parte, o título que ainda não tem 3
    quadro = pag.split('id="t-titulos"')[1].split('id="lista-pesquisas"')[0]
    # o botão do quadro manda para o formulário f-titulo, que fica FORA do formulário do cargo (um <form> dentro de outro fechava o do cargo
    # antes da hora, e os botões de salvar ficavam soltos — defeito de 10/10/2026)
    assert 'Usar as 3 vagas deste título' in quadro and quadro.count('form="f-titulo" name="titulo" value="Educador social"') == 1 and '<form' not in quadro
    assert pag.count('<form id="f-titulo" method="post" action="/p/%d/rh/1/usar-titulo"></form>' % pid) == 1
    from conftest import formularios_soltos
    assert formularios_soltos(pag) == []
    cargo = pag.split('id="f-cargo"')[1]                                                        # do formulário do cargo em diante
    assert cargo.index('Salvar e continuar aqui') < cargo.index('Salvar e voltar para') < cargo.index('</form>')   # os botões de salvar vêm ANTES de ele fechar
    ruim = '<form id="a"><form action="/x"><button>Usar</button></form><button name="depois">Salvar</button></form><button>Solto</button>'
    assert formularios_soltos(ruim) == ['<form /x> dentro de <form a>', 'botão de enviar fora de formulário: "Solto"']
    assert 'Ainda sem 3 vagas (não podem ser usados): Agente social (1)' in quadro and 'value="Agente social"' not in quadro
    # "usar as vagas do banco": só a vaga do título do cargo entra; as outras duas ficam em branco (nada de completar com o título similar)
    cliente.post(f'/p/{pid}/rh/1/vagas/banco')
    p = db.carregar(pid)[0]
    assert [q.nome for q in p.rubricas[0].pesquisas] == ['ALFA', '', ''] and not any(a.regra in ('S04', 'S11') for a in verificar(p))
    # uma vaga de outro título não entra numa pesquisa avulsa
    r = cliente.post(f'/p/{pid}/rh/1/usar-vaga', data={'url': 'https://vagas.exemplo/beta', 'k': '1'}, follow_redirects=False)
    assert 'vagas%20de%20t%C3%ADtulos%20diferentes' in r.headers['location'] and [q.nome for q in db.carregar(pid)[0].rubricas[0].pesquisas] == ['ALFA', '', '']
    # a OSC escolhe o grupo "Educador social": as 3 pesquisas são trocadas de uma vez, e a verificação aponta cada uma (S04), sem mistura (S11)
    r = cliente.post(f'/p/{pid}/rh/1/usar-titulo', data={'titulo': 'Educador social'}, follow_redirects=False)
    assert r.status_code == 303 and '#t-pesq' in r.headers['location']
    p = db.carregar(pid)[0]
    assert p.rubricas[0].titulo_em_uso == 'Educador social' and servico.titulo_em_uso(p.rubricas[0]) == 'Educador social'
    assert [q.nome for q in p.rubricas[0].pesquisas] == ['ALFA FILIAL', 'BETA', 'GAMA'] and all(q.titulo_vaga == 'Educador social' for q in p.rubricas[0].pesquisas)
    assert sum(a.regra == 'S04' for a in verificar(p)) == 3 and not any(a.regra == 'S11' for a in verificar(p)) and servico.rh_pronto(p.rubricas[0])
    pag = cliente.get(f'/p/{pid}/rh/1').text
    quadro = pag.split('id="t-titulos"')[1].split('id="lista-pesquisas"')[0]
    assert 'Hoje estão com o título <b>Educador social</b>' in quadro and 'value="Orientador socioeducativo"' in quadro   # dá para voltar ao título do cargo
    # título que não tem 3 vagas não pode ser escolhido
    r = cliente.post(f'/p/{pid}/rh/1/usar-titulo', data={'titulo': 'Agente social'}, follow_redirects=False)
    assert 'n%C3%A3o%20tem%203%20vagas' in r.headers['location'] and db.carregar(pid)[0].rubricas[0].titulo_em_uso == 'Educador social'
    # projeto antigo, com títulos misturados: a verificação aponta o erro (S11), o cargo não conta como pronto e a tela pede para escolher um título
    p = db.carregar(pid)[0]
    r0 = p.rubricas[0]
    r0.titulo_em_uso = None
    r0.pesquisas[0].titulo_vaga = 'Orientador Socioeducativo'
    db.salvar(pid, p)
    p = db.carregar(pid)[0]
    assert servico.titulos_misturados(p.rubricas[0]) == ['Orientador socioeducativo', 'Educador social'] and not servico.rh_pronto(p.rubricas[0])
    s11 = [a for a in verificar(p) if a.regra == 'S11']
    assert len(s11) == 1 and s11[0].gravidade == 'erro' and 'não vão juntas para o orçamento' in s11[0].mensagem
    assert 'As pesquisas deste cargo são de títulos diferentes' in cliente.get(f'/p/{pid}/rh/1').text
    # voltar ao título do cargo: fica só a vaga dele; as do título similar saem
    cliente.post(f'/p/{pid}/rh/1/usar-titulo', data={'titulo': 'Orientador socioeducativo'})
    p = db.carregar(pid)[0]
    assert p.rubricas[0].titulo_em_uso is None and [q.nome for q in p.rubricas[0].pesquisas] == ['ALFA', '', ''] and not servico.titulos_misturados(p.rubricas[0])
    # a OSC desmarca o título similar: ele deixa de valer para este cargo
    r = p.rubricas[0]
    dados = {'cargo': r.cargo, 'quantidade': '3', 'regime': r.regime, 'horas_mes': '60', 'meses': '10', 'similares_enviados': '1', 'similar': ['Agente social'],
             'depois': 'ficar'}
    cliente.post(f'/p/{pid}/rh/1', data=dados)
    assert db.carregar(pid)[0].rubricas[0].titulos_similares == ['Agente social']
    assert servico.similares_do_cargo(db.carregar(pid)[0].rubricas[0]) == ['Agente social']


# ---------------------------------------------------------------- 4 e 6. vários itens de uma vez, com especificação
def test_varios_itens_de_uma_vez_com_especificacao(cliente):
    from orcamento import db
    from orcamento.modelo import Subitem, pedido_do_subitem, descricao_completa
    assert pedido_do_subitem(Subitem(descricao='Café torrado', especificacao='500 g', qtd=1)) == 'Café torrado 500 g'
    assert pedido_do_subitem(Subitem(descricao='Café torrado 500 g', especificacao='500 g', qtd=1)) == 'Café torrado 500 g'
    assert descricao_completa(Subitem(descricao='Café Pilão 500 g', descricao_original='Café', especificacao='500 g', nivel=1, qtd=1)) == 'Café Pilão 500 g'
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Alimentação', 'regra': 'mercado', 'meses': '12'})
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert pag.count('name="ndesc"') >= 3 and 'data-adicionar-linha' in pag and '<template id="modelo-linha">' in pag
    r = cliente.post(f'/p/{pid}/mat/1', data={'descricao': 'Alimentação', 'meses': '12', 'n_sub': '0', 'depois': 'ficar',
                                              'ndesc': ['Arroz tipo 1', 'Feijão carioca', 'Arroz tipo 1', ''], 'nesp': ['5 kg', '1 kg', '5 kg', ''],
                                              'nqtd': ['2', '3', '1', '1']}, follow_redirects=False)
    assert r.headers['location'].startswith(f'/p/{pid}/mat/1?leitura=')
    subs = db.carregar(pid)[0].rubricas[0].subitens
    assert [(s.descricao, s.especificacao, s.qtd) for s in subs] == [('Arroz tipo 1', '5 kg', 2), ('Feijão carioca', '1 kg', 3)]   # o repetido não entra
    assert [pedido_do_subitem(s) for s in subs] == ['Arroz tipo 1 5 kg', 'Feijão carioca 1 kg']


# ---------------------------------------------------------------- 5. depois de salvar, volta para a parte de onde veio
def test_salvar_volta_para_a_parte_certa_do_projeto(cliente):
    pid = _exemplo(cliente)
    from test_interface import _campos
    dados = _campos(cliente.get(f'/p/{pid}/rh/1').text)
    loc = cliente.post(f'/p/{pid}/rh/1', data=dados, follow_redirects=False).headers['location']
    assert loc.startswith(f'/p/{pid}?msg=') and loc.endswith('#item1')
    loc = cliente.post(f'/p/{pid}/rh/1', data=dict(dados, depois='ficar'), follow_redirects=False).headers['location']
    assert loc.startswith(f'/p/{pid}/rh/1?ok=1')
    dados = _campos(cliente.get(f'/p/{pid}/mat/12').text)
    assert cliente.post(f'/p/{pid}/mat/12', data=dados, follow_redirects=False).headers['location'].endswith('#item12')
    loc = cliente.post(f'/p/{pid}/config', data={'nome': 'X', 'teto': '150.000,00', 'divisor_horas': 'legal', 'cep': '01001-000'}, follow_redirects=False).headers['location']
    assert loc.endswith('#configuracao')
    assert cliente.post(f'/p/{pid}/excluir/15', follow_redirects=False).headers['location'].endswith('#materiais')
    assert cliente.post(f'/p/{pid}/excluir/11', follow_redirects=False).headers['location'].endswith('#mao-de-obra')
    assert 'data-toast-se-rolar' in cliente.get(f'/p/{pid}?msg=Teste').text            # a mensagem aparece também quando a página abre lá embaixo


# ---------------------------------------------------------------- 7, 8 e 16. avisos, nome na aba, cancelar uma vez, erro claro
def test_nome_na_aba_avisos_e_cancelar_uma_vez(cliente):
    from orcamento import db, tarefas
    assert '<title>Orça.AI · Projetos</title>' in cliente.get('/').text
    pid = _exemplo(cliente)
    assert f'<title>Orça.AI · ' in cliente.get(f'/p/{pid}').text and 'Orçamentos OSC' not in cliente.get(f'/p/{pid}').text
    tid = tarefas.criar('teste', 'Tarefa de teste', pid)
    with db.conectar() as c:
        c.execute("UPDATE tarefa SET estado='rodando', cancelar=1 WHERE id=?", (tid,))
    pag = cliente.get(f'/tarefa/{tid}').text
    assert 'Cancelando…' in pag and re.search(r'id="cancelar"[^>]*disabled', pag) and 'Cancelamento pedido' in pag
    assert '<div class="cartao cartao--plano"><ul class="lista-simples lista-simples--avisos" id="avisos">' in pag
    # erro explicado pelo sistema: só a mensagem, sem o nome técnico do erro
    def falha(ctx):
        raise ValueError('a rubrica ainda não tem itens: cadastre ao menos um item')
    tid = tarefas.iniciar('teste', 'Falha de teste', falha, pid)
    for _ in range(50):
        t = tarefas.ler(tid)
        if t['estado'] not in ('na fila', 'rodando'):
            break
        time.sleep(0.1)
    assert t['estado'] == 'falhou' and t['erro'] == 'A rubrica ainda não tem itens: cadastre ao menos um item'


# ---------------------------------------------------------------- 9 a 12. vagas: link, em dúvida, posição, parciais
def test_vagas_parciais_posicao_e_descartar(cliente):
    from orcamento import db, servico, vagas as V
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': 'Psicólogo', 'horas_mes': '90', 'meses': '10'})
    a = _guardar(V, 'Psicólogo', 'Alfa', '11111111000111', 300000)
    b = _guardar(V, 'Psicólogo', 'Beta', '22222222000122', 310000)
    d = _guardar(V, 'Psicólogo', 'Duvida', '44444444000144', 250000, status='🟡', pdf=False)
    # só 2 confirmadas: entram as 2 e a 3ª fica em branco (antes nada entrava)
    loc = cliente.post(f'/p/{pid}/rh/1/vagas/banco', follow_redirects=False).headers['location']
    assert 'ok=1' in loc
    ps = db.carregar(pid)[0].rubricas[0].pesquisas
    assert [q.nome for q in ps] == ['ALFA', 'BETA', ''] and servico.pesquisa_completa(ps[0]) and not servico.pesquisa_completa(ps[2])
    # o número da posição em que a vaga está aparece preenchido; clicar em outro número troca de lugar
    pag = cliente.get(f'/p/{pid}/rh/1').text
    assert pag.count('btn--posicao" aria-pressed="true"') == 2 and 'Esta vaga está na pesquisa 1' in pag and 'Esta vaga está na pesquisa 2' in pag and pag.count('>em uso<') == 2
    cliente.post(f'/p/{pid}/rh/1/usar-vaga', data={'url': a, 'k': '2'})
    assert [q.nome for q in db.carregar(pid)[0].rubricas[0].pesquisas] == ['', 'BETA', 'ALFA']
    # a vaga em dúvida pode ser confirmada pela OSC (formulário com o CNPJ) ou descartada; o link da empresa abre o PDF guardado
    assert 'Confirmar a empresa' in pag and f'/vaga/pdf?url=' in pag and 'no site' in pag
    assert cliente.get('/vaga/pdf', params={'url': a}).headers['content-type'] == 'application/pdf'
    cliente.post(f'/p/{pid}/rh/1/vaga/descartar', data={'url': d})
    assert d not in [x['url'] for x in V.vagas_do_banco('Psicólogo', so_verdes=False)]
    _guardar(V, 'Psicólogo', 'Duvida', '44444444000144', 250000, status='🟡', pdf=False)       # a coleta não desfaz o descarte
    assert d not in [x['url'] for x in V.vagas_do_banco('Psicólogo', so_verdes=False)]
    assert '1 vaga(s) descartada(s)' in cliente.get(f'/p/{pid}/rh/1').text
    cliente.post(f'/p/{pid}/rh/1/vaga/mostrar-descartadas')
    assert d in [x['url'] for x in V.vagas_do_banco('Psicólogo', so_verdes=False)]


def test_osc_confirma_vaga_em_duvida(cliente, monkeypatch):
    from test_vagas import _pdf_vaga
    from orcamento import cnpj_base, vagas as V
    url = _guardar(V, 'Psicólogo', 'Clínica Dúvida', None, 250000, status='🟡', pdf=False)
    monkeypatch.setattr(cnpj_base, 'por_cnpj', lambda c: dict(razao='CLINICA DUVIDA LTDA', situacao='ATIVA') if re.sub(r'\D', '', c) == '11222333000181' else None)

    async def pagina(u, rotulo, empresa=None):
        return _pdf_vaga('Salário R$ 2.500,00'), 'agora'
    monkeypatch.setattr(V, 'capturar', pagina)
    with pytest.raises(ValueError, match='CNPJ inválido'):
        asyncio.run(V.confirmar_vaga(url, '11.222.333/0001-80'))
    res = asyncio.run(V.confirmar_vaga(url, '11.222.333/0001-81', Ctx()))
    v = next(x for x in V.vagas_do_banco('Psicólogo') if x['url'] == url)
    assert res['cnpj'] == '11.222.333/0001-81' and v['cnpj_status'] == '🟢' and v['pdf'] and v['cnpj_motivo'].startswith('confirmado pela OSC')
    _guardar(V, 'Psicólogo', 'Clínica Dúvida', None, 250000, status='🟡', pdf=False)           # uma nova coleta não desfaz a confirmação
    assert next(x for x in V.vagas_do_banco('Psicólogo') if x['url'] == url)['cnpj_status'] == '🟢'
    # vaga encerrada no site: sem a página, não há comprovante
    url2 = _guardar(V, 'Psicólogo', 'Encerrada', None, 260000, status='🟡', pdf=False)

    async def encerrada(u, rotulo, empresa=None):
        return _pdf_vaga('Ops! Esta vaga não está mais disponível. Tente selecionando outra vaga da lista.'), 'agora'
    monkeypatch.setattr(V, 'capturar', encerrada)
    with pytest.raises(ValueError, match='encerrada'):
        asyncio.run(V.confirmar_vaga(url2, '11.222.333/0001-81'))


# ---------------------------------------------------------------- 13. marcar como revisado
def test_marcar_ponto_como_revisado_e_desfazer(cliente):
    import app
    from orcamento import db
    from orcamento.calculo import chave_alerta
    pid = _exemplo(cliente)
    ctx = app.contexto(db.carregar(pid)[0], pid, 1)
    a = next(x for x in ctx['alertas'] if x.gravidade == 'atencao')
    n = ctx['res']['atencao']
    assert 'Marcar como revisado' in cliente.get(f'/p/{pid}').text
    assert cliente.post(f'/p/{pid}/revisar', data={'chave': chave_alerta(a)}, follow_redirects=False).headers['location'].endswith('#verificacao')
    ctx = app.contexto(db.carregar(pid)[0], pid, 2)
    assert ctx['res']['atencao'] == n - 1 and ctx['res']['revisados'] == 1
    assert any(x.gravidade == 'revisado' and chave_alerta(x) == chave_alerta(a) for x in ctx['alertas'])
    assert 'Revisados' in cliente.get(f'/p/{pid}').text
    cliente.post(f'/p/{pid}/revisar', data={'chave': chave_alerta(a), 'acao': 'desmarcar'})
    assert app.contexto(db.carregar(pid)[0], pid, 3)['res']['atencao'] == n


# ---------------------------------------------------------------- 14. nova pesquisa só de um item
def test_nova_pesquisa_de_um_item_em_outras_lojas(cliente, monkeypatch):
    import app
    from orcamento import db, servico, tarefas
    from orcamento.modelo import Fonte
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Alimentação', 'regra': 'mercado', 'meses': '12'})
    cliente.post(f'/p/{pid}/mat/1', data={'descricao': 'Alimentação', 'meses': '12', 'n_sub': '0', 'ndesc': ['Arroz'], 'nesp': ['5 kg'], 'nqtd': ['2']})
    p = db.carregar(pid)[0]
    p.rubricas[0].subitens[0].fontes = [Fonte(nome='X', plataforma=app.LOJAS[k]['nome']) for k in list(app.LOJAS)[:3]]
    db.salvar(pid, p)
    chamadas = {}

    async def pesquisar(pid_, item, ctx, somente=None, sem_lojas=(), respeitar_teto=True):
        chamadas.update(somente=somente, sem_lojas=list(sem_lojas), respeitar_teto=respeitar_teto)
        return dict(linhas=[dict(desc=somente[0], acao='RETIRADO', motivo='não achado em 3 lojas')])
    monkeypatch.setattr(servico, 'pesquisar_rubrica', pesquisar)
    from test_interface import _campos
    dados = dict(_campos(cliente.get(f'/p/{pid}/mat/1').text), depois='repesquisar-0', modo0='outras')
    loc = cliente.post(f'/p/{pid}/mat/1', data=dados, follow_redirects=False).headers['location']
    tid = int(loc.rsplit('/', 1)[-1])
    for _ in range(50):
        t = tarefas.ler(tid)
        if t['estado'] not in ('na fila', 'rodando'):
            break
        time.sleep(0.1)
    assert t['estado'] == 'concluída' and chamadas == dict(somente=['Arroz 5 kg'], sem_lojas=list(app.LOJAS)[:3], respeitar_teto=False)
    assert 'ficaram como estavam' in t['avisos'][0] and t['resultado']['ir_para'].endswith('#sub0')


# ---------------------------------------------------------------- 15 e 17. sistema sem item; uma tela para cada tipo de rubrica
def test_tela_de_sistema_e_de_servico(cliente, monkeypatch):
    from orcamento import db, servico, ia
    monkeypatch.setattr(ia, 'disponivel', lambda: False)                   # teste sem rede: a cotação automática para antes de abrir as páginas
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Sistema de gestão', 'regra': 'sistema', 'meses': '12'})
    pag = cliente.get(f'/p/{pid}/mat/1').text
    for t in ('1. Ferramentas de referência', 'Cotação 1', 'Cotação 3', 'Preço mensal do plano', 'Salvar e cotar sistemas automaticamente', 'Fornecedores que o sistema conhece'):
        assert t in pag, t
    for t in ('Adicionar itens', 'Fornecedores padrão', 'carrinho impresso', 'Itens extras'):
        assert t not in pag, t
    asyncio.run(servico.pesquisar_sistema(pid, 1, Ctx()))                  # sem item cadastrado: não dá mais "a rubrica não tem subitens"
    from test_interface import _campos
    cliente.post(f'/p/{pid}/mat/1', data=dict(_campos(pag), referencia='Cadastro de atendidos\nControle de frequência'))
    r = db.carregar(pid)[0].rubricas[0]
    assert [s.descricao for s in r.subitens] == ['Sistema de gestão'] and r.referencia.startswith('Cadastro')
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Oficina de capoeira', 'regra': 'servico', 'meses': '10'})
    pag = cliente.get(f'/p/{pid}/mat/2').text
    for t in ('Serviços e as 3 propostas', 'Adicionar serviços', 'não há\n    pesquisa automática'):
        assert t in pag, t
    assert 'Pesquisa automática' not in pag and 'Salvar e pesquisar' not in pag
    proj = cliente.get(f'/p/{pid}').text
    assert 'Editar e cotar sistemas' in proj and 'Editar e anexar propostas' in proj


# ---------------------------------------------------------------- pedido de 02/10/2026 (noite): sistema no menor valor; revisado não volta por mudança de valor
def test_sistema_fica_no_menor_valor_e_etapas_concluidas(cliente):
    from orcamento import db, servico
    from orcamento.calculo import verificar
    from orcamento.modelo import Fonte, Evidencia
    from orcamento.otimizador import otimizar
    pid = _novo(cliente)
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Sistema de gestão', 'regra': 'sistema', 'meses': '12'})
    from test_interface import _campos
    dados = dict(_campos(cliente.get(f'/p/{pid}/mat/1').text), referencia='Cadastro de atendidos', sp0_0='270,92', sp0_1='499,00', sp0_2='320,00')
    cliente.post(f'/p/{pid}/mat/1', data=dados)
    p = db.carregar(pid)[0]; s = p.rubricas[0].subitens[0]
    assert s.precos == [27092, 49900, 32000] and s.valor_plano == 27092                      # o menor, não a média (363,31)
    s.valor_plano = 32000; db.salvar(pid, p)                                                 # valor antigo (ex.: escolhido pelo "Fechar no teto" antes)
    assert any(a.regra == 'S06' for a in verificar(p))
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert 'Ao salvar esta tela, o valor passa a ser o menor das 3 cotações (R$ 270,92)' in pag
    p.teto = 27092 * 12
    res = otimizar(p)
    assert res['status'] == 'OK' and res['projeto'].rubricas[0].subitens[0].valor_plano == 27092   # "Fechar no teto" não tira o sistema do menor valor
    # etapas: com as ferramentas, uma proposta anexada e as 3 cotações comprovadas, nenhuma fica parada
    s.fontes = [Fonte(nome=n, cnpj=c, data_pesquisa='2026-10-02', evidencia=Evidencia(arquivo='x.pdf', origem='pdf')) for n, c in
                [('A', '11.111.111/0001-11'), ('B', '22.222.222/0001-22'), ('C', '33.333.333/0001-33')]]
    s.valor_plano = 27092; db.salvar(pid, p)
    pag = cliente.get(f'/p/{pid}/mat/1').text
    assert pag.count('passo passo--feito') == 3 and 'As 3 cotações estão prontas' in pag and 'Próximo passo' not in pag


def test_revisado_continua_revisado_quando_so_o_valor_muda(cliente):
    from orcamento import db
    from orcamento.calculo import Alerta, chave_alerta, verificar
    pid = _novo(cliente)
    p = db.carregar(pid)[0]
    antes = Alerta('D09', 'atencao', 'Item 9 – Sistema', 'mensal R$ 363,31 passa do teto da rubrica R$ 280,00')
    depois = Alerta('D09', 'atencao', 'Item 9 – Sistema', 'mensal R$ 320,00 passa do teto da rubrica R$ 280,00')
    outro = Alerta('D09', 'atencao', 'Item 9 – Sistema', 'outro motivo qualquer')
    assert chave_alerta(antes) == chave_alerta(depois) != chave_alerta(outro)
    # chave antiga (gravada com os valores) também vale; e "voltar para revisar" a remove
    r05 = next(a for a in verificar(p) if a.regra == 'R05')
    p.revisados['R05|Plano|' + r05.mensagem.replace('100.000,00', '99.999,99')] = dict(em='x'); db.salvar(pid, p)
    assert next(a for a in verificar(db.carregar(pid)[0]) if a.regra == 'R05').gravidade == 'revisado'
    cliente.post(f'/p/{pid}/revisar', data={'chave': chave_alerta(r05), 'acao': 'desmarcar'})
    assert db.carregar(pid)[0].revisados == {}
