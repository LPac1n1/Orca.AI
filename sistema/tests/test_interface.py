"""Interface reformulada (02/10/2026): formatos, leitura de valores, guia de passos, telas novas e o que as telas mandam para o sistema."""
import re

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


def test_formatos_e_leitura_de_valores(cliente):
    import app
    assert app.moeda(15000000) == '150.000,00' and app.moeda(7990) == '79,90' and app.moeda(None) == '' and app.moeda(0) == '0,00'
    assert app.data_br('2026-10-02T15:28:00-03:00') == '02/10/2026 15:28' and app.data_br('2026-10-02', False) == '02/10/2026' and app.data_br(None) == '—'
    assert app.duracao(45) == '45 s' and app.duracao(185) == '3 min 05 s' and app.duracao(4320) == '1 h 12 min'
    # o que a máscara de moeda manda ("1.234,56") e o que alguém digita sem a máscara
    assert app.cent('150.000,00') == 15000000 and app.cent('1.234,56') == 123456 and app.cent('79,9') == 7990 and app.cent('R$ 2.300') == 230000
    assert app.cent('150.000') == 15000000            # só pontos de milhar: cento e cinquenta mil (antes virava R$ 150,00)
    assert app.cent('1234.56') == 123456 and app.cent('') is None
    assert app.inteiro('12', 5) == 12 and app.inteiro('', 5) == 5 and app.inteiro('abc', 5) == 5 and app.inteiro('1.200', 5) == 1200


def test_todas_as_telas_abrem_com_a_estrutura_nova(cliente):
    pid = _exemplo(cliente)
    telas = [('/', ['Seus projetos', 'Novo projeto', 'Primeira vez aqui?', 'Situação do sistema']),
             (f'/p/{pid}', ['O que fazer agora', 'Monte o plano', 'Pesquisar tudo automaticamente', 'Mão de obra', 'Verificação', 'Configuração do projeto', 'Errou alguma coisa?']),
             (f'/p/{pid}/rh/1', ['1. Dados do cargo', 'Quantidade de profissionais', 'Títulos similares aceitos', '2. As 3 pesquisas de salário', '3. Valor no plano',
                                 'Salvar e voltar para Mão de obra', 'Salvar e continuar aqui', 'Excluir cargo']),
             (f'/p/{pid}/mat/12', ['1. Pesquisa automática', '2. Itens e as 3 pesquisas de preço', '3. Dados da rubrica', 'Adicionar itens', 'Adicionar outra linha',
                                   'Especificação', 'Pesquisar de novo só este item', 'Detalhes e comprovante']),
             (f'/p/{pid}/cnpjs', ['Como emitir e importar', 'Emitir na Receita', 'Importar da pasta Orça.AI']),
             (f'/p/{pid}/historico', ['Versões', 'Registro de eventos', 'Versão atual']),
             ('/tarefas', ['Tarefas', 'Nenhuma tarefa ainda']), ('/base-receita', ['Base oficial do CNPJ']),
             ('/ajuda', ['O caminho, do começo ao fim', 'Palavras que aparecem nas telas', 'R02']),
             ('/guia-de-interface', ['Cores', 'Botões', 'Campos de formulário', '--cor-primaria'])]
    for url, textos in telas:
        r = cliente.get(url)
        assert r.status_code == 200, url
        for t in textos:
            assert t in r.text, (url, t)
        assert 'Pular para o conteúdo' in r.text and 'id="modal-confirmar"' in r.text and r.text.count('<h1') == 1, url
        assert 'onsubmit="return confirm' not in r.text, url                                 # confirmações pela janela do sistema, não pelo "OK/Cancelar" do navegador
        for m in re.finditer(r'<(?:input|select|textarea)\b[^>]*>', r.text):               # todo campo visível tem rótulo
            tag = m.group(0)
            if 'type="hidden"' in tag or 'aria-label' in tag:
                continue
            ident = re.search(r'\bid="([^"]+)"', tag)
            dentro_de_label = 'type="checkbox"' in tag or 'type="radio"' in tag
            assert dentro_de_label or (ident and f'for="{ident.group(1)}"' in r.text), (url, tag[:120])
    pag = cliente.get(f'/p/{pid}/mat/12').text
    assert 'data-mascara="moeda"' in pag and 'data-mascara="cnpj"' in pag and 'inputmode="numeric"' in pag and 'type="date"' in pag and 'data-confirmar=' in pag


def test_telas_de_erro_explicam_o_que_fazer(cliente):
    r = cliente.get('/tarefa/999')
    assert r.status_code == 404 and 'Tarefa não encontrada' in r.text
    r = cliente.get('/p/999')
    assert r.status_code == 404 and 'Projeto não encontrado' in r.text
    pid = _exemplo(cliente)
    c2 = TestClient(cliente.app, raise_server_exceptions=False)
    r = c2.post(f'/p/{pid}/config', data={'nome': 'X', 'teto': 'abc', 'divisor_horas': 'legal'})   # valor que o sistema não entende
    assert r.status_code == 400 and 'Não deu para gravar' in r.text and 'Internal Server Error' not in r.text


def test_guia_de_passos_do_projeto(cliente):
    import app
    from orcamento import db
    novo = int(cliente.post('/projetos', data={'nome': 'Vazio', 'teto': '1.000,00'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    p, _ = db.carregar(novo)
    assert p.teto == 100000
    g = app.guia_do_projeto(p, dict(total=0, saldo=100000, erros=0, atencao=0))
    assert [x['chave'] for x in g] == ['plano', 'pesquisa', 'cnpjs', 'pendencias', 'teto', 'exportar']
    assert g[0]['atual'] and not any(x['feito'] for x in g)                                            # projeto vazio: o 1º passo é montar o plano
    pag = cliente.get(f'/p/{novo}').text
    assert 'Nenhum cargo cadastrado' in pag and 'Nenhuma rubrica de materiais' in pag and 'Próximo passo' in pag
    pid = _exemplo(cliente)
    p, _ = db.carregar(pid)
    ctx = app.contexto(p, pid, 1)
    g = app.guia_do_projeto(p, ctx['res'])
    assert g[0]['feito'] and g[1]['atual'] and g[1]['texto'].startswith('0 de')                        # plano montado; faltam as pesquisas comprovadas
    a = next(x for x in ctx['alertas'] if x.item.startswith('Item '))
    assert ctx['link_alerta'](a).startswith(f'/p/{pid}/')                                              # cada pendência leva à tela onde se corrige


def _campos(html):
    """O que o navegador mandaria ao enviar o formulário principal da tela, sem mexer em nada."""
    f = re.search(r'<form method="post"[^>]*class="pilha[^"]*"[^>]*data-avisar-saida>.*?</form>', html, re.S).group(0)
    f = re.sub(r'<template.*?</template>', '', f, flags=re.S)                                         # o modelo de linha nova não é enviado
    desfaz = lambda v: v.replace('&#34;', '"').replace('&#39;', "'").replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    d = {}
    for m in re.finditer(r'<input\b[^>]*\bname="([^"]+)"[^>]*>', f):
        tag = m.group(0)
        if 'type="file"' in tag or (('type="checkbox"' in tag or 'type="radio"' in tag) and ' checked' not in tag):
            continue
        v = re.search(r'\bvalue="([^"]*)"', tag)
        d[m.group(1)] = desfaz(v.group(1)) if v else ''
    for m in re.finditer(r'<select\b[^>]*\bname="([^"]+)".*?</select>', f, re.S):
        s = re.search(r'<option value="([^"]*)" selected', m.group(0))
        d[m.group(1)] = s.group(1) if s else ''
    for m in re.finditer(r'<textarea\b[^>]*\bname="([^"]+)"[^>]*>(.*?)</textarea>', f, re.S):
        d[m.group(1)] = desfaz(m.group(2))
    return d


def test_salvar_pelas_telas_novas_nao_muda_os_dados(cliente):
    """As telas mostram os valores no formato brasileiro (1.234,56); gravar sem alterar nada tem de manter tudo igual."""
    from orcamento import db
    pid = _exemplo(cliente)
    cliente.get(f'/p/{pid}')                                # ao abrir, o sistema acerta uma vez a escrita dos itens antigos (descrição simples, unidades)
    antes, v0 = db.carregar(pid)
    antes = antes.model_dump()
    for rota in ('rh/1', 'mat/15', 'mat/13'):
        dados = _campos(cliente.get(f'/p/{pid}/{rota}').text)
        assert len(dados) > 10, rota
        assert cliente.post(f'/p/{pid}/{rota}', data=dados, follow_redirects=False).status_code == 303, rota
    depois, v = db.carregar(pid)
    depois = depois.model_dump()
    assert v == v0 + 3
    por_item = lambda d: {r['item']: r for r in d['rubricas']}
    a, b = por_item(antes), por_item(depois)
    pesq = lambda r: [(q['nome'], q['cnpj'], q['data_pesquisa'], q['plataforma'], q['faixa_min'] or q['valor'], q['faixa_max'], q['valor'], q['evidencia']['url']) for q in r['pesquisas']]
    assert pesq(a[1]) == pesq(b[1]) and (a[1]['horas_mes'], a[1]['meses'], a[1]['cargo'], a[1]['regime']) == (b[1]['horas_mes'], b[1]['meses'], b[1]['cargo'], b[1]['regime'])
    assert a[1]['valor_mensal_plano'] == b[1]['valor_mensal_plano']
    for item in (15, 13):
        resumo = lambda r: [(s['descricao'], s['qtd'], s['precos'], s['valor_plano'], s['fontes']) for s in r['subitens']]
        assert resumo(a[item]) == resumo(b[item]), item
        assert a[item]['fontes'] == b[item]['fontes'] and a[item]['meses'] == b[item]['meses'] and a[item]['descricao'] == b[item]['descricao'], item


def test_link_digitado_em_item_sem_fornecedores_proprios_e_gravado(cliente):
    from orcamento import db
    pid = _exemplo(cliente)
    dados = _campos(cliente.get(f'/p/{pid}/mat/15').text)
    r = next(x for x in db.carregar(pid)[0].rubricas if x.item == 15)
    assert len(r.subitens[0].fontes) != 3                                                              # no exemplo, o item usa os fornecedores da rubrica
    dados['surl0_1'] = 'https://www.exemplo.com.br/agua-sanitaria/p'
    cliente.post(f'/p/{pid}/mat/15', data=dados)
    s = next(x for x in db.carregar(pid)[0].rubricas if x.item == 15).subitens[0]
    assert len(s.fontes) == 3 and s.fontes[1].evidencia.url == 'https://www.exemplo.com.br/agua-sanitaria/p' and s.fontes[1].nome == r.fontes[1].nome


def test_cnpj_preenche_o_nome_pela_base_local(cliente, monkeypatch):
    from orcamento import cnpj_base
    monkeypatch.setattr(cnpj_base, 'por_cnpj', lambda c: dict(razao='ATACADAO S.A.', situacao='ATIVA', municipio='SAO PAULO', uf='SP') if re.sub(r'\D', '', c) == '75315333000109' else None)
    assert cliente.get('/api/cnpj/75315333000109').json() == dict(ok=True, razao='ATACADAO S.A.', situacao='ATIVA', municipio='SAO PAULO', uf='SP')
    assert cliente.get('/api/cnpj/75315333000108').json()['motivo'] == 'CNPJ inválido'
    assert cliente.get('/api/cnpj/01157555001186').json()['ok'] is False


# ---------------------------------------------------------------- pedidos de 02/10/2026 (noite): tarefas, modo escuro, sistema sem dados de uma OSC
def _tarefa(pid, tipo, estado):
    from orcamento import db
    with db.conectar() as c:
        return c.execute('INSERT INTO tarefa (projeto_id, tipo, titulo, estado, progresso, criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?)',
                         (pid, tipo, f'{tipo} de teste', estado, 100, db.agora(), db.agora())).lastrowid


def test_tarefas_rotinas_do_sistema_e_limpeza(cliente):
    from orcamento import db, tarefas
    pid = _exemplo(cliente); outro = _exemplo(cliente)
    _tarefa(pid, 'tudo', 'concluída'); _tarefa(outro, 'tudo', 'concluída')
    diaria = _tarefa(None, 'vagas_diaria', 'concluída'); receita = _tarefa(None, 'base_receita', 'concluída'); rodando = _tarefa(None, 'vagas_diaria', 'rodando')
    pag = cliente.get('/tarefas').text
    assert 'Rotina do sistema' in pag and 'Limpar tarefas terminadas' in pag                         # a rotina não aparece como se fosse de um projeto
    # apagar o projeto de vez leva as tarefas dele E os registros terminados da coleta diária (falavam dos cargos dele)
    cliente.post(f'/p/{pid}/remover'); cliente.post(f'/p/{pid}/apagar-de-vez', data={'confirmacao': db.carregar(pid)[0].nome})
    ids = {t['id']: t for t in tarefas.listar(limite=50)}
    assert not any(t['projeto_id'] == pid for t in ids.values()) and diaria not in ids
    assert receita in ids and rodando in ids and any(t['projeto_id'] == outro for t in ids.values())  # o resto fica
    # limpar o registro: saem as terminadas, fica a que está rodando
    r = cliente.post('/tarefas/limpar')
    assert '2 tarefa(s) terminada(s) saíram do registro' in r.text
    assert [t['id'] for t in tarefas.listar(limite=50)] == [rodando]
    assert 'Não havia tarefas terminadas' in cliente.post('/tarefas/limpar').text and len(db.historico(outro)[0]) == 1   # o projeto não muda


def test_modo_escuro(cliente):
    pag = cliente.get('/').text
    assert 'id="alternar-tema"' in pag and "localStorage.getItem('osc-tema')" in pag and pag.index('osc-tema') < pag.index('<style>')   # o tema é decidido antes de a página ser desenhada
    assert ':root[data-tema="escuro"]' in pag and 'color-scheme: dark' in pag
    css = pag[pag.index('<style>'):pag.index('</style>')]
    regras = css[css.index('/* ---------------------------------------------------------------- 2. BASE */'):css.index('@media print')]
    soltas = [l.strip()[:90] for l in regras.splitlines() if re.search(r'(?<![\w-])(color|background|border-color)\s*:\s*#[0-9a-fA-F]{3,6}', l)]
    assert not soltas, soltas                                                                        # nenhum componente com cor fixa: tudo vem dos tokens (e muda com o tema)
    claro, escuro = css[css.index(':root {'):css.index(':root[data-tema="escuro"]')], css[css.index(':root[data-tema="escuro"]'):css.index('/* ---------------------------------------------------------------- 2. BASE */')]
    cores_claro = set(re.findall(r'(--cor-[a-z0-9-]+)\s*:', claro))
    assert cores_claro and cores_claro == set(re.findall(r'(--cor-[a-z0-9-]+)\s*:', escuro))        # toda cor do tema claro tem valor no escuro


def test_sistema_sem_dados_de_uma_osc_especifica(cliente):
    import importlib
    import app as appmod
    from orcamento import servico
    from orcamento.modelo import Projeto
    importlib.reload(appmod)                                                                         # o sistema como é entregue (sem a rota dos testes)
    limpo = TestClient(appmod.app)
    assert limpo.post('/exemplo').status_code in (404, 405)
    pag = limpo.get('/').text
    for texto in ('Parecer 8', 'exemplo real', '26 de Julho', '03977', 'CPIS'):
        assert texto not in pag, texto
    campo_cep = re.search(r'<input[^>]*name="cep"[^>]*>', pag).group(0)
    assert 'required' in campo_cep and 'value=""' in campo_cep                                       # sem CEP de ninguém pré-preenchido
    with pytest.raises(ValueError, match='CEP de entrega'):
        servico._cep(Projeto(nome='Sem CEP', teto=1000))
    assert servico._cep(Projeto(nome='Com CEP', teto=1000, cep='01001-000')) == '01001-000'
    for url in ('/ajuda', '/guia-de-interface', '/tarefas', '/base-receita'):
        html = limpo.get(url).text
        assert '26 de Julho' not in html and '03977' not in html and 'decisão da OSC' not in html, url
    # os pareceres técnicos foram dirigidos a uma OSC: as telas e o Excel só dizem que a regra é da Secretaria
    from orcamento.regras import REGRAS
    assert all(origem in ('regra da SEJC', 'regra do sistema', 'recomendação do sistema', 'configuração da rubrica') for _, origem in REGRAS.values())
    assert sorted(k for k, (_, origem) in REGRAS.items() if origem == 'regra da SEJC') == [f'R{n:02d}' for n in range(1, 18)] + ['S05']   # S05: empresa visível na página da vaga
    novo = int(limpo.post('/projetos', data={'nome': 'Qualquer OSC', 'teto': '1.000,00', 'cep': '01001-000'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    limpo.post(f'/p/{novo}/rubrica', data={'tipo': 'rh', 'nome': 'Educador social', 'horas_mes': '120', 'meses': '12'})                                            # um cargo sem pesquisas: gera pendências com o código da regra
    for url in ('/', '/ajuda', f'/p/{novo}', f'/p/{novo}/rh/1', f'/p/{novo}/cnpjs', f'/p/{novo}/historico', '/guia-de-interface'):
        html = limpo.get(url).text
        m = re.search(r'\b[Pp]arecer(es)?\b|\bPT[1-8]\b', html)
        assert not m, (url, html[max(0, m.start() - 80):m.end() + 80])
    pag = limpo.get(f'/p/{novo}').text                                                             # as regras vêm do órgão do projeto (o padrão é a SEJC-SP)
    assert 'regra da SEJC' in pag and 'com as regras de <b>Secretaria da Justiça e Cidadania do Estado de São Paulo</b>' in pag


def test_itens_e_pesquisas_em_lista_recolhida(cliente):
    """Pedido da OSC (03/10/2026): na tela de edição, cada item (e cada pesquisa de salário) é uma linha-resumo; o conteúdo completo só abre ao
    clicar. Os campos continuam na página (o que está recolhido também é salvo) e as âncoras #subN / #pesquisaN / #t-banco continuam existindo."""
    pid = _exemplo(cliente)
    pag = cliente.get(f'/p/{pid}/mat/12').text
    itens = re.findall(r'<details class="item-recolhivel item-cartao" id="sub(\d+)" data-recolhivel\s*(open)?>', pag)
    assert len(itens) > 1 and [int(i) for i, _ in itens] == list(range(len(itens))) and not any(aberto for _, aberto in itens)   # vários itens: todos recolhidos
    assert '<article class="cartao item-cartao"' not in pag and pag.count('<summary class="item-resumo">') == len(itens)
    assert 'class="itens__cabecalho"' in pag and 'data-recolher="abrir"' in pag and 'data-recolher="fechar"' in pag
    for i in range(len(itens)):                                                                     # os campos de cada item continuam no formulário
        for nome in ('sdesc', 'smarca', 'sesp', 'sqtd', 'splano', 'sdel'):
            assert f'name="{nome}{i}"' in pag, (nome, i)
    resumo = re.search(r'<summary class="item-resumo">.*?</summary>', pag, re.S).group(0)           # a linha mostra quantidade, os 3 preços, a média e o plano
    for rotulo in ('Qtd.', 'Pesquisa 1', 'Pesquisa 2', 'Pesquisa 3', 'Média', 'No plano'):
        assert rotulo in resumo, rotulo
    assert '<input' not in resumo and '<button' not in resumo                                       # nada para preencher na linha: clicar nela só abre e fecha

    pag = cliente.get(f'/p/{pid}/rh/1').text
    assert [int(k) for k in re.findall(r'<details class="item-recolhivel" id="pesquisa(\d)" data-recolhivel>', pag)] == [0, 1, 2]
    assert re.search(r'<details class="detalhe secao" id="t-banco" data-recolhivel', pag) and 'id="t-pesq"' in pag
    for k in range(3):
        for nome in ('nome', 'cnpj', 'faixa_min', 'faixa_max', 'plataforma', 'data', 'url'):
            assert f'name="{nome}{k}"' in pag, (nome, k)
        assert f'value="outra-{k}"' in pag
    js = cliente.get(f'/p/{pid}').text
    assert 'details[data-recolhivel]' in js and 'orca-abertos:' in js                               # abre o item da âncora e lembra o que estava aberto

    # serviço: a mesma lista, com "Proposta" no lugar de "Pesquisa"; quando a rubrica só tem um item, ele já vem aberto
    from orcamento import db
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'material', 'nome': 'Oficina de capoeira', 'regra': 'servico', 'meses': '10'})
    n = db.carregar(pid)[0].rubricas[-1].item
    cliente.post(f'/p/{pid}/mat/{n}', data={'descricao': 'Oficina de capoeira', 'meses': '10', 'regra': 'servico', 'n_sub': '0',
                                           'ndesc': ['Oficina de capoeira'], 'nesp': ['4 h por semana'], 'nqtd': ['1']})
    pag = cliente.get(f'/p/{pid}/mat/{n}').text
    assert re.search(r'<details class="item-recolhivel item-cartao" id="sub0" data-recolhivel\s*open>', pag)
    assert 'Proposta 1' in pag and 'name="sdel0"' in pag and 'name="sp0_2"' in pag and 'data-recolher="abrir"' not in pag      # um item só: sem "abrir todos"
