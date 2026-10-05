"""v0.3: título exato das vagas, tarefas com progresso/cancelamento, base da Receita (homônimos) e grade com fornecedores por item."""
import os
import sqlite3
import time

import pytest

from orcamento.vagas import titulo_exato, avaliar


@pytest.mark.parametrize('titulo, cargo, esperado', [
    ('Coordenador(a) de Projetos', 'Coordenador de Projetos', True), ('Coordenadora de Projeto', 'Coordenador de Projetos', True),
    ('COORDENADOR DE PROJETOS', 'Coordenador de Projetos', True), ('Coordenador/a de Projetos', 'Coordenador de Projetos', True),
    ('Coordenador de Projetos de TI', 'Coordenador de Projetos', False), ('Coordenador de Projetos Sociais', 'Coordenador de Projetos', False),
    ('Coordenador de Projetos - São Paulo', 'Coordenador de Projetos', False), ('Auxiliar de Serviço Geral', 'Auxiliar de serviços gerais', True),
    ('Psicóloga', 'Psicólogo', True), ('Psicólogo Clínico', 'Psicólogo', False), ('Orientadora Socioeducativa', 'Orientador socioeducativo', True),
    ('Designer Gráfico Pleno', 'Designer Gráfico', False), ('Auxiliar Administrativa', 'Auxiliar Administrativo', True),
])
def test_titulo_exato(titulo, cargo, esperado):
    assert titulo_exato(titulo, cargo) == esperado


def test_agregador_nao_vale():
    v = dict(titulo='Assistente Social', empresa='OEmprego - Vagas Brasil', faixa_min=300000, faixa_max=300000, unidade='MONTH')
    assert 'agregador' in avaliar(v, 'Assistente Social')


@pytest.fixture
def dados(tmp_path, monkeypatch):
    import orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    return tmp_path


def test_tarefa_progresso_e_cancelamento(dados):
    from orcamento import tarefas

    def trabalho(ctx):
        ctx.fonte('Loja A', 'ok'); ctx.fonte('Loja B', 'falhou', 'sem resposta em 75 s')
        ctx.aviso('RESULTADO INCOMPLETO — Loja B')
        for i in range(50):
            ctx.progresso(i * 2, f'passo {i}'); time.sleep(0.05)
        return dict(ok=True, ir_para='/x')
    tid = tarefas.iniciar('teste', 'tarefa de teste', trabalho)
    time.sleep(0.6)
    t = tarefas.ler(tid)
    assert t['estado'] == 'rodando' and t['fontes']['Loja B']['estado'] == 'falhou' and t['avisos']
    tarefas.cancelar(tid)
    for _ in range(50):
        if tarefas.ler(tid)['estado'] != 'rodando':
            break
        time.sleep(0.1)
    assert tarefas.ler(tid)['estado'] == 'cancelada'
    tid2 = tarefas.iniciar('teste', 'termina', lambda ctx: dict(ir_para='/p/1'), projeto_id=1)   # com projeto: registra no histórico
    for _ in range(50):
        if tarefas.ler(tid2)['estado'] == 'concluída':
            break
        time.sleep(0.1)
    t2 = tarefas.ler(tid2)
    assert t2['estado'] == 'concluída' and t2['progresso'] == 100 and t2['resultado']['ir_para'] == '/p/1'


def _base_exemplo(caminho):
    """Mini base no formato do índice: 2 empresas 'Confiança RH' em Niterói e 1 empresa de nome único."""
    c = sqlite3.connect(caminho)
    c.executescript("""CREATE TABLE empresa(basico TEXT PRIMARY KEY, razao TEXT);
        CREATE TABLE estab(cnpj TEXT PRIMARY KEY, basico TEXT, matriz INTEGER, fantasia TEXT, uf TEXT, municipio TEXT, cnae TEXT);
        CREATE TABLE municipio(codigo TEXT PRIMARY KEY, nome TEXT); CREATE TABLE meta(chave TEXT PRIMARY KEY, valor TEXT);
        CREATE VIRTUAL TABLE nomes USING fts5(nome, cnpj UNINDEXED, tokenize='unicode61 remove_diacritics 2');
        INSERT INTO municipio VALUES ('5865','NITEROI'),('7107','SAO PAULO');
        INSERT INTO empresa VALUES ('03472547','CONFIANCA RH, CONSULTORIA E PRESTADORA DE SERVICOS LTDA'),('12802628','CONFIANCA SERVICOS DE ASSESSORIA LTDA'),
                                   ('13312641','DNA FACILITIES LTDA');
        INSERT INTO estab VALUES ('03472547000188','03472547',1,'','RJ','5865','7820500'),('12802628000190','12802628',1,'CONFIANCA RH','RJ','5865','7820500'),
                                 ('13312641000123','13312641',1,'','SP','7107','8111700');
        INSERT INTO meta VALUES ('pasta_origem','2026-09');
        INSERT INTO nomes(nome, cnpj) SELECT COALESCE(e.fantasia,'') || ' | ' || COALESCE(m.razao,''), e.cnpj FROM estab e LEFT JOIN empresa m ON m.basico=e.basico;""")
    c.commit(); c.close()


def test_base_da_receita_homonimos_e_nome_unico(dados, monkeypatch):
    from orcamento import cnpj_base, cnpj_busca
    arq = os.path.join(dados, 'cnpj_teste.sqlite'); _base_exemplo(arq)
    monkeypatch.setattr(cnpj_base, 'BASE', arq)
    assert cnpj_busca.cnpj_pela_base('DNA Facilities')['cnpj'] == '13312641000123'
    assert cnpj_busca.cnpj_pela_base('Confiança RH') is None                          # 2 empresas com o nome: não escolhe
    r = cnpj_busca.conferir_homonimos(dict(status='🟢', cnpj='12802628000190', motivo='nome confere', fonte='Yahoo'), 'Confiança RH')
    assert r['status'] == '🟡' and 'mais 1 empresa' in r['motivo']
    assert cnpj_busca.conferir_local(dict(status='🟢', cnpj='1', municipio='EXTERIOR', uf='EX', motivo='x'), 'Goiás', None)['status'] == '🔴'


def test_grade_com_fornecedor_por_item(dados, tmp_path):
    from openpyxl import load_workbook
    from orcamento.modelo import Projeto, RubricaMaterial, Subitem, Fonte
    from orcamento.exportar import exportar
    fs = [Fonte(nome=n, cnpj=c, data_pesquisa='2026-09-27') for n, c in
          [('ATACADAO S.A.', '75.315.333/0001-09'), ('CARREFOUR COMERCIO E INDUSTRIA LTDA', '45.543.915/0001-81'), ('TENDA ATACADO SA', '01.157.555/0011-86')]]
    s = Subitem(descricao='Maionese 250g', qtd=10, precos=[858, 999, 815], fontes=fs, valor_plano=890)
    p = Projeto(nome='t', teto=8900, rubricas=[RubricaMaterial(item=1, descricao='Alimentação', meses=1, subitens=[s])])
    arq = os.path.join(tmp_path, 'g.xlsx'); exportar(p, [], {}, arq)
    ws = load_workbook(arq)['Grade Comparativa']
    textos = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any('ATACADAO S.A. - CNPJ: 75.315.333/0001-09' in t for t in textos) and any('TENDA ATACADO SA' in t for t in textos)
    assert any('fornecedores por subitem' in t for t in textos)


def test_banco_de_vagas_cria_a_pasta(dados):
    from orcamento import vagas as V
    v = dict(titulo='Auxiliar de Serviços Gerais', empresa='Adecco', url='https://x/vaga/1', plataforma='InfoJobs', faixa_min=180000,
             faixa_max=180000, unidade='MONTH', cidade='São Paulo', uf='SP')
    V.guardar_no_banco('Auxiliar de serviços gerais', v, dict(status='🟢', cnpj='12345678000199', razao='ADECCO', motivo='teste'), b'%PDF-1.4 teste')
    assert os.path.exists(os.path.join(dados, 'banco_vagas'))
    assert any(f.endswith('_adecco.pdf') for f in os.listdir(os.path.join(dados, 'banco_vagas')))


@pytest.mark.parametrize('texto, esperado', [
    ('Função: SERVENTE/COPEIRA Salário: R$ 1.727.27 + 131,00 Gratificação', [172727]),
    ('<p>Salário base: R$ 2.000,00</p>', [200000]),
    ('Salário de R$ 1800 + VT', [180000]),
    ('Benefícios: vale alimentação R$ 900,00', []),
])
def test_salario_no_texto_da_vaga(texto, esperado):
    from orcamento.vagas import salarios_no_texto
    assert salarios_no_texto(texto) == esperado


def test_salario_do_texto_diferente_do_anuncio_nao_vale():
    v = dict(titulo='Auxiliar de Serviços Gerais', empresa='Orsegups', faixa_min=200000, faixa_max=200000, unidade='MONTH', salarios_texto=[172727])
    assert 'o texto da vaga diz salário de R$ 1.727,27' in avaliar(v, 'Auxiliar de serviços gerais')
    assert avaliar(dict(v, salarios_texto=[200000]), 'Auxiliar de serviços gerais') is None
