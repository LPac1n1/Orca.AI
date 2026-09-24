"""Plataformas de vagas (Fase 2, etapa 11; D-69).

A busca de vagas é feita pela pessoa, na janela do sistema: os termos de uso ou o
robots.txt das plataformas proíbem programas nas buscas (verificado em 24/09/2026).
O sistema só monta o endereço da busca, já com o cargo e a cidade, e guarda a página
da vaga que a pessoa escolher.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import yaml

from orca.coleta.catalogo import PASTA_CATALOGOS

VAGAS_PADRAO = PASTA_CATALOGOS / "vagas.yaml"


def _slug(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


@dataclass(frozen=True)
class PlataformaDeVagas:
    id: str
    nome: str
    dominio: str
    busca: str
    busca_sem_cidade: str
    abrir_vaga: str  # sistema | janela
    motivo: str

    def endereco(self, cargo: str, cidade: str | None = None, uf: str | None = None) -> str:
        """A busca da plataforma já preenchida (sem cidade, se ela não for informada)."""
        com_cidade = bool(cidade and cidade.strip())
        modelo = self.busca if com_cidade else self.busca_sem_cidade
        if com_cidade and "{uf}" in modelo and not (uf and uf.strip()):
            modelo = self.busca_sem_cidade
        return (modelo.replace("{cargo_slug}", _slug(cargo)).replace("{cargo_q}", quote_plus(cargo.strip()))
                .replace("{cidade_slug}", _slug(cidade or "")).replace("{cidade_q}", quote_plus((cidade or "").strip()))
                .replace("{uf}", (uf or "").strip().lower()))


def plataformas_de_vagas(dados: dict) -> list[PlataformaDeVagas]:
    return [
        PlataformaDeVagas(p["id"], p["nome"], p["dominio"], p["busca"], p["busca_sem_cidade"],
                          p.get("abrir_vaga", "janela"), p.get("motivo", ""))
        for p in dados.get("plataformas") or []
    ]


def ler_plataformas(caminho: Path | str = VAGAS_PADRAO) -> list[PlataformaDeVagas]:
    caminho = Path(caminho)
    if not caminho.exists():
        return []
    return plataformas_de_vagas(yaml.safe_load(caminho.read_text(encoding="utf-8")) or {})


def plataforma_do_endereco(url: str, plataformas: list[PlataformaDeVagas]) -> PlataformaDeVagas | None:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return next((p for p in plataformas if p.dominio.lower().removeprefix("www.") == host), None)
