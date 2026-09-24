"""Fila de tarefas: o trabalho demorado roda em segundo plano (docs/04 §3).

Duas pistas, cada uma com o seu trabalhador (o Playwright síncrono precisa ficar
sempre na mesma thread):
- principal: coletar páginas, consultar CNPJs, fechar o teto, exportar — sem janela;
- assistida: captura assistida e comprovante da Receita — com janela visível, em
  que QUEM NAVEGA É O USUÁRIO (D-67). Ela espera o usuário sem travar a outra pista.
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

PISTA_ASSISTIDA = frozenset({"captura_assistida", "comprovante"})


class ErroTarefa(RuntimeError):
    pass


class TarefaCancelada(RuntimeError):
    """O usuário cancelou a tarefa (ex.: fechou a captura assistida)."""


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
    abrir_navegador_visivel: Callable[[], AbstractContextManager] | None = None
    cliente_http: Callable[[], httpx.Client] | None = None
    hoje: Callable[[], date] = field(default=hoje_em_brasilia)
    intervalo_busca_s: float = 3.0  # entre dois pedidos à mesma loja na busca automática (poucas requisições)


Executor = Callable[["Fila", str, dict], dict]
EXECUTORES: dict[str, Executor] = {}


def tarefa(tipo: str):
    """Registra a função que executa um tipo de tarefa."""
    def registrar(funcao: Executor) -> Executor:
        EXECUTORES[tipo] = funcao
        return funcao
    return registrar


def pista_do_tipo(tipo: str) -> str:
    return "assistida" if tipo in PISTA_ASSISTIDA else "principal"


class Fila:
    def __init__(self, contexto: Contexto):
        self.contexto = contexto
        self._parar = threading.Event()
        self._acordar = {"principal": threading.Event(), "assistida": threading.Event()}
        self._trabalhadores: list[threading.Thread] = []
        self._local = threading.local()
        self._sinais: dict[str, threading.Event] = {}
        self._cancelamentos: dict[str, threading.Event] = {}
        self._trava = threading.Lock()

    # --- Criar e acompanhar ------------------------------------------------------------------------

    def enfileirar(self, sessao: Session, tipo: str, parametros: dict, projeto_id: str | None = None) -> Tarefa:
        if tipo not in EXECUTORES:
            raise ErroTarefa(f"Tipo de tarefa desconhecido: {tipo}")
        nova = Tarefa(tipo=tipo, parametros=parametros, projeto_id=projeto_id, autor=sessao.info["autor"],
                      estado="pendente", progresso=0)
        sessao.add(nova)
        self._acordar[pista_do_tipo(tipo)].set()
        return nova

    def _atualizar(self, tarefa_id: str, **campos) -> None:
        with self.contexto.fabrica() as sessao:
            t = sessao.get(Tarefa, tarefa_id)
            for chave, valor in campos.items():
                setattr(t, chave, valor)
            sessao.commit()

    def progresso(self, tarefa_id: str, percentual: int, mensagem: str | None = None) -> None:
        campos = {"progresso": max(0, min(100, percentual)), "estado": "rodando"}
        if mensagem is not None:
            campos["mensagem"] = mensagem
        self._atualizar(tarefa_id, **campos)

    def esperar_usuario(self, tarefa_id: str, mensagem: str) -> None:
        self._atualizar(tarefa_id, estado="esperando_usuario", mensagem=mensagem)

    def _evento(self, mapa: dict[str, threading.Event], tarefa_id: str) -> threading.Event:
        with self._trava:
            return mapa.setdefault(tarefa_id, threading.Event())

    def sinal(self, tarefa_id: str) -> threading.Event:
        """Sinal de "Capturar agora" dado pelo usuário na interface."""
        return self._evento(self._sinais, tarefa_id)

    def cancelamento(self, tarefa_id: str) -> threading.Event:
        return self._evento(self._cancelamentos, tarefa_id)

    def capturar_agora(self, tarefa_id: str) -> None:
        self.sinal(tarefa_id).set()

    def cancelar(self, sessao: Session, tarefa_id: str) -> Tarefa:
        t = sessao.get(Tarefa, tarefa_id)
        if t is None:
            raise ErroTarefa("Tarefa não encontrada.")
        if t.estado == "pendente":
            t.estado, t.mensagem, t.concluida_em = "cancelada", "cancelada antes de começar", agora()
        elif t.estado in ("rodando", "esperando_usuario"):
            self.cancelamento(tarefa_id).set()
        else:
            raise ErroTarefa("Esta tarefa já terminou.")
        return t

    # --- Executar ----------------------------------------------------------------------------------

    def _pegar_proxima(self, pista: str) -> tuple[str, str, dict] | None:
        with self.contexto.fabrica() as sessao:
            consulta = select(Tarefa).where(Tarefa.estado == "pendente").order_by(Tarefa.criado_em, Tarefa.id)
            consulta = consulta.where(Tarefa.tipo.in_(PISTA_ASSISTIDA) if pista == "assistida"
                                      else Tarefa.tipo.not_in(PISTA_ASSISTIDA))
            t = sessao.scalars(consulta).first()
            if t is None:
                return None
            t.estado, t.iniciada_em = "rodando", agora()
            sessao.commit()
            return t.id, t.tipo, dict(t.parametros)

    def processar_proxima(self, pista: str = "principal") -> str | None:
        """Executa a tarefa pendente mais antiga da pista. Devolve o id, ou None se não há nenhuma."""
        self._local.pista = pista
        proxima = self._pegar_proxima(pista)
        if proxima is None:
            return None
        tarefa_id, tipo, parametros = proxima
        try:
            resultado = EXECUTORES[tipo](self, tarefa_id, parametros)
            estado, mensagem = "concluida", (resultado or {}).get("mensagem")
        except TarefaCancelada:
            resultado, estado, mensagem = None, "cancelada", "cancelada por você"
        except Exception as erro:  # noqa: BLE001 — a tarefa falha, o trabalhador continua
            resultado, estado, mensagem = None, "falhou", str(erro) or type(erro).__name__
        with self.contexto.fabrica() as sessao:
            t = sessao.get(Tarefa, tarefa_id)
            t.estado, t.resultado, t.concluida_em = estado, resultado, agora()
            t.progresso = 100 if estado == "concluida" else t.progresso
            t.mensagem = mensagem
            sessao.commit()
        with self._trava:
            self._sinais.pop(tarefa_id, None)
            self._cancelamentos.pop(tarefa_id, None)
        return tarefa_id

    def processar_todas(self) -> list[str]:
        feitas = []
        for pista in ("principal", "assistida", "principal"):
            while (feita := self.processar_proxima(pista)) is not None:
                feitas.append(feita)
        return feitas

    # --- Recursos que ficam abertos entre tarefas (um conjunto por pista/thread) -----------------------

    def _recursos(self) -> dict:
        if not hasattr(self._local, "recursos"):
            self._local.recursos = {}
        return self._local.recursos

    def recurso(self, nome: str, abrir: Callable[[], AbstractContextManager]):
        recursos = self._recursos()
        if nome not in recursos:
            gerenciador = abrir()
            recursos[nome] = (gerenciador, gerenciador.__enter__())
        return recursos[nome][1]

    def navegador(self) -> CapturaPaginas:
        return self.recurso("navegador", self.contexto.abrir_navegador)

    def navegador_visivel(self):
        if self.contexto.abrir_navegador_visivel is None:
            raise ErroTarefa("A captura assistida não está disponível neste computador.")
        return self.recurso("navegador_visivel", self.contexto.abrir_navegador_visivel)

    def renderizador(self):
        return self.recurso("renderizador", self.contexto.abrir_renderizador)

    def fechar_recursos(self) -> None:
        recursos = self._recursos()
        for gerenciador, _ in recursos.values():
            try:
                gerenciador.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        recursos.clear()

    # --- Trabalhadores em segundo plano ----------------------------------------------------------------

    def iniciar(self) -> None:
        if self._trabalhadores:
            return
        self._retomar_interrompidas()
        for pista in ("principal", "assistida"):
            t = threading.Thread(target=self._laco, args=(pista,), name=f"orca-tarefas-{pista}", daemon=True)
            t.start()
            self._trabalhadores.append(t)

    def _retomar_interrompidas(self) -> None:
        """Ao abrir o programa: tarefas que estavam rodando voltam para a fila; capturas assistidas são canceladas."""
        with self.contexto.fabrica() as sessao:
            for t in sessao.scalars(select(Tarefa).where(Tarefa.estado.in_(("rodando", "esperando_usuario")))):
                if t.tipo in PISTA_ASSISTIDA:
                    t.estado, t.mensagem, t.concluida_em = "cancelada", "o programa foi fechado durante a captura", agora()
                else:
                    t.estado, t.mensagem = "pendente", "retomada depois de o programa ser fechado"
            sessao.commit()

    def _laco(self, pista: str) -> None:
        try:
            while not self._parar.is_set():
                if self.processar_proxima(pista) is None:
                    self._acordar[pista].wait(timeout=1.0)
                    self._acordar[pista].clear()
        finally:
            self.fechar_recursos()

    def parar(self, espera_s: float = 10.0) -> None:
        self._parar.set()
        for evento in (*self._acordar.values(), *self._cancelamentos.values()):
            evento.set()
        for t in self._trabalhadores:
            t.join(timeout=espera_s)
        self._trabalhadores = []
