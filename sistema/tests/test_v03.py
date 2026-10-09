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
    ('Coordenador de Projetos - São Paulo', 'Coordenador de Projetos', True), ('Auxiliar de Serviço Geral', 'Auxiliar de serviços gerais', True),
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


def test_sede_em_outro_estado_so_e_duvida_quando_ha_homonima(dados, monkeypatch):
    """Pedido da OSC (06/10/2026): muitas vagas ficavam "em dúvida" por causa do nome da empresa. Medido no banco: 10 de 31 eram só "CNPJ em
    outro estado", sem haver outra empresa com o nome. A vaga diz onde é o TRABALHO; a sede pode ser em outro lugar."""
    import asyncio
    from orcamento import cnpj_base, cnpj_busca
    arq = os.path.join(dados, 'cnpj_teste.sqlite'); _base_exemplo(arq)
    monkeypatch.setattr(cnpj_base, 'BASE', arq)
    # empresa única com esse nome no Brasil, sede em SP, vaga no Ceará: é ela
    unica = dict(status='🟢', cnpj='13312641000123', municipio='SAO PAULO', uf='SP', motivo='nome confere', fonte='Yahoo')
    r = cnpj_busca.conferir_local(unica, 'Fortaleza', 'CE', 'DNA Facilities')
    assert r['status'] == '🟢' and 'sede em SP, vaga em CE' in r['motivo'] and 'única empresa ativa com esse nome' in r['motivo']
    # há outra empresa com o mesmo nome: continua em dúvida
    r = cnpj_busca.conferir_local(dict(status='🟢', cnpj='12802628000190', municipio='NITEROI', uf='RJ', motivo='nome confere', fonte='Yahoo'), 'São Paulo', 'SP', 'Confiança RH')
    assert r['status'] == '🟡' and cnpj_busca.OUTRA_UF in r['motivo']
    # CNPJ publicado no site oficial da empresa (ou escrito na vaga): a sede em outro estado não é dúvida, mesmo havendo homônimas
    r = cnpj_busca.conferir_local(dict(status='🟢', cnpj='12802628000190', municipio='NITEROI', uf='RJ', motivo='CNPJ publicado no site oficial', fonte='site oficial https://x'),
                                  'São Paulo', 'SP', 'Confiança RH')
    assert r['status'] == '🟢' and 'sede em RJ, vaga em SP' in r['motivo']
    assert cnpj_busca.conferir_local(unica, 'São Paulo', 'SP', 'DNA Facilities') == unica                 # mesmo estado: nada muda
    assert cnpj_busca.conferir_local(unica, 'Fortaleza', 'CE')['status'] == '🟡'                            # sem o nome não dá para conferir as homônimas
    # dúvida guardada (memória de 30 dias) só por causa do estado: é conferida de novo com a regra atual, sem consultar a internet
    from orcamento import db
    chave = 'dna facilities|fortaleza|ce'
    with db.conectar() as c:
        c.execute('INSERT OR REPLACE INTO empresa_cnpj (chave, consultado_em, json) VALUES (?,?,?)',
                  (chave, db.agora(), '{"status": "🟡", "cnpj": "13312641000123", "uf": "SP", "municipio": "SAO PAULO", "fonte": "Yahoo", '
                                      '"motivo": "nome confere; CNPJ em SP, vaga em CE: pode ser filial ou homônima"}'))
    r = asyncio.run(cnpj_busca.cnpj_do_empregador(None, None, 'DNA Facilities', 'Fortaleza', 'CE'))
    assert r['status'] == '🟢' and r['cnpj'] == '13312641000123' and r['motivo'].startswith('nome confere; sede em SP, vaga em CE')
    # CNPJ escrito no texto da própria vaga: vale (ativo na base e o nome confere), antes de qualquer busca
    from orcamento.vagas import cnpjs_no_texto
    assert cnpjs_no_texto('<p>Empresa DNA Facilities, CNPJ 13.312.641/0001-23. Contato...</p> CNPJ: 13312641000123') == ['13312641000123']
    r = asyncio.run(cnpj_busca.cnpj_do_empregador(None, None, 'DNA Facilities', 'Rio de Janeiro', 'RJ', cnpjs_texto=['13312641000123']))
    assert r['status'] == '🟢' and r['fonte'] == 'texto da vaga' and 'escrito no texto da própria vaga' in r['motivo'] and 'sede em SP, vaga em RJ' in r['motivo']
    assert asyncio.run(cnpj_busca.cnpj_do_texto(None, 'Outra Empresa Qualquer', ['13312641000123'])) is None   # o CNPJ escrito é de outra empresa: não vale
    # para a OSC escolher com um clique: as empresas com esse nome, as do estado da vaga primeiro
    cs = cnpj_busca.candidatos_da_base('Confiança RH', 'Niterói', 'RJ')
    assert [(c['cnpj'], c['municipio'], c['na_cidade']) for c in cs] == [('12802628000190', 'NITEROI', True), ('03472547000188', 'NITEROI', True)]   # o nome idêntico antes do nome contido
    assert cnpj_busca.candidatos_da_base('Empresa Que Não Existe', 'Niterói', 'RJ') == []


def test_nova_fonte_de_vagas_titulo_no_endereco_e_milhar_escrito_com_ponto():
    """Pedido da OSC (08/10/2026): melhorar a busca de vagas. Sondados 8 sites; entrou o Empregos.com.br (título, empresa e salário legíveis, sem
    verificação humana). Nele o link da vaga só diz "Mais detalhes" (o título está no endereço) e o salário de R$ 2.200 vem como "2.2"."""
    from orcamento import vagas as V
    nomes = [f[0] for f in V.fontes('Auxiliar Administrativo')]
    assert 'Empregos.com.br' in nomes and 'https://www.empregos.com.br/vagas/auxiliar-administrativo' in [f[1] for f in V.fontes('Auxiliar Administrativo')]
    assert 'Empregos.com.br' not in [f[0] for f in V.fontes('Auxiliar Administrativo', profundo=True)]
    assert V.titulo_do_endereco('https://www.empregos.com.br/vaga/11891982/auxiliar-administrativo-em-atibaia-sp') == 'auxiliar administrativo em atibaia sp'
    assert V.titulo_confere(V.titulo_do_endereco('https://www.empregos.com.br/vaga/11891982/auxiliar-administrativo-em-atibaia-sp'), 'Auxiliar Administrativo')
    assert not V.titulo_confere(V.titulo_do_endereco('https://www.empregos.com.br/vaga/11891982/motorista-em-atibaia-sp'), 'Auxiliar Administrativo')
    # o valor escrito do jeito americano também confirma o salário na página guardada
    assert V.salario_no_texto('Remuneração R$2,295.00 Publicado há 1 dia', 229500) and V.salario_no_texto('Remuneração R$ 2.295,00', 229500)
    assert not V.salario_no_texto('R$2,295.50', 229500) and not V.salario_no_texto('R$ 12,295.00', 229500)
    # "2.295" nos dados da vaga: é R$ 2.295,00 SÓ se a página mostrar esse valor; senão, a vaga fica sem salário
    v = dict(titulo='Auxiliar Administrativo', empresa='Empresa Exemplo', faixa_min=230, faixa_max=230, unidade='MONTH', faixa_bruta=[2.295, 2.295])
    V.milhar_com_ponto(v, 'Nº de vagas 1 Remuneração R$2,295.00 Publicado há 1 dia')
    assert (v['faixa_min'], v['faixa_max'], v['salario_da']) == (229500, 229500, 'página (milhar)') and avaliar(v, 'Auxiliar administrativo') is None
    v = dict(titulo='Auxiliar Administrativo', empresa='Empresa Exemplo', faixa_min=220, faixa_max=220, unidade='MONTH', faixa_bruta=[2.2, 2.2])
    V.milhar_com_ponto(v, 'Página sem o valor por extenso')
    assert v['faixa_min'] is None and avaliar(v, 'Auxiliar administrativo') == 'sem salário informado'
    # salário mensal de menos de R$ 100 nunca passa (com o fim do mínimo de R$ 1.000, um erro de leitura viraria a vaga "mais barata")
    assert 'menos de R$ 100' in avaliar(dict(titulo='Auxiliar Administrativo', empresa='Empresa Exemplo', faixa_min=220, faixa_max=220, unidade='MONTH'), 'Auxiliar administrativo')
    v = dict(titulo='Auxiliar Administrativo', empresa='Empresa Exemplo', faixa_min=180000, faixa_max=180000, unidade='MONTH', faixa_bruta=[1800, 1800])
    assert V.milhar_com_ponto(v, 'qualquer texto')['faixa_min'] == 180000                                 # salário normal: nada muda


def test_coleta_consulta_primeiro_quem_a_base_resolve_e_refaz_o_que_o_modo_de_espera_interrompeu(dados, monkeypatch):
    """Pesquisa completa de 08/10/2026 (na cópia): a consulta ONLINE do CNPJ leva de 2 a 4 minutos por empresa, e o computador entrou em modo
    de espera três vezes — ao voltar, a consulta em andamento estourava o tempo e a vaga era gravada como erro. Agora: primeiro as empresas que
    a base da Receita resolve na hora; as outras só enquanto puderem mudar o resultado (as 3 continuam sendo as de MENOR salário entre as
    válidas); e a consulta interrompida pelo modo de espera é refeita."""
    import asyncio, time
    from orcamento import vagas as V, cnpj_busca, tarefas
    from test_vagas import _pdf_vaga

    class Navegador:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        class chromium:
            @staticmethod
            async def launch():
                class B:
                    async def close(self): pass
                return B()
    monkeypatch.setattr('playwright.async_api.async_playwright', lambda: Navegador())
    monkeypatch.setattr(V, 'corrigir_banco_pela_pagina', lambda: 0)
    dinheiro = lambda c: f'{c / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    vaga = lambda nome, sal: dict(titulo='Psicólogo', empresa=nome, url=f'https://vagas.exemplo/{nome.lower()}/12345', plataforma='InfoJobs', faixa_min=sal, faixa_max=sal,
                                  unidade='MONTH', cidade='São Paulo', uf='SP', apta=True, motivo=None)
    aptas = [vaga('Fox', 200000), vaga('Eco', 190000), vaga('Delta', 180000), vaga('Charlie', 170000), vaga('Bravo', 160000), vaga('Alfa', 150000)]
    lentas = {'Alfa', 'Eco'}                                                         # a base da Receita não resolve estas: só com consulta online

    async def buscar_brasil(br, cargo, ctx=None, profundo=False, ignorar=(), pct=(0, 50)):
        return ([] if profundo else list(aptas)), len(aptas)
    consultas, cnpj = [], {n: f'{i + 11}222333000181'[:14] for i, n in enumerate(('Alfa', 'Bravo', 'Charlie', 'Delta', 'Eco', 'Fox'))}

    async def cnpj_do_empregador(br, api, nome, cidade=None, uf=None, site=None, ctx=None, cnpjs_texto=()):
        consultas.append(nome)
        if nome == 'Alfa' and consultas.count('Alfa') == 1:                          # o computador entra em modo de espera no meio desta consulta
            tarefas._esperas.append((time.time(), 1500.0))
            raise asyncio.TimeoutError()
        return dict(status='🟢', cnpj=cnpj[nome], razao_social=nome.upper() + ' LTDA', motivo='teste')

    async def capturar_pdf(br, url, rotulo, empresa=None):
        sal = next(v['faixa_min'] for v in aptas if v['url'] == url)
        return _pdf_vaga('Salário R$ ' + dinheiro(sal)), '2026-10-08T10:00:00-03:00'

    async def sem_pausa(desde, pausa=0):
        return bool(tarefas.esperas(desde))
    monkeypatch.setattr(V, 'buscar_brasil', buscar_brasil)
    monkeypatch.setattr(V, 'capturar_pdf', capturar_pdf)
    monkeypatch.setattr(cnpj_busca, 'cnpj_do_empregador', cnpj_do_empregador)
    monkeypatch.setattr(cnpj_busca, 'cnpj_pela_base', lambda nome, cidade=None, uf=None: None if nome in lentas else dict(status='🟢', cnpj=cnpj[nome]))
    monkeypatch.setattr(tarefas, '_esperas', [])
    monkeypatch.setattr(tarefas, 'depois_da_espera', sem_pausa)
    res = asyncio.run(V.coletar('Psicólogo'))
    # 1º as que a base resolve, da de menor salário para a maior, até fechar 3 (Bravo, Charlie, Delta); a Fox (2.000) não melhora: fica sem consulta.
    # Depois as outras: a Alfa (1.500) pode entrar — é consultada (e refeita, porque o computador "dormiu" na 1ª vez); a Eco (1.900) não melhora.
    assert consultas == ['Bravo', 'Charlie', 'Delta', 'Alfa', 'Alfa']
    assert [v['empresa'] for v in V.tres_do_banco('Psicólogo')] == ['Alfa', 'Bravo', 'Charlie'] and res['no_banco'] == 3   # as 3 de menor salário entre as válidas
    assert not [v for v in V.vagas_do_banco('Psicólogo', so_verdes=False) if 'erro' in (v['cnpj_motivo'] or '')]             # nada gravado como erro por causa do modo de espera
    # o vigia e o pedido de tela acesa
    assert tarefas.esperas(time.time() + 10) == [] and len(tarefas.esperas()) == 1 and round(tarefas.esperas()[0][1]) == 1500
    assert asyncio.run(sem_pausa(time.time() + 10)) is False
    # mais fontes de vagas: a busca do Trabalha Brasil é por cidade (4 cidades na 1ª volta, outras 4 na volta mais funda)
    tb = [f for f in V.fontes('Auxiliar Administrativo') if f[0] == 'Trabalha Brasil']
    assert len(tb) == 4 and tb[0][1] == 'https://www.trabalhabrasil.com.br/vagas-de-emprego-em-sao-paulo-sp/auxiliar-administrativo'
    assert len([f for f in V.fontes('Auxiliar Administrativo', profundo=True) if f[0] == 'Trabalha Brasil']) == 4
    import re
    assert re.search(tb[0][2], 'https://www.trabalhabrasil.com.br/vagas-de-emprego-em-sao-paulo-sp/auxiliar-administrativo/13697134')
    # o texto que a pessoa vê: sem os números que estão nos blocos de programa da página
    assert V.texto_visivel('<p>Salário R$ 2.000,00</p><script>{"v": 3000}</script><style>a{}</style> fim').split() == ['Salário', 'R$', '2.000,00', 'fim']


def test_empresa_descrita_em_vez_de_nomeada_nao_e_empresa_identificada():
    """Pesquisa completa de 09/10/2026: "Empresa Localizada No Bairro Campina Do Siqueira" passou como empresa e o sistema gastou minutos atrás do
    CNPJ dela; antes, uma "Empresa nacional" tinha casado com uma empresa de verdade. É empresa que não se identificou."""
    base = dict(titulo='Auxiliar Administrativo', faixa_min=200000, faixa_max=200000, unidade='MONTH')
    for nome in ('Empresa Localizada No Bairro Campina Do Siqueira', 'Empresa nacional', 'Empresa do ramo alimentício', 'Empresa de grande porte', 'Nosso cliente',
                 'Indústria do segmento metalúrgico', 'Empresa', 'Clínica localizada na zona sul', 'Empresa multinacional'):
        assert avaliar(dict(base, empresa=nome), 'Auxiliar administrativo') == 'empresa confidencial/não identificada', nome
    for nome in ('Empresa Brasileira de Correios e Telégrafos', 'Clínica Santa Clara', 'Loja Exemplo Ltda', 'Nacional Gás', 'Companhia de Saneamento Exemplo', 'Empresa Júnior Exemplo'):
        assert avaliar(dict(base, empresa=nome), 'Auxiliar administrativo') is None, nome


def test_cnpj_de_outro_estado_so_e_confirmado_com_estabelecimento_no_estado_ou_razao_social(dados, monkeypatch):
    """Pesquisa completa de 09/10/2026: de 6 empresas confirmadas sozinhas com CNPJ de outro estado, 2 eram OUTRA empresa — um anúncio de São Paulo
    recebeu o CNPJ de uma gráfica do interior da Bahia, a única do Brasil com aquele nome fantasia. O nome sozinho não basta: o CNPJ de outro
    estado só vale quando a empresa tem estabelecimento no estado da vaga ou quando o anúncio traz a razão social dela."""
    import asyncio, sqlite3
    from orcamento import cnpj_base, cnpj_busca, db
    arq = os.path.join(dados, 'cnpj_teste.sqlite'); _base_exemplo(arq)
    c = sqlite3.connect(arq)
    c.executescript("""INSERT INTO municipio VALUES ('3849','SALVADOR');
        INSERT INTO empresa VALUES ('77777777','MARIA TESTE DE SOUZA'),('88888888','AGENCIA NORTE SUL DE MODELOS LTDA');
        INSERT INTO estab VALUES ('77777777000177','77777777',1,'ZETAPLAK COMUNICACAO VISUAL','BA','3849','1813001'),
                                 ('88888888000188','88888888',1,'NORTE SUL','SP','7107','7490105'),('88888888000269','88888888',0,'OMEGA MODEL','BA','3849','7490105');
        INSERT INTO nomes(nome, cnpj) VALUES ('ZETAPLAK COMUNICACAO VISUAL | MARIA TESTE DE SOUZA','77777777000177'),
            ('NORTE SUL | AGENCIA NORTE SUL DE MODELOS LTDA','88888888000188'),('OMEGA MODEL | AGENCIA NORTE SUL DE MODELOS LTDA','88888888000269');""")
    c.commit(); c.close()
    monkeypatch.setattr(cnpj_base, 'BASE', arq)

    def pela_base(nome, cidade, uf):
        return cnpj_busca.conferir_local(cnpj_busca.cnpj_pela_base(nome, cidade, uf), cidade, uf, nome)
    # só o nome fantasia confere e a empresa não existe no estado da vaga: em dúvida, com a empresa indicada para a OSC confirmar
    r = pela_base('Zetaplak', 'São Paulo', 'SP')
    assert (r['status'], r['cnpj']) == ('🟡', '77777777000177') and cnpj_busca.SEM_ESTABELECIMENTO in r['motivo'] and 'CNPJ em BA, vaga em SP' in r['motivo']
    # o nome do anúncio é o nome fantasia da filial da Bahia, mas a matriz fica na cidade da vaga: é ela, com o CNPJ da cidade da vaga
    r = pela_base('Omega Model', 'São Paulo', 'SP')
    assert (r['status'], r['cnpj'], r['municipio']) == ('🟢', '88888888000188', 'SAO PAULO')
    assert pela_base('Omega Model', 'Salvador', 'BA')['cnpj'] == '88888888000269'                        # na Bahia, a filial que leva o nome
    assert pela_base('Omega Model', 'Niterói', 'RJ')['status'] == '🟡'                                    # no Rio a empresa não tem nada
    # CNPJ achado na internet, de outro estado: vale se a empresa tem estabelecimento ativo no estado da vaga
    da_bahia = dict(status='🟢', cnpj='88888888000269', municipio='SALVADOR', uf='BA', motivo='nome confere', fonte='Yahoo')
    r = cnpj_busca.conferir_local(da_bahia, 'Campinas', 'SP', 'Omega Model')
    assert r['status'] == '🟢' and 'a empresa tem estabelecimento em SP' in r['motivo']
    # o anúncio traz a razão social (2 palavras ou mais que a distinguem) da única empresa ativa com o nome: é ela, onde quer que fique
    assert cnpj_busca.nome_formal('DNA Facilities', 'DNA FACILITIES LTDA') and cnpj_busca.nome_formal('Agência Norte Sul de Modelos', 'AGENCIA NORTE SUL DE MODELOS LTDA')
    assert not cnpj_busca.nome_formal('Zetaplak', 'MARIA TESTE DE SOUZA') and not cnpj_busca.nome_formal('Zetaplak', 'ZETAPLAK LTDA')   # uma palavra só não basta
    r = pela_base('DNA Facilities', 'Fortaleza', 'CE')
    assert r['status'] == '🟢' and 'o anúncio traz a razão social da única empresa ativa com esse nome' in r['motivo']
    # o que a regra de 08/10 tinha confirmado e guardado (memória de 30 dias) é conferido de novo, sem internet
    with db.conectar() as cx:
        cx.execute('INSERT OR REPLACE INTO empresa_cnpj (chave, consultado_em, json) VALUES (?,?,?)',
                   ('zetaplak|sao paulo|sp', db.agora(), '{"status": "🟢", "cnpj": "77777777000177", "uf": "BA", "municipio": "SALVADOR", "razao_social": "MARIA TESTE DE SOUZA", '
                    '"fonte": "base da Receita (dados abertos)", "motivo": "base da Receita: única empresa ativa com esse nome no Brasil; sede em BA, vaga em SP: '
                    'é a única empresa ativa com esse nome na base da Receita"}'))
    r = asyncio.run(cnpj_busca.cnpj_do_empregador(None, None, 'Zetaplak', 'São Paulo', 'SP'))
    assert r['status'] == '🟡' and cnpj_busca.SEM_ESTABELECIMENTO in r['motivo']


def test_empresa_achada_na_internet_e_a_unica_com_o_nome_na_cidade_da_vaga(dados, monkeypatch):
    """Pesquisa completa de 09/10/2026: de 11 empresas de um cargo, 1 teve o CNPJ confirmado; várias paravam em homônimas de OUTRAS cidades. A base
    da Receita já confirmava sozinha "N empresas com esse nome no Brasil, uma só na cidade da vaga"; agora o CNPJ achado na internet também."""
    import asyncio, sqlite3
    from orcamento import cnpj_base, cnpj_busca, db
    arq = os.path.join(dados, 'cnpj_teste.sqlite'); _base_exemplo(arq)
    c = sqlite3.connect(arq)
    c.executescript("""INSERT INTO municipio VALUES ('6291','CAMPINAS');
        INSERT INTO empresa VALUES ('55555555','ALFA BETA SERVICOS LTDA'),('66666666','ALFA BETA SERVICOS E COMERCIO LTDA');
        INSERT INTO estab VALUES ('55555555000155','55555555',1,'','SP','6291','8111700'),('66666666000166','66666666',1,'ALFA BETA SERVICOS','RJ','5865','8111700');
        INSERT INTO nomes(nome, cnpj) VALUES (' | ALFA BETA SERVICOS LTDA','55555555000155'),('ALFA BETA SERVICOS | ALFA BETA SERVICOS E COMERCIO LTDA','66666666000166');""")
    c.commit(); c.close()
    monkeypatch.setattr(cnpj_base, 'BASE', arq)
    achado = dict(status='🟢', cnpj='55555555000155', municipio='CAMPINAS', uf='SP', motivo='nome confere', fonte='Yahoo')
    r = cnpj_busca.conferir_homonimos(achado, 'Alfa Beta Serviços', 'Campinas')
    assert r['status'] == '🟢' and 'uma só em Campinas' in r['motivo']                       # a homônima fica em Niterói: em Campinas só há esta
    assert cnpj_busca.conferir_homonimos(achado, 'Alfa Beta Serviços')['status'] == '🟡'       # sem a cidade da vaga não dá para afirmar
    # "São Paulo" pode ser a cidade ou o estado: a homônima fica no Rio, e no estado de São Paulo só existe esta (regra de 09/10/2026)
    r = cnpj_busca.conferir_homonimos(achado, 'Alfa Beta Serviços', 'São Paulo')
    assert r['status'] == '🟢' and cnpj_busca.UMA_NO_ESTADO + ' (SP)' in r['motivo']
    assert cnpj_busca.conferir_homonimos(achado, 'Alfa Beta Serviços', 'Santos', 'SP')['status'] == '🟢'            # outra cidade do mesmo estado: continua sendo a única nele
    assert cnpj_busca.conferir_homonimos(achado, 'Alfa Beta Serviços', 'Niterói', 'RJ')['status'] == '🟡'           # no Rio fica a homônima
    r = cnpj_busca.cnpj_pela_base('Alfa Beta Serviços', None, 'SP')                                                 # a base resolve sozinha pelo estado
    assert r['cnpj'] == '55555555000155' and r['motivo'] == 'base da Receita: 2 empresas com esse nome no Brasil, uma só no estado da vaga (SP)'
    assert cnpj_busca.cnpj_pela_base('Alfa Beta Serviços') is None and cnpj_busca.cnpj_pela_base('Confiança RH', 'Rio de Janeiro', 'RJ') is None   # sem lugar; duas no estado
    assert cnpj_busca.conferir_homonimos(dict(achado, municipio='SANTOS'), 'Alfa Beta Serviços', 'Campinas')['status'] == '🟡'   # o CNPJ achado nem é da cidade da vaga
    # as duas "Confiança RH" ficam em Niterói: continua em dúvida
    r = cnpj_busca.conferir_homonimos(dict(status='🟢', cnpj='12802628000190', municipio='NITEROI', uf='RJ', motivo='nome confere', fonte='Yahoo'), 'Confiança RH', 'Niterói')
    assert r['status'] == '🟡' and 'mais 1 empresa' in r['motivo']
    # a dúvida guardada (memória de 30 dias) é conferida de novo com a regra da cidade, sem internet
    with db.conectar() as cx:
        cx.execute('INSERT OR REPLACE INTO empresa_cnpj (chave, consultado_em, json) VALUES (?,?,?)',
                   ('alfa beta servicos|campinas|sp', db.agora(), '{"status": "🟡", "cnpj": "55555555000155", "uf": "SP", "municipio": "CAMPINAS", "fonte": "Yahoo", '
                                                                 '"motivo": "nome confere; base da Receita: mais 1 empresa(s) ativa(s) com esse nome (NITEROI/RJ)"}'))
    r = asyncio.run(cnpj_busca.cnpj_do_empregador(None, None, 'Alfa Beta Serviços', 'Campinas', 'SP'))
    assert r['status'] == '🟢' and r['motivo'].startswith('nome confere; base da Receita: 2 empresas ativas com esse nome no Brasil, uma só em Campinas')
    # os dados do CNPJ vêm primeiro da base deste computador (na hora): os serviços da internet só para quem não está nela
    class SemInternet:
        async def get(self, *a, **k): raise AssertionError('não era para consultar a internet')
    api = cnpj_busca.Api(SemInternet())
    j = asyncio.run(api.dados('55555555000155'))
    assert (j['razao_social'], j['municipio'], j['descricao_situacao_cadastral'], j['origem']) == ('ALFA BETA SERVICOS LTDA', 'CAMPINAS', 'ATIVA', 'base da Receita')


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


def test_salario_do_texto_da_vaga_e_o_que_vale():
    """Decisão da OSC (06/10/2026): o texto da vaga pode citar o salário e, se citar, é o do texto que vale (antes a vaga era recusada)."""
    from orcamento.vagas import salarios_no_texto
    v = dict(titulo='Auxiliar de Serviços Gerais', empresa='Orsegups', faixa_min=200000, faixa_max=200000, unidade='MONTH', salarios_texto=[172727])
    assert avaliar(v, 'Auxiliar de serviços gerais') is None
    assert (v['faixa_min'], v['faixa_max'], v['salario_da']) == (172727, 172727, 'texto')
    v2 = dict(v, faixa_min=200000, faixa_max=200000, salarios_texto=[200000]); v2.pop('salario_da')
    assert avaliar(v2, 'Auxiliar de serviços gerais') is None and 'salario_da' not in v2            # o texto diz o mesmo: nada muda
    v3 = dict(v, faixa_min=None, faixa_max=None, salarios_texto=[250000, 180000])                  # o site não informa; o texto cita dois valores
    assert avaliar(v3, 'Auxiliar de serviços gerais') is None and (v3['faixa_min'], v3['faixa_max']) == (180000, 250000)
    # qualquer salário mensal vale: não há mais o mínimo de R$ 1.000
    assert avaliar(dict(titulo='Auxiliar de Serviços Gerais', empresa='Orsegups', faixa_min=80000, faixa_max=80000, unidade='MONTH'), 'Auxiliar de serviços gerais') is None
    # valor por hora, por dia ou por aula escrito no texto não é salário mensal
    assert salarios_no_texto('Salário: R$ 1.727,27 + benefícios. Salário de R$ 25,00 por hora. Salário R$ 120,00/dia. salário R$ 800') == [172727, 80000]
    v4 = dict(v, faixa_min=200000, faixa_max=200000, salarios_texto=[172727], a_combinar=True)
    assert 'a combinar' in avaliar(v4, 'Auxiliar de serviços gerais') and v4['faixa_min'] == 200000   # "a combinar" continua fora
