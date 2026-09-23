"""Gravação das execuções do otimizador (docs/03 §4.6): entradas, resultado, versões e linhas finais."""

import dataclasses
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from orca.banco.tabelas import ExecucaoOtimizacao, LinhaFinal, Projeto
from orca.otimizacao import VERSAO_OTIMIZADOR, ProblemaTeto, SemSolucao, SolucaoTeto


def para_json(valor: Any) -> Any:
    """Dataclasses, dicionários e tuplas → estrutura JSON (como fica gravada no banco)."""
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return {c.name: para_json(getattr(valor, c.name)) for c in dataclasses.fields(valor)}
    if isinstance(valor, Mapping):
        return {str(k): para_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [para_json(v) for v in valor]
    return valor


def registrar_execucao(
    sessao: Session,
    projeto: Projeto,
    problema: ProblemaTeto,
    resultado: SolucaoTeto | SemSolucao,
    impressao_regras: str,
) -> ExecucaoOtimizacao:
    """Grava a execução. As linhas finais só são gravadas se a verificação independente passou."""
    autor = sessao.info.get("autor")
    if isinstance(resultado, SolucaoTeto):
        status = "otima" if resultado.otima else "viavel"
        total, verificacao_ok, versao = resultado.total_centavos, resultado.verificacao_ok, resultado.versao_otimizador
    else:
        status, total, verificacao_ok, versao = "sem_solucao", None, False, VERSAO_OTIMIZADOR
    execucao = ExecucaoOtimizacao(
        projeto=projeto,
        impressao_regras=impressao_regras,
        status=status,
        teto_centavos=problema.teto_centavos,
        total_centavos=total,
        verificacao_ok=verificacao_ok,
        versao_otimizador=versao,
        entradas=para_json(problema),
        resultado=para_json(resultado),
        autor=autor,
    )
    sessao.add(execucao)
    if isinstance(resultado, SolucaoTeto) and resultado.verificacao_ok:
        for l in problema.materiais:
            sessao.add(
                LinhaFinal(
                    execucao=execucao, linha_id=l.id, alvo_tipo="item",
                    preco_unitario_centavos=l.preco_centavos, quantidade=resultado.quantidades[l.id],
                    meses=l.meses, total_centavos=resultado.totais[l.id],
                )
            )
        for l in problema.mao_de_obra:
            sessao.add(
                LinhaFinal(
                    execucao=execucao, linha_id=l.id, alvo_tipo="cargo",
                    valor_hora_centavos=l.valor_hora_centavos, horas_centesimos=resultado.horas_centesimos[l.id],
                    valor_mensal_centavos=resultado.valores_mensais[l.id], postos=l.postos,
                    meses=l.meses, total_centavos=resultado.totais[l.id],
                )
            )
    return execucao
