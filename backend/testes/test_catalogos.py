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
