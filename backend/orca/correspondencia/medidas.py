"""Leitura de medidas em títulos de produtos (texto já normalizado), sem float.

Cada leitor devolve os valores encontrados com o trecho do texto de onde saíram
(para não contar a mesma coisa duas vezes). Valores iguais escritos de formas
diferentes ficam iguais: "1kg" = "1.000 g", "1,5 L" = "1500 ml", "210mmx297mm" = A4.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

NUM = r"(\d+(?:[.,]\d+)?)"
INTEIRO = r"(\d{1,3}(?:\.\d{3})+|\d+)"
_FIM = r"(?![a-z0-9])"

_MASSA = {"mg": Fraction(1, 1000), "g": 1, "gr": 1, "grs": 1, "grama": 1, "gramas": 1, "kg": 1000, "kgs": 1000,
          "quilo": 1000, "quilos": 1000}
_VOLUME = {"ml": 1, "l": 1000, "lt": 1000, "lts": 1000, "litro": 1000, "litros": 1000}
_UNIDADE_QTD = "|".join(sorted(list(_MASSA) + list(_VOLUME), key=len, reverse=True))
_NAO_GRAMATURA = r"(?!\s*/\s*m)"  # "75 g/m2" é gramatura, não peso


def numero(texto: str) -> Fraction:
    """ "1,5" → 3/2; "1.000" → 1000 (ponto seguido de 3 dígitos = milhar); "2.5" → 5/2."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", texto):
        return Fraction(int(texto.replace(".", "")))
    return Fraction(texto.replace(",", "."))


def _formatar(valor: Fraction) -> str:
    if valor.denominator == 1:
        return str(valor.numerator)
    return f"{float(valor):g}".replace(".", ",")  # só para mensagens


@dataclass(frozen=True, order=True)
class Quantidade:
    """Conteúdo líquido: `unidades` × `conteudo` (em g ou ml)."""

    grandeza: str  # "massa" (g) | "volume" (ml)
    unidades: int
    conteudo: Fraction

    @property
    def total(self) -> Fraction:
        return self.unidades * self.conteudo

    def __str__(self) -> str:
        unidade = "g" if self.grandeza == "massa" else "ml"
        base = f"{_formatar(self.conteudo)} {unidade}"
        return base if self.unidades == 1 else f"{self.unidades} × {base}"


@dataclass(frozen=True)
class Achado:
    valor: object  # comparável e com __str__ legível
    inicio: int
    fim: int


def _quantidade(n: str, unidade: str, unidades: int = 1) -> Quantidade:
    if unidade in _MASSA:
        return Quantidade("massa", unidades, numero(n) * _MASSA[unidade])
    return Quantidade("volume", unidades, numero(n) * _VOLUME[unidade])


def preparar(texto: str) -> str:
    """Promoções: "LV 990g PG 900g" → "990g"; "leve 12 pague 11 rolos" → "12 rolos"; "15% grátis" some."""
    texto = re.sub(
        rf"\b(?:leve|lv)\s*{NUM}\s*([a-z]+)?\s*(?:pague|pg)\s*{NUM}\s*([a-z]+)?",
        lambda m: f"{m.group(1)} {m.group(2) or m.group(4) or ''}",
        texto,
    )
    return re.sub(r"\d+\s*%\s*(?:gratis|a mais|off)\b", " ", texto)


# --- Leitores -----------------------------------------------------------------------------


def quantidades(texto: str, grandezas: tuple[str, ...] = ("massa", "volume")) -> list[Achado]:
    achados: list[Achado] = []
    ocupado: list[tuple[int, int]] = []
    multiplo = rf"(?<![\w.,])(\d+)\s*x\s*{NUM}\s*({_UNIDADE_QTD}){_NAO_GRAMATURA}{_FIM}"
    for m in re.finditer(multiplo, texto):
        q = _quantidade(m.group(2), m.group(3), int(m.group(1)))
        if q.grandeza in grandezas and int(m.group(1)) > 0:
            achados.append(Achado(q, m.start(), m.end()))
        ocupado.append((m.start(), m.end()))
    simples = rf"(?<![\w.,]){NUM}\s*({_UNIDADE_QTD}){_NAO_GRAMATURA}{_FIM}"
    for m in re.finditer(simples, texto):
        if any(i <= m.start() < f for i, f in ocupado):
            continue
        q = _quantidade(m.group(1), m.group(2))
        if q.grandeza in grandezas:
            achados.append(Achado(q, m.start(), m.end()))
    return achados


def gramaturas(texto: str) -> list[Achado]:
    """Papel: "75g", "75 g/m2", "75gsm" (em papel, "75 g" é sempre gramatura)."""
    padrao = rf"(?<![\w.,]){NUM}\s*(?:g|gr|grs|gsm)(?:\s*/\s*m2?|\s*m2)?{_FIM}"
    return [Achado(_Valor(numero(m.group(1)), "g/m²"), m.start(), m.end()) for m in re.finditer(padrao, texto)]


_FORMATOS_MM = {(210, 297): "a4", (297, 420): "a3", (148, 210): "a5", (105, 148): "a6", (216, 330): "oficio",
                (216, 279): "carta", (420, 594): "a2"}


def formatos(texto: str) -> list[Achado]:
    achados = [Achado(_Valor(m.group(1), ""), m.start(), m.end())
               for m in re.finditer(r"\b(a[0-6]|oficio|carta)\b", texto)]
    for d in dimensoes(texto):
        lados = d.valor.valor
        for (a, b), nome in _FORMATOS_MM.items():
            if abs(lados[0] - a) <= 2 and abs(lados[1] - b) <= 2:
                achados.append(Achado(_Valor(nome, ""), d.inicio, d.fim))
    return achados


def folhas(texto: str) -> list[Achado]:
    padrao = rf"(?<![\w.,]){INTEIRO}\s*(?:folhas?|fls?|fl){_FIM}"
    return [Achado(_Valor(int(numero(m.group(1))), "folhas"), m.start(), m.end()) for m in re.finditer(padrao, texto)]


_CONTAVEIS = r"un|und|unds|unid|unidades?|pecas?|pcs?|rolos?|saches?|capsulas?|tabletes?|envelopes?|pares?|sacos?"


def unidades(texto: str) -> list[Achado]:
    """Unidades na embalagem: "50 un", "12 rolos", "com 26 un", "kit 2", "c/ 12", "10x5,2g" (10)."""
    achados = []
    for m in re.finditer(rf"(?<![\w.,]){INTEIRO}\s*(?:{_CONTAVEIS}){_FIM}", texto):
        achados.append(Achado(_Valor(int(numero(m.group(1))), "un"), m.start(), m.end()))
    for m in re.finditer(rf"\b(?:kit|pack|fardo|c/|com)\s*(?:com\s*)?(\d+){_FIM}(?!\s*(?:{_UNIDADE_QTD}|m|cm|mm|folhas?|fls?|fl|{_CONTAVEIS})\b)", texto):
        achados.append(Achado(_Valor(int(m.group(1)), "un"), m.start(), m.end()))
    for m in re.finditer(rf"(?<![\w.,])(\d+)\s*x\s*{NUM}\s*(?:{_UNIDADE_QTD}){_FIM}", texto):
        achados.append(Achado(_Valor(int(m.group(1)), "un"), m.start(), m.start() + len(m.group(1))))
    return achados


def dimensoes(texto: str) -> list[Achado]:
    """ "30x29,5cm", "23cmx22cm", "210mmx297mm" → lados em mm, do menor para o maior."""
    fator = {"mm": 1, "cm": 10, "m": 1000}
    padrao = rf"(?<![\w.,]){NUM}\s*(mm|cm|m)?\s*x\s*{NUM}\s*(mm|cm|m){_FIM}"
    achados = []
    for m in re.finditer(padrao, texto):
        u2 = fator[m.group(4)]
        u1 = fator[m.group(2)] if m.group(2) else u2
        lados = tuple(sorted((numero(m.group(1)) * u1, numero(m.group(3)) * u2)))
        achados.append(Achado(_Valor(lados, "mm"), m.start(), m.end()))
    return achados


def comprimentos(texto: str) -> list[Achado]:
    """Metragem de rolo: "30m", "300 metros"."""
    padrao = rf"(?<![\w.,x]){NUM}\s*(?:m|metros?){_FIM}(?!\s*x)"
    return [Achado(_Valor(numero(m.group(1)), "m"), m.start(), m.end()) for m in re.finditer(padrao, texto)]


def concentracoes(texto: str) -> list[Achado]:
    """ "70%", "70°INPM", "46 °gl"."""
    padrao = rf"(?<![\w.,]){NUM}\s*(?:%|°)\s*(?:inpm|gl)?{_FIM}"
    return [Achado(_Valor(numero(m.group(1)), "%"), m.start(), m.end()) for m in re.finditer(padrao, texto)]


def voltagens(texto: str) -> list[Achado]:
    achados = [Achado(_Valor(m.group(1), "V"), m.start(), m.end())
               for m in re.finditer(r"(?<![\w.,])(110|127|220|12|24)\s*v(?:olts?)?\b", texto)]
    achados += [Achado(_Valor("bivolt", ""), m.start(), m.end()) for m in re.finditer(r"\bbivolt\b", texto)]
    return achados


def espessuras(texto: str) -> list[Achado]:
    padrao = rf"(?<![\w.,])(\d[.,]\d)\s*mm{_FIM}"
    return [Achado(_Valor(numero(m.group(1)), "mm"), m.start(), m.end()) for m in re.finditer(padrao, texto)]


def numeros_de_modelo(texto: str) -> list[Achado]:
    """ "Nº 103", "n° 102", "número 3"."""
    padrao = r"\b(?:n\s*°|no\.|numero)\s*(\d+)\b"
    return [Achado(_Valor(int(m.group(1)), ""), m.start(), m.end()) for m in re.finditer(padrao, texto)]


def tipos_numerados(texto: str) -> list[Achado]:
    """Classificação oficial: "Tipo 1", "tipo 2"."""
    return [Achado(_Valor(int(m.group(1)), ""), m.start(), m.end()) for m in re.finditer(r"\btipo\s*(\d)\b", texto)]


@dataclass(frozen=True, order=True)
class _Valor:
    valor: object
    unidade: str

    def __str__(self) -> str:
        v = self.valor
        if isinstance(v, tuple):
            texto = "x".join(_formatar(x) for x in v)
        elif isinstance(v, Fraction):
            texto = _formatar(v)
        else:
            texto = str(v).upper() if isinstance(v, str) and len(str(v)) <= 3 else str(v)
        return f"{texto} {self.unidade}".strip()


LEITORES: dict[str, Callable[[str], list[Achado]]] = {
    "peso_ou_volume_liquido": quantidades,
    "volume": lambda t: quantidades(t, ("volume",)),
    "capacidade": lambda t: quantidades(t, ("volume",)),
    "gramatura": gramaturas,
    "formato": formatos,
    "folhas_por_pacote": folhas,
    "unidades_por_embalagem": unidades,
    "dimensoes": dimensoes,
    "comprimento": comprimentos,
    "concentracao": concentracoes,
    "voltagem": voltagens,
    "espessura_ponta": espessuras,
    "numero_do_modelo": numeros_de_modelo,
    "tipo_numerado": tipos_numerados,
}
