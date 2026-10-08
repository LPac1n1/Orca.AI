"""A IA à vista (pedido da OSC, 08/10/2026): "Não sabia nem que existia cota gratuita. Seria bom deixar isso bem visível no sistema, para
saber quando a IA pode/está sendo utilizada ou não." O topo de todas as telas mostra a situação; a tela /ia explica; a proposta e o
"Pesquisar tudo" dizem quantas perguntas ficaram sem resposta."""
import time

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


def _ia(monkeypatch, chave='chave-de-teste', modelos=('m1', 'm2'), esgotados=()):
    from orcamento import ia
    monkeypatch.setattr(ia, 'chave', lambda: chave)
    monkeypatch.setattr(ia, 'PREFERIDOS', list(modelos))
    monkeypatch.setattr(ia, '_nomes', list(modelos))
    monkeypatch.setattr(ia, '_modelo', modelos[0] if modelos else None)
    monkeypatch.setattr(ia, '_esgotados', {m: time.strftime('%Y-%m-%d') for m in esgotados})
    monkeypatch.setattr(ia, '_uso', dict(novas=0, guardadas=0, sem_resposta=0))
    monkeypatch.setattr(ia, '_falha', {})
    return ia


def test_estado_da_ia_sem_chave_pronta_parte_da_cota_e_cota_esgotada(cliente, monkeypatch):
    ia = _ia(monkeypatch, chave=None)
    e = ia.estado()
    assert (e['chave'], e['situacao'], e['rotulo'], e['hoje']) == (False, 'sem_chave', 'sem chave', 0)
    pag = cliente.get('/ia').text
    assert 'Sem chave neste computador' in pag and 'nenhuma pesquisa está usando a IA' in pag and 'GEMINI_PASSO_A_PASSO.md' in pag
    assert 'href="/ia"' in cliente.get('/').text and 'sem chave' in cliente.get('/').text            # o indicador está no topo de todas as telas
    ia = _ia(monkeypatch)
    assert ia.estado()['situacao'] == 'pronta' and ia.estado()['modelo'] == 'm1'
    assert 'Ligada e pronta' in cliente.get('/ia').text and '>ligada<' in cliente.get('/').text
    ia = _ia(monkeypatch, esgotados=['m1'])
    e = ia.estado()
    assert (e['situacao'], e['modelo'], e['esgotados']) == ('parcial', 'm2', ['m1'])
    assert 'continua usando a IA' in cliente.get('/ia').text and 'parte da cota' in cliente.get('/').text
    ia = _ia(monkeypatch, esgotados=['m1', 'm2'])
    assert ia.estado()['situacao'] == 'esgotada' and ia.estado()['modelo'] is None
    pag = cliente.get('/ia').text
    assert 'A cota gratuita de hoje acabou' in pag and 'as pesquisas de agora seguem sem a IA' in pag and 'sem cota hoje' in cliente.get('/').text
    # a pergunta sem resposta é contada (e o motivo fica à vista); nada é aprovado no lugar da IA
    antes = ia.marca()
    assert ia.mesmo_produto(['Caneta A', 'Caneta B', 'Caneta C']) is None
    assert ia.desde(antes) == dict(novas=0, guardadas=0, sem_resposta=1)
    e = ia.estado()
    assert e['falha']['motivo'] == 'a cota gratuita de hoje acabou em todos os modelos' and e['falha']['tipo'] == 'conferir se 3 anúncios são o mesmo produto'
    assert '1 pergunta(s) sem resposta' in cliente.get('/ia').text
    # resposta já guardada: é reaproveitada, sem gastar a cota — e aparece no uso de hoje
    from orcamento import db
    import hashlib, json
    dados = {'anuncio_1': 'X', 'anuncio_2': 'Y'}
    pergunta = json.dumps(dados, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha256(('mesmo_produto' + ia.MESMO_PRODUTO + pergunta).encode()).hexdigest()[:16]
    with db.conectar() as c:
        c.execute('INSERT INTO ia_log (quando, projeto_id, tipo, modelo, pergunta, resposta) VALUES (?,?,?,?,?,?)',
                  (db.agora(), None, 'mesmo_produto', 'm1', f'{h}|{pergunta}', '{"mesmo_produto": true, "motivo": "igual"}'))
    assert ia.mesmo_produto(['X', 'Y']) == (True, 'igual') and ia.desde(antes) == dict(novas=0, guardadas=1, sem_resposta=1)
    e = ia.estado()
    assert e['hoje'] == 1 and e['por_tipo'] == [('conferir se 3 anúncios são o mesmo produto', 1)] and e['ultima']['modelo'] == 'm1'
    assert 'Para que ela foi usada hoje' in cliente.get('/ia').text
