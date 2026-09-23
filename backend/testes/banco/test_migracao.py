"""Banco: migrações, proteções e ausência de números decimais."""

import sqlite3

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Float, Numeric, inspect, text
from sqlalchemy.exc import DatabaseError

from orca.banco import TABELAS_IMUTAVEIS, Base, copiar_banco, criar_engine, revisao_atual, revisao_mais_nova


def test_migracoes_criam_exatamente_as_tabelas_do_codigo(fabrica):
    engine = fabrica.kw["bind"]
    assert revisao_atual(engine) == revisao_mais_nova()
    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    assert diferencas == [], f"Migração desatualizada em relação às tabelas: {diferencas}"


def test_banco_com_chaves_estrangeiras_e_wal(fabrica):
    with fabrica.kw["bind"].connect() as conexao:
        assert conexao.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conexao.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_todas_as_tabelas_protegidas_por_gatilhos(fabrica):
    engine = fabrica.kw["bind"]
    tabelas = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tabelas == set(Base.metadata.tables)
    with engine.connect() as conexao:
        gatilhos = set(conexao.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'")).scalars())
    for tabela in tabelas:
        assert f"nao_apagar_{tabela}" in gatilhos, tabela
        assert (f"imutavel_{tabela}" in gatilhos) == (tabela in TABELAS_IMUTAVEIS), tabela


def test_nenhuma_coluna_decimal():
    for tabela in Base.metadata.tables.values():
        for coluna in tabela.columns:
            assert not isinstance(coluna.type, (Float, Numeric)), f"{tabela.name}.{coluna.name} usa número decimal"


def test_gatilhos_recusam_apagar_e_alterar_imutavel(fabrica, projeto_id):
    engine = fabrica.kw["bind"]
    with engine.begin() as conexao:
        with pytest.raises(DatabaseError, match="nunca são apagados"):
            conexao.execute(text("DELETE FROM projeto"))
    with engine.begin() as conexao:
        with pytest.raises(DatabaseError, match="imutável"):
            conexao.execute(text("UPDATE perfil_regras SET versao = 99"))
    with engine.begin() as conexao:
        with pytest.raises(DatabaseError, match="imutável"):
            conexao.execute(text("UPDATE evento SET autor = 'usuario:Outro'"))
    with engine.begin() as conexao:  # tabela viva aceita alteração direta
        conexao.execute(text("UPDATE projeto SET nome = 'Outro nome'"))


def test_restricoes_do_banco(fabrica, projeto_id):
    engine = fabrica.kw["bind"]
    with engine.begin() as conexao:
        with pytest.raises(DatabaseError):
            conexao.execute(text("UPDATE projeto SET teto_centavos = 0"))


def test_copia_de_seguranca(fabrica, projeto_id, tmp_path):
    destino = copiar_banco(fabrica.kw["bind"], tmp_path / "copia.sqlite")
    with sqlite3.connect(destino) as copia:
        assert copia.execute("SELECT count(*) FROM projeto").fetchone()[0] == 1


def test_reabrir_nao_refaz_migracao(tmp_path):
    from orca.banco import abrir_banco

    caminho = tmp_path / "orca.sqlite"
    abrir_banco(caminho)
    abrir_banco(caminho)  # já atualizado: nenhuma cópia é criada
    assert not list(tmp_path.glob("orca.sqlite.copia-*"))
    assert revisao_atual(criar_engine(caminho)) == revisao_mais_nova()
