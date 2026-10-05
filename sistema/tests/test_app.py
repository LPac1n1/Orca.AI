"""Teste de ponta a ponta da interface (sem navegador): exemplo → fechar no teto → carrinho em PDF → exportar → histórico."""
import os
import pytest
from fastapi.testclient import TestClient

RAIZ = os.path.join(os.path.dirname(__file__), '..', '..')
PDF_TENDA = os.path.join(RAIZ, 'docs-base', 'Parecer Técnico 8', 'Orçamentos', '15. Limpeza', 'Tenda.pdf')


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


def test_fluxo_completo(cliente):
    r = cliente.post('/exemplo', follow_redirects=False); assert r.status_code == 303
    pid = r.headers['location'].rsplit('/', 1)[-1]
    assert 'R$ 150.000,00' in cliente.get(f'/p/{pid}').text
    prev = cliente.post(f'/p/{pid}/otimizar', data={'ajustar_horas': '1'}); assert 'Solução exata' in prev.text
    cliente.post(f'/p/{pid}/otimizar/aplicar', data={'ajustar_horas': '1'})
    pag = cliente.get(f'/p/{pid}').text
    assert 'versão 2' in pag and 'R$ 0,00' in pag
    if os.path.exists(PDF_TENDA):
        r = cliente.post(f'/p/{pid}/mat/15/carrinho/1', files={'arquivo': ('Tenda.pdf', open(PDF_TENDA, 'rb'), 'application/pdf')})
        assert '6 preço(s) lido(s) com conferência; 0 para revisão' in r.text
    # editar as pesquisas do item 8 replica para os itens 9 e 10 (mesmo cargo), sem mudar horas/meses
    dados = {'cargo': 'Orientador socioeducativo', 'regime': 'RECIBO_MEI', 'horas_mes': '60', 'meses': '10'}
    for k, (n, c, v) in enumerate([('Emp A', '13.312.641/0001-23', '3000,00'), ('Emp B', '55.974.555/0001-26', '2500,00'), ('Emp C', '03.725.434/0001-47', '2800,00')]):
        dados.update({f'nome{k}': n, f'cnpj{k}': c, f'faixa_min{k}': v, f'data{k}': '2026-09-25'})
    cliente.post(f'/p/{pid}/rh/8', data=dados)
    pag = cliente.get(f'/p/{pid}').text
    assert pag.count('Emp A') >= 3
    x = cliente.get(f'/p/{pid}/exportar'); assert x.status_code == 200 and x.content[:2] == b'PK'
    h = cliente.get(f'/p/{pid}/historico').text
    assert 'plano fechado no teto' in h and 'importado do Parecer' in h


def test_pesquisa_sem_link_com_pdf_anexado(cliente):
    """Decisão da OSC (01/10/2026): um item/preço pode não ter link; a proposta em PDF é o comprovante."""
    import pymupdf
    from orcamento import db
    r = cliente.post('/exemplo', follow_redirects=False)
    pid = int(r.headers['location'].rsplit('/', 1)[-1])
    d = pymupdf.open(); pg = d.new_page()
    pg.insert_textbox(pymupdf.Rect(40, 40, 560, 800), 'PROPOSTA COMERCIAL\nMódulo: Pesquisa\n3.1 - Pesquisa online;\n3.2 - Relatório com gráficos;\n'
                                                      'Plano Mensal: R$ 270,92 mês;\nF&D SOLUTIONS\nCNPJ: 42.274.849/0001-37', fontsize=9)
    r = cliente.post(f'/p/{pid}/mat/13/sub/0/pdf/0', files={'arquivo': ('F&D Solutions.pdf', d.tobytes(), 'application/pdf')})
    assert 'PDF anexado' in r.text and 'sem link' in r.text and 'ver PDF' in r.text and 'anexado por você' in r.text
    p, _ = db.carregar(pid)
    rub = next(x for x in p.rubricas if x.item == 13); s = rub.subitens[0]
    assert s.fontes[0].evidencia.arquivo and s.fontes[0].evidencia.url is None and s.fontes[0].evidencia.origem == 'pdf'
    assert rub.referencia.startswith('Módulo: Pesquisa')
    r = cliente.post(f'/p/{pid}/mat/13/sub/0/pdf/1', files={'arquivo': ('nota.txt', b'isto nao e um pdf', 'text/plain')})
    assert 'Não anexado' in r.text
    # a tela deixa mudar empresa, CNPJ, data e produto de cada pesquisa; o PDF anexado continua valendo e o link segue vazio
    f = {'descricao': rub.descricao, 'meses': str(rub.meses), 'n_sub': '1', 'sdesc0': s.descricao, 'sqtd0': '1', 'referencia': 'Cadastro de atendidos\nPesquisa online'}
    for k in range(3):
        f.update({f'sp0_{k}': f'{s.precos[k] / 100:.2f}', f'sfn0_{k}': s.fontes[k].nome, f'sfc0_{k}': s.fontes[k].cnpj, f'sfd0_{k}': '2026-10-01',
                  f'sfp0_{k}': 'Plano mensal' if k == 0 else '', f'surl0_{k}': ''})
        f.update({f'fnome{k}': rub.fontes[k].nome, f'fcnpj{k}': rub.fontes[k].cnpj, f'fdata{k}': rub.fontes[k].data_pesquisa or ''})
    f['sfn0_1'] = 'Outro Sistema Ltda'
    cliente.post(f'/p/{pid}/mat/13', data=f)
    p, _ = db.carregar(pid)
    rub = next(x for x in p.rubricas if x.item == 13); s = rub.subitens[0]
    assert s.fontes[1].nome == 'Outro Sistema Ltda' and s.fontes[0].data_pesquisa == '2026-10-01' and s.produtos[0] == 'Plano mensal'
    assert s.fontes[0].evidencia.arquivo and s.fontes[0].evidencia.url is None
    assert rub.referencia == 'Cadastro de atendidos\nPesquisa online'


def test_remover_projeto_e_comecar_do_zero(cliente):
    """Pedido da OSC (02/10/2026): poder remover o projeto usado nos testes e começar outro do zero. Nada é apagado; dá para restaurar."""
    from orcamento import db
    r = cliente.post('/exemplo', follow_redirects=False)
    pid = int(r.headers['location'].rsplit('/', 1)[-1])
    assert 'Remover este projeto' in cliente.get(f'/p/{pid}').text
    r = cliente.post(f'/p/{pid}/remover')
    assert 'removido da lista' in r.text and 'Projetos removidos (1)' in r.text and 'Nenhum projeto em uso' in r.text
    assert db.listar() == [] and [x['id'] for x in db.listar(removidos=True)] == [pid]
    # removido = só consulta: nada é alterado nem pesquisado, e o histórico continua lá
    v = db.carregar(pid)[1]
    for rota in ('rubrica', 'pesquisar-tudo', 'mat/13/pesquisar', 'excluir/13'):
        assert cliente.post(f'/p/{pid}/{rota}', data={'tipo': 'rh'}, follow_redirects=False).status_code == 303
    assert db.carregar(pid)[1] == v
    pag = cliente.get(f'/p/{pid}').text
    assert 'removido da lista' in pag and 'Restaurar projeto' in pag and 'Remover este projeto' not in pag
    assert 'importado do Parecer' in cliente.get(f'/p/{pid}/historico').text
    # começar do zero: projeto novo, vazio, com outro número
    r = cliente.post('/projetos', data={'nome': 'Projeto novo', 'teto': '150.000,00', 'cep': '03977-015'}, follow_redirects=False)
    novo = int(r.headers['location'].rsplit('/', 1)[-1])
    p, v = db.carregar(novo)
    assert novo != pid and v == 1 and p.rubricas == [] and p.teto == 15_000_000
    assert [x['id'] for x in db.listar()] == [novo]
    cliente.post(f'/p/{novo}/rubrica', data={'tipo': 'rh', 'nome': 'Assistente Social', 'horas_mes': '120', 'meses': '12'})
    assert len(db.carregar(novo)[0].rubricas) == 1
    # restaurar
    r = cliente.post(f'/p/{pid}/restaurar-projeto')
    assert 'Projeto restaurado' in r.text and sorted(x['id'] for x in db.listar()) == [pid, novo] and db.listar(removidos=True) == []
    tipos = [e['tipo'] for e in db.historico(pid)[1]]
    assert 'PROJETO_REMOVIDO' in tipos and 'PROJETO_RESTAURADO' in tipos


def test_banco_antigo_ganha_a_coluna_de_projeto_removido(tmp_path, monkeypatch):
    """Os dados que já existem (banco criado antes desta função) continuam abrindo."""
    import sqlite3
    import orcamento.db as dbm
    c = sqlite3.connect(str(tmp_path / 'orcamento.db'))
    c.executescript("""CREATE TABLE projeto (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, criado_em TEXT NOT NULL);
        CREATE TABLE versao (id INTEGER PRIMARY KEY, projeto_id INTEGER NOT NULL, numero INTEGER NOT NULL, criado_em TEXT NOT NULL, autor TEXT, motivo TEXT,
                             json TEXT NOT NULL, UNIQUE(projeto_id, numero));
        INSERT INTO projeto VALUES (1, 'Antigo', '2026-09-25T19:24:00-03:00');
        INSERT INTO versao VALUES (1, 1, 1, '2026-09-25T19:24:00-03:00', 'usuário', 'criação', '{"nome": "Antigo", "teto": 100}');""")
    c.commit(); c.close()
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    assert [x['nome'] for x in dbm.listar()] == ['Antigo'] and dbm.removido_em(1) is None
    dbm.remover_projeto(1)
    assert dbm.listar() == [] and dbm.removido_em(1) and dbm.carregar(1)[0].nome == 'Antigo'


def test_apagar_projeto_de_vez(cliente, tmp_path):
    """Pedido da OSC (02/10/2026): poder remover definitivamente. Só projeto já removido da lista, com o nome digitado; não tem volta."""
    import sqlite3
    import pymupdf
    import pytest
    from orcamento import db
    outro = int(cliente.post('/projetos', data={'nome': 'Fica', 'teto': '1.000,00'}, follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    pid = int(cliente.post('/exemplo', follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    nome = db.carregar(pid)[0].nome
    d = pymupdf.open(); d.new_page().insert_text((40, 60), 'Proposta comercial R$ 270,92')
    cliente.post(f'/p/{pid}/mat/13/sub/0/pdf/0', files={'arquivo': ('proposta.pdf', d.tobytes(), 'application/pdf')})
    db.produtos_guardar(pid, 14, 'Leite 1L', [dict(nivel=0, ofertas=[])])
    pasta = tmp_path / 'projetos' / str(pid)
    assert pasta.is_dir() and any(pasta.rglob('*.pdf'))
    # 1) projeto em uso não pode ser apagado: primeiro a remoção da lista
    r = cliente.post(f'/p/{pid}/apagar-de-vez', data={'confirmacao': nome})
    assert 'primeiro remova o projeto da lista' in r.text and db.existe(pid)
    with pytest.raises(ValueError):
        db.apagar_projeto(pid)
    cliente.post(f'/p/{pid}/remover')
    assert 'Apagar de vez' in cliente.get('/').text
    # 2) nome errado: nada é apagado
    r = cliente.post(f'/p/{pid}/apagar-de-vez', data={'confirmacao': 'outro nome'})
    assert 'Nada foi apagado' in r.text and db.existe(pid) and pasta.is_dir()
    # 3) nome certo: some tudo o que é do projeto, e só dele
    r = cliente.post(f'/p/{pid}/apagar-de-vez', data={'confirmacao': nome})
    assert 'apagado de vez' in r.text and 'Projetos removidos' not in r.text
    assert not db.existe(pid) and db.carregar(pid) == (None, None) and not pasta.exists()
    assert [x['id'] for x in db.listar()] == [outro] and db.listar(removidos=True) == []
    assert db.produtos_do_banco(pid, 14) == {} and db.historico(pid) == ([], [])
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM arquivo WHERE caminho LIKE ?", (f'projetos/{pid}/%',)).fetchone()[0] == 0
        ev = [dict(x) for x in c.execute("SELECT projeto_id, detalhe FROM evento WHERE tipo='PROJETO_APAGADO'")]
        assert len(ev) == 1 and ev[0]['projeto_id'] is None and nome in ev[0]['detalhe']        # fica o registro do que foi apagado
        with pytest.raises(sqlite3.DatabaseError):                                               # o log continua imutável
            c.execute('DELETE FROM evento')
    assert db.carregar(outro)[0].nome == 'Fica' and len(db.historico(outro)[0]) == 1               # o outro projeto não foi tocado
    # 4) endereços do projeto apagado não quebram o sistema
    assert cliente.get(f'/p/{pid}').status_code == 404 and cliente.get(f'/p/{pid}/mat/13').status_code == 404
    assert cliente.post(f'/p/{pid}/pesquisar-tudo', follow_redirects=False).status_code == 404
    # 5) começar do zero: projeto novo, com histórico limpo
    novo = int(cliente.post('/exemplo', follow_redirects=False).headers['location'].rsplit('/', 1)[-1])
    assert db.carregar(novo)[1] == 1 and len(db.historico(novo)[0]) == 1 and db.produtos_do_banco(novo, 14) == {}
