"""API local (FastAPI) e comando `orca` (docs/04 §1)."""

from orca.api.app import Servico, contexto_padrao, criar_app
from orca.api.config import Configuracao, ler_config, salvar_config

__all__ = ["Configuracao", "Servico", "contexto_padrao", "criar_app", "ler_config", "salvar_config"]
