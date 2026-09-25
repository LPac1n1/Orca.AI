"""É o mesmo produto? Cascata 🟢🟡🔴 sem IA (docs/02 §7; D-17).

1. Código de barras (EAN) igual → 🟢 (a menos que os atributos se contradigam: 🟡).
   Códigos diferentes nunca dão 🟢: a mesma embalagem pode ter dois códigos, mas
   quem confirma é uma pessoa.
2. Atributos críticos: marca, modelo e apresentação sempre, mais os da categoria.
   - todos iguais → 🟢 (por atributos: o perfil diz se precisa de aprovação)
   - algum ausente, ou citado só de um lado → 🟡, com o motivo
   - algum diferente → 🔴
3. Palavras que sobram de um lado só (ex.: "orgânico") → 🟡: diferença que o
   vocabulário ainda não conhece nunca vira 🟢.

Na dúvida, 🟡. Um 🟢 errado é o pior erro possível (T-11); um 🟡 a mais só custa
uma conferência humana.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from orca.correspondencia.medidas import LEITORES, Achado, Quantidade, preparar
from orca.correspondencia.texto import (
    apagar_trechos,
    compacto,
    normalizar,
    palavras_da_marca,
    palavras_significativas,
)
from orca.correspondencia.vocabulario import Vocabulario, valores_no_texto
from orca.dominio import OrigemCorrespondencia, StatusCorrespondencia, normalizar_gtin

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
VERDE, AMARELO, VERMELHO = StatusCorrespondencia.VERDE, StatusCorrespondencia.AMARELO, StatusCorrespondencia.VERMELHO

# Medidas conferidas em qualquer categoria quando aparecem (ex.: "kit 2", "Nº 103").
GERAIS = ("unidades_por_embalagem", "numero_do_modelo", "tipo_numerado")
NOMES = {
    "peso_ou_volume_liquido": "conteúdo", "volume": "volume", "capacidade": "capacidade",
    "gramatura": "gramatura", "formato": "formato", "folhas_por_pacote": "nº de folhas",
    "unidades_por_embalagem": "quantidade na embalagem", "dimensoes": "medidas", "comprimento": "comprimento",
    "concentracao": "concentração", "voltagem": "voltagem", "espessura_ponta": "ponta",
    "numero_do_modelo": "número do modelo", "tipo_numerado": "tipo (classificação)",
}


class Situacao(StrEnum):
    IGUAL = "igual"
    DIFERENTE = "diferente"
    AUSENTE = "ausente"  # o item define, a página não diz
    SO_NA_PAGINA = "so_na_pagina"  # a página diz, o item não define
    INCERTO = "incerto"  # vários valores, unidades diferentes…
    NAO_SE_APLICA = "nao_se_aplica"  # nenhum dos dois fala disso


@dataclass(frozen=True)
class Especificacao:
    """O item pedido (D-17). `atributos` traz valores escritos pelo usuário, ex.: {"sabor": "morango"}."""

    descricao: str
    categoria: str | None = None
    marca: str | None = None
    modelo: str | None = None
    apresentacao: str | None = None
    atributos: Mapping[str, str] = field(default_factory=dict)
    ean: str | None = None

    def texto(self) -> str:
        partes = [self.descricao, self.marca, self.modelo, self.apresentacao, *self.atributos.values()]
        return " ".join(p for p in partes if p)


@dataclass(frozen=True)
class Anuncio:
    """O que a página mostra."""

    titulo: str
    marca: str | None = None
    ean: str | None = None
    complemento: str = ""  # modelo, apresentação ou descrição, quando a página traz

    def texto(self) -> str:
        return " ".join(p for p in (self.titulo, self.marca, self.complemento) if p)


@dataclass(frozen=True)
class ComparacaoAtributo:
    atributo: str
    situacao: Situacao
    esperado: str | None
    encontrado: str | None
    motivo: str


@dataclass(frozen=True)
class ResultadoCorrespondencia:
    status: StatusCorrespondencia
    origem: OrigemCorrespondencia
    motivos: tuple[str, ...]
    atributos: tuple[ComparacaoAtributo, ...]


def _ean(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return normalizar_gtin(valor).zfill(14)
    except ValueError:
        return None


# --- Comparação de cada atributo --------------------------------------------------------------


def _lista(achados: list[Achado]) -> list:
    return list(dict.fromkeys(a.valor for a in achados))


def _texto(valores) -> str:
    return ", ".join(str(v) for v in valores)


def _comparar_medida(atributo: str, esperado: list, encontrado: list) -> ComparacaoAtributo:
    nome = NOMES.get(atributo, atributo)
    e, f = _texto(esperado) or None, _texto(encontrado) or None
    if not esperado and not encontrado:
        return ComparacaoAtributo(atributo, Situacao.NAO_SE_APLICA, None, None, "")
    if not encontrado:
        return ComparacaoAtributo(atributo, Situacao.AUSENTE, e, None, f"a página não informa: {nome} ({e})")
    if not esperado:
        return ComparacaoAtributo(atributo, Situacao.SO_NA_PAGINA, None, f, f"a página diz {f} ({nome}) e o item não define")
    if len(esperado) > 1:
        return ComparacaoAtributo(atributo, Situacao.INCERTO, e, f, f"o item tem mais de um valor ({nome}: {e})")
    alvo = esperado[0]
    if alvo in encontrado:
        if len(encontrado) == 1:
            return ComparacaoAtributo(atributo, Situacao.IGUAL, e, f, "")
        return ComparacaoAtributo(atributo, Situacao.INCERTO, e, f, f"a página mostra mais de um valor ({nome}: {f})")
    if isinstance(alvo, Quantidade):
        mesma_grandeza = [q for q in encontrado if q.grandeza == alvo.grandeza]
        if not mesma_grandeza:
            return ComparacaoAtributo(atributo, Situacao.INCERTO, e, f, f"{nome} em outra unidade: {e} × {f}")
        if any(q.total == alvo.total for q in mesma_grandeza):
            return ComparacaoAtributo(atributo, Situacao.INCERTO, e, f, f"mesmo total, embalagem diferente: {e} × {f}")
    return ComparacaoAtributo(atributo, Situacao.DIFERENTE, e, f, f"diferença em {nome}: {e} × {f}")


def _comparar_grupo(nome: str, esperado: frozenset, encontrado: frozenset) -> ComparacaoAtributo:
    e = ", ".join(sorted(esperado)).replace("_", " ") or None
    f = ", ".join(sorted(encontrado)).replace("_", " ") or None
    if not esperado and not encontrado:
        return ComparacaoAtributo(nome, Situacao.NAO_SE_APLICA, None, None, "")
    if not encontrado:
        return ComparacaoAtributo(nome, Situacao.AUSENTE, e, None, f"a página não diz se é {e}")
    if not esperado:
        return ComparacaoAtributo(nome, Situacao.SO_NA_PAGINA, None, f, f"a página diz “{f}” e o item não define isso")
    if esperado == encontrado:
        return ComparacaoAtributo(nome, Situacao.IGUAL, e, f, "")
    if esperado - encontrado and encontrado - esperado:  # cada lado cita um valor que o outro não tem
        so_item = ", ".join(sorted(esperado - encontrado)).replace("_", " ")
        so_pagina = ", ".join(sorted(encontrado - esperado)).replace("_", " ")
        return ComparacaoAtributo(nome, Situacao.DIFERENTE, e, f, f"variante diferente: “{so_item}” × “{so_pagina}”")
    return ComparacaoAtributo(nome, Situacao.INCERTO, e, f, f"a página cita “{f}”; o item pede “{e}”")


def _comparar_marca(marca: str | None, anuncio: Anuncio, texto_anuncio: str) -> ComparacaoAtributo:
    if not marca:
        return ComparacaoAtributo("marca", Situacao.AUSENTE, None, anuncio.marca, "o item não define a marca (D-17)")
    alvo = compacto(marca)
    if alvo and alvo in compacto(texto_anuncio):
        return ComparacaoAtributo("marca", Situacao.IGUAL, marca, anuncio.marca or marca, "")
    if anuncio.marca:
        return ComparacaoAtributo("marca", Situacao.DIFERENTE, marca, anuncio.marca, f"marca diferente: {marca} × {anuncio.marca}")
    return ComparacaoAtributo("marca", Situacao.AUSENTE, marca, None, f"a página não mostra a marca {marca}")


def _comparar_modelo(modelo: str | None, texto_anuncio: str) -> ComparacaoAtributo:
    """O modelo é conferido palavra por palavra e número por número ("Cafeteria Espresso", "BIC Cristal 1.0")."""
    if not modelo:
        return ComparacaoAtributo("modelo", Situacao.NAO_SE_APLICA, None, None, "")
    texto_modelo = normalizar(modelo)
    faltam_palavras = palavras_significativas(texto_modelo) - palavras_significativas(texto_anuncio)
    faltam_numeros = set(re.findall(r"\d+", texto_modelo)) - set(re.findall(r"\d+", texto_anuncio))
    if not faltam_palavras and not faltam_numeros:
        return ComparacaoAtributo("modelo", Situacao.IGUAL, modelo, modelo, "")
    return ComparacaoAtributo("modelo", Situacao.AUSENTE, modelo, None, f"a página não mostra o modelo “{modelo}”")


# --- Cascata ------------------------------------------------------------------------------------


def comparar(especificacao: Especificacao, anuncio: Anuncio, vocabulario: Vocabulario) -> ResultadoCorrespondencia:
    texto_item = preparar(normalizar(especificacao.texto()))
    texto_anuncio = preparar(normalizar(anuncio.texto()))
    atributos_categoria = vocabulario.atributos_da_categoria(especificacao.categoria)
    lacunas: list[str] = []
    if atributos_categoria is None:
        lacunas.append(
            f"categoria “{especificacao.categoria}” sem atributos no catálogo" if especificacao.categoria
            else "o item não tem categoria: não dá para saber os atributos críticos"
        )
        atributos_categoria = (*vocabulario.sempre, *(a for a in LEITORES if a != "gramatura"),
                               *sorted({g.atributo for g in vocabulario.grupos}))
    ativos = tuple(dict.fromkeys([*atributos_categoria, *GERAIS]))

    comparacoes: list[ComparacaoAtributo] = []
    ocupado_item: list[tuple[int, int]] = []
    ocupado_anuncio: list[tuple[int, int]] = []

    for atributo in ativos:
        if atributo in ("marca", "modelo"):
            continue
        if atributo in LEITORES:
            leitor = LEITORES[atributo]
            achados_item, achados_anuncio = leitor(texto_item), leitor(texto_anuncio)
            ocupado_item += [(a.inicio, a.fim) for a in achados_item]
            ocupado_anuncio += [(a.inicio, a.fim) for a in achados_anuncio]
            comparacoes.append(_comparar_medida(atributo, _lista(achados_item), _lista(achados_anuncio)))
            continue
        grupos = vocabulario.grupos_de(atributo)
        for grupo in grupos:
            no_item, no_anuncio = valores_no_texto(grupo, texto_item), valores_no_texto(grupo, texto_anuncio)
            ocupado_item += no_item.trechos
            ocupado_anuncio += no_anuncio.trechos
            comparacoes.append(_comparar_grupo(f"{atributo}: {grupo.nome}", no_item.valores, no_anuncio.valores))
        if not grupos and atributo != "apresentacao":
            esperado = especificacao.atributos.get(atributo)
            if esperado and palavras_significativas(normalizar(esperado)) <= palavras_significativas(texto_anuncio):
                comparacoes.append(ComparacaoAtributo(atributo, Situacao.IGUAL, esperado, esperado, ""))
            else:
                comparacoes.append(ComparacaoAtributo(
                    atributo, Situacao.INCERTO, esperado, None,
                    f"“{atributo}” precisa ser conferido por uma pessoa",
                ))

    comparacoes.insert(0, _comparar_marca(especificacao.marca, anuncio, texto_anuncio))
    comparacoes.insert(1, _comparar_modelo(especificacao.modelo, texto_anuncio))

    # Palavras que sobram de um lado só
    marca = palavras_da_marca(especificacao.marca) | palavras_da_marca(anuncio.marca)
    sobra_item, sobra_anuncio = apagar_trechos(texto_item, ocupado_item), apagar_trechos(texto_anuncio, ocupado_anuncio)
    # números que nenhuma medida reconheceu também contam ("252° graus", "23x22" sem leitor ativo)
    restantes_item = (palavras_significativas(sobra_item) | set(_NUMERO.findall(sobra_item))) - marca
    restantes_anuncio = (palavras_significativas(sobra_anuncio) | set(_NUMERO.findall(sobra_anuncio))) - marca
    so_item, so_anuncio = sorted(restantes_item - restantes_anuncio), sorted(restantes_anuncio - restantes_item)
    if so_item or so_anuncio:
        partes = []
        if so_anuncio:
            partes.append("a página tem “" + ", ".join(so_anuncio[:6]) + "”")
        if so_item:
            partes.append("o item tem “" + ", ".join(so_item[:6]) + "”")
        comparacoes.append(ComparacaoAtributo(
            "texto", Situacao.INCERTO, ", ".join(so_item) or None, ", ".join(so_anuncio) or None,
            "palavras que não batem: " + "; ".join(partes),
        ))

    diferentes = list(dict.fromkeys(c.motivo for c in comparacoes if c.situacao is Situacao.DIFERENTE))
    duvidas = lacunas + list(dict.fromkeys(
        c.motivo for c in comparacoes if c.situacao in (Situacao.AUSENTE, Situacao.SO_NA_PAGINA, Situacao.INCERTO)
    ))

    ean_item, ean_anuncio = _ean(especificacao.ean), _ean(anuncio.ean)
    if ean_item and ean_anuncio and ean_item == ean_anuncio:
        if diferentes:
            motivos = ("mesmo código de barras, mas a página contradiz o item: " + "; ".join(diferentes),)
            return ResultadoCorrespondencia(AMARELO, OrigemCorrespondencia.EAN, motivos, tuple(comparacoes))
        return ResultadoCorrespondencia(VERDE, OrigemCorrespondencia.EAN, ("mesmo código de barras",), tuple(comparacoes))
    if ean_item and ean_anuncio:
        duvidas.insert(0, "códigos de barras diferentes (pode ser outra versão da embalagem): confira")

    if diferentes:
        return ResultadoCorrespondencia(VERMELHO, OrigemCorrespondencia.ATRIBUTOS, tuple(diferentes), tuple(comparacoes))
    if duvidas:
        return ResultadoCorrespondencia(AMARELO, OrigemCorrespondencia.ATRIBUTOS, tuple(duvidas), tuple(comparacoes))
    return ResultadoCorrespondencia(
        VERDE, OrigemCorrespondencia.ATRIBUTOS, ("marca e atributos críticos iguais",), tuple(comparacoes)
    )


# --- Produto de referência (D-71) -------------------------------------------------------------


def comparar_com_referencia(
    especificacao: Especificacao, referencia: Anuncio, anuncio: Anuncio, vocabulario: Vocabulario
) -> ResultadoCorrespondencia:
    """Compara com o item e com a página que uma pessoa confirmou como o item (D-71).

    O item costuma dizer pouco ("Papel sulfite 500 folhas, Chamex"); a referência diz o resto
    (75 g, branco, o código de barras). Mesmo código de barras da referência → 🟢; atributo
    diferente do da referência → 🔴; marca e atributos iguais aos da referência → 🟢 por
    atributos. No resto, vale a comparação com o item (na dúvida, 🟡).
    """
    item = replace(especificacao, ean=especificacao.ean or referencia.ean)
    pelo_item = comparar(item, anuncio, vocabulario)
    if pelo_item.status is VERDE and pelo_item.origem is OrigemCorrespondencia.EAN and not especificacao.ean:
        return replace(pelo_item, motivos=("mesmo código de barras do produto de referência",))
    if pelo_item.status is not AMARELO:
        return pelo_item
    produto = Especificacao(
        " ".join(p for p in (referencia.titulo, referencia.complemento) if p), especificacao.categoria,
        especificacao.marca or referencia.marca, atributos=especificacao.atributos,
    )
    pela_referencia = comparar(produto, anuncio, vocabulario)
    if pela_referencia.status is VERMELHO:
        motivos = tuple(f"diferente do produto de referência: {m}" for m in pela_referencia.motivos)
        return ResultadoCorrespondencia(VERMELHO, OrigemCorrespondencia.ATRIBUTOS, motivos, pela_referencia.atributos)
    if pela_referencia.status is VERDE:
        return ResultadoCorrespondencia(VERDE, OrigemCorrespondencia.ATRIBUTOS,
                                        ("marca e atributos iguais aos do produto de referência",),
                                        pela_referencia.atributos)
    return pelo_item
