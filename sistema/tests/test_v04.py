"""Regras pedidas pela OSC em 27/09/2026 (2ª rodada): lojas com CAPTCHA descartadas, menor preço, empresas diferentes, troca pela
categoria da rubrica, vaga "a combinar", comprovante oficial da Receita, tipos de rubrica e o que já está pronto não é refeito."""
import pytest

from orcamento.modelo import RubricaMaterial, RubricaRH, Subitem, Fonte, Evidencia, PesquisaSalarial
from orcamento.produtos import cesta, lojas as L, categorias as C


# ---------------------------------------------------------------- lojas
def test_carrefour_descartado_e_lojas_novas():
    lojas = L.lojas_para('alimentacao', bloqueadas={})
    assert 'carrefour' not in lojas and {'paodeacucar', 'extra', 'coop'} <= set(lojas)
    assert 'tenda' not in L.lojas_para('alimentacao', bloqueadas={'tenda': {}})          # pediu CAPTCHA nos últimos 30 dias: fora
    assert L.raiz('paodeacucar') == L.raiz('extra') == '47508411' and L.raiz('coop') == '57508426'


def test_loja_com_captcha_fica_descartada_por_30_dias(monkeypatch, tmp_path):
    from orcamento import db
    monkeypatch.setattr(db, 'PASTA_LOCAL', str(tmp_path))
    db.loja_bloquear('kalunga', 'a loja pediu verificação humana (CAPTCHA/anti-robô)')
    b = db.lojas_bloqueadas()
    assert list(b) == ['kalunga'] and b['kalunga']['ate'] > b['kalunga']['desde']
    assert 'kalunga' not in L.lojas_para('papelaria')
    db.loja_liberar('kalunga')
    assert db.lojas_bloqueadas() == {} and 'kalunga' in L.lojas_para('papelaria')


# ---------------------------------------------------------------- menor preço e empresas diferentes
def _g(precos, ean=None):
    return dict(por_loja={l: dict(nome='Detergente Líquido Limpol Neutro 500ml', preco=p, ean=ean, url=f'https://{l}/p', loja=l) for l, p in precos.items()})


def test_as_3_lojas_mais_baratas_de_empresas_diferentes():
    g = _g(dict(paodeacucar=289, extra=299, atacadao=310, tenda=320, gimba=450))
    tres, reservas = cesta.Motor._ordem_lojas(g)
    assert tres == ['paodeacucar', 'atacadao', 'tenda']          # Extra é da mesma empresa do Pão de Açúcar (R09): não entra junto
    assert reservas == ['extra', 'gimba']
    assert len(cesta.Motor._ordem_lojas(_g(dict(paodeacucar=289, extra=299, atacadao=310)))[0]) == 2   # só 2 empresas: não fecha 3


def test_entre_produtos_iguais_ao_pedido_vence_o_mais_barato():
    it = dict(desc='Detergente 500mL', qtd=10, familia='detergente')
    caro = _g(dict(atacadao=400, tenda=410, gimba=420), ean='7891022638004')      # com EAN nas 3
    barato = dict(por_loja={l: dict(nome='Detergente Líquido Ypê Clear 500ml', preco=p, ean=None, url=f'https://{l}/y', loja=l)
                            for l, p in dict(atacadao=219, tenda=239, gimba=319).items()})
    ops = [cesta.Motor._opcao(it, g, 0, tuple(cesta.Motor._ordem_lojas(g)[0])) for g in (caro, barato)]
    ops.sort(key=cesta.Motor._chave)
    assert ops[0]['ofertas'][0]['nome'].startswith('Detergente Líquido Ypê Clear')     # o EAN confirma a identidade; o preço decide
    assert ops[0]['confirmacao'] == 'descrição' and ops[1]['confirmacao'] == 'EAN nas 3 lojas'


def test_teto_segue_a_ordem_do_motor_menor_preco():
    from orcamento.produtos import teto
    item = dict(desc='Detergente 500mL', qtd=10, opcoes=[dict(precos=[219, 239, 319], distancia=0), dict(precos=[400, 410, 420], distancia=0)])
    r = teto.otimizar([item])
    assert r['linhas'][0]['opcao'] == 0 and r['linhas'][0]['valor'] == 259          # 1ª opção (a mais barata), valor = média


# ---------------------------------------------------------------- troca pela categoria da rubrica
def test_candidatos_da_categoria_nao_repetem_itens_da_cesta():
    cesta_ = ['Suco de uva 1L', 'Leite 1L', 'Café 500g', 'Banana chips 100g']
    cands = C.candidatos('alimentacao', cesta_, extras=['Bolacha recheada 130g'])
    assert cands[0] == 'Bolacha recheada 130g'                                       # os extras da rubrica vêm primeiro
    assert 'Biscoito cream cracker 400g' in cands
    assert not any(c.lower().startswith('café') for c in cands)
    assert C.candidatos('limpeza', ['Sacos de Lixo 50L 50 Unidades']) and C.candidatos('papelaria', [])


def test_opcao_do_degrau_categoria():
    it = dict(desc='Banana chips 100g', qtd=1, familia='chips', valor_ref=900)
    g = dict(por_loja={l: dict(nome='Amendoim Torrado Dori 150g', preco=p, ean=None, url=f'https://{l}/a', loja=l) for l, p in dict(atacadao=850, tenda=880, coop=990).items()})
    o = cesta.Motor._opcao(it, g, 3, ('atacadao', 'tenda', 'coop'), substituto='Amendoim torrado 150g')
    assert o['nivel'] == 3 and o['perdidos'] == ['Banana chips 100g'] and o['substituto'] == 'Amendoim torrado 150g'
    longe = dict(o, ofertas=[dict(x, preco=3000) for x in o['ofertas']])
    assert cesta.Motor._chave(o, 900) < cesta.Motor._chave(longe, 900)              # fica o de preço mais próximo do que o item valia no plano


# ---------------------------------------------------------------- vagas
def test_vaga_a_combinar_e_faixa_generica_nao_entram():
    from orcamento.vagas import a_combinar, avaliar
    assert a_combinar('Cargo: psicólogo Salário: a combinar Empresa: Santa Casa')
    assert not a_combinar('Horário a combinar com a coordenação. Salário: R$ 2.000,00')
    v = dict(titulo='Psicólogo', empresa='Santa Casa de Misericordia do Recife', faixa_min=100000, faixa_max=1500000, unidade='MONTH')
    assert 'faixa salarial genérica' in avaliar(v, 'Psicólogo')                      # caso real do BNE (R$ 1.000 a R$ 15.000)
    assert 'a combinar' in avaliar(dict(v, faixa_max=100000, a_combinar=True), 'Psicólogo')
    assert avaliar(dict(v, faixa_min=300100, faixa_max=400000), 'Psicólogo') is None


@pytest.fixture
def dados(tmp_path, monkeypatch):
    import orcamento.db as dbm
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    return tmp_path


def test_banco_escolhe_as_vagas_de_menor_salario(dados):
    from orcamento import vagas as V
    for emp, cnpj, sal in [('Alfa', '11111111000111', 350000), ('Beta', '22222222000122', 210000), ('Gama', '33333333000133', 280000),
                           ('Delta', '44444444000144', 190000), ('Beta Filial', '22222222000203', 150000)]:
        v = dict(titulo='Psicólogo', empresa=emp, url=f'https://x/{emp}', plataforma='InfoJobs', faixa_min=sal, faixa_max=sal, unidade='MONTH')
        V.guardar_no_banco('Psicólogo', v, dict(status='🟢', cnpj=cnpj, razao_social=emp.upper(), motivo='teste'), b'%PDF-1.4 vaga de teste')
    tres = V.tres_do_banco('Psicólogo')
    assert [x['empresa'] for x in tres] == ['Beta Filial', 'Delta', 'Gama']          # menores salários, uma vaga por empresa (raiz do CNPJ)


# ---------------------------------------------------------------- comprovante oficial da Receita
def _pdf(texto):
    import pymupdf
    d = pymupdf.open(); pg = d.new_page()
    pg.insert_textbox(pymupdf.Rect(40, 40, 560, 800), texto, fontsize=9)
    return d.tobytes()


COMPROVANTE = """REPÚBLICA FEDERATIVA DO BRASIL
CADASTRO NACIONAL DA PESSOA JURÍDICA
NÚMERO DE INSCRIÇÃO
75.315.333/0001-09
MATRIZ
COMPROVANTE DE INSCRIÇÃO E DE SITUAÇÃO CADASTRAL
DATA DE ABERTURA
13/11/1981
NOME EMPRESARIAL
ATACADAO S.A.
TÍTULO DO ESTABELECIMENTO (NOME DE FANTASIA)
ATACADAO
SITUAÇÃO CADASTRAL
{sit}
DATA DA SITUAÇÃO CADASTRAL
03/11/2005
Aprovado pela Instrução Normativa RFB nº 2.119, de 06 de dezembro de 2022.
Emitido no dia {dia} às 10:15:42 (data e hora de Brasília)."""


def test_comprovante_oficial_da_receita():
    import datetime as dt
    from orcamento import comprovante_receita as CR
    hoje = dt.date.today()
    info = CR.ler(_pdf(COMPROVANTE.format(sit='ATIVA', dia=hoje.strftime('%d/%m/%Y'))))
    assert info == dict(cnpj='75.315.333/0001-09', situacao='ATIVA', emitido_em=hoje.isoformat() + 'T10:15:42', razao='ATACADAO S.A.')
    assert CR.conferir(info, {'75.315.333/0001-09'}) is None
    assert 'não é de nenhuma empresa' in CR.conferir(info, {'01.157.555/0011-86'})
    assert 'BAIXADA' in CR.conferir(CR.ler(_pdf(COMPROVANTE.format(sit='BAIXADA', dia=hoje.strftime('%d/%m/%Y')))), {'75.315.333/0001-09'})
    velho = (hoje - dt.timedelta(days=200)).strftime('%d/%m/%Y')
    assert 'mais antigo' in CR.conferir(CR.ler(_pdf(COMPROVANTE.format(sit='ATIVA', dia=velho))), {'75.315.333/0001-09'})
    assert CR.ler(_pdf('Carrinho de compras Atacadão CNPJ 75.315.333/0001-09')) is None          # outro PDF qualquer não é o comprovante
    assert CR.url_emissao('75.315.333/0001-09').endswith('cnpj=75315333000109')


def test_importar_comprovantes(dados):
    import datetime as dt
    from orcamento import servico
    from orcamento.modelo import Projeto
    p = Projeto(nome='t', teto=1000)
    pdf = _pdf(COMPROVANTE.format(sit='ATIVA', dia=dt.date.today().strftime('%d/%m/%Y')))
    ok, prob = servico.importar_comprovantes(p, 1, [('atacadao.pdf', pdf), ('boleto.pdf', _pdf('boleto bancário'))], {'75.315.333/0001-09'}, avisar_outros=False)
    assert ok == ['75.315.333/0001-09'] and prob == []
    c = p.comprovantes_cnpj['75.315.333/0001-09']
    assert c['situacao'] == 'ATIVA' and c['arquivo'].endswith('.pdf') and len(c['sha256']) == 64


# ---------------------------------------------------------------- tipos de rubrica e o que já está pronto
def test_tipo_da_rubrica():
    from orcamento.servico import tipo_da_rubrica
    mat = lambda d, **k: RubricaMaterial(item=1, descricao=d, meses=1, **k)
    assert tipo_da_rubrica(RubricaRH(item=1, cargo='Psicólogo', horas_mes=40, meses=10)) == 'rh'
    assert tipo_da_rubrica(mat('Alimentação')) == tipo_da_rubrica(mat('Material Pedagógico e Escritório')) == tipo_da_rubrica(mat('Limpeza + utensílios')) == 'mercado'
    assert tipo_da_rubrica(mat('Sistema de gestão de dados')) == 'sistema'
    assert tipo_da_rubrica(mat('Locação de equipamento de som')) == 'servico'
    assert tipo_da_rubrica(mat('Material esportivo')) == 'material'
    assert tipo_da_rubrica(mat('Material esportivo', regra='mercado')) == 'mercado'                # a OSC pode escolher o tipo


def test_o_que_ja_esta_pronto_nao_e_refeito(dados):
    from orcamento.servico import subitem_pronto, rh_pronto
    ev = Evidencia(arquivo='projetos/1/evidencias/x.pdf', sha256='a' * 64, url='https://x')
    fs = [Fonte(nome=n, cnpj=c, evidencia=ev) for n, c in [('A', '75.315.333/0001-09'), ('B', '01.157.555/0011-86'), ('C', '57.508.426/0001-78')]]
    assert subitem_pronto(Subitem(descricao='Leite 1L', qtd=2, precos=[500, 520, 540], fontes=fs))
    assert not subitem_pronto(Subitem(descricao='Leite 1L', qtd=2, precos=[500, 520, 540], fontes=fs[:2] + [Fonte(nome='C', cnpj='x')]))   # falta 1 PDF
    assert not subitem_pronto(Subitem(descricao='Leite 1L', qtd=2))
    ps = [PesquisaSalarial(nome=n, cnpj=c, faixa_min=300000, faixa_max=400000, evidencia=ev) for n, c in [('A', '1'), ('B', '2'), ('C', '3')]]
    r = RubricaRH(item=5, cargo='Psicólogo', horas_mes=40, meses=10, pesquisas=ps)
    assert rh_pronto(r)
    r.pesquisas[2].faixa_min, r.pesquisas[2].faixa_max = 100000, 1500000                              # faixa genérica ("a combinar"): refaz
    assert not rh_pronto(r)


# ---------------------------------------------------------------- produto igual de outra marca (mesma especificação)
def _of(loja, nome, preco, ean=None, nivel=None):
    d = dict(loja=loja, nome=nome, preco=preco, ean=ean, url=f'https://{loja}/{abs(hash(nome)) % 10 ** 6}', disp=True)
    return dict(d, nivel=nivel) if nivel is not None else d


def test_mesma_especificacao_com_marcas_diferentes():
    from orcamento.produtos import identidade as ID
    ofs = [_of('papelex', 'Pasta Sanfonada A4 Line Azul 12 Divisórias - Dello', 1689), _of('bazarhorizonte', 'Pasta Plástica Sanfonada A4 12 Divisórias - Azul', 2490),
           _of('lepok', 'Pasta sanfonada A4 com 12 divisórias - Azul - 6070.C - Dello', 2541), _of('gimba', 'Pasta Sanfonada Plascony Ofício 12 Divisórias Cristal', 2300),
           _of('lepok', 'Pasta sanfonada A4 com 12 divisórias Linho serena - Verde pastel', 2517)]
    desc = 'Pasta sanfonada 12 Divisórias'
    azul = ID.agrupar_espec(ofs, desc, cor_sempre=True)[0]
    assert sorted(azul['por_loja']) == ['bazarhorizonte', 'lepok', 'papelex'] and azul['por_loja']['lepok']['preco'] == 2541   # as 3 azuis, A4
    sem_cor = ID.agrupar_espec(ofs, desc)[0]
    assert sorted(sem_cor['por_loja']) == ['bazarhorizonte', 'lepok', 'papelex'] and sem_cor['por_loja']['lepok']['preco'] == 2517   # a mais barata de cada loja
    assert 'gimba' not in sem_cor['por_loja']                                    # Ofício × A4: outra especificação
    assert ID.chave_espec('Grampo Galvanizado Cis 26/6 5000 un', 'Grampo 5000 Unidades') != ID.chave_espec('Grampo Galvanizado Cis 24/6 5000 un', 'Grampo 5000 Unidades')


def test_grupo_com_ean_aceita_loja_que_escreve_o_nome_de_outro_jeito():
    """Caso real: Lepok e Livrarias Curitiba têm o mesmo EAN, mas a segunda escreve "26.6" no lugar de "26/6"; a Gimba (sem EAN) confere com a Lepok."""
    from orcamento.produtos import identidade as ID
    ofs = [_of('lepok', 'Grampo galvanizado 26/6 - com 5000 unidades - Bacchi', 965, '7897849621601'),
           _of('livrariascuritiba', 'Grampo 26.6 Com 5000 Unidades Galvanizado', 1444, '7897849621601'),
           _of('gimba', 'Grampo Galvanizado Bacchi 26/6 Caixa 5000 UN', 1049), _of('gimba', 'Grampo Galvanizado Bacchi 24/6 Caixa 5000 UN', 2290)]
    g = ID.agrupar(ofs, 'Grampo 5000 Unidades')[0]
    assert sorted(g['por_loja']) == ['gimba', 'lepok', 'livrariascuritiba'] and '26/6' in g['por_loja']['gimba']['nome']


def test_grampeador_nao_e_o_item_grampo():
    assert not cesta.Motor._outro_item('Grampeador de Mesa Preto Para 20 Folhas', ['Grampo 5000 Unidades'])
    assert cesta.Motor._outro_item('Grampo Galvanizado Bacchi 26/6 Caixa 5000 UN', ['Grampo 5000 Unidades'])


def test_trio_montado_pela_ia_e_validado(monkeypatch):
    from orcamento import ia
    it = dict(desc='Caneta esferográfica 50 Unidades', qtd=1, familia='caneta')
    m = cesta.Motor([it], ['gimba', 'papelex', 'lepok', 'paodeacucar', 'extra'], '03977-015')
    m.ofertas[(it['desc'], 0)] = [_of('gimba', 'Caneta Esferográfica Injex Pen 1mm Azul CX C/50 UN', 3690), _of('papelex', 'Caneta Esferográfica Top 2000 Azul C/ 50 - Compactor', 4519),
                                  _of('lepok', 'Caneta esferográfica Cristal 1.0mm Azul caixa com 50 unidades - Bic', 4650)]
    perguntas = []

    def trio(pedido, anuncios, pid=None):
        perguntas.append(anuncios)
        return [0, 1, 2], 'canetas azuis, caixas com 50'
    monkeypatch.setattr(ia, 'montar_trio', trio)
    o = m._trio_pela_ia(m.itens[0], set())
    assert [x['loja'] for x in o['ofertas']] == ['gimba', 'papelex', 'lepok'] and o['misto'] and o['trio_ia'] and o['nivel'] == 0
    assert o['confirmacao'] == 'mesma especificação, marcas diferentes' and len(perguntas[0]) == 3
    monkeypatch.setattr(ia, 'montar_trio', lambda *a, **k: ([0, 0, 1], 'x'))            # a IA repetiu a loja: o sistema não aceita
    assert m._trio_pela_ia(m.itens[0], set()) is None
    monkeypatch.setattr(ia, 'montar_trio', lambda *a, **k: ([0, 1, 9], 'x'))            # índice que não existe
    assert m._trio_pela_ia(m.itens[0], set()) is None
    monkeypatch.setattr(ia, 'montar_trio', lambda *a, **k: (None, 'não há 3 equivalentes'))
    assert m._trio_pela_ia(m.itens[0], set()) is None


def test_gpa_busca_sem_resultado_nao_e_falha():
    import asyncio

    class R:
        status_code, text = 404, '{"message":"Partner error: Products not found"}'

    class C:
        async def post(self, *a, **k):
            return R()
    assert asyncio.run(L.gpa(C(), 'paodeacucar', 'pasta sanfonada', 461)) == []
    assert L.LOJAS['paodeacucar']['loja_padrao'] == 461 and 'papelaria' not in L.LOJAS['paodeacucar']['setores']


def test_sistemas_justificativa_e_tipos():
    from orcamento import sistemas as S
    assert all(f['cnpj'] and f['razao'] for f in S.com_preco_publico())
    assert 'fdsolutions' in {f['chave'] for f in S.sob_consulta()} and 'ongsys' in {f['chave'] for f in S.com_preco_publico()}   # a Ongsys publica preço


def test_trio_da_ia_com_lojas_reserva(monkeypatch):
    """A IA indica também anúncios equivalentes de outras lojas: entram no lugar de uma loja do trio que ficar sem comprovante."""
    from orcamento import ia
    it = dict(desc='Caneta esferográfica 50 Unidades', qtd=1, familia='caneta')
    m = cesta.Motor([it], ['gimba', 'papelex', 'lepok', 'paodeacucar', 'extra'], '03977-015')
    m.ofertas[(it['desc'], 0)] = [_of('gimba', 'Caneta Esferográfica Injex Pen 1mm Azul CX C/50 UN', 3690), _of('papelex', 'Caneta Esferográfica Top 2000 Azul C/ 50 - Compactor', 4519),
                                  _of('lepok', 'Caneta esferográfica Cristal 1.0mm Azul caixa com 50 unidades - Bic', 4650),
                                  _of('paodeacucar', 'Caneta Esferográfica Azul Bic Cristal caixa 50 unidades', 4990), _of('extra', 'Caneta Esferográfica Azul Bic Cristal caixa 50 unidades', 5090)]
    monkeypatch.setattr(ia, 'montar_trio', lambda pedido, anuncios, pid=None: ([0, 1, 2], 'canetas azuis, caixas com 50', [3, 4, 0, 99]))
    o = m._trio_pela_ia(m.itens[0], set())
    assert [x['loja'] for x in o['ofertas']] == ['gimba', 'papelex', 'lepok']
    assert [x['loja'] for x in o['reservas']] == ['paodeacucar']          # Extra é a mesma empresa do Pão de Açúcar; loja do trio e índice inválido não entram
    assert o['reservas'][0]['url'] and o['reservas'][0]['preco'] == 4990


def test_limite_de_acessos_nao_e_captcha(monkeypatch, tmp_path):
    """429 (a loja limitou os acessos) não é CAPTCHA: a loja descansa até amanhã, em vez de ser descartada por 30 dias."""
    import datetime as dt
    from orcamento import db
    monkeypatch.setattr(db, 'PASTA_LOCAL', str(tmp_path))
    m = cesta.Motor([dict(desc='Clips 100 Unidades', qtd=1, familia='clips')], ['afonsoruotolo', 'kalunga', 'gimba'], '03977-015')
    m._bloquear('afonsoruotolo', 'a loja limitou o número de acessos (429)')
    m._bloquear('kalunga', 'a loja pediu verificação humana (CAPTCHA/anti-robô)')
    b = db.lojas_bloqueadas(); hoje = dt.date.today()
    assert b['afonsoruotolo']['ate'] == (hoje + dt.timedelta(days=1)).isoformat()
    assert b['kalunga']['ate'] == (hoje + dt.timedelta(days=db.DIAS_BLOQUEIO)).isoformat()
    assert set(m.bloqueadas) == {'afonsoruotolo', 'kalunga'}                       # as duas ficam fora desta pesquisa


def test_no_limite_de_acessos_a_loja_descansa_e_vai_mais_devagar_antes_de_sair(monkeypatch, tmp_path):
    """Pesquisa completa de 09/10/2026: uma papelaria respondeu "muitos acessos" (429) aos 2 minutos e ficou de fora o resto do dia — e fez falta
    (5 de 8 itens de papelaria sem 3 lojas). O 429 é um pedido para ir mais devagar: o sistema para de acessar a loja por um tempo, passa a
    espaçar os acessos e tenta de novo; só se o limite voltar depois disso é que a loja fica de fora até amanhã."""
    import asyncio
    import time
    from orcamento import db
    monkeypatch.setattr(db, 'PASTA_LOCAL', str(tmp_path))
    monkeypatch.setattr(cesta, 'PAUSA_429', 0.3)
    monkeypatch.setitem(cesta.INTERVALO, 'nuvemshop', 0.05)
    respostas, horas = [], []

    async def loja_falsa(c, loja, q):
        horas.append(time.monotonic())
        r = respostas.pop(0)
        if r == 429:
            raise cesta.L.Bloqueada('a loja limitou o número de acessos (429)')
        return r
    monkeypatch.setattr(cesta.L, 'nuvemshop', loja_falsa)

    async def rodar(m, consultas):
        m.sem, m.c, m.br = asyncio.Semaphore(3), None, None
        return [await m._buscar('afonsoruotolo', q) for q in consultas]
    achado = [dict(loja='afonsoruotolo', nome='Clips 2/0 100 un', preco=479, url='https://loja.exemplo/clips')]
    # 1) o limite aparece uma vez: a loja descansa, a consulta é refeita e a loja continua na pesquisa, mais devagar
    m = cesta.Motor([dict(desc='Clips 100 Unidades', qtd=1, familia='clips')], ['afonsoruotolo', 'gimba'], '03977-015')
    respostas[:] = [429, achado, achado]
    r = asyncio.run(rodar(m, ['clips 100 unidades', 'clips niquelado']))
    assert r == [achado, achado] and 'afonsoruotolo' not in m.bloqueadas and 'afonsoruotolo' not in db.lojas_bloqueadas()
    assert horas[1] - horas[0] >= 0.3                                                # esperou a pausa antes de tentar de novo
    assert horas[2] - horas[1] >= 0.05 * cesta.MAIS_DEVAGAR - 0.01                   # e passou a espaçar mais os acessos
    # 2) o limite volta depois da pausa: aí sim a loja fica de fora até amanhã (e não por 30 dias, como no CAPTCHA)
    m = cesta.Motor([dict(desc='Clips 100 Unidades', qtd=1, familia='clips')], ['afonsoruotolo', 'gimba'], '03977-015')
    respostas[:] = [429, 429]; horas.clear()
    assert asyncio.run(rodar(m, ['clips galvanizado'])) == [[]]
    assert 'afonsoruotolo' in m.bloqueadas and db.lojas_bloqueadas()['afonsoruotolo']['ate'] == (__import__('datetime').date.today() + __import__('datetime').timedelta(days=1)).isoformat()


def test_loja_que_barrou_nao_e_mais_acessada():
    """Teste real de 02/10/2026: a Kalunga pediu CAPTCHA no meio da pesquisa e, mesmo assim, anúncios dela entraram na proposta e o sistema
    voltou à loja para os comprovantes. Agora os anúncios dela saem das opções e os comprovantes não voltam à loja."""
    import asyncio
    from orcamento import servico
    it = dict(desc='Clips 100 Unidades', qtd=1, familia='clips')
    m = cesta.Motor([it], ['kalunga', 'gimba', 'lepok'], '03977-015')
    m.ofertas[(it['desc'], 0)] = [_of('kalunga', 'Clips 2/0 100 un', 300), _of('gimba', 'Clips 2/0 100 un', 320), _of('lepok', 'Clips 2/0 100 un', 350)]
    m.brutos[it['desc']] = [dict(_of('kalunga', 'Clips 2/0 100 un', 300)), dict(_of('gimba', 'Clips 2/0 100 un', 320))]
    m.bloqueadas['kalunga'] = 'a loja pediu verificação humana (CAPTCHA/anti-robô)'
    m._sem_bloqueadas()
    assert [x['loja'] for x in m.ofertas[(it['desc'], 0)]] == ['gimba', 'lepok'] and [x['loja'] for x in m.brutos[it['desc']]] == ['gimba']
    x = _of('kalunga', 'Clips 2/0 100 un', 300)
    res = asyncio.run(servico._comprovar(None, 1, 12, 'kalunga', [(dict(desc='Clips 100 Unidades', qtd=1), x)], '03977-015', None,
                                         bloqueadas={'kalunga': 'loja fora de uso: CAPTCHA'}))   # sem navegador: a loja nem é aberta
    assert res[('kalunga', x['url'])] == dict(ev=None, preco=None, problema='loja fora de uso: CAPTCHA')


def test_comprovante_tem_de_provar_o_preco(dados):
    """Teste de ponta a ponta de 02/10/2026: PDFs do Tenda com o preço borrado (CEP não aceito) e do Pão de Açúcar com preço diferente do
    registrado contavam como prontos. Agora o preço registrado tem de aparecer no PDF; comprovante com problema fica marcado e pendente."""
    from orcamento import db, servico
    from orcamento.produtos.evidencia import preco_principal_gpa
    pagina = ('Leite Longa Vida Integral ITALAC 1 Litro\nCód.: 4426370\nR$ 6,79\nPreço por 1L - R$ 6,79\nFaça sua primeira compra online com cupom\n'
              'Para compras acima de R$299,00\nVeja também\nLeite UHT Integral Paulista Caixa com Tampa 1l\nR$ 7,79\n' + 'Descrição do produto. ' * 12)
    assert preco_principal_gpa(pagina) == 679 and preco_principal_gpa('página sem código') is None
    sha, rel = db.guardar_arquivo(1, 'produto_paodeacucar_item14_Leite_1L.pdf', _pdf(pagina))
    ev = Evidencia(arquivo=rel, sha256=sha, url='https://www.paodeacucar.com/produto/176191/leite', origem='navegador')
    f = Fonte(nome='CBD', cnpj='47.508.411/0001-56', plataforma='Pão de Açúcar', evidencia=ev)
    assert servico.preco_no_pdf(rel, 679) is True and servico.preco_no_pdf(rel, 699) is False
    assert servico.pesquisa_comprovada(f, 679) and not servico.pesquisa_comprovada(f, 699)          # o PDF mostra 6,79; a grade dizia 6,99
    assert servico._sem_preco(_pdf(pagina), 699) == 'o preço não aparece no PDF da página' and servico._sem_preco(_pdf(pagina), 679) is None
    assert servico._sem_preco(b'%PDF-1.4 sem texto', 699) is None                                    # PDF sem texto: não dá para conferir
    s = Subitem(descricao='Leite 1L', qtd=20, precos=[679, 679, 679], fontes=[f, f.model_copy(deep=True), f.model_copy(deep=True)])
    assert servico.subitem_pronto(s)
    s.precos[2] = 699
    assert not servico.subitem_pronto(s)                                                             # "Pesquisar tudo" refaz
    s.precos[2] = 679; s.fontes[1].evidencia.problema = 'a página diz que o produto está indisponível'
    assert not servico.subitem_pronto(s) and not servico.comprovante_no_formato(s.fontes[1].evidencia)
    s.fontes[1].evidencia.problema = None; s.precos[0] = 27092; s.fontes[0].evidencia.origem = 'pdf'  # PDF anexado pela OSC: não é conferido aqui
    assert servico.subitem_pronto(s)
