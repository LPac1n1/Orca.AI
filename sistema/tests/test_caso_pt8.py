"""Testes de regressão com o caso real do Parecer Técnico 8 (SEJC-SP). Rodar: python -m pytest -q sistema/tests"""
import datetime as dt
import os
import pytest

from orcamento.importar_pt8 import carregar
from orcamento.calculo import verificar, mensal_maximo_rh, total_projeto, media_subitem
from orcamento.modelo import RubricaRH
from orcamento.otimizador import otimizar
from orcamento.regras import cnpj_formatar

AQUI = os.path.dirname(__file__)
DADOS = os.path.join(AQUI, '..', '..', 'fase0', 'sejc', 'pt8_dados.json')
APONTADOS_PT8 = {'Folha sulfite 500 Folhas', 'Grampo 5000 Unidades', 'Lápis preto 4 Unidades', 'Suco de uva 1L', 'Café 500g',
                 'Café solúvel 100g', 'Pão de forma Integral 400g', 'Bisnaguinha 300g', 'Manteiga com sal 1Kg',
                 'Geleia de morango 320g', 'Maionese 250g', 'Sardinha com tomate 125g', 'Água sanitária 5L', 'Desinfetante 5L'}


@pytest.fixture
def pt8():
    return carregar(DADOS)


def todos_ativos(p):
    st = {}
    for r in p.rubricas:
        for f in (r.pesquisas if isinstance(r, RubricaRH) else r.fontes):
            st[cnpj_formatar(f.cnpj)] = 'ATIVA'
        if not isinstance(r, RubricaRH):
            for fs in r.fontes_por_subitem.values():
                for f in fs:
                    st[cnpj_formatar(f['cnpj'])] = 'ATIVA'
    return st


def test_total_do_plano_enviado(pt8):
    assert total_projeto(pt8) == 15000000


def test_reproduz_exatamente_os_14_itens_do_parecer_8(pt8):
    al = verificar(pt8, todos_ativos(pt8), hoje=dt.date(2026, 9, 9))  # data do parecer
    acima = {a.item.split(' / ')[-1] for a in al if a.regra == 'R02'}
    assert acima == APONTADOS_PT8


def test_reproduz_calculo_de_mao_de_obra_aceito(pt8):
    for r in pt8.rubricas:
        if isinstance(r, RubricaRH):
            maxm, vh, div = mensal_maximo_rh(r, pt8.config)
            assert maxm == r.valor_mensal_plano, r.cargo


def test_validade_de_180_dias(pt8):
    al = verificar(pt8, todos_ativos(pt8), hoje=dt.date(2026, 9, 25))
    assert any(a.regra == 'R06' and a.gravidade == 'erro' for a in al)


def test_cnpj_baixado_bloqueia(pt8):
    st = todos_ativos(pt8); st['10.361.314/0001-73'] = 'BAIXADA'
    al = verificar(pt8, st, hoje=dt.date(2026, 9, 9))
    assert any(a.regra == 'R07' and a.gravidade == 'erro' and 'ORSEGUPS' in a.mensagem for a in al)


def test_cnpj_da_plataforma_e_rejeitado(pt8):
    pt8.rubricas[0].pesquisas[0].cnpj = '03.753.088/0001-00'
    al = verificar(pt8, todos_ativos(pt8), hoje=dt.date(2026, 9, 9))
    assert any(a.regra == 'R08' and 'Catho' in a.mensagem for a in al)


def test_otimizador_fecha_no_teto_com_valores_defensaveis(pt8):
    res = otimizar(pt8, ajustar_horas=True)
    assert res['status'] == 'OK'
    novo = res['projeto']
    assert total_projeto(novo) == novo.teto
    al = verificar(novo, todos_ativos(novo), hoje=dt.date(2026, 9, 9))
    assert not [a for a in al if a.regra in ('R02', 'R03', 'S01', 'R05')], [a.mensagem for a in al if a.regra in ('R02', 'R03', 'S01', 'R05')]
    for r in novo.rubricas:
        if not isinstance(r, RubricaRH):
            for s in r.subitens:
                assert s.valor_plano in set(s.precos) | {media_subitem(s)}
    assert len([m for m in res['mudancas'] if m['campo'] == 'horas/mensal']) <= 4


def test_jornada_legal_sem_ajuste_de_horas_e_impossivel_com_prova(pt8):
    pt8.config.divisor_horas = 'legal'
    res = otimizar(pt8, ajustar_horas=False)
    assert res['status'] == 'SEM_SOLUCAO'
    assert 'Faltam R$ 22.055,70' in res['prova']                    # sistema no menor valor (R$ 270,92), como no plano enviado à SEJC
