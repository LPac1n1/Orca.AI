"""Fechar o teto a partir do estado do projeto: monta o problema, roda o otimizador e grava a execução."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco import ExecucaoOtimizacao, registrar_execucao
from orca.banco.execucoes import para_json
from orca.fluxo.estado import EstadoProjeto
from orca.otimizacao import (
    ProblemaTeto,
    SemSolucao,
    SolucaoTeto,
    fechar_teto,
    limites_das_regras,
    linha_de_cargo,
    linhas_do_lote,
)
from orca.selecao import AnaliseLote


@dataclass(frozen=True)
class ProblemaMontado:
    problema: ProblemaTeto | None
    pendencias: tuple[str, ...]  # o que impede otimizar (lote sem trio, cargo sem cotação…)


def _margem(linha) -> tuple[int, int] | None:
    if linha.margem_min_percentual is None and linha.margem_max_percentual is None:
        return None
    return linha.margem_min_percentual, linha.margem_max_percentual


def montar_problema(estado: EstadoProjeto) -> ProblemaMontado:
    pendencias: list[str] = []
    materiais, restricoes, mao_de_obra = [], [], []
    for o, estado_lote in estado.lotes():
        lote = estado_lote.lote
        if not estado_lote.itens:
            continue
        if not isinstance(estado_lote.analise, AnaliseLote):
            motivo = estado_lote.analise.mensagem if estado_lote.analise else "nenhuma loja pesquisada"
            pendencias.append(f"{o.orcamento.nome} — lote {lote.nome}: {motivo}")
            continue
        regras = o.perfil.regras
        padrao = regras.otimizacao.margem_quantidade
        margens = {
            i.id: (
                i.margem_min_percentual if i.margem_min_percentual is not None else padrao.min_percentual,
                i.margem_max_percentual if i.margem_max_percentual is not None else padrao.max_percentual,
            )
            for i in estado_lote.itens if _margem(i) is not None
        }
        linhas, restricao = linhas_do_lote(
            estado_lote.analise, regras, orcamento=o.orcamento.id, lote=lote.id,
            margens=margens, travados={i.id for i in estado_lote.itens if i.travado},
        )
        materiais += linhas
        if restricao is not None:
            restricoes.append(restricao)
    for o, estado_cargo in estado.cargos():
        cargo = estado_cargo.cargo
        if estado_cargo.calculo is None:
            pendencias.append(f"{o.orcamento.nome} — {cargo.nome}: {estado_cargo.problema}")
            continue
        padrao = o.perfil.regras.otimizacao.margem_horas
        margem = None
        if _margem(cargo) is not None:
            margem = (
                cargo.margem_min_percentual if cargo.margem_min_percentual is not None else padrao.min_percentual,
                cargo.margem_max_percentual if cargo.margem_max_percentual is not None else padrao.max_percentual,
            )
        mao_de_obra.append(linha_de_cargo(cargo.id, cargo.nome, o.orcamento.id, estado_cargo.calculo, o.perfil.regras,
                                          margem=margem, travado=cargo.travado))
    if pendencias:
        return ProblemaMontado(None, tuple(pendencias))
    if not materiais and not mao_de_obra:
        return ProblemaMontado(None, ("o projeto ainda não tem itens nem cargos",))
    ids_por_nome = {o.orcamento.nome: o.orcamento.id for o in estado.orcamentos}
    try:
        limites = limites_das_regras(estado.perfil.regras, estado.projeto.teto_centavos, ids_por_nome)
    except ValueError as e:
        return ProblemaMontado(None, (str(e),))
    problema = ProblemaTeto(
        estado.projeto.teto_centavos,
        materiais=tuple(materiais),
        mao_de_obra=tuple(mao_de_obra),
        lotes=tuple(restricoes),
        limites=tuple(limites),
    )
    return ProblemaMontado(problema, ())


def fechar_teto_do_projeto(
    sessao: Session, estado: EstadoProjeto, tempo_limite_s: float = 20.0
) -> tuple[ExecucaoOtimizacao | None, SolucaoTeto | SemSolucao | None, tuple[str, ...]]:
    """Roda o otimizador e grava a execução (com as linhas finais, se a verificação passou)."""
    montado = montar_problema(estado)
    if montado.problema is None:
        return None, None, montado.pendencias
    resultado = fechar_teto(montado.problema, tempo_limite_s)
    execucao = registrar_execucao(sessao, estado.projeto, montado.problema, resultado, estado.perfil.impressao)
    return execucao, resultado, ()


def execucao_vigente(sessao: Session, estado: EstadoProjeto) -> ExecucaoOtimizacao | None:
    """A execução mais recente, se ainda vale: mesmas entradas do problema de hoje e verificação ok.

    Qualquer mudança (preço, quantidade, loja, regra) torna a execução antiga desatualizada.
    """
    montado = montar_problema(estado)
    if montado.problema is None:
        return None
    ultima = sessao.scalars(
        select(ExecucaoOtimizacao)
        .where(ExecucaoOtimizacao.projeto_id == estado.projeto.id)
        .order_by(ExecucaoOtimizacao.criado_em.desc(), ExecucaoOtimizacao.id.desc())
    ).first()
    if ultima is None or not ultima.verificacao_ok:
        return None
    if ultima.impressao_regras != estado.perfil.impressao or ultima.entradas != para_json(montado.problema):
        return None
    return ultima


def solucao_da_execucao(execucao: ExecucaoOtimizacao) -> dict:
    """Quantidades e horas finais gravadas (linha → valor)."""
    return {
        "quantidades": dict(execucao.resultado.get("quantidades", {})),
        "horas_centesimos": dict(execucao.resultado.get("horas_centesimos", {})),
        "alteracoes": list(execucao.resultado.get("alteracoes", [])),
        "verificacao": list(execucao.resultado.get("verificacao", [])),
    }
