"""IA opcional e plugável (D-50 a D-52; Fase 2, etapa 15). O sistema funciona sem ela."""

from orca.ia.correspondencia import Julgamento, dados_enviados, julgar_correspondencia
from orca.ia.provedores import (
    ENDERECO_LOCAL,
    MODELO_GEMINI,
    PROVEDORES,
    ConfigIA,
    ErroFormatoIA,
    ErroIA,
    Gemini,
    ModeloLocal,
    ProvedorIA,
    provedor_configurado,
)

__all__ = [
    "ENDERECO_LOCAL",
    "MODELO_GEMINI",
    "PROVEDORES",
    "ConfigIA",
    "ErroFormatoIA",
    "ErroIA",
    "Gemini",
    "Julgamento",
    "ModeloLocal",
    "ProvedorIA",
    "dados_enviados",
    "julgar_correspondencia",
    "provedor_configurado",
]
