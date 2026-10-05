"""Persistência local (SQLite). Cada gravação cria uma NOVA versão do projeto: nada é sobrescrito ou apagado.
Eventos (quem, quando, o quê) ficam num log só de inclusão.
Única exceção: apagar_projeto, a pedido da OSC, para um projeto já removido da lista (fica o registro do que foi apagado)."""
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3

from .modelo import Projeto

PASTA_DADOS = os.environ.get('ORCAMENTO_DADOS', os.path.join(os.path.dirname(__file__), '..', 'dados'))
ESQUEMA = """
CREATE TABLE IF NOT EXISTS projeto (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versao (id INTEGER PRIMARY KEY, projeto_id INTEGER NOT NULL, numero INTEGER NOT NULL,
    criado_em TEXT NOT NULL, autor TEXT, motivo TEXT, json TEXT NOT NULL, UNIQUE(projeto_id, numero));
CREATE TABLE IF NOT EXISTS evento (id INTEGER PRIMARY KEY, projeto_id INTEGER, quando TEXT NOT NULL, autor TEXT,
    tipo TEXT NOT NULL, detalhe TEXT);
CREATE TABLE IF NOT EXISTS cnpj_cache (cnpj TEXT PRIMARY KEY, consultado_em TEXT NOT NULL, situacao TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS arquivo (sha256 TEXT PRIMARY KEY, nome_original TEXT, caminho TEXT NOT NULL, criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tarefa (id INTEGER PRIMARY KEY, projeto_id INTEGER, tipo TEXT NOT NULL, titulo TEXT, estado TEXT NOT NULL,
    progresso REAL DEFAULT 0, etapa TEXT, fontes TEXT, avisos TEXT, criado_em TEXT NOT NULL, atualizado_em TEXT, fim_em TEXT,
    resultado TEXT, erro TEXT, cancelar INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS loja_cnpj (loja TEXT PRIMARY KEY, cnpj TEXT, razao TEXT, origem TEXT, consultado_em TEXT);
CREATE TABLE IF NOT EXISTS vaga_banco (url TEXT PRIMARY KEY, cargo_chave TEXT NOT NULL, cargo TEXT, titulo TEXT, empresa TEXT, cidade TEXT, uf TEXT,
    faixa_min INTEGER, faixa_max INTEGER, plataforma TEXT, data_vaga TEXT, coletada_em TEXT NOT NULL, valida_ate TEXT NOT NULL,
    cnpj TEXT, cnpj_status TEXT, cnpj_motivo TEXT, razao TEXT, pdf TEXT, sha256 TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS empresa_cnpj (chave TEXT PRIMARY KEY, consultado_em TEXT NOT NULL, json TEXT);
CREATE TABLE IF NOT EXISTS ia_log (id INTEGER PRIMARY KEY, quando TEXT NOT NULL, projeto_id INTEGER, tipo TEXT, modelo TEXT, pergunta TEXT, resposta TEXT);
CREATE TABLE IF NOT EXISTS produto_banco (projeto_id INTEGER NOT NULL, item INTEGER NOT NULL, descricao TEXT NOT NULL, pesquisado_em TEXT NOT NULL,
    json TEXT, PRIMARY KEY (projeto_id, item, descricao));
CREATE TRIGGER IF NOT EXISTS evento_imutavel_u BEFORE UPDATE ON evento BEGIN SELECT RAISE(ABORT, 'log de eventos é imutável'); END;
CREATE TRIGGER IF NOT EXISTS evento_imutavel_d BEFORE DELETE ON evento BEGIN SELECT RAISE(ABORT, 'log de eventos é imutável'); END;
CREATE TRIGGER IF NOT EXISTS versao_imutavel_u BEFORE UPDATE ON versao BEGIN SELECT RAISE(ABORT, 'versões são imutáveis'); END;
"""


def agora():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def conectar():
    os.makedirs(PASTA_DADOS, exist_ok=True)
    c = sqlite3.connect(os.path.join(PASTA_DADOS, 'orcamento.db'), timeout=30)  # tarefas em segundo plano também gravam
    c.row_factory = sqlite3.Row
    c.executescript(ESQUEMA)
    _migrar(c)
    return c


_MIGRADO = set()


def _migrar(c):
    """Colunas acrescentadas depois da 1ª versão do banco (uma vez por arquivo de dados)."""
    if PASTA_DADOS in _MIGRADO:
        return
    if 'removido_em' not in [r[1] for r in c.execute('PRAGMA table_info(projeto)')]:
        c.execute('ALTER TABLE projeto ADD COLUMN removido_em TEXT')   # projeto removido da lista (nada é apagado; dá para restaurar)
    if 'descartada_em' not in [r[1] for r in c.execute('PRAGMA table_info(vaga_banco)')]:
        c.execute('ALTER TABLE vaga_banco ADD COLUMN descartada_em TEXT')   # vaga que a OSC descartou (não aparece nem entra; dá para mostrar de novo)
    _MIGRADO.add(PASTA_DADOS)


def evento(c, projeto_id, tipo, autor='usuário', **detalhe):
    c.execute('INSERT INTO evento (projeto_id, quando, autor, tipo, detalhe) VALUES (?,?,?,?,?)',
              (projeto_id, agora(), autor, tipo, json.dumps(detalhe, ensure_ascii=False, default=str)))


def criar(p: Projeto, autor='usuário', motivo='criação'):
    with conectar() as c:
        pid = c.execute('INSERT INTO projeto (nome, criado_em) VALUES (?,?)', (p.nome, agora())).lastrowid
        c.execute('INSERT INTO versao (projeto_id, numero, criado_em, autor, motivo, json) VALUES (?,?,?,?,?,?)',
                  (pid, 1, agora(), autor, motivo, p.model_dump_json()))
        evento(c, pid, 'PROJETO_CRIADO', autor, motivo=motivo)
    return pid


def salvar(pid, p: Projeto, autor='usuário', motivo='', **detalhe):
    with conectar() as c:
        n = c.execute('SELECT COALESCE(MAX(numero),0)+1 FROM versao WHERE projeto_id=?', (pid,)).fetchone()[0]
        c.execute('INSERT INTO versao (projeto_id, numero, criado_em, autor, motivo, json) VALUES (?,?,?,?,?,?)',
                  (pid, n, agora(), autor, motivo, p.model_dump_json()))
        evento(c, pid, 'VERSAO_SALVA', autor, versao=n, motivo=motivo, **detalhe)
    return n


def carregar(pid, numero=None):
    with conectar() as c:
        q = 'SELECT json, numero FROM versao WHERE projeto_id=? ' + ('AND numero=?' if numero else 'ORDER BY numero DESC LIMIT 1')
        row = c.execute(q, (pid, numero) if numero else (pid,)).fetchone()
    return (Projeto.model_validate_json(row['json']), row['numero']) if row else (None, None)


def listar(removidos=False):
    """Projetos em uso (padrão) ou os removidos da lista."""
    with conectar() as c:
        return [dict(r) for r in c.execute(
            'SELECT p.id, p.nome, p.criado_em, p.removido_em, MAX(v.numero) AS versoes, MAX(v.criado_em) AS alterado_em '
            'FROM projeto p JOIN versao v ON v.projeto_id=p.id WHERE p.removido_em IS ' + ('NOT NULL' if removidos else 'NULL')
            + ' GROUP BY p.id ORDER BY p.id DESC')]


def removido_em(pid):
    with conectar() as c:
        row = c.execute('SELECT removido_em FROM projeto WHERE id=?', (pid,)).fetchone()
    return row['removido_em'] if row else None


def remover_projeto(pid, autor='usuário'):
    """Tira o projeto da lista e das rotinas automáticas. Versões, eventos e comprovantes continuam guardados; dá para restaurar."""
    with conectar() as c:
        c.execute('UPDATE projeto SET removido_em=? WHERE id=? AND removido_em IS NULL', (agora(), pid))
        evento(c, pid, 'PROJETO_REMOVIDO', autor)


def restaurar_projeto(pid, autor='usuário'):
    with conectar() as c:
        c.execute('UPDATE projeto SET removido_em=NULL WHERE id=?', (pid,))
        evento(c, pid, 'PROJETO_RESTAURADO', autor)


def existe(pid):
    with conectar() as c:
        return c.execute('SELECT 1 FROM projeto WHERE id=?', (pid,)).fetchone() is not None


def apagar_projeto(pid, autor='usuário'):
    """Apaga DE VEZ um projeto que já foi removido da lista: versões, histórico, tarefas, registros da IA, banco de produtos e a pasta de
    comprovantes. NÃO TEM VOLTA. É a única exceção à regra de nunca apagar: por isso exige a remoção antes e deixa um registro no log
    (quem, quando, qual projeto, quantas versões e arquivos). O que é comum a todos os projetos (banco de vagas, CNPJs consultados) fica.
    Devolve dict(nome, versoes, arquivos, sobraram)."""
    pid = int(pid)
    with conectar() as c:
        row = c.execute('SELECT nome, removido_em FROM projeto WHERE id=?', (pid,)).fetchone()
        if row is None:
            raise ValueError('projeto não encontrado')
        if not row['removido_em']:
            raise ValueError('só dá para apagar de vez um projeto que já foi removido da lista')
        if c.execute("SELECT 1 FROM tarefa WHERE projeto_id=? AND estado IN ('rodando', 'na fila')", (pid,)).fetchone():
            raise ValueError('há uma tarefa em andamento neste projeto')
        nome = row['nome']
        n_v = c.execute('SELECT COUNT(*) FROM versao WHERE projeto_id=?', (pid,)).fetchone()[0]
        n_e = c.execute('SELECT COUNT(*) FROM evento WHERE projeto_id=?', (pid,)).fetchone()[0]
        pasta = os.path.realpath(os.path.join(PASTA_DADOS, 'projetos', str(pid)))
        n_a = sum(len(fs) for _, _, fs in os.walk(pasta)) if os.path.isdir(pasta) else 0
        c.execute('DROP TRIGGER IF EXISTS evento_imutavel_d')   # o log é imutável; só esta rotina apaga os eventos do projeto apagado
        c.execute('DELETE FROM evento WHERE projeto_id=?', (pid,))
        c.execute("CREATE TRIGGER IF NOT EXISTS evento_imutavel_d BEFORE DELETE ON evento BEGIN SELECT RAISE(ABORT, 'log de eventos é imutável'); END")
        for tabela in ('versao', 'tarefa', 'ia_log', 'produto_banco'):
            c.execute(f'DELETE FROM {tabela} WHERE projeto_id=?', (pid,))
        # a coleta diária de vagas é uma rotina do sistema (sem projeto), mas o registro dela lista os cargos dos projetos da época:
        # com o projeto apagado, os registros já concluídos saem também (as vagas guardadas no banco de vagas ficam)
        c.execute("DELETE FROM tarefa WHERE projeto_id IS NULL AND tipo='vagas_diaria' AND estado NOT IN ('rodando', 'na fila')")
        c.execute('DELETE FROM arquivo WHERE caminho LIKE ?', (f'projetos/{pid}/%',))
        c.execute('DELETE FROM projeto WHERE id=?', (pid,))
        evento(c, None, 'PROJETO_APAGADO', autor, projeto=pid, nome=nome, versoes=n_v, eventos=n_e, arquivos=n_a)
    sobraram = 0
    base = os.path.realpath(os.path.join(PASTA_DADOS, 'projetos'))
    if os.path.isdir(pasta) and os.path.dirname(pasta) == base:   # só a pasta deste projeto, dentro da pasta de dados
        shutil.rmtree(pasta, ignore_errors=True)
        sobraram = sum(len(fs) for _, _, fs in os.walk(pasta)) if os.path.isdir(pasta) else 0   # arquivo aberto em outro programa não sai
    return dict(nome=nome, versoes=n_v, arquivos=n_a, sobraram=sobraram)


def historico(pid):
    with conectar() as c:
        v = [dict(r) for r in c.execute('SELECT numero, criado_em, autor, motivo FROM versao WHERE projeto_id=? ORDER BY numero DESC', (pid,))]
        e = [dict(r) for r in c.execute('SELECT quando, autor, tipo, detalhe FROM evento WHERE projeto_id=? ORDER BY id DESC LIMIT 300', (pid,))]
    return v, e


def guardar_arquivo(pid, nome, conteudo: bytes):
    """Evidência imutável: guardada pelo SHA-256; devolve (sha, caminho relativo)."""
    sha = hashlib.sha256(conteudo).hexdigest()
    rel = '/'.join(['projetos', str(pid), 'evidencias', f'{sha[:12]}_{os.path.basename(nome)}'])  # portável
    ab = os.path.join(PASTA_DADOS, rel)
    os.makedirs(os.path.dirname(ab), exist_ok=True)
    if not os.path.exists(ab):
        with open(ab, 'wb') as f:
            f.write(conteudo)
    with conectar() as c:
        c.execute('INSERT OR IGNORE INTO arquivo (sha256, nome_original, caminho, criado_em) VALUES (?,?,?,?)', (sha, nome, rel, agora()))
        evento(c, pid, 'EVIDENCIA_GUARDADA', arquivo=nome, sha256=sha)
    return sha, rel


def caminho_absoluto(rel):
    return os.path.join(PASTA_DADOS, rel)


# ------------------------------------------------------------------ banco de produtos (opções válidas de cada item, da última pesquisa)
def produtos_guardar(pid, item, descricao, opcoes):
    with conectar() as c:
        c.execute('INSERT OR REPLACE INTO produto_banco (projeto_id, item, descricao, pesquisado_em, json) VALUES (?,?,?,?,?)',
                  (pid, item, descricao, agora(), json.dumps(opcoes, ensure_ascii=False, default=str)))


def produtos_do_banco(pid, item):
    """{descrição do item: dict(pesquisado_em, opcoes)}"""
    with conectar() as c:
        return {r['descricao']: dict(pesquisado_em=r['pesquisado_em'], opcoes=json.loads(r['json'] or '[]'))
                for r in c.execute('SELECT * FROM produto_banco WHERE projeto_id=? AND item=?', (pid, item))}


# ------------------------------------------------------------------ dados locais pesados (fora do OneDrive)
PASTA_LOCAL = os.environ.get('ORCAMENTO_LOCAL') or os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'OrcamentoOSC')


def conectar_cache():
    """Cache das buscas nas lojas (renovado a cada dia). Fica fora do OneDrive para não sincronizar à toa."""
    os.makedirs(PASTA_LOCAL, exist_ok=True)
    c = sqlite3.connect(os.path.join(PASTA_LOCAL, 'cache_buscas.sqlite'), timeout=30)
    c.execute('CREATE TABLE IF NOT EXISTS busca (chave TEXT PRIMARY KEY, dia TEXT NOT NULL, json TEXT)')
    return c


def cache_ler(chave):
    with conectar_cache() as c:
        r = c.execute('SELECT json FROM busca WHERE chave=? AND dia=?', (chave, dt.date.today().isoformat())).fetchone()
    return json.loads(r[0]) if r else None


def cache_gravar(chave, valor):
    with conectar_cache() as c:
        c.execute('INSERT OR REPLACE INTO busca (chave, dia, json) VALUES (?,?,?)', (chave, dt.date.today().isoformat(), json.dumps(valor, ensure_ascii=False)))


def cache_prefixo(prefixo):
    """Todas as entradas de hoje cuja chave começa com o prefixo: {chave: valor}."""
    with conectar_cache() as c:
        return {r[0]: json.loads(r[1]) for r in c.execute('SELECT chave, json FROM busca WHERE substr(chave, 1, ?) = ? AND dia=?',
                                                          (len(prefixo), prefixo, dt.date.today().isoformat()))}


def cache_limpar_antigos():
    with conectar_cache() as c:
        c.execute('DELETE FROM busca WHERE dia < ?', (dt.date.today().isoformat(),))


# ------------------------------------------------------------------ lojas que pediram verificação humana (CAPTCHA)
DIAS_BLOQUEIO = 30   # decisão da OSC (27/09/2026): loja que barra com CAPTCHA é descartada; volta a ser tentada depois de 30 dias


def _conectar_bloqueio():
    c = conectar_cache()
    c.execute('CREATE TABLE IF NOT EXISTS loja_bloqueio (loja TEXT PRIMARY KEY, desde TEXT NOT NULL, ate TEXT NOT NULL, motivo TEXT, vezes INTEGER DEFAULT 1)')
    return c


def loja_bloquear(loja, motivo, dias=DIAS_BLOQUEIO):
    hoje = dt.date.today()
    with _conectar_bloqueio() as c:
        c.execute("""INSERT INTO loja_bloqueio (loja, desde, ate, motivo) VALUES (?,?,?,?)
                     ON CONFLICT(loja) DO UPDATE SET ate=excluded.ate, motivo=excluded.motivo, vezes=vezes+1""",
                  (loja, hoje.isoformat(), (hoje + dt.timedelta(days=dias)).isoformat(), motivo))


def lojas_bloqueadas():
    """{loja: dict(desde, ate, motivo, vezes)} das lojas descartadas por bloqueio ainda dentro do prazo."""
    with _conectar_bloqueio() as c:
        return {r[0]: dict(desde=r[1], ate=r[2], motivo=r[3], vezes=r[4])
                for r in c.execute('SELECT loja, desde, ate, motivo, vezes FROM loja_bloqueio WHERE ate >= ?', (dt.date.today().isoformat(),))}


def loja_liberar(loja):
    with _conectar_bloqueio() as c:
        c.execute('DELETE FROM loja_bloqueio WHERE loja=?', (loja,))
