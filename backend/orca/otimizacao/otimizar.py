"""Fechar o teto exato com o OR-Tools CP-SAT (docs/03 §4).

Variáveis: quantidades (materiais) e horas por mês (mão de obra). Restrições:
C1 arredondamento do valor mensal, C2 teto exato, C3 loja escolhida continua a de
menor total, C4 classificação mantida, C5 limites por rubrica, C6 limites das linhas.
Objetivo em duas fases: (1) menos linhas alteradas (ponderadas pelo custo de
alteração); (2) menor desvio relativo. Execução determinística (1 processo, semente fixa).
"""

from collections.abc import Collection
from dataclasses import dataclass, field

import ortools
from ortools.sat.python import cp_model

from orca.otimizacao.modelo import Alteracao, LinhaMaoDeObra, LinhaMaterial, ProblemaTeto, SemSolucao, SolucaoTeto
from orca.otimizacao.verificacao import verificar

VERSAO_OTIMIZADOR = f"ortools-{ortools.__version__}"
_ESCALA_DESVIO = 1_000_000


@dataclass
class _Modelo:
    cp: cp_model.CpModel
    q: dict[str, cp_model.IntVar] = field(default_factory=dict)
    h: dict[str, cp_model.IntVar] = field(default_factory=dict)
    v: dict[str, cp_model.IntVar] = field(default_factory=dict)
    total_linha: dict[str, cp_model.LinearExprT] = field(default_factory=dict)
    grupos: dict[str, cp_model.IntVar] = field(default_factory=dict)  # nome do grupo → literal


def _dominio_material(l: LinhaMaterial, amplo: bool) -> tuple[int, int]:
    if not amplo:
        return l.qtd_min, l.qtd_max
    return 0, max(l.qtd_max * 10, l.qtd_max + 1000, l.quantidade_planejada * 10 + 1000)


def construir(
    p: ProblemaTeto,
    *,
    com_grupos: bool = False,
    relaxar: Collection[str] = frozenset(),
) -> _Modelo:
    """Monta o modelo. Com `com_grupos`, cada grupo de restrições relaxáveis fica ligado a um
    literal (para achar conflitos); grupos em `relaxar` ficam de fora."""
    mod = _Modelo(cp_model.CpModel())
    cp = mod.cp
    amplo = com_grupos or bool(relaxar)

    def grupo(nome: str):
        """Literal que liga o grupo (ou None quando a restrição é sempre aplicada)."""
        if not com_grupos:
            return None
        literal = cp.new_bool_var(nome)
        mod.grupos[nome] = literal
        return literal

    def aplicar(restricao, literal):
        if literal is not None:
            restricao.only_enforce_if(literal)

    for l in p.materiais:
        minimo, maximo = _dominio_material(l, amplo)
        q = cp.new_int_var(minimo, maximo, f"q_{l.id}")
        mod.q[l.id] = q
        mod.total_linha[l.id] = q * (l.preco_centavos * l.meses)
        nome = f"margem:{l.id}"
        if amplo and nome not in relaxar:
            literal = grupo(nome)
            aplicar(cp.add(q >= l.qtd_min), literal)
            aplicar(cp.add(q <= l.qtd_max), literal)

    for l in p.mao_de_obra:
        minimo, maximo = (1, l.horas_legais_centesimos) if amplo else (l.horas_min_centesimos, l.horas_max_centesimos)
        h = cp.new_int_var(minimo, maximo, f"h_{l.id}")
        v_min = (l.valor_hora_centavos * minimo + 50) // 100
        v_max = (l.valor_hora_centavos * maximo + 50) // 100
        v = cp.new_int_var(v_min, v_max, f"v_{l.id}")
        # C1: V = ⌊(valor_hora·H + 50) / 100⌋  (arredondamento comercial, D-43)
        cp.add(100 * v <= l.valor_hora_centavos * h + 50)
        cp.add(l.valor_hora_centavos * h + 50 <= 100 * v + 99)
        mod.h[l.id], mod.v[l.id] = h, v
        mod.total_linha[l.id] = v * (l.meses * l.postos)
        nome = f"margem:{l.id}"
        if amplo and nome not in relaxar:
            literal = grupo(nome)
            aplicar(cp.add(h >= l.horas_min_centesimos), literal)
            aplicar(cp.add(h <= l.horas_max_centesimos), literal)

    # C2: teto exato
    cp.add(sum(mod.total_linha.values()) + p.fixos_centavos == p.teto_centavos)

    meses = {l.id: l.meses for l in p.materiais}
    for lote in p.lotes:
        def total(loja: str, lote=lote):
            return sum(mod.q[linha] * (preco * meses[linha]) for linha, preco in lote.precos[loja].items())

        nome = f"escolhida:{lote.lote}"
        if lote.manter_escolhida and nome not in relaxar:  # C3
            literal = grupo(nome)
            for outra in lote.outras_do_trio:
                aplicar(cp.add(total(lote.escolhida) <= total(outra)), literal)
        nome = f"classificacao:{lote.lote}"
        if lote.manter_classificacao and lote.fora_do_trio and nome not in relaxar:  # C4
            literal = grupo(nome)
            referencia = lote.outras_do_trio or (lote.escolhida,)
            for fora in lote.fora_do_trio:
                for dentro in referencia:
                    aplicar(cp.add(total(fora) >= total(dentro)), literal)

    for limite in p.limites:  # C5
        nome = f"limite:{limite.orcamento}"
        if nome in relaxar:
            continue
        linhas = [l.id for l in (*p.materiais, *p.mao_de_obra) if l.orcamento == limite.orcamento]
        soma = sum(mod.total_linha[i] for i in linhas)
        literal = grupo(nome)
        if limite.min_centavos is not None:
            aplicar(cp.add(soma >= limite.min_centavos), literal)
        if limite.max_centavos is not None:
            aplicar(cp.add(soma <= limite.max_centavos), literal)
    return mod


def novo_resolvedor(tempo_limite_s: float) -> cp_model.CpSolver:
    resolvedor = cp_model.CpSolver()
    resolvedor.parameters.num_workers = 1  # determinístico
    resolvedor.parameters.random_seed = 0
    resolvedor.parameters.max_time_in_seconds = tempo_limite_s
    return resolvedor


def _linhas(p: ProblemaTeto) -> list[tuple[str, int, int, bool, int, int]]:
    """(id, valor planejado, custo, é_mão_de_obra, mínimo, máximo) de cada linha."""
    return [
        (l.id, l.quantidade_planejada, l.custo_alteracao, False, l.qtd_min, l.qtd_max) for l in p.materiais
    ] + [
        (l.id, l.horas_planejadas_centesimos, l.custo_alteracao, True, l.horas_min_centesimos, l.horas_max_centesimos)
        for l in p.mao_de_obra
    ]


def _var(mod: _Modelo, linha: str) -> cp_model.IntVar:
    return mod.q[linha] if linha in mod.q else mod.h[linha]


def fechar_teto(p: ProblemaTeto, tempo_limite_s: float = 20.0) -> SolucaoTeto | SemSolucao:
    """Encontra quantidades e horas que somam exatamente o teto, mexendo o mínimo possível."""
    from orca.otimizacao.diagnostico import diagnosticar

    mod = construir(p)
    cp = mod.cp
    linhas = _linhas(p)
    alterada, desvio = {}, {}
    for linha, planejado, _custo, _mao, minimo, maximo in linhas:
        var = _var(mod, linha)
        alterada[linha] = cp.new_bool_var(f"alterada_{linha}")
        cp.add(var == planejado).only_enforce_if(~alterada[linha])
        desvio[linha] = cp.new_int_var(0, max(abs(maximo - planejado), abs(planejado - minimo)), f"desvio_{linha}")
        cp.add_abs_equality(desvio[linha], var - planejado)
    custo_total = sum(alterada[l] * c for l, _p, c, *_ in linhas)

    resolvedor = novo_resolvedor(tempo_limite_s)
    cp.minimize(custo_total)
    status1 = resolvedor.solve(cp)
    if status1 == cp_model.INFEASIBLE:
        return diagnosticar(p, tempo_limite_s)
    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SemSolucao(
            "tempo",
            f"O tempo de {tempo_limite_s:g} s acabou antes de encontrar uma solução. Tente de novo com mais tempo.",
        )
    melhor = round(resolvedor.objective_value)
    valores1 = {l: resolvedor.value(_var(mod, l)) for l, *_ in linhas}

    # Fase 2: mantendo o mínimo de alterações, o menor desvio relativo.
    cp.clear_objective()
    cp.add(custo_total <= melhor)
    for linha, valor in valores1.items():
        cp.add_hint(_var(mod, linha), valor)
    cp.minimize(sum(desvio[l] * (_ESCALA_DESVIO // max(p0, 1)) for l, p0, *_ in linhas))
    status2 = resolvedor.solve(cp)
    if status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        valores = {l: resolvedor.value(_var(mod, l)) for l, *_ in linhas}
    else:
        valores = valores1
    otima = status1 == cp_model.OPTIMAL and status2 == cp_model.OPTIMAL

    quantidades = {l.id: valores[l.id] for l in p.materiais}
    horas = {l.id: valores[l.id] for l in p.mao_de_obra}
    resultado = verificar(p, quantidades, horas)
    nomes = {l.id: l.nome for l in (*p.materiais, *p.mao_de_obra)}
    alteracoes = tuple(
        Alteracao(l, nomes[l], planejado, valores[l], "h" if mao else "un")
        for l, planejado, _c, mao, *_ in linhas
        if valores[l] != planejado
    )
    return SolucaoTeto(
        otima=otima,
        quantidades=quantidades,
        horas_centesimos=horas,
        valores_mensais=resultado.valores_mensais,
        totais=resultado.totais,
        total_centavos=resultado.total_centavos,
        alteracoes=alteracoes,
        verificacao=tuple(resultado.problemas),
        versao_otimizador=VERSAO_OTIMIZADOR,
    )
