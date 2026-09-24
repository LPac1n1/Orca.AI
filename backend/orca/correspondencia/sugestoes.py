"""Sugestões para o vocabulário a partir dos pares rotulados (D-65; Fase 2, etapa 13). Sem rede nem disco.

Quando uma pessoa diz que dois produtos são **diferentes** e o sistema ainda os acha
parecidos, a palavra que sobra de cada lado (ex.: "neutro" × "limão") vira a sugestão
de valores que se excluem. Quando ela diz que são **o mesmo** e o sistema tinha dúvida,
e uma das palavras já é um valor do vocabulário, a outra vira sinônimo dela.

Só casos claros (uma palavra de cada lado). Nenhuma sugestão é aplicada sozinha: a pessoa
confere o teste de correspondência (todos os pares) e aprova.
"""

import re
from dataclasses import dataclass

from orca.correspondencia.avaliacao import Par
from orca.correspondencia.comparar import Anuncio, Especificacao, Situacao, comparar
from orca.correspondencia.medidas import LEITORES
from orca.correspondencia.texto import PALAVRAS_VAZIAS, normalizar, palavras, raiz
from orca.correspondencia.vocabulario import Grupo, Vocabulario

_ACERTOS = {("diferente", "vermelho"), ("mesmo", "verde")}


@dataclass(frozen=True)
class Sugestao:
    tipo: str  # valor_exclusivo | grupo_novo | sinonimo | atributo_na_categoria
    explicacao: str
    mudancas: dict  # a acrescentar ao catálogo de atributos da OSC (mesmo formato da camada)


def _chave(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalizar(texto)).strip("_")


def _originais(raizes: str | None, titulo: str) -> list[str]:
    """As palavras do título cuja raiz está entre as que sobraram na comparação."""
    if not raizes:
        return []
    alvo = {r.strip() for r in raizes.split(",")}
    return list(dict.fromkeys(p for p in palavras(normalizar(titulo))
                              if raiz(p) in alvo and p not in PALAVRAS_VAZIAS and len(p) > 1))


def _grupo_com(vocabulario: Vocabulario, palavra: str) -> tuple[Grupo, str] | None:
    alvo = raiz(normalizar(palavra))
    for grupo in vocabulario.grupos:
        for valor, sinonimos in grupo.valores.items():
            if any(" " not in s and raiz(s) == alvo for s in sinonimos):
                return grupo, valor
    return None


def _atributo_de_texto(vocabulario: Vocabulario, categoria: str | None) -> str:
    """O atributo de texto da categoria (ex.: fragrância, sabor); "tipo" se não houver."""
    atributos = vocabulario.categorias.get(_chave(categoria or ""), ())
    com_vocabulario = {g.atributo for g in vocabulario.grupos}
    for atributo in atributos:
        if atributo not in LEITORES and atributo in com_vocabulario and atributo != "apresentacao":
            return atributo
    return "tipo"


def sugerir(par: Par, vocabulario: Vocabulario) -> list[Sugestao]:
    """Sugestões que ensinariam o sistema a acertar este par (vazio se ele já acerta ou o caso não é claro)."""
    resultado = comparar(Especificacao(par.titulo_a, par.categoria, par.marca_a), Anuncio(par.titulo_b, par.marca_b),
                         vocabulario)
    if (par.rotulo, resultado.status.value) in _ACERTOS:
        return []
    sobra = next((c for c in resultado.atributos if c.atributo == "texto"), None)
    do_item = _originais(sobra.esperado, par.titulo_a) if sobra else []
    da_pagina = _originais(sobra.encontrado, par.titulo_b) if sobra else []

    # Um lado cita um valor conhecido ("moído") e o outro, uma palavra que o vocabulário não conhece ("pilado")
    for c in resultado.atributos:
        if ":" not in c.atributo or c.situacao not in (Situacao.AUSENTE, Situacao.SO_NA_PAGINA):
            continue
        atributo, nome_grupo = (p.strip() for p in c.atributo.split(":", 1))
        grupo = next((g for g in vocabulario.grupos if g.atributo == atributo and g.nome == nome_grupo), None)
        if c.situacao is Situacao.AUSENTE and len(da_pagina) == 1 and not do_item:
            valor, nova = c.esperado, da_pagina[0]
        elif c.situacao is Situacao.SO_NA_PAGINA and len(do_item) == 1 and not da_pagina:
            valor, nova = c.encontrado, do_item[0]
        else:
            continue
        chave_valor = (valor or "").replace(" ", "_")
        if grupo is None or "," in (valor or "") or chave_valor not in grupo.valores or _grupo_com(vocabulario, nova):
            continue
        rotulo_grupo = grupo.nome.replace("_", " ")
        if par.rotulo == "diferente":
            return [Sugestao(
                "valor_exclusivo", f"“{nova}” é outro valor de “{rotulo_grupo}” ({atributo}), diferente de “{valor}”",
                {"vocabulario": {atributo: {grupo.nome: {_chave(nova): [nova]}}}},
            )]
        return [Sugestao(
            "sinonimo", f"“{nova}” quer dizer o mesmo que “{valor}” ({rotulo_grupo})",
            {"vocabulario": {atributo: {grupo.nome: {chave_valor: [*grupo.valores[chave_valor], nova]}}}},
        )]

    if len(do_item) != 1 or len(da_pagina) != 1:
        return []
    a, b = do_item[0], da_pagina[0]
    conhecidas = [(conhecida, nova, _grupo_com(vocabulario, conhecida)) for conhecida, nova in ((a, b), (b, a))]

    if par.rotulo == "diferente":
        for _, nova, achado in conhecidas:
            if achado and not _grupo_com(vocabulario, nova):
                grupo, valor = achado
                return [Sugestao(
                    "valor_exclusivo",
                    f"“{nova}” é outro valor de “{grupo.nome.replace('_', ' ')}” ({grupo.atributo}), diferente de “{valor}”",
                    {"vocabulario": {grupo.atributo: {grupo.nome: {_chave(nova): [nova]}}}},
                )]
        (_, _, g_a), (_, _, g_b) = conhecidas
        categoria = _chave(par.categoria or "")
        if g_a and g_b and g_a[0] is g_b[0] and categoria in vocabulario.categorias \
                and g_a[0].atributo not in vocabulario.categorias[categoria]:
            atributo = g_a[0].atributo  # ex.: as duas são cores, mas a categoria não confere a cor
            return [Sugestao(
                "atributo_na_categoria",
                f"a categoria “{categoria.replace('_', ' ')}” passa a conferir “{atributo}” (“{a}” × “{b}”)",
                {"categorias": {categoria: [*vocabulario.categorias[categoria], atributo]}},
            )]
        if g_a or g_b:
            return []  # as duas já estão no vocabulário: o motivo é outro
        atributo = _atributo_de_texto(vocabulario, par.categoria)
        mudancas: dict = {"vocabulario": {atributo: {f"{_chave(a)}_ou_{_chave(b)}": {_chave(a): [a], _chave(b): [b]}}}}
        if categoria in vocabulario.categorias and atributo not in vocabulario.categorias[categoria]:
            mudancas["categorias"] = {categoria: [*vocabulario.categorias[categoria], atributo]}
        return [Sugestao("grupo_novo", f"“{a}” e “{b}” são valores que se excluem (grupo novo em “{atributo}”)", mudancas)]

    for conhecida, nova, achado in conhecidas:
        if achado and not _grupo_com(vocabulario, nova):
            grupo, valor = achado
            return [Sugestao(
                "sinonimo",
                f"“{nova}” quer dizer o mesmo que “{valor.replace('_', ' ')}” ({grupo.nome.replace('_', ' ')})",
                {"vocabulario": {grupo.atributo: {grupo.nome: {valor: [*grupo.valores[valor], nova]}}}},
            )]
    return []
