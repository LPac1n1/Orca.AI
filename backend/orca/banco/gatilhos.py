"""Gatilhos do SQLite que protegem o histórico (princípio 6: nada é apagado).

- Toda tabela: DELETE é recusado.
- Tabelas imutáveis: UPDATE também é recusado.

Atenção em migrações futuras: operações "batch" do Alembic recriam a tabela e
perdem os gatilhos. Depois delas, chame `criar_gatilhos` de novo. Um teste
confere que todas as tabelas continuam protegidas.
"""

MENSAGEM_APAGAR = "Orça.AI: registros nunca são apagados (use exclusão lógica)"
MENSAGEM_IMUTAVEL = "Orça.AI: registro imutável (crie um novo em vez de alterar)"


def sql_gatilhos(tabela: str, imutavel: bool) -> list[str]:
    comandos = [
        f"DROP TRIGGER IF EXISTS nao_apagar_{tabela}",
        f"CREATE TRIGGER nao_apagar_{tabela} BEFORE DELETE ON {tabela} "
        f"BEGIN SELECT RAISE(ABORT, '{MENSAGEM_APAGAR}'); END",
    ]
    if imutavel:
        comandos += [
            f"DROP TRIGGER IF EXISTS imutavel_{tabela}",
            f"CREATE TRIGGER imutavel_{tabela} BEFORE UPDATE ON {tabela} "
            f"BEGIN SELECT RAISE(ABORT, '{MENSAGEM_IMUTAVEL}'); END",
        ]
    return comandos


def criar_gatilhos(executar, tabela: str, imutavel: bool) -> None:
    """`executar` recebe um comando SQL (ex.: `op.execute` numa migração)."""
    for comando in sql_gatilhos(tabela, imutavel):
        executar(comando)
