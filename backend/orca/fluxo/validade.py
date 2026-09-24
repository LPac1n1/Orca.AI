"""Validade das pesquisas (D-12; Fase 2, etapa 12): o que venceu ou vai vencer, e como pesquisar de novo."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from orca.banco import Observacao, Projeto, perfil_do_projeto
from orca.busca import ler_plataformas, plataforma_do_endereco
from orca.coleta.pendencias import observacoes_do_projeto, vigentes
from orca.evidencias import SituacaoValidade, validade


@dataclass(frozen=True)
class PesquisaParaRefazer:
    observacao: Observacao
    situacao: SituacaoValidade
    valida_ate: date


def pesquisas_a_refazer(sessao: Session, projeto: Projeto, hoje: date) -> list[PesquisaParaRefazer]:
    """As pesquisas em uso (a mais recente de cada página) que venceram, vencem antes da entrega ou vencem em breve."""
    regras = perfil_do_projeto(sessao, projeto).regras.fontes
    lista = []
    for obs in vigentes(observacoes_do_projeto(sessao, projeto)):
        if not obs.encontrado:
            continue
        v = validade(obs.coletado_em, hoje, regras.validade_dias, regras.aviso_vencimento_dias, projeto.data_entrega)
        if v.situacao is not SituacaoValidade.VALIDA:
            lista.append(PesquisaParaRefazer(obs, v.situacao, v.valida_ate))
    ordem = {SituacaoValidade.VENCIDA: 0, SituacaoValidade.VENCE_ANTES_DA_ENTREGA: 1, SituacaoValidade.VENCE_EM_BREVE: 2}
    return sorted(lista, key=lambda p: (ordem[p.situacao], p.valida_ate))


def como_refazer(obs: Observacao) -> tuple[str, dict] | None:
    """Tipo de tarefa e parâmetros para pesquisar de novo a mesma página; None se só a pessoa pode (PDF enviado).

    Página capturada pelo sistema: o sistema abre de novo. Página capturada na janela (ou de plataforma
    que proíbe programas, D-69): a janela abre de novo, com a pessoa.
    """
    evidencia = obs.evidencia
    if evidencia is not None and evidencia.png is None and evidencia.html is None:
        return None  # PDF salvo e enviado pela pessoa: ela salva e envia de novo
    plataforma = plataforma_do_endereco(obs.url, ler_plataformas()) if obs.cargo_id else None
    janela = obs.metodo == "C4" or (plataforma is not None and plataforma.abrir_vaga == "janela")
    if obs.item_id:
        parametros = {"item_id": obs.item_id, "url": obs.url}
        if obs.cnpj_vendedor:
            parametros["cnpj_vendedor"] = obs.cnpj_vendedor
        return ("captura_assistida" if janela else "coletar_item"), parametros
    parametros = {"cargo_id": obs.cargo_id, "url": obs.url}
    if obs.cnpj_vendedor:
        parametros["cnpj_empresa"] = obs.cnpj_vendedor
    return ("captura_assistida" if janela else "coletar_cargo"), parametros
