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

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
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
    CatalogoCamada,
    ErroCorrespondencia,
    Evidencia,
    ExecucaoOtimizacao,
    Item,
    Lote,
    Observacao,
    Orcamento,
    Organizacao,
    ParReferencia,
    Projeto,
    Tarefa,
    abrir_banco,
    agora,
    correspondencia_vigente,
    corresponder,
    decidir_correspondencia,
    definir_camadas_do_projeto,
    definir_referencia,
    especificacao_do_item,
    perfil_do_orcamento,
    perfil_do_projeto,
    referencia_do_item,
    sessao_como,
)
from orca.coleta import (
    CATALOGO_PADRAO,
    LIMITE_PDF,
    Navegador,
    captura_de_pdf,
    comprovantes_pendentes,
    corrigir_preco,
    dominio_da_url,
    ler_atributos_dados,
    ler_comprovante_pdf,
    ler_catalogo,
    ler_catalogo_dados,
    ler_jornadas,
    ler_vocabulario,
    registrar_comprovante_enviado,
    url_do_comprovante,
)
from orca.busca import ler_plataformas, lojas_de_busca, plataforma_do_endereco, termo_de_busca
from orca.coleta.pendencias import vigentes
from orca.correspondencia import LEITORES, avaliar, pares_do_sistema
from orca.documentos import Renderizador, conferir
from orca.dominio import normalizar_cnpj
from orca.cofre import CHAVES, CofreDoWindows, ErroCofre
from orca.evidencias import ArmazemArquivos, ErroIntegridade
from orca.ia import ENDERECO_LOCAL, MODELO_GEMINI, ErroIA, provedor_configurado
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
    recomparar_item,
)
from orca.fluxo import catalogos as cat
from orca.fluxo import regras as rg
from orca.fluxo.fechamento import fechamento
from orca.fluxo.validade import como_refazer, pesquisas_a_refazer
from orca.selecao import ParametrosSelecao
from orca.tarefas import Contexto, ErroTarefa, Fila
from orca.tarefas.executores import registrar_cargo, registrar_item

ESTATICO = Path(__file__).parent / "estatico"
CAMPOS_DA_ESPECIFICACAO = {"descricao", "categoria", "marca", "modelo", "apresentacao", "atributos", "ean", "unidade"}
TIPOS_DE_EVIDENCIA = {"pdf": ("pdf", "application/pdf"), "png": ("png", "image/png"),
                      "mhtml": ("html", "multipart/related")}


class Servico:
    """O que as rotas usam: banco, armazém, fila e configuração."""

    def __init__(self, config: Configuracao, contexto: Contexto, fila: Fila,
                 guardar_config: Callable[[Configuracao], object] | None = None):
        self.config, self.contexto, self.fila = config, contexto, fila
        self.guardar_config = guardar_config  # None nos testes: nada é gravado no computador

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
        abrir_navegador_visivel=trocas.pop("abrir_navegador_visivel", None) or (lambda: Navegador(sem_janela=False)),
        cofre=trocas.pop("cofre", None) or CofreDoWindows(),
        ia=config.ia,
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


def criar_app(config: Configuracao, contexto: Contexto | None = None, iniciar_trabalhador: bool = True,
              guardar_config: Callable[[Configuracao], object] | None = None) -> FastAPI:
    contexto = contexto or contexto_padrao(config)
    fila = Fila(contexto)
    servico = Servico(config, contexto, fila, guardar_config)

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
    _rotas_de_captura(app, servico)
    _rotas_de_catalogos(app, servico)
    _rotas_de_opcionais(app, servico)

    if (ESTATICO / "index.html").exists():
        app.mount("/", StaticFiles(directory=ESTATICO, html=True), name="interface")
    else:
        @app.get("/", response_class=HTMLResponse)
        def inicio():
            return "<h1>Orça.AI</h1><p>A interface ainda não foi compilada. A API está em <a href='/api/docs'>/api/docs</a>.</p>"
    return app


# --- Opcionais: SerpApi e IA (Fase 2, etapa 15; D-50 a D-52) ------------------------------------------


def _estado_dos_opcionais(sv: Servico) -> dict:
    erro, chaves = None, dict.fromkeys(CHAVES, False)
    try:
        chaves = {nome: bool(sv.contexto.cofre.ler(nome)) for nome in CHAVES} if sv.contexto.cofre else chaves
    except ErroCofre as e_:
        erro = str(e_)
    ia = sv.contexto.ia
    return {"serpapi": {"chave": chaves["serpapi"]},
            "ia": {"provedor": ia.provedor, "modelo": ia.modelo, "endereco": ia.endereco, "chave_gemini": chaves["gemini"],
                   "ligada": ia.provedor != "nenhum", "modelo_padrao": MODELO_GEMINI, "endereco_padrao": ENDERECO_LOCAL},
            "erro_cofre": erro}


def _rotas_de_opcionais(app: FastAPI, sv: Servico) -> None:
    @app.get("/api/opcionais")
    def opcionais():
        """O que está ligado. As chaves nunca voltam: só se existem."""
        return _estado_dos_opcionais(sv)

    @app.put("/api/opcionais")
    def mudar_opcionais(dados: e.Opcionais):
        cofre = sv.contexto.cofre
        try:
            for nome, valor in (("serpapi", dados.chave_serpapi), ("gemini", dados.chave_gemini)):
                if valor is None:
                    continue
                if valor:
                    cofre.gravar(nome, valor)
                else:
                    cofre.apagar(nome)
        except ErroCofre as erro:
            raise HTTPException(500, str(erro)) from erro
        ia = sv.contexto.ia
        if dados.ia_provedor is not None:
            ia.provedor = dados.ia_provedor
        if dados.ia_modelo is not None:
            ia.modelo = dados.ia_modelo
        if dados.ia_endereco is not None:
            ia.endereco = dados.ia_endereco
        sv.config.ia = ia
        if sv.guardar_config:
            sv.guardar_config(sv.config)
        return _estado_dos_opcionais(sv)

    @app.post("/api/opcionais/testar-ia")
    def testar_ia():
        """Um pedido sem dados (“responda {"ok": true}”), para conferir a chave, o modelo e a conexão."""
        cliente = sv.contexto.cliente_http() if sv.contexto.cliente_http else httpx.Client()
        try:
            provedor = provedor_configurado(sv.contexto.ia, sv.contexto.cofre, cliente)
            if provedor is None:
                raise HTTPException(409, "A IA está desligada.")
            resposta = provedor.responder_json('Responda só com este JSON: {"ok": true}')
        except ErroIA as erro:
            raise HTTPException(502, str(erro)) from erro
        finally:
            cliente.close()
        return {"ok": resposta.get("ok") is True, "mensagem": f"{provedor.nome} ({provedor.modelo}) respondeu."}

    @app.post("/api/lotes/{lote_id}/descobrir", status_code=202)
    def descobrir(lote_id: str, dados: e.PedidoDeDescoberta):
        """C2: procura páginas do produto pela SerpApi. Só aponta links; a pessoa escolhe o que capturar."""
        with sv.sessao() as s:
            lote = _obter(s, Lote, lote_id, "Lote")
            if not _estado_dos_opcionais(sv)["serpapi"]["chave"]:
                raise HTTPException(409, "Falta a chave da SerpApi (em Opcionais).")
            t = sv.fila.enfileirar(s, "descobrir_na_web", {"lote_id": lote.id, "itens": dados.itens or []},
                                   lote.orcamento.projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.post("/api/cargos/{cargo_id}/vagas-google", status_code=202)
    def vagas_google(cargo_id: str, dados: e.BuscaNoGoogleVagas):
        """D-69 revista: procura o cargo no Google Vagas (SerpApi) e captura as vagas que podem ser abertas."""
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            if not _estado_dos_opcionais(sv)["serpapi"]["chave"]:
                raise HTTPException(409, "Falta a chave da SerpApi (em Opcionais).")
            t = sv.fila.enfileirar(s, "descobrir_vagas", {"cargo_id": cargo.id, "cidade": dados.cidade, "uf": dados.uf},
                                   cargo.orcamento.projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.post("/api/projetos/{projeto_id}/julgar-amarelos", status_code=202)
    def julgar_amarelos(projeto_id: str):
        """A IA confere os 🟡 do projeto: mantém ou rebaixa para 🔴, nunca aprova (D-52)."""
        with sv.sessao() as s:
            projeto = _obter(s, Projeto, projeto_id, "Projeto")
            if sv.contexto.ia.provedor == "nenhum":
                raise HTTPException(409, "A IA está desligada (em Opcionais).")
            t = sv.fila.enfileirar(s, "julgar_amarelos", {"projeto_id": projeto.id}, projeto.id)
            s.flush()
            return ap.tarefa_json(t)


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
    def categorias(organizacao_id: str | None = None):
        with sv.sessao() as s:
            v = cat.vocabulario_da_organizacao(s, organizacao_id)
        return [{"id": c, "atributos": list(v.atributos_da_categoria(c) or ())} for c in v.categorias]

    @app.get("/api/catalogos/lojas")
    def lojas(organizacao_id: str | None = None):
        with sv.sessao() as s:
            catalogo = cat.catalogo_da_organizacao(s, organizacao_id)
        return [{"id": l.id, "nome": l.nome, "dominio": l.dominio, "tipo": l.tipo, "coleta": l.coleta,
                 "marketplace": l.marketplace, "preco_a_usar": l.preco_a_usar}
                for l in catalogo.values()]

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
        """Página de uma vaga. Em plataformas que proíbem programas (D-69), abre na janela, com a pessoa."""
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            plataforma = plataforma_do_endereco(dados.url, ler_plataformas())
            tipo = "captura_assistida" if plataforma is not None and plataforma.abrir_vaga == "janela" else "coletar_cargo"
            t = sv.fila.enfileirar(s, tipo, {"cargo_id": cargo.id, **dados.model_dump(exclude_none=True)},
                                   cargo.orcamento.projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.get("/api/plataformas-de-vagas")
    def plataformas_de_vagas():
        return [{"id": p.id, "nome": p.nome, "dominio": p.dominio, "abrir_vaga": p.abrir_vaga, "motivo": p.motivo}
                for p in ler_plataformas()]

    @app.post("/api/cargos/{cargo_id}/busca-de-vagas", status_code=202)
    def buscar_vagas(cargo_id: str, dados: e.BuscaDeVagas):
        """Uma janela por plataforma, na busca já preenchida; a pessoa escolhe a vaga (D-69)."""
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            escolhidas = [p for p in ler_plataformas() if p.id in set(dados.plataformas)]
            if not escolhidas:
                raise HTTPException(400, "Escolha ao menos uma plataforma.")
            tarefas = [sv.fila.enfileirar(s, "captura_assistida",
                                          {"cargo_id": cargo.id, "url": p.endereco(cargo.nome, dados.cidade, dados.uf)},
                                          cargo.orcamento.projeto_id) for p in escolhidas]
            s.flush()
            return {"tarefas": [ap.tarefa_json(t) for t in tarefas]}

    @app.get("/api/itens/{item_id}/observacoes")
    def observacoes_do_item(item_id: str):
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            regras = perfil_do_projeto(s, item.lote.orcamento.projeto).regras
            obs = s.scalars(select(Observacao).where(Observacao.item_id == item.id).order_by(Observacao.coletado_em.desc(), Observacao.criado_em.desc()))
            return [ap.observacao_json(o, ap.correspondencia_json(correspondencia_vigente(s, item.id, o.id), regras))
                    for o in obs]

    @app.get("/api/cargos/{cargo_id}/observacoes")
    def observacoes_do_cargo(cargo_id: str):
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            obs = s.scalars(select(Observacao).where(Observacao.cargo_id == cargo.id).order_by(Observacao.coletado_em.desc(), Observacao.criado_em.desc()))
            return [ap.observacao_json(o) for o in obs]

    def _recomparar(item_id: str) -> int:
        """A referência do item mudou: as páginas que uma pessoa não decidiu são comparadas de novo (D-71)."""
        with sessao_como(sv.contexto.fabrica, "sistema:referencia") as s:
            item = s.get(Item, item_id)
            vocabulario = cat.vocabulario_da_organizacao(s, item.lote.orcamento.projeto.organizacao_id)
            return len(recomparar_item(s, item, vocabulario))

    @app.post("/api/correspondencias", status_code=201)
    def decidir(dados: e.DecisaoDeCorrespondencia):
        with sv.sessao() as s:
            item = _obter(s, Item, dados.item_id, "Item")
            obs = s.get(Observacao, dados.observacao_id)
            if obs is None or obs.item_id != item.id:
                raise HTTPException(404, "Observação não encontrada para este item")
            antes = referencia_do_item(s, item)
            c = decidir_correspondencia(s, item, obs, dados.status, dados.justificativa)
            s.flush()
            cat.par_da_decisao(s, c)  # D-64: a decisão ensina o teste de correspondência
            if c.status == "verde" and antes is None:  # D-71: a primeira página confirmada vira a referência
                definir_referencia(s, item, obs, "primeira página confirmada como o mesmo produto (D-71)")
                s.flush()
            depois = referencia_do_item(s, item)
            mudou = (antes.id if antes else None) != (depois.id if depois else None)
            regras = perfil_do_projeto(s, item.lote.orcamento.projeto).regras
            resposta = ap.correspondencia_json(c, regras)
            item_id = item.id
        return resposta | {"referencia_mudou": mudou, "recomparadas": _recomparar(item_id) if mudou else 0}

    @app.post("/api/itens/{item_id}/referencia", status_code=201)
    def escolher_referencia(item_id: str, dados: e.EscolhaDeReferencia):
        """Esta página é o produto do item (D-71): confirma, se preciso, e compara as outras lojas com ela."""
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            obs = s.get(Observacao, dados.observacao_id)
            if obs is None or obs.item_id != item.id or not obs.encontrado:
                raise HTTPException(404, "Observação não encontrada para este item")
            vigente = correspondencia_vigente(s, item.id, obs.id)
            if vigente is None or (vigente.status, vigente.origem) != ("verde", "humano"):
                c = decidir_correspondencia(s, item, obs, "verde", dados.justificativa)
                s.flush()
                cat.par_da_decisao(s, c)
            definir_referencia(s, item, obs, dados.justificativa)
            s.flush()
        return {"referencia": dados.observacao_id, "recomparadas": _recomparar(item_id)}

    @app.post("/api/observacoes/{observacao_id}/corrigir-preco", status_code=201)
    def corrigir(observacao_id: str, dados: e.CorrecaoDePreco):
        """Outro valor escrito na mesma página (ex.: o preço no Pix). A leitura anterior fica no histórico."""
        with sv.sessao() as s:
            anterior = s.get(Observacao, observacao_id)
            if anterior is None or anterior.item is None:
                raise HTTPException(404, "Observação não encontrada")
            item = anterior.item
            nova = corrigir_preco(s, sv.contexto.armazem, anterior, dados.preco_centavos, dados.justificativa)
            s.flush()
            decisao = correspondencia_vigente(s, item.id, anterior.id)
            if decisao is not None and decisao.origem == "humano":  # o produto é o mesmo: a decisão da pessoa continua
                decidir_correspondencia(s, item, nova, decisao.status,
                                        "mesmo produto já decidido nesta página; só o preço foi corrigido")
            else:
                corresponder(s, item, nova, cat.vocabulario_da_organizacao(s, item.lote.orcamento.projeto.organizacao_id))
            s.flush()
            regras = perfil_do_projeto(s, item.lote.orcamento.projeto).regras
            return ap.observacao_json(nova, ap.correspondencia_json(correspondencia_vigente(s, item.id, nova.id), regras))

    def _faltando_por_loja(s: Session, lote: Lote, lojas) -> dict[str, list[Item]]:
        """Itens do lote ainda sem página encontrada em cada loja."""
        itens = [i for i in lote.itens if i.excluido_em is None]
        obs = vigentes(s.scalars(select(Observacao).where(Observacao.item_id.in_([i.id for i in itens]))))
        achados = {(o.item_id, dominio_da_url(o.url)) for o in obs if o.encontrado}
        return {l.id: [i for i in itens if (i.id, dominio_da_url("https://" + l.dominio)) not in achados] for l in lojas}

    @app.get("/api/lotes/{lote_id}/lojas-de-busca")
    def lojas_para_buscar(lote_id: str):
        """As lojas que o sistema sabe pesquisar, com as sugeridas para as categorias do lote (D-68)."""
        with sv.sessao() as s:
            lote = _obter(s, Lote, lote_id, "Lote")
            lojas = lojas_de_busca(cat.lojas_da_organizacao(s, lote.orcamento.projeto.organizacao_id))
            categorias = {i.categoria for i in lote.itens if i.excluido_em is None}
            faltando = _faltando_por_loja(s, lote, lojas)
            return {"itens": sum(1 for i in lote.itens if i.excluido_em is None),
                    "lojas": [{"id": l.id, "nome": l.nome, "modo": l.modo, "sugerida": l.atende(categorias),
                               "faltam": len(faltando[l.id])} for l in lojas]}

    def _enfileirar_busca(lote_id: str, escolhidas: list[str], tipo: str) -> dict:
        """Busca automática nas lojas escolhidas; nas que recusam programas, uma captura com janela por item."""
        with sv.sessao() as s:
            lote = _obter(s, Lote, lote_id, "Lote")
            projeto_id = lote.orcamento.projeto_id
            lojas = [l for l in lojas_de_busca(cat.lojas_da_organizacao(s, lote.orcamento.projeto.organizacao_id))
                     if l.id in set(escolhidas)]
            if not lojas:
                raise HTTPException(400, "Nenhuma das lojas escolhidas tem busca configurada.")
            tarefas = []
            automaticas = [l.id for l in lojas if l.automatica]
            if automaticas:
                tarefas.append(sv.fila.enfileirar(s, tipo, {"lote_id": lote.id, "lojas": automaticas}, projeto_id))
            faltando = _faltando_por_loja(s, lote, lojas)
            for loja in (l for l in lojas if not l.automatica):
                for item in faltando[loja.id]:
                    url = loja.endereco(termo_de_busca(especificacao_do_item(item)))
                    tarefas.append(sv.fila.enfileirar(s, "captura_assistida", {"item_id": item.id, "url": url}, projeto_id))
            s.flush()
            return {"tarefas": [ap.tarefa_json(t) for t in tarefas]}

    @app.post("/api/lotes/{lote_id}/busca", status_code=202)
    def buscar(lote_id: str, dados: e.PedidoDeBusca):
        return _enfileirar_busca(lote_id, dados.lojas, "buscar_lote")

    @app.post("/api/lotes/{lote_id}/fechar", status_code=202)
    def fechar_lote(lote_id: str, dados: e.PedidoDeBusca):
        """D-72: pesquisa todos os itens e sugere a troca dos que faltam nas 3 lojas mais completas."""
        return _enfileirar_busca(lote_id, dados.lojas, "fechar_lote")

    @app.get("/api/lotes/{lote_id}/fechamento")
    def situacao_do_fechamento(lote_id: str):
        """O que falta para fechar o lote (ao vivo) e as sugestões da última vez que ele foi fechado (D-72)."""
        with sv.sessao() as s:
            lote = _obter(s, Lote, lote_id, "Lote")
            estado = sv.estado(s, lote.orcamento.projeto)
            orcamento, estado_lote = next((o, l) for o, l in estado.lotes() if l.lote.id == lote.id)
            f = fechamento(estado_lote, orcamento.perfil.regras)
            nomes = {i.id: i.descricao for i in estado_lote.itens}
            ultima = next((t for t in s.scalars(select(Tarefa).where(Tarefa.tipo == "fechar_lote")
                                                  .order_by(Tarefa.criado_em.desc()).limit(50))
                           if t.parametros.get("lote_id") == lote.id), None)
            return {
                "itens": len(nomes),
                "lojas": [{"id": l.id, "nome": l.nome, "tem": len(l.tem), "faltam": [nomes[i] for i in l.faltam]}
                          for l in f.lojas],
                "melhores": [l.id for l in f.melhores],
                "faltando": [{"item_id": i, "item": nomes[i], "lojas": list(lojas)} for i, lojas in f.faltando.items()],
                "a_confirmar": [{"item_id": i, "item": nomes[i]} for i in f.a_confirmar],
                "ultima": {"tarefa_id": ultima.id, "estado": ultima.estado, "mensagem": ultima.mensagem,
                           "progresso": ultima.progresso,
                           "alternativas": {i: o for i, o in ((ultima.resultado or {}).get("alternativas") or {}).items()
                                            if i in nomes},
                           "avisos": (ultima.resultado or {}).get("avisos", [])} if ultima else None,
            }

    @app.post("/api/itens/{item_id}/alternativas", status_code=202)
    def buscar_alternativas(item_id: str):
        """Saída 1 com busca (D-23): procura o item sem a marca nas 3 lojas do trio. Só mostra; não grava."""
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            t = sv.fila.enfileirar(s, "buscar_alternativas", {"item_id": item.id}, _projeto_do_item(item))
            s.flush()
            return ap.tarefa_json(t)

    @app.post("/api/itens/{item_id}/usar-alternativa", status_code=201)
    def usar_alternativa(item_id: str, dados: e.UsoDeAlternativa):
        """Troca o produto pela alternativa escolhida e captura as páginas dela nas lojas do trio (as provas)."""
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            t = s.get(Tarefa, dados.tarefa_id)
            deste_item = t is not None and (
                (t.tipo == "buscar_alternativas" and t.parametros.get("item_id") == item.id)
                or (t.tipo == "fechar_lote" and t.parametros.get("lote_id") == item.lote_id))  # D-72
            if not deste_item or t.estado != "concluida" or not t.resultado:
                raise HTTPException(409, "Essa busca de alternativas não é deste item ou não terminou.")
            opcoes = (t.resultado.get("opcoes", []) if t.tipo == "buscar_alternativas"
                      else (t.resultado.get("alternativas") or {}).get(item.id, []))
            if dados.indice >= len(opcoes):
                raise HTTPException(404, "Alternativa não encontrada")
            opcao = opcoes[dados.indice]
            novo = substituir_item(s, item, dados.justificativa, descricao=dados.descricao.strip(),
                                   marca=dados.marca.strip(), modelo=None, ean=None)
            tarefas = [sv.fila.enfileirar(s, "coletar_item", {"item_id": novo.id, "url": l["url"]}, _projeto_do_item(novo))
                       for l in opcao["lojas"] if l.get("url")]
            s.flush()
            return {"item": ap.item_json(novo), "tarefas": [ap.tarefa_json(x) for x in tarefas]}

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
            a_refazer = tuple(p.situacao.value for p in pesquisas_a_refazer(s, estado.projeto, estado.hoje))
            return ap.painel_json(painel(estado, execucao, montar_problema(estado).pendencias, a_refazer))

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
            pendentes = comprovantes_pendentes(s, cnpjs, estado.hoje, dias)
            return {"pendentes": pendentes, "paginas": {c: url_do_comprovante(c) for c in pendentes}}

    def _nome_do_alvo(obs: Observacao) -> str:
        return obs.item.descricao if obs.item_id else obs.cargo.nome

    @app.get("/api/projetos/{projeto_id}/validade")
    def validade_das_pesquisas(projeto_id: str):
        """Pesquisas em uso vencidas ou vencendo (D-12), com o jeito de pesquisar de novo."""
        with sv.sessao() as s:
            projeto = _obter(s, Projeto, projeto_id, "Projeto")
            lista = []
            for p in pesquisas_a_refazer(s, projeto, sv.contexto.hoje()):
                refazer = como_refazer(p.observacao)
                lista.append({
                    "observacao_id": p.observacao.id, "nome": _nome_do_alvo(p.observacao), "loja": p.observacao.fonte.nome,
                    "url": p.observacao.url, "coletado_em": ap._data(p.observacao.coletado_em),
                    "valida_ate": p.valida_ate.isoformat(), "situacao": p.situacao.value,
                    "como": refazer[0] if refazer else "pdf",
                })
            return {"pesquisas": lista}

    @app.post("/api/projetos/{projeto_id}/pesquisar-de-novo", status_code=202)
    def pesquisar_de_novo(projeto_id: str, dados: e.PesquisarDeNovo):
        """Pesquisa de novo as mesmas páginas (em um clique). A pesquisa anterior fica no histórico."""
        with sv.sessao() as s:
            projeto = _obter(s, Projeto, projeto_id, "Projeto")
            a_refazer = pesquisas_a_refazer(s, projeto, sv.contexto.hoje())
            escolhidas = [p.observacao for p in a_refazer if dados.observacoes is None or p.observacao.id in dados.observacoes]
            if dados.observacoes:  # uma pesquisa pedida pela pessoa, mesmo que ainda válida
                ids_a_refazer = {o.id for o in escolhidas}
                for obs_id in dados.observacoes:
                    obs = s.get(Observacao, obs_id)
                    if obs is not None and obs.id not in ids_a_refazer:
                        escolhidas.append(obs)
            tarefas, so_pela_pessoa = [], []
            for obs in escolhidas:
                refazer = como_refazer(obs)
                if refazer is None:
                    so_pela_pessoa.append(f"{_nome_do_alvo(obs)} ({obs.fonte.nome})")
                    continue
                tarefas.append(sv.fila.enfileirar(s, refazer[0], refazer[1], projeto_id))
            s.flush()
            return {"tarefas": [ap.tarefa_json(t) for t in tarefas], "so_pela_pessoa": so_pela_pessoa}

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
            projeto = _obter(s, Projeto, projeto_id, "Projeto")
            perfil = perfil_do_projeto(s, projeto)
            orcamentos = [{"id": o.id, "nome": o.nome, "proprias": rg.regras_proprias_do_orcamento(s, o),
                           "impressao": perfil_do_orcamento(s, o).impressao}
                          for o in projeto.orcamentos if o.excluido_em is None]
            return {"impressao": perfil.impressao, "camadas": [c.nome for c in perfil.cadeia],
                    "cadeia": [{"nome": c.nome, "nivel": c.nivel, "versao": c.versao} for c in perfil.cadeia],
                    "regras": perfil.regras.model_dump(mode="json"), "origem": dict(perfil.origem),
                    "proprias": rg.regras_proprias_do_projeto(s, projeto), "orcamentos": orcamentos}


# --- Captura assistida, PDF enviado e comprovantes (D-13, D-67) ------------------------------------------


def _rotas_de_captura(app: FastAPI, sv: Servico) -> None:
    def _tarefa(s: Session, tarefa_id: str) -> Tarefa:
        t = s.get(Tarefa, tarefa_id)
        if t is None:
            raise HTTPException(404, "tarefa não encontrada")
        return t

    @app.post("/api/tarefas/{tarefa_id}/capturar-agora")
    def capturar_agora(tarefa_id: str):
        with sv.sessao() as s:
            t = _tarefa(s, tarefa_id)
            if t.tipo != "captura_assistida" or t.estado != "esperando_usuario":
                raise HTTPException(409, "Esta tarefa não está esperando a captura.")
        sv.fila.capturar_agora(tarefa_id)
        return {"ok": True}

    @app.post("/api/tarefas/{tarefa_id}/cancelar")
    def cancelar(tarefa_id: str):
        with sv.sessao() as s:
            _tarefa(s, tarefa_id)
            t = sv.fila.cancelar(s, tarefa_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.post("/api/itens/{item_id}/captura-assistida", status_code=202)
    def assistida_do_item(item_id: str, dados: e.CapturaAssistida):
        with sv.sessao() as s:
            item = _obter(s, Item, item_id, "Item")
            t = sv.fila.enfileirar(s, "captura_assistida", {"item_id": item.id, **dados.model_dump(exclude_none=True)},
                                   item.lote.orcamento.projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    @app.post("/api/cargos/{cargo_id}/captura-assistida", status_code=202)
    def assistida_do_cargo(cargo_id: str, dados: e.CapturaAssistidaDeCargo):
        with sv.sessao() as s:
            cargo = _obter(s, Cargo, cargo_id, "Cargo")
            t = sv.fila.enfileirar(s, "captura_assistida", {"cargo_id": cargo.id, **dados.model_dump(exclude_none=True)},
                                   cargo.orcamento.projeto_id)
            s.flush()
            return ap.tarefa_json(t)

    def _ler_pdf(arquivo: UploadFile, url: str, titulo: str | None):
        if not url.startswith(("http://", "https://")):
            raise HTTPException(422, "informe o endereço (http:// ou https://) da página salva")
        conteudo = arquivo.file.read(LIMITE_PDF + 1)
        return captura_de_pdf(conteudo, url, agora(), titulo)

    @app.post("/api/itens/{item_id}/pdf", status_code=201)
    def pdf_do_item(item_id: str, arquivo: UploadFile = File(...), url: str = Form(...),
                    preco_centavos: int | None = Form(None), cnpj_vendedor: str | None = Form(None),
                    titulo: str | None = Form(None)):
        """PDF que o usuário salvou da página (lojas que recusam programas, D-67)."""
        with sv.sessao() as s:
            _obter(s, Item, item_id, "Item")
        if preco_centavos is not None and preco_centavos <= 0:
            raise HTTPException(422, "o preço deve ser maior que zero")
        captura, avisos = _ler_pdf(arquivo, url, titulo)
        return registrar_item(sv.contexto, {"item_id": item_id, "preco_centavos": preco_centavos,
                                            "cnpj_vendedor": cnpj_vendedor}, captura, sv.config.autor, avisos)

    @app.post("/api/cargos/{cargo_id}/pdf", status_code=201)
    def pdf_do_cargo(cargo_id: str, arquivo: UploadFile = File(...), url: str = Form(...),
                     salario_min_centavos: int | None = Form(None), salario_max_centavos: int | None = Form(None),
                     cnpj_empresa: str | None = Form(None), titulo: str | None = Form(None)):
        with sv.sessao() as s:
            _obter(s, Cargo, cargo_id, "Cargo")
        captura, avisos = _ler_pdf(arquivo, url, titulo)
        return registrar_cargo(sv.contexto, {"cargo_id": cargo_id, "salario_min_centavos": salario_min_centavos,
                                             "salario_max_centavos": salario_max_centavos, "cnpj_empresa": cnpj_empresa},
                               captura, sv.config.autor, avisos)

    @app.post("/api/comprovantes/pdf", status_code=201)
    def comprovante_enviado(arquivo: UploadFile = File(...), cnpj: str = Form(...)):
        """Comprovante emitido no navegador da pessoa e salvo em PDF (a Receita recusa a janela do sistema)."""
        cnpj = normalizar_cnpj(cnpj)
        conteudo = arquivo.file.read(5 * 1024 * 1024 + 1)
        emitido, avisos = ler_comprovante_pdf(conteudo, cnpj, agora())
        with sv.sessao() as s:
            registro = registrar_comprovante_enviado(s, sv.contexto.armazem, cnpj, conteudo, emitido)
            s.flush()
            return {"id": registro.id, "cnpj": cnpj, "emitido_em": ap._data(emitido), "avisos": list(avisos)}

    @app.post("/api/comprovantes", status_code=202)
    def emitir_comprovante(dados: e.PedidoDeComprovante):
        """Abre a página da Receita com o CNPJ preenchido; o usuário resolve a verificação (D-13)."""
        cnpj = normalizar_cnpj(dados.cnpj)
        with sv.sessao() as s:
            abertas = s.scalars(select(Tarefa).where(
                Tarefa.tipo == "comprovante", Tarefa.estado.in_(("pendente", "rodando", "esperando_usuario"))))
            repetida = next((t for t in abertas if t.parametros.get("cnpj") == cnpj), None)
            if repetida is not None:
                return ap.tarefa_json(repetida)
            t = sv.fila.enfileirar(s, "comprovante", {"cnpj": cnpj}, dados.projeto_id)
            s.flush()
            return ap.tarefa_json(t)


# --- Catálogos, vocabulário, pares e regras editados pela OSC (D-64 a D-66) -------------------------------


def _historico_do_catalogo(s: Session, organizacao_id: str, tipo: str) -> list[dict]:
    camadas = s.scalars(select(CatalogoCamada).where(CatalogoCamada.organizacao_id == organizacao_id,
                                                     CatalogoCamada.tipo == tipo).order_by(CatalogoCamada.versao.desc()))
    return [{"versao": c.versao, "criado_em": ap._data(c.criado_em), "autor": c.autor, "resumo": c.resumo}
            for c in camadas]


def _par_json(par, status: str | None) -> dict:
    erro = (par.rotulo == "diferente" and status == "verde") or (par.rotulo == "mesmo" and status == "vermelho")
    return {"id": par.id, "titulo_a": par.titulo_a, "marca_a": par.marca_a, "titulo_b": par.titulo_b,
            "marca_b": par.marca_b, "categoria": par.categoria, "rotulo": par.rotulo, "origem": par.origem,
            "motivo": getattr(par, "motivo", None), "status_atual": status, "erro": erro}


def _resumo_da_avaliacao(a) -> dict:
    return {"total": a.total, "contagem": a.contagem, "falsos_verdes": len(a.falsos_verdes),
            "iguais_recusados": len(a.iguais_recusados)}


def _rotas_de_catalogos(app: FastAPI, sv: Servico) -> None:
    def _org(s: Session, organizacao_id: str) -> Organizacao:
        return _obter(s, Organizacao, organizacao_id, "Organização")

    @app.get("/api/organizacoes/{organizacao_id}/catalogos/atributos")
    def atributos(organizacao_id: str):
        with sv.sessao() as s:
            _org(s, organizacao_id)
            camada = cat.camada_vigente(s, organizacao_id, "atributos")
            return {"versao": camada.versao if camada else 0, "mudancas": camada.conteudo if camada else {},
                    "vigente": cat.atributos_da_organizacao(s, organizacao_id), "sistema": ler_atributos_dados(),
                    "leitores": sorted(LEITORES), "so_por_pessoa": sorted(cat.SO_POR_PESSOA),
                    "historico": _historico_do_catalogo(s, organizacao_id, "atributos")}

    def _conferir(s: Session, organizacao_id: str, editado: dict) -> dict:
        mudancas = cat.diferenca_de_atributos(ler_atributos_dados(), editado)
        r = cat.avaliar_mudanca_de_atributos(s, organizacao_id, mudancas)
        mudaram = [
            {"titulo_a": p.titulo_a, "titulo_b": p.titulo_b, "rotulo": p.rotulo, "origem": p.origem,
             "antes": r.antes.resultados.get(p.id), "depois": r.depois.resultados.get(p.id)}
            for p in pares_do_sistema() + cat.pares_da_organizacao(s, organizacao_id)
            if r.antes.resultados.get(p.id) != r.depois.resultados.get(p.id)
        ]
        return {"aprovada": r.aprovada, "antes": _resumo_da_avaliacao(r.antes),
                "depois": _resumo_da_avaliacao(r.depois), "mudancas": mudancas,
                "novos_falsos_verdes": [{"titulo_a": p.titulo_a, "titulo_b": p.titulo_b} for p in r.novos_falsos_verdes],
                "pares_que_mudaram": mudaram}

    @app.post("/api/organizacoes/{organizacao_id}/catalogos/atributos/conferir")
    def conferir_atributos(organizacao_id: str, dados: e.CatalogoEditado):
        """Roda o teste de correspondência antes e depois da mudança (nada é gravado)."""
        with sv.sessao() as s:
            _org(s, organizacao_id)
            return _conferir(s, organizacao_id, dados.conteudo)

    def _sugestao(s: Session, organizacao_id: str, sugestao_id: str):
        for chave, par, sugestao in cat.sugestoes_da_organizacao(s, organizacao_id):
            if chave == sugestao_id:
                return par, sugestao
        raise HTTPException(404, "Sugestão não encontrada (o vocabulário pode já ter mudado).")

    @app.get("/api/organizacoes/{organizacao_id}/sugestoes")
    def sugestoes(organizacao_id: str):
        """Sugestões para o vocabulário a partir dos pares que o sistema ainda não acerta (D-65)."""
        with sv.sessao() as s:
            _org(s, organizacao_id)
            return [{"id": chave, "tipo": sug.tipo, "explicacao": sug.explicacao, "mudancas": sug.mudancas,
                     "par": {"titulo_a": par.titulo_a, "titulo_b": par.titulo_b, "rotulo": par.rotulo,
                             "origem": par.origem, "categoria": par.categoria}}
                    for chave, par, sug in cat.sugestoes_da_organizacao(s, organizacao_id)]

    @app.post("/api/organizacoes/{organizacao_id}/sugestoes/{sugestao_id}/conferir")
    def conferir_sugestao(organizacao_id: str, sugestao_id: str):
        with sv.sessao() as s:
            _org(s, organizacao_id)
            _, sugestao = _sugestao(s, organizacao_id, sugestao_id)
            return _conferir(s, organizacao_id, cat.catalogo_com_sugestao(s, organizacao_id, sugestao))

    @app.post("/api/organizacoes/{organizacao_id}/sugestoes/{sugestao_id}/aplicar")
    def aplicar_sugestao(organizacao_id: str, sugestao_id: str):
        """Grava a sugestão no catálogo da OSC, só se o teste não criar nenhum 🟢 errado novo (D-65)."""
        with sv.sessao() as s:
            _org(s, organizacao_id)
            _, sugestao = _sugestao(s, organizacao_id, sugestao_id)
            editado = cat.catalogo_com_sugestao(s, organizacao_id, sugestao)
            mudancas = cat.diferenca_de_atributos(ler_atributos_dados(), editado)
            camada = cat.salvar_atributos(s, organizacao_id, mudancas, f"sugestão aprovada: {sugestao.explicacao}")
            s.flush()
            return {"versao": camada.versao, "mudancas": camada.conteudo}

    @app.put("/api/organizacoes/{organizacao_id}/catalogos/atributos")
    def salvar_atributos(organizacao_id: str, dados: e.CatalogoEditado):
        with sv.sessao() as s:
            _org(s, organizacao_id)
            mudancas = cat.diferenca_de_atributos(ler_atributos_dados(), dados.conteudo)
            camada = cat.salvar_atributos(s, organizacao_id, mudancas, dados.resumo)
            s.flush()
            return {"versao": camada.versao, "mudancas": camada.conteudo}

    @app.get("/api/organizacoes/{organizacao_id}/catalogos/lojas")
    def catalogo_de_lojas(organizacao_id: str):
        with sv.sessao() as s:
            _org(s, organizacao_id)
            camada = cat.camada_vigente(s, organizacao_id, "lojas")
            return {"versao": camada.versao if camada else 0, "mudancas": camada.conteudo if camada else {},
                    "vigente": cat.lojas_da_organizacao(s, organizacao_id), "coletas": list(cat.COLETAS),
                    "historico": _historico_do_catalogo(s, organizacao_id, "lojas")}

    @app.put("/api/organizacoes/{organizacao_id}/catalogos/lojas")
    def salvar_lojas(organizacao_id: str, dados: e.CatalogoEditado):
        with sv.sessao() as s:
            _org(s, organizacao_id)
            mudancas = cat.diferenca_de_lojas(ler_catalogo_dados(), dados.conteudo)
            camada = cat.salvar_lojas(s, organizacao_id, mudancas, dados.resumo)
            s.flush()
            return {"versao": camada.versao, "mudancas": camada.conteudo}

    @app.get("/api/organizacoes/{organizacao_id}/pares")
    def pares(organizacao_id: str):
        """Os pares da OSC com o resultado atual da correspondência, e o resumo do teste completo."""
        with sv.sessao() as s:
            _org(s, organizacao_id)
            vocabulario = cat.vocabulario_da_organizacao(s, organizacao_id)
            registros = list(s.scalars(select(ParReferencia).where(
                ParReferencia.organizacao_id == organizacao_id, ParReferencia.excluido_em.is_(None))
                .order_by(ParReferencia.criado_em.desc())))
            da_osc = cat.pares_da_organizacao(s, organizacao_id)
            avaliacao_osc = avaliar(da_osc, vocabulario)
            avaliacao_sistema = avaliar(pares_do_sistema(), vocabulario)
            return {"pares": [_par_json(r, avaliacao_osc.resultados.get(r.id)) for r in registros],
                    "resumo_osc": _resumo_da_avaliacao(avaliacao_osc),
                    "resumo_sistema": _resumo_da_avaliacao(avaliacao_sistema)}

    @app.post("/api/organizacoes/{organizacao_id}/pares", status_code=201)
    def novo_par(organizacao_id: str, dados: e.NovoPar):
        with sv.sessao() as s:
            _org(s, organizacao_id)
            par = cat.adicionar_par(s, organizacao_id, **dados.model_dump())
            s.flush()
            status = avaliar([cat.par_de(par)], cat.vocabulario_da_organizacao(s, organizacao_id)).resultados
            return _par_json(par, status.get(par.id))

    @app.post("/api/pares/{par_id}/retirar")
    def retirar_par(par_id: str):
        with sv.sessao() as s:
            cat.retirar_par(s, _obter(s, ParReferencia, par_id, "Par"))
            return {"ok": True}

    @app.put("/api/projetos/{projeto_id}/regras")
    def salvar_regras_do_projeto(projeto_id: str, dados: e.RegrasProprias):
        with sv.sessao() as s:
            perfil = rg.salvar_regras_do_projeto(s, _obter(s, Projeto, projeto_id, "Projeto"), dados.conteudo)
            s.flush()
            return {"impressao": perfil.impressao}

    @app.put("/api/orcamentos/{orcamento_id}/regras")
    def salvar_regras_do_orcamento(orcamento_id: str, dados: e.RegrasProprias):
        with sv.sessao() as s:
            perfil = rg.salvar_regras_do_orcamento(s, _obter(s, Orcamento, orcamento_id, "Orçamento"), dados.conteudo)
            s.flush()
            return {"impressao": perfil.impressao}


__all__ = ["Servico", "contexto_padrao", "criar_app"]
