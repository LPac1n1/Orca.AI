"""Lojas virtuais usadas na pesquisa de preços (CEP de referência do projeto) e os adaptadores de busca de cada uma.

- VTEX (Atacadão, Sam's Club, Oba, drogarias, Americanas, Livrarias Curitiba, Mambo, Giga...): API pública de catálogo (nome, marca, EAN, sku);
  estoque e preço REAIS para o CEP vêm da simulação de carrinho da própria loja (o catálogo sozinho engana: ex. Atacadão).
  Só vale o produto VENDIDO PELA PRÓPRIA LOJA: oferta de outro vendedor do marketplace é de outra empresa, com outro CNPJ.
- Tenda: dados da página (inclui o título completo que abre a descrição; o nome da busca vem cortado). O estoque é por FILIAL:
  a filial que atende o CEP vem da API pública de opções de entrega, e o produto só vale se tiver estoque nela.
- Carrefour, Kalunga, Lepok: página de busca renderizada; EAN lido na página do produto (Lepok no HTML; os outros renderizados).
- Gimba: HTML da busca. Afonso Ruotolo: loja Nuvemshop (busca + dados estruturados do produto).
Toda busca tem limite de tempo; falhas são contadas por loja (a tarefa avisa quando o resultado de uma loja fica incompleto)."""
import asyncio
import html as H
import json
import re
from urllib.parse import quote

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'

# setores: o que cada loja vende (para não procurar papelaria em hortifruti etc.)
LOJAS = {
    'atacadao':          dict(nome='Atacadão', plataforma='vtex', dominio='www.atacadao.com.br', setores={'alimentacao', 'limpeza', 'papelaria'}, carrinho=True),
    'samsclub':          dict(nome="Sam's Club", plataforma='vtex', dominio='www.samsclub.com.br', setores={'alimentacao', 'limpeza', 'papelaria'}, carrinho=True),
    'oba':               dict(nome='Oba Hortifruti', plataforma='vtex', dominio='www.obahortifruti.com.br', setores={'alimentacao', 'limpeza'}, carrinho=True),
    'drogariasp':        dict(nome='Drogaria São Paulo', plataforma='vtex', dominio='www.drogariasaopaulo.com.br', setores={'limpeza', 'papelaria'}, carrinho=True),
    'pacheco':           dict(nome='Drogarias Pacheco', plataforma='vtex', dominio='www.drogariaspacheco.com.br', setores={'limpeza', 'papelaria'}, carrinho=True),
    'americanas':        dict(nome='Americanas', plataforma='vtex', dominio='www.americanas.com.br', setores={'alimentacao', 'limpeza', 'papelaria'}, carrinho=True),
    'livrariascuritiba': dict(nome='Livrarias Curitiba', plataforma='vtex', dominio='www.livrariascuritiba.com.br', setores={'papelaria'}, carrinho=True),
    'tenda':             dict(nome='Tenda Atacado', plataforma='tenda', dominio='www.tendaatacado.com.br', setores={'alimentacao', 'limpeza', 'papelaria'}, carrinho=True),
    'carrefour':         dict(nome='Carrefour', plataforma='render', dominio='mercado.carrefour.com.br', setores={'alimentacao', 'limpeza', 'papelaria'}, carrinho=False,
                              busca=lambda q: f'https://mercado.carrefour.com.br/busca/{quote(q)}', link=r'mercado\.carrefour\.com\.br/produto/', ean='render',
                              descartada='pede verificação humana (CAPTCHA) com frequência'),
    # GPA (Pão de Açúcar e Extra Mercado): API pública de busca, EAN no detalhe do produto. O CEP diz se a loja ENTREGA no endereço; o preço
    # é o da loja padrão do site (loja_padrao), o MESMO que a página pública do produto mostra a quem abre o link sem informar endereço
    # (assim o PDF e o analista da SEJC veem o preço que está na grade).
    # As duas são da MESMA empresa (mesma raiz de CNPJ): nunca entram juntas no mesmo item (R09).
    'paodeacucar':       dict(nome='Pão de Açúcar', plataforma='gpa', banner='pa', dominio='www.paodeacucar.com', setores={'alimentacao', 'limpeza'}, loja_padrao=461,
                              carrinho=False, ean='gpa'),
    'extra':             dict(nome='Extra Mercado', plataforma='gpa', banner='ex', dominio='www.extramercado.com.br', setores={'alimentacao', 'limpeza'}, loja_padrao=483,
                              carrinho=False, ean='gpa'),
    'coop':              dict(nome='Coop Supermercado', plataforma='vtex', dominio='www.coopsupermercado.com.br', setores={'alimentacao', 'limpeza', 'papelaria'}, carrinho=True),
    # papelarias com catálogo aberto (VTEX), incluídas em 01/10/2026 depois que a Kalunga pediu CAPTCHA
    'papelex':           dict(nome='Papelex', plataforma='vtex', dominio='www.papelex.com.br', setores={'papelaria'}, carrinho=True),
    'bazarhorizonte':    dict(nome='Bazar Horizonte', plataforma='vtex', dominio='www.bazarhorizonte.com.br', setores={'papelaria'}, carrinho=True),
    'kalunga':           dict(nome='Kalunga', plataforma='render', dominio='www.kalunga.com.br', setores={'papelaria', 'limpeza', 'alimentacao'}, carrinho=False,
                              busca=lambda q: f'https://www.kalunga.com.br/busca/1?q={quote(q)}', link=r'kalunga\.com\.br/prod/', ean='render'),
    'lepok':             dict(nome='Lepok', plataforma='render', dominio='www.lepok.com.br', setores={'papelaria', 'limpeza'}, carrinho=False,
                              busca=lambda q: f'https://www.lepok.com.br/busca/{quote(q)}', link=r'lepok\.com\.br/produto/', ean='html'),
    'gimba':             dict(nome='Gimba', plataforma='gimba', dominio='www.gimba.com.br', setores={'papelaria', 'limpeza', 'alimentacao'}, carrinho=False),
    'afonsoruotolo':     dict(nome='Afonso Ruotolo', plataforma='nuvemshop', dominio='www.afonsoruotolo.com.br', setores={'papelaria'}, carrinho=False),
    # incluídas em 05/10/2026 (pedido da OSC: todas as lojas sem bloqueio possíveis). De 89 sites sondados, estas têm a busca aberta, entregam em
    # São Paulo, publicam o CNPJ no próprio site e abrem no navegador sem verificação humana. Ficaram de fora: as que não entregam em SP, as que
    # pedem verificação humana (Le Biscuit, Leitura, Camicado, Obramax, Loja do Mecânico) e as que não publicam o CNPJ no site (Grafitti Artes).
    'mambo':             dict(nome='Mambo', plataforma='vtex', dominio='www.mambo.com.br', setores={'alimentacao', 'limpeza'}, carrinho=True),
    'giga':              dict(nome='Giga Atacado', plataforma='vtex', dominio='www.giga.com.vc', setores={'alimentacao', 'limpeza', 'papelaria'}, carrinho=True),
    'casaevideo':        dict(nome='Casa & Video', plataforma='vtex', dominio='www.casaevideo.com.br', setores={'limpeza', 'papelaria'}, carrinho=True),
    'telhanorte':        dict(nome='Telhanorte', plataforma='vtex', dominio='www.telhanorte.com.br', setores={'limpeza'}, carrinho=True),
    'drogal':            dict(nome='Drogal', plataforma='vtex', dominio='www.drogal.com.br', setores={'limpeza', 'papelaria'}, carrinho=True),
    'paguemenos':        dict(nome='Farmácias Pague Menos', plataforma='vtex', dominio='www.paguemenos.com.br', setores={'limpeza'}, carrinho=True),
}

# CNPJ de cada loja: do rodapé do site ou de grade já aceita pela SEJC, conferido como ATIVO na base oficial da Receita (27/09/2026).
# O sistema reconfere a situação cadastral antes de usar (regra R07).
CNPJ_LOJAS = {
    'atacadao': ('75.315.333/0001-09', 'ATACADAO S.A.', 'base oficial da Receita'),
    'carrefour': ('45.543.915/0001-81', 'CARREFOUR COMERCIO E INDUSTRIA LTDA', 'base oficial da Receita'),
    'tenda': ('01.157.555/0011-86', 'TENDA ATACADO SA', 'base oficial da Receita'),
    'kalunga': ('43.283.811/0001-50', 'KALUNGA SA', 'base oficial da Receita'),
    'lepok': ('19.576.717/0001-04', 'LEPOK DISTRIBUICAO E LOGISTICA LTDA', 'base oficial da Receita'),
    'gimba': ('54.651.716/0011-50', 'SUPRICORP SUPRIMENTOS LTDA', 'base oficial da Receita'),
    'samsclub': ('00.063.960/0001-09', 'WMB SUPERMERCADOS DO BRASIL LTDA.', 'rodapé do site + base da Receita'),
    'oba': ('04.972.092/0001-22', 'GRUPO FARTURA DE HORTIFRUT S.A.', 'rodapé do site + base da Receita'),
    'drogariasp': ('61.412.110/0565-33', 'DROGARIA SAO PAULO S.A.', 'rodapé do site + base da Receita'),
    'pacheco': ('33.438.250/0187-08', 'DROGARIAS PACHECO S/A', 'rodapé do site + base da Receita'),
    'americanas': ('00.776.574/0006-60', 'AMERICANAS S.A.', 'rodapé do site + base da Receita'),
    'afonsoruotolo': ('60.413.249/0001-50', 'COSTA MEGA STORE LTDA', 'rodapé do site + base da Receita'),
    'livrariascuritiba': ('79.065.181/0001-94', 'DISTRIBUIDORA CURITIBA DE PAPEIS E LIVROS S/A', 'base da Receita (nome fantasia LIVRARIAS CURITIBA, matriz)'),
    'paodeacucar': ('47.508.411/0001-56', 'COMPANHIA BRASILEIRA DE DISTRIBUICAO', 'base da Receita (matriz do GPA; o site não publica o CNPJ no rodapé)'),
    'extra': ('47.508.411/0001-56', 'COMPANHIA BRASILEIRA DE DISTRIBUICAO', 'base da Receita (matriz do GPA; o site não publica o CNPJ no rodapé)'),
    'coop': ('57.508.426/0001-78', 'COOP - COOPERATIVA DE CONSUMO', 'rodapé do site + base da Receita'),
    'papelex': ('13.987.222/0001-91', 'MGX COMERCIO DE PAPEIS LTDA', 'rodapé do site + base da Receita (nome fantasia PAPELEX)'),
    'bazarhorizonte': ('44.913.721/0001-68', 'ARTESANA BAZAR E ARMARINHO LTDA', 'CNPJ do rodapé do site; razão social conforme a base da Receita (o rodapé diz "Bazar e Papelaria Horizonte Ltda")'),
    # 05/10/2026: CNPJ lido no rodapé de cada site e conferido como ATIVO na base da Receita
    'mambo': ('71.676.316/0001-46', 'SUPERMERCADOS MAMBO LTDA.', 'rodapé do site + base da Receita'),
    'giga': ('09.182.947/0001-35', 'CENCOSUD BRASIL ATACADO LTDA.', 'CNPJ do rodapé do site; razão social conforme a base da Receita (o rodapé diz "Cencosud Atacado Comercial Ltda.")'),
    'casaevideo': ('11.114.284/0001-63', 'CASA E VIDEO BRASIL S.A. - EM RECUPERACAO JUDICIAL', 'rodapé do site + base da Receita'),
    'telhanorte': ('03.840.986/0056-70', 'TELHANORTE DISTRIBUICAO LTDA', 'CNPJ do rodapé do site; razão social conforme a base da Receita'),
    'drogal': ('54.375.647/0066-72', 'DROGAL FARMACEUTICA LTDA', 'rodapé do site + base da Receita'),
    'paguemenos': ('06.626.253/0001-51', 'EMPREENDIMENTOS PAGUE MENOS S/A', 'rodapé do site + base da Receita'),
}


def raiz(loja):
    """Raiz do CNPJ (8 dígitos): lojas da mesma empresa não podem ser 2 das 3 pesquisas de um item (R09)."""
    c = re.sub(r'\D', '', (CNPJ_LOJAS.get(loja) or ('',))[0])
    return c[:8] or loja
EAN_RE = re.compile(r'"(?:gtin13|gtin|gtin14|gtin12|gtin8|ean|EAN|ean13|codigoBarras|barcode)"\s*:\s*"?(\d{8,14})"?')
EAN_TXT = re.compile(r'\b(?:EAN|GTIN|C[óo]d(?:igo)?\.? de barras)\W{0,20}(\d{8,14})\b', re.I)
# frases das telas de desafio/bloqueio (não basta a palavra "captcha": páginas normais carregam o reCAPTCHA de formulários)
BLOQUEIO_RE = re.compile(r'verificando se voc[eê] [eé] humano|verify you are human|checking (if the site connection is secure|your browser)|'
                         r'just a moment\.\.\.|attention required! \| cloudflare|acesso bloqueado|access denied|request blocked|'
                         r'complete (o|the) captcha|resolva o captcha|/cdn-cgi/challenge-platform', re.I)


class Bloqueada(RuntimeError):
    """A loja pediu verificação humana (CAPTCHA / desafio anti-robô). O sistema NÃO resolve CAPTCHA: a loja sai da tarefa."""


def conferir_bloqueio(texto, status=None):
    if status in (403, 429) or BLOQUEIO_RE.search((texto or '')[:4000]):
        raise Bloqueada('a loja pediu verificação humana (CAPTCHA/anti-robô)' if status != 429 else 'a loja limitou o número de acessos (429)')


JS_CARDS = """(pat)=>{const re=new RegExp(pat);const out=[];const vistos=new Set();
for(const a of document.querySelectorAll('a[href]')){ if(!re.test(a.href)||vistos.has(a.href)) continue;
  let el=a, txt=''; for(let i=0;i<6&&el;i++){ txt=el.innerText||''; if(/R\\$\\s?\\d/.test(txt)&&txt.length<600) break; el=el.parentElement; }
  const nome=(a.getAttribute('title')||a.innerText||'').trim().split('\\n')[0]; if(!nome||nome.length<6) continue;
  vistos.add(a.href); out.push([a.href,nome,txt]); } return out.slice(0,24);}"""


SERVICO_RE = re.compile(r'\b(sistemas?|software|licen[cç]as?|assinaturas?|consultoria|assessoria|servi[cç]os? de|presta[cç][aã]o de servi|'
                        r'loca[cç][aã]o|aluguel|hospedagem|transporte|frete|plataforma digital)\b', re.I)


def setor_da_rubrica(descricao):
    """Setor de produtos da rubrica (define as lojas). 'servico' = não é produto de loja (orçamento com fornecedores do serviço);
    None = material sem setor definido (procura em todas as lojas)."""
    d = (descricao or '').lower()
    if SERVICO_RE.search(d) and not re.search(r'\bmateria(l|is)\b', d):
        return 'servico'
    if re.search(r'aliment|lanche|refei|comida|cafe da manha|café da manhã|nutri', d):
        return 'alimentacao'
    if re.search(r'limpeza|higien|utens', d):
        return 'limpeza'
    if re.search(r'papel|escrit|pedag|expediente|consumo', d):
        return 'papelaria'
    return None


def lojas_para(setor, desligadas=(), bloqueadas=None):
    """Lojas do setor, sem as desligadas na configuração, as descartadas e as que pediram CAPTCHA nos últimos 30 dias."""
    if bloqueadas is None:
        try:
            from .. import db
            bloqueadas = db.lojas_bloqueadas()
        except Exception:
            bloqueadas = {}
    return [k for k, v in LOJAS.items() if k not in desligadas and not v.get('descartada') and k not in bloqueadas
            and (setor is None or setor in v['setores'])]


def ean_valido(e):
    e = e.zfill(13) if len(e) <= 13 else e
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(e[:-1][-12:].zfill(12)))
    return len(e) in (13, 14) and (10 - s % 10) % 10 == int(e[-1])


def preco_card(txt):
    """Preço à vista do card: ignora parcelas ('3x de R$'), preço antigo ('De R$') e preço por unidade de medida."""
    vals = []
    for m in re.finditer(r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', txt):
        antes = txt[max(0, m.start() - 12):m.start()].lower(); depois = txt[m.end():m.end() + 6].lower()
        if re.search(r'\d\s?x\s?(de)?\s*$', antes) or antes.strip().endswith('de') or depois.startswith('/'):
            continue
        vals.append(int(m.group(1).replace('.', '').replace(',', '')))
    return min(vals) if vals else None


# ------------------------------------------------------------------ adaptadores
def consulta(q):
    """Texto de busca sem os símbolos que as buscas das lojas recusam (ex.: marca "Malu (Malu Chips)" → HTTP 400 na VTEX)."""
    return re.sub(r'\s+', ' ', re.sub(r"[^\w\s\-.,/%']", ' ', q or '')).strip()


def _link_vtex(dom, p):
    """Endereço público do produto. Algumas lojas devolvem o link no endereço interno da plataforma (ex.: Casa & Video →
    casaevideonewio.vtexcommercestable.com.br), que abre uma página vazia: vale sempre o domínio da loja."""
    link = p.get('link') or ''
    if p.get('linkText') and not link.startswith(f'https://{dom}/'):
        return f'https://{dom}/{p["linkText"]}/p'
    return link or None


async def vtex(c, loja, q=None, ean=None):
    """Catálogo VTEX (nome, marca, EAN, sku, vendedor com estoque). Preço/estoque definitivos: simular()."""
    dom = LOJAS[loja]['dominio']
    fq = f'fq=alternateIds_Ean:{ean}' if ean else f'ft={quote(consulta(q))}&_from=0&_to=29'
    r = await c.get(f'https://{dom}/api/catalog_system/pub/products/search?{fq}')
    if r.status_code not in (200, 206):
        conferir_bloqueio(r.text, r.status_code)
        raise RuntimeError(f'HTTP {r.status_code}')
    j = r.json() if r.text[:1] == '[' else []
    out = []
    for p in j:
        for it in p.get('items', [])[:3]:
            if ean and (it.get('ean') or '').lstrip('0') != ean.lstrip('0'):
                continue
            # só o que a PRÓPRIA loja vende: em sites com marketplace (Americanas, Casa & Video, Pague Menos), a oferta de outro vendedor é de
            # outra empresa — o CNPJ da pesquisa não seria o dela. Na VTEX, a loja dona do site é o vendedor "1".
            proprios = [v for v in it.get('sellers') or [] if str(v.get('sellerId')) == str(LOJAS[loja].get('vendedor', '1'))]
            if not proprios:
                continue
            s = proprios[0]
            co = s['commertialOffer']
            out.append(dict(nome=p['productName'] if len(p['items']) == 1 else f"{p['productName']} {it.get('name', '')}".strip(), marca=p.get('brand'),
                            ean=it.get('ean'), sku=it['itemId'], seller=s['sellerId'], vendedor=s.get('sellerName'),
                            preco=round(co.get('Price', 0) * 100), disp=True, simular=True, url=_link_vtex(dom, p)))
            if not ean:
                break
    return out


async def simular(c, loja, ofertas, cep, memo):
    """Estoque e preço REAIS para o CEP (simulação de carrinho da loja, até 40 ofertas por chamada). memo: dicionário de cache."""
    dom = LOJAS[loja]['dominio']
    faltam = [x for x in ofertas if f"{loja}|{x['sku']}|{x['seller']}" not in memo]
    for i in range(0, len(faltam), 40):
        lote = faltam[i:i + 40]
        body = {'items': [{'id': x['sku'], 'quantity': 1, 'seller': x['seller']} for x in lote], 'postalCode': re.sub(r'\D', '', cep), 'country': 'BRA'}
        try:
            r = await c.post(f'https://{dom}/api/checkout/pub/orderForms/simulation', json=body)
            d = r.json() if r.status_code == 200 else {}
        except Exception:
            continue
        entrega = {li.get('itemIndex'): bool(li.get('slas')) for li in d.get('logisticsInfo') or []}
        for it in d.get('items') or []:
            k = it.get('requestIndex')
            if k is None or k >= len(lote):
                continue
            x = lote[k]
            memo[f"{loja}|{x['sku']}|{x['seller']}"] = [it.get('availability') == 'available' and entrega.get(k, False), it.get('sellingPrice')]
    for x in ofertas:
        v = memo.get(f"{loja}|{x['sku']}|{x['seller']}")
        x['disp'], x['preco'] = (bool(v[0]) and bool(v[1]), v[1]) if v else (False, None)
        x['simular'] = False


async def tenda_filial(c, cep):
    """Filial do Tenda que entrega no CEP (ex.: 03977-015 → 48, São Mateus). None se a consulta falhar."""
    try:
        r = await c.get(f'https://api.tendaatacado.com.br/api/public/store/shipping-options/{re.sub(r"[^0-9]", "", cep)}',
                        headers={'User-Agent': UA, 'Accept': 'application/json'})
        d = r.json() if r.status_code == 200 else {}
    except Exception:
        return None
    b = (d.get('delivery') or {}).get('branch') or next(iter((d.get('pickup') or {}).get('branches') or []), None)
    return str(b['id']) if b and b.get('id') is not None else None


def _tenda_disp(o, filial):
    if not o.get('isAvailable', True):
        return False
    inv = o.get('inventory')
    if filial and isinstance(inv, list) and inv:
        return any(str(x.get('branchId')) == filial and (x.get('totalAvailable') or 0) > 0 for x in inv)
    return True


async def tenda(c, q, filial=None):
    """Busca do Tenda lida direto do HTML (dados __NEXT_DATA__), sem abrir o navegador: ~2 s por busca, contra ~10 s no navegador
    (com várias páginas abertas ao mesmo tempo, as buscas no navegador estouravam o limite de tempo)."""
    r = await c.get(f'https://www.tendaatacado.com.br/busca?q={quote(q)}', headers={'User-Agent': UA, 'Accept': 'text/html', 'Accept-Language': 'pt-BR'})
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    nd = m.group(1) if m else None
    if not nd:
        conferir_bloqueio(re.sub(r'<[^>]+>', ' ', r.text), r.status_code)
        raise RuntimeError('página sem dados de produtos')
    out, vistos = [], set()

    def rec(o):
        if isinstance(o, dict):
            if 'name' in o and 'price' in o and 'token' in o and o.get('token') not in vistos:
                vistos.add(o['token'])
                desc = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', H.unescape(str(o.get('description') or '')))).strip()
                desc = re.sub(r'^[\W_]+', '', desc)  # marcadores no início ("• Hellmann's Tradicional 250g: ...")
                m = re.match(r'([^:.!?]{12,140}):', desc)
                titulo = m.group(1).strip() if m and not re.search(r'\b(desenvolvid|ideal|perfeit|garant)', m.group(1), re.I) else None
                out.append(dict(nome=o['name'], titulo=titulo, marca=o.get('brand'), ean=None, sku=o.get('sku'),
                                preco=round(float(o['price']) * 100) if o.get('price') else None, disp=_tenda_disp(o, filial), url=o.get('url')))
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec(json.loads(nd))
    return out


async def render(br, loja, q):
    cfg = LOJAS[loja]
    ctx = await br.new_context(locale='pt-BR', user_agent=UA, viewport={'width': 1366, 'height': 1000}); p = await ctx.new_page()
    try:
        r = await p.goto(cfg['busca'](q), timeout=45000, wait_until='domcontentloaded'); await p.wait_for_timeout(5000)
        cards = await p.evaluate(JS_CARDS, cfg['link'])
        if not cards:   # sem resultado OU bloqueio: um bloqueio nunca pode passar por "produto não existe"
            conferir_bloqueio(await p.inner_text('body'), r.status if r else None)
    finally:
        await ctx.close()
    return [dict(nome=n, marca=None, ean=None, preco=preco_card(t), url=h,
                 disp=preco_card(t) is not None and 'indisponível' not in t.lower() and 'esgotado' not in t.lower()) for h, n, t in cards]


async def gimba(c, q):
    r = await c.get('https://www.gimba.com.br/', params={'txt-busca': q, 'btn-buscar': 'Buscar'}, headers={'User-Agent': UA, 'Accept': 'text/html'})
    t = r.content.decode('utf-8', errors='replace')
    if 'DadosDoCard' not in t:
        conferir_bloqueio(t, r.status_code)
    out = []
    for b in re.split(r'<div class="DadosDoCard">', t)[1:]:
        nome = re.search(r'class="ChamaItem"[^>]*>([^<]+)<', b); link = re.search(r'href="([^"]+PID=\d+)"', b)
        txt = re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', b[:3000])))
        m = re.search(r'por apenas\s*R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', txt) or re.search(r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', txt)
        if nome and m:
            out.append(dict(nome=H.unescape(nome.group(1)).strip(), marca=None, ean=None, preco=int(m.group(1).replace('.', '').replace(',', '')),
                            disp='indispon' not in txt.lower() and 'esgotad' not in txt.lower(),
                            url=('https://www.gimba.com.br' + link.group(1)) if link and not link.group(1).startswith('http') else (link.group(1) if link else None)))
    return out


async def nuvemshop(c, loja, q, max_prod=14):
    dom = LOJAS[loja]['dominio']
    r = await c.get(f'https://{dom}/search/?q={quote(q)}', headers={'User-Agent': UA, 'Accept': 'text/html'})
    if r.status_code != 200:
        conferir_bloqueio(r.text, r.status_code)
    links = list(dict.fromkeys(re.findall(r'href="(https?://' + re.escape(dom) + r'/produtos/[^"#?]+)"', r.text)))[:max_prod]

    async def um(u):
        try:
            h = (await c.get(u, headers={'User-Agent': UA, 'Accept': 'text/html'})).text
        except Exception:
            return None
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S | re.I):
            try:
                d = json.loads(m.group(1).strip())
            except Exception:
                continue
            for x in (d if isinstance(d, list) else [d]):
                if isinstance(x, dict) and 'Product' in str(x.get('@type')):
                    of = x.get('offers') or {}
                    of = of[0] if isinstance(of, list) and of else of
                    preco = of.get('price') or of.get('lowPrice')
                    marca = x.get('brand', {}).get('name') if isinstance(x.get('brand'), dict) else x.get('brand')
                    return dict(nome=H.unescape(x.get('name') or ''), marca=marca, ean=x.get('gtin13') or x.get('gtin') or None,
                                preco=round(float(preco) * 100) if preco else None, disp='InStock' in str(of.get('availability')), url=u)
        return None
    return [x for x in await asyncio.gather(*[um(u) for u in links]) if x]


GPA_API = 'https://api.vendas.gpa.digital'
_GPA_LOJA = {}


def _gpa_cab(loja):
    dom = LOJAS[loja]['dominio']
    return {'User-Agent': UA, 'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/json',
            'Origin': f'https://{dom}', 'Referer': f'https://{dom}/'}


async def gpa_loja(c, loja, cep):
    """Loja física do GPA que atende o CEP (ex.: 03977-015 → 2271, Shopping Santo André). None se a consulta falhar."""
    chave = (loja, re.sub(r'\D', '', cep))
    if chave not in _GPA_LOJA:
        try:
            r = await c.get(f'{GPA_API}/{LOJAS[loja]["banner"]}/v2/delivery/ecom/{chave[1]}', headers=_gpa_cab(loja))
            tipos = ((r.json().get('content') or {}).get('deliveryTypes') or []) if r.status_code == 200 else []
            _GPA_LOJA[chave] = tipos[0]['storeid'] if tipos else None
        except Exception:
            return None
    return _GPA_LOJA[chave]


async def gpa(c, loja, q, loja_id):
    """Busca na API do GPA, na loja que atende o CEP: nome, marca, sku, preço e estoque. O EAN vem do detalhe (ean_da_pagina)."""
    corpo = {'terms': q, 'page': 1, 'sortBy': 'relevance', 'resultsPerPage': 24, 'allowRedirect': False, 'storeId': loja_id,
             'department': 'ecom', 'customerPlus': True, 'partner': 'fallback'}
    r = await c.post(f'{GPA_API}/{LOJAS[loja]["banner"]}/search/search', json=corpo, headers=_gpa_cab(loja))
    if r.status_code == 404 and 'not found' in r.text.lower():   # "Products not found": busca sem resultado, não é falha da loja
        return []
    if r.status_code != 200:
        conferir_bloqueio(r.text, r.status_code)
        raise RuntimeError(f'HTTP {r.status_code}')
    return [dict(nome=p['name'], marca=p.get('brand'), ean=None, sku=str(p.get('id')), preco=round(float(p['price']) * 100) if p.get('price') else None,
                 disp=bool(p.get('stock')), url=p.get('urlDetails'), loja_gpa=loja_id) for p in r.json().get('products') or []]


async def ean_da_pagina(br, c, loja, url):
    """EAN publicado na página do produto (Lepok no HTML; Kalunga e Carrefour só na página renderizada). None se não houver."""
    modo = LOJAS[loja].get('ean')
    if not modo or not url:
        return None
    if modo == 'gpa':   # detalhe do produto na API (sem abrir a página)
        m = re.search(r'/produto/(\d+)', url)
        if not m:
            return None
        lj = next((v for (l, _), v in _GPA_LOJA.items() if l == loja and v), None)
        r = await c.get(f'{GPA_API}/{LOJAS[loja]["banner"]}/v4/products/ecom/{m.group(1)}' + (f'?storeId={lj}' if lj else ''), headers=_gpa_cab(loja))
        achados = [x for x in EAN_RE.findall(r.text) if ean_valido(x)] if r.status_code == 200 else []
        return max(set(achados), key=achados.count) if achados else None
    if modo == 'html':
        h = (await c.get(url, headers={'User-Agent': UA, 'Accept': 'text/html'})).text
    else:
        ctx = await br.new_context(locale='pt-BR', user_agent=UA); p = await ctx.new_page()
        try:
            await p.goto(url, timeout=45000, wait_until='domcontentloaded'); await p.wait_for_timeout(3500)
            h = await p.content() + ' ' + await p.inner_text('body')
        finally:
            await ctx.close()
    achados = [x for x in EAN_RE.findall(h) + EAN_TXT.findall(h) if ean_valido(x)]
    if not achados:   # página bloqueada não pode virar "produto sem EAN" no cache
        conferir_bloqueio(re.sub(r'<[^>]+>', ' ', h))
    return achados[0] if achados else None
