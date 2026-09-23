"""Monta o problema do teto a partir das regras, da seleção de lojas e do cálculo de mão de obra."""

from collections.abc import Collection, Mapping

from orca.calculo import CalculoMaoDeObra
from orca.otimizacao.modelo import LimiteRubrica, LinhaMaoDeObra, LinhaMaterial, RestricaoLote, faixa
from orca.regras import PerfilRegras
from orca.selecao import AnaliseLote


def linhas_do_lote(
    analise: AnaliseLote,
    regras: PerfilRegras,
    orcamento: str,
    lote: str,
    *,
    margens: Mapping[str, tuple[int, int]] | None = None,
    travados: Collection[str] = (),
    custos: Mapping[str, int] | None = None,
) -> tuple[list[LinhaMaterial], RestricaoLote | None]:
    """Linhas de material do lote (preço final da seleção) e, na Regra B, as restrições C3/C4."""
    margens, custos = margens or {}, custos or {}
    padrao = regras.otimizacao.margem_quantidade
    linhas = []
    for linha in analise.linhas:
        item = linha.item
        minimo_pct, maximo_pct = margens.get(item.id, (padrao.min_percentual, padrao.max_percentual))
        qmin, qmax = faixa(item.quantidade, minimo_pct, maximo_pct, item.id in travados)
        linhas.append(
            LinhaMaterial(
                id=item.id,
                nome=item.nome,
                orcamento=orcamento,
                preco_centavos=linha.preco_final_centavos,
                quantidade_planejada=item.quantidade,
                meses=item.meses,
                qtd_min=qmin,
                qtd_max=qmax,
                custo_alteracao=custos.get(item.id, 1),
            )
        )
    if analise.parametros.base_preco_final != "B":
        return linhas, None  # Regra A: o preço é a média; a ordem dos orçamentos se ajusta depois
    lojas = [lc.loja for lc in (*analise.trio, *analise.demais_elegiveis)]
    restricao = RestricaoLote(
        lote=lote,
        escolhida=analise.trio[0].loja.id,
        outras_do_trio=tuple(lc.loja.id for lc in analise.trio[1:]),
        fora_do_trio=tuple(lc.loja.id for lc in analise.demais_elegiveis),
        precos={l.id: {i.item.id: l.ofertas[i.item.id].preco_centavos for i in analise.linhas} for l in lojas},
        manter_escolhida=regras.otimizacao.manter_loja_escolhida_menor_total,
        manter_classificacao=regras.otimizacao.manter_classificacao,
    )
    return linhas, restricao


def linha_de_cargo(
    id: str,
    nome: str,
    orcamento: str,
    calculo: CalculoMaoDeObra,
    regras: PerfilRegras,
    *,
    margem: tuple[int, int] | None = None,
    travado: bool = False,
    custo: int = 1,
) -> LinhaMaoDeObra:
    """Linha de mão de obra a partir do cálculo da cotação (valor-hora já arredondado, D-43)."""
    padrao = regras.otimizacao.margem_horas
    minimo_pct, maximo_pct = margem or (padrao.min_percentual, padrao.max_percentual)
    legais = calculo.divisor * 100
    hmin, hmax = faixa(calculo.horas_mes_centesimos, minimo_pct, maximo_pct, travado)
    return LinhaMaoDeObra(
        id=id,
        nome=nome,
        orcamento=orcamento,
        valor_hora_centavos=calculo.valor_hora,
        horas_planejadas_centesimos=calculo.horas_mes_centesimos,
        meses=calculo.meses,
        postos=calculo.postos,
        horas_min_centesimos=max(1, min(hmin, legais)),
        horas_max_centesimos=min(hmax, legais),
        horas_legais_centesimos=legais,
        custo_alteracao=custo,
    )


def limites_das_regras(regras: PerfilRegras, teto_centavos: int, ids_por_nome: Mapping[str, str]) -> list[LimiteRubrica]:
    """Converte `teto.limites_por_orcamento` (por nome da rubrica) em limites em centavos."""
    limites = []
    for nome, limite in regras.teto.limites_por_orcamento.items():
        if nome not in ids_por_nome:
            raise ValueError(f"As regras citam a rubrica {nome!r}, que não existe no projeto")
        minimos = [v for v in (limite.min_centavos,) if v is not None]
        maximos = [v for v in (limite.max_centavos,) if v is not None]
        if limite.min_percentual is not None:
            minimos.append(-((-teto_centavos * limite.min_percentual) // 100))
        if limite.max_percentual is not None:
            maximos.append((teto_centavos * limite.max_percentual) // 100)
        limites.append(
            LimiteRubrica(
                orcamento=ids_por_nome[nome],
                min_centavos=max(minimos) if minimos else None,
                max_centavos=min(maximos) if maximos else None,
            )
        )
    return limites
