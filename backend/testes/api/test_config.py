"""Configuração local do comando `orca` (pasta de dados, nome e porta)."""

import json

import pytest

from orca.api.config import Configuracao, ler_config, salvar_config


def test_primeira_vez_cria_a_configuracao(tmp_path):
    caminho = tmp_path / "Orca.AI" / "config.json"
    config = ler_config(caminho)
    assert caminho.exists() and config.porta == 8765 and config.usuario
    assert config.autor == f"usuario:{config.usuario}"


def test_le_o_que_foi_salvo(tmp_path):
    caminho = tmp_path / "config.json"
    salvar_config(Configuracao(str(tmp_path / "dados"), "  Maria   da Silva ", 8800), caminho)
    config = ler_config(caminho)
    assert (config.usuario, config.porta, config.pasta) == ("Maria da Silva", 8800, tmp_path / "dados")


def test_arquivo_salvo_com_bom_pelo_bloco_de_notas(tmp_path):
    caminho = tmp_path / "config.json"
    dados = {"pasta_dados": str(tmp_path / "dados"), "usuario": "Leonardo", "porta": 8765}
    caminho.write_text(json.dumps(dados), encoding="utf-8-sig")  # começa com a marca BOM
    assert ler_config(caminho).usuario == "Leonardo"


def test_nome_vazio_e_recusado(tmp_path):
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps({"pasta_dados": str(tmp_path), "usuario": "   "}), encoding="utf-8")
    with pytest.raises(ValueError, match="nome"):
        ler_config(caminho)
