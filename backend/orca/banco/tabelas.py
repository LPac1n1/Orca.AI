"""Tabelas do banco (docs/04 §7).

- Identificadores são gerados pelo programa (UUID), sem depender do banco.
- Dinheiro em centavos e horas em centésimos: sempre inteiros.
- Nada é apagado: tabelas "vivas" usam exclusão lógica (`excluido_em`); tabelas
  marcadas com `__imutavel__` nunca mudam depois de gravadas (gatilhos no banco).
- Toda gravação gera um registro em `evento` (orca.auditoria).
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from orca.banco.base import Base, Data, DataHora, agora, novo_id
from orca.dominio import AlvoTipo, Autor, normalizar_cnpj, normalizar_gtin
from orca.regras import NIVEIS

ID = String(32)
ESTADOS_TAREFA = ("pendente", "rodando", "esperando_usuario", "concluida", "falhou", "cancelada")


def _opcoes(coluna: str, valores) -> str:
    return f"{coluna} IN ({', '.join(repr(str(v)) for v in valores)})"


def _cep(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpo = valor.replace("-", "").strip()
    if len(limpo) != 8 or not limpo.isdigit():
        raise ValueError(f"CEP inválido: {valor!r}")
    return limpo


class _ComId:
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=novo_id)


class _ComCriacao:
    criado_em: Mapped[datetime] = mapped_column(DataHora, default=agora)


class _ComAutor:
    autor: Mapped[str] = mapped_column(String(120))

    @validates("autor")
    def _validar_autor(self, _chave, valor):
        return str(Autor(valor))


class _ExclusaoLogica:
    excluido_em: Mapped[datetime | None] = mapped_column(DataHora, default=None)


# --- Estrutura ---------------------------------------------------------------


class Organizacao(_ComId, _ComCriacao, Base):
    __tablename__ = "organizacao"

    nome: Mapped[str] = mapped_column(String(200))
    cnpj: Mapped[str | None] = mapped_column(String(14), default=None)

    @validates("cnpj")
    def _validar_cnpj(self, _chave, valor):
        return None if valor is None else normalizar_cnpj(valor)


class PerfilRegras(_ComId, _ComCriacao, Base):
    """Uma versão de uma camada de regras (orca.regras). Nunca muda: nova versão = novo registro."""

    __tablename__ = "perfil_regras"
    __imutavel__ = True
    __table_args__ = (
        UniqueConstraint("organizacao_id", "nome", "versao"),
        CheckConstraint(_opcoes("nivel", NIVEIS), name="nivel"),
        CheckConstraint("versao >= 1", name="versao"),
        CheckConstraint("(nivel = 'sistema') = (organizacao_id IS NULL)", name="sistema_sem_organizacao"),
    )

    organizacao_id: Mapped[str | None] = mapped_column(ForeignKey("organizacao.id"), default=None)
    nome: Mapped[str] = mapped_column(String(200))
    nivel: Mapped[str] = mapped_column(String(20))
    versao: Mapped[int] = mapped_column(Integer)
    impressao: Mapped[str] = mapped_column(String(64))
    conteudo_yaml: Mapped[str] = mapped_column(Text)


class Projeto(_ComId, _ComCriacao, _ExclusaoLogica, Base):
    __tablename__ = "projeto"
    __table_args__ = (
        CheckConstraint("teto_centavos > 0", name="teto"),
        CheckConstraint("duracao_meses BETWEEN 1 AND 120", name="duracao"),
    )

    organizacao_id: Mapped[str] = mapped_column(ForeignKey("organizacao.id"))
    nome: Mapped[str] = mapped_column(String(300))
    orgao: Mapped[str | None] = mapped_column(String(300), default=None)
    instrumento: Mapped[str | None] = mapped_column(String(100), default=None)
    processo: Mapped[str | None] = mapped_column(String(100), default=None)
    teto_centavos: Mapped[int] = mapped_column(Integer)
    duracao_meses: Mapped[int] = mapped_column(Integer)
    cep: Mapped[str | None] = mapped_column(String(8), default=None)
    data_entrega: Mapped[date | None] = mapped_column(Data, default=None)
    camadas_regras: Mapped[list[str]] = mapped_column(JSON, default=list)
    arquivado_em: Mapped[datetime | None] = mapped_column(DataHora, default=None)

    organizacao: Mapped[Organizacao] = relationship()
    orcamentos: Mapped[list["Orcamento"]] = relationship(back_populates="projeto")

    @validates("cep")
    def _validar_cep(self, _chave, valor):
        return _cep(valor)

    def _projeto_id(self) -> str:
        return self.id


class Orcamento(_ComId, _ComCriacao, _ExclusaoLogica, Base):
    """Uma rubrica do projeto."""

    __tablename__ = "orcamento"
    __table_args__ = (CheckConstraint(_opcoes("tipo", ("materiais", "mao_de_obra", "servicos")), name="tipo"),)

    projeto_id: Mapped[str] = mapped_column(ForeignKey("projeto.id"))
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str | None] = mapped_column(Text, default=None)
    tipo: Mapped[str] = mapped_column(String(20))
    camada_regras_id: Mapped[str | None] = mapped_column(ForeignKey("perfil_regras.id"), default=None)
    arquivado_em: Mapped[datetime | None] = mapped_column(DataHora, default=None)

    projeto: Mapped[Projeto] = relationship(back_populates="orcamentos")
    lotes: Mapped[list["Lote"]] = relationship(back_populates="orcamento")
    cargos: Mapped[list["Cargo"]] = relationship(back_populates="orcamento")
    camada_regras: Mapped[PerfilRegras | None] = relationship()

    def _projeto_id(self) -> str | None:
        return self.projeto_id or (self.projeto.id if self.projeto else None)


class Lote(_ComId, _ComCriacao, _ExclusaoLogica, Base):
    __tablename__ = "lote"

    orcamento_id: Mapped[str] = mapped_column(ForeignKey("orcamento.id"))
    nome: Mapped[str] = mapped_column(String(200))

    orcamento: Mapped[Orcamento] = relationship(back_populates="lotes")
    itens: Mapped[list["Item"]] = relationship(back_populates="lote", foreign_keys="Item.lote_id")

    def _projeto_id(self) -> str | None:
        return self.orcamento._projeto_id() if self.orcamento else None


class _Linha:
    """Campos comuns de item e cargo: meses ativos, margem e trava (D-32)."""

    mes_inicio: Mapped[int] = mapped_column(Integer)
    mes_fim: Mapped[int] = mapped_column(Integer)
    margem_min_percentual: Mapped[int | None] = mapped_column(Integer, default=None)
    margem_max_percentual: Mapped[int | None] = mapped_column(Integer, default=None)
    travado: Mapped[bool] = mapped_column(Boolean, default=False)


def _checks_linha() -> tuple:
    return (
        CheckConstraint("mes_inicio >= 1 AND mes_fim >= mes_inicio", name="meses"),
        CheckConstraint("margem_min_percentual IS NULL OR margem_min_percentual BETWEEN -100 AND 0", name="margem_min"),
        CheckConstraint("margem_max_percentual IS NULL OR margem_max_percentual BETWEEN 0 AND 1000", name="margem_max"),
    )


class Item(_ComId, _ComCriacao, _ExclusaoLogica, _Linha, Base):
    """Produto ou serviço com especificação exata (D-17)."""

    __tablename__ = "item"
    __table_args__ = (*_checks_linha(), CheckConstraint("qtd_planejada >= 0", name="quantidade"))

    lote_id: Mapped[str] = mapped_column(ForeignKey("lote.id"))
    descricao: Mapped[str] = mapped_column(String(300))
    categoria: Mapped[str | None] = mapped_column(String(50), default=None)
    marca: Mapped[str | None] = mapped_column(String(120), default=None)
    modelo: Mapped[str | None] = mapped_column(String(200), default=None)
    apresentacao: Mapped[str | None] = mapped_column(String(200), default=None)
    atributos: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ean: Mapped[str | None] = mapped_column(String(14), default=None)
    catmat: Mapped[str | None] = mapped_column(String(20), default=None)
    unidade: Mapped[str] = mapped_column(String(20), default="un")
    qtd_planejada: Mapped[int] = mapped_column(Integer)
    substitui_item_id: Mapped[str | None] = mapped_column(ForeignKey("item.id"), default=None)

    lote: Mapped[Lote] = relationship(back_populates="itens", foreign_keys=[lote_id])

    @validates("ean")
    def _validar_ean(self, _chave, valor):
        return None if valor is None else normalizar_gtin(valor)

    def _projeto_id(self) -> str | None:
        return self.lote._projeto_id() if self.lote else None


class Cargo(_ComId, _ComCriacao, _ExclusaoLogica, _Linha, Base):
    __tablename__ = "cargo"
    __table_args__ = (
        *_checks_linha(),
        CheckConstraint("postos >= 1", name="postos"),
        CheckConstraint("horas_planejadas_centesimos > 0", name="horas"),
        CheckConstraint(_opcoes("regime", ("mei", "recibo", "clt")), name="regime"),
    )

    orcamento_id: Mapped[str] = mapped_column(ForeignKey("orcamento.id"))
    nome: Mapped[str] = mapped_column(String(200))
    cbo: Mapped[str | None] = mapped_column(String(10), default=None)
    postos: Mapped[int] = mapped_column(Integer, default=1)
    regime: Mapped[str] = mapped_column(String(10))
    jornada_id: Mapped[str] = mapped_column(String(60), default="regra_geral")  # catalogos/jornadas.yaml
    horas_planejadas_centesimos: Mapped[int] = mapped_column(Integer)

    orcamento: Mapped[Orcamento] = relationship(back_populates="cargos")

    def _projeto_id(self) -> str | None:
        return self.orcamento._projeto_id() if self.orcamento else None


# --- Pesquisa e evidências ---------------------------------------------------


class Fonte(_ComId, _ComCriacao, Base):
    __tablename__ = "fonte"
    __table_args__ = (CheckConstraint(_opcoes("tipo", ("loja", "empresa", "fornecedor", "publica")), name="tipo"),)

    tipo: Mapped[str] = mapped_column(String(20))
    nome: Mapped[str] = mapped_column(String(200))
    dominio: Mapped[str | None] = mapped_column(String(200), default=None)
    catalogo_id: Mapped[str | None] = mapped_column(String(60), default=None)  # catalogos/lojas.yaml
    conector: Mapped[str | None] = mapped_column(String(40), default=None)


class ConsultaCnpj(_ComId, _ComCriacao, Base):
    """Resultado de uma consulta de situação cadastral, como veio do provedor."""

    __tablename__ = "consulta_cnpj"
    __imutavel__ = True

    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    razao_social: Mapped[str | None] = mapped_column(String(300), default=None)
    nome_fantasia: Mapped[str | None] = mapped_column(String(300), default=None)
    situacao: Mapped[str | None] = mapped_column(String(40), default=None)
    data_situacao: Mapped[date | None] = mapped_column(Data, default=None)
    municipio: Mapped[str | None] = mapped_column(String(120), default=None)
    uf: Mapped[str | None] = mapped_column(String(2), default=None)
    provedor: Mapped[str] = mapped_column(String(40))
    consultado_em: Mapped[datetime] = mapped_column(DataHora)
    dados_brutos: Mapped[str | None] = mapped_column(Text, default=None)

    @validates("cnpj")
    def _validar_cnpj(self, _chave, valor):
        return normalizar_cnpj(valor)


class Arquivo(_ComCriacao, Base):
    """Arquivo de evidência, identificado pela impressão digital do conteúdo."""

    __tablename__ = "arquivo"
    __imutavel__ = True
    __table_args__ = (
        CheckConstraint("length(sha256) = 64", name="sha256"),
        CheckConstraint("tamanho >= 0", name="tamanho"),
    )

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    caminho: Mapped[str] = mapped_column(String(300))
    tipo_mime: Mapped[str] = mapped_column(String(100))
    tamanho: Mapped[int] = mapped_column(Integer)


class Evidencia(_ComId, _ComCriacao, Base):
    """Captura de uma página: PDF obrigatório (D-13), imagem e HTML."""

    __tablename__ = "evidencia"
    __imutavel__ = True

    url: Mapped[str] = mapped_column(Text)
    capturado_em: Mapped[datetime] = mapped_column(DataHora)
    metodo: Mapped[str] = mapped_column(String(20))
    cep: Mapped[str | None] = mapped_column(String(8), default=None)
    pdf_sha256: Mapped[str] = mapped_column(ForeignKey("arquivo.sha256"))
    png_sha256: Mapped[str | None] = mapped_column(ForeignKey("arquivo.sha256"), default=None)
    html_sha256: Mapped[str | None] = mapped_column(ForeignKey("arquivo.sha256"), default=None)

    pdf: Mapped[Arquivo] = relationship(foreign_keys=[pdf_sha256])
    png: Mapped[Arquivo | None] = relationship(foreign_keys=[png_sha256])
    html: Mapped[Arquivo | None] = relationship(foreign_keys=[html_sha256])

    @validates("cep")
    def _validar_cep(self, _chave, valor):
        return _cep(valor)


class Comprovante(_ComId, _ComCriacao, Base):
    """Comprovante de Inscrição e Situação Cadastral da Receita (D-13, D-14)."""

    __tablename__ = "comprovante"
    __imutavel__ = True

    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    arquivo_sha256: Mapped[str] = mapped_column(ForeignKey("arquivo.sha256"))
    emitido_em: Mapped[datetime] = mapped_column(DataHora)

    arquivo: Mapped[Arquivo] = relationship()

    @validates("cnpj")
    def _validar_cnpj(self, _chave, valor):
        return normalizar_cnpj(valor)


class Observacao(_ComId, _ComCriacao, _ComAutor, Base):
    """Um preço ou salário visto numa fonte, num momento. Nunca muda (princípio 5)."""

    __tablename__ = "observacao"
    __imutavel__ = True
    __table_args__ = (
        CheckConstraint(
            "(alvo_tipo = 'item' AND item_id IS NOT NULL AND cargo_id IS NULL) OR "
            "(alvo_tipo = 'cargo' AND cargo_id IS NOT NULL AND item_id IS NULL)",
            name="alvo",
        ),
        CheckConstraint("preco_centavos IS NULL OR preco_centavos > 0", name="preco"),
        CheckConstraint(
            "salario_min_centavos IS NULL OR salario_max_centavos IS NULL "
            "OR salario_min_centavos <= salario_max_centavos",
            name="faixa_salarial",
        ),
    )

    alvo_tipo: Mapped[str] = mapped_column(String(10))
    item_id: Mapped[str | None] = mapped_column(ForeignKey("item.id"), default=None, index=True)
    cargo_id: Mapped[str | None] = mapped_column(ForeignKey("cargo.id"), default=None, index=True)
    fonte_id: Mapped[str] = mapped_column(ForeignKey("fonte.id"))
    cnpj_vendedor: Mapped[str | None] = mapped_column(String(14), default=None)
    url: Mapped[str] = mapped_column(Text)
    titulo: Mapped[str | None] = mapped_column(Text, default=None)
    marca: Mapped[str | None] = mapped_column(String(120), default=None)
    modelo: Mapped[str | None] = mapped_column(String(200), default=None)
    apresentacao: Mapped[str | None] = mapped_column(String(200), default=None)
    ean: Mapped[str | None] = mapped_column(String(14), default=None)
    preco_centavos: Mapped[int | None] = mapped_column(Integer, default=None)
    salario_min_centavos: Mapped[int | None] = mapped_column(Integer, default=None)
    salario_max_centavos: Mapped[int | None] = mapped_column(Integer, default=None)
    encontrado: Mapped[bool] = mapped_column(Boolean)
    disponivel: Mapped[bool | None] = mapped_column(Boolean, default=None)
    coletado_em: Mapped[datetime] = mapped_column(DataHora)
    cep: Mapped[str | None] = mapped_column(String(8), default=None)
    metodo: Mapped[str] = mapped_column(String(20))
    evidencia_id: Mapped[str | None] = mapped_column(ForeignKey("evidencia.id"), default=None)
    preco_no_html: Mapped[bool | None] = mapped_column(Boolean, default=None)
    dados_brutos: Mapped[str | None] = mapped_column(Text, default=None)

    item: Mapped[Item | None] = relationship()
    cargo: Mapped[Cargo | None] = relationship()
    fonte: Mapped[Fonte] = relationship()
    evidencia: Mapped[Evidencia | None] = relationship()

    @validates("alvo_tipo")
    def _validar_alvo(self, _chave, valor):
        return str(AlvoTipo(valor))

    @validates("cnpj_vendedor")
    def _validar_cnpj(self, _chave, valor):
        return None if valor is None else normalizar_cnpj(valor)

    @validates("ean")
    def _validar_ean(self, _chave, valor):
        return None if valor is None else normalizar_gtin(valor)

    @validates("cep")
    def _validar_cep(self, _chave, valor):
        return _cep(valor)

    def _projeto_id(self) -> str | None:
        alvo = self.item or self.cargo
        return alvo._projeto_id() if alvo else None


class Correspondencia(_ComId, _ComCriacao, _ComAutor, Base):
    """Decisão sobre "é o mesmo produto?". Nova decisão = novo registro."""

    __tablename__ = "correspondencia"
    __imutavel__ = True
    __table_args__ = (
        CheckConstraint(_opcoes("status", ("verde", "amarelo", "vermelho")), name="status"),
        CheckConstraint(_opcoes("origem", ("ean", "atributos", "ia", "humano")), name="origem"),
        # Princípio 4: a IA pode rebaixar, nunca promover para 🟢.
        CheckConstraint("NOT (status = 'verde' AND origem = 'ia')", name="ia_nao_promove"),
    )

    item_id: Mapped[str] = mapped_column(ForeignKey("item.id"), index=True)
    observacao_id: Mapped[str] = mapped_column(ForeignKey("observacao.id"), index=True)
    status: Mapped[str] = mapped_column(String(10))
    motivos: Mapped[list[str]] = mapped_column(JSON, default=list)
    origem: Mapped[str] = mapped_column(String(10))

    item: Mapped[Item] = relationship()
    observacao: Mapped[Observacao] = relationship()

    def _projeto_id(self) -> str | None:
        return self.item._projeto_id() if self.item else None


class Cotacao(_ComId, _ComCriacao, _ComAutor, Base):
    """As fontes usadas para um item ou cargo, com a média (docs/03 §2)."""

    __tablename__ = "cotacao"
    __imutavel__ = True
    __table_args__ = (
        CheckConstraint(
            "(alvo_tipo = 'item' AND item_id IS NOT NULL AND cargo_id IS NULL) OR "
            "(alvo_tipo = 'cargo' AND cargo_id IS NOT NULL AND item_id IS NULL)",
            name="alvo",
        ),
        CheckConstraint("n >= 1 AND soma_centavos > 0 AND media_exibida_centavos > 0", name="valores"),
    )

    alvo_tipo: Mapped[str] = mapped_column(String(10))
    item_id: Mapped[str | None] = mapped_column(ForeignKey("item.id"), default=None, index=True)
    cargo_id: Mapped[str | None] = mapped_column(ForeignKey("cargo.id"), default=None, index=True)
    n: Mapped[int] = mapped_column(Integer)
    soma_centavos: Mapped[int] = mapped_column(Integer)
    media_exibida_centavos: Mapped[int] = mapped_column(Integer)
    impressao_regras: Mapped[str] = mapped_column(String(64))

    item: Mapped[Item | None] = relationship()
    cargo: Mapped[Cargo | None] = relationship()


class CotacaoObservacao(_ComCriacao, Base):
    __tablename__ = "cotacao_observacao"
    __imutavel__ = True
    __table_args__ = (CheckConstraint("ordem >= 1", name="ordem"),)

    cotacao_id: Mapped[str] = mapped_column(ForeignKey("cotacao.id"), primary_key=True)
    ordem: Mapped[int] = mapped_column(Integer, primary_key=True)
    observacao_id: Mapped[str] = mapped_column(ForeignKey("observacao.id"))

    cotacao: Mapped[Cotacao] = relationship()
    observacao: Mapped[Observacao] = relationship()


# --- Otimização ----------------------------------------------------------------


class ExecucaoOtimizacao(_ComId, _ComCriacao, _ComAutor, Base):
    """Uma execução do otimizador: entradas, resultado, verificação e versões (docs/03 §4.6)."""

    __tablename__ = "execucao_otimizacao"
    __imutavel__ = True
    __table_args__ = (CheckConstraint(_opcoes("status", ("otima", "viavel", "sem_solucao")), name="status"),)

    projeto_id: Mapped[str] = mapped_column(ForeignKey("projeto.id"), index=True)
    impressao_regras: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12))
    teto_centavos: Mapped[int] = mapped_column(Integer)
    total_centavos: Mapped[int | None] = mapped_column(Integer, default=None)
    verificacao_ok: Mapped[bool] = mapped_column(Boolean)
    versao_otimizador: Mapped[str] = mapped_column(String(40))
    entradas: Mapped[dict[str, Any]] = mapped_column(JSON)
    resultado: Mapped[dict[str, Any]] = mapped_column(JSON)

    projeto: Mapped[Projeto] = relationship()

    def _projeto_id(self) -> str | None:
        return self.projeto_id or (self.projeto.id if self.projeto else None)


class LinhaFinal(_ComId, _ComCriacao, Base):
    """Linha do orçamento final de uma execução (preço × quantidade ou valor mensal × meses × postos)."""

    __tablename__ = "linha_final"
    __imutavel__ = True
    __table_args__ = (
        CheckConstraint(_opcoes("alvo_tipo", ("item", "cargo")), name="alvo"),
        CheckConstraint("meses >= 1 AND total_centavos >= 0", name="valores"),
    )

    execucao_id: Mapped[str] = mapped_column(ForeignKey("execucao_otimizacao.id"), index=True)
    linha_id: Mapped[str] = mapped_column(String(64))
    alvo_tipo: Mapped[str] = mapped_column(String(10))
    preco_unitario_centavos: Mapped[int | None] = mapped_column(Integer, default=None)
    quantidade: Mapped[int | None] = mapped_column(Integer, default=None)
    valor_hora_centavos: Mapped[int | None] = mapped_column(Integer, default=None)
    horas_centesimos: Mapped[int | None] = mapped_column(Integer, default=None)
    valor_mensal_centavos: Mapped[int | None] = mapped_column(Integer, default=None)
    postos: Mapped[int | None] = mapped_column(Integer, default=None)
    meses: Mapped[int] = mapped_column(Integer)
    total_centavos: Mapped[int] = mapped_column(Integer)

    execucao: Mapped[ExecucaoOtimizacao] = relationship()

    def _projeto_id(self) -> str | None:
        return self.execucao._projeto_id() if self.execucao else None


# --- Decisões, alertas e auditoria -------------------------------------------


class Decisao(_ComId, _ComCriacao, _ComAutor, Base):
    """Decisão humana registrada (aprovação, escolha, substituição…)."""

    __tablename__ = "decisao"
    __imutavel__ = True

    tipo: Mapped[str] = mapped_column(String(60))
    alvo_tipo: Mapped[str] = mapped_column(String(30))
    alvo_id: Mapped[str] = mapped_column(String(64), index=True)
    valor: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    justificativa: Mapped[str | None] = mapped_column(Text, default=None)


class Alerta(_ComId, _ComCriacao, Base):
    __tablename__ = "alerta"
    __table_args__ = (CheckConstraint(_opcoes("severidade", ("info", "atencao", "problema")), name="severidade"),)

    projeto_id: Mapped[str] = mapped_column(ForeignKey("projeto.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(60))
    severidade: Mapped[str] = mapped_column(String(10))
    alvo_tipo: Mapped[str | None] = mapped_column(String(30), default=None)
    alvo_id: Mapped[str | None] = mapped_column(String(64), default=None)
    mensagem: Mapped[str] = mapped_column(Text)
    resolvido_em: Mapped[datetime | None] = mapped_column(DataHora, default=None)

    projeto: Mapped[Projeto] = relationship()

    def _projeto_id(self) -> str | None:
        return self.projeto_id or (self.projeto.id if self.projeto else None)


class Tarefa(_ComId, _ComCriacao, _ComAutor, Base):
    """Trabalho demorado feito em segundo plano: coleta, consulta de CNPJ, otimização, exportação.

    É um registro de operação (andamento, resultado), não dado do orçamento: suas
    atualizações de andamento não geram eventos (`__auditar__ = False`), mas nunca é apagada.
    """

    __tablename__ = "tarefa"
    __auditar__ = False
    __table_args__ = (
        CheckConstraint(_opcoes("estado", ESTADOS_TAREFA), name="estado"),
        CheckConstraint("progresso BETWEEN 0 AND 100", name="progresso"),
    )

    projeto_id: Mapped[str | None] = mapped_column(ForeignKey("projeto.id"), default=None, index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    estado: Mapped[str] = mapped_column(String(20), default="pendente")
    progresso: Mapped[int] = mapped_column(Integer, default=0)
    mensagem: Mapped[str | None] = mapped_column(Text, default=None)
    parametros: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    iniciada_em: Mapped[datetime | None] = mapped_column(DataHora, default=None)
    concluida_em: Mapped[datetime | None] = mapped_column(DataHora, default=None)

    def _projeto_id(self) -> str | None:
        return self.projeto_id


class Evento(Base):
    """Histórico: cada criação ou alteração, com antes, depois, autor e hora. Só acréscimo."""

    __tablename__ = "evento"
    __imutavel__ = True
    __table_args__ = (Index(None, "entidade", "entidade_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    projeto_id: Mapped[str | None] = mapped_column(ID, default=None, index=True)
    entidade: Mapped[str] = mapped_column(String(40))
    entidade_id: Mapped[str] = mapped_column(String(64))
    acao: Mapped[str] = mapped_column(String(20))
    antes: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    depois: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    autor: Mapped[str] = mapped_column(String(120))
    criado_em: Mapped[datetime] = mapped_column(DataHora, default=agora)


TABELAS_IMUTAVEIS = tuple(
    sorted(m.class_.__tablename__ for m in Base.registry.mappers if getattr(m.class_, "__imutavel__", False))
)
