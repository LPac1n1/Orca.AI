"""Teto por rubrica (D9): cabe ajustando valor/opção; tira só se inevitável; acrescenta só se sobrar além da folga."""
from orcamento.produtos.teto import otimizar


def op(precos, distancia=0, ean_em=3):
    return dict(precos=precos, distancia=distancia, ean_em=ean_em)


def test_cabe_ajustando_valores_sem_tirar_nem_acrescentar():
    itens = [dict(desc='Água sanitária 5L', qtd=5, opcoes=[op([1390, 1459, 1489])]),
             dict(desc='Sacos de lixo', qtd=5, opcoes=[op([1490, 2590, 4999])])]
    extra = [dict(desc='Limpador multiuso', opcoes=[op([659, 1559, 929])])]
    r = otimizar(itens, teto=23000, extras=extra)   # soma das médias 223,60: sobra de 2,8% (abaixo da folga)
    assert all(l['acao'] == 'mantido' for l in r['linhas']) and r['total'] <= 23000


def test_prefere_opcao_mais_barata_a_tirar_item():
    # opção 1 (sem troca) estoura o teto; opção 2 (troca) cabe: o motor troca em vez de tirar
    itens = [dict(desc='Sabão em pó 1,6kg', qtd=3, opcoes=[op([2999, 3100, 3200]), op([799, 1009, 1369], distancia=12)]),
             dict(desc='Detergente', qtd=10, opcoes=[op([229, 255, 275])])]
    r = otimizar(itens, teto=6000)
    assert [l['acao'] for l in r['linhas']] == ['mantido', 'mantido'] and r['linhas'][0]['opcao'] == 1


def test_tira_quando_nao_cabe_de_jeito_nenhum():
    itens = [dict(desc='A', qtd=1, opcoes=[op([10000, 10000, 10000])]), dict(desc='B', qtd=1, opcoes=[op([500, 600, 700])])]
    r = otimizar(itens, teto=5000)
    acoes = {l['desc']: l['acao'] for l in r['linhas']}
    assert acoes == {'A': 'RETIRADO', 'B': 'mantido'}


def test_acrescenta_quando_sobra_demais():
    itens = [dict(desc='Papel', qtd=2, opcoes=[op([2890, 3350, 3560])])]
    extra = [dict(desc='Borracha', opcoes=[op([150, 180, 200])])]
    r = otimizar(itens, teto=8000, extras=extra, folga=0.05)
    assert any(l['acao'] == 'ACRESCENTADO' for l in r['linhas']) and r['total'] <= 8000


def test_item_sem_opcao_aparece_como_retirado_com_motivo():
    r = otimizar([dict(desc='Banana chips', qtd=1, opcoes=[])], teto=1000)
    assert r['linhas'][0]['acao'] == 'RETIRADO' and 'sem o mesmo produto' in r['linhas'][0]['motivo']


def test_sem_teto_o_valor_e_a_media():
    r = otimizar([dict(desc='Água sanitária', qtd=5, opcoes=[op([1189, 1290, 1697])])], teto=None)
    assert r['linhas'][0]['valor'] == r['linhas'][0]['media'] == 1392
