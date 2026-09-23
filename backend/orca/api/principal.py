r"""Comando `orca`: abre o Orça.AI no navegador (http://localhost:8765).

    orca                      usa a configuração salva (ou cria uma na primeira vez)
    orca --pasta D:\Dados     muda a pasta de dados
    orca --usuario "Maria"    muda o nome que aparece no histórico
"""

import argparse
import threading
import webbrowser

import uvicorn

from orca.api.app import criar_app
from orca.api.config import arquivo_de_config, ler_config, nome_valido, salvar_config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="orca", description="Orça.AI — montador de orçamentos para OSCs")
    parser.add_argument("--pasta", help="pasta de dados (banco, evidências e exportações)")
    parser.add_argument("--usuario", help="seu nome, como aparece no histórico")
    parser.add_argument("--porta", type=int, help="porta local (padrão 8765)")
    parser.add_argument("--sem-navegador", action="store_true", help="não abrir o navegador")
    args = parser.parse_args(argv)

    config = ler_config()
    if args.pasta or args.usuario or args.porta:
        config.pasta_dados = args.pasta or config.pasta_dados
        config.usuario = nome_valido(args.usuario) if args.usuario else config.usuario
        config.porta = args.porta or config.porta
        salvar_config(config)
    endereco = f"http://localhost:{config.porta}"
    print(f"Orça.AI em {endereco}")
    print(f"Pasta de dados: {config.pasta}  ·  usuário: {config.usuario}  ·  configuração: {arquivo_de_config()}")
    print("Para encerrar, feche esta janela ou aperte Ctrl+C.")
    app = criar_app(config)
    if not args.sem_navegador:
        threading.Timer(1.5, webbrowser.open, [endereco]).start()
    uvicorn.run(app, host="127.0.0.1", port=config.porta, log_level="warning")


if __name__ == "__main__":
    main()
