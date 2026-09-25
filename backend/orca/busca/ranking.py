"""Escolha dos resultados da busca (sem rede): qual página de produto vale a pena capturar.

A busca só aponta o caminho; a prova e a correspondência que valem são as da página do
produto, capturada depois (docs/04 §5.1). Aqui o sistema só ordena os candidatos: primeiro
os 🟢, depois os 🟡 mais parecidos com o item. Os 🔴 (outro produto) nunca são capturados.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from orca.correspondencia import Anuncio, Especificacao, Vocabulario, comparar, normalizar
from orca.correspondencia.texto import PALAVRAS_VAZIAS, palavras_da_marca, raiz

_ORDEM = {"verde": 0, "amarelo": 1}
_ABREVIACOES = {"fl": "folhas", "fls": "folhas", "folha": "folhas", "un": "unidades", "und": "unidades",
                "unid": "unidades", "pct": "pacote", "pt": "pacote", "pc": "pacote", "cx": "caixa"}


@dataclass(frozen=True)
class Candidato:
    """Um produto na página (ou na API) de busca da loja."""

    url: str
    titulo: str
    marca: str | None = None
    ean: str | None = None
    preco_centavos: int | None = None  # só para mostrar; o preço que vale é o da página do produto
    texto: str = ""  # o texto do cartão do produto na busca
    imagem: str | None = None  # foto do produto na busca (vitrine, D-75)


@dataclass(frozen=True)
class CandidatoAvaliado:
    candidato: Candidato
    status: str  # verde | amarelo
    parecenca: float  # 0 a 1: palavras em comum entre o item e o título
    motivos: tuple[str, ...]


def _palavras(texto: str) -> set[str]:
    palavras = [p.strip(".;:|()[]") for p in normalizar(texto).replace(",", " ").split()]  # "500 fl." = 500 folhas
    palavras = [re.sub(r"^c/(?=\d)", "", p) for p in palavras]  # "caixa c/50" = caixa com 50
    return {_ABREVIACOES.get(p, p) for p in palavras if len(p) > 1 or p.isdigit()}


def parecenca(especificacao: Especificacao, titulo: str) -> float:
    """Palavras em comum sobre todas as palavras do item e do título (0 a 1).

    Palavras a mais no título pesam contra: "reciclado", "eco", "kit" costumam ser outra
    variação do produto (visto no ensaio real da Kalunga, 24/09/2026).
    """
    item = _palavras(" ".join(p for p in (especificacao.descricao, especificacao.marca, especificacao.modelo,
                                          especificacao.apresentacao) if p))
    candidato = _palavras(titulo)
    return len(item & candidato) / len(item | candidato) if item else 0.0


def titulo_do_endereco(url: str) -> str:
    """Quando o cartão não tem texto: o nome do produto costuma estar no endereço."""
    partes = [p for p in urlsplit(url).path.split("/") if p and not p.isdigit() and p not in ("p", "prod", "produto")]
    return re.sub(r"[-_]+", " ", max(partes, key=len)) if partes else ""


PARECENCA_MINIMA = 0.3  # sem a palavra do tipo do produto no título, pelo menos isto de palavras em comum
PARECENCA_COM_TIPO = 0.15  # com a palavra do tipo, ainda um mínimo (evita "Louro em folhas" para "Folha sulfite")


def palavra_do_tipo(especificacao: Especificacao) -> str | None:
    """A primeira palavra da descrição que diz o que o produto é ("Perfurador 4 furos" → perfurador)."""
    for palavra in normalizar(especificacao.descricao).replace(",", " ").split():
        if len(palavra) > 2 and palavra.isalpha() and palavra not in PALAVRAS_VAZIAS:
            return raiz(palavra)
    return None


def _primeira_palavra(titulo: str, marca: str | None) -> str | None:
    """A palavra que abre o título, sem contar a marca ("Bic Caneta Cristal" → caneta)."""
    da_marca = palavras_da_marca(marca)
    for palavra in (p.strip(".;:|()[]") for p in normalizar(titulo).replace(",", " ").split()):
        if len(palavra) > 2 and palavra.isalpha() and palavra not in PALAVRAS_VAZIAS and raiz(palavra) not in da_marca:
            return raiz(_ABREVIACOES.get(palavra, palavra))
    return None


def mesmo_tipo(especificacao: Especificacao, titulo: str, parecido: float, marca: str | None = None) -> bool:
    """O título fala do mesmo tipo de produto (evita "Louro em folhas" para "Perfurador ... 10 folhas").

    Busca de loja às vezes devolve sugestões sem relação quando não acha o produto (visto no piloto,
    24/09/2026): elas não viram candidatos. O título precisa começar pelo tipo do item ("Grampos para
    grampeador" não é um grampeador) ou ter muitas palavras em comum com ele.
    """
    tipo = palavra_do_tipo(especificacao)
    if tipo and tipo == _primeira_palavra(titulo, marca or especificacao.marca):
        return parecido >= PARECENCA_COM_TIPO
    return parecido >= PARECENCA_MINIMA


def algum_do_mesmo_tipo(especificacao: Especificacao, candidatos: list[Candidato]) -> bool:
    """A busca trouxe algum produto do tipo do item, de qualquer marca? (Sem nenhum, a busca não serve.)"""
    for c in candidatos:
        titulo = c.titulo or titulo_do_endereco(c.url)
        if mesmo_tipo(especificacao, titulo, parecenca(especificacao, titulo), c.marca):
            return True
    return False


def avaliar_candidatos(especificacao: Especificacao, candidatos: list[Candidato], vocabulario: Vocabulario,
                       limite: int = 40) -> list[CandidatoAvaliado]:
    """Os candidatos que podem ser o item, do melhor para o pior (🔴 e produtos de outro tipo ficam de fora)."""
    avaliados = []
    vistos = set()
    for c in candidatos[:limite]:
        if c.url in vistos:
            continue
        vistos.add(c.url)
        titulo = c.titulo or titulo_do_endereco(c.url)
        resultado = comparar(especificacao, Anuncio(titulo, c.marca, c.ean), vocabulario)
        status = resultado.status.value
        parecido = parecenca(especificacao, titulo)
        if status not in _ORDEM or not mesmo_tipo(especificacao, titulo, parecido, c.marca):
            continue
        avaliados.append(CandidatoAvaliado(c, status, parecido, tuple(resultado.motivos)))
    return sorted(avaliados, key=lambda a: (_ORDEM[a.status], -a.parecenca))


def termo_de_busca(especificacao: Especificacao) -> str:
    """O que digitar na busca da loja: descrição e marca, sem palavras repetidas."""
    vistas, termo = set(), []
    for palavra in " ".join(p for p in (especificacao.descricao, especificacao.marca, especificacao.modelo) if p).split():
        chave = normalizar(palavra)
        if chave and chave not in vistas:
            vistas.add(chave)
            termo.append(palavra)
    return " ".join(termo)


_MEDIDA = re.compile(r"^\d+([.,]\d+)?(g|kg|mg|ml|l|lt|mm|cm|m|un|und|fl|fls|w|v|%)?$", re.I)
_UNIDADES = {"folhas", "folha", "fl", "fls", "unidades", "unidade", "un", "und", "g", "kg", "ml", "l", "litro",
             "litros", "gramas", "metros", "m"}


def termo_curto(especificacao: Especificacao) -> str:
    """Segunda tentativa, mais aberta: sem as medidas ("75g", "500 folhas"), mas com códigos como "A4".

    As buscas longas às vezes escondem o produto (ensaio real na Kalunga, 24/09/2026).
    """
    palavras = termo_de_busca(especificacao).split()
    resultado = []
    for n, palavra in enumerate(palavras):
        depois_de_numero = n > 0 and _MEDIDA.match(palavras[n - 1]) is not None
        if _MEDIDA.match(palavra) or (depois_de_numero and normalizar(palavra) in _UNIDADES):
            continue
        resultado.append(palavra)
    return " ".join(resultado)


def termo_minimo(especificacao: Especificacao) -> str:
    """Última tentativa, para buscas que exigem todas as palavras: o tipo do produto e a marca ("Caneta Bic")."""
    tipo = next((p for p in especificacao.descricao.split()
                 if len(p) > 2 and normalizar(p).isalpha() and normalizar(p) not in PALAVRAS_VAZIAS), "")
    return " ".join(p for p in (tipo, especificacao.marca) if p)


def bom_o_bastante(avaliados: list[CandidatoAvaliado]) -> bool:
    """O primeiro candidato já é 🟢, ou um 🟡 bem parecido: não precisa buscar de novo."""
    return bool(avaliados) and (avaliados[0].status == "verde" or avaliados[0].parecenca >= 0.75)


def ordem_dos_itens(itens: list[tuple[str, bool]], cobertura: dict[str, int]) -> list[str]:
    """O item mais difícil primeiro (docs/02 §6.2): o que está em menos lojas; sem código de barras antes.

    `itens`: (id, tem código de barras). `cobertura`: em quantas lojas o item já tem preço.
    """
    return [i for i, _ in sorted(itens, key=lambda x: (cobertura.get(x[0], 0), x[1]))]
