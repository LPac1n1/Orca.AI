"""Monta as partes do dossiê a partir dos resultados da seleção, do cálculo e da otimização."""

from collections.abc import Mapping, Sequence

from orca.calculo import CalculoMaoDeObra, calcular_mao_de_obra, formatar_horas
from orca.documentos.modelo import (
    AlteracaoDoc,
    CargoDoc,
    Empresa,
    EvidenciaDoc,
    FonteItem,
    LinhaCotacao,
    LojaDoLote,
    LoteDoc,
    OtimizacaoDoc,
    VagaDoc,
)
from orca.otimizacao import ProblemaTeto, SemSolucao, SolucaoTeto
from orca.selecao import AnaliseLote, Loja


def _empresa(loja: Loja, empresas: Mapping[str, Empresa]) -> Empresa:
    return empresas.get(loja.cnpj or "") or Empresa(loja.nome, loja.cnpj)


def lote_doc(
    analise: AnaliseLote,
    nome: str,
    *,
    quantidades: Mapping[str, int] | None = None,
    empresas: Mapping[str, Empresa] | None = None,
    evidencias: Mapping[tuple[str, str], EvidenciaDoc] | None = None,
    titulos: Mapping[tuple[str, str], str] | None = None,
    unidades: Mapping[str, str] | None = None,
    inicios: Mapping[str, int] | None = None,
) -> LoteDoc:
    """Lote com as quantidades finais (D-25). `evidencias`/`titulos`: (loja, item) → página."""
    quantidades, empresas = quantidades or {}, empresas or {}
    evidencias, titulos, unidades, inicios = evidencias or {}, titulos or {}, unidades or {}, inicios or {}
    base = analise.parametros.base_preco_final
    qtd = {l.item.id: quantidades.get(l.item.id, l.item.quantidade) for l in analise.linhas}

    def total(loja: Loja) -> int:
        return sum(loja.ofertas[i].preco_centavos * q for i, q in qtd.items())

    trio = [lc.loja for lc in analise.trio]
    if base == "B":  # a loja escolhida continua no Orçamento 1 (C3); as outras pela ordem do total
        ordem = [trio[0], *sorted(trio[1:], key=total)]
    else:  # Regra A: todos pela ordem do total com as quantidades finais (D-26)
        ordem = sorted(trio, key=total)
    linhas = []
    for linha in analise.linhas:
        item = linha.item
        fontes = tuple(
            FonteItem(
                loja.id,
                loja.ofertas[item.id].preco_centavos,
                evidencias.get((loja.id, item.id)),
                titulos.get((loja.id, item.id)),
            )
            for loja in ordem
        )
        linhas.append(LinhaCotacao(
            id=item.id,
            nome=item.nome,
            unidade=unidades.get(item.id, "un"),
            quantidade=qtd[item.id],
            quantidade_planejada=item.quantidade,
            meses=item.meses,
            mes_inicio=inicios.get(item.id, 1),
            fontes=fontes,
            preco_final_centavos=linha.preco_final_centavos,
            base_preco_final=base,
            comparar_com=analise.parametros.comparar_com.value,
        ))
    return LoteDoc(
        nome=nome,
        lojas=tuple(LojaDoLote(l.id, _empresa(l, empresas), total(l)) for l in ordem),
        linhas=tuple(linhas),
        base_preco_final=base,
        justificativa=analise.justificativa,
        demais_elegiveis=tuple(
            LojaDoLote(lc.loja.id, _empresa(lc.loja, empresas), total(lc.loja)) for lc in analise.demais_elegiveis
        ),
        descartadas=tuple((loja.nome, motivo) for loja, motivo in analise.descartadas),
    )


def cargo_doc(
    id: str,
    nome: str,
    regime: str,
    planejado: CalculoMaoDeObra,
    vagas: Sequence[VagaDoc],
    *,
    horas_finais_centesimos: int | None = None,
    descartadas: Sequence[tuple[str, str]] = (),
    mes_inicio: int = 1,
) -> CargoDoc:
    """Cargo com as horas finais: o cálculo é refeito para a memória mostrar os valores usados."""
    horas = horas_finais_centesimos if horas_finais_centesimos is not None else planejado.horas_mes_centesimos
    final = calcular_mao_de_obra(
        planejado.salarios, planejado.jornada_semanal_horas, horas, planejado.meses, planejado.postos,
        fator_divisor=planejado.divisor // planejado.jornada_semanal_horas,
    )
    return CargoDoc(
        id=id,
        nome=nome,
        regime=regime,
        jornada_semanal_horas=final.jornada_semanal_horas,
        divisor=final.divisor,
        vagas=tuple(vagas),
        media_centavos=final.media,
        valor_hora_centavos=final.valor_hora,
        horas_mes_centesimos=horas,
        horas_planejadas_centesimos=planejado.horas_mes_centesimos,
        valor_mensal_centavos=final.valor_mensal,
        meses=final.meses,
        postos=final.postos,
        mes_inicio=mes_inicio,
        memoria=tuple(final.memoria()),
        descartadas=tuple(descartadas),
    )


def otimizacao_doc(problema: ProblemaTeto, resultado: SolucaoTeto | SemSolucao | None) -> OtimizacaoDoc:
    if resultado is None:
        total = sum(l.preco_centavos * l.quantidade_planejada * l.meses for l in problema.materiais)
        return OtimizacaoDoc("sem_otimizacao", total)
    if isinstance(resultado, SemSolucao):
        raise ValueError(f"Sem solução para o teto: {resultado.mensagem}")
    alteracoes = tuple(
        AlteracaoDoc(
            a.nome,
            *(
                (f"{a.de} un", f"{a.para} un") if a.unidade == "un"
                else (f"{formatar_horas(a.de)} h/mês", f"{formatar_horas(a.para)} h/mês")
            ),
        )
        for a in resultado.alteracoes
    )
    return OtimizacaoDoc(
        "otima" if resultado.otima else "viavel",
        resultado.total_centavos,
        alteracoes,
        resultado.verificacao,
        resultado.versao_otimizador,
    )
