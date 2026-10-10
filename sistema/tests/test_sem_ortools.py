"""O sistema funciona sem o OR-Tools. Em 09/10/2026 o Controle de Aplicativo do Windows bloqueou as bibliotecas dele (ortools.dll e
libscip.dll) num computador em uso: `import app` falhava e o sistema inteiro deixou de abrir. Agora, quando o OR-Tools não carrega, quem faz as
contas são os otimizadores próprios, em Python puro — as mesmas regras e os mesmos pesos (orcamento/produtos/teto.py e orcamento/otimizador.py).
Estes testes forçam esse caminho, para ele ser conferido também nos computadores em que o OR-Tools carrega."""
import importlib
import sys

import pytest

from orcamento.calculo import media_rh, media_subitem, total_projeto, verificar
from orcamento.modelo import Config, PesquisaSalarial, Projeto, RubricaMaterial, RubricaRH, Subitem
from orcamento.regras import divisor_horas, horas_maximas, valor_hora


@pytest.fixture
def sem_ortools(monkeypatch):
    from orcamento import otimizador
    from orcamento.produtos import teto
    monkeypatch.setattr(teto, 'cp_model', None)
    monkeypatch.setattr(otimizador, 'cp_model', None)


def test_o_sistema_abre_quando_o_ortools_nao_carrega(monkeypatch):
    import orcamento.cp as cp
    for k in [k for k in sys.modules if k == 'ortools' or k.startswith('ortools.')]:
        monkeypatch.delitem(sys.modules, k)
    monkeypatch.setitem(sys.modules, 'ortools', None)   # importar o OR-Tools passa a falhar, como quando o Windows bloqueia a biblioteca
    try:
        importlib.reload(cp)
        assert cp.cp_model is None and not cp.disponivel() and cp.MOTIVO
    finally:
        monkeypatch.undo()
        importlib.reload(cp)                            # volta ao que este computador tem
    assert cp.disponivel() == (cp.MOTIVO is None)


def test_teto_da_rubrica_sem_o_ortools(sem_ortools):
    """Os mesmos casos de tests/test_teto.py, pelo otimizador próprio."""
    import test_teto
    from orcamento.produtos import teto
    for nome in [n for n in dir(test_teto) if n.startswith('test_')]:
        getattr(test_teto, nome)()
    op = test_teto.op
    r = teto.otimizar([dict(desc='Café 500g', qtd=4, opcoes=[op([1500, 1700, 2000]), op([1400, 1450, 1500], distancia=0.2)]),
                       dict(desc='Leite 1L', qtd=10, opcoes=[op([500, 520, 560])])], teto=11800)
    assert r['status'] == teto.SEM_ORTOOLS and r['total'] <= 11800 and r['sobra'] == 11800 - r['total']
    assert [l['acao'] for l in r['linhas']] == ['mantido', 'mantido']                                  # ninguém sai: cabe ajustando valor e opção
    for l in r['linhas']:
        assert l['valor'] in (min(l['precos']), l['media']) and l['subtotal'] == l['valor'] * l['qtd']   # só o menor preço ou a média
    assert r['sobra'] <= int(11800 * 0.05)                                                             # e fica dentro da folga do teto


def _projeto(teto, faixas=(300000, 100000, 120000), horas_max=220, defensaveis=True):
    sal = [(1000000, 1100000, 1200000), (350000, 380000, 420000), (220000, 250000, 300000)]
    cargos = [RubricaRH(item=i + 1, cargo=c, horas_mes=40, meses=10, faixa_pretendida=f,
                        pesquisas=[PesquisaSalarial(nome=f'EMPRESA {i}{k}', cnpj=str(k), valor=v, faixa_min=v) for k, v in enumerate(sal[i])])
              for i, (c, f) in enumerate(zip(('Coordenador de Projetos', 'Educador Social', 'Auxiliar Administrativo'), faixas))]
    itens = [Subitem(descricao=f'Item {k}', qtd=q, precos=list(ps)) for k, (q, ps) in enumerate((
        (20, (999, 1099, 1299)), (20, (529, 548, 649)), (10, (2289, 2999, 3299)), (5, (2190, 2299, 2390)), (5, (1232, 1398, 1699)), (3, (1299, 1489, 1559)),
        (10, (245, 279, 319)), (2, (1918, 2190, 3159)), (5, (1390, 1398, 1999)), (10, (749, 838, 839)), (1, (809, 1049, 1444)), (5, (479, 499, 960))))]
    sistema = RubricaMaterial(item=5, descricao='Sistema de gestão', meses=10, regra='sistema', subitens=[Subitem(descricao='Sistema', qtd=1, precos=[27092, 49900, 32000])])
    return Projeto(nome='T', teto=teto, config=Config(horas_max_mes=horas_max, valores_defensaveis=defensaveis),
                   rubricas=cargos + [RubricaMaterial(item=4, descricao='Alimentação', meses=10, regra='mercado', subitens=itens), sistema])


def _nas_faixas(p):
    """O total com cada cargo nas horas mais perto da faixa, os itens na média e o sistema no menor preço."""
    from orcamento.calculo import horas_pela_faixa
    return (sum(horas_pela_faixa(c, p.config)[1] * c.meses for c in p.rubricas[:3]) + sum(media_subitem(s) * s.qtd * 10 for s in p.rubricas[3].subitens)
            + 27092 * 10)


def _conferir(p, r):
    """O que vale para qualquer solução: fecha no centavo, horas inteiras dentro do limite, cada item no menor preço ou na média, sistema no menor."""
    assert r['status'] == 'OK', r
    n = r['projeto']
    assert total_projeto(n) == p.teto
    for rub in n.rubricas:
        if isinstance(rub, RubricaRH):
            vh = valor_hora(media_rh(rub), divisor_horas(rub.cargo, p.config.divisor_horas)[0])
            assert 1 <= rub.horas_mes <= horas_maximas(rub.cargo, p.config) and rub.valor_mensal_plano == vh * rub.horas_mes
        else:
            for s in rub.subitens:
                assert s.valor_plano == min(s.precos) if rub.regra == 'sistema' else s.valor_plano in (min(s.precos), media_subitem(s))
    assert not [a for a in verificar(n) if a.regra in ('R02', 'R03', 'S01', 'S12', 'R17') and a.gravidade == 'erro']
    return n


def test_fechar_no_teto_sem_o_ortools(sem_ortools):
    from orcamento import otimizador
    from orcamento.otimizador import otimizar
    # 1) as faixas cabem no teto: os cargos ficam praticamente na faixa e os itens fazem o ajuste fino
    p = _projeto(teto=0)
    p.teto = _nas_faixas(p) - 12_340                                                  # R$ 123,40 abaixo do total "ideal"
    r = otimizar(p)
    n = _conferir(p, r)
    assert r['solver'] == otimizador.SEM_ORTOOLS and len(r['faixas']) == 3
    assert max(abs(f['pct']) for f in r['faixas']) <= 2.0, r['faixas']
    # 2) as faixas NÃO cabem (10% acima do teto): a diferença é repartida entre os cargos em proporção da faixa — ninguém fica longe sozinho
    p = _projeto(teto=0)
    p.teto = _nas_faixas(p) * 9 // 100 * 10                                           # 10% abaixo
    r = otimizar(p)
    _conferir(p, r)
    pcts = [f['pct'] for f in r['faixas']]
    assert all(x < 0 for x in pcts) and max(pcts) - min(pcts) <= 3.0, pcts
    assert r['sobra_das_faixas']['excesso_minimo'] > 0                                # a tela avisa: "as faixas não cabem no teto"
    # 3) sem ajustar as horas, só os itens se mexem (e só nos dois valores permitidos)
    p = _projeto(teto=0)
    for c, h in zip(p.rubricas[:3], (66, 58, 99)):
        c.horas_mes = h
    base = sum(valor_hora(media_rh(c), 220) * c.horas_mes * 10 for c in p.rubricas[:3]) + 27092 * 10
    p.teto = base + sum((min(s.precos) if k % 2 else media_subitem(s)) * s.qtd * 10 for k, s in enumerate(p.rubricas[3].subitens))   # uma combinação que existe
    r = otimizar(p, ajustar_horas=False)
    n = _conferir(p, r)
    assert [c.horas_mes for c in n.rubricas[:3]] == [66, 58, 99] and not [m for m in r['mudancas'] if m['campo'] != 'valor' and 'h /' in m['antes'] and m['antes'].split(' h')[0] != m['depois'].split(' h')[0]]
    # 4) teto fora do alcance: não força números — devolve a prova
    p = _projeto(teto=90_000_000)
    r = otimizar(p)
    assert r['status'] == 'SEM_SOLUCAO' and 'Máximo alcançável dentro das regras' in r['prova']
    p = _projeto(teto=100_000)
    r = otimizar(p)
    assert r['status'] == 'SEM_SOLUCAO' and 'Mínimo alcançável dentro das regras' in r['prova']
    # 5) dados incompletos: a mesma resposta de sempre
    p = _projeto(teto=5_000_000)
    p.rubricas[3].subitens[0].precos = [999, None, 1299]
    assert otimizar(p)['status'] == 'DADOS_INCOMPLETOS'
    # 6) cargos sem faixa: mexe em poucas horas, perto do plano atual
    p = _projeto(teto=0, faixas=(None, None, None))
    for c, h in zip(p.rubricas[:3], (60, 55, 90)):
        c.horas_mes = h; c.valor_mensal_plano = valor_hora(media_rh(c), 220) * h
    for s in p.rubricas[3].subitens:
        s.valor_plano = media_subitem(s)
    p.rubricas[4].subitens[0].valor_plano = 27092
    p.teto = total_projeto(p) + 43_210                                               # falta pouco para o teto: uma hora a mais num cargo e o resto nos itens
    r = otimizar(p)
    n = _conferir(p, r)
    assert sum(abs(a.horas_mes - b.horas_mes) for a, b in zip(p.rubricas[:3], n.rubricas[:3])) <= 3
    # 7) sem itens para o ajuste fino, poucas combinações de horas fecham no centavo e elas ficam longe do ponto de partida: a busca completa
    #    (todas as somas possíveis das horas, em conjuntos de bits) acha — e, quando ela não acha, é porque não existe
    p = _projeto(teto=0)
    p.rubricas[3].subitens = []
    p.teto = sum(valor_hora(media_rh(c), 220) * h * 10 for c, h in zip(p.rubricas[:3], (211, 138, 25))) + 27092 * 10
    _conferir(p, otimizar(p))
    p.teto += 3                                                                      # 3 centavos a mais: todos os valores são múltiplos de 10
    r = otimizar(p)
    assert r['status'] == 'SEM_SOLUCAO' and 'nenhuma combinação exata' in r['prova']


def test_a_tela_diz_quando_o_otimizador_proprio_foi_usado(tmp_path, monkeypatch):
    import orcamento.db as dbm
    monkeypatch.setenv('ORCAMENTO_DADOS', str(tmp_path))
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    monkeypatch.setattr(dbm, 'PASTA_LOCAL', str(tmp_path / 'local'))
    import app as appmod
    importlib.reload(appmod)
    from conftest import registrar_exemplo
    from fastapi.testclient import TestClient
    from orcamento import otimizador
    registrar_exemplo(appmod)
    monkeypatch.setattr(otimizador, 'cp_model', None)
    c = TestClient(appmod.app)
    pid = c.post('/exemplo', follow_redirects=False).headers['location'].rsplit('/', 1)[-1]
    pag = c.post(f'/p/{pid}/otimizar', data={'ajustar_horas': '1'}).text
    assert 'Solução exata' in pag and 'Conta feita pelo otimizador próprio do sistema' in pag
    c.post(f'/p/{pid}/otimizar/aplicar', data={'ajustar_horas': '1'})
    assert 'R$ 0,00' in c.get(f'/p/{pid}').text                       # aplicado: o plano fecha no teto (diferença zero)
    assert 'O "Fechar no teto" diz que usou o otimizador próprio' in c.get('/ajuda').text
