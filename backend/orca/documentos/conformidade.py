"""Relatório de conformidade: cada regra conferida no dossiê pronto (docs/02 §18).

Situação de cada conferência: "ok", "atencao" (precisa de alguém olhar) ou
"problema" (o orçamento não está em condições de ser entregue).
"""

from dataclasses import dataclass
from datetime import date

from orca.calculo import formatar
from orca.documentos.modelo import Dossie
from orca.dominio import cnpj_raiz, formatar_cnpj
from orca.evidencias import SituacaoValidade, validade

OK, ATENCAO, PROBLEMA = "ok", "atencao", "problema"


@dataclass(frozen=True)
class Conferencia:
    regra: str
    situacao: str
    detalhes: tuple[str, ...] = ()


def _situacao(problemas: list[str], atencoes: list[str] = ()) -> str:
    return PROBLEMA if problemas else ATENCAO if atencoes else OK


def conferir(dossie: Dossie, hoje: date) -> tuple[Conferencia, ...]:
    p = dossie.projeto
    conferencias = []

    total = dossie.total_centavos
    diferenca = p.teto_centavos - total
    conferencias.append(Conferencia(
        "Teto exato ao centavo (D-30)",
        OK if diferenca == 0 else PROBLEMA,
        (f"Total {formatar(total)} · teto {formatar(p.teto_centavos)} · diferença {formatar(diferenca)}",),
    ))

    lotes = [(o, l) for o in dossie.orcamentos for l in o.lotes]
    faltam = [f"{l.nome}: {len(l.lojas)} de {p.fontes_por_cotacao} fontes" for _, l in lotes if len(l.lojas) != p.fontes_por_cotacao]
    conferencias.append(Conferencia(f"{p.fontes_por_cotacao} fontes por cotação (D-10)", _situacao(faltam), tuple(faltam)))

    acima = [
        f"{l.nome} — {linha.nome}: {formatar(linha.preco_final_centavos)} × média {formatar(linha.media_exibida)}"
        for _, l in lotes for linha in l.linhas if linha.dentro_da_media is False
    ]
    conferencias.append(Conferencia("Preço final dentro da média (regra B, D-23)", _situacao(acima), tuple(acima)))

    repetidos = []
    for _, lote in lotes:
        raizes = [cnpj_raiz(loja.empresa.cnpj) for loja in lote.lojas if loja.empresa.cnpj]
        if len(raizes) != len(set(raizes)) or len(raizes) != len(lote.lojas):
            repetidos.append(f"{lote.nome}: CNPJs repetidos ou não identificados")
    for o in dossie.orcamentos:
        for cargo in o.cargos:
            raizes = [cnpj_raiz(v.empresa.cnpj) for v in cargo.vagas if v.empresa.cnpj]
            if len(raizes) != len(set(raizes)) or len(raizes) != len(cargo.vagas):
                repetidos.append(f"{cargo.nome}: empresas repetidas ou não identificadas")
    conferencias.append(Conferencia("Empresas diferentes em cada cotação (P-03, P-04)", _situacao(repetidos), tuple(repetidos)))

    cnpjs = {loja.empresa.cnpj: loja.empresa for _, l in lotes for loja in l.lojas if loja.empresa.cnpj}
    cnpjs |= {v.empresa.cnpj: v.empresa for o in dossie.orcamentos for c in o.cargos for v in c.vagas if v.empresa.cnpj}
    inativos, sem_consulta, sem_comprovante = [], [], []
    for cnpj, empresa in sorted(cnpjs.items()):
        dados = dossie.empresa(cnpj) or empresa
        rotulo = f"{formatar_cnpj(cnpj)} {dados.nome}"
        if dados.situacao is None:
            sem_consulta.append(rotulo)
        elif dados.situacao != "ATIVA":
            inativos.append(f"{rotulo}: {dados.situacao}")
        if dados.comprovante is None:
            sem_comprovante.append(rotulo)
    conferencias.append(Conferencia(
        "CNPJ ativo em todas as fontes", _situacao(inativos, sem_consulta),
        tuple(inativos + [f"não consultado: {x}" for x in sem_consulta]),
    ))
    conferencias.append(Conferencia(
        "Comprovante da Receita de cada empresa (D-13)", _situacao([], sem_comprovante),
        tuple(f"pendente: {x}" for x in sem_comprovante),
    ))

    sem_evidencia, vencidas, a_vencer = [], [], []
    evidencias = [
        (f"{l.nome} — {linha.nome} (Orçamento {k + 1})", fonte.evidencia)
        for _, l in lotes for linha in l.linhas for k, fonte in enumerate(linha.fontes)
    ] + [
        (f"{c.nome} — vaga {k + 1}", vaga.evidencia)
        for o in dossie.orcamentos for c in o.cargos for k, vaga in enumerate(c.vagas)
    ]
    for rotulo, evidencia in evidencias:
        if evidencia is None or evidencia.arquivo("pdf") is None:
            sem_evidencia.append(f"{rotulo}: Não foi possível validar automaticamente (sem evidência em PDF)")
            continue
        v = validade(evidencia.coletado_em, hoje, p.validade_dias, p.aviso_vencimento_dias, p.data_entrega)
        ate = v.valida_ate.strftime("%d/%m/%Y")
        if v.situacao is SituacaoValidade.VENCIDA:
            vencidas.append(f"{rotulo}: venceu em {ate}")
        elif v.situacao is SituacaoValidade.VENCE_ANTES_DA_ENTREGA:
            vencidas.append(f"{rotulo}: vale até {ate}, antes da entrega")
        elif v.situacao is SituacaoValidade.VENCE_EM_BREVE:
            a_vencer.append(f"{rotulo}: vence em {ate}")
    conferencias.append(Conferencia("Evidência (PDF) de cada preço e salário (D-13)", _situacao(sem_evidencia), tuple(sem_evidencia)))
    conferencias.append(Conferencia(f"Validade das pesquisas: {p.validade_dias} dias (D-12)", _situacao(vencidas, a_vencer),
                                    tuple(vencidas + a_vencer)))

    vagas = [f"{c.nome}: {len(c.vagas)} de {p.fontes_por_cotacao} vagas" for o in dossie.orcamentos
             for c in o.cargos if len(c.vagas) != p.fontes_por_cotacao]
    conferencias.append(Conferencia("Vagas por cargo (D-40, D-48)", _situacao(vagas), tuple(vagas)))

    otim = dossie.otimizacao
    if otim.status == "sem_otimizacao":
        conferencias.append(Conferencia("Otimização e verificação independente", ATENCAO, ("o teto não foi fechado pelo otimizador",)))
    else:
        conferencias.append(Conferencia(
            "Otimização e verificação independente", _situacao(list(otim.verificacao)),
            tuple(otim.verificacao) or (f"{len(otim.alteracoes)} linha(s) ajustada(s); verificação sem problemas",),
        ))
    return tuple(conferencias)


def resumo_da_conformidade(conferencias: tuple[Conferencia, ...]) -> dict[str, int]:
    return {s: sum(1 for c in conferencias if c.situacao == s) for s in (OK, ATENCAO, PROBLEMA)}
