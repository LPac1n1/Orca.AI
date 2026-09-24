"""Plataformas de vagas (Fase 2, etapa 11; D-69): a busca é com janela, já preenchida."""

from orca.busca import ler_plataformas, plataforma_do_endereco


def test_enderecos_das_buscas():
    p = {x.id: x for x in ler_plataformas()}
    assert set(p) == {"catho", "indeed", "infojobs", "vagas_com", "linkedin"}
    assert p["catho"].endereco("Educador Social", "São Paulo", "SP") == "https://www.catho.com.br/vagas/educador-social/sao-paulo-sp/"
    assert p["infojobs"].endereco("Educador Social", "São Paulo", "SP") == \
        "https://www.infojobs.com.br/vagas-de-educador-social-em-sao-paulo,-sp.aspx"
    assert p["vagas_com"].endereco("Educador Social", "São Paulo") == "https://www.vagas.com.br/vagas-de-educador-social-em-sao-paulo"
    assert p["indeed"].endereco("Assistente Social") == "https://br.indeed.com/jobs?q=Assistente+Social"
    assert p["catho"].endereco("Psicólogo", "São Paulo") == "https://www.catho.com.br/vagas/psicologo/"  # sem UF: sem cidade


def test_quem_abre_a_pagina_da_vaga():
    plataformas = ler_plataformas()
    assert plataforma_do_endereco("https://br.indeed.com/viewjob?jk=1", plataformas).abrir_vaga == "janela"
    assert plataforma_do_endereco("https://www.catho.com.br/vagas/educador-social/31584684/", plataformas).abrir_vaga == "sistema"
    assert plataforma_do_endereco("https://www.empresa.com.br/vaga", plataformas) is None
