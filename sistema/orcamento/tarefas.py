"""Tarefas em segundo plano com progresso visível (pedido do usuário: barra de porcentagem e aviso quando trava ou dá erro).

Cada tarefa roda numa thread própria (com o seu laço asyncio) e grava no banco, a cada passo:
  progresso (0–100 %), etapa atual, situação de cada fonte (✔ concluída / ⏳ rodando / ⚠ repetindo / ✘ falhou) e avisos.
A tela consulta /api/tarefa/{id} a cada segundo. Se a tarefa ficar sem dar notícia por mais de SEM_NOTICIA segundos,
a tela avisa "parece travada" (cada etapa também tem limite de tempo próprio). O botão Cancelar pede a parada, que a tarefa
atende no próximo passo. Enquanto houver tarefa rodando, o Windows é impedido de entrar em suspensão."""
import asyncio
import datetime as dt
import json
import sys
import threading
import traceback

from . import db

SEM_NOTICIA = 90  # segundos sem atualização → a tela avisa que a tarefa pode estar travada
_ativas = set()
_trava = threading.Lock()


class Cancelada(BaseException):
    """A pessoa pediu para cancelar. (BaseException: não é confundida com falha de uma loja nos 'except Exception' das buscas.)"""


def _acordado(ligar):
    """Impede a suspensão do Windows enquanto houver tarefa rodando (não altera nenhuma configuração do sistema)."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if ligar else 0))
    except Exception:
        pass


class Contexto:
    """O que a tarefa usa para informar o andamento."""

    def __init__(self, tid):
        self.id = tid
        self._fontes, self._avisos = {}, []
        self._prog, self._etapa = 0.0, ''
        self._ultima = 0.0

    def _gravar(self, forcar=True):
        import time
        agora = time.monotonic()
        if not forcar and agora - self._ultima < 0.4:
            return
        self._ultima = agora
        with db.conectar() as c:
            c.execute('UPDATE tarefa SET progresso=?, etapa=?, fontes=?, avisos=?, atualizado_em=? WHERE id=?',
                      (round(self._prog, 1), self._etapa, json.dumps(self._fontes, ensure_ascii=False),
                       json.dumps(self._avisos, ensure_ascii=False), db.agora(), self.id))
            row = c.execute('SELECT cancelar FROM tarefa WHERE id=?', (self.id,)).fetchone()
        if row and row['cancelar']:
            raise Cancelada()

    def progresso(self, pct, etapa=None):
        self._prog = max(0.0, min(100.0, float(pct)))
        mudou = etapa is not None and etapa != self._etapa
        if etapa is not None:
            self._etapa = etapa
        self._gravar(forcar=mudou)

    def etapa(self, texto):
        self._etapa = texto; self._gravar()

    def fonte(self, nome, estado, detalhe=''):
        """estado: 'rodando' | 'ok' | 'repetindo' | 'falhou' | 'pulada'."""
        f = self._fontes.setdefault(nome, dict(estado='rodando', detalhe='', falhas=0, feitas=0))
        if estado == 'falhou':
            f['falhas'] += 1
        if estado == 'ok':
            f['feitas'] += 1
        mudou = f['estado'] != estado
        f['estado'], f['detalhe'] = estado, detalhe
        self._gravar(forcar=mudou and estado in ('falhou', 'repetindo'))

    def aviso(self, msg):
        if msg not in self._avisos:
            self._avisos.append(msg)
        self._gravar()

    def verificar_cancelamento(self):
        self._gravar()


def criar(tipo, titulo, projeto_id=None):
    with db.conectar() as c:
        return c.execute('INSERT INTO tarefa (projeto_id, tipo, titulo, estado, criado_em, atualizado_em, fontes, avisos) VALUES (?,?,?,?,?,?,?,?)',
                         (projeto_id, tipo, titulo, 'na fila', db.agora(), db.agora(), '{}', '[]')).lastrowid


def iniciar(tipo, titulo, funcao, projeto_id=None):
    """funcao(ctx) -> dict (resultado; pode conter 'ir_para' com o endereço da tela de resultado). Pode ser assíncrona."""
    tid = criar(tipo, titulo, projeto_id)

    def rodar():
        with _trava:
            _ativas.add(tid); _acordado(True)
        ctx = Contexto(tid)
        with db.conectar() as c:
            c.execute('UPDATE tarefa SET estado=? WHERE id=?', ('rodando', tid))
        try:
            r = funcao(ctx)
            if asyncio.iscoroutine(r):
                r = asyncio.run(r)
            estado, erro, res = 'concluída', None, r
        except Cancelada:
            estado, erro, res = 'cancelada', 'cancelada a pedido', None
        except ValueError as e:   # motivo explicado pelo próprio sistema (ex.: falta cadastrar um item): a mensagem já diz o que fazer
            m = str(e)
            estado, erro, res = 'falhou', (m[:1].upper() + m[1:]) if m else 'a tarefa não pôde continuar', None
        except Exception as e:
            estado, erro, res = 'falhou', f'erro inesperado ({type(e).__name__}: {e})', None
            traceback.print_exc()
        try:
            ctx._gravar(forcar=True)  # grava o último estado das fontes e avisos
        except Cancelada:
            pass
        with db.conectar() as c:
            c.execute('UPDATE tarefa SET estado=?, erro=?, resultado=?, fim_em=?, atualizado_em=?, progresso=CASE WHEN ?="concluída" THEN 100 ELSE progresso END WHERE id=?',
                      (estado, erro, json.dumps(res, ensure_ascii=False, default=str) if res is not None else None, db.agora(), db.agora(), estado, tid))
        if projeto_id:
            try:  # o registro no histórico nunca pode apagar o resultado da tarefa
                with db.conectar() as c:
                    db.evento(c, projeto_id, 'TAREFA_' + estado.upper().replace('Í', 'I'), 'sistema', tarefa=tid, tipo_tarefa=tipo, erro=erro)
            except Exception:
                traceback.print_exc()
        with _trava:
            _ativas.discard(tid)
            if not _ativas:
                _acordado(False)

    threading.Thread(target=rodar, daemon=True, name=f'tarefa-{tid}').start()
    return tid


def cancelar(tid):
    with db.conectar() as c:
        c.execute('UPDATE tarefa SET cancelar=1 WHERE id=? AND estado IN ("na fila", "rodando")', (tid,))


def ler(tid):
    with db.conectar() as c:
        r = c.execute('SELECT * FROM tarefa WHERE id=?', (tid,)).fetchone()
    if not r:
        return None
    t = dict(r)
    for k in ('fontes', 'avisos', 'resultado'):
        t[k] = json.loads(t[k]) if t.get(k) else ({} if k == 'fontes' else [] if k == 'avisos' else None)
    ult = dt.datetime.fromisoformat(t['atualizado_em'])
    t['segundos_sem_noticia'] = int((dt.datetime.now().astimezone() - ult).total_seconds())
    t['parece_travada'] = t['estado'] == 'rodando' and t['segundos_sem_noticia'] > SEM_NOTICIA
    ini = dt.datetime.fromisoformat(t['criado_em'])
    fim = dt.datetime.fromisoformat(t['fim_em']) if t.get('fim_em') else dt.datetime.now().astimezone()
    t['duracao_s'] = int((fim - ini).total_seconds())
    return t


def listar(projeto_id=None, limite=30):
    with db.conectar() as c:
        q = 'SELECT id FROM tarefa ' + ('WHERE projeto_id=? ' if projeto_id else '') + 'ORDER BY id DESC LIMIT ?'
        ids = [r['id'] for r in c.execute(q, ((projeto_id, limite) if projeto_id else (limite,)))]
    return [ler(i) for i in ids]


def contar_terminadas():
    with db.conectar() as c:
        return c.execute("SELECT COUNT(*) FROM tarefa WHERE estado NOT IN ('rodando', 'na fila')").fetchone()[0]


def limpar_concluidas():
    """Apaga do registro as tarefas que já terminaram (concluídas, com falha, canceladas ou interrompidas). As que estão rodando ou na
    fila ficam. Só o registro da tarefa sai: versões, comprovantes e o banco de vagas não mudam. Devolve quantas foram apagadas."""
    with db.conectar() as c:
        return c.execute("DELETE FROM tarefa WHERE estado NOT IN ('rodando', 'na fila')").rowcount


def marcar_interrompidas():
    """Ao abrir o sistema: tarefas que estavam 'rodando' quando ele foi fechado ficam como interrompidas (não somem)."""
    with db.conectar() as c:
        c.execute('UPDATE tarefa SET estado="interrompida", erro="o sistema foi fechado durante a tarefa", fim_em=? WHERE estado IN ("rodando", "na fila")', (db.agora(),))


async def com_limite(coro, segundos, ctx=None, fonte=None):
    """Executa com limite de tempo; registra a falha na fonte (em vez de travar a tarefa inteira)."""
    try:
        return await asyncio.wait_for(coro, segundos)
    except asyncio.TimeoutError:
        if ctx and fonte:
            ctx.fonte(fonte, 'falhou', f'sem resposta em {segundos} s')
        return None
