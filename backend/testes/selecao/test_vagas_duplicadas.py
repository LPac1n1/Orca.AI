"""Vagas repetidas em plataformas diferentes (T-09, D-49): casos claros agrupados, incertos para o usuário."""

from datetime import date

from orca.selecao import AnuncioVaga, Vaga, agrupar_duplicadas, selecionar_vagas, semelhanca_titulos

A = "43283811000150"
A_FILIAL = "43283811000230"  # filial: mesma raiz de CNPJ
B = "54651716001150"


def _anuncio(id, cnpj, titulo, sal_min, sal_max=None, cidade="São Paulo", dia=10, identificador=None):
    return AnuncioVaga(
        Vaga(id, "Empresa", cnpj, sal_min, sal_max, plataforma=id.split("-")[0]),
        titulo,
        cidade,
        date(2026, 9, dia) if dia else None,
        identificador,
    )


def test_semelhanca_de_titulos():
    assert semelhanca_titulos("Educador(a) Social", "EDUCADOR SOCIAL") == 1.0
    assert semelhanca_titulos("Social Educador", "educador social") == 1.0  # ordem não importa
    assert semelhanca_titulos("Auxiliar de Limpeza", "Vaga: Auxiliar Limpeza") == 1.0
    assert semelhanca_titulos("Cozinheira", "Auxiliar de cozinha") < 0.6
    assert semelhanca_titulos("", "Educador") == 0.0


def test_mesma_vaga_em_duas_plataformas_conta_uma_vez():
    anuncios = [
        _anuncio("catho-1", A, "Educador Social", 250000, 300000, dia=10),
        _anuncio("indeed-1", A, "Educador(a) Social", 250000, 300000, dia=12),
        _anuncio("infojobs-1", B, "Educador Social", 260000, dia=11),
    ]
    d = agrupar_duplicadas(anuncios)
    grupos = {v.id: v.grupo for v in d.vagas}
    assert grupos == {"catho-1": "catho-1", "indeed-1": "catho-1", "infojobs-1": None}
    assert d.incertos == ()
    s = selecionar_vagas(d.vagas)
    motivos = {v.id: m for v, m in s.descartadas}
    assert "mesma vaga" in motivos["indeed-1"]


def test_empresas_diferentes_nunca_sao_a_mesma_vaga():
    d = agrupar_duplicadas([_anuncio("a", A, "Educador Social", 250000), _anuncio("b", B, "Educador Social", 250000)])
    assert all(v.grupo is None for v in d.vagas) and d.incertos == ()


def test_mesma_raiz_de_cnpj_cidades_ou_salarios_diferentes():
    base = _anuncio("a", A, "Educador Social", 250000)
    assert agrupar_duplicadas([base, _anuncio("b", A_FILIAL, "Educador Social", 250000)]).vagas[1].grupo == "a"
    outra_cidade = agrupar_duplicadas([base, _anuncio("b", A, "Educador Social", 250000, cidade="Campinas")])
    assert all(v.grupo is None for v in outra_cidade.vagas) and outra_cidade.incertos == ()
    outro_salario = agrupar_duplicadas([base, _anuncio("b", A, "Educador Social", 310000)])
    assert all(v.grupo is None for v in outro_salario.vagas) and outro_salario.incertos == ()


def test_casos_incertos_ficam_para_o_usuario():
    d = agrupar_duplicadas([
        _anuncio("a", A, "Educador Social", 250000, 300000, dia=1),
        _anuncio("b", A, "Educador Social Pleno", 280000, dia=2),  # título parecido, faixas que se cruzam
        _anuncio("c", A, "Educador Social", 250000, cidade=None, dia=3),  # sem cidade
    ])
    assert all(v.grupo is None for v in d.vagas)
    pares = {(p.a, p.b): p.motivo for p in d.incertos}
    assert set(pares) == {("a", "b"), ("a", "c")}  # b–c: faixas que não se cruzam = vagas diferentes
    assert "títulos parecidos" in pares[("a", "b")] and "faixas salariais" in pares[("a", "b")]
    assert "cidade não informada" in pares[("a", "c")]


def test_datas_distantes_e_identificador_da_vaga():
    longe = agrupar_duplicadas([_anuncio("a", A, "Educador Social", 250000, dia=1),
                                AnuncioVaga(Vaga("b", "E", A, 250000), "Educador Social", "São Paulo", date(2026, 12, 1))])
    assert all(v.grupo is None for v in longe.vagas) and longe.incertos == ()
    mesmo_codigo = agrupar_duplicadas([
        _anuncio("a", A, "Educador Social I", 250000, cidade=None, dia=None, identificador="V-99"),
        _anuncio("b", A, "Educador(a) Social", 250000, cidade=None, dia=None, identificador="v-99 "),
    ])
    assert mesmo_codigo.vagas[1].grupo == "a"
    codigos_diferentes = agrupar_duplicadas([
        _anuncio("a", A, "Educador Social", 250000, identificador="V-1"),
        _anuncio("b", A, "Educador Social", 250000, identificador="V-2"),
    ])
    assert all(v.grupo is None for v in codigos_diferentes.vagas)


def test_grupo_transitivo_resolve_incerto():
    d = agrupar_duplicadas([
        _anuncio("a", A, "Educador Social", 250000, dia=1),
        _anuncio("b", A, "Educador Social", 250000, dia=10),
        _anuncio("c", A, "Educador Social", 250000, dia=19),  # a–c: 18 dias (incerto), mas b liga os dois
    ])
    assert {v.grupo for v in d.vagas} == {"a"}
    assert d.incertos == ()
