"""Painel do projeto (docs/02 §17), status de cada item e cargo (§14) e alertas (§16)."""

from dataclasses import dataclass, field

from orca.banco import ExecucaoOtimizacao
from orca.fluxo.estado import EstadoCargo, EstadoLote, EstadoProjeto
from orca.selecao import AnaliseLote, SemTrio

VERDE, AMARELO, VERMELHO = "verde", "amarelo", "vermelho"


@dataclass(frozen=True)
class StatusLinha:
    id: str
    nome: str
    tipo: str  # "item" | "cargo"
    status: str  # verde (pronto) | amarelo (falta algo ou precisa de revisão) | vermelho (problema)
    motivos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Painel:
    teto_centavos: int
    total_centavos: int | None  # da execução vigente; None = teto ainda não fechado
    planejado_centavos: int  # com as quantidades e horas planejadas (itens e cargos já cotados)
    linhas: tuple[StatusLinha, ...]
    cnpjs: int
    cnpjs_ativos: int
    cnpjs_sem_consulta: tuple[str, ...]
    aguardando_aprovacao: int  # correspondências 🟢 por atributos esperando confirmação
    pendencias_teto: tuple[str, ...] = ()
    alertas: tuple[str, ...] = field(default=())

    @property
    def contagem(self) -> dict[str, int]:
        return {s: sum(1 for l in self.linhas if l.status == s) for s in (VERDE, AMARELO, VERMELHO)}

    @property
    def diferenca_centavos(self) -> int | None:
        return None if self.total_centavos is None else self.teto_centavos - self.total_centavos


def _status_itens(estado_lote: EstadoLote, n: int) -> list[StatusLinha]:
    analise = estado_lote.analise
    violacoes = {v.item.id: v for v in analise.violacoes} if isinstance(analise, AnaliseLote) else {}
    bloqueadores = {i.id: k for i, k in analise.bloqueadores} if isinstance(analise, SemTrio) else {}
    resultado = []
    for item in estado_lote.itens:
        motivos = []
        aguardando = estado_lote.aguardando_aprovacao.get(item.id, 0)
        if aguardando:
            motivos.append(f"{aguardando} correspondência(s) 🟢 esperando a sua confirmação")
        if analise is None:
            resultado.append(StatusLinha(item.id, item.descricao, "item", AMARELO, ("nenhuma loja pesquisada", *motivos)))
            continue
        if item.id in violacoes:
            resultado.append(StatusLinha(item.id, item.descricao, "item", VERMELHO, (violacoes[item.id].mensagem, *motivos)))
            continue
        if isinstance(analise, SemTrio):
            if item.id in bloqueadores:
                motivo = f"encontrado em só {bloqueadores[item.id]} de {n} lojas válidas"
                resultado.append(StatusLinha(item.id, item.descricao, "item", VERMELHO, (motivo, *motivos)))
            else:
                resultado.append(StatusLinha(item.id, item.descricao, "item", AMARELO,
                                             (f"o lote ainda não tem {n} lojas completas", *motivos)))
            continue
        resultado.append(StatusLinha(item.id, item.descricao, "item", AMARELO if motivos else VERDE, tuple(motivos)))
    return resultado


def _status_cargo(estado_cargo: EstadoCargo) -> StatusLinha:
    cargo = estado_cargo.cargo
    motivos = []
    if estado_cargo.duplicidade.incertos:
        motivos.append(f"{len(estado_cargo.duplicidade.incertos)} par(es) de vagas talvez repetidas: confira")
    if estado_cargo.problema:
        return StatusLinha(cargo.id, cargo.nome, "cargo", VERMELHO if estado_cargo.vagas else AMARELO,
                           (estado_cargo.problema, *motivos))
    return StatusLinha(cargo.id, cargo.nome, "cargo", AMARELO if motivos else VERDE, tuple(motivos))


def painel(estado: EstadoProjeto, execucao: ExecucaoOtimizacao | None, pendencias_teto: tuple[str, ...] = ()) -> Painel:
    linhas: list[StatusLinha] = []
    planejado = 0
    for o, estado_lote in estado.lotes():
        n = o.perfil.regras.fontes.fontes_por_cotacao
        linhas += _status_itens(estado_lote, n)
        if isinstance(estado_lote.analise, AnaliseLote):
            planejado += sum(l.preco_final_centavos * l.item.quantidade_total for l in estado_lote.analise.linhas)
    for _, estado_cargo in estado.cargos():
        linhas.append(_status_cargo(estado_cargo))
        if estado_cargo.calculo:
            planejado += estado_cargo.calculo.total

    cnpjs = {obs.cnpj_vendedor for _, l in estado.lotes() for obs in l.observacoes.values() if obs.cnpj_vendedor}
    cnpjs |= {obs.cnpj_vendedor for _, c in estado.cargos() for obs in c.anuncios.values() if obs.cnpj_vendedor}
    sem_consulta = tuple(sorted(c for c in cnpjs if c not in estado.consultas))
    ativos = sum(1 for c in cnpjs if c in estado.consultas and estado.consultas[c].situacao == "ATIVA")
    aguardando = sum(sum(l.aguardando_aprovacao.values()) for _, l in estado.lotes())

    alertas = []
    if execucao is None:
        alertas.append("Teto ainda não fechado (ou mudou algo depois da última otimização).")
    if sem_consulta:
        alertas.append(f"{len(sem_consulta)} CNPJ(s) ainda sem consulta da situação cadastral.")
    if cnpjs and ativos < len(cnpjs) - len(sem_consulta):
        alertas.append(f"{len(cnpjs) - len(sem_consulta) - ativos} CNPJ(s) não estão ativos.")
    if aguardando:
        alertas.append(f"{aguardando} correspondência(s) esperando a sua confirmação.")
    vermelhos = sum(1 for l in linhas if l.status == VERMELHO)
    if vermelhos:
        alertas.append(f"{vermelhos} linha(s) com problema.")
    alertas += [f"Não dá para fechar o teto: {p}" for p in pendencias_teto]
    return Painel(
        teto_centavos=estado.projeto.teto_centavos,
        total_centavos=execucao.total_centavos if execucao is not None else None,
        planejado_centavos=planejado,
        linhas=tuple(linhas),
        cnpjs=len(cnpjs),
        cnpjs_ativos=ativos,
        cnpjs_sem_consulta=sem_consulta,
        aguardando_aprovacao=aguardando,
        pendencias_teto=pendencias_teto,
        alertas=tuple(alertas),
    )
