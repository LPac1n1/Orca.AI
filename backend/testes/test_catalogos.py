"""Conferência dos catálogos versionados no repositório."""

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]


def test_jornadas_divisor_e_semanal_vezes_fator_e_revisado():
    dados = yaml.safe_load((RAIZ / "catalogos" / "jornadas.yaml").read_text(encoding="utf-8"))
    fator = dados["fator_divisor"]
    ids = [j["id"] for j in dados["jornadas"]]
    assert "regra_geral" in ids
    assert len(ids) == len(set(ids))
    for j in dados["jornadas"]:
        assert j["divisor_mensal"] == j["jornada_semanal_horas"] * fator, j["id"]
        assert j["fonte_legal"], j["id"]
        assert j["revisado_por"] and j["revisado_em"], j["id"]


def test_lojas_tem_campos_basicos():
    dados = yaml.safe_load((RAIZ / "catalogos" / "lojas.yaml").read_text(encoding="utf-8"))
    ids = []
    for loja in dados["lojas"] + dados["fornecedores_servico"]:
        assert loja["id"] and loja["nome"] and loja["dominio"] and loja["coleta"], loja
        ids.append(loja["id"])
    assert len(ids) == len(set(ids))


def test_atributos_tem_leitor_ou_vocabulario():
    """Todo atributo de categoria é lido pelo programa, tem vocabulário ou é conferido por uma pessoa."""
    from orca.coleta import ler_vocabulario
    from orca.correspondencia import LEITORES

    vocabulario = ler_vocabulario()
    so_por_pessoa = {"escopo", "periodicidade", "unidade_de_cobranca", "modelo_exato"}
    com_vocabulario = {g.atributo for g in vocabulario.grupos}
    for categoria, atributos in vocabulario.categorias.items():
        for atributo in atributos:
            assert atributo in LEITORES or atributo in com_vocabulario or atributo in so_por_pessoa, (categoria, atributo)
    assert set(vocabulario.sempre) == {"marca", "modelo", "apresentacao"}  # D-17


def test_vocabulario_sem_sinonimo_repetido_no_mesmo_grupo():
    from orca.coleta import ler_vocabulario

    for grupo in ler_vocabulario().grupos:
        sinonimos = [s for lista in grupo.valores.values() for s in lista]
        assert len(sinonimos) == len(set(sinonimos)), (grupo.atributo, grupo.nome)
        assert all(sinonimos), (grupo.atributo, grupo.nome)
