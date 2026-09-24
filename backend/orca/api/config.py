"""Configuração local: pasta de dados, nome de quem usa e porta (D-05).

Guardada em %APPDATA%\\Orca.AI\\config.json (ou no caminho de ORCA_CONFIG). Os dados
em si ficam na pasta de dados escolhida (pode estar no OneDrive ou Google Drive).
"""

import getpass
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

PORTA_PADRAO = 8765


def arquivo_de_config() -> Path:
    if os.environ.get("ORCA_CONFIG"):
        return Path(os.environ["ORCA_CONFIG"])
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    return base / "Orca.AI" / "config.json"


def pasta_padrao() -> Path:
    documentos = Path.home() / "Documents"
    return (documentos if documentos.exists() else Path.home()) / "Orca.AI"


def nome_valido(nome: str) -> str:
    """O nome entra no histórico como "usuario:<nome>"."""
    nome = re.sub(r"\s+", " ", nome or "").strip()
    if not nome or len(nome) > 100:
        raise ValueError("Informe um nome de até 100 letras.")
    return nome


@dataclass
class Configuracao:
    pasta_dados: str
    usuario: str
    porta: int = PORTA_PADRAO

    @property
    def autor(self) -> str:
        return f"usuario:{self.usuario}"

    @property
    def pasta(self) -> Path:
        return Path(self.pasta_dados)


def ler_config(caminho: Path | None = None) -> Configuracao:
    caminho = caminho or arquivo_de_config()
    if caminho.exists():
        dados = json.loads(caminho.read_text(encoding="utf-8-sig"))  # aceita o arquivo salvo pelo Bloco de Notas (com BOM)
        return Configuracao(dados["pasta_dados"], nome_valido(dados["usuario"]), int(dados.get("porta", PORTA_PADRAO)))
    config = Configuracao(str(pasta_padrao()), nome_valido(getpass.getuser() or "Usuário"))
    salvar_config(config, caminho)
    return config


def salvar_config(config: Configuracao, caminho: Path | None = None) -> Path:
    caminho = caminho or arquivo_de_config()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho
