"""CNPJ do EMPREGADOR a partir do nome que aparece na vaga (as plataformas não trazem o CNPJ).

Ordem (validada na Fase 1B, §10.5–10.7: 9/15 do gabarito de teste resolvidos só pela base, sem nenhum erro):
 1. Base oficial da Receita (local): nome ÚNICO entre as empresas ativas do Brasil, ou único no município da vaga → 🟢.
 2. Senão: buscadores (Ecosia + Yahoo; Brave de reserva) + CNPJ publicado no SITE OFICIAL da empresa; cada número é conferido na
    API pública (nome confere, situação ATIVA).
 3. Travas: empresa estrangeira → 🔴; CNPJ em outra UF que a da vaga → 🟡; homônimas na base da Receita → 🟡
    (salvo CNPJ do site oficial). Em dúvida, NUNCA escolhe: 🟡 e o motor passa para a próxima vaga.
Resultado: dict(status 🟢|🟡|🔴, cnpj, razao_social, nome_fantasia, municipio, uf, fonte, candidatos, motivo).
Cada nome consultado fica guardado 30 dias (menos consultas aos buscadores, menos bloqueio)."""
import asyncio
import datetime as dt
import json
import re
import time
import unicodedata
from urllib.parse import quote_plus

from rapidfuzz import fuzz

from . import db
from . import cnpj_base

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
CNPJ_RE = re.compile(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b')
BUSCADORES = [('Ecosia', lambda q: f'https://www.ecosia.org/search?q={quote_plus(q)}'),
              ('Yahoo', lambda q: f'https://br.search.yahoo.com/search?p={quote_plus(q)}'),
              ('Brave', lambda q: f'https://search.brave.com/search?q={quote_plus(q)}')]
BLOQ = ['captcha', 'unusual traffic', 'trafego incomum', 'verify you are human', 'are you a robot', 'nao e um robo']
GENERICAS = cnpj_base.GENERICAS
NAO_OFICIAIS = re.compile(r'cnpj|econodata|serasa|jusbrasil|casadosdados|solutudo|consultasocio|empresasdobrasil|linkana|informecadastral|'
                          r'linkedin|facebook|instagram|twitter|x\.com|youtube|tiktok|wikipedia|gupy|infojobs|catho|vagas\.com|indeed|glassdoor|'
                          r'reclameaqui|bne\.com|jooble|trabalhabrasil|google|bing|yahoo|ecosia|brave|search\.|mapa|guiamais|apontador|telelistas|'
                          r'transparencia|gov\.br|jus\.br|escavador|empresaqui|cadastroempresa|b2bleads|speedio|dnb\.com|zoominfo', re.I)
UFS = {'acre': 'AC', 'alagoas': 'AL', 'amapa': 'AP', 'amazonas': 'AM', 'bahia': 'BA', 'ceara': 'CE', 'distrito federal': 'DF', 'espirito santo': 'ES',
       'goias': 'GO', 'maranhao': 'MA', 'mato grosso': 'MT', 'mato grosso do sul': 'MS', 'minas gerais': 'MG', 'para': 'PA', 'paraiba': 'PB', 'parana': 'PR',
       'pernambuco': 'PE', 'piaui': 'PI', 'rio de janeiro': 'RJ', 'rio grande do norte': 'RN', 'rio grande do sul': 'RS', 'rondonia': 'RO', 'roraima': 'RR',
       'santa catarina': 'SC', 'sao paulo': 'SP', 'sergipe': 'SE', 'tocantins': 'TO', 'brasilia': 'DF'}
INTERVALO_BUSCADOR = 4.0   # segundos entre consultas ao mesmo buscador (evita bloqueio)
_ultimo_uso = {}


def sa(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', (s or '').lower()) if not unicodedata.combining(c))


def limpa(s):
    s = re.sub(r'[^a-z0-9 ]', ' ', sa(s).replace('s/a', 'sa'))
    return [w for w in s.split() if w not in GENERICAS]


def dv_ok(d):
    if len(d) != 14 or len(set(d)) == 1:
        return False
    def dv(base, pesos):
        r = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return '0' if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return d[12] == dv(d[:12], p1) and d[13] == dv(d[:13], [6] + p1)


def confere(nome, j):
    """0 não confere · 1 nome contido no cadastro · 2 mesmas palavras."""
    alvo = limpa(nome)
    if not alvo:
        return 0
    melhor = 0
    for campo in (j.get('nome_fantasia'), j.get('razao_social')):
        cand = limpa(campo)
        if not cand:
            continue
        if fuzz.token_sort_ratio(' '.join(alvo), ' '.join(cand)) >= 92:
            return 2
        if fuzz.token_set_ratio(' '.join(alvo), ' '.join(cand)) >= 95 and len(cand) <= len(alvo) + 3:
            melhor = 1
    return melhor


def uf_da_vaga(cidade, uf):
    for x in (uf, cidade):
        x = sa(x).strip()
        if len(x) == 2 and x.upper() in UFS.values():
            return x.upper()
        if x in UFS:
            return UFS[x]
    return None


def _local(j, cidade, uf):
    u = uf_da_vaga(cidade, uf)
    ok_uf = not u or (j.get('uf') or '').upper() == u
    ok_cid = not cidade or uf_da_vaga(cidade, None) or sa(j.get('municipio')) == sa(cidade)
    return ok_uf and ok_cid


OUTRA_UF = 'pode ser filial ou homônima'


def conferir_local(r, cidade, uf, nome=None):
    """Trava do lugar. Empresa com sede num estado e vaga em outro é o normal (a vaga diz onde é o TRABALHO): isso só é dúvida quando existe
    OUTRA empresa ativa com o mesmo nome. Não é dúvida quando o CNPJ é o publicado no site oficial da empresa, nem quando ela é a única
    com esse nome na base da Receita (ajuste de 08/10/2026: 10 das 31 vagas "em dúvida" do banco estavam assim, sem haver homônima)."""
    if not r.get('cnpj'):
        return r
    if sa(r.get('municipio')) == 'exterior':
        return dict(r, status='🔴', motivo='empresa estrangeira (município EXTERIOR): não é o empregador no Brasil')
    u = uf_da_vaga(cidade, uf)
    if r['status'] == '🟢' and u and (r.get('uf') or '').upper() != u:
        if str(r.get('fonte', '')).startswith(('site oficial', 'texto da vaga')):
            return dict(r, motivo=f"{r['motivo']}; sede em {r.get('uf')}, vaga em {u}")
        h = homonimos_na_base(nome) if nome else None
        if h is not None and not [k for k in h if k != re.sub(r'\D', '', r['cnpj'])[:8]]:
            return dict(r, motivo=f"{r['motivo']}; sede em {r.get('uf')}, vaga em {u}: é a única empresa ativa com esse nome na base da Receita")
        return dict(r, status='🟡', motivo=f"{r['motivo']}; CNPJ em {r.get('uf')}, vaga em {u}: {OUTRA_UF}")
    return r


def candidatos_da_base(nome, cidade=None, uf=None, limite=8):
    """As empresas ATIVAS da base da Receita com esse nome (uma por empresa: o estabelecimento da cidade ou da UF da vaga, senão a matriz),
    para a OSC escolher com um clique quando o sistema fica em dúvida. As da cidade e da UF da vaga vêm primeiro."""
    if not nome or not cnpj_base.situacao().get('existe'):
        return []
    u, cid = uf_da_vaga(cidade, uf), (sa(cidade) if cidade and not uf_da_vaga(cidade, None) else None)
    por_raiz = {}
    for e in cnpj_base.buscar(nome, limite=2000):
        f = confere(nome, {'razao_social': e['razao'], 'nome_fantasia': e['fantasia']})
        if f:
            por_raiz.setdefault(e['cnpj'][:8], dict(forca=f, estabs=[]))['estabs'].append(e)
            por_raiz[e['cnpj'][:8]]['forca'] = max(por_raiz[e['cnpj'][:8]]['forca'], f)
    out = []
    for d in por_raiz.values():
        ests = d['estabs']
        e = (next((x for x in ests if cid and sa(x['municipio']) == cid), None) or next((x for x in ests if u and (x['uf'] or '').upper() == u), None)
             or next((x for x in ests if x['matriz']), ests[0]))
        out.append(dict(cnpj=e['cnpj'], razao=e['razao'], fantasia=e['fantasia'], municipio=e['municipio'], uf=e['uf'], matriz=e['matriz'], forca=d['forca'],
                        na_cidade=bool(cid and sa(e['municipio']) == cid), na_uf=bool(u and (e['uf'] or '').upper() == u), estabelecimentos=len(ests)))
    out.sort(key=lambda x: (not x['na_cidade'], not x['na_uf'], -x['forca'], x['razao'] or ''))
    return out[:limite]


async def cnpj_do_texto(api, nome, cnpjs):
    """CNPJ que a própria empresa escreveu no texto da vaga: se é válido, ATIVO e o nome confere, é o do empregador (não há o que adivinhar)."""
    for x in dict.fromkeys(re.sub(r'\D', '', c) for c in cnpjs or ()):
        if not dv_ok(x):
            continue
        b = cnpj_base.por_cnpj(x)
        if b and confere(nome, {'razao_social': b['razao'], 'nome_fantasia': b['fantasia']}):
            return dict(status='🟢', cnpj=x, razao_social=b['razao'], nome_fantasia=b['fantasia'], municipio=b['municipio'], uf=b['uf'], fonte='texto da vaga',
                        candidatos=[], motivo='CNPJ escrito no texto da própria vaga; nome confere e a empresa está ATIVA na base da Receita')
        j = None if b else await api.dados(x)
        if j and confere(nome, j) and (j.get('descricao_situacao_cadastral') or '').upper() == 'ATIVA':
            return dict(status='🟢', cnpj=x, razao_social=j.get('razao_social'), nome_fantasia=j.get('nome_fantasia'), municipio=j.get('municipio'), uf=j.get('uf'),
                        fonte='texto da vaga', candidatos=[], motivo='CNPJ escrito no texto da própria vaga; nome confere e a situação é ATIVA')
    return None


def homonimos_na_base(nome):
    if not cnpj_base.situacao().get('existe'):
        return None
    raizes = {}
    for r in cnpj_base.buscar(nome, limite=2000):
        if confere(nome, {'razao_social': r['razao'], 'nome_fantasia': r['fantasia']}) >= 1:
            raizes.setdefault(r['cnpj'][:8], r)
    return raizes


def conferir_homonimos(r, nome):
    if r.get('status') != '🟢' or not r.get('cnpj') or str(r.get('fonte', '')).startswith('site oficial'):
        return r
    h = homonimos_na_base(nome)
    if h is None:
        return dict(r, aviso='base da Receita indisponível: homônimos não conferidos')
    outros = [v for k, v in h.items() if k != r['cnpj'][:8]]
    if outros:
        return dict(r, status='🟡', motivo=f"{r['motivo']}; base da Receita: mais {len(outros)} empresa(s) ativa(s) com esse nome "
                    f"({', '.join(str(o['municipio']) + '/' + str(o['uf']) for o in outros[:3])})")
    return dict(r, motivo=r['motivo'] + '; base da Receita: nome único entre as empresas ativas')


def cnpj_pela_base(nome, cidade=None, uf=None):
    if not cnpj_base.situacao().get('existe'):
        return None
    por_raiz = {}
    prefixo = ' '.join(limpa(nome))
    for r in cnpj_base.buscar(nome, limite=2000):
        f = confere(nome, {'razao_social': r['razao'], 'nome_fantasia': r['fantasia']})
        if f == 1 and len(prefixo) >= 5 and any(' '.join(limpa(c)).startswith(prefixo) for c in (r['razao'], r['fantasia']) if c):
            f = 2
        if f:
            d = por_raiz.setdefault(r['cnpj'][:8], dict(forca=0, estabs=[]))
            d['forca'] = max(d['forca'], f); d['estabs'].append(r)
    if not por_raiz:
        return None
    cid = sa(cidade) if cidade and not uf_da_vaga(cidade, None) else None

    def escolher(raiz, criterio):
        ests = por_raiz[raiz]['estabs']
        e = next((x for x in ests if cid and sa(x['municipio']) == cid), None) or next((x for x in ests if x['matriz']), ests[0])
        return dict(status='🟢', cnpj=e['cnpj'], razao_social=e['razao'], nome_fantasia=e['fantasia'], municipio=e['municipio'], uf=e['uf'],
                    fonte='base da Receita (dados abertos)', candidatos=[], motivo=criterio)
    fortes = [k for k, v in por_raiz.items() if v['forca'] == 2]
    if len(por_raiz) == 1 and fortes:
        return escolher(fortes[0], 'base da Receita: única empresa ativa com esse nome no Brasil')
    if cid:
        na_cidade = [k for k, v in por_raiz.items() if any(sa(x['municipio']) == cid for x in v['estabs'])]
        if len(na_cidade) == 1 and na_cidade[0] in fortes:
            return escolher(na_cidade[0], f'base da Receita: {len(por_raiz)} empresas com esse nome no Brasil, uma só em {cidade}')
    return None


# ------------------------------------------------------------------ busca online (quando a base não resolve)
class Api:
    """Confirma um CNPJ em APIs públicas gratuitas (MinhaReceita, BrasilAPI), com memória na execução."""

    def __init__(self, c):
        self.c, self.memo = c, {}

    async def dados(self, d):
        """Os dados cadastrais do CNPJ. Primeiro a base da Receita deste computador, que responde na hora e só tem empresas ATIVAS (pesquisa
        completa de 09/10/2026: cada empresa levava de 2 a 4 minutos, quase tudo em consultas de CNPJ a serviços da internet, 8 por buscador).
        Os serviços públicos ficam para o CNPJ que não está na base (empresa baixada, inapta ou aberta depois da última atualização)."""
        if d in self.memo:
            return self.memo[d]
        try:
            b = cnpj_base.por_cnpj(d)
        except Exception:
            b = None
        if b:
            self.memo[d] = dict(razao_social=b.get('razao'), nome_fantasia=b.get('fantasia'), municipio=b.get('municipio'), uf=b.get('uf'),
                                descricao_situacao_cadastral='ATIVA', origem='base da Receita')
            return self.memo[d]
        for u in (f'https://minhareceita.org/{d}', f'https://brasilapi.com.br/api/cnpj/v1/{d}'):
            for _ in range(2):
                try:
                    r = await self.c.get(u, timeout=8)
                    if r.status_code == 200:
                        self.memo[d] = r.json(); return self.memo[d]
                    if r.status_code == 404:
                        break
                except Exception:
                    await asyncio.sleep(1)
        self.memo[d] = None
        return None


async def _pagina(br, url):
    ctx = await br.new_context(locale='pt-BR', user_agent=UA)
    try:
        p = await ctx.new_page()
        await p.goto(url, timeout=30000, wait_until='domcontentloaded')
        t = ''
        for espera in (2500, 3000, 4000):
            await p.wait_for_timeout(espera)
            t = await p.inner_text('body')
            if CNPJ_RE.search(t) or any(k in sa(t) for k in BLOQ):
                break
        links = await p.eval_on_selector_all('a[href^="http"]', 'els => els.map(e => e.href)')
        return t, links
    except Exception:
        return '', []
    finally:
        await ctx.close()


def site_parece_oficial(url, nome):
    m = re.match(r'https?://(?:www\.)?([^/:]+)', url or '')
    if not m or NAO_OFICIAIS.search(m.group(1)):
        return False
    rotulo = re.sub(r'\.(com|org|net|ong|edu|ind|art|coop)?(\.br)?$', '', m.group(1)).replace('-', '').replace('.', '')
    palavras = [w for w in limpa(nome) if len(w) >= 2]
    return bool(palavras) and (all(w in rotulo for w in palavras) or fuzz.ratio(''.join(palavras), rotulo) >= 88)


async def _do_site(api, nome, links, confiaveis=()):
    import httpx
    bases = [re.match(r'https?://[^/]+', u).group(0) for u in confiaveis if u and re.match(r'https?://', u) and not NAO_OFICIAIS.search(u)]
    bases += [re.match(r'https?://[^/]+', u).group(0) for u in links if site_parece_oficial(u, nome)][:2]
    caminhos = ('', '/contato', '/fale-conosco', '/sobre', '/quem-somos', '/politica-de-privacidade')
    for base in list(dict.fromkeys(bases))[:3]:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={'User-Agent': UA}) as c:
            paginas = await asyncio.gather(*[c.get(base + caminho) for caminho in caminhos], return_exceptions=True)
            for caminho, r in zip(caminhos, paginas):
                if isinstance(r, BaseException) or r.status_code != 200:
                    continue
                achados = []
                for x in dict.fromkeys(re.sub(r'\D', '', y) for y in CNPJ_RE.findall(re.sub(r'<[^>]+>', ' ', r.text[:600_000]))):
                    if dv_ok(x):
                        j = await api.dados(x)
                        if j and confere(nome, j):
                            achados.append(dict(forca=2, cnpj=x, j=j, fonte=f'site oficial {base}{caminho}'))
                if achados:
                    return achados
    return []


async def _online(br, api, nome, cidade, uf, site, ctx=None):
    tentativas, confirmados, links_vistos = [], {}, []

    async def consultar(fonte, tpl):
        espera = INTERVALO_BUSCADOR - (time.monotonic() - _ultimo_uso.get(fonte, 0))
        if espera > 0:
            await asyncio.sleep(espera)
        _ultimo_uso[fonte] = time.monotonic()
        try:
            return (fonte,) + tuple(await asyncio.wait_for(_pagina(br, tpl(f'CNPJ "{nome}"')), 50))
        except Exception:
            return fonte, '', []
    respostas = list(await asyncio.gather(*[consultar(f, t) for f, t in BUSCADORES[:2]]))   # os dois primeiros ao mesmo tempo
    for i in range(3):
        if i == 2:
            if confirmados:
                break
            respostas.append(await consultar(*BUSCADORES[2]))
        fonte, t, links = respostas[i]
        links_vistos += links
        if not t or (any(k in sa(t) for k in BLOQ) and not CNPJ_RE.search(t)):
            tentativas.append(f'{fonte}: sem resposta/bloqueado')
            if ctx:
                ctx.fonte(f'Buscador {fonte}', 'falhou', 'sem resposta ou bloqueado')
            continue
        if ctx:
            ctx.fonte(f'Buscador {fonte}', 'ok')
        nums = [d for d in dict.fromkeys(re.sub(r'\D', '', x) for x in CNPJ_RE.findall(t)) if dv_ok(d)][:8]
        n_ok = 0
        for d in nums:
            j = await api.dados(d)
            f = confere(nome, j) if j else 0
            if f:
                confirmados.setdefault(d[:8], dict(forca=f, cnpj=d, j=j, fonte=fonte)); n_ok += 1
        tentativas.append(f'{fonte}: {len(nums)} CNPJs na página, {n_ok} conferem')
    do_site = await _do_site(api, nome, links_vistos, [site] if site else [])
    if len({v['cnpj'][:8] for v in do_site}) == 1:
        v = do_site[0]; j = v['j']
        situ = (j.get('descricao_situacao_cadastral') or '').upper()
        return dict(status='🟢' if situ == 'ATIVA' else '🔴', cnpj=v['cnpj'], razao_social=j.get('razao_social'), nome_fantasia=j.get('nome_fantasia'),
                    municipio=j.get('municipio'), uf=j.get('uf'), fonte=v['fonte'], candidatos=[],
                    motivo='CNPJ publicado no site oficial' if situ == 'ATIVA' else f'situação cadastral {situ} (R07)')
    if not confirmados:
        return dict(status='🔴', cnpj=None, fonte=None, candidatos=[], motivo='Não foi possível validar automaticamente: ' + '; '.join(tentativas))
    fortes = {r: v for r, v in confirmados.items() if v['forca'] == 2}
    escolha = fortes or confirmados
    cands = [(v['cnpj'], v['j'].get('razao_social'), v['j'].get('municipio'), v['j'].get('uf')) for v in escolha.values()]
    criterio, desempate = ('nome confere' if fortes else 'nome contido no cadastro'), False
    if len(escolha) > 1 and (cidade or uf):
        no_local = {r: v for r, v in escolha.items() if _local(v['j'], cidade, uf)}
        if len(no_local) == 1:
            escolha, criterio, desempate = no_local, criterio + f' + única na UF da vaga entre {len(escolha)} homônimas (conferir)', True
    if len(escolha) > 1:
        return dict(status='🟡', cnpj=None, fonte=None, candidatos=cands, motivo=f'{len(escolha)} empresas diferentes com esse nome (homônimas)')
    v = next(iter(escolha.values())); j = v['j']
    situ = (j.get('descricao_situacao_cadastral') or '').upper()
    if situ != 'ATIVA':
        return dict(status='🔴', cnpj=v['cnpj'], razao_social=j.get('razao_social'), municipio=j.get('municipio'), uf=j.get('uf'),
                    fonte=v['fonte'], candidatos=cands, motivo=f'situação cadastral {situ or "?"} (R07)')
    return dict(status='🟢' if v['forca'] == 2 and not desempate else '🟡', cnpj=v['cnpj'], razao_social=j.get('razao_social'),
                nome_fantasia=j.get('nome_fantasia'), municipio=j.get('municipio'), uf=j.get('uf'), fonte=v['fonte'], candidatos=cands, motivo=criterio)


async def cnpj_do_empregador(br, api, nome, cidade=None, uf=None, site=None, ctx=None, cnpjs_texto=()):
    """Resolve o CNPJ do empregador (o CNPJ escrito na vaga, se houver; a base; online só quando precisa), com memória de 30 dias por nome/local."""
    do_texto = await cnpj_do_texto(api, nome, cnpjs_texto) if cnpjs_texto else None
    if do_texto:
        return conferir_local(do_texto, cidade, uf, nome)
    chave = f'{sa(nome)}|{sa(cidade)}|{sa(uf)}'
    with db.conectar() as c:
        row = c.execute('SELECT consultado_em, json FROM empresa_cnpj WHERE chave=?', (chave,)).fetchone()
    if row and (dt.datetime.now().astimezone() - dt.datetime.fromisoformat(row['consultado_em'])).days < 30:
        r = json.loads(row['json'])
        if r.get('status') == '🟡' and OUTRA_UF in (r.get('motivo') or '') and r.get('cnpj'):
            # dúvida guardada só por a sede ser em outro estado: conferida de novo com a regra atual (sem consultar nada na internet)
            r = conferir_homonimos(conferir_local(dict(r, status='🟢', motivo=r['motivo'].split('; CNPJ em')[0]), cidade, uf, nome), nome)
            if r.get('status') == '🟢':
                with db.conectar() as c:
                    c.execute('INSERT OR REPLACE INTO empresa_cnpj (chave, consultado_em, json) VALUES (?,?,?)', (chave, row['consultado_em'], json.dumps(r, ensure_ascii=False)))
        return r
    b = cnpj_pela_base(nome, cidade, uf)
    if b:
        r = conferir_local(b, cidade, uf, nome)
    else:
        r = conferir_homonimos(conferir_local(await _online(br, api, nome, cidade, uf, site, ctx), cidade, uf, nome), nome)
    with db.conectar() as c:
        c.execute('INSERT OR REPLACE INTO empresa_cnpj (chave, consultado_em, json) VALUES (?,?,?)', (chave, db.agora(), json.dumps(r, ensure_ascii=False)))
    return r
