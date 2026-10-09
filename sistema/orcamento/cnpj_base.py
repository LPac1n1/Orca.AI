"""Base oficial do CNPJ (Receita Federal, Dados Abertos) num índice LOCAL — decisão D8 da OSC.

Para que serve: achar o CNPJ do empregador pelo nome da vaga e, principalmente, saber se existe OUTRA empresa ativa com o mesmo
nome (homônima). Online não dá para saber isso; com a base, dá (ex.: 25 empresas ativas chamadas "Clave de Sol").

- Guarda só estabelecimentos ATIVOS: CNPJ, matriz/filial, nome fantasia, razão social, UF, município e CNAE principal.
- Fica FORA do OneDrive (%LOCALAPPDATA%\\OrcamentoOSC\\receita), para não sincronizar ~14 GB com a nuvem.
- Atualização mensal automática: baixa a pasta nova (Empresas + Estabelecimentos + Municípios, ~6,4 GB), monta um índice novo
  ao lado e só troca quando termina; o índice anterior continua valendo enquanto isso.
Fonte: https://arquivos.receitafederal.gov.br (compartilhamento público da Receita, pastas AAAA-MM)."""
import csv
import glob
import io
import os
import re
import shutil
import sqlite3
import time
import unicodedata
import zipfile

from . import db

WEBDAV = 'https://arquivos.receitafederal.gov.br/public.php/webdav/'
WEBDAV_USUARIO = 'YggdBLfdninEJX9'   # identificador PÚBLICO do compartilhamento de dados abertos da Receita (sem senha)
PASTA = os.path.join(db.PASTA_LOCAL, 'receita')
BASE = os.environ.get('BASE_CNPJ_LOCAL') or os.path.join(PASTA, 'cnpj.sqlite')
ARQUIVOS = ['Municipios.zip', 'Cnaes.zip'] + [f'Empresas{i}.zip' for i in range(10)] + [f'Estabelecimentos{i}.zip' for i in range(10)]
GENERICAS = set('ltda s a sa me epp eireli sociedade limitada servicos servico comercio de da do das dos e em associacao grupo instituto '
                'empresa empresas brasil brasileira cia companhia holding'.split())
csv.field_size_limit(10_000_000)


def sa(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', (s or '').lower()) if not unicodedata.combining(c))


# ------------------------------------------------------------------ situação da base local
def situacao():
    if not os.path.exists(BASE):
        return dict(existe=False)
    try:
        with sqlite3.connect(BASE) as c:
            meta = dict(c.execute('SELECT chave, valor FROM meta').fetchall())
    except Exception:
        meta = {}
    return dict(existe=True, arquivo=BASE, tamanho_mb=round(os.path.getsize(BASE) / 1048576), montado_em=meta.get('montado_em'),
                mes=meta.get('pasta_origem'), estabelecimentos=meta.get('estabelecimentos'))


def pastas_remotas():
    import httpx
    r = httpx.request('PROPFIND', WEBDAV, headers={'Depth': '1'}, auth=(WEBDAV_USUARIO, ''), timeout=60)
    return sorted(set(re.findall(r'/webdav/(\d{4}-\d{2})/', r.text)))


def arquivos_remotos(mes):
    import httpx
    r = httpx.request('PROPFIND', WEBDAV + mes + '/', headers={'Depth': '1'}, auth=(WEBDAV_USUARIO, ''), timeout=60)
    out = {}
    for resp in re.findall(r'<d:response>(.*?)</d:response>', r.text, re.S):
        href = re.search(r'<d:href>([^<]*)</d:href>', resp).group(1)
        tam = re.search(r'<d:getcontentlength>(\d+)</d:getcontentlength>', resp)
        if tam:
            out[href.rsplit('/', 1)[-1]] = int(tam.group(1))
    return out


def precisa_atualizar():
    """(True/False, mês mais novo disponível, mês da base local)."""
    try:
        novo = pastas_remotas()[-1]
    except Exception:
        return False, None, situacao().get('mes')
    atual = situacao().get('mes')
    return (atual is None or novo > atual), novo, atual


# ------------------------------------------------------------------ download e montagem
def baixar(mes, ctx=None, base_pct=0, peso=60):
    """Baixa os arquivos do mês (retoma arquivos pela metade). Progresso proporcional aos bytes."""
    import httpx
    destino = os.path.join(PASTA, mes); os.makedirs(destino, exist_ok=True)
    tamanhos = {k: v for k, v in arquivos_remotos(mes).items() if k in ARQUIVOS}
    total = sum(tamanhos.values()) or 1
    feitos = sum(min(os.path.getsize(os.path.join(destino, k)), v) for k, v in tamanhos.items() if os.path.exists(os.path.join(destino, k)))
    for nome, tam in tamanhos.items():
        arq = os.path.join(destino, nome)
        for tentativa in range(5):
            ja = os.path.getsize(arq) if os.path.exists(arq) else 0
            if ja >= tam:
                break
            try:
                with httpx.stream('GET', WEBDAV + mes + '/' + nome, auth=(WEBDAV_USUARIO, ''), headers={'Range': f'bytes={ja}-'} if ja else {},
                                  timeout=httpx.Timeout(60, read=120)) as r, open(arq, 'ab' if ja else 'wb') as f:
                    for bloco in r.iter_bytes(1 << 20):
                        f.write(bloco); feitos += len(bloco)
                        if ctx:
                            ctx.progresso(base_pct + peso * feitos / total, f'Baixando a base da Receita ({mes}): {nome} — {feitos / 1073741824:.1f} de {total / 1073741824:.1f} GB')
            except Exception as e:
                if ctx:
                    ctx.fonte('Receita (download)', 'repetindo', f'{nome}: {type(e).__name__}; tentando de novo')
                time.sleep(10 * (tentativa + 1))
        if os.path.getsize(arq) < tam:
            raise RuntimeError(f'não foi possível baixar {nome} depois de 5 tentativas')
    if ctx:
        ctx.fonte('Receita (download)', 'ok', f'{len(tamanhos)} arquivos')
    return destino


def _linhas_zip(caminho):
    with zipfile.ZipFile(caminho) as z:
        for nome in z.namelist():
            with z.open(nome) as f:
                yield from csv.reader(io.TextIOWrapper(f, encoding='latin-1', newline=''), delimiter=';', quotechar='"')


def montar(pasta_zips, arquivo_db, ctx=None, base_pct=60, peso=40):
    t0 = time.time()
    if os.path.exists(arquivo_db):
        os.remove(arquivo_db)
    con = sqlite3.connect(arquivo_db); cur = con.cursor()
    cur.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-400000;
        CREATE TABLE empresa(basico TEXT PRIMARY KEY, razao TEXT);
        CREATE TABLE estab(cnpj TEXT PRIMARY KEY, basico TEXT, matriz INTEGER, fantasia TEXT, uf TEXT, municipio TEXT, cnae TEXT);
        CREATE TABLE municipio(codigo TEXT PRIMARY KEY, nome TEXT);
        CREATE TABLE meta(chave TEXT PRIMARY KEY, valor TEXT);
    """)
    zips = sorted(glob.glob(os.path.join(pasta_zips, '*.zip')))
    passos = len(zips) + 3; n = 0

    def passo(txt):
        nonlocal n
        n += 1
        if ctx:
            ctx.progresso(base_pct + peso * n / passos, f'Montando o índice local: {txt}')
    for z in [x for x in zips if os.path.basename(x).startswith('Municipios')]:
        cur.executemany('INSERT OR REPLACE INTO municipio VALUES (?,?)', ((r[0], r[1]) for r in _linhas_zip(z) if len(r) >= 2)); passo('municípios')
    for z in [x for x in zips if os.path.basename(x).startswith('Empresas')]:
        lote = []
        for r in _linhas_zip(z):
            if len(r) >= 2:
                lote.append((r[0], r[1]))
                if len(lote) >= 200_000:
                    cur.executemany('INSERT OR REPLACE INTO empresa VALUES (?,?)', lote); lote = []
        cur.executemany('INSERT OR REPLACE INTO empresa VALUES (?,?)', lote); con.commit(); passo(os.path.basename(z))
    ativos = 0
    for z in [x for x in zips if os.path.basename(x).startswith('Estabelecimentos')]:
        lote = []
        for r in _linhas_zip(z):
            if len(r) < 21 or r[5] != '02':  # 02 = ATIVA
                continue
            ativos += 1
            lote.append((r[0] + r[1] + r[2], r[0], 1 if r[3] == '1' else 0, r[4], r[19], r[20], r[11]))
            if len(lote) >= 200_000:
                cur.executemany('INSERT OR REPLACE INTO estab VALUES (?,?,?,?,?,?,?)', lote); lote = []
        cur.executemany('INSERT OR REPLACE INTO estab VALUES (?,?,?,?,?,?,?)', lote); con.commit(); passo(os.path.basename(z))
    cur.executescript('CREATE INDEX ix_estab_basico ON estab(basico); DELETE FROM empresa WHERE NOT EXISTS (SELECT 1 FROM estab e WHERE e.basico = empresa.basico);')
    con.commit(); passo('empresas sem estabelecimento ativo descartadas')
    # índice de palavras sem posições (detail=none): as buscas do sistema não precisam de frase exata e fica bem mais rápido de montar
    cur.executescript("""CREATE VIRTUAL TABLE nomes USING fts5(nome, cnpj UNINDEXED, tokenize='unicode61 remove_diacritics 2', detail=none, columnsize=0);
        INSERT INTO nomes(nome, cnpj) SELECT COALESCE(e.fantasia,'') || ' | ' || COALESCE(m.razao,''), e.cnpj FROM estab e LEFT JOIN empresa m ON m.basico = e.basico;""")
    for k, v in (('montado_em', time.strftime('%Y-%m-%d %H:%M')), ('pasta_origem', os.path.basename(os.path.normpath(pasta_zips))), ('estabelecimentos', str(ativos))):
        cur.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (k, v))
    con.commit(); passo('índice de nomes'); cur.execute('VACUUM'); con.close()
    return dict(estabelecimentos=ativos, segundos=round(time.time() - t0))


def atualizar(ctx=None, forcar=False):
    """Tarefa mensal: baixa a pasta mais nova e troca o índice só no fim. Apaga os arquivos do mês anterior depois da troca."""
    precisa, novo, atual = precisa_atualizar()
    if not (precisa or forcar) or not novo:
        return dict(atualizado=False, mes=atual, motivo='a base local já é a mais recente' if atual else 'não foi possível consultar a Receita')
    pasta = baixar(novo, ctx)
    temp = BASE + '.novo'
    r = montar(pasta, temp, ctx)
    os.replace(temp, BASE)
    for antiga in glob.glob(os.path.join(PASTA, '????-??')):
        if os.path.basename(antiga) != novo:
            shutil.rmtree(antiga, ignore_errors=True)
    return dict(atualizado=True, mes=novo, **r)


# ------------------------------------------------------------------ consultas
def buscar(nome, limite=2000, db_path=None):
    """Estabelecimentos ATIVOS cujo nome fantasia ou razão social contém TODAS as palavras distintivas do nome."""
    arq = db_path or BASE
    palavras = [w for w in re.findall(r'[a-z0-9]+', sa(nome)) if w not in GENERICAS]
    if not palavras or not os.path.exists(arq):
        return []
    q = ' AND '.join(f'"{w}"' for w in palavras)
    with sqlite3.connect(arq) as c:
        rows = c.execute("""SELECT e.cnpj, e.matriz, e.fantasia, m.razao, e.uf, mu.nome, e.cnae FROM nomes n
                            JOIN estab e ON e.cnpj = n.cnpj LEFT JOIN empresa m ON m.basico = e.basico LEFT JOIN municipio mu ON mu.codigo = e.municipio
                            WHERE nomes MATCH ? LIMIT ?""", (q, limite)).fetchall()
    return [dict(cnpj=r[0], matriz=bool(r[1]), fantasia=r[2], razao=r[3], uf=r[4], municipio=r[5], cnae=r[6]) for r in rows]


def estabelecimentos(raiz, db_path=None):
    """TODOS os estabelecimentos ATIVOS de uma empresa (pelos 8 primeiros dígitos do CNPJ), e não só os que levam o nome procurado:
    é com eles que se sabe se a empresa existe no estado ou na cidade da vaga."""
    arq = db_path or BASE
    d = re.sub(r'\D', '', raiz or '')[:8]
    if len(d) != 8 or not os.path.exists(arq):
        return []
    with sqlite3.connect(arq) as c:
        rows = c.execute("""SELECT e.cnpj, e.matriz, e.fantasia, m.razao, e.uf, mu.nome, e.cnae FROM estab e LEFT JOIN empresa m ON m.basico = e.basico
                            LEFT JOIN municipio mu ON mu.codigo = e.municipio WHERE e.basico=? ORDER BY e.cnpj LIMIT 5000""", (d,)).fetchall()
    return [dict(cnpj=r[0], matriz=bool(r[1]), fantasia=r[2], razao=r[3], uf=r[4], municipio=r[5], cnae=r[6]) for r in rows]


def por_cnpj(cnpj, db_path=None):
    arq = db_path or BASE
    d = re.sub(r'\D', '', cnpj or '')
    if len(d) != 14 or not os.path.exists(arq):
        return None
    with sqlite3.connect(arq) as c:
        r = c.execute("""SELECT e.cnpj, e.matriz, e.fantasia, m.razao, e.uf, mu.nome, e.cnae FROM estab e LEFT JOIN empresa m ON m.basico = e.basico
                         LEFT JOIN municipio mu ON mu.codigo = e.municipio WHERE e.cnpj=?""", (d,)).fetchone()
    return dict(cnpj=r[0], matriz=bool(r[1]), fantasia=r[2], razao=r[3], uf=r[4], municipio=r[5], cnae=r[6], situacao='ATIVA') if r else None
