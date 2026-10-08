"""Apagar todas as pesquisas de um projeto para refazer do zero (pedido da OSC, 05/10/2026): os itens ficam como foram pedidos, o resultado das
pesquisas sai, e nada do que estava guardado é reaproveitado pela pesquisa nova. A versão anterior continua no histórico."""
import re

import pytest
from fastapi.testclient import TestClient

CNPJS = ('11.222.333/0001-81', '11.444.777/0001-61', '45.997.418/0001-53')


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


def _ev(origem='navegador', url='https://loja.exemplo/p'):
    from orcamento.modelo import Evidencia
    return Evidencia(arquivo='x.pdf', origem=origem, sha256='a' * 64, url=url)


def _fontes(origens=('navegador',) * 3):
    from orcamento.modelo import Fonte
    return [Fonte(nome=f'LOJA {k}', cnpj=CNPJS[k], data_pesquisa='2026-10-01', evidencia=_ev(o, f'https://loja{k}.exemplo/p')) for k, o in enumerate(origens)]


CONFIRMADA = 'https://vagas.exemplo/psi0'   # vaga que o sistema achou e cuja empresa a OSC confirmou (está no cargo e no banco de vagas)


def _vagas(origens=('navegador',) * 3, cargo='psi'):
    from orcamento.modelo import PesquisaSalarial
    return [PesquisaSalarial(nome=f'EMPRESA {k}', cnpj=CNPJS[k], valor=200000 + k * 1000, faixa_min=200000 + k * 1000, data_pesquisa='2026-10-01',
                             evidencia=_ev(o, f'https://vagas.exemplo/{cargo}{k}')) for k, o in enumerate(origens)]


def _montar(cliente):
    """Projeto com um pouco de tudo: cargos (um com vaga anexada à mão), itens trocados, marca posta pela pesquisa, marca da OSC, quantidade
    ajustada, item com pesquisa feita à mão, item ainda sem pesquisa, sistema (2 cotações automáticas e 1 da OSC) e serviço (propostas)."""
    from orcamento import db
    from orcamento.modelo import RubricaRH, RubricaMaterial, Subitem
    pid = int(cliente.post('/projetos', data={'nome': 'T', 'teto': '50.000,00', 'cep': '01001-000'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    p = db.carregar(pid)[0]
    sub = lambda desc, **k: Subitem(descricao=desc, qtd=k.pop('qtd', 2), **k)
    # 1ª versão: o plano como a OSC escreveu, ainda sem pesquisa
    p.rubricas = [
        RubricaRH(item=1, cargo='Psicólogo', horas_mes=100, meses=10, faixa_pretendida=150000),
        RubricaRH(item=2, cargo='Assistente Social', horas_mes=80, meses=10, quantidade=3),
        RubricaMaterial(item=3, descricao='Alimentação', meses=10, regra='mercado', teto_mensal=200000, subitens=[
            sub('Pão de Forma', especificacao='480g'), sub('Café', especificacao='500g'), sub('Suco de Maracujá', marca='Maguary', especificacao='1L'),
            sub('Café Solúvel', especificacao='100g', qtd=5), sub('Leite', especificacao='1L'), sub('Açúcar', especificacao='1kg')]),
        RubricaMaterial(item=4, descricao='Sistema de Gestão', meses=12, regra='sistema', subitens=[sub('Sistema de Gestão', qtd=1)]),
        RubricaMaterial(item=5, descricao='Serviço de Transporte', meses=10, regra='servico', subitens=[sub('Transporte dos participantes', qtd=1)])]
    db.salvar(pid, p, motivo='plano digitado')
    # 2ª versão: a pesquisa automática grava os resultados
    p = db.carregar(pid)[0]
    p.rubricas[0].pesquisas, p.rubricas[0].valor_mensal_plano, p.rubricas[0].horas_mes = _vagas(), 149800, 166
    p.rubricas[1].pesquisas, p.rubricas[1].valor_mensal_plano = _vagas(('navegador', 'pdf', 'navegador'), 'ass'), 90000
    pronto = dict(precos=[1000, 1100, 1200], valor_plano=1100, produtos=['Produto A', 'Produto A 2', 'Produto A 3'], eans=['789', '789', '789'], confirmacao='EAN nas 3 lojas')
    al = p.rubricas[2].subitens
    al[0] = al[0].model_copy(update=dict(pronto, descricao='Pão de Forma', marca='Pullman', especificacao='500g', nivel=1, descricao_original='Pão de Forma',
                                         marca_original='', especificacao_original='480g', fontes=_fontes(), justificativa='troca por item parecido'))
    al[1] = al[1].model_copy(update=dict(pronto, marca='Pilão', fontes=_fontes()))                                    # a pesquisa preencheu a marca
    al[2] = al[2].model_copy(update=dict(pronto, fontes=_fontes()))                                                   # a marca é a que a OSC escreveu
    al[3] = al[3].model_copy(update=dict(pronto, qtd=3, fontes=_fontes(), justificativa='as 3 lojas mais baratas; quantidade ajustada de 5 para 3: limite de compra'))
    al[4] = al[4].model_copy(update=dict(pronto, fontes=_fontes(('navegador', 'pdf', 'navegador'))))                  # a OSC anexou um PDF
    p.rubricas[3].subitens[0] = p.rubricas[3].subitens[0].model_copy(update=dict(precos=[27092, 49900, 32000], valor_plano=27092, fontes=_fontes(('navegador', 'manual', 'navegador')),
                                                                                 produtos=['Plano A', 'Plano B', 'Plano C'], confirmacao='sistemas diferentes; plano pelas ferramentas de referência'))
    db.salvar(pid, p, autor='sistema (pesquisa automática)', motivo='pesquisa')
    # 3ª versão: a OSC anexa as propostas do serviço, marca pontos como revisados e importa um comprovante de CNPJ
    p = db.carregar(pid)[0]
    p.rubricas[4].subitens[0] = p.rubricas[4].subitens[0].model_copy(update=dict(precos=[50000, 52000, 54000], valor_plano=50000, fontes=_fontes(('pdf', 'pdf', 'pdf'))))
    p.revisados = {'S03|Item 3 – Alimentação / Café|mesmo produto confirmado pela descrição': dict(em='x'), 'S09|Item 1 – Psicólogo|o valor no plano': dict(em='x'),
                   'D09|Item 5 – Serviço de Transporte|teto': dict(em='x'), 'R05|Plano|total abaixo do teto': dict(em='x')}
    p.comprovantes_cnpj = {CNPJS[0]: dict(arquivo='cnpj.pdf', situacao='ATIVA', emitido_em='2026-10-05')}
    db.salvar(pid, p, motivo='propostas anexadas')
    # o que estava guardado e a pesquisa nova não pode reaproveitar
    db.produtos_guardar(pid, 3, 'Café 500g', [dict(ofertas=[], reservas=[])]); db.produtos_guardar(pid, 3, 'Pão de Forma 480g', [dict(ofertas=[], reservas=[])])
    db.produtos_guardar(pid, 3, 'Leite 1L', [dict(ofertas=[], reservas=[])]); db.produtos_guardar(pid, 4, 'Sistema de Gestão', [dict(ofertas=[], reservas=[])])
    db.produtos_guardar(pid + 99, 3, 'Café 500g', [dict(ofertas=[], reservas=[])])                                    # de outro projeto: não é tocado
    from orcamento import vagas as V
    with db.conectar() as c:
        for url, cargo, motivo, descartada in (('v1', 'Psicólogo', None, None), ('v2', 'Psicólogo', None, '2026-10-01'), (CONFIRMADA, 'Psicólogo', V.CONFIRMADA_PELA_OSC + ' em 01/10', None),
                                               ('v4', 'Assistente Social', None, None), ('v5', 'Motorista', None, None)):
            c.execute('INSERT INTO vaga_banco (url, cargo_chave, cargo, titulo, empresa, coletada_em, valida_ate, cnpj_status, cnpj_motivo, pdf, descartada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                      (url, V.chave_cargo(cargo), cargo, cargo, 'EMPRESA', '2026-10-01T10:00:00', '2027-03-30', '🟢', motivo, 'banco_vagas/x.pdf', descartada))
    db.cache_gravar('busca|loja|cafe', [1, 2, 3])
    return pid


def test_previa_mostra_o_que_sai_e_o_que_fica_sem_mudar_nada(cliente):
    from orcamento import db
    pid = _montar(cliente)
    v = db.carregar(pid)[1]
    pag = cliente.get(f'/p/{pid}/zerar-pesquisas').text
    assert db.carregar(pid)[1] == v and db.cache_ler('busca|loja|cafe') == [1, 2, 3]                                   # a tela só mostra: nada é mudado
    for texto in ('Apagar as pesquisas e refazer do zero', 'Os <b>itens ficam</b>', 'Pão de Forma Pullman 500g', '<b>Pão de Forma 480g</b>', 'Café (Pilão)',
                  'Café Solúvel: de 3 para <b>5</b>', 'Apagar as marcas que a pesquisa preencheu', 'Apagar também o que foi feito à mão', f'restaure a versão {v}',
                  'Os comprovantes de CNPJ', 'Apagar e pesquisar tudo de novo', 'Só apagar', 'O banco de vagas é comum a todos os projetos',
                  'Apagar também as vagas que você confirmou</b> (1 no projeto, 1 guardada(s))', 'name="confirmadas" value="1" checked', 'passa por todo o processo outra vez'):
        assert texto in pag, texto
    assert 'Maguary' not in pag.split('Apagar as marcas')[1].split('</label>')[0]                                       # a marca que a OSC escreveu não entra na lista
    ind = dict(re.findall(r'indicador__rotulo">([^<]+)</div><div class="indicador__valor">(\d+)', pag))
    assert {k: ind[k] for k in ('Pesquisas automáticas', 'Itens que voltam ao pedido', 'Marcas apagadas', 'Feitas à mão')} ==         {'Pesquisas automáticas': '21', 'Itens que voltam ao pedido': '1', 'Marcas apagadas': '1', 'Feitas à mão': '6'}
    proj = cliente.get(f'/p/{pid}').text                                                                               # a entrada: na visão geral e na configuração
    assert proj.count(f'href="/p/{pid}/zerar-pesquisas"') == 2 and 'Refazer as pesquisas do zero' in proj
    vazio = int(cliente.post('/projetos', data={'nome': 'V', 'teto': '1.000,00'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    assert 'ainda não tem pesquisas para apagar' in cliente.get(f'/p/{vazio}/zerar-pesquisas').text
    assert 'não tinha pesquisas para apagar' in cliente.post(f'/p/{vazio}/zerar-pesquisas', data={'marcas': '1'}, follow_redirects=True).text


def test_apagar_as_pesquisas_deixa_os_itens_como_foram_pedidos(cliente):
    from orcamento import db, vagas as V
    from orcamento.calculo import total_projeto
    pid = _montar(cliente)
    v = db.carregar(pid)[1]
    r = cliente.post(f'/p/{pid}/zerar-pesquisas', data={'marcas': '1', 'confirmadas': '1', 'depois': ''}, follow_redirects=True)   # como a tela manda, sem mexer nas opções
    assert '19 pesquisa(s) apagada(s)' in r.text and f'a versão {v}, com as pesquisas, continua no histórico' in r.text
    p, nova = db.carregar(pid)
    assert nova == v + 1
    psi, ass, al, sis, srv = p.rubricas
    # cargos: as vagas e o valor saem; o que a OSC definiu fica (horas, faixa, quantidade); a vaga anexada à mão fica no lugar
    assert psi.pesquisas == [] and psi.valor_mensal_plano is None and (psi.horas_mes, psi.faixa_pretendida, psi.meses) == (166, 150000, 10)
    assert [q.nome for q in ass.pesquisas] == ['', 'EMPRESA 1', ''] and ass.pesquisas[1].evidencia.origem == 'pdf' and ass.valor_mensal_plano is None and ass.quantidade == 3
    # itens: voltam ao que foi pedido, sem preços, lojas nem comprovantes
    assert [(s.descricao, s.marca, s.especificacao, s.qtd) for s in al.subitens] == [
        ('Pão de Forma', None, '480g', 2),            # a troca foi desfeita
        ('Café', None, '500g', 2),                    # a marca que a pesquisa pôs saiu
        ('Suco de Maracujá', 'Maguary', '1L', 2),     # a marca que a OSC escreveu ficou
        ('Café Solúvel', None, '100g', 5),            # a quantidade voltou à pedida
        ('Leite', None, '1L', 2), ('Açúcar', None, '1kg', 2)]
    for s in al.subitens[:4]:
        assert (s.fontes, s.precos, s.produtos, s.eans, s.valor_plano, s.nivel, s.confirmacao, s.justificativa, s.descricao_original) == \
            ([], [None] * 3, [None] * 3, [None] * 3, None, 0, None, None, None)
    leite = al.subitens[4]                                                                                              # tinha um PDF anexado pela OSC: o item fica inteiro
    assert leite.precos == [1000, 1100, 1200] and len(leite.fontes) == 3 and leite.valor_plano == 1100
    assert al.teto_mensal == 200000 and al.meses == 10                                                                  # o que a OSC configurou na rubrica fica
    s = sis.subitens[0]                                                                                                 # sistema: a cotação da OSC fica no lugar; as automáticas saem
    assert s.precos == [None, 49900, None] and [f.nome for f in s.fontes] == ['', 'LOJA 1', ''] and s.valor_plano is None and s.produtos == [None, 'Plano B', None]
    assert srv.subitens[0].precos == [50000, 52000, 54000] and srv.subitens[0].valor_plano == 50000                     # serviço: propostas anexadas, ficam
    assert total_projeto(p) == (1100 * 2 + 50000) * 10
    # revisados dos itens que mudaram saem; os outros e os comprovantes de CNPJ ficam
    assert set(p.revisados) == {'D09|Item 5 – Serviço de Transporte|teto', 'R05|Plano|total abaixo do teto'} and list(p.comprovantes_cnpj) == [CNPJS[0]]
    # nada guardado é reaproveitado: banco de produtos dos itens zerados, vagas guardadas dos cargos, buscas do dia
    banco = db.produtos_do_banco(pid, 3)
    assert set(banco) == {'Leite 1L'} and db.produtos_do_banco(pid, 4) == {} and set(db.produtos_do_banco(pid + 99, 3)) == {'Café 500g'}
    with db.conectar() as c:
        ficaram = {row['url'] for row in c.execute('SELECT url FROM vaga_banco')}
    assert ficaram == {'v5'}                        # só a de outro cargo fica: a descartada pela OSC também sai (reencontrada, passa por todo o processo de novo)
                                                    # (senão voltaria para o cargo na hora, e a pesquisa não recomeçaria do zero)
    assert db.cache_ler('busca|loja|cafe') is None
    motivo = db.historico(pid)[0][0]['motivo']
    assert motivo.startswith('pesquisas zeradas para refazer do zero em') and '1 item(ns) trocado(s) voltaram ao pedido original' in motivo and '6 pesquisa(s) feita(s) à mão mantida(s)' in motivo
    assert '3 opção(ões) de produto e 4 vaga(s) guardadas saíram dos bancos' in motivo and 'confirmada' not in motivo
    # "Pesquisar tudo" enxerga os itens como não pesquisados; e dá para voltar atrás: a versão anterior volta inteira
    assert not cliente.appmod.servico.rh_pronto(psi) and len(cliente.appmod.servico.subitens_a_pesquisar(al)) == 5
    cliente.post(f'/p/{pid}/restaurar/{v}')
    p2 = db.carregar(pid)[0]
    assert len(p2.rubricas[0].pesquisas) == 3 and p2.rubricas[2].subitens[1].marca == 'Pilão' and p2.rubricas[2].subitens[0].descricao_original == 'Pão de Forma'


def test_opcoes_manter_as_marcas_manter_as_confirmadas_e_apagar_o_que_foi_feito_a_mao(cliente):
    from orcamento import db
    pid = _montar(cliente)
    # sem "marcas": as marcas ficam · sem "confirmadas": a vaga que a OSC confirmou fica no cargo e no banco · com "a_mao": sai o que foi anexado ou digitado
    cliente.post(f'/p/{pid}/zerar-pesquisas', data={'a_mao': '1'})
    p = db.carregar(pid)[0]
    psi, ass, al, sis, srv = p.rubricas
    assert [q.nome for q in psi.pesquisas] == ['EMPRESA 0', '', ''] and psi.pesquisas[0].evidencia.url == CONFIRMADA and psi.valor_mensal_plano is None
    assert ass.pesquisas == [] and al.subitens[1].marca == 'Pilão' and al.subitens[1].precos == [None] * 3
    assert al.subitens[4].precos == [None] * 3 and al.subitens[4].fontes == []                                         # o item com PDF anexado também foi zerado
    assert sis.subitens[0].precos == [None] * 3 and srv.subitens[0].precos == [None] * 3 and srv.subitens[0].valor_plano is None
    assert set(p.revisados) == {'R05|Plano|total abaixo do teto'} and db.produtos_do_banco(pid, 3) == {}
    with db.conectar() as c:
        assert {row['url'] for row in c.execute('SELECT url FROM vaga_banco')} == {CONFIRMADA, 'v5'}
    motivo = db.historico(pid)[0][0]['motivo']
    assert '26 pesquisa(s) apagada(s)' in motivo and '1 vaga(s) confirmada(s) pela OSC mantida(s)' in motivo and 'à mão mantida' not in motivo


def test_apagar_e_pesquisar_de_novo_e_tarefa_em_andamento(cliente, monkeypatch):
    from fastapi.responses import RedirectResponse
    from orcamento import db
    pid = _montar(cliente)
    v = db.carregar(pid)[1]
    # com uma tarefa rodando no projeto, nada é apagado
    monkeypatch.setattr(cliente.appmod.tarefas, 'listar', lambda *a, **k: [dict(id=7, estado='rodando', titulo='Pesquisar tudo', tipo='tudo', progresso=10, etapa='x', criado_em='2026-10-05T10:00:00')])
    assert 'Há uma tarefa em andamento neste projeto' in cliente.get(f'/p/{pid}/zerar-pesquisas').text
    r = cliente.post(f'/p/{pid}/zerar-pesquisas', data={'marcas': '1', 'depois': 'pesquisar'}, follow_redirects=False)
    assert 'Nada%20foi%20apagado' in r.headers['location'] and db.carregar(pid)[1] == v and db.cache_ler('busca|loja|cafe') == [1, 2, 3]
    # sem tarefa: apaga e já começa o "Pesquisar tudo"
    monkeypatch.setattr(cliente.appmod.tarefas, 'listar', lambda *a, **k: [])
    chamadas = []
    monkeypatch.setattr(cliente.appmod, 'pesquisar_tudo', lambda p_: chamadas.append(p_) or RedirectResponse('/tarefa/99', status_code=303))
    r = cliente.post(f'/p/{pid}/zerar-pesquisas', data={'marcas': '1', 'confirmadas': '1', 'depois': 'pesquisar'}, follow_redirects=False)
    assert r.headers['location'] == '/tarefa/99' and chamadas == [pid] and db.carregar(pid)[1] == v + 1 and db.carregar(pid)[0].rubricas[0].pesquisas == []


def test_marca_que_a_osc_trocou_depois_da_pesquisa_nao_e_apagada(cliente):
    """A marca só sai quando foi a pesquisa que a pôs (o histórico diz) e a OSC não mexeu nela depois."""
    from orcamento import db, zerar
    pid = _montar(cliente)
    p = db.carregar(pid)[0]
    assert zerar.marcas_da_pesquisa(pid, p) == {(3, 1)}                                                                # só o Café (Pilão)
    p.rubricas[2].subitens[1].marca = 'Melitta'                                                                        # a OSC troca a marca
    db.salvar(pid, p, motivo='marca trocada pela OSC')
    p = db.carregar(pid)[0]
    assert zerar.marcas_da_pesquisa(pid, p) == set()
    res = zerar.zerar(p, pid)
    assert res['marcas'] == [] and p.rubricas[2].subitens[1].marca == 'Melitta' and p.rubricas[2].subitens[1].precos == [None] * 3


def test_pesquisas_em_branco_nao_sao_a_mesma_empresa(cliente):
    """Depois de zerar, o item que ficou com uma cotação feita à mão e duas em branco não pode acusar "a mesma empresa em mais de uma
    pesquisa" (as duas em branco eram comparadas como iguais). Empresa repetida de verdade continua sendo apontada."""
    from orcamento import db
    from orcamento.calculo import verificar
    pid = _montar(cliente)
    cliente.post(f'/p/{pid}/zerar-pesquisas', data={'marcas': '1'})
    p = db.carregar(pid)[0]
    r09 = lambda: [a.item for a in verificar(p) if a.regra == 'R09']
    assert r09() == []                                                         # cargo com 1 vaga anexada + 2 em branco; sistema com 1 cotação + 2 em branco
    p.rubricas[1].pesquisas[0] = p.rubricas[1].pesquisas[1].model_copy()       # agora sim: a mesma empresa em duas pesquisas do cargo
    assert r09() == ['Item 2 – Assistente Social']


def test_vaga_reencontrada_depois_de_zerar_passa_por_todo_o_processo(cliente):
    """Decisão da OSC (06/10/2026): ao apagar para refazer, as vagas dos cargos saem TODAS do banco — também as descartadas — e a consulta de
    CNPJ guardada de cada empresa sai junto: a vaga que a pesquisa nova encontrar de novo não é pulada nem volta descartada."""
    from orcamento import db, vagas as V, zerar
    with db.conectar() as c:
        for url, empresa, descartada in (('z1', 'Alfa Serviços', None), ('z2', 'Beta Clínica', '2026-10-01T10:00:00'), ('z3', 'Gama', None)):
            c.execute('INSERT INTO vaga_banco (url, cargo_chave, cargo, titulo, empresa, cidade, uf, coletada_em, valida_ate, cnpj_status, pdf, descartada_em) '
                      'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (url, V.chave_cargo('Psicólogo' if url != 'z3' else 'Motorista'), 'Psicólogo', 'Psicólogo', empresa, 'São Paulo', 'SP',
                                                           '2026-10-01T10:00:00', '2027-03-30', '🟢', 'banco_vagas/x.pdf', descartada))
        for chave in ('alfa servicos|sao paulo|sp', 'beta clinica|sao paulo|sp', 'gama|sao paulo|sp'):
            c.execute('INSERT INTO empresa_cnpj (chave, consultado_em, json) VALUES (?,?,?)', (chave, '2026-10-01T10:00:00-03:00', '{}'))
    res = dict(rubricas_inteiras=[], pedidos=[], chaves_de_vaga=[V.chave_cargo('Psicólogo')], com_confirmadas=True)
    assert zerar.contar_bancos(1, res) == (0, 2) and zerar.zerar_bancos(1, res) == (0, 2)
    with db.conectar() as c:
        assert [r['url'] for r in c.execute('SELECT url FROM vaga_banco')] == ['z3']                                   # a descartada (z2) também saiu
        assert [r['chave'] for r in c.execute('SELECT chave FROM empresa_cnpj')] == ['gama|sao paulo|sp']             # o CNPJ das duas será conferido de novo
