"""Filtros da pesquisa de vagas (sem rede): regras R08, R09, R11, R16 e decisões do usuário."""
from orcamento.vagas import avaliar, titulo_confere, sugerir, _extrai


def vaga(titulo, empresa, fmin=250000, fmax=300000, unidade='MONTH', data='2026-09-20'):
    return dict(titulo=titulo, empresa=empresa, faixa_min=fmin, faixa_max=fmax, unidade=unidade, data=data)


def test_titulo_precisa_corresponder_ao_cargo():
    assert titulo_confere('Coordenador(a) de Projetos', 'Coordenador de projetos')
    assert titulo_confere('Coordenadora de Projetos Sociais', 'Coordenador de projetos')
    assert not titulo_confere('Coordenador Financeiro', 'Coordenador de projetos')
    assert not titulo_confere('Assistente Social', 'Orientador socioeducativo')


def test_exclusoes():
    c = 'Assistente Social'
    assert avaliar(vaga('Assistente Social', 'Empresa Confidencial'), c)
    assert avaliar(vaga('Assistente Social', ''), c)
    assert avaliar(vaga('Assistente Social', 'X', fmin=None), c)
    assert avaliar(vaga('Assistente Social', 'X', fmin=10000), c)          # R$ 100/mês: erro de cadastro
    assert avaliar(vaga('Assistente Social', 'X', unidade='HOUR'), c)
    assert avaliar(vaga('Assistente Social', 'Lar Esperança'), c) is None


def test_sugestao_empresas_distintas_e_nao_pelo_maior_salario():
    vs = [dict(vaga('Assistente Social', 'A Ltda', fmin=200000), apta=True),
          dict(vaga('Assistente Social', 'A LTDA', fmin=900000), apta=True),   # mesma empresa (R09)
          dict(vaga('Assistente Social', 'B', fmin=210000), apta=True),
          dict(vaga('Assistente Social', 'C', fmin=220000), apta=True),
          dict(vaga('Assistente Social', 'D', fmin=990000), apta=True)]
    assert sugerir(vs) == [0, 2, 3]


def test_faixa_do_jsonld_vira_menor_valor():
    jp = {'title': 'Assistente Social', 'hiringOrganization': {'name': 'Lar'}, 'datePosted': '2026-09-17T00:00:00',
          'baseSalary': {'value': {'minValue': 3001, 'maxValue': 4000, 'unitText': 'MONTH'}}}
    v = _extrai(jp)
    assert v['faixa_min'] == 300100 and v['faixa_max'] == 400000 and v['data'] == '2026-09-17'


# ---------------------------------------------------------------- salário EXIBIDO na página (caso real da Catho, apontado pela OSC em 01/10/2026):
# os dados estruturados trazem a faixa cadastrada (2.001 a 3.000; 3.001 a 4.000) e a página mostra o salário real (R$ 2.300; a partir de R$ 3.000)
def test_salario_escrito_na_pagina():
    from orcamento.vagas import ler_salario, salario_exibido, salario_no_texto
    assert ler_salario('R$ 2.300') == (230000, 230000)
    assert ler_salario('A partir de R$ 3.000,00') == (300000, 300000)
    assert ler_salario('De R$ 2.001,00 a R$ 3.000,00') == (200100, 300000)
    assert ler_salario('A combinar') == 'a combinar'
    assert ler_salario('Até R$ 3.000') == 'sem mínimo'                    # não define o salário
    assert ler_salario('Benefícios') is None
    assert salario_exibido('<li><span class="icon i_salary"></span> R$ 2.300</li>') == (230000, 230000)
    assert salario_exibido('<span class="icon i_salary"></span><strong>A partir de R$ 3.000,00</strong>') == (300000, 300000)
    assert salario_exibido('<span class="icon i_salary"></span> A combinar') == 'a combinar'
    assert salario_exibido('<p>página sem o bloco do salário</p>') is None
    assert salario_no_texto('Salário R$ 2.300 Regime CLT', 230000) and salario_no_texto('R$2300,00', 230000) and salario_no_texto('2.300,00', 230000)
    assert not salario_no_texto('R$ 12.300', 230000) and not salario_no_texto('R$ 2.300,50', 230000) and not salario_no_texto('De R$ 2.001 a R$ 3.000', 230000)


def _pdf_vaga(salario):
    import pymupdf
    d = pymupdf.open(); pg = d.new_page()
    pg.insert_textbox(pymupdf.Rect(40, 40, 560, 800), 'Psicólogo\nInstituto Exemplo de Assistência Social\nSão Paulo - SP\n' + salario + '\nRegime de contratação CLT\n'
                      + 'Descrição da vaga: atendimento psicológico individual e em grupo, elaboração de relatórios, visitas domiciliares e '
                        'participação nas reuniões da equipe técnica do serviço, de segunda a sexta-feira.', fontsize=9)
    return d.tobytes()


def test_salario_conferido_com_o_pdf_da_vaga():
    from orcamento.vagas import conferir_salario_pdf
    assert conferir_salario_pdf(_pdf_vaga('Salário R$ 2.300'), 200100) == (230000, 230000)          # a página mostra outro salário: vale o da página
    assert conferir_salario_pdf(_pdf_vaga('Salário A partir de R$ 3.000,00'), 300100) == (300000, 300000)
    assert conferir_salario_pdf(_pdf_vaga('Salário R$ 2.300'), 230000) is True
    assert conferir_salario_pdf(_pdf_vaga('Faixa salarial: R$ 2.500,00 por mês'), 250000) is True  # outra plataforma: o valor aparece na página
    assert conferir_salario_pdf(_pdf_vaga('Remuneração compatível com o mercado'), 250000) is False
    assert conferir_salario_pdf(b'%PDF-1.4 sem texto', 250000) is None                              # não dá para conferir


def test_banco_de_vagas_corrigido_pela_pagina(tmp_path, monkeypatch):
    import orcamento.db as dbm
    from orcamento import vagas as V
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    for emp, cnpj, sal, pag in [('Alfa', '11111111000111', 200100, 'Salário R$ 2.300'), ('Beta', '22222222000122', 300100, 'Salário A partir de R$ 3.000,00'),
                                ('Gama', '33333333000133', 280000, 'Salário R$ 2.800,00')]:
        v = dict(titulo='Psicólogo', empresa=emp, url=f'https://x/{emp}', plataforma='Catho', faixa_min=sal, faixa_max=sal + 99900, unidade='MONTH')
        V.guardar_no_banco('Psicólogo', v, dict(status='🟢', cnpj=cnpj, razao_social=emp.upper(), motivo='teste'), _pdf_vaga(pag))
    assert V.corrigir_banco_pela_pagina() == 2
    banco = {x['empresa']: (x['faixa_min'], x['faixa_max']) for x in V.vagas_do_banco('Psicólogo')}
    assert banco == {'Alfa': (230000, 230000), 'Beta': (300000, 300000), 'Gama': (280000, 379900)}
    assert [x['empresa'] for x in V.tres_do_banco('Psicólogo')] == ['Alfa', 'Gama', 'Beta']        # menor salário primeiro, já com o valor da página


def test_a_combinar_de_outra_vaga_da_mesma_pagina_nao_conta():
    """Caso real (InfoJobs, Grupo Servtec): a vaga mostra R$ 11.860,00 e, no fim da página, uma vaga parecida diz 'Salário: A combinar'."""
    from orcamento.vagas import a_combinar_na_vaga
    pagina = ('Coordenador de Projetos Servtec São Paulo - SP R$ 11.860,00 (Bruto mensal) Híbrido CANDIDATAR-ME ... Vagas parecidas: '
              'Coordenador de Projetos CAPEX Horário: Comercial Salário: A combinar Sobre a ... Candidatar-me')
    assert not a_combinar_na_vaga(pagina, 1186000)
    assert a_combinar_na_vaga(pagina, 250000)                                          # o salário registrado não aparece antes: não dá para afastar
    assert a_combinar_na_vaga('Vaga de Psicólogo Cargo: psicólogo Salário: a combinar Empresa: Santa Casa', 300000)
    assert a_combinar_na_vaga('Salário: a combinar. Vagas parecidas: Psicólogo R$ 3.000,00', 300000)   # o valor só aparece depois (outra vaga)
    assert not a_combinar_na_vaga('Salário R$ 2.300 Benefícios: horário a combinar com a coordenação', 230000)


def test_salario_da_pesquisa_gravada_corrigido_pela_pagina(tmp_path, monkeypatch):
    """A vaga fica; o salário passa a ser o que o PDF dela mostra (cargo com menos de 3 vagas no banco ficava com o valor antigo)."""
    import orcamento.db as dbm
    from orcamento import servico
    from orcamento.modelo import Projeto, RubricaRH, PesquisaSalarial, Evidencia
    monkeypatch.setattr(dbm, 'PASTA_DADOS', str(tmp_path))
    ps = []
    for nome, sal, pag in [('PERSEVERANÇA', 200100, 'Salário R$ 2.407'), ('Base Facilities', 380000, 'R$ 3.800,00 (Bruto mensal)'), ('Caminho de Luz', 217300, 'R$ 2.173,00 a R$ 3.100,00')]:
        sha, rel = dbm.guardar_arquivo(1, f'vaga_{nome}.pdf', _pdf_vaga(pag))
        ps.append(PesquisaSalarial(nome=nome, cnpj='1', faixa_min=sal, faixa_max=sal + 99900, valor=sal, evidencia=Evidencia(arquivo=rel, sha256=sha, url='https://x')))
    r = RubricaRH(item=8, cargo='Orientador socioeducativo', horas_mes=60, meses=10, pesquisas=ps, valor_mensal_plano=100000)
    p = Projeto(nome='T', teto=10_000_000, rubricas=[r])
    assert not servico.rh_pronto(r)
    assert servico.corrigir_salarios_pela_pagina(p) == [(8, 'PERSEVERANÇA', 200100, 240700)]
    assert (ps[0].faixa_min, ps[0].faixa_max, ps[0].valor) == (240700, 240700, 240700) and ps[1].faixa_min == 380000
    assert servico.rh_pronto(r) and servico.corrigir_salarios_pela_pagina(p) == []
