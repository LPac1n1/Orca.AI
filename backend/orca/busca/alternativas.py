"""Saída 1 com busca (D-23; Fase 2, etapa 14): produtos de outra marca que aparecem nas lojas do trio.

A busca procura o item sem a marca nas lojas do trio. Cada candidato da loja escolhida (a de
menor total) é procurado nas outras lojas pelo título: um produto parecido (mesmas palavras,
sem contradição de atributos) conta como o mesmo. Os preços são os da **prévia** da página de
busca, sem prova: servem só para mostrar quais alternativas resolveriam (a conta é a de
sempre, `orca.selecao.trocar_produto`). A troca é decisão da pessoa, e as provas e a
correspondência que valem vêm depois, da página de cada produto (docs/04 §5.1).
"""

import re
from dataclasses import dataclass, field, replace

from orca.busca.ranking import Candidato, _palavras, avaliar_candidatos, titulo_do_endereco
from orca.correspondencia import Anuncio, Especificacao, Vocabulario, comparar
from orca.correspondencia.texto import normalizar, palavras_da_marca, palavras_significativas

PARECIDOS = 0.5  # palavras em comum entre os títulos, para ser o mesmo produto em outra loja
_MEDIDA = re.compile(r"\b(\d+(?:[.,]\d+)?)\s+(g|gr|gramas|kg|ml|l|litros?)\b")
_UNIDADE = {"gr": "g", "gramas": "g", "litro": "l", "litros": "l"}


@dataclass(frozen=True)
class ProdutoNasLojas:
    """Um produto alternativo e onde ele apareceu (loja → endereço e preço da prévia)."""

    titulo: str
    marca: str | None
    urls: dict[str, str] = field(default_factory=dict)
    precos: dict[str, int | None] = field(default_factory=dict)


def _palavras_da_marca(e: Especificacao) -> set[str]:
    return palavras_da_marca(e.marca) | palavras_da_marca(e.modelo)


def especificacao_sem_marca(e: Especificacao) -> Especificacao:
    """O item sem marca, modelo e código de barras (e sem as palavras da marca na descrição).

    Os atributos obrigatórios ficam: a alternativa tem a mesma finalidade (docs/02 §9.2).
    """
    marca = _palavras_da_marca(e)

    def da_marca(palavra: str) -> bool:
        n = normalizar(palavra)
        s = palavras_significativas(n) or ({n} if n.isdigit() else set())  # "3" de "3 Corações"
        return bool(s) and s <= marca

    descricao = " ".join(p for p in e.descricao.split() if not da_marca(p))
    return replace(e, descricao=descricao or e.descricao, marca=None, modelo=None, ean=None)


def _da_mesma_marca(candidato: Candidato, marca: set[str]) -> bool:
    if not marca:
        return False
    titulo = candidato.titulo or titulo_do_endereco(candidato.url)
    return marca <= palavras_significativas(normalizar(f"{titulo} {candidato.marca or ''}"))


def _palavras_do_titulo(titulo: str) -> set[str]:
    """Palavras do título, com as medidas juntas: "395 g" e "395 gramas" viram "395g"."""
    return _palavras(_MEDIDA.sub(lambda m: m.group(1) + _UNIDADE.get(m.group(2), m.group(2)), normalizar(titulo)))


def _mesmos_titulos(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def produtos_nas_lojas(item: Especificacao, escolhida: str, candidatos: dict[str, list[Candidato]],
                       vocabulario: Vocabulario, limite: int = 8) -> list[ProdutoNasLojas]:
    """Alternativas de outra marca achadas na loja escolhida, com o parecido de cada outra loja."""
    generico = especificacao_sem_marca(item)
    marca = _palavras_da_marca(item)
    resultado = []
    for avaliado in avaliar_candidatos(generico, candidatos.get(escolhida, []), vocabulario):
        c = avaliado.candidato
        if _da_mesma_marca(c, marca):
            continue  # o mesmo produto de antes não é alternativa
        titulo = c.titulo or titulo_do_endereco(c.url)
        produto = ProdutoNasLojas(titulo, c.marca, {escolhida: c.url}, {escolhida: c.preco_centavos})
        palavras = _palavras_do_titulo(titulo)
        # o que distingue o produto (em geral, a marca): tem que estar no título da outra loja
        distintivas = palavras - _palavras_do_titulo(generico.texto())
        referencia = Especificacao(titulo, generico.categoria, c.marca, atributos=generico.atributos)
        for loja, lista in candidatos.items():
            if loja == escolhida or not distintivas:
                continue  # sem palavra que distinga, não dá para saber se é o mesmo produto na outra loja
            parecidos = []
            for b in lista:
                titulo_b = b.titulo or titulo_do_endereco(b.url)
                palavras_b = _palavras_do_titulo(f"{titulo_b} {b.marca or ''}")
                if not distintivas <= palavras_b:
                    continue
                if comparar(referencia, Anuncio(titulo_b, b.marca, b.ean), vocabulario).status.value == "vermelho":
                    continue
                parecidos.append((_mesmos_titulos(palavras, palavras_b), b))
            nota, melhor = max(parecidos, key=lambda x: x[0], default=(0.0, None))
            if melhor is not None and nota >= PARECIDOS:
                produto.urls[loja], produto.precos[loja] = melhor.url, melhor.preco_centavos
        resultado.append(produto)
        if len(resultado) == limite:
            break
    return resultado
