"""Catálogo de lojas e fornecedores (catalogos/lojas.yaml): o que o sistema já sabe de cada site."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

CATALOGO_PADRAO = Path(__file__).resolve().parents[3] / "catalogos" / "lojas.yaml"


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
