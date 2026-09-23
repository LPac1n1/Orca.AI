"""Normalização de textos de produtos: minúsculas, sem acentos, palavras comparáveis.

"Chamex Papel Sulfite A4 75g – 500 fls" e "Papel Sulfite A4 75g Chamex 500 folhas"
precisam virar a mesma coisa; diferenças só de escrita não podem separar produtos.
"""

import re
import unicodedata

# Palavras que não distinguem produtos: ligação, embalagem genérica e comércio.
PALAVRAS_VAZIAS = frozenset(
    """
    a o as os e de da do das dos em no na nos nas com para p c sem por ao aos um uma
    pacote pct pt pc caixa cx caixeta embalagem emb unidade unidades un und unid unds
    produto novo nova original oferta promocao gratis leve pague lv pg economica
    tamanho familia tipo marca ref cod codigo item x
    """.split()
)

_NUMERO_POR_EXTENSO = {"um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "quatro": "4", "cinco": "5"}


def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar(texto: str | None) -> str:
    """Minúsculas, sem acentos, "º" → "°", "²" → "2", espaços simples. Mantém , . / x % ° para as medidas."""
    if not texto:
        return ""
    t = texto.lower().replace("º", "°").replace("ª", "a").replace("²", "2").replace("³", "3")
    t = sem_acentos(t)
    t = re.sub(r"[‐-―−]", "-", t)  # travessões
    t = re.sub(r"[^a-z0-9°%.,/+\-x ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def raiz(palavra: str) -> str:
    """Forma comparável: sem plural e sem gênero ("folhas" → "folh", "moída" → "moid")."""
    if len(palavra) > 3 and palavra.endswith("s"):
        palavra = palavra[:-1]
    if len(palavra) > 3 and palavra[-1] in "ao":
        palavra = palavra[:-1]
    return palavra


def palavras(texto: str) -> list[str]:
    """Palavras de um texto já normalizado (sem números)."""
    return [p for p in re.findall(r"[a-z]+", texto) if not p.isdigit()]


def palavras_significativas(texto: str) -> set[str]:
    return {raiz(p) for p in palavras(texto) if p not in PALAVRAS_VAZIAS and len(p) > 1}


def compacto(texto: str | None) -> str:
    """Para comparar marcas: "Paper One" = "PaperOne"; "Três Corações" = "3 Corações"."""
    t = normalizar(texto)
    t = " ".join(_NUMERO_POR_EXTENSO.get(p, p) for p in t.split())
    return re.sub(r"[^a-z0-9]", "", t)


def apagar_trechos(texto: str, trechos: list[tuple[int, int]]) -> str:
    """Troca por espaços os trechos já reconhecidos (medidas, valores do vocabulário)."""
    letras = list(texto)
    for inicio, fim in trechos:
        for i in range(inicio, fim):
            letras[i] = " "
    return "".join(letras)


def palavras_da_marca(marca: str | None) -> set[str]:
    """Palavras e números da marca, com os números também por extenso ("3 Corações" ↔ "Três Corações")."""
    texto = normalizar(marca)
    numeros = set(re.findall(r"\d+", texto)) | {_NUMERO_POR_EXTENSO[p] for p in texto.split() if p in _NUMERO_POR_EXTENSO}
    extenso = {raiz(p) for p, n in _NUMERO_POR_EXTENSO.items() if n in numeros}
    return palavras_significativas(texto) | numeros | extenso
