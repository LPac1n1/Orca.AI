"""Fila de tarefas: o trabalho demorado roda em segundo plano, uma tarefa de cada vez (docs/04 §3).

Coletar uma página, consultar CNPJs, fechar o teto e gerar o pacote podem levar de
segundos a minutos. A interface cria a tarefa e acompanha o andamento; um único
trabalhador executa as tarefas em ordem (o navegador fica aberto entre elas).
"""

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from orca.banco import Tarefa, agora
from orca.coleta.catalogo import Jornada, LojaCatalogo
from orca.coleta.registro import CapturaPaginas
from orca.correspondencia import Vocabulario
from orca.evidencias import ArmazemArquivos, hoje_em_brasilia


class ErroTarefa(RuntimeError):
    pass


@dataclass
class Contexto:
    """Tudo de que as tarefas precisam. Os testes trocam o navegador e a rede por falsos."""

    fabrica: sessionmaker[Session]
    armazem: ArmazemArquivos
    pasta_dados: Path
    vocabulario: Vocabulario
    catalogo: dict[str, LojaCatalogo]
    jornadas: dict[str, Jornada]
    abrir_navegador: Callable[[], AbstractContextManager[CapturaPaginas]]
    abrir_renderizador: Callable[[], AbstractContextManager]
    cliente_http: Callable[[], httpx.Client] | None = None
    hoje: Callable[[], date] = field(default=hoje_em_brasilia)


Executor = Callable[["Fila", str, dict], dict]
EXECUTORES: dict[str, Executor] = {}


def tarefa(tipo: str):
    """Registra a função que executa um tipo de tarefa."""
    def registrar(funcao: Executor) -> Executor:
        EXECUTORES[tipo] = funcao
        return funcao
    return registrar


class Fila:
    def __init__(self, contexto: Contexto):
        self.contexto = contexto
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self._trabalhador: threading.Thread | None = None
        self._recursos: dict[str, tuple[AbstractContextManager, object]] = {}

    # --- Criar e acompanhar ------------------------------------------------------------------------

    def enfileirar(self, sessao: Session, tipo: str, parametros: dict, projeto_id: str | None = None) -> Tarefa:
        if tipo not in EXECUTORES:
            raise ErroTarefa(f"Tipo de tarefa desconhecido: {tipo}")
        nova = Tarefa(tipo=tipo, parametros=parametros, projeto_id=projeto_id, autor=sessao.info["autor"],
                      estado="pendente", progresso=0)
        sessao.add(nova)
        self._acordar.set()
        return nova

    def progresso(self, tarefa_id: str, percentual: int, mensagem: str | None = None) -> None:
        with self.contexto.fabrica() as sessao:
            t = sessao.get(Tarefa, tarefa_id)
            t.progresso = max(0, min(100, percentual))
            if mensagem is not None:
                t.mensagem = mensagem
            sessao.commit()

    # --- Executar ----------------------------------------------------------------------------------

    def _pegar_proxima(self) -> tuple[str, str, dict] | None:
        with self.contexto.fabrica() as sessao:
            t = sessao.scalars(
                select(Tarefa).where(Tarefa.estado == "pendente").order_by(Tarefa.criado_em, Tarefa.id)
            ).first()
            if t is None:
                return None
            t.estado, t.iniciada_em = "rodando", agora()
            sessao.commit()
            return t.id, t.tipo, dict(t.parametros)

    def processar_proxima(self) -> str | None:
        """Executa a tarefa pendente mais antiga. Devolve o id, ou None se a fila está vazia."""
        proxima = self._pegar_proxima()
        if proxima is None:
            return None
        tarefa_id, tipo, parametros = proxima
        try:
            resultado = EXECUTORES[tipo](self, tarefa_id, parametros)
            estado, mensagem = "concluida", (resultado or {}).get("mensagem")
        except Exception as erro:  # noqa: BLE001 — a tarefa falha, o trabalhador continua
            resultado, estado, mensagem = None, "falhou", str(erro) or type(erro).__name__
        with self.contexto.fabrica() as sessao:
            t = sessao.get(Tarefa, tarefa_id)
            t.estado, t.resultado, t.concluida_em = estado, resultado, agora()
            t.progresso = 100 if estado == "concluida" else t.progresso
            t.mensagem = mensagem
            sessao.commit()
        return tarefa_id

    def processar_todas(self) -> list[str]:
        feitas = []
        while (feita := self.processar_proxima()) is not None:
            feitas.append(feita)
        return feitas

    # --- Recursos que ficam abertos entre tarefas ----------------------------------------------------

    def recurso(self, nome: str, abrir: Callable[[], AbstractContextManager]):
        if nome not in self._recursos:
            gerenciador = abrir()
            self._recursos[nome] = (gerenciador, gerenciador.__enter__())
        return self._recursos[nome][1]

    def navegador(self) -> CapturaPaginas:
        return self.recurso("navegador", self.contexto.abrir_navegador)

    def renderizador(self):
        return self.recurso("renderizador", self.contexto.abrir_renderizador)

    def fechar_recursos(self) -> None:
        for gerenciador, _ in self._recursos.values():
            try:
                gerenciador.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        self._recursos.clear()

    # --- Trabalhador em segundo plano ----------------------------------------------------------------

    def iniciar(self) -> None:
        if self._trabalhador is not None:
            return
        self._retomar_interrompidas()
        self._trabalhador = threading.Thread(target=self._laco, name="orca-tarefas", daemon=True)
        self._trabalhador.start()

    def _retomar_interrompidas(self) -> None:
        """Tarefas que estavam rodando quando o programa fechou voltam para a fila."""
        with self.contexto.fabrica() as sessao:
            for t in sessao.scalars(select(Tarefa).where(Tarefa.estado == "rodando")):
                t.estado, t.mensagem = "pendente", "retomada depois de o programa ser fechado"
            sessao.commit()

    def _laco(self) -> None:
        # O Playwright síncrono precisa ser usado sempre na mesma thread: por isso um só trabalhador.
        try:
            while not self._parar.is_set():
                if self.processar_proxima() is None:
                    self._acordar.wait(timeout=1.0)
                    self._acordar.clear()
        finally:
            self.fechar_recursos()

    def parar(self, espera_s: float = 10.0) -> None:
        self._parar.set()
        self._acordar.set()
        if self._trabalhador is not None:
            self._trabalhador.join(timeout=espera_s)
            self._trabalhador = None
