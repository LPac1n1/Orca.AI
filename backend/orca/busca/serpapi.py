"""Descoberta pela internet (C2, opcional): a busca do Google pela SerpApi, no plano grátis.

Serve só para achar páginas: de produto em lojas que o catálogo não pesquisa sozinho, e de
vagas (Google Vagas, D-69 revista). Não é evidência (docs/04 §5.1): cada página é capturada
e conferida como se tivesse sido colada (prova, preço ou salário, CNPJ, correspondência).
"""

from dataclasses import dataclass

import httpx

from orca.busca.conectores import IDENTIFICACAO, ErroBusca
from orca.busca.ranking import Candidato
from orca.coleta.extracao import precos_visiveis

ENDERECO = "https://serpapi.com/search.json"


def _pedir(cliente: httpx.Client, parametros: dict) -> dict:
    """Um pedido à SerpApi (a chave só vai como parâmetro, que é o único jeito que ela aceita, por HTTPS)."""
    try:
        r = cliente.get(ENDERECO, params=parametros, headers=IDENTIFICACAO, timeout=60)
    except httpx.HTTPError as erro:
        raise ErroBusca(f"Não deu para falar com a SerpApi: {erro.__class__.__name__}") from erro
    try:
        dados = r.json()
    except ValueError:
        dados = {}
    erro = str(dados.get("error") or "") if isinstance(dados, dict) else ""
    if r.status_code == 401 or "api key" in erro.lower():
        raise ErroBusca("A SerpApi recusou a chave. Confira a chave em Opcionais.")
    if r.status_code == 429 or "run out of searches" in erro.lower():
        raise ErroBusca("As buscas do plano grátis da SerpApi acabaram neste mês.")
    if r.status_code >= 400:
        raise ErroBusca(f"A SerpApi respondeu com erro (código {r.status_code}).")
    return dados if isinstance(dados, dict) else {}


def buscar_na_web(cliente: httpx.Client, chave: str, termo: str, quantos: int = 20) -> list[Candidato]:
    """Resultados da busca do Google (Brasil, em português) para o termo."""
    dados = _pedir(cliente, {"engine": "google", "q": termo, "gl": "br", "hl": "pt-br", "google_domain": "google.com.br",
                             "num": quantos, "api_key": chave})
    candidatos = []
    for resultado in dados.get("organic_results") or []:
        link = resultado.get("link") or ""
        if not link.startswith(("https://", "http://")):
            continue
        extensoes = ((resultado.get("rich_snippet") or {}).get("top") or {}).get("extensions") or []
        texto = " ".join(str(p) for p in (resultado.get("title"), resultado.get("snippet"), *extensoes) if p)
        precos = precos_visiveis(texto)  # só para mostrar; o preço que vale é o da página
        candidatos.append(Candidato(url=link, titulo=" ".join(str(resultado.get("title") or "").split())[:300],
                                    preco_centavos=precos[0] if precos else None, texto=texto[:600]))
    return candidatos


@dataclass(frozen=True)
class VagaNoGoogle:
    """Uma vaga como o Google Vagas mostra. O salário daqui não é prova: vale o da página da vaga."""

    titulo: str
    empresa: str | None
    local: str | None
    salario: str | None
    publicada: str | None
    links: tuple[tuple[str, str], ...]  # (onde se candidatar, endereço)


def buscar_vagas_google(cliente: httpx.Client, chave: str, cargo: str, cidade: str | None = None,
                        uf: str | None = None) -> list[VagaNoGoogle]:
    """Google Vagas (D-69 revista): o Google junta as vagas de várias plataformas."""
    termo = " ".join(p.strip() for p in (cargo, cidade, uf) if p and p.strip())
    dados = _pedir(cliente, {"engine": "google_jobs", "q": termo, "gl": "br", "hl": "pt-br",
                             "google_domain": "google.com.br", "api_key": chave})
    vagas = []
    for v in dados.get("jobs_results") or []:
        extensoes = v.get("detected_extensions") or {}
        links = tuple((str(o.get("title") or ""), o["link"]) for o in v.get("apply_options") or []
                      if str(o.get("link") or "").startswith(("https://", "http://")))
        vagas.append(VagaNoGoogle(titulo=str(v.get("title") or ""), empresa=v.get("company_name"), local=v.get("location"),
                                  salario=extensoes.get("salary"), publicada=extensoes.get("posted_at"), links=links))
    return vagas

