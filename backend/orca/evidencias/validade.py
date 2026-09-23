"""Validade das pesquisas (D-12) e reaproveitamento dos comprovantes da Receita (D-14).

Conta em dias do calendário de Brasília. Uma pesquisa de validade N dias vale do dia
da coleta até o dia da coleta + N − 1 (N dias contando o próprio dia da coleta): é a
leitura mais segura de "vale 180 dias a partir da coleta".
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

BRASILIA = ZoneInfo("America/Sao_Paulo")


class SituacaoValidade(StrEnum):
    VALIDA = "valida"
    VENCE_EM_BREVE = "vence_em_breve"
    VENCE_ANTES_DA_ENTREGA = "vence_antes_da_entrega"
    VENCIDA = "vencida"


@dataclass(frozen=True)
class Validade:
    coletado_em: date
    valida_ate: date  # último dia válido
    dias_restantes: int  # 0 = último dia; negativo = vencida
    situacao: SituacaoValidade


def dia_em_brasilia(momento: datetime) -> date:
    if momento.tzinfo is None:
        raise ValueError("data e hora sem fuso horário")
    return momento.astimezone(BRASILIA).date()


def hoje_em_brasilia() -> date:
    return datetime.now(BRASILIA).date()


def validade(
    coletado_em: datetime,
    hoje: date,
    validade_dias: int,
    aviso_dias: int,
    data_entrega: date | None = None,
) -> Validade:
    """Situação de uma pesquisa hoje. Ordem de gravidade: vencida, vence antes da entrega, vence em breve."""
    coleta = dia_em_brasilia(coletado_em)
    valida_ate = coleta + timedelta(days=validade_dias - 1)
    restantes = (valida_ate - hoje).days
    if restantes < 0:
        situacao = SituacaoValidade.VENCIDA
    elif data_entrega is not None and data_entrega > valida_ate:
        situacao = SituacaoValidade.VENCE_ANTES_DA_ENTREGA
    elif restantes < aviso_dias:
        situacao = SituacaoValidade.VENCE_EM_BREVE
    else:
        situacao = SituacaoValidade.VALIDA
    return Validade(coleta, valida_ate, restantes, situacao)


def comprovante_reaproveitavel(emitido_em: datetime, hoje: date, reaproveitar_dias: int) -> bool:
    """O comprovante emitido há menos de `reaproveitar_dias` dias pode ser usado de novo (D-14)."""
    return 0 <= (hoje - dia_em_brasilia(emitido_em)).days < reaproveitar_dias
