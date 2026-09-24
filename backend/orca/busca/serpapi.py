"""Descoberta pela internet (C2, opcional): a busca do Google pela SerpApi, no plano grátis.

Serve só para achar páginas de produto em lojas que o catálogo não pesquisa sozinho. Não
é evidência (docs/04 §5.1): a pessoa escolhe os links, e cada página é capturada e conferida
como se tivesse sido colada (prova, preço, CNPJ do vendedor, correspondência).
"""

import httpx

from orca.busca.conectores import IDENTIFICACAO, ErroBusca
from orca.busca.ranking import Candidato
from orca.coleta.extracao import precos_visiveis

ENDERECO = "https://serpapi.com/search.json"


def buscar_na_web(cliente: httpx.Client, chave: str, termo: str, quantos: int = 20) -> list[Candidato]:
    """Resultados da busca do Google (Brasil, em português) para o termo."""
    parametros = {"engine": "google", "q": termo, "gl": "br", "hl": "pt-br", "google_domain": "google.com.br",
                  "num": quantos, "api_key": chave}  # a SerpApi só aceita a chave como parâmetro (HTTPS)
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
