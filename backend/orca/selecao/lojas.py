"""Cobertura, classificação, trio e conferência preço × média (docs/02 §8–§9)."""

from collections.abc import Collection, Sequence

from orca.calculo import Cotacao, formatar, formatar_exato
from orca.dominio import cnpj_raiz
from orca.selecao.modelos import (
    AnaliseLote,
    ItemLote,
    LinhaGrade,
    Loja,
    LojaClassificada,
    ParametrosSelecao,
    SemTrio,
    Violacao,
)


def _validar_entrada(itens: Sequence[ItemLote], lojas: Sequence[Loja]) -> None:
    if not itens:
        raise ValueError("O lote precisa de ao menos um item")
    for nome, ids in (("itens", [i.id for i in itens]), ("lojas", [l.id for l in lojas])):
        if len(set(ids)) != len(ids):
            raise ValueError(f"Há {nome} repetidos no lote")
    for item in itens:
        if item.quantidade < 0 or item.meses < 1:
            raise ValueError(f"Quantidade ou meses inválidos em {item.nome!r}")


def _motivo_cnpj(loja: Loja, p: ParametrosSelecao) -> str | None:
    if p.exige_cnpj and not loja.cnpj:
        return "sem CNPJ do vendedor identificado (D-16)"
    if p.cnpj_ativo_obrigatorio and loja.cnpj and not loja.cnpj_ativo:
        return "CNPJ não está ativo"
    return None


def motivos_inelegivel(loja: Loja, itens: Sequence[ItemLote], p: ParametrosSelecao) -> list[str]:
    """Por que a loja não pode entrar no trio (lista vazia = elegível)."""
    motivos = []
    if (motivo := _motivo_cnpj(loja, p)) is not None:
        motivos.append(motivo)
    faltando = [i.nome for i in itens if i.id not in loja.ofertas]
    diferentes = [i.nome for i in itens if i.id in loja.ofertas and not loja.ofertas[i.id].verde]
    sem_evidencia = [
        i.nome
        for i in itens
        if i.id in loja.ofertas and loja.ofertas[i.id].verde and not loja.ofertas[i.id].evidencia_valida
    ]
    if faltando:
        motivos.append("não tem: " + ", ".join(faltando))
    if diferentes:
        motivos.append("produto não confirmado como idêntico: " + ", ".join(diferentes))
    if sem_evidencia:
        motivos.append("evidência inválida: " + ", ".join(sem_evidencia))
    return motivos


def total_da_loja(loja: Loja, itens: Sequence[ItemLote]) -> int:
    """Total do lote na loja com as quantidades planejadas × meses (P-05)."""
    return sum(loja.ofertas[i.id].preco_centavos * i.quantidade_total for i in itens)


def _chave(lc: LojaClassificada) -> tuple:
    # Menor total primeiro; desempate: melhor evidência, depois nome (docs/02 §8).
    return (lc.total_centavos, -lc.loja.qualidade_evidencia, lc.loja.nome, lc.loja.id)


def classificar(
    itens: Sequence[ItemLote], lojas: Sequence[Loja], p: ParametrosSelecao
) -> tuple[list[LojaClassificada], list[tuple[Loja, str]]]:
    """Lojas elegíveis em ordem de total, e as descartadas com o motivo."""
    elegiveis, descartadas = [], []
    for loja in lojas:
        motivos = motivos_inelegivel(loja, itens, p)
        if motivos:
            descartadas.append((loja, "; ".join(motivos)))
        else:
            elegiveis.append(LojaClassificada(loja, total_da_loja(loja, itens)))
    return sorted(elegiveis, key=_chave), descartadas


def _montar_trio(
    classificacao: Sequence[LojaClassificada], p: ParametrosSelecao, excluir: Collection[str]
) -> tuple[list[LojaClassificada], list[tuple[Loja, str]]]:
    trio: list[LojaClassificada] = []
    puladas: list[tuple[Loja, str]] = []
    empresas: dict[str, str] = {}
    for lc in classificacao:
        if lc.loja.id in excluir:
            continue
        raiz = cnpj_raiz(lc.loja.cnpj) if lc.loja.cnpj else None
        if p.cnpjs_distintos and raiz is not None and raiz in empresas:
            puladas.append((lc.loja, f"mesma empresa (CNPJ) de {empresas[raiz]} (P-03)"))
            continue
        trio.append(lc)
        if raiz is not None:
            empresas[raiz] = lc.loja.nome
        if len(trio) == p.fontes_por_cotacao:
            break
    return trio, puladas


def _justificativa(trio: Sequence[LojaClassificada], n_itens: int, n_completas: int) -> str:
    escolhida = trio[0]
    outras = ", ".join(f"{lc.loja.nome} ({formatar(lc.total_centavos)})" for lc in trio[1:])
    return (
        f"{escolhida.loja.nome} escolhida para o Orçamento 1: possui os {n_itens} itens e teve o menor "
        f"total ({formatar(escolhida.total_centavos)}) entre as {n_completas} lojas completas. "
        f"Orçamentos 2 e 3: {outras}."
    )


def _sem_trio(
    itens: Sequence[ItemLote],
    lojas: Sequence[Loja],
    p: ParametrosSelecao,
    completas: Sequence[LojaClassificada],
    descartadas: list[tuple[Loja, str]],
    excluir: Collection[str],
) -> SemTrio:
    n = p.fontes_por_cotacao
    validas = [l for l in lojas if l.id not in excluir and _motivo_cnpj(l, p) is None]
    cobertura = [
        (item, sum(1 for l in validas if (o := l.ofertas.get(item.id)) is not None and o.utilizavel))
        for item in itens
    ]
    bloqueadores = sorted(((i, c) for i, c in cobertura if c < n), key=lambda x: (x[1], x[0].nome))
    lojas_completas = tuple(lc.loja for lc in completas if lc.loja.id not in excluir)
    if bloqueadores:
        lista = ", ".join(f"{i.nome} (em {c} {'loja' if c == 1 else 'lojas'})" for i, c in bloqueadores)
        mensagem = f"Não há {n} lojas com todos os itens. Itens que impedem: {lista}."
    elif len(lojas_completas) >= n:
        mensagem = f"Há {len(lojas_completas)} lojas completas, mas não {n} empresas diferentes (P-03)."
    else:
        menos = sorted(cobertura, key=lambda x: (x[1], x[0].nome))[:3]
        lista = ", ".join(f"{i.nome} (em {c} lojas)" for i, c in menos)
        mensagem = (
            f"Cada item existe em ao menos {n} lojas, mas nenhum grupo de {n} lojas tem todos os itens juntos. "
            f"Itens com menor cobertura: {lista}."
        )
    sugestoes = ["pesquisar mais lojas", "trocar o produto por um alternativo equivalente (com aprovação)"]
    if p.lotes_permitidos and bloqueadores:
        sugestoes.append("criar um lote separado para o item, com o seu próprio trio")
    return SemTrio(
        necessarias=n,
        completas=lojas_completas,
        bloqueadores=tuple(bloqueadores),
        descartadas=tuple(descartadas),
        mensagem=mensagem,
        sugestoes=tuple(sugestoes),
    )


def analisar_lote(
    itens: Sequence[ItemLote],
    lojas: Sequence[Loja],
    p: ParametrosSelecao,
    excluir: Collection[str] = frozenset(),
) -> AnaliseLote | SemTrio:
    """Escolhe o trio, monta a grade e confere preço × média. `excluir` = lojas já retiradas (Saída 2)."""
    _validar_entrada(itens, lojas)
    classificacao, descartadas = classificar(itens, lojas, p)
    trio, puladas = _montar_trio(classificacao, p, excluir)
    descartadas = descartadas + puladas
    if len(trio) < p.fontes_por_cotacao:
        return _sem_trio(itens, lojas, p, classificacao, descartadas, excluir)

    regra_b = p.base_preco_final == "B"
    escolhida = trio[0].loja
    linhas, violacoes = [], []
    for item in itens:
        precos = tuple(lc.loja.ofertas[item.id].preco_centavos for lc in trio)
        cotacao = Cotacao(precos)
        dentro = cotacao.dentro_da_media(precos[0], p.comparar_com) if regra_b else None
        linhas.append(
            LinhaGrade(
                item=item,
                precos=precos,
                totais=cotacao.totais(item.quantidade),
                cotacao=cotacao,
                media_total_centavos=cotacao.media_dos_totais(item.quantidade),
                preco_final_centavos=precos[0] if regra_b else cotacao.preco_regra_a(),
                dentro_da_media=dentro,
            )
        )
        if dentro is False:
            violacoes.append(
                Violacao(
                    item=item,
                    loja=escolhida,
                    preco_centavos=precos[0],
                    cotacao=cotacao,
                    mensagem=(
                        f"{item.nome}: {formatar(precos[0])} na loja {escolhida.nome} passa da média "
                        f"{formatar_exato(cotacao.media_exata)}"
                    ),
                )
            )
    n_completas = len([lc for lc in classificacao if lc.loja.id not in excluir])
    return AnaliseLote(
        trio=tuple(trio),
        linhas=tuple(linhas),
        violacoes=tuple(violacoes),
        descartadas=tuple(descartadas),
        justificativa=_justificativa(trio, len(itens), n_completas),
        parametros=p,
    )
