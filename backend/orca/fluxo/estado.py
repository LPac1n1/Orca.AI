"""Estado do projeto a partir do banco: lojas e seleção de cada lote, vagas e cálculo de cada cargo.

É a ligação das etapas (docs/02 §1): lê o que foi gravado (itens, observações,
correspondências, consultas de CNPJ, decisões) e roda o núcleo puro. Nada aqui é
gravado; o resultado é recalculado sempre que pedido (é rápido e determinístico).
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from orca.banco import (
    Cargo,
    ConsultaCnpj,
    Correspondencia,
    Decisao,
    Item,
    Lote,
    Observacao,
    Orcamento,
    Projeto,
    perfil_do_orcamento,
    perfil_do_projeto,
    vale_como_verde,
)
from orca.calculo import CalculoMaoDeObra, calcular_mao_de_obra
from orca.coleta.catalogo import Jornada
from orca.evidencias import SituacaoValidade, hoje_em_brasilia, validade
from orca.regras import PerfilResolvido
from orca.selecao import (
    AnaliseLote,
    AnuncioVaga,
    Duplicidade,
    ItemLote,
    Loja,
    Oferta,
    ParametrosSelecao,
    SelecaoVagas,
    SemTrio,
    Vaga,
    agrupar_duplicadas,
    analisar_lote,
    selecionar_vagas,
)

SEM_CNPJ = "sem-cnpj"


def id_da_loja(observacao: Observacao) -> str:
    """Uma loja = um site (fonte) + um vendedor (CNPJ). Em marketplace, cada vendedor é uma loja (D-16)."""
    return f"{observacao.fonte_id}:{observacao.cnpj_vendedor or SEM_CNPJ}"


def meses_ativos(linha: Item | Cargo) -> int:
    return linha.mes_fim - linha.mes_inicio + 1


# --- Lotes ---------------------------------------------------------------------------------------


@dataclass
class EstadoLote:
    lote: Lote
    itens: list[Item]
    itens_lote: list[ItemLote]
    lojas: list[Loja]
    observacoes: dict[tuple[str, str], Observacao]  # (loja, item) → observação usada
    retiradas: set[str]  # lojas retiradas pelo usuário (Saída 2, D-23)
    analise: AnaliseLote | SemTrio | None
    aguardando_aprovacao: dict[str, int] = field(default_factory=dict)  # item → nº de 🟢 por atributos a confirmar
    correspondencias: dict[tuple[str, str], Correspondencia] = field(default_factory=dict)  # (item, observação)


@dataclass
class EstadoCargo:
    cargo: Cargo
    jornada: Jornada | None
    vagas: list[Vaga]
    anuncios: dict[str, Observacao]  # vaga → observação
    duplicidade: Duplicidade
    selecao: SelecaoVagas
    calculo: CalculoMaoDeObra | None
    problema: str | None = None


@dataclass
class EstadoOrcamento:
    orcamento: Orcamento
    perfil: PerfilResolvido
    lotes: list[EstadoLote]
    cargos: list[EstadoCargo]


@dataclass
class EstadoProjeto:
    projeto: Projeto
    perfil: PerfilResolvido
    orcamentos: list[EstadoOrcamento]
    hoje: date
    consultas: dict[str, ConsultaCnpj]  # CNPJ → consulta mais recente

    def lotes(self):
        for o in self.orcamentos:
            for l in o.lotes:
                yield o, l

    def cargos(self):
        for o in self.orcamentos:
            for c in o.cargos:
                yield o, c


def _ultimas_consultas(sessao: Session, cnpjs: set[str]) -> dict[str, ConsultaCnpj]:
    if not cnpjs:
        return {}
    ultimas: dict[str, ConsultaCnpj] = {}
    for c in sessao.scalars(select(ConsultaCnpj).where(ConsultaCnpj.cnpj.in_(cnpjs)).order_by(ConsultaCnpj.consultado_em)):
        ultimas[c.cnpj] = c
    return ultimas


def _correspondencias(sessao: Session, observacao_ids: set[str]) -> dict[tuple[str, str], Correspondencia]:
    """A decisão mais recente de cada (item, observação)."""
    if not observacao_ids:
        return {}
    vigentes: dict[tuple[str, str], Correspondencia] = {}
    consulta = (
        select(Correspondencia)
        .where(Correspondencia.observacao_id.in_(observacao_ids))
        .order_by(Correspondencia.criado_em, Correspondencia.id)
    )
    for c in sessao.scalars(consulta):
        vigentes[(c.item_id, c.observacao_id)] = c
    return vigentes


def _decisoes(sessao: Session, alvo_tipo: str, alvo_id: str) -> list[Decisao]:
    return list(sessao.scalars(
        select(Decisao).where(Decisao.alvo_tipo == alvo_tipo, Decisao.alvo_id == alvo_id).order_by(Decisao.criado_em, Decisao.id)
    ))


def lojas_retiradas(sessao: Session, lote: Lote) -> set[str]:
    retiradas: set[str] = set()
    for d in _decisoes(sessao, "lote", lote.id):
        if d.tipo == "retirar_loja":
            retiradas.add(d.valor["loja"])
        elif d.tipo == "devolver_loja":
            retiradas.discard(d.valor["loja"])
    return retiradas


def _evidencia_valida(obs: Observacao, hoje: date, perfil: PerfilResolvido) -> bool:
    """PDF capturado, preço conferido na página e pesquisa dentro da validade (D-12, D-13)."""
    if obs.evidencia is None or obs.evidencia.pdf is None or obs.preco_no_html is not True:
        return False
    fontes = perfil.regras.fontes
    v = validade(obs.coletado_em, hoje, fontes.validade_dias, fontes.aviso_vencimento_dias)
    return v.situacao is not SituacaoValidade.VENCIDA


def _nome_da_loja(obs: Observacao, consultas: dict[str, ConsultaCnpj]) -> str:
    consulta = consultas.get(obs.cnpj_vendedor or "")
    if consulta and (consulta.nome_fantasia or consulta.razao_social):
        return consulta.nome_fantasia or consulta.razao_social
    return obs.fonte.nome


def _estado_do_lote(
    sessao: Session, lote: Lote, perfil: PerfilResolvido, hoje: date, consultas: dict[str, ConsultaCnpj]
) -> EstadoLote:
    itens = [i for i in lote.itens if i.excluido_em is None]
    itens_lote = [ItemLote(i.id, i.descricao, i.qtd_planejada, meses_ativos(i)) for i in itens]
    if not itens:
        return EstadoLote(lote, [], [], [], {}, set(), None)
    observacoes = list(sessao.scalars(
        select(Observacao)
        .where(Observacao.item_id.in_([i.id for i in itens]))
        .order_by(Observacao.coletado_em, Observacao.id)
    ))
    vigentes: dict[tuple, Observacao] = {}
    for obs in observacoes:  # a mais recente de cada (item, página); "não encontrado" também vale
        vigentes[(obs.item_id, obs.url)] = obs
    vigentes = {k: o for k, o in vigentes.items() if o.encontrado and o.preco_centavos is not None}
    correspondencias = _correspondencias(sessao, {o.id for o in vigentes.values()})
    regras = perfil.regras

    por_loja: dict[str, dict[str, tuple[Oferta, Observacao]]] = defaultdict(dict)
    aguardando: dict[str, int] = defaultdict(int)
    for obs in vigentes.values():
        corr = correspondencias.get((obs.item_id, obs.id))
        verde = vale_como_verde(corr, regras)
        if corr is not None and corr.status == "verde" and not verde:
            aguardando[obs.item_id] += 1
        oferta = Oferta(obs.preco_centavos, verde, _evidencia_valida(obs, hoje, perfil), obs.id)
        loja = id_da_loja(obs)
        atual = por_loja[loja].get(obs.item_id)
        # Duas páginas do mesmo item na mesma loja: vale a utilizável; empate → a mais recente.
        if atual is None or (oferta.utilizavel, obs.coletado_em) >= (atual[0].utilizavel, atual[1].coletado_em):
            por_loja[loja][obs.item_id] = (oferta, obs)

    lojas = []
    usadas: dict[tuple[str, str], Observacao] = {}
    for loja_id, ofertas in sorted(por_loja.items()):
        exemplo = next(iter(ofertas.values()))[1]
        consulta = consultas.get(exemplo.cnpj_vendedor or "")
        lojas.append(Loja(
            id=loja_id,
            nome=_nome_da_loja(exemplo, consultas),
            cnpj=exemplo.cnpj_vendedor,
            ofertas={item_id: oferta for item_id, (oferta, _) in ofertas.items()},
            cnpj_ativo=consulta is not None and consulta.situacao == "ATIVA",
        ))
        usadas |= {(loja_id, item_id): obs for item_id, (_, obs) in ofertas.items()}
    retiradas = lojas_retiradas(sessao, lote)
    analise = analisar_lote(itens_lote, lojas, ParametrosSelecao.de_regras(regras), excluir=retiradas) if lojas else None
    return EstadoLote(lote, itens, itens_lote, lojas, usadas, retiradas, analise, dict(aguardando), correspondencias)


# --- Cargos --------------------------------------------------------------------------------------


def _anuncio(obs: Observacao, vaga: Vaga) -> AnuncioVaga:
    brutos = json.loads(obs.dados_brutos or "{}")
    extraido = brutos.get("extraido") or {}
    publicada = None
    if extraido.get("data_publicacao"):
        try:
            publicada = date.fromisoformat(extraido["data_publicacao"][:10])
        except ValueError:
            publicada = None
    return AnuncioVaga(vaga, obs.titulo or "", extraido.get("cidade"), publicada, extraido.get("identificador"))


def _grupos_decididos(sessao: Session, cargo: Cargo) -> list[tuple[str, str]]:
    """Pares de vagas que o usuário marcou como a mesma vaga (casos 🟡, D-49)."""
    pares = []
    for d in _decisoes(sessao, "cargo", cargo.id):
        if d.tipo == "mesma_vaga":
            pares.append((d.valor["a"], d.valor["b"]))
    return pares


def _estado_do_cargo(
    sessao: Session, cargo: Cargo, perfil: PerfilResolvido, jornadas: dict[str, Jornada], consultas: dict[str, ConsultaCnpj]
) -> EstadoCargo:
    regras = perfil.regras.mao_de_obra
    observacoes = list(sessao.scalars(
        select(Observacao).where(Observacao.cargo_id == cargo.id).order_by(Observacao.coletado_em, Observacao.id)
    ))
    vigentes: dict[str, Observacao] = {}
    for obs in observacoes:
        vigentes[obs.url] = obs
    vagas, anuncios = [], {}
    for obs in vigentes.values():
        consulta = consultas.get(obs.cnpj_vendedor or "")
        empresa = (consulta.nome_fantasia or consulta.razao_social) if consulta else obs.fonte.nome
        vaga = Vaga(obs.id, empresa, obs.cnpj_vendedor, obs.salario_min_centavos, obs.salario_max_centavos,
                    plataforma=obs.fonte.nome)
        vagas.append(vaga)
        anuncios[vaga.id] = obs
    duplicidade = agrupar_duplicadas([_anuncio(anuncios[v.id], v) for v in vagas])
    agrupadas = {v.id: v for v in duplicidade.vagas}
    for a, b in _grupos_decididos(sessao, cargo):
        if a in agrupadas and b in agrupadas:
            grupo = agrupadas[a].grupo or agrupadas[b].grupo or min(a, b)
            for vid in (a, b):
                agrupadas[vid] = replace(agrupadas[vid], grupo=grupo)
    vagas = [agrupadas[v.id] for v in vagas]
    selecao = selecionar_vagas(vagas, regras.fontes_por_cotacao, regras.empresas_distintas_na_cotacao)
    jornada = jornadas.get(cargo.jornada_id)
    calculo, problema = None, None
    if jornada is None:
        problema = f"jornada “{cargo.jornada_id}” não está na tabela de jornadas"
    elif not selecao.suficiente:
        problema = selecao.mensagem
    else:
        try:
            calculo = calcular_mao_de_obra(
                [v.salario_referencia for v in selecao.escolhidas], jornada.jornada_semanal_horas,
                cargo.horas_planejadas_centesimos, meses_ativos(cargo), cargo.postos, jornada.fator_divisor,
            )
        except ValueError as e:
            problema = str(e)
    return EstadoCargo(cargo, jornada, vagas, anuncios, duplicidade, selecao, calculo, problema)


# --- Projeto -------------------------------------------------------------------------------------


def estado_do_projeto(
    sessao: Session, projeto: Projeto, jornadas: dict[str, Jornada], hoje: date | None = None
) -> EstadoProjeto:
    hoje = hoje or hoje_em_brasilia()
    orcamentos = [o for o in projeto.orcamentos if o.excluido_em is None and o.arquivado_em is None]
    cnpjs = set(sessao.scalars(
        select(Observacao.cnpj_vendedor)
        .outerjoin(Item, Observacao.item_id == Item.id)
        .outerjoin(Lote, Item.lote_id == Lote.id)
        .outerjoin(Cargo, Observacao.cargo_id == Cargo.id)
        .where(Observacao.cnpj_vendedor.is_not(None))
        .where((Lote.orcamento_id.in_([o.id for o in orcamentos])) | (Cargo.orcamento_id.in_([o.id for o in orcamentos])))
    ))
    consultas = _ultimas_consultas(sessao, cnpjs)
    estados = []
    for orcamento in orcamentos:
        perfil = perfil_do_orcamento(sessao, orcamento)
        lotes = [_estado_do_lote(sessao, l, perfil, hoje, consultas) for l in orcamento.lotes if l.excluido_em is None]
        cargos = [_estado_do_cargo(sessao, c, perfil, jornadas, consultas) for c in orcamento.cargos if c.excluido_em is None]
        estados.append(EstadoOrcamento(orcamento, perfil, lotes, cargos))
    return EstadoProjeto(projeto, perfil_do_projeto(sessao, projeto), estados, hoje, consultas)
