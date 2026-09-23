"""Quando não há solução: por quê e qual a menor mudança que resolve (docs/03 §4.5).

1. Limites: mesmo tudo no máximo (ou no mínimo) não chega ao teto.
2. Divisibilidade: as linhas ajustáveis só mudam o total em múltiplos de um valor
   que não divide o que falta (só quando não há mão de obra ajustável).
3. Conflito: quais grupos de restrições, juntos, impedem a solução (núcleo de
   inviabilidade do CP-SAT).
Sugestões: o modelo é resolvido de novo relaxando um grupo por vez, e o sistema
informa o tamanho da mudança necessária. Preços nunca são alterados.
"""

from fractions import Fraction
from math import gcd

from ortools.sat.python import cp_model

from orca.calculo import arredondar_centavos, formatar, formatar_horas
from orca.otimizacao.modelo import ProblemaTeto, SemSolucao, Sugestao
from orca.otimizacao.otimizar import construir, novo_resolvedor


def _mensal(valor_hora: int, horas: int) -> int:
    return arredondar_centavos(Fraction(valor_hora * horas, 100))


def _extremos(p: ProblemaTeto) -> tuple[int, int]:
    minimo = p.fixos_centavos + sum(l.preco_centavos * l.meses * l.qtd_min for l in p.materiais)
    maximo = p.fixos_centavos + sum(l.preco_centavos * l.meses * l.qtd_max for l in p.materiais)
    for l in p.mao_de_obra:
        minimo += _mensal(l.valor_hora_centavos, l.horas_min_centesimos) * l.meses * l.postos
        maximo += _mensal(l.valor_hora_centavos, l.horas_max_centesimos) * l.meses * l.postos
    return minimo, maximo


def _divisibilidade(p: ProblemaTeto) -> str | None:
    if any(l.horas_min_centesimos < l.horas_max_centesimos for l in p.mao_de_obra):
        return None  # horas decimais dão passos pequenos; não se aplica
    minimo, _ = _extremos(p)
    passos = [l.preco_centavos * l.meses for l in p.materiais if l.qtd_min < l.qtd_max]
    g = 0
    for passo in passos:
        g = gcd(g, passo)
    falta = p.teto_centavos - minimo
    if g > 1 and falta % g != 0:
        return (
            f"As linhas ajustáveis só mudam o total em múltiplos de {formatar(g)}; "
            f"do mínimo até o teto faltam {formatar(falta)}, que não é múltiplo de {formatar(g)}."
        )
    return None


def _nucleo(p: ProblemaTeto, tempo: float) -> list[str]:
    mod = construir(p, com_grupos=True)
    nomes = list(mod.grupos)
    mod.cp.add_assumptions([mod.grupos[n] for n in nomes])
    resolvedor = novo_resolvedor(tempo)
    if resolvedor.solve(mod.cp) != cp_model.INFEASIBLE:
        return []
    indices = set(resolvedor.sufficient_assumptions_for_infeasibility())
    return [n for n in nomes if mod.grupos[n].index in indices]


def _nome_do_grupo(p: ProblemaTeto, grupo: str) -> str:
    tipo, alvo = grupo.split(":", 1)
    nomes = {l.id: l.nome for l in (*p.materiais, *p.mao_de_obra)}
    return {
        "margem": f"limites de {nomes.get(alvo, alvo)}",
        "escolhida": f"loja escolhida continua a mais barata no lote {alvo} (C3)",
        "classificacao": f"classificação das lojas mantida no lote {alvo} (C4)",
        "limite": f"limite da rubrica {alvo}",
    }[tipo]


def _sugestao_margem(p: ProblemaTeto, linha_id: str, tempo: float) -> Sugestao | None:
    """Resolve sem os limites da linha, com o menor excesso possível; diz quanto seria preciso."""
    mod = construir(p, relaxar={f"margem:{linha_id}"})
    material = next((l for l in p.materiais if l.id == linha_id), None)
    if material is not None:
        var, minimo, maximo, planejado = mod.q[linha_id], material.qtd_min, material.qtd_max, material.quantidade_planejada
    else:
        l = next(l for l in p.mao_de_obra if l.id == linha_id)
        var, minimo, maximo, planejado = mod.h[linha_id], l.horas_min_centesimos, l.horas_max_centesimos, l.horas_planejadas_centesimos
    acima = mod.cp.new_int_var(0, 10**12, "acima")
    abaixo = mod.cp.new_int_var(0, 10**12, "abaixo")
    mod.cp.add(acima >= var - maximo)
    mod.cp.add(abaixo >= minimo - var)
    mod.cp.minimize(acima + abaixo)
    resolvedor = novo_resolvedor(tempo)
    if resolvedor.solve(mod.cp) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    valor = resolvedor.value(var)
    variacao = (valor - planejado) / planejado * 100 if planejado else 0.0
    if material is not None:
        mensagem = (
            f"{material.nome}: permitir {valor} por período (limite atual {minimo}–{maximo}; "
            f"{variacao:+.0f}% sobre o planejado {planejado})"
        )
        excesso = max(valor - maximo, minimo - valor, 0) / max(planejado, 1)
    else:
        mensagem = (
            f"{l.nome}: permitir {formatar_horas(valor)} por mês (limite atual "
            f"{formatar_horas(minimo)[:-2]}–{formatar_horas(maximo)}; "
            f"{variacao:+.0f}% sobre o planejado {formatar_horas(planejado)})"
        )
        excesso = max(valor - maximo, minimo - valor, 0) / max(planejado, 1)
    if minimo == maximo:
        mensagem = f"Destravar a linha — {mensagem}"
    return Sugestao("margem", linha_id, mensagem, excesso)


def _sugestao_limite(p: ProblemaTeto, orcamento: str, tempo: float) -> Sugestao | None:
    mod = construir(p, relaxar={f"limite:{orcamento}"})
    linhas = [l.id for l in (*p.materiais, *p.mao_de_obra) if l.orcamento == orcamento]
    soma = sum(mod.total_linha[i] for i in linhas)
    limite = next(l for l in p.limites if l.orcamento == orcamento)
    fora = mod.cp.new_int_var(0, 10**12, "fora")
    if limite.max_centavos is not None:
        mod.cp.add(fora >= soma - limite.max_centavos)
    if limite.min_centavos is not None:
        mod.cp.add(fora >= limite.min_centavos - soma)
    mod.cp.minimize(fora)
    resolvedor = novo_resolvedor(tempo)
    if resolvedor.solve(mod.cp) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    valor = resolvedor.value(soma)
    atual = f"{formatar(limite.min_centavos) if limite.min_centavos is not None else '—'} a " \
            f"{formatar(limite.max_centavos) if limite.max_centavos is not None else '—'}"
    return Sugestao(
        "limite_rubrica", orcamento,
        f"Rubrica {orcamento}: precisaria de {formatar(valor)} (limite atual {atual})",
        resolvedor.value(fora) / p.teto_centavos,
    )


def _sugestao_lote(p: ProblemaTeto, grupo: str, tempo: float) -> Sugestao | None:
    mod = construir(p, relaxar={grupo})
    if novo_resolvedor(tempo).solve(mod.cp) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    tipo, lote = grupo.split(":", 1)
    if tipo == "classificacao":
        return Sugestao(
            "classificacao", lote,
            f"Lote {lote}: desligar a regra de manter a classificação (otimizacao.manter_classificacao) — "
            "uma loja fora do trio ficaria mais barata que uma do trio",
            0.5,
        )
    return Sugestao(
        "trio", lote,
        f"Lote {lote}: a loja escolhida deixaria de ser a mais barata; rever as lojas (Saída 2) ou os produtos",
        1.0,
    )


def diagnosticar(p: ProblemaTeto, tempo_limite_s: float = 20.0) -> SemSolucao:
    minimo, maximo = _extremos(p)
    if maximo < p.teto_centavos:
        motivo = "limites"
        mensagem = (
            f"Mesmo com todas as quantidades e horas no máximo, o total é {formatar(maximo)}, "
            f"{formatar(p.teto_centavos - maximo)} abaixo do teto."
        )
    elif minimo > p.teto_centavos:
        motivo = "limites"
        mensagem = (
            f"Mesmo com todas as quantidades e horas no mínimo, o total é {formatar(minimo)}, "
            f"{formatar(minimo - p.teto_centavos)} acima do teto."
        )
    elif (texto := _divisibilidade(p)) is not None:
        motivo, mensagem = "divisibilidade", texto
    else:
        motivo, mensagem = "conflito", "As regras e os limites, juntos, não permitem chegar ao teto exato."

    nucleo = _nucleo(p, tempo_limite_s)
    conflitos = tuple(_nome_do_grupo(p, g) for g in nucleo)
    if motivo == "conflito" and conflitos:
        mensagem += " Não cabem juntos: " + "; ".join(conflitos) + "."

    candidatos = nucleo or [f"margem:{l.id}" for l in (*p.materiais, *p.mao_de_obra)]
    sugestoes = []
    for grupo in candidatos:
        tipo, alvo = grupo.split(":", 1)
        if tipo == "margem":
            s = _sugestao_margem(p, alvo, tempo_limite_s)
        elif tipo == "limite":
            s = _sugestao_limite(p, alvo, tempo_limite_s)
        else:
            s = _sugestao_lote(p, grupo, tempo_limite_s)
        if s is not None:
            sugestoes.append(s)
    if motivo == "divisibilidade":
        sugestoes.append(
            Sugestao(
                "produto", "",
                "Trocar algum produto por outro cujo preço não seja múltiplo do mesmo valor, "
                "ou incluir uma linha com horas ajustáveis",
                2.0,
            )
        )
    sugestoes.sort(key=lambda s: (s.tamanho, s.mensagem))
    return SemSolucao(motivo, mensagem, conflitos, tuple(sugestoes))
