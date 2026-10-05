"""Pedido de 02/10/2026: a SEJC pede que a página da vaga mostre as informações da empresa. A Catho só as mostra para quem está logado:
sem login, a página traz o nome e "Cadastre-se gratuitamente para ver mais informações da empresa"."""
import pytest
from fastapi.testclient import TestClient


def _pdf(texto):
    import pymupdf
    d = pymupdf.open(); pg = d.new_page()
    pg.insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto, fontsize=9)
    return d.tobytes()


CORPO = ('Psicólogo\nClínica Exemplo de Atendimento Infantil\nSão Paulo - SP\nSalário R$ 3.000,00\nRegime de contratação CLT\n'
         'Descrição da vaga: atendimento psicológico individual e em grupo, elaboração de relatórios e participação nas reuniões da equipe técnica, '
         'de segunda a sexta-feira, das 9h às 18h.\n')
OCULTA = CORPO + 'Sobre a empresa\nCLÍNICA EXEMPLO DE ATENDIMENTO INFANTIL\nCadastre-se gratuitamente para ver mais informações da empresa.'
VISIVEL = CORPO + 'Sobre a empresa\nCLÍNICA EXEMPLO DE ATENDIMENTO INFANTIL\nClínica de atendimento infantil com 20 anos de atuação. Porte: pequeno. São Paulo/SP.'


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv('ORCAMENTO_DADOS', str(tmp_path))
    import importlib, orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    import app as appmod
    importlib.reload(appmod)
    return TestClient(appmod.app)


def test_reconhece_a_pagina_que_esconde_a_empresa():
    from orcamento.vagas import empresa_oculta
    assert empresa_oculta(_pdf(OCULTA)) and not empresa_oculta(_pdf(VISIVEL))


def test_vaga_da_catho_sem_login_nao_entra_e_a_pesquisa_fica_pendente(cliente):
    from orcamento import db, servico, vagas as V
    from orcamento.calculo import verificar
    r = cliente.post('/projetos', data={'nome': 'T', 'teto': '100.000,00', 'cep': '01001-000'}, follow_redirects=False)
    pid = int(r.headers['location'].rsplit('/', 1)[-1])
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': 'Psicólogo', 'horas_mes': '90', 'meses': '10'})
    for emp, cnpj, sal, plat, txt in [('Clínica Um', '11111111000111', 250000, 'Catho', OCULTA), ('Info Dois', '22222222000122', 300000, 'InfoJobs', VISIVEL)]:
        v = dict(titulo='Psicólogo', empresa=emp, url=f'https://x/{emp}', plataforma=plat, faixa_min=sal, faixa_max=sal, unidade='MONTH')
        V.guardar_no_banco('Psicólogo', v, dict(status='🟢', cnpj=cnpj, razao_social=emp.upper(), motivo='teste'),
                           _pdf(txt.replace('3.000,00', f'{sal // 100:,}'.replace(',', '.') + ',00')))
    assert [v['empresa'] for v in V.tres_do_banco('Psicólogo')] == ['Info Dois']           # a da Catho (mais barata) fica de fora
    pag = cliente.get(f'/p/{pid}/rh/1').text
    assert 'a página não mostra as informações da empresa (a Catho só mostra com login)' in pag
    # pesquisa já gravada com a página da Catho sem login: pendência S05 e o cargo não está pronto
    p = db.carregar(pid)[0]
    rh = p.rubricas[0]
    rh.pesquisas[0] = servico._pesquisa_da_vaga(pid, next(x for x in V.vagas_do_banco('Psicólogo') if x['empresa'] == 'Clínica Um'))
    db.salvar(pid, p)
    assert any(a.regra == 'S05' and a.gravidade == 'erro' for a in verificar(p)) and not servico.pesquisa_completa(rh.pesquisas[0])
    assert 'A página não mostra as informações da empresa' in cliente.get(f'/p/{pid}/rh/1').text
    # a OSC anexa a página impressa com o login: a da Catho sem login é recusada; a com a empresa visível vale
    loc = cliente.post(f'/p/{pid}/rh/1/pesquisa/0/pdf', files={'arquivo': ('vaga.pdf', _pdf(OCULTA), 'application/pdf')}, follow_redirects=False).headers['location']
    assert 'N%C3%A3o%20anexado' in loc
    loc = cliente.post(f'/p/{pid}/rh/1/pesquisa/0/pdf', files={'arquivo': ('vaga.pdf', _pdf(VISIVEL.replace('3.000,00', '2.500,00')), 'application/pdf')},
                       follow_redirects=False).headers['location']
    assert 'ok=1' in loc and 'aparece%20no%20PDF' in loc
    q = db.carregar(pid)[0].rubricas[0].pesquisas[0]
    assert q.evidencia.origem == 'pdf' and q.evidencia.url == 'https://x/Clínica Um' and servico.pesquisa_completa(q)
    assert not any(a.regra == 'S05' for a in verificar(db.carregar(pid)[0]))


# ---------------------------------------------------------------- sessão da Catho feita pela OSC (o login é dela; aqui a captura é simulada)
@pytest.fixture
def com_sessao(cliente, tmp_path, monkeypatch):
    import orcamento.db as dbm
    from orcamento import sessao_catho as SC
    monkeypatch.setattr(dbm, 'PASTA_LOCAL', str(tmp_path / 'local'))          # nunca o perfil real deste computador
    paginas = {'texto': VISIVEL}

    async def capturar(url, rotulo, empresa=None):
        return _pdf(paginas['texto']), '2026-10-02T20:00:00-03:00'
    monkeypatch.setattr(SC, 'capturar', capturar)
    return paginas


def _projeto_com_catho(cliente):
    from orcamento import db, servico, vagas as V
    r = cliente.post('/projetos', data={'nome': 'T', 'teto': '100.000,00', 'cep': '01001-000'}, follow_redirects=False)
    pid = int(r.headers['location'].rsplit('/', 1)[-1])
    cliente.post(f'/p/{pid}/rubrica', data={'tipo': 'rh', 'nome': 'Psicólogo', 'horas_mes': '90', 'meses': '10'})
    for emp, cnpj in [('Clínica Um', '11111111000111'), ('Clínica Dois', '22222222000122'), ('Clínica Três', '33333333000133')]:
        v = dict(titulo='Psicólogo', empresa=emp, url=f'https://www.catho.com.br/vagas/psicologo/{cnpj[:4]}', plataforma='Catho', faixa_min=300000,
                 faixa_max=300000, unidade='MONTH')
        V.guardar_no_banco('Psicólogo', v, dict(status='🟢', cnpj=cnpj, razao_social=emp.upper(), motivo='teste'), _pdf(OCULTA))
    p = db.carregar(pid)[0]
    p.rubricas[0].pesquisas = [servico._pesquisa_da_vaga(pid, v) for v in V.vagas_do_banco('Psicólogo')]
    db.salvar(pid, p)
    return pid


def test_sem_sessao_a_tela_explica_como_entrar(cliente, tmp_path, monkeypatch):
    import orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_LOCAL', str(tmp_path / 'local'))
    pid = _projeto_com_catho(cliente)
    pag = cliente.get(f'/p/{pid}').text
    assert 'Entrar na Catho' in pag and '3 pesquisa(s)</b> usam páginas da Catho' in pag and 'o sistema não os vê nem guarda' in pag
    rh = cliente.get(f'/p/{pid}/rh/1').text
    assert rh.count('id="catho"') == 1 and rh.index('id="catho"') > rh.index('</form>')        # fora do formulário principal (não há formulário dentro de formulário)


def test_com_sessao_as_paginas_da_catho_sao_guardadas_de_novo(cliente, com_sessao):
    import asyncio
    from orcamento import db, servico, sessao_catho as SC, vagas as V
    from orcamento.calculo import verificar
    pid = _projeto_com_catho(cliente)
    assert sum(a.regra == 'S05' for a in verificar(db.carregar(pid)[0])) == 3
    os = __import__('os'); os.makedirs(SC.perfil()); SC._gravar(ok=True)
    assert SC.tem_sessao() and 'Sessão da Catho ativa neste computador' in cliente.get(f'/p/{pid}').text

    class Ctx:
        id = 0; avisos = []
        def progresso(self, *a, **k): pass
        def etapa(self, *a): pass
        def aviso(self, m): self.avisos.append(m)
    res = asyncio.run(servico.recapturar_catho(pid, Ctx()))
    p = db.carregar(pid)[0]
    assert res['recapturadas'] == 3 and not any(a.regra == 'S05' for a in verificar(p)) and servico.rh_pronto(p.rubricas[0])
    assert all(not V.empresa_oculta(caminho=db.caminho_absoluto(q.evidencia.arquivo)) for q in p.rubricas[0].pesquisas)
    assert len(V.tres_do_banco('Psicólogo')) == 3                                                  # as vagas da Catho voltam a valer no banco
    # coleta com sessão: a página da Catho é guardada pela sessão (a captura comum não é usada)
    pdf, _ = asyncio.run(V.capturar_pdf(None, 'https://www.catho.com.br/vagas/psicologo/9', 'teste'))
    assert not V.empresa_oculta(pdf)


def test_sessao_expirada_e_sair(cliente, com_sessao):
    import asyncio, os
    from orcamento import db, servico, sessao_catho as SC
    pid = _projeto_com_catho(cliente)
    os.makedirs(SC.perfil()); SC._gravar(ok=True)
    com_sessao['texto'] = OCULTA                                                                    # a Catho voltou a esconder a empresa: sessão expirou

    class Ctx:
        id = 0; avisos = []
        def progresso(self, *a, **k): pass
        def etapa(self, *a): pass
        def aviso(self, m): self.avisos.append(m)
    c = Ctx()
    res = asyncio.run(servico.recapturar_catho(pid, c))
    assert res['recapturadas'] == 0 and not SC.tem_sessao() and any('expirou' in a for a in c.avisos)
    assert 'Entrar na Catho' in cliente.get(f'/p/{pid}').text and 'expirou' in cliente.get(f'/p/{pid}').text
    SC._gravar(ok=True)
    r = cliente.post('/catho/sair', headers={'referer': f'http://127.0.0.1:8000/p/{pid}'}, follow_redirects=False)
    assert r.headers['location'].startswith(f'/p/{pid}?msg=') and not os.path.exists(SC.perfil()) and not SC.tem_sessao()
