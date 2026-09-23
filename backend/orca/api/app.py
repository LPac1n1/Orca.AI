"""API local (FastAPI) do Orça.AI: http://localhost:8765 (D-05).

Segurança de um programa local:
- escuta só no próprio computador (127.0.0.1);
- recusa pedidos com outro nome de endereço (proteção contra DNS rebinding);
- pedidos que mudam dados precisam do cabeçalho X-Orca: 1, que outros sites não
  conseguem enviar ao navegador (proteção contra CSRF). A interface envia sempre.
"""

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as ErroHttp

from orca.api import apresentacao as ap
from orca.api import esquemas as e
from orca.api.config import Configuracao
from orca.auditoria import ErroAuditoria, historico_do_projeto
from orca.banco import (
    Cargo,
    ErroCorrespondencia,
    Evidencia,
    ExecucaoOtimizacao,
    Item,
    Lote,
    Observacao,
    Orcamento,
    Organizacao,
    Projeto,
    Tarefa,
    abrir_banco,
    agora,
    correspondencia_vigente,
    decidir_correspondencia,
    definir_camadas_do_projeto,
    perfil_do_projeto,
    sessao_como,
)
from orca.coleta import (
    CATALOGO_PADRAO,
    Navegador,
    comprovantes_pendentes,
    ler_catalogo,
    ler_jornadas,
    ler_vocabulario,
)
from orca.documentos import Renderizador, conferir
from orca.evidencias import ArmazemArquivos, ErroIntegridade
from orca.fluxo import (
    ErroAcao,
    ErroDossie,
    devolver_loja,
    dossie_do_projeto,
    estado_do_projeto,
    execucao_vigente,
    marcar_mesma_vaga,
    montar_problema,
    painel,
    retirar_loja,
    simular_troca_de_loja,
    substituir_item,
    versao_do_sistema,
)
from orca.selecao import ParametrosSelecao
from orca.tarefas import Contexto, ErroTarefa, Fila

ESTATICO = Path(__file__).parent / "estatico"
CAMPOS_DA_ESPECIFICACAO = {"descricao", "categoria", "marca", "modelo", "apresentacao", "atributos", "ean", "unidade"}
TIPOS_DE_EVIDENCIA = {"pdf": ("pdf", "application/pdf"), "png": ("png", "image/png"),
                      "mhtml": ("html", "multipart/related")}


class Servico:
    """O que as rotas usam: banco, armazém, fila e configuração."""

    def __init__(self, config: Configuracao, contexto: Contexto, fila: Fila):
        self.config, self.contexto, self.fila = config, contexto, fila

    @contextmanager
    def sessao(self) -> Iterator[Session]:
        with sessao_como(self.contexto.fabrica, self.config.autor) as s:
            yield s

    def estado(self, s: Session, projeto: Projeto, hoje: date | None = None):
        return estado_do_projeto(s, projeto, self.contexto.jornadas, hoje or self.contexto.hoje())


def contexto_padrao(config: Configuracao, **trocas) -> Contexto:
    pasta = config.pasta
    pasta.mkdir(parents=True, exist_ok=True)
    return Contexto(
        fabrica=trocas.pop("fabrica", None) or abrir_banco(pasta / "orcamentos.sqlite"),
        armazem=ArmazemArquivos(pasta),
        pasta_dados=pasta,
        vocabulario=trocas.pop("vocabulario", None) or ler_vocabulario(),
        catalogo=ler_catalogo(CATALOGO_PADRAO),
        jornadas=ler_jornadas(),
        abrir_navegador=trocas.pop("abrir_navegador", None) or (lambda: Navegador()),
        abrir_renderizador=trocas.pop("abrir_renderizador", None) or (lambda: Renderizador()),
        **trocas,
    )


def _obter(s: Session, classe, id_: str, nome: str):
    objeto = s.get(classe, id_)
    if objeto is None or getattr(objeto, "excluido_em", None) is not None:
        raise HTTPException(404, f"{nome} não encontrado(a)")
    return objeto


def _aplicar(objeto, dados: dict) -> None:
    for campo, valor in dados.items():
        setattr(objeto, campo, valor)


def criar_app(config: Configuracao, contexto: Contexto | None = None, iniciar_trabalhador: bool = True) -> FastAPI:
    contexto = contexto or contexto_padrao(config)
    fila = Fila(contexto)
    servico = Servico(config, contexto, fila)

    @asynccontextmanager
    async def ciclo(_app: FastAPI):
        if iniciar_trabalhador:
            fila.iniciar()
        yield
        fila.parar()

    app = FastAPI(title="Orça.AI", version=versao_do_sistema() or "0", lifespan=ciclo, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)
    app.state.servico = servico
    hosts = {f"localhost:{config.porta}", f"127.0.0.1:{config.porta}", "localhost", "127.0.0.1"}

    @app.middleware("http")
    async def protecao(request: Request, chamar_proximo: Callable):
        if request.headers.get("host", "") not in hosts:
            return JSONResponse({"erro": "endereço não permitido"}, status_code=400)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-orca") != "1":
            return JSONResponse({"erro": "pedido sem o cabeçalho X-Orca"}, status_code=403)
        return await chamar_proximo(request)

    def _erro(status: int):
        async def tratar(_request: Request, erro: Exception):
            return JSONResponse({"erro": str(erro)}, status_code=status)
        return tratar

    for classe in (ErroAcao, ErroCorrespondencia, ErroTarefa, ErroAuditoria, ValueError):
        app.add_exception_handler(classe, _erro(400))
    app.add_exception_handler(ErroDossie, _erro(409))

    async def erro_http(_request: Request, erro: ErroHttp):
        return JSONResponse({"erro": erro.detail}, status_code=erro.status_code)

    async def dados_invalidos(_request: Request, erro: RequestValidationError):
        return JSONResponse({"erro": "dados inválidos", "detalhes": jsonable_encoder(erro.errors())}, status_code=422)

    app.add_exception_handler(ErroHttp, erro_http)
    app.add_exception_handler(RequestValidationError, dados_invalidos)
    app.add_exception_handler(ErroIntegridade, _erro(409))
    app.add_exception_handler(IntegrityError, lambda r, erro: JSONResponse(
        {"erro": "o banco recusou a gravação (dados inconsistentes)", "detalhe": str(erro.orig)}, status_code=400))

    _rotas_gerais(app, servico)
    _rotas_de_cadastro(app, servico)
    _rotas_de_pesquisa(app, servico)
    _rotas_de_resultado(app, servico)

    if (ESTATICO / "index.html").exists():
        app.mount("/", StaticFiles(directory=ESTATICO, html=True), name="interface")
    else:
        @app.get("/", response_class=HTMLResponse)
        def inicio():
            return "<h1>Orça.AI</h1><p>A interface ainda não foi compilada. A API está em <a href='/api/docs'>/api/docs</a>.</p>"
    return app


# --- Gerais ----------------------------------------------------------------------------------------


def _rotas_gerais(app: FastAPI, sv: Servico) -> None:
    @app.get("/api/situacao")
    def situacao():
        return {"sistema": "Orça.AI", "versao": versao_do_sistema(), "usuario": sv.config.usuario,
                "pasta_dados": str(sv.config.pasta), "hoje": sv.contexto.hoje().isoformat()}

    @app.get("/api/catalogos/jornadas")
    def jornadas():
        return [{"id": j.id, "descricao": j.descricao, "semanal_horas": j.jornada_semanal_horas,
                 "divisor": j.jornada_semanal_horas * j.fator_divisor, "fonte_legal": j.fonte_legal}
                for j in sv.contexto.jornadas.values()]

    @app.get("/api/catalogos/categorias")
    def categorias():
        v = sv.contexto.vocabulario
        return [{"id": c, "atributos": list(v.atributos_da_categoria(c) or ())} for c in v.categorias]

    @app.get("/api/catalogos/lojas")
    def lojas():
        return [{"id": l.id, "nome": l.nome, "dominio": l.dominio, "tipo": l.tipo, "coleta": l.coleta,
                 "marketplace": l.marketplace, "preco_a_usar": l.preco_a_usar}
                for l in sv.contexto.catalogo.values()]

    @app.get("/api/tarefas")
    def tarefas(projeto_id: str | None = None, limite: int = 50):
        with sv.sessao() as s:
            consulta = select(Tarefa).order_by(Tarefa.criado_em.desc()).limit(limite)
            if projeto_id:
                consulta = consulta.where(Tarefa.projeto_id == projeto_id)
            return [ap.tarefa_json(t) for t in s.scalars(consulta)]

    @app.get("/api/tarefas/{tarefa_id}")
    def tarefa(tarefa_id: str):
        with sv.sessao() as s:
            t = s.get(Tarefa, tarefa_id)
            if t is None:
                raise HTTPException(404, "tarefa não encontrada")
            return ap.tarefa_json(t)


# --- Cadastro: organizações, projetos, orçamentos, lotes, itens, cargos -------------------------------


def _rotas_de_cadastro(app: FastAPI, sv: Servico) -> None:
    @app.get("/api/organizacoes")
    def organizacoes():
        with sv.sessao() as s:
            return [{"id": o.id, "nome": o.nome, "cnpj": o.cnpj} for o in s.scalars(select(Organizacao).order_by(Organizacao.nome))]

    @app.post("/api/organizacoes", status_code=201)
    def nova_organizacao(dados: e.NovaOrganizacao):
        with sv.sessao() as s:
            org = Organizacao(nome=dados.nome, cnpj=dados.cnpj or None)
            s.add(org)
            s.flush()
            return {"id": org.id, "nome": org.nome, "cnpj": org.cnpj}

    @app.get("/api/projetos")
    def projetos(arquivados: bool = False):
        with sv.sessao() as s:
            consulta = select(Projeto).where(Projeto.excluido_em.is_(None)).order_by(Projeto.criado_em.desc())
            if not arquivados:
                consulta = consulta.where(Projeto.arquivado_em.is_(None))
            return [ap.projeto_json(p) for p in s.scalars(consulta)]

    @app.post("/api/projetos", status_code=201)
    def novo_projeto(dados: e.NovoProjeto):
        with sv.sessao() as s:
            org = _obter(s, Organizacao, dados.organizacao_id, "Organização")
            projeto = Projeto(organizacao=org, **dados.model_dump(exclude={"organizacao_id"}))
            s.add(projeto)
            definir_camadas_do_projeto(s, projeto)
            s.flush()
            return ap.projeto_completo_json(projeto)

    @app.get("/api/projetos/{projeto_id}")
    def projeto(projeto_id: str):
        with sv.sessao() as s:
            return ap.projeto_completo_json(_obter(s, Projeto, projeto_id, "Projeto"))

    @app.patch("/api/projetos/{projeto_id}")
    def mudar_projeto(projeto_id: str, dados: e.MudancaProjeto):
        with sv.sessao() as s:
            p = _obter(s, Projeto, projeto_id, "Projeto")
            _aplicar(p, dados.model_dump(exclude_unset=True))
            s.flush()
            return ap.projeto_completo_json(p)

    @app.post("/api/projetos/{projeto_id}/arquivar")
    def arquivar(projeto_id: str):
        with sv.sessao() as s:
            _obter(s, Projeto, projeto_id, "Projeto").arquivado_em = agora()
            return {"ok": True}

    @app.post("/api/projetos/{projeto_id}/desarquivar")
    def desarquivar(projeto_id: str):
        with sv.sessao() as s:
            _obter(s, Projeto, projeto_id, "Projeto").arquivado_em = None
            return {"ok": True}

    def _excluir(classe, nome: str):
        def excluir(id_: str):
            with sv.sessao() as s:
                _obter(s, classe, id_, nome).excluido_em = agora()  # exclusão lógica: o histórico fica
                return {"ok": True}
        return excluir

    for rota, classe, nome in (("projetos", Projeto, "Projeto"), ("orcamentos", Orcamento, "Orçamento"),
                               ("lotes", Lote, "Lote"), ("itens", Item, "Item"), ("cargos", Cargo, "Cargo")):
        app.post(f"/api/{rota}/{{id_}}/excluir", name=f"excluir_{rota}")(_excluir(classe, nome))

    @app.post("/api/projetos/{projeto_id}/orcamentos", status_code=201)
    def novo_orcamento(projeto_id: str, dados: e.NovoOrcamento):
        with sv.sessao() as s:
            o = Orcamento(projeto=_obter(s, Projeto, projeto_id, "Projeto"), **dados.model_dump())
            s.add(o)
            s.flush()
            return ap.orcamento_json(o)

    @app.patch("/api/orcamentos/{orcamento_id}")
    def mudar_orcamento(orcamento_id: str, dados: e.MudancaOrcamento):
        with sv.sessao() as s:
            o = _obter(s, Orcamento, orcamento_id, "Orçamento")
            _aplicar(o, dados.model_dump(exclude_unset=True))
            s.flush()
            return ap.orcamento_json(o)

    @app.post("/api/orcamentos/{orcamento_id}/lotes", status_code=201)
    def novo_lote(orcamento_id: str, dados: e.NovoLote):
        with sv.sessao() as s:
            lote = Lote(orcamento=_obter(s, Orcamento, orcamento_id, "Orçamento"), nome=dados.nome)
            s.add(lote)
            s.flush()
            return ap.lote_json(lote)

    @app.patch("/api/lotes/{lote_id}")
    def mudar_lote(lote_id: str, dados: e.NovoLote):
        with sv.sessao() as s:
            lote = _obter(s, Lote, lote_id, "Lote")
            lote.nome = dados.nome
            s.flush()
            return ap.lote_json(lote)

    @app.post("/api/lotes/{lote_id}/itens", status_code=201)
    def novo_item(lote_id: str, dados: e.NovoItem):
        with sv.sessao() as s:
            valores = {k: v for k, v in dados.model_dump().items() if v is not None}
            item = Item(lote=_obter(s, Lote, lote_id, "Lote"), **valores)
            s.add(item)
            s.flush()
            return ap.item_json(item)

    @app.patch("/api/itens/{item_id}")
    def mudar_item(item_id: str, dados: e.DadosItem):
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            mudancas = dados.model_dump(exclude_unset=True)
            pesquisado = s.scalars(select(Observacao.id).where(Observacao.item_id == item.id)).first() is not None
            if pesquisado and CAMPOS_DA_ESPECIFICACAO & set(mudancas):
                raise HTTPException(409, "O item já foi pesquisado: para mudar o produto, use “trocar produto” "
                                         "(o item antigo e as pesquisas ficam no histórico).")
            _aplicar(item, mudancas)
            s.flush()
            return ap.item_json(item)

    @app.post("/api/itens/{item_id}/trocar-produto", status_code=201)
    def trocar_produto(item_id: str, dados: e.TrocaDeProduto):
        with sv.sessao() as s:
            mudancas = dados.model_dump(exclude_unset=True, exclude={"justificativa"})
            novo = substituir_item(s, _obter(s, Item, item_id, "Item"), dados.justificativa, **mudancas)
            return ap.item_json(novo)

    @app.post("/api/orcamentos/{orcamento_id}/cargos", status_code=201)
    def novo_cargo(orcamento_id: str, dados: e.NovoCargo):
        with sv.sessao() as s:
            valores = {k: v for k, v in dados.model_dump().items() if v is not None}
            cargo = Cargo(orcamento=_obter(s, Orcamento, orcamento_id, "Orçamento"), **valores)
            s.add(cargo)
            s.flush()
            return ap.cargo_json(cargo)

    @app.patch("/api/cargos/{cargo_id}")
    def mudar_cargo(cargo_id: str, dados: e.DadosCargo):
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            _aplicar(cargo, dados.model_dump(exclude_unset=True))
            s.flush()
            return ap.cargo_json(cargo)


# --- Pesquisa: coletas, observações, correspondência, decisões ------------------------------------------


def _rotas_de_pesquisa(app: FastAPI, sv: Servico) -> None:
    def _projeto_do_item(item: Item) -> str:
        return item.lote.orcamento.projeto_id

    @app.post("/api/itens/{item_id}/coletas", status_code=202)
    def coletar_item(item_id: str, dados: e.ColetaDeItem):
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            t = sv.fila.enfileirar(s, "coletar_item", {"item_id": item.id, **dados.model_dump(exclude_none=True)},
                                   _projeto_do_item(item))
            s.flush()
            return ap.tarefa_json(t)

    @app.post("/api/cargos/{cargo_id}/coletas", status_code=202)
    def coletar_cargo(cargo_id: str, dados: e.ColetaDeCargo):
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            t = sv.fila.enfileirar(s, "coletar_cargo", {"cargo_id": cargo.id, **dados.model_dump(exclude_none=True)},
                                   cargo.orcamento.projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.get("/api/itens/{item_id}/observacoes")
    def observacoes_do_item(item_id: str):
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            regras = perfil_do_projeto(s, item.lote.orcamento.projeto).regras
            obs = s.scalars(select(Observacao).where(Observacao.item_id == item.id).order_by(Observacao.coletado_em.desc()))
            return [ap.observacao_json(o, ap.correspondencia_json(correspondencia_vigente(s, item.id, o.id), regras))
                    for o in obs]

    @app.get("/api/cargos/{cargo_id}/observacoes")
    def observacoes_do_cargo(cargo_id: str):
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            obs = s.scalars(select(Observacao).where(Observacao.cargo_id == cargo.id).order_by(Observacao.coletado_em.desc()))
            return [ap.observacao_json(o) for o in obs]

    @app.post("/api/correspondencias", status_code=201)
    def decidir(dados: e.DecisaoDeCorrespondencia):
        with sv.sessao() as s:
            item = _obter(s, Item, dados.item_id, "Item")
            obs = s.get(Observacao, dados.observacao_id)
            if obs is None or obs.item_id != item.id:
                raise HTTPException(404, "Observação não encontrada para este item")
            c = decidir_correspondencia(s, item, obs, dados.status, dados.justificativa)
            s.flush()
            regras = perfil_do_projeto(s, item.lote.orcamento.projeto).regras
            return ap.correspondencia_json(c, regras)

    @app.post("/api/lotes/{lote_id}/retirar-loja", status_code=201)
    def retirar(lote_id: str, dados: e.DecisaoDeLoja):
        with sv.sessao() as s:
            d = retirar_loja(s, _obter(s, Lote, lote_id, "Lote"), dados.loja, dados.justificativa)
            s.flush()
            return {"decisao_id": d.id}

    @app.post("/api/lotes/{lote_id}/devolver-loja", status_code=201)
    def devolver(lote_id: str, dados: e.DecisaoDeLoja):
        with sv.sessao() as s:
            d = devolver_loja(s, _obter(s, Lote, lote_id, "Lote"), dados.loja, dados.justificativa)
            s.flush()
            return {"decisao_id": d.id}

    @app.get("/api/lotes/{lote_id}/simular-troca-de-loja")
    def simular(lote_id: str):
        with sv.sessao() as s:
            lote = _obter(s, Lote, lote_id, "Lote")
            estado = sv.estado(s, lote.orcamento.projeto)
            for o, estado_lote in estado.lotes():
                if estado_lote.lote.id == lote.id:
                    r = simular_troca_de_loja(estado_lote, ParametrosSelecao.de_regras(o.perfil.regras))
                    return {
                        "sucesso": r.sucesso, "mensagem": r.mensagem,
                        "tentativas": [{"retirada": t.removida.nome, "loja": t.removida.id, "motivo": t.motivo}
                                       for t in r.tentativas],
                        "escolhida_final": r.final.escolhida.nome if r.final else None,
                    }
            raise HTTPException(404, "Lote não encontrado")

    @app.post("/api/cargos/{cargo_id}/mesma-vaga", status_code=201)
    def mesma_vaga(cargo_id: str, dados: e.MesmaVaga):
        with sv.sessao() as s:
            d = marcar_mesma_vaga(s, _obter(s, Cargo, cargo_id, "Cargo"), dados.a, dados.b, dados.justificativa)
            s.flush()
            return {"decisao_id": d.id}


# --- Resultado: revisão, painel, teto, CNPJ, exportação, histórico, arquivos ------------------------------


def _rotas_de_resultado(app: FastAPI, sv: Servico) -> None:
    @app.get("/api/projetos/{projeto_id}/revisao")
    def revisao(projeto_id: str):
        with sv.sessao() as s:
            estado = sv.estado(s, _obter(s, Projeto, projeto_id, "Projeto"))
            execucao = execucao_vigente(s, estado)
            return ap.revisao_json(estado, painel(estado, execucao, montar_problema(estado).pendencias))

    @app.get("/api/projetos/{projeto_id}/painel")
    def painel_do_projeto(projeto_id: str):
        with sv.sessao() as s:
            estado = sv.estado(s, _obter(s, Projeto, projeto_id, "Projeto"))
            execucao = execucao_vigente(s, estado)
            return ap.painel_json(painel(estado, execucao, montar_problema(estado).pendencias))

    @app.post("/api/projetos/{projeto_id}/fechar-teto", status_code=202)
    def fechar_teto(projeto_id: str):
        with sv.sessao() as s:
            _obter(s, Projeto, projeto_id, "Projeto")
            t = sv.fila.enfileirar(s, "fechar_teto", {"projeto_id": projeto_id}, projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.get("/api/projetos/{projeto_id}/otimizacao")
    def otimizacao(projeto_id: str):
        with sv.sessao() as s:
            estado = sv.estado(s, _obter(s, Projeto, projeto_id, "Projeto"))
            vigente = execucao_vigente(s, estado)
            ultima = s.scalars(select(ExecucaoOtimizacao).where(ExecucaoOtimizacao.projeto_id == projeto_id)
                               .order_by(ExecucaoOtimizacao.criado_em.desc())).first()
            return {"ultima": ap.execucao_json(ultima, vigente is not None and ultima is not None and vigente.id == ultima.id),
                    "pendencias": list(montar_problema(estado).pendencias)}

    @app.post("/api/projetos/{projeto_id}/consultar-cnpjs", status_code=202)
    def consultar_cnpjs(projeto_id: str):
        with sv.sessao() as s:
            estado = sv.estado(s, _obter(s, Projeto, projeto_id, "Projeto"))
            pendentes = list(painel(estado, None).cnpjs_sem_consulta)
            if not pendentes:
                return {"mensagem": "todos os CNPJs já foram consultados"}
            t = sv.fila.enfileirar(s, "consultar_cnpj", {"cnpjs": pendentes}, projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.get("/api/projetos/{projeto_id}/comprovantes-pendentes")
    def comprovantes(projeto_id: str):
        with sv.sessao() as s:
            projeto = _obter(s, Projeto, projeto_id, "Projeto")
            estado = sv.estado(s, projeto)
            cnpjs = sorted({o.cnpj_vendedor for _, l in estado.lotes() for o in l.observacoes.values() if o.cnpj_vendedor}
                           | {o.cnpj_vendedor for _, c in estado.cargos() for o in c.anuncios.values() if o.cnpj_vendedor})
            dias = estado.perfil.regras.evidencia.reaproveitar_comprovante_dias
            return {"pendentes": comprovantes_pendentes(s, cnpjs, estado.hoje, dias)}

    @app.get("/api/projetos/{projeto_id}/conformidade")
    def conformidade(projeto_id: str):
        """A conferência de cada regra (a mesma do relatório do pacote), antes de gerar os documentos."""
        with sv.sessao() as s:
            estado = sv.estado(s, _obter(s, Projeto, projeto_id, "Projeto"))
            try:
                dossie = dossie_do_projeto(s, estado, execucao_vigente(s, estado))
            except ErroDossie as erro:
                return {"conferencias": [], "pendencias": str(erro)}
            return {"conferencias": [{"regra": c.regra, "situacao": c.situacao, "detalhes": list(c.detalhes)}
                                     for c in conferir(dossie, estado.hoje)], "pendencias": None}

    @app.post("/api/projetos/{projeto_id}/exportar", status_code=202)
    def exportar(projeto_id: str):
        with sv.sessao() as s:
            _obter(s, Projeto, projeto_id, "Projeto")
            t = sv.fila.enfileirar(s, "exportar", {"projeto_id": projeto_id}, projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.get("/api/projetos/{projeto_id}/exportacoes")
    def exportacoes(projeto_id: str):
        with sv.sessao() as s:
            tarefas = s.scalars(select(Tarefa).where(Tarefa.projeto_id == projeto_id, Tarefa.tipo == "exportar",
                                                     Tarefa.estado == "concluida").order_by(Tarefa.concluida_em.desc()))
            return [{"arquivo": t.resultado["arquivo"], "bytes": t.resultado["bytes"],
                     "total_centavos": t.resultado["total_centavos"], "gerado_em": ap._data(t.concluida_em)}
                    for t in tarefas]

    @app.get("/api/arquivos/{caminho:path}")
    def arquivo(caminho: str):
        raiz = sv.config.pasta.resolve()
        destino = (raiz / caminho).resolve()
        if raiz not in destino.parents or not destino.is_file() or not destino.is_relative_to(raiz / "exportacoes"):
            raise HTTPException(404, "Arquivo não encontrado")
        return FileResponse(destino, filename=destino.name)

    @app.get("/api/evidencias/{evidencia_id}/{tipo}")
    def evidencia(evidencia_id: str, tipo: str):
        if tipo not in TIPOS_DE_EVIDENCIA:
            raise HTTPException(404, "Tipo de evidência desconhecido")
        atributo, mime = TIPOS_DE_EVIDENCIA[tipo]
        with sv.sessao() as s:
            ev = s.get(Evidencia, evidencia_id)
            arquivo = getattr(ev, atributo) if ev else None
            if arquivo is None:
                raise HTTPException(404, "Evidência não encontrada")
            conteudo = sv.contexto.armazem.ler(arquivo.caminho)  # confere a impressão digital
            return Response(conteudo, media_type=mime,
                            headers={"Content-Disposition": f'inline; filename="evidencia-{evidencia_id[:8]}.{tipo}"'})

    @app.get("/api/projetos/{projeto_id}/historico")
    def historico(projeto_id: str, limite: int = 500):
        with sv.sessao() as s:
            _obter(s, Projeto, projeto_id, "Projeto")
            eventos = historico_do_projeto(s, projeto_id)[-limite:]
            return [{"id": ev.id, "criado_em": ap._data(ev.criado_em), "autor": ev.autor, "entidade": ev.entidade,
                     "entidade_id": ev.entidade_id, "acao": ev.acao, "antes": ev.antes, "depois": ev.depois}
                    for ev in reversed(eventos)]

    @app.get("/api/projetos/{projeto_id}/regras")
    def regras(projeto_id: str):
        with sv.sessao() as s:
            perfil = perfil_do_projeto(s, _obter(s, Projeto, projeto_id, "Projeto"))
            return {"impressao": perfil.impressao, "camadas": [c.nome for c in perfil.cadeia],
                    "regras": perfil.regras.model_dump(mode="json"), "origem": dict(perfil.origem)}


__all__ = ["Servico", "contexto_padrao", "criar_app"]
