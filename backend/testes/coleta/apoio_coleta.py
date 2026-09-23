"""Apoio aos testes da coleta: páginas e capturas sintéticas, navegador falso."""

import json
from datetime import UTC, datetime

from orca.coleta import Captura

USUARIO = "usuario:Leonardo"
EAN = "7891000100103"


def pagina_produto(preco: str = "25.29", titulo: str = "Papel Sulfite A4 Chamex 500 folhas") -> str:
    produto = {
        "@type": "Product", "name": titulo, "brand": "Chamex", "gtin13": EAN,
        "offers": {"price": preco, "priceCurrency": "BRL", "availability": "InStock"},
    }
    return f'<html><script type="application/ld+json">{json.dumps(produto)}</script><body>{titulo}</body></html>'


def captura_falsa(
    url: str = "https://www.kalunga.com.br/prod/papel-a4/1",
    html: str | None = None,
    texto: str = "Papel Sulfite A4 Chamex por R$ 25,29 — Kalunga S.A. CNPJ 43.283.811/0001-50",
    momento: datetime = datetime(2026, 9, 23, 15, 0, tzinfo=UTC),
    cep: str | None = None,
    metodo: str = "C1",
    bloqueio: str | None = None,
    semente: str = "",
) -> Captura:
    """Captura sem navegador: os arquivos são bytes distintos, marcados pela URL e pelo momento."""
    marca = f"{url}|{momento.isoformat()}|{semente}".encode()
    return Captura(
        url_pedida=url, url_final=url, capturado_em=momento, titulo="Página", status_http=200,
        html=html if html is not None else pagina_produto(), html_quadros=(), texto_visivel=texto,
        pdf=b"%PDF-" + marca, png=b"PNG-" + marca, mhtml=b"MHTML-" + marca,
        cep=cep, metodo=metodo, bloqueio=bloqueio,
    )


class NavegadorFalso:
    """Devolve capturas preparadas, na ordem, e guarda as URLs pedidas."""

    def __init__(self, *capturas: Captura):
        self.capturas = list(capturas)
        self.pedidas: list[tuple[str, str | None]] = []

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        self.pedidas.append((url, cep))
        return self.capturas.pop(0)
