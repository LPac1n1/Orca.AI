"""Conversão do estado do projeto para JSON (o que as telas mostram). Dinheiro sempre em centavos."""

import json
from datetime import date, datetime

from orca.banco import (
    Cargo,
    Correspondencia,
    ExecucaoOtimizacao,
    Item,
    Lote,
    Observacao,
    Orcamento,
    Projeto,
    Tarefa,
    vale_como_verde,
)
from orca.calculo import formatar_exato
from orca.coleta import precos_da_pagina
from orca.fluxo import EstadoCargo, EstadoLote, EstadoProjeto, Painel
from orca.selecao import AnaliseLote, SemTrio


def _data(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def projeto_json(p: Projeto) -> dict:
    return {
        "id": p.id, "nome": p.nome, "organizacao": {"id": p.organizacao.id, "nome": p.organizacao.nome,
                                                   "cnpj": p.organizacao.cnpj},
        "orgao": p.orgao, "instrumento": p.instrumento, "processo": p.processo, "teto_centavos": p.teto_centavos,
        "duracao_meses": p.duracao_meses, "cep": p.cep, "data_entrega": _data(p.data_entrega),
        "arquivado": p.arquivado_em is not None, "criado_em": _data(p.criado_em),
    }


def item_json(i: Item) -> dict:
    return {
        "id": i.id, "lote_id": i.lote_id, "descricao": i.descricao, "categoria": i.categoria, "marca": i.marca,
        "modelo": i.modelo, "apresentacao": i.apresentacao, "atributos": i.atributos, "ean": i.ean, "unidade": i.unidade,
        "qtd_planejada": i.qtd_planejada, "mes_inicio": i.mes_inicio, "mes_fim": i.mes_fim,
        "margem_min_percentual": i.margem_min_percentual, "margem_max_percentual": i.margem_max_percentual,
        "travado": i.travado, "substitui_item_id": i.substitui_item_id,
    }


def cargo_json(c: Cargo) -> dict:
    return {
        "id": c.id, "orcamento_id": c.orcamento_id, "nome": c.nome, "cbo": c.cbo, "postos": c.postos,
        "regime": c.regime, "jornada_id": c.jornada_id, "horas_planejadas_centesimos": c.horas_planejadas_centesimos,
        "mes_inicio": c.mes_inicio, "mes_fim": c.mes_fim, "margem_min_percentual": c.margem_min_percentual,
        "margem_max_percentual": c.margem_max_percentual, "travado": c.travado,
    }


def lote_json(l: Lote) -> dict:
    return {"id": l.id, "orcamento_id": l.orcamento_id, "nome": l.nome,
            "itens": [item_json(i) for i in l.itens if i.excluido_em is None]}


def orcamento_json(o: Orcamento) -> dict:
    return {
        "id": o.id, "projeto_id": o.projeto_id, "nome": o.nome, "descricao": o.descricao, "tipo": o.tipo,
        "arquivado": o.arquivado_em is not None,
        "lotes": [lote_json(l) for l in o.lotes if l.excluido_em is None],
        "cargos": [cargo_json(c) for c in o.cargos if c.excluido_em is None],
    }


def projeto_completo_json(p: Projeto) -> dict:
    return projeto_json(p) | {
        "orcamentos": [orcamento_json(o) for o in p.orcamentos if o.excluido_em is None],
    }


def correspondencia_json(c: Correspondencia | None, regras) -> dict | None:
    if c is None:
        return None
    return {"id": c.id, "status": c.status, "origem": c.origem, "motivos": list(c.motivos), "autor": c.autor,
            "vale": vale_como_verde(c, regras),
            "precisa_confirmar": c.status == "verde" and not vale_como_verde(c, regras)}


def observacao_json(o: Observacao, correspondencia: dict | None = None) -> dict:
    brutos = json.loads(o.dados_brutos or "{}")
    return {
        "id": o.id, "url": o.url, "loja": o.fonte.nome, "fonte_id": o.fonte_id, "cnpj_vendedor": o.cnpj_vendedor,
        "titulo": o.titulo, "marca": o.marca, "ean": o.ean, "preco_centavos": o.preco_centavos,
        "salario_min_centavos": o.salario_min_centavos, "salario_max_centavos": o.salario_max_centavos,
        "encontrado": o.encontrado, "disponivel": o.disponivel, "coletado_em": _data(o.coletado_em), "metodo": o.metodo,
        "preco_no_html": o.preco_no_html, "evidencia_id": o.evidencia_id, "avisos": brutos.get("avisos", []),
        "autor": o.autor, "correspondencia": correspondencia,
        "precos_da_pagina": precos_da_pagina(o) if o.alvo_tipo == "item" else [],
        "forma_de_pagamento": (brutos.get("escolha_d60") or {}).get("forma"),
    }


def _lojas_do_lote(estado: EstadoLote) -> list[dict]:
    analise = estado.analise
    posicoes, totais, situacao, motivos = {}, {}, {}, {}
    if isinstance(analise, AnaliseLote):
        for k, lc in enumerate(analise.trio, 1):
            posicoes[lc.loja.id], totais[lc.loja.id], situacao[lc.loja.id] = k, lc.total_centavos, "trio"
        for lc in analise.demais_elegiveis:
            totais[lc.loja.id], situacao[lc.loja.id] = lc.total_centavos, "elegivel"
    elif isinstance(analise, SemTrio):
        for loja in analise.completas:
            situacao[loja.id] = "completa"
    descartadas = analise.descartadas if analise is not None else ()
    for loja, motivo in descartadas:
        situacao[loja.id], motivos[loja.id] = "descartada", motivo
    for loja_id in estado.retiradas:
        situacao[loja_id], motivos[loja_id] = "retirada", "retirada por decisão do usuário"
    return [
        {"id": l.id, "nome": l.nome, "cnpj": l.cnpj, "cnpj_ativo": l.cnpj_ativo, "cnpj_consultado": l.cnpj_consultado, "posicao": posicoes.get(l.id),
         "total_centavos": totais.get(l.id), "situacao": situacao.get(l.id, "incompleta"), "motivo": motivos.get(l.id)}
        for l in sorted(estado.lojas, key=lambda l: (posicoes.get(l.id) or 99, totais.get(l.id) or 10**15, l.nome))
    ]


def _itens_do_lote(estado: EstadoLote, regras, status: dict) -> list[dict]:
    linhas = {l.item.id: l for l in estado.analise.linhas} if isinstance(estado.analise, AnaliseLote) else {}
    resultado = []
    for item in estado.itens:
        ofertas = {}
        for loja in estado.lojas:
            oferta = loja.ofertas.get(item.id)
            if oferta is None:
                continue
            obs = estado.observacoes.get((loja.id, item.id))
            corr = estado.correspondencias.get((item.id, obs.id)) if obs else None
            ofertas[loja.id] = {
                "preco_centavos": oferta.preco_centavos, "observacao_id": oferta.observacao_id,
                "utilizavel": oferta.utilizavel, "evidencia_valida": oferta.evidencia_valida,
                "evidencia_id": obs.evidencia_id if obs else None, "url": obs.url if obs else None,
                "titulo": obs.titulo if obs else None, "correspondencia": correspondencia_json(corr, regras),
            }
        linha = linhas.get(item.id)
        situacao = status.get(item.id)
        resultado.append(item_json(item) | {
            "meses": item.mes_fim - item.mes_inicio + 1,
            "status": situacao.status if situacao else None,
            "motivos": list(situacao.motivos) if situacao else [],
            "ofertas": ofertas,
            "media_centavos": linha.cotacao.media_exibida if linha else None,
            "media_exata": formatar_exato(linha.cotacao.media_exata) if linha else None,
            "preco_final_centavos": linha.preco_final_centavos if linha else None,
            "dentro_da_media": linha.dentro_da_media if linha else None,
        })
    return resultado


def _cargo(estado: EstadoCargo, status: dict) -> dict:
    escolhidas = {v.id for v in estado.selecao.escolhidas}
    descartes = {v.id: m for v, m in estado.selecao.descartadas}
    calc = estado.calculo
    situacao = status.get(estado.cargo.id)
    return cargo_json(estado.cargo) | {
        "status": situacao.status if situacao else None,
        "motivos": list(situacao.motivos) if situacao else [],
        "jornada": {"id": estado.jornada.id, "descricao": estado.jornada.descricao,
                    "semanal_horas": estado.jornada.jornada_semanal_horas} if estado.jornada else None,
        "vagas": [
            {"id": v.id, "empresa": v.empresa, "cnpj": v.cnpj, "salario_min_centavos": v.salario_min_centavos,
             "salario_max_centavos": v.salario_max_centavos, "referencia_centavos": v.salario_referencia,
             "plataforma": v.plataforma, "grupo": v.grupo, "escolhida": v.id in escolhidas,
             "motivo_descarte": descartes.get(v.id), "evidencia_id": estado.anuncios[v.id].evidencia_id,
             "url": estado.anuncios[v.id].url, "titulo": estado.anuncios[v.id].titulo}
            for v in estado.vagas
        ],
        "incertos": [{"a": p.a, "b": p.b, "motivo": p.motivo} for p in estado.duplicidade.incertos],
        "calculo": None if calc is None else {
            "salarios_centavos": list(calc.salarios), "media_centavos": calc.media, "divisor": calc.divisor,
            "valor_hora_centavos": calc.valor_hora, "horas_mes_centesimos": calc.horas_mes_centesimos,
            "valor_mensal_centavos": calc.valor_mensal, "meses": calc.meses, "postos": calc.postos,
            "total_centavos": calc.total, "memoria": calc.memoria(),
        },
        "problema": estado.problema,
    }


def revisao_json(estado: EstadoProjeto, painel: Painel) -> dict:
    """A matriz de revisão (docs/02 §14): cada item com as ofertas de cada loja, e cada cargo com as vagas."""
    status = {l.id: l for l in painel.linhas}
    orcamentos = []
    for o in estado.orcamentos:
        regras = o.perfil.regras
        lotes = []
        for l in o.lotes:
            analise = l.analise
            lotes.append({
                "id": l.lote.id, "nome": l.lote.nome,
                "situacao": "ok" if isinstance(analise, AnaliseLote) else "sem_trio" if analise else "sem_pesquisa",
                "mensagem": analise.justificativa if isinstance(analise, AnaliseLote) else analise.mensagem if analise else None,
                "sugestoes": list(analise.sugestoes) if isinstance(analise, SemTrio) else [],
                "lojas": _lojas_do_lote(l),
                "itens": _itens_do_lote(l, regras, status),
            })
        orcamentos.append({
            "id": o.orcamento.id, "nome": o.orcamento.nome, "tipo": o.orcamento.tipo,
            "base_preco_final": regras.calculo.base_preco_final, "fontes_por_cotacao": regras.fontes.fontes_por_cotacao,
            "lotes": lotes, "cargos": [_cargo(c, status) for c in o.cargos],
        })
    return {"projeto_id": estado.projeto.id, "hoje": estado.hoje.isoformat(), "orcamentos": orcamentos}


def painel_json(p: Painel) -> dict:
    return {
        "teto_centavos": p.teto_centavos, "total_centavos": p.total_centavos, "diferenca_centavos": p.diferenca_centavos,
        "planejado_centavos": p.planejado_centavos, "contagem": p.contagem, "cnpjs": p.cnpjs,
        "cnpjs_ativos": p.cnpjs_ativos, "cnpjs_sem_consulta": list(p.cnpjs_sem_consulta),
        "aguardando_aprovacao": p.aguardando_aprovacao, "pendencias_teto": list(p.pendencias_teto),
        "alertas": list(p.alertas),
        "linhas": [{"id": l.id, "nome": l.nome, "tipo": l.tipo, "status": l.status, "motivos": list(l.motivos)}
                   for l in p.linhas],
    }


def execucao_json(e: ExecucaoOtimizacao | None, vigente: bool) -> dict | None:
    if e is None:
        return None
    return {"id": e.id, "status": e.status, "total_centavos": e.total_centavos, "teto_centavos": e.teto_centavos,
            "verificacao_ok": e.verificacao_ok, "versao": e.versao_otimizador, "criado_em": _data(e.criado_em),
            "vigente": vigente, "resultado": e.resultado}


def tarefa_json(t: Tarefa) -> dict:
    return {"id": t.id, "projeto_id": t.projeto_id, "tipo": t.tipo, "estado": t.estado, "progresso": t.progresso,
            "mensagem": t.mensagem, "parametros": t.parametros, "resultado": t.resultado, "autor": t.autor,
            "criado_em": _data(t.criado_em), "iniciada_em": _data(t.iniciada_em), "concluida_em": _data(t.concluida_em)}
