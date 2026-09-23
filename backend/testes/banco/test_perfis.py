"""Perfis de regras gravados: versões imutáveis e cadeia do projeto e do orçamento."""

import pytest
from sqlalchemy import func, select

from orca.banco import (
    Orcamento,
    PerfilRegras,
    Projeto,
    definir_camada_do_orcamento,
    definir_camadas_do_projeto,
    perfil_do_orcamento,
    perfil_do_projeto,
    registrar_camada,
    sessao_como,
)
from orca.regras import ErroRegras, camada_padrao, ler_camada

USUARIO = "usuario:Leonardo"

SECRETARIA = """perfil: Secretaria Exemplo
camada: secretaria
versao: 1
fontes:
  validade_dias: 90
"""


def _camada(texto):
    return ler_camada(texto, "teste")


def test_projeto_usa_o_padrao_do_sistema(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        perfil = perfil_do_projeto(s, s.get(Projeto, projeto_id))
        assert perfil.regras.fontes.validade_dias == 180
        assert [c.nome for c in perfil.cadeia] == ["padrao-sistema"]


def test_cadeia_com_secretaria_e_orcamento(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        projeto = s.get(Projeto, projeto_id)
        definir_camadas_do_projeto(s, projeto, [_camada(SECRETARIA)])
        orcamento = s.scalars(select(Orcamento)).first()
        definir_camada_do_orcamento(
            s, orcamento, _camada("perfil: Alimentação\ncamada: orcamento\nversao: 1\ncalculo:\n  base_preco_final: A\n")
        )
    with sessao_como(fabrica, USUARIO) as s:
        orcamento = s.scalars(select(Orcamento)).first()
        perfil = perfil_do_orcamento(s, orcamento)
        assert perfil.regras.fontes.validade_dias == 90
        assert perfil.regras.calculo.base_preco_final == "A"
        assert perfil.origem_de("fontes.validade_dias") == "Secretaria Exemplo"
        assert perfil.origem_de("calculo.base_preco_final") == "Alimentação"
        assert [c.nivel for c in perfil.cadeia] == ["sistema", "secretaria", "orcamento"]
        assert perfil_do_projeto(s, orcamento.projeto).regras.calculo.base_preco_final == "B"


def test_registrar_a_mesma_versao_duas_vezes_reaproveita(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        org_id = s.get(Projeto, projeto_id).organizacao_id
        a = registrar_camada(s, _camada(SECRETARIA), org_id)
        b = registrar_camada(s, _camada(SECRETARIA), org_id)
        assert a is b
        assert s.scalar(select(func.count()).select_from(PerfilRegras).where(PerfilRegras.nome == "Secretaria Exemplo")) == 1


def test_mesma_versao_com_conteudo_diferente_e_recusada(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        org_id = s.get(Projeto, projeto_id).organizacao_id
        registrar_camada(s, _camada(SECRETARIA), org_id)
        with pytest.raises(ErroRegras, match="aumente a versão"):
            registrar_camada(s, _camada(SECRETARIA.replace("90", "60")), org_id)
        registrar_camada(s, _camada(SECRETARIA.replace("90", "60").replace("versao: 1", "versao: 2")), org_id)


def test_padrao_do_sistema_e_gravado_uma_vez_so(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        definir_camadas_do_projeto(s, s.get(Projeto, projeto_id))
        total = s.scalar(select(func.count()).select_from(PerfilRegras).where(PerfilRegras.nivel == "sistema"))
        assert total == 1


def test_cadeia_invalida_nao_e_gravada(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        projeto = s.get(Projeto, projeto_id)
        antes = list(projeto.camadas_regras)
        with pytest.raises(ErroRegras, match="chave desconhecida"):
            definir_camadas_do_projeto(s, projeto, [_camada(SECRETARIA.replace("validade_dias", "validade_dia"))])
        with pytest.raises(ErroRegras, match="camadas de orçamento"):
            definir_camadas_do_projeto(s, projeto, [_camada("perfil: X\ncamada: orcamento\nversao: 1\n")])
        assert projeto.camadas_regras == antes


def test_camada_do_sistema_nao_pertence_a_organizacao(fabrica, projeto_id):
    with sessao_como(fabrica, USUARIO) as s:
        org_id = s.get(Projeto, projeto_id).organizacao_id
        with pytest.raises(ErroRegras, match="não tem organização"):
            registrar_camada(s, camada_padrao(), org_id)
        with pytest.raises(ErroRegras, match="precisam ter"):
            registrar_camada(s, _camada(SECRETARIA), None)
