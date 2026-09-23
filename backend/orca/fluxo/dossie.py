"""Dossiê do projeto a partir do banco (etapa 9): o que os documentos e o pacote mostram."""

from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

from sqlalchemy.orm import Session

from orca.auditoria import historico_do_projeto
from orca.banco import ExecucaoOtimizacao, Observacao, agora
from orca.calculo import formatar_horas
from orca.coleta.pendencias import comprovante_valido
from orca.documentos import (
    AlteracaoDoc,
    ArquivoRef,
    Dossie,
    Empresa,
    EventoDoc,
    EvidenciaDoc,
    OrcamentoDoc,
    OtimizacaoDoc,
    ProjetoDoc,
    VagaDoc,
    cargo_doc,
    lote_doc,
)
from orca.fluxo.estado import EstadoProjeto
from orca.selecao import AnaliseLote

TIPOS_DE_ARQUIVO = (("pdf", "pdf"), ("png", "png"), ("html", "mhtml"))


class ErroDossie(RuntimeError):
    """O projeto ainda não tem o necessário para gerar os documentos."""


def versao_do_sistema() -> str:
    try:
        return version("orca-ai")
    except PackageNotFoundError:
        return ""


def evidencia_doc(obs: Observacao | None) -> EvidenciaDoc | None:
    if obs is None or obs.evidencia is None:
        return None
    ev = obs.evidencia
    arquivos = tuple(
        ArquivoRef(arquivo.caminho, arquivo.sha256, tipo)
        for atributo, tipo in TIPOS_DE_ARQUIVO
        if (arquivo := getattr(ev, atributo)) is not None
    )
    return EvidenciaDoc(ev.url, ev.capturado_em, ev.metodo, arquivos)


def _empresas(sessao: Session, estado: EstadoProjeto) -> dict[str, Empresa]:
    observacoes = [o for _, l in estado.lotes() for o in l.observacoes.values()]
    observacoes += [o for _, c in estado.cargos() for o in c.anuncios.values()]
    dias = estado.perfil.regras.evidencia.reaproveitar_comprovante_dias
    empresas = {}
    for obs in observacoes:
        cnpj = obs.cnpj_vendedor
        if not cnpj or cnpj in empresas:
            continue
        consulta = estado.consultas.get(cnpj)
        comprovante = comprovante_valido(sessao, cnpj, estado.hoje, dias)
        empresas[cnpj] = Empresa(
            nome=(consulta.razao_social if consulta and consulta.razao_social else obs.fonte.nome),
            cnpj=cnpj,
            situacao=consulta.situacao if consulta else None,
            consultado_em=consulta.consultado_em if consulta else None,
            comprovante=ArquivoRef(comprovante.arquivo.caminho, comprovante.arquivo_sha256, "pdf") if comprovante else None,
        )
    return empresas


def _otimizacao(execucao: ExecucaoOtimizacao | None, planejado: int) -> OtimizacaoDoc:
    if execucao is None:
        return OtimizacaoDoc("sem_otimizacao", planejado)
    alteracoes = tuple(
        AlteracaoDoc(
            a["nome"],
            f"{a['de']} un" if a["unidade"] == "un" else f"{formatar_horas(a['de'])} h/mês",
            f"{a['para']} un" if a["unidade"] == "un" else f"{formatar_horas(a['para'])} h/mês",
        )
        for a in execucao.resultado.get("alteracoes", [])
    )
    return OtimizacaoDoc(execucao.status, execucao.total_centavos or 0, alteracoes,
                         tuple(execucao.resultado.get("verificacao", [])), execucao.versao_otimizador)


def dossie_do_projeto(
    sessao: Session, estado: EstadoProjeto, execucao: ExecucaoOtimizacao | None, gerado_em: datetime | None = None
) -> Dossie:
    pendencias = [
        f"{o.orcamento.nome} — lote {l.lote.nome}: {l.analise.mensagem if l.analise else 'nenhuma loja pesquisada'}"
        for o, l in estado.lotes() if l.itens and not isinstance(l.analise, AnaliseLote)
    ] + [f"{o.orcamento.nome} — {c.cargo.nome}: {c.problema}" for o, c in estado.cargos() if c.calculo is None]
    if pendencias:
        raise ErroDossie("Ainda não dá para gerar os documentos: " + "; ".join(pendencias))

    empresas = _empresas(sessao, estado)
    quantidades = execucao.resultado.get("quantidades", {}) if execucao else {}
    horas = execucao.resultado.get("horas_centesimos", {}) if execucao else {}
    orcamentos, planejado = [], 0
    for o in estado.orcamentos:
        lotes = []
        for l in o.lotes:
            if not l.itens:
                continue
            lotes.append(lote_doc(
                l.analise, l.lote.nome,
                quantidades=quantidades or None,
                empresas=empresas,
                evidencias={chave: evidencia_doc(obs) for chave, obs in l.observacoes.items()},
                titulos={chave: obs.titulo for chave, obs in l.observacoes.items() if obs.titulo},
                unidades={i.id: i.unidade for i in l.itens},
                inicios={i.id: i.mes_inicio for i in l.itens},
            ))
            planejado += sum(linha.preco_final_centavos * linha.item.quantidade_total for linha in l.analise.linhas)
        cargos = []
        for c in o.cargos:
            vagas = []
            for vaga in c.selecao.escolhidas:
                obs = c.anuncios[vaga.id]
                empresa = empresas.get(vaga.cnpj or "") or Empresa(vaga.empresa or obs.fonte.nome, vaga.cnpj)
                vagas.append(VagaDoc(empresa, vaga.salario_referencia, obs.titulo or "", vaga.plataforma, evidencia_doc(obs)))
            descartadas = [(f"{v.empresa or 'empresa não identificada'} ({v.plataforma})", motivo)
                           for v, motivo in c.selecao.descartadas]
            cargos.append(cargo_doc(
                c.cargo.id, c.cargo.nome, c.cargo.regime, c.calculo, vagas,
                horas_finais_centesimos=horas.get(c.cargo.id), descartadas=descartadas, mes_inicio=c.cargo.mes_inicio,
            ))
            planejado += c.calculo.total
        if lotes or cargos:
            orcamentos.append(OrcamentoDoc(o.orcamento.nome, o.orcamento.tipo, tuple(lotes), tuple(cargos)))

    p, regras = estado.projeto, estado.perfil.regras
    projeto = ProjetoDoc(
        nome=p.nome,
        organizacao=Empresa(p.organizacao.nome, p.organizacao.cnpj),
        teto_centavos=p.teto_centavos,
        duracao_meses=p.duracao_meses,
        orgao=p.orgao,
        instrumento=p.instrumento,
        processo=p.processo,
        cep=p.cep,
        data_entrega=p.data_entrega,
        desembolso=regras.desembolso.padrao,
        fontes_por_cotacao=regras.fontes.fontes_por_cotacao,
        validade_dias=regras.fontes.validade_dias,
        aviso_vencimento_dias=regras.fontes.aviso_vencimento_dias,
        impressao_regras=estado.perfil.impressao,
        versao_sistema=versao_do_sistema(),
        gerado_em=gerado_em or agora(),
    )
    eventos = tuple(
        EventoDoc(e.criado_em, e.entidade, e.entidade_id, e.acao, e.autor, e.antes, e.depois)
        for e in historico_do_projeto(sessao, p.id)
    )
    return Dossie(projeto, tuple(orcamentos), _otimizacao(execucao, planejado), empresas, eventos)
