"""Comprovantes das pesquisas de preço (evidências guardadas com SHA-256 na pasta do projeto).

- Lojas VTEX (Atacadão, Sam's, Oba, drogarias, Americanas, Livrarias Curitiba): CARRINHO REAL na loja, com os itens que ela orça e
  as mesmas quantidades do plano, no CEP do projeto; o PDF é a página do carrinho da própria loja (formato aceito pela SEJC).
  Algumas lojas não juntam no mesmo carrinho produtos que saem de centros de distribuição diferentes (Atacadão:
  "maxNumberOfSellersReached"): o sistema divide em mais de um carrinho. Item indisponível mesmo sozinho = sem comprovante.
- Tenda: carrinho real pelo navegador (CEP no campo lateral, produto adicionado pelo card da busca, quantidade digitada no carrinho).
- Demais lojas: PDF da PÁGINA DO PRODUTO, com faixa de identificação (pesquisa de preço, item, quantidade, CEP, data/hora, endereço).
  A SEJC aceita orçamento por página de produto.
Todo comprovante é CONFERIDO antes de ser aceito: página de erro da loja, produto indisponível ou preço que não aparece na página
= nova tentativa (até 3); se continuar, o comprovante volta com o problema descrito (e o sistema tenta outra loja com o mesmo produto).
O frete nunca entra no plano (R14): vale o subtotal dos itens. Não se interage com avisos de cookies."""
import asyncio
import datetime as dt
import re
import unicodedata
from urllib.parse import quote

from .lojas import LOJAS, UA, BLOQUEIO_RE

# Janelas sobrepostas (aviso de cookies, propaganda, chat, "informe seu CEP") escondem o item e o preço no PDF. Antes da captura elas são
# OCULTADAS (display:none) — nada é clicado: nem "aceitar", nem "recusar". Não se oculta o que contém o preço do item nem o cabeçalho da loja.
LIMPAR = r"""(manter)=>{const vw=innerWidth,vh=innerHeight,fora=[];
const DIALOGO='[role=dialog],[aria-modal=true],dialog,[class*=modal i],[class*=popup i],[class*=pop-up i],[class*=overlay i],[class*=backdrop i],'+
 '[id*=modal i],[id*=popup i],[class*=cookie i],[id*=cookie i],[class*=consent i],[id*=consent i],[id*=onetrust i],[class*=lgpd i],[class*=newsletter i],'+
 '[class*=ShippingModal],[class*=chat i],[id*=chat i],[class*=whatsapp i]';
const COOKIE=/cookies?|lgpd|pol[ií]tica de privacidade/i, BOTAO=/aceit|concord|entendi|prosseguir|gerenciar|saiba mais|fechar|\bok\b/i;
const ocultar=(el)=>{el.style.setProperty('display','none','important');
  // componente que força a própria exibição (regra interna :host{display:block!important} vence a de fora): sai da página antes do PDF
  if(getComputedStyle(el).display!=='none')el.remove();
  fora.push((el.className||el.tagName).toString().slice(0,40));};
for(const el of document.querySelectorAll('body *')){
  if(el.id==='faixa-orcamento'||el.closest('#faixa-orcamento'))continue;
  const cs=getComputedStyle(el); if(cs.display==='none'||cs.visibility==='hidden')continue;
  const pos=cs.position, fixo=pos==='fixed', dialogo=el.matches(DIALOGO);
  const posto=fixo||pos==='absolute'||pos==='sticky';
  if(!posto&&!dialogo)continue;
  const r=el.getBoundingClientRect(); if(r.width<2||r.height<2)continue;
  const txt=el.innerText||'';
  // aviso de cookies fora da posição fixa: bloco curto que fala de cookies e tem botão (aceitar, gerenciar, fechar)
  if(!fixo&&txt.length<1500&&r.height<vh*0.7&&COOKIE.test(txt)&&(posto||dialogo)&&[...el.querySelectorAll('button,a,[role=button]')].some(b=>BOTAO.test(b.innerText||''))){ocultar(el);continue;}
  // balão "informe seu CEP" preso ao cabeçalho, por cima do nome do produto (Casa & Video, 05/10/2026): bloco curto, posto por cima da
  // página, com o campo do CEP e sem o preço do item
  if(posto&&pos!=='sticky'&&txt.length<300&&r.width<vw*0.6&&/informe (o )?seu cep|digite (o )?seu cep/i.test(txt)&&el.querySelector('input')
     &&!(manter&&manter.some(m=>m&&txt.includes(m)))){ocultar(el);continue;}
  // janela ou véu por cima do conteúdo em posição absoluta: tem z-index alto e é uma janela (modal, popup) ou cobre a tela quase sem texto
  const z=parseInt(cs.zIndex)||0;
  const sobre=pos==='absolute'&&z>=100&&(dialogo||(r.width>=vw*0.9&&r.height>=vh*0.9&&txt.trim().length<200));
  if(!fixo&&!(dialogo&&pos==='sticky')&&!sobre)continue;
  if(manter&&manter.some(m=>m&&txt.includes(m))&&!dialogo)continue;        // bloco com o preço do item: fica
  if(r.top<=8&&r.height<vh*0.22&&!dialogo)continue;                           // cabeçalho da loja (logo, busca): fica
  ocultar(el);
}
// Janela montada dentro de um componente fechado (shadow DOM), presa a um elemento de tamanho zero (ex.: o pop-up de promoção das Livrarias
// Curitiba, 03/10/2026): o laço acima não a enxerga. Aqui vale o que está PINTADO por cima da página: se o elemento do topo num ponto da
// tela não ocupa aquele ponto (o que aparece ali é o conteúdo interno dele, posto em outro lugar), ele é o suporte de uma janela sobreposta.
for(let volta=0;volta<4;volta++){let mudou=false;
  for(let i=1;i<=5;i++)for(let j=1;j<=5;j++){const x=vw*i/6,y=vh*j/6;
    for(const el of document.elementsFromPoint(x,y)){
      if(el===document.body||el===document.documentElement)break;
      if(el.id==='faixa-orcamento'||el.closest('#faixa-orcamento'))continue;
      const r=el.getBoundingClientRect();
      // só o suporte de uma janela: tamanho zero ou componente com conteúdo interno (um enfeite ::before/::after fora da caixa não conta),
      // e nunca o que contém o preço do item
      const ce=getComputedStyle(el), alto=(ce.position==='fixed'||ce.position==='absolute')&&(parseInt(ce.zIndex)||0)>=1000;
      const suporte=((alto&&(r.width<2||r.height<2))||!!el.shadowRoot)&&(x<r.left-1||x>r.right+1||y<r.top-1||y>r.bottom+1);
      if(suporte&&!(manter&&manter.some(m=>m&&(el.innerText||'').includes(m)))){ocultar(el);mudou=true;}
      break;
    }}
  if(!mudou)break;}
for(const e of [document.documentElement,document.body]){e.style.setProperty('overflow','visible','important');e.style.removeProperty('position');}
[...document.body.classList].forEach(c=>{if(/modal|popup|no-?scroll|overflow|lock|fixed/i.test(c))document.body.classList.remove(c)});
return fora;}"""

FAIXA = ("(t)=>{const d=document.createElement('div');d.id='faixa-orcamento';d.style='position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#fff8c4;"
         "font:12px monospace;padding:5px';d.textContent=t;document.body.prepend(d)}")
ERRO_PAGINA = re.compile(r'\boops\b|problema inesperado|p[aá]gina n[aã]o (foi )?encontrada|page not found|\b404\b|access denied|acesso negado|'
                         r'erro interno|service unavailable|temporariamente indispon', re.I)
INDISPONIVEL = re.compile(r'produto indispon[ií]vel|produtos indispon[ií]veis|fora de estoque|esgotado|avise-me quando chegar', re.I)
TENTATIVAS = 3
BLOQUEIO = 'BLOQUEIO: a loja pediu verificação humana (CAPTCHA/anti-robô); o sistema não resolve CAPTCHA'


async def limpar(p, manter=()):
    """Oculta as janelas sobrepostas antes do PDF (ver LIMPAR). Devolve o que foi ocultado (para conferência)."""
    try:
        return await p.evaluate(LIMPAR, list(manter))
    except Exception:
        return []


async def preparar_pdf(p, manter, faixa):
    """Antes do PDF: oculta as janelas sobrepostas, põe a faixa de identificação e oculta de novo o que apareceu com atraso (propaganda
    que abre alguns instantes depois da página)."""
    await limpar(p, manter)
    await p.evaluate(FAIXA, faixa)
    await p.wait_for_timeout(900)
    await limpar(p, manter)


def _agora():
    return dt.datetime.now().astimezone().isoformat(timespec='seconds')


def _sa(t):
    return ''.join(ch for ch in unicodedata.normalize('NFD', t or '') if unicodedata.category(ch) != 'Mn').lower()


def reais(centavos):
    """1859 → '18,59'; 123456 → '1.234,56' (como as lojas escrevem)."""
    r, c = divmod(int(centavos), 100)
    return f'{r:,}'.replace(',', '.') + f',{c:02d}'


def preco_na_pagina(texto, centavos):
    t = (texto or '').replace('\xa0', ' ')
    v = reais(centavos)
    return re.search(r'(?<![\d.,])' + re.escape(v) + r'(?![\d])', t) is not None


def conferir_pagina(texto, precos=(), indisponivel_conta=True):
    """None se a página serve de comprovante; senão, o problema encontrado."""
    t = (texto or '').replace('\xa0', ' ')
    if BLOQUEIO_RE.search(t[:4000]):
        return BLOQUEIO
    faltam = [p for p in precos if p and not preco_na_pagina(t, p)]
    if ERRO_PAGINA.search(t[:6000]) and (faltam or not precos):
        return 'a loja mostrou uma página de erro'
    if len(t.strip()) < 300:
        return 'página vazia'
    if indisponivel_conta and INDISPONIVEL.search(t):
        return 'a página diz que o produto está indisponível'
    if faltam:
        return 'o preço da pesquisa (' + ', '.join('R$ ' + reais(p) for p in faltam) + ') não aparece na página'
    return None


async def _ir(p, url, espera):
    await asyncio.wait_for(p.goto(url, timeout=60000, wait_until='domcontentloaded'), 70)
    await p.wait_for_timeout(espera)


# ------------------------------------------------------------------ VTEX
async def _endereco_vtex(c, dom, cep):
    """Endereço completo do CEP pelo serviço da própria loja (sem cidade/UF o carrinho não calcula a entrega)."""
    num = re.sub(r'\D', '', cep)
    try:
        e = (await c.get(f'https://{dom}/api/checkout/pub/postal-code/BRA/{num}')).json()
    except Exception:
        e = {}
    end = {k: e.get(k) for k in ('postalCode', 'city', 'state', 'street', 'neighborhood', 'geoCoordinates') if e.get(k)}
    end.update(postalCode=num, country='BRA', addressType='residential')
    return end


async def _um_carrinho_vtex(dom, itens, endereco):
    """Carrinho novo (sessão nova, sem cookies de outro carrinho). Devolve (orderFormId, orderForm)."""
    import httpx
    async with httpx.AsyncClient(headers={'User-Agent': UA, 'Accept': 'application/json'}, timeout=30, follow_redirects=True) as c:
        ofid = (await c.get(f'https://{dom}/api/checkout/pub/orderForm')).json()['orderFormId']
        await c.post(f'https://{dom}/api/checkout/pub/orderForm/{ofid}/items',
                     json={'orderItems': [{'id': i['sku'], 'quantity': i['qtd'], 'seller': i['seller']} for i in itens]})
        await c.post(f'https://{dom}/api/checkout/pub/orderForm/{ofid}/attachments/shippingData',
                     json={'address': endereco, 'clearAddressIfPostalCodeNotFound': False})
        return ofid, (await c.get(f'https://{dom}/api/checkout/pub/orderForm/{ofid}')).json()


async def _pdf_carrinho_vtex(br, loja, ofid, cep, precos):
    dom = LOJAS[loja]['dominio']
    url = f'https://{dom}/checkout/#/cart'
    problema = None
    for k in range(TENTATIVAS):
        ctx = await br.new_context(locale='pt-BR', user_agent=UA, viewport={'width': 1280, 'height': 1100})
        try:
            await ctx.add_cookies([{'name': 'checkout.vtex.com', 'value': f'__ofid={ofid}', 'domain': '.' + dom.replace('www.', ''), 'path': '/'}])
            p = await ctx.new_page()
            await _ir(p, url, 9000 + 4000 * k)
            problema = conferir_pagina(await p.inner_text('body'), precos)
            if problema == BLOQUEIO:
                return None, _agora(), url, problema
            if problema is None or k == TENTATIVAS - 1:
                quando = _agora()
                await preparar_pdf(p, [reais(x) for x in precos if x], f'SIMULAÇÃO DE COMPRA | {LOJAS[loja]["nome"]} | CEP {cep} | {quando} | {url}')
                return await p.pdf(print_background=True), quando, url, problema
        except Exception as e:
            problema = f'{type(e).__name__} ao abrir o carrinho'
        finally:
            await ctx.close()
    return None, _agora(), url, problema


async def carrinhos_vtex(br, loja, itens, cep, max_carrinhos=6):
    """itens: [dict(sku, seller, qtd, nome)]. Monta 1 ou mais carrinhos na loja (divide quando ela não junta os itens) e captura a
    página de cada um. Devolve (carrinhos=[dict(pdf, skus, precos={sku: unitário}, subtotal, capturado_em, url, problema)],
    indisponiveis={sku: motivo})."""
    import httpx
    dom = LOJAS[loja]['dominio']
    async with httpx.AsyncClient(headers={'User-Agent': UA, 'Accept': 'application/json'}, timeout=30, follow_redirects=True) as c:
        endereco = await _endereco_vtex(c, dom, cep)
    pendentes, prontos, indisp = [list(itens)], [], {}
    while pendentes and len(prontos) + len(pendentes) <= max_carrinhos + 2:
        g = pendentes.pop(0)
        ofid, of = await _um_carrinho_vtex(dom, g, endereco)
        st = {x['id']: x.get('availability') for x in of.get('items', [])}
        qt = {x['id']: x.get('quantity') for x in of.get('items', [])}
        ok = lambda i: st.get(i['sku']) == 'available' and qt.get(i['sku']) == i['qtd']
        ruins = [i for i in g if not ok(i)]
        bons = [i for i in g if ok(i)]
        if not ruins:
            prontos.append((ofid, g, of))
        elif len(g) == 1:
            i = g[0]
            indisp[i['sku']] = (f'a loja aceita no máximo {qt[i["sku"]]} unidade(s) (plano: {i["qtd"]})'
                                if st.get(i['sku']) == 'available' and qt.get(i['sku']) else st.get(i['sku']) or 'não entrou no carrinho')
        elif bons:   # refaz com os que ficaram disponíveis; os outros tentam juntos em outro carrinho
            pendentes.insert(0, bons); pendentes.append(ruins)
        else:
            pendentes.extend([i] for i in ruins)
    for g in pendentes:
        for i in g:
            indisp.setdefault(i['sku'], 'itens demais em carrinhos separados')
    out = []
    for ofid, g, of in prontos[:max_carrinhos]:
        precos = {x['id']: x.get('sellingPrice') or x.get('price') for x in of.get('items', [])}
        qtds = {x['id']: x.get('quantity') for x in of.get('items', [])}
        errado = [i['nome'] for i in g if qtds.get(i['sku']) != i['qtd']]
        pdf, quando, url, problema = await _pdf_carrinho_vtex(br, loja, ofid, cep, [precos[i['sku']] for i in g if precos.get(i['sku'])])
        if errado:
            problema = 'quantidade diferente do plano no carrinho: ' + ', '.join(errado)
        out.append(dict(pdf=pdf, skus=[i['sku'] for i in g], precos=precos, subtotal=sum((precos.get(i['sku']) or 0) * i['qtd'] for i in g),
                        capturado_em=quando, url=url, problema=problema))
    return out, indisp


# ------------------------------------------------------------------ Tenda
TENDA = 'https://www.tendaatacado.com.br'
JS_TENDA_COMPRAR = """(tk)=>{for(const a of document.querySelectorAll('a[href*="/produto/"]')){
  if(!(a.getAttribute('href')||'').replace(/\\/$/,'').endsWith('/'+tk))continue;
  let c=a;for(let i=0;i<8&&c;i++){c=c.parentElement;if(c&&c.querySelector('button[id^=buttonbuy]'))break;}
  const b=c&&c.querySelector('button[id^=buttonbuy]');if(b&&!b.disabled){b.click();return true}}return false}"""
JS_TENDA_LINHAS = """()=>[...document.querySelectorAll('.cart-card-content')].map(c=>{const i=c.querySelector('input.input-qtd');
  const im=c.querySelector('img');return [im?im.getAttribute('alt'):'', i?i.value:null, (c.innerText||'').replace(/\\s+/g,' ')]})"""


def _token(url):
    return (url or '').rstrip('/').split('/')[-1]


async def _tenda_cep(p, cep):
    x = p.locator('.ShippingModalContainer button, .ShippingModalContainer [class*=close]').first
    if await x.count():
        await x.dispatch_event('click'); await p.wait_for_timeout(1000)
    await p.locator('input[placeholder="00000-000"]').first.fill(cep, timeout=15000)
    await p.get_by_role('button', name=re.compile('^Enviar$', re.I)).first.dispatch_event('click')
    await p.wait_for_timeout(6000)
    return re.sub(r'\D', '', cep)[:5] in re.sub(r'\D', '', await p.inner_text('body'))


def preco_unitario_tenda(texto_linha, qtd):
    """Preço unitário que o carrinho cobra: subtotal da linha ÷ quantidade (o preço de atacado a partir de N unidades aparece
    depois do preço cheio riscado: 'R$ 18,59 un R$ 16,59 un _ 3 + R$ 49,77' → 1659)."""
    vs = [round(float(v.replace('.', '').replace(',', '.')) * 100) for v in re.findall(r'R\$\s?([\d.]+,\d{2})', texto_linha or '')]
    if not vs:
        return None
    sub = vs[-1]
    if qtd and sub % qtd == 0 and sub // qtd in vs:
        return sub // qtd
    un = [v for v in vs[:-1] if v * qtd == sub]
    return un[-1] if un else (vs[0] if qtd == 1 else None)


def _linha_tenda(linhas, nome, unico=False):
    if unico and len(linhas) == 1:   # carrinho de um item só: a única linha é o produto (o carrinho pode abreviar o nome)
        return linhas[0]
    alvo = _sa(nome)
    return next((l for l in linhas if _sa(l[0]) == alvo), None) or next((l for l in linhas if _sa(l[0]).startswith(alvo) or alvo.startswith(_sa(l[0]) or '#')), None)


async def carrinho_tenda(br, itens, cep):
    """itens: [dict(nome, url, qtd, preco)]. Devolve (pdf, dict(precos={url: unitário}, faltando={url: motivo}, subtotal, capturado_em, url, problema))."""
    ctx = await br.new_context(locale='pt-BR', user_agent=UA, viewport={'width': 1280, 'height': 1100})
    faltando = {}
    try:
        p = await ctx.new_page()
        await _ir(p, f'{TENDA}/busca?q={quote(itens[0]["nome"])}', 6000)
        if not await _tenda_cep(p, cep):
            raise RuntimeError('o site não aceitou o CEP')
        for it in itens:
            ok = False
            for k in range(2):
                await _ir(p, f'{TENDA}/busca?q={quote(it["nome"])}', 5000 + 3000 * k)
                if await p.evaluate(JS_TENDA_COMPRAR, _token(it['url'])):
                    ok = True; await p.wait_for_timeout(3000); break
            if not ok:
                faltando[it['url']] = 'o produto não pôde ser adicionado (indisponível no CEP ou fora da busca)'
        await _ir(p, f'{TENDA}/carrinho', 7000)
        for it in itens:
            if it['url'] in faltando or it['qtd'] == 1:
                continue
            for tent in range(3):   # o campo às vezes não aceita a quantidade na 1ª vez: confere e digita de novo
                linhas = await p.evaluate(JS_TENDA_LINHAS)
                l = _linha_tenda(linhas, it['nome'], len(itens) == 1)
                if not l:
                    faltando[it['url']] = 'o produto não apareceu no carrinho'; break
                if str(l[1]) == str(it['qtd']):
                    break
                campo = p.locator('.cart-card-content').nth(linhas.index(l)).locator('input.input-qtd')
                await campo.click(); await campo.press('Control+A'); await campo.type(str(it['qtd']), delay=80); await campo.press('Tab')
                await p.wait_for_timeout(3500 + 2000 * tent)
        await p.reload(wait_until='domcontentloaded'); await p.wait_for_timeout(7000)
        linhas = await p.evaluate(JS_TENDA_LINHAS)
        precos = {}
        for it in itens:
            if it['url'] in faltando:
                continue
            l = _linha_tenda(linhas, it['nome'], len(itens) == 1)
            if not l:
                faltando[it['url']] = 'o produto não apareceu no carrinho'; continue
            if str(l[1]) != str(it['qtd']):
                # ficou em 1 = o site não aceitou a digitação (falha passageira), não é limite de compra: a quantidade do plano não muda
                faltando[it['url']] = (f'a quantidade não pôde ser alterada no carrinho (continuou 1; plano: {it["qtd"]})' if str(l[1]) == '1'
                                       else f'a quantidade no carrinho ficou {l[1]} (plano: {it["qtd"]})'); continue
            u = preco_unitario_tenda(l[2], it['qtd'])
            if u:
                precos[it['url']] = u
        texto = await p.inner_text('body')
        problema = conferir_pagina(texto, list(precos.values()), indisponivel_conta=False)
        quando = _agora()
        await preparar_pdf(p, [reais(v) for v in precos.values()], f'SIMULAÇÃO DE COMPRA | Tenda Atacado | CEP {cep} | {quando} | {p.url}')
        pdf = await p.pdf(print_background=True)
        sub = sum(precos[it['url']] * it['qtd'] for it in itens if it['url'] in precos)
        return pdf, dict(precos=precos, faltando=faltando, subtotal=sub, capturado_em=quando, url=p.url, problema=problema)
    finally:
        await ctx.close()


# ------------------------------------------------------------------ página qualquer (preços de sistemas, serviços)
ROLAR = """async () => { const passo = Math.max(400, innerHeight * 0.8);
  for (let y = 0; y < document.documentElement.scrollHeight && y < 40000; y += passo) { scrollTo(0, y); await new Promise(r => setTimeout(r, 300)); }
  scrollTo(0, 0); }"""
# Texto da página com ✓/✗ no lugar dos ícones das tabelas de planos ("incluído" / "não incluído"); nada fica alterado na página.
TEXTO_MARCAS = """() => { const postos = [], donos = [];
  for (const e of document.querySelectorAll('[aria-label], [class]')) {
    if (e.children.length > 3 || (e.innerText || '').trim() || donos.some(d => d.contains(e))) continue;
    const a = (e.getAttribute('aria-label') || '').trim().toLowerCase();
    const c = ' ' + (typeof e.className === 'string' ? e.className : '').toLowerCase() + ' ';
    let m = null;
    if (/^(n[aã]o |sem |indispon)/.test(a) || / (no|nao|cross|times|deny|unavailable) /.test(c)) m = '✗';
    else if (/^(inclu|sim$|dispon|yes$)/.test(a) || / (yes|sim|check|checked|included) /.test(c)) m = '✓';
    if (!m) continue;
    const s = document.createElement('span'); s.textContent = m; e.appendChild(s); postos.push(s); donos.push(e);
  }
  const t = document.body ? document.body.innerText : '';
  postos.forEach(s => s.remove());
  return t; }"""


async def texto_completo(p):
    """Texto da página e dos quadros (iframes) dela, com ✓/✗ nas tabelas de planos."""
    partes = []
    for f in [p.main_frame] + sorted((f for f in p.frames if f != p.main_frame), key=lambda f: f.url):   # ordem estável: o mesmo texto a cada leitura
        try:
            t = await asyncio.wait_for(f.evaluate(TEXTO_MARCAS), 15)
        except Exception:
            t = ''
        if t and t.strip():
            partes.append(t)
    return '\n'.join(partes)


async def pagina(br, url, faixa, preco=None, completa=False):
    """PDF de uma página conferida (erro, bloqueio, preço ausente → nova tentativa). Devolve (pdf, dict(capturado_em, problema, texto)).
    completa: rola a página até o fim antes (conteúdo que só carrega ao rolar) e lê também o texto dos quadros (tabelas de planos)."""
    problema, texto = None, ''
    for k in range(TENTATIVAS):
        ctx = await br.new_context(locale='pt-BR', user_agent=UA, viewport={'width': 1280, 'height': 1100})
        try:
            p = await ctx.new_page()
            await _ir(p, url, 5000 + 3000 * k)
            if completa:
                await asyncio.wait_for(p.evaluate(ROLAR), 60)
                await p.wait_for_timeout(3000 + 2000 * k)
                texto = await texto_completo(p)
            else:
                texto = await p.inner_text('body')
            problema = conferir_pagina(texto, [preco] if preco else [], indisponivel_conta=False)
            if problema == BLOQUEIO:
                return None, dict(capturado_em=_agora(), problema=problema, texto=texto)
            if problema is None or k == TENTATIVAS - 1:
                quando = _agora()
                await preparar_pdf(p, [reais(preco)] if preco else [], f'{faixa} | {quando} | {url}')
                return await p.pdf(print_background=True, page_ranges='1-8' if completa else '1-3'), dict(capturado_em=quando, problema=problema, texto=texto)
        except Exception as e:
            problema = f'{type(e).__name__} ao abrir a página'
        finally:
            await ctx.close()
    return None, dict(capturado_em=_agora(), problema=problema, texto=texto)


# ------------------------------------------------------------------ página do produto
def preco_principal_gpa(texto):
    """Preço do produto na página do Pão de Açúcar/Extra: o valor logo depois do código do produto ('Cód.: 4426370  R$ 6,79')."""
    m = re.search(r'C[oó]d\.?:\s*\d+\s*R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', texto or '')
    return int(m.group(1).replace('.', '').replace(',', '')) if m else None


async def pagina_produto(br, loja, url, rotulo, cep, preco=None):
    """PDF da página do produto, conferido (erro da loja, indisponível, preço ausente → nova tentativa). info['problema'] = None se ok.
    info['preco_pagina']: preço que a página mostra, quando é diferente do pesquisado (Pão de Açúcar/Extra): é o que vale."""
    problema, preco_pagina = None, None
    for k in range(TENTATIVAS):
        ctx = await br.new_context(locale='pt-BR', user_agent=UA, viewport={'width': 1280, 'height': 1100})
        try:
            p = await ctx.new_page()
            if loja == 'tenda':   # preço e estoque do Tenda dependem do CEP: informa antes de abrir o produto
                await _ir(p, f'{TENDA}/busca?q={quote(_token(url).replace("-", " "))}', 6000)
                if not await _tenda_cep(p, cep):   # sem o CEP a página mostra o preço BORRADO: não serve de comprovante
                    raise RuntimeError('o site do Tenda não aceitou o CEP')
            elif k or loja == 'carrefour':   # o Carrefour bloqueia (403 → "Oops!") a 1ª visita sem cookies: passa pela página inicial antes
                await _ir(p, f'https://{LOJAS[loja]["dominio"]}/', 4000)
            await _ir(p, url, 5000 + 4000 * k)
            texto = await p.inner_text('body')
            if LOJAS[loja]['plataforma'] == 'gpa':   # vale o preço que a PÁGINA mostra (é o que o PDF comprova); a API pode trazer outro
                na_pagina = preco_principal_gpa(texto)
                if na_pagina and preco and na_pagina != preco and 0.7 * preco <= na_pagina <= 1.3 * preco:
                    preco_pagina = preco = na_pagina
            problema = conferir_pagina(texto, [preco] if preco else [])
            if problema == BLOQUEIO:   # não insiste: mais acessos só agravam o bloqueio
                return None, dict(capturado_em=_agora(), url=url, problema=problema)
            if problema == 'página vazia':   # a loja ainda está montando a página: espera mais antes de recarregar
                await p.wait_for_timeout(8000)
                problema = conferir_pagina(await p.inner_text('body'), [preco] if preco else [])
            if problema:   # recarregar na mesma sessão costuma resolver erro passageiro da loja
                await p.reload(wait_until='domcontentloaded'); await p.wait_for_timeout(7000 + 4000 * k)
                problema = conferir_pagina(await p.inner_text('body'), [preco] if preco else [])
                if problema == BLOQUEIO:
                    return None, dict(capturado_em=_agora(), url=url, problema=problema)
            if problema is None or k == TENTATIVAS - 1:
                quando = _agora()
                await preparar_pdf(p, [reais(preco)] if preco else [], f'PESQUISA DE PREÇO | {LOJAS[loja]["nome"]} | {rotulo} | CEP {cep} | {quando} | {url}')
                pdf = await p.pdf(print_background=True, page_ranges='1-2')
                return pdf, dict(capturado_em=quando, url=url, problema=problema, preco_pagina=preco_pagina)
        except Exception as e:
            problema = str(e) if isinstance(e, RuntimeError) else f'{type(e).__name__} ao abrir a página'
        finally:
            await ctx.close()
        await asyncio.sleep(3 * (k + 1))
    return None, dict(capturado_em=_agora(), url=url, problema=problema)
