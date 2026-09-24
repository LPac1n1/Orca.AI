"""Como perguntar a cada loja (rede): API pública VTEX e página de busca do site.

O sistema se identifica como Orça.AI e vai devagar (poucas requisições, D-67): não
se disfarça, não aceita cookies, não resolve captcha. Se a loja recusar, a busca dela
passa para a captura assistida.
"""

import json
import time
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

import httpx

from orca.busca.lojas import LojaDeBusca
from orca.busca.ranking import Candidato
from orca.calculo import centavos_de_decimal
from orca.coleta.extracao import precos_visiveis

IDENTIFICACAO = {"User-Agent": "Orca.AI/0.1 (orcamentos para OSCs; https://github.com/LPac1n1/Orca.AI)"}  # só ASCII no cabeçalho


class ErroBusca(RuntimeError):
    pass


@dataclass(frozen=True)
class Consulta:
    texto: str
    ean: str | None = None


class Ritmo:
    """Intervalo mínimo entre dois pedidos à mesma loja."""

    def __init__(self, intervalo_s: float):
        self.intervalo_s = intervalo_s
        self._ultimo: dict[str, float] = {}

    def esperar(self, dominio: str) -> None:
        falta = self._ultimo.get(dominio, float("-inf")) + self.intervalo_s - time.monotonic()
        if falta > 0:
            time.sleep(falta)
        self._ultimo[dominio] = time.monotonic()


def _no_dominio(url: str, dominio: str) -> str:
    """A API às vezes devolve o link em outro endereço da loja (ex.: secure.); a prova é no site da loja."""
    partes = urlsplit(url)
    return urlunsplit(("https", dominio, partes.path, partes.query, ""))


def _centavos(valor) -> int | None:
    try:
        centavos = centavos_de_decimal(Decimal(str(valor)))
    except (ValueError, ArithmeticError):
        return None
    return centavos if centavos > 0 else None


def buscar_vtex(cliente: httpx.Client, loja: LojaDeBusca, consulta: Consulta) -> list[Candidato]:
    """API pública de catálogo VTEX: por código de barras, se houver; senão, por texto."""
    parametros = {"fq": f"alternateIds_Ean:{consulta.ean}"} if consulta.ean else {"ft": consulta.texto}
    try:
        resposta = cliente.get(loja.url, params=parametros, headers=IDENTIFICACAO, follow_redirects=True, timeout=30)
    except httpx.HTTPError as e:
        raise ErroBusca(f"{loja.nome}: a busca não respondeu ({e})") from e
    if resposta.status_code not in (200, 206):
        raise ErroBusca(f"{loja.nome}: a busca respondeu com o código {resposta.status_code}")
    try:
        produtos = json.loads(resposta.text, parse_float=Decimal)
    except json.JSONDecodeError as e:
        raise ErroBusca(f"{loja.nome}: a busca não devolveu dados") from e
    candidatos = []
    for p in produtos if isinstance(produtos, list) else []:
        item = (p.get("items") or [{}])[0]
        oferta = ((item.get("sellers") or [{}])[0].get("commertialOffer") or {})
        if not p.get("link"):
            continue
        candidatos.append(Candidato(
            url=_no_dominio(p["link"], loja.dominio), titulo=p.get("productName") or "", marca=p.get("brand"),
            ean=item.get("ean") or None, preco_centavos=_centavos(oferta.get("Price")),
        ))
    return candidatos


def candidatos_da_pagina(resultados: list[dict]) -> list[Candidato]:
    """Os cartões de produto lidos na página de busca (endereço, título e texto do cartão)."""
    candidatos = []
    for r in resultados:
        texto = " ".join((r.get("texto") or "").split())
        precos = precos_visiveis(texto)
        candidatos.append(Candidato(url=r["href"], titulo=" ".join((r.get("titulo") or "").split())[:300],
                                    preco_centavos=precos[0] if precos else None, texto=texto[:600]))
    return candidatos


def buscar_na_pagina(navegador, loja: LojaDeBusca, consulta: Consulta) -> list[Candidato]:
    """Abre a página de busca do site (sem janela) e lê os produtos que ela mostra."""
    status, resultados = navegador.resultados_de_busca(loja.endereco(consulta.texto), loja.produto or "")
    if status in (401, 403, 429, 503):
        raise ErroBusca(f"{loja.nome}: a busca recusou o programa (código {status}); use a captura com janela")
    return candidatos_da_pagina(resultados)
