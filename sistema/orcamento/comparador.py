# Comparador de produtos validado na Fase 0 (800 pares reais rotulados por EAN; ver FASE0_RESULTADOS.md §2.3)
"""Comparador determinístico v2: extrai medidas/variantes/marca e classifica VERDE/AMARELO/VERMELHO.
Política conservadora: VERDE só quando nada distingue as descrições; qualquer dúvida -> AMARELO."""
import re, unicodedata
from rapidfuzz import fuzz

UNITS = {
    'g': ('massa', 1), 'gr': ('massa', 1), 'grs': ('massa', 1), 'gramas': ('massa', 1), 'kg': ('massa', 1000), 'mg': ('massa', 0.001),
    'ml': ('vol', 1), 'l': ('vol', 1000), 'lt': ('vol', 1000), 'lts': ('vol', 1000), 'litro': ('vol', 1000), 'litros': ('vol', 1000),
    'cm': ('comp', 10), 'mm': ('comp', 1), 'm': ('comp', 1000), 'mts': ('comp', 1000), 'metros': ('comp', 1000),
    'folhas': ('folhas', 1), 'fls': ('folhas', 1), 'fl': ('folhas', 1), 'f': ('folhas', 1),
    'un': ('unid', 1), 'und': ('unid', 1), 'unds': ('unid', 1), 'unid': ('unid', 1), 'unidades': ('unid', 1), 'pares': ('unid', 1),
    'rolos': ('rolos', 1), 'capsulas': ('unid', 1), 'caps': ('unid', 1), 'comprimidos': ('unid', 1), 'saches': ('unid', 1), 'sachets': ('unid', 1), 'tabletes': ('unid', 1), 'rolo': ('rolos', 1), 'cores': ('cores', 1), 'w': ('pot', 1), 'v': ('volt', 1),
    'g/m2': ('gram', 1), 'gsm': ('gram', 1), 'materias': ('materias', 1),
}
VARIANT_GROUPS = {
    'cor': set('azul preta preto vermelha vermelho verde amarela amarelo rosa roxo lilas laranja branca branco colorido colorida'.split()),
    'aroma_sabor': set('neutro limao lavanda coco maca mentol eucalipto floral citrus pinho marine morango chocolate baunilha amendoas'.split()),
    'forma': set('gel po barra spray liquido'.split()),
    'versao': set('integral desnatado semidesnatado zero light diet refil concentrado reciclado aquarelavel fluorescente neon pastel metalico infantil adulto sensitive extraforte descafeinado soluvel moido graos organico parboilizado'.split()),
}
SYN = {'aerosol': 'spray', 'aerossol': 'spray', 'refis': 'refil', 'preto': 'preta', 'vermelho': 'vermelha', 'amarelo': 'amarela', 'branco': 'branca'}
VARIANT = set("""azul preta preto vermelha vermelho verde amarela amarelo rosa roxo lilas laranja branca branco colorido colorida
neutro limao lavanda coco maca original tradicional integral desnatado semidesnatado zero light diet refil refis concentrado
reciclado aquarelavel fluorescente neon pastel metalico infantil adulto mentol eucalipto floral citrus pinho marine fresh baby
sensitive extra forte suave premium parboilizado agulhinha carioca moido graos soluvel extraforte descafeinado cristal refinado
demerara mascavo organico gel liquido po barra spray aerosol perfumado""".split())
GENERIC = set("""de da do das dos com para e em a o c un und unid pct pacote pacotes emb embalagem caixa cx kit leve pague produto
novo nova linha escolar papel sulfite caneta lapis cola detergente sabao agua sanitaria desinfetante esponja saco lixo arroz
feijao oleo soja cafe acucar leite biscoito sabonete alcool higienico folha folhas multiuso lava loucas roupas uso geral limpeza
tamanho formato tipo cor cores ref modelo mais super ultra plus max top""".split())

QTY_RE = re.compile(r'(\d+(?:\.\d+)?)\s?(g/m2|gsm|kg|mg|ml|lts|lt|litros|litro|gramas|grs|gr|g|cm|mm|metros|mts|m|l|folhas|fls|fl|f|unidades|unds|und|unid|un|rolos|rolo|capsulas|caps|comprimidos|saches|sachets|tabletes|cores|w|v|pares)\b')


def norm(s):
    s = unicodedata.normalize('NFKD', (s or '').lower())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace('g/m²', 'g/m2').replace(',', '.')
    s = re.sub(r'(\d)\s*x\s*(\d)', r'\1 x \2', s)
    return re.sub(r'\s+', ' ', s).strip()


def qty(s):
    out = {}
    for m in QTY_RE.finditer(s):
        v = float(m.group(1)); u = m.group(2); d, f = UNITS.get(u, (u, 1))
        if d == 'massa' and 60 <= v <= 120 and u in ('g', 'gr', 'grs') and ('a4' in s or 'sulfite' in s):
            d = 'gram'  # gramatura de papel
        out.setdefault(d, set()).add(round(v * f, 3))
    m = (re.search(r'\b(\d{1,3})\s?x\s?\d', s) or re.search(r'\b(?:c/|com|cx|caixa|kit|pack|leve)\s?(\d{1,3})\b', s))
    if m:
        out.setdefault('pack', set()).add(int(m.group(1)))
    return out


def toks(s):
    return set(re.findall(r'[a-z0-9]+', s))


def match(a, b, brand_a=None, brand_b=None, ean_a=None, ean_b=None):
    if ean_a and ean_b:
        g, why = match(a, b, brand_a, brand_b)
        if ean_a == ean_b:
            return ('VERDE', 'EAN idêntico') if g != 'VERMELHO' else ('AMARELO', f'EAN idêntico, mas descrições conflitam ({why}) - possível erro de cadastro da loja')
        return ('VERMELHO', f'EAN diferente; {why}') if g == 'VERMELHO' else ('AMARELO', f'EAN diferente com descrição compatível - possível troca de embalagem ({why})')
    A, B = norm(a), norm(b); why = []
    ba, bb = norm(brand_a or ''), norm(brand_b or '')
    bad = {'nao disponivel', 'generico', 'outras', 'sem marca', ''}
    ba = '' if ba in bad else ba; bb = '' if bb in bad else bb
    same_brand = (not ba or not bb or ba == bb or ba in B or bb in A or ba.split()[0][:5] == bb.split()[0][:5])
    if not same_brand:
        why.append(f'marca {ba}≠{bb}')
    qa, qb = qty(A), qty(B)
    for d in set(qa) & set(qb):
        if not (qa[d] & qb[d]):
            why.append(f'{d}: {sorted(qa[d])}≠{sorted(qb[d])}')
    ta = {SYN.get(t, t) for t in toks(A)}; tb = {SYN.get(t, t) for t in toks(B)}
    for gname, gset in VARIANT_GROUPS.items():
        ga, gb = ta & gset, tb & gset
        if gname == 'forma' and not (ga and gb):
            continue
        if ga and gb and not (ga & gb):
            why.append(f'{gname}: {sorted(ga)}≠{sorted(gb)}')
    va, vb = ta & VARIANT, tb & VARIANT
    if why:
        return 'VERMELHO', '; '.join(why)
    reasons = []
    if set(qa) ^ set(qb):
        reasons.append(f'medida só de um lado: {sorted(set(qa) ^ set(qb))}')
    if va ^ vb:
        reasons.append(f'variante só de um lado: {sorted(va ^ vb)}')
    brand_toks = set(ba.split()) | set(bb.split())
    ex = [t for t in (toks(A) ^ toks(B)) if t not in GENERIC and not t.isdigit() and len(t) > 2 and t not in brand_toks]
    if ex:
        reasons.append(f'termos exclusivos: {sorted(ex)[:6]}')
    sc = fuzz.token_set_ratio(A, B)
    if reasons or sc < 80:
        return 'AMARELO', f'{"; ".join(reasons)} (sim={sc:.0f})'
    return 'VERDE', f'atributos iguais (sim={sc:.0f})'
