"""Catálogos versionados: lojas e fornecedores (lojas.yaml) e atributos por categoria (atributos.yaml)."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from orca.correspondencia import Vocabulario

PASTA_CATALOGOS = Path(__file__).resolve().parents[3] / "catalogos"
CATALOGO_PADRAO = PASTA_CATALOGOS / "lojas.yaml"
ATRIBUTOS_PADRAO = PASTA_CATALOGOS / "atributos.yaml"
JORNADAS_PADRAO = PASTA_CATALOGOS / "jornadas.yaml"


@dataclass(frozen=True)
class LojaCatalogo:
    id: str
    nome: str
    dominio: str  # sem "www."
    tipo: str  # "loja" | "fornecedor" (tabela fonte)
    coleta: str  # C0…C4
    marketplace: bool
    cep: str | None  # como o site trata o CEP (regiao_por_cep, pede_cep, a_verificar…)
    preco_a_usar: str | None  # D-60 a D-63


def dominio_da_url(url: str) -> str:
    dominio = (urlparse(url).hostname or "").lower()
    return dominio[4:] if dominio.startswith("www.") else dominio


def ler_catalogo(caminho: Path | str = CATALOGO_PADRAO) -> dict[str, LojaCatalogo]:
    """Entradas do catálogo por domínio. Sem o arquivo, o catálogo fica vazio."""
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    entradas = {}
    for grupo, tipo in (("lojas", "loja"), ("fornecedores_servico", "fornecedor")):
        for d in dados.get(grupo) or []:
            dominio = dominio_da_url("https://" + d["dominio"])
            entradas[dominio] = LojaCatalogo(
                id=d["id"],
                nome=d["nome"],
                dominio=dominio,
                tipo=tipo,
                coleta=d["coleta"],
                marketplace=bool(d.get("marketplace", False)),
                cep=d.get("cep"),
                preco_a_usar=d.get("preco_a_usar"),
            )
    return entradas


def ler_vocabulario(caminho: Path | str = ATRIBUTOS_PADRAO) -> Vocabulario:
    """Atributos críticos por categoria e vocabulário de valores (catalogos/atributos.yaml)."""
    return Vocabulario.de_dados(yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {})


@dataclass(frozen=True)
class Jornada:
    id: str
    descricao: str
    jornada_semanal_horas: int
    fator_divisor: int  # divisor mensal = jornada semanal × fator (D-42)
    fonte_legal: str


def ler_jornadas(caminho: Path | str = JORNADAS_PADRAO) -> dict[str, Jornada]:
    """Tabela de jornadas revisada por humano (catalogos/jornadas.yaml), por id."""
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    fator = int(dados["fator_divisor"])
    return {
        j["id"]: Jornada(j["id"], j["descricao"], int(j["jornada_semanal_horas"]), fator, j.get("fonte_legal", ""))
        for j in dados["jornadas"]
    }
