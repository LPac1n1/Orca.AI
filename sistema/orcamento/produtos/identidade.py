"""Identidade de produto: decide se um anúncio atende um item da rubrica e se anúncios de lojas diferentes são o MESMO produto.

Regras (validadas com casos-armadilha reais na Fase 1):
- 🟢 mesmo EAN (código de barras) nas lojas, com a mesma quantidade na embalagem;
- 🟡 sem EAN em alguma loja: mesma marca, mesmas unidades, nenhuma medida/cor/formato/variante/linha em conflito,
  variante dita só em um dos nomes conta como diferente, número de modelo igual (clips "NR 1/0" = "Nº0");
- nunca: "zero álcool" como álcool, "sem sal" como "com sal", produto que não começa pelo tipo (porta-objetos no lugar de clips),
  outro item da mesma cesta no lugar deste, e tamanho fora de metade/dobro nas trocas.
Níveis do item: 0 = como descrito · 1 = parecido (mesmo tipo, outro tamanho/variante) · 2 = relacionado (mesma família)."""
import math
import re
import unicodedata

from ..comparador import qty, norm as cnorm


def sa(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', (s or '').lower()) if not unicodedata.combining(c))


# ------------------------------------------------------------------ vocabulário
# Marcas pelo nome inteiro. As de mais de uma palavra ficam inteiras: pedaços ("da" de Gomes da Costa, "coco" de Kero Coco, "sol" de Pinho Sol)
# não são marca — eram, e "Água de Coco" ficava com a marca "coco".
MARCAS = set("""ype limpol qboa candura candida veja omo tixan brilhante ariel coperalcool zulu tupi embalixo dover sanol lysoform bak brilux assim minuano
urca sanifort lavita ninho italac piracanjuba parmalat xando pilao melitta pullman visconti wickbold panco president aviacao qualy teixeira queensberry
hellmann's hellmanns heinz coqueiro benafrutti nestle nescafe marata chamex report magnum bic cis tilibra pilot 3m post-it maped acrilex jandaia polibras dello
plascony spiral bacchi eagle goller compactor stabilo leo&leo leonora molin yin's yins acc dac scotch-brite scotch bombril assolan cif vim sapolio uau
comfort downy fofo personal neve kleenex snob mili santher faber-castell maguary camil nissin bauducco marilan piraque vitarella adria renata sadia perdigao seara
itambe batavo danone vigor tirol quata yoki kitano knorr maggi fugini predilecta pomarola nescau toddy ovomaltine mabel plusvita uniao caravelas guarani soya
limppano esfrebom bettanin novica harpic vanish azulim triex barbarex poliflor mercur pritt tenaz adelbras eurocel foroni credeal chamequinho copimax brw tris newpen
cadersil jocar multilaser maxprint sufresh tial mococa frimesa catupiry polenghi caboclo elma chips aurora sococo ducoco""".split()) - {'elma', 'chips', 'aurora'}
MARCAS |= {'super candida', 'pinho sol', 'dover roll', 'girando sol', 'del valle', 'natural one', '3 coracoes', 'tres coracoes', 'kero coco', 'coco quadrado',
           'seven boys', 'gomes da costa', 'paper one', 'faber castell', 'mr musculo', 'tio joao', 'pif paf', 'cafe do ponto', 'sao domingos', 'elma chips', 'do bem'}
EMBALAGEM = set("""pacote pct caixa cx frasco galao garrafa pet lata vidro sache refil squeeze embalagem economica un und unid unidade unidades bisnaga pote
tetra pak tp saco sacola rolo resma bandeja pouch de da do das dos com e em para o a uso geral liquido liquida po pó profissional""".split())
SUAVES = {'tradicional', 'original', 'classic', 'classico', 'classica', 'natural', 'regular', 'comum', 'branco', 'branca'}
SINONIMOS = {'bloco de notas adesivas': ['bloco adesivo', 'post-it', 'notas adesivas', 'bloco de notas adesivo'],
             'papel sulfite': ['papel sulfite', 'papel a4', 'sulfite'], 'folha sulfite': ['papel sulfite', 'sulfite', 'folha sulfite'],
             'clips': ['clips', 'clipes', 'clipe'], 'pasta sanfonada': ['pasta sanfonada', 'sanfonada'],
             'lapis preto': ['lapis preto', 'lapis grafite', 'lapis n2', 'lapis hb'],
             'sacos de lixo': ['saco de lixo', 'saco para lixo', 'saco lixo', 'sacos de lixo', 'saco plastico para lixo']}
CONECTORES = set('de da do das dos com para e em sem uso unidades unidade folhas folha cores mesa pacote caixa'.split())
MARCA_DA_LOJA = {'lc', 'livrarias curitiba', 'kalunga', 'gimba', 'lepok', 'carrefour', 'atacadao', 'sams club', "sam's club", 'tenda', 'oba',
                 'americanas', 'drogaria sao paulo', 'drogarias pacheco'}
CORES = set('azul preto preta vermelho vermelha verde amarelo amarela rosa roxo roxa laranja branco branca cinza marrom neon pastel transparente '
            'cristal fume colorido colorida sortido sortida'.split())
FORMATO = re.compile(r'\b(a[3-6]|meio oficio|oficio|carta)\b')
VARIANTES = set('neutro limao lavanda eucalipto floral citrus coco maca original tradicional light zero diet integral desnatado semidesnatado '
                'sal fina media grossa dura macia extra super economico reforcado galvanizado cobreado niquelado latonado colorido'.split())
PADRAO = set('galvanizado tradicional original classico classica regular comum branco branca natural'.split())   # variante "de sempre"
LINHAS = set('linha leve premium max plus pro gold slim eco kids profissional ultra power concentrado'.split())
# Tipo de embalagem que define OUTRO produto (pedido da OSC, 03/10/2026: café a vácuo × em saco/pouch não é o mesmo produto). Dois anúncios
# que citam tipos diferentes não são o mesmo produto; e os tipos de EXCLUSIVAS, que o anúncio sempre cita quando valem (a vácuo, refil, sachê),
# também separam quando só um dos anúncios cita.
TIPO_EMBALAGEM = {'vacuo': 'vacuo', 'almofada': 'almofada', 'pouch': 'almofada', 'lata': 'lata', 'vidro': 'vidro', 'sache': 'sache', 'sachet': 'sache',
                  'refil': 'refil'}
EXCLUSIVAS = {'vacuo', 'refil', 'sache'}
MODELO = re.compile(r'\bn(?:o|r|umero)?\.?\s*(\d{1,2}(?:/0)?)\b|\b(\d{1,2}/0)\b')
GENERICAS = EMBALAGEM | set('para com sem de da do em mm cm ml kg und un unid unidades folhas fls tamanho escritorio escolar mesa nr no numero'.split())
EMBALAGEM_N = re.compile(r'\b(?:caixa|cx)\s*(?:com|c/)?\s*(\d+)|\bc/\s*(\d+)')
KIT = re.compile(r'\b(kit|fardo|combo|leve \d|\d+\s?x\s?\d+\s?(ml|g|l)\b|pack)')
MEDIDA_NAO_UNIDADE = r'(?![\d.,])(?!\s*(?:folhas|fls|fl|g|gr|kg|ml|l|lt|mm|cm|m|furos|divisorias|cores|x\d))'
MED = re.compile(r'(\d+(?:[.,]\d+)?)\s*(kg|g|gr|gramas|l|lt|litros?|ml)\b')
TOL = (0.5, 2.0)          # tamanho de um substituto: entre metade e o dobro do pedido
NEGA = r'\b(?:sem|zero|livre de|isento de|0\s?%)\s+'

# ------------------------------------------------------------------ entender o pedido (pedido da OSC, 03/10/2026)
# O pedido é escrito por uma pessoa: a embalagem pode vir na frente ("Caixa Caneta Esferográfica Azul" = canetas esferográficas azuis, em caixa),
# pode vir abreviado ("c/", "cx") ou como adjetivo ("Sardinha Enlatada" = sardinha, em lata). Antes de procurar e de comparar, o pedido é posto na
# forma que as lojas usam: o TIPO do produto primeiro, a embalagem depois. A embalagem nunca é exigida no nome do anúncio (quase nenhuma loja
# escreve "lata" na sardinha), mas um anúncio que cita OUTRA embalagem (vidro, sachê, refil) não atende.
INVARIAVEIS = set('lapis clips tenis pires onibus atlas gratis mais menos tres simples chips cookies ourives'.split())


def singular(w):
    if w in INVARIAVEIS or len(w) < 4:
        return w
    if len(w) > 4:
        for fim_, troca in (('oes', 'ao'), ('aes', 'ao'), ('ais', 'al'), ('eis', 'el'), ('uis', 'ul'), ('ois', 'ol'), ('ns', 'm')):
            if w.endswith(fim_):
                return w[:-len(fim_)] + troca
        if w.endswith(('res', 'zes')):
            return w[:-2]
    return w[:-1] if w.endswith('s') and not w.endswith('ss') else w


def raiz(w):
    """Palavra sem plural e sem gênero: canetas/caneta → canet · azuis/azul → azul · preta/preto → pret (palavras curtas ficam inteiras)."""
    w = singular(w)
    return w[:-1] if len(w) >= 5 and w[-1] in 'ao' else w


_ABREV = [(r'\bc/\s*', 'com '), (r'\bs/\s*', 'sem '), (r'\bp/\s*', 'para '), (r'\bcx\b\.?', 'caixa'), (r'\b(?:pct|pcte)\b\.?', 'pacote'), (r'\bfls\b\.?', 'folhas'),
          (r'\benlatad[oa]s?\b', 'em lata'), (r'\bengarrafad[oa]s?\b', 'em garrafa'), (r'\bensacad[oa]s?\b', 'em saco'),
          (r'\bencaixotad[oa]s?\b', 'em caixa'), (r'\bempacotad[oa]s?\b', 'em pacote')]
_LIDER = re.compile(r'^(caixas?|pacotes?|latas?|garrafas?|frascos?|galao|galoes|potes?|vidros?|fardos?|kits?|resmas?|rolos?|cartelas?|blister|estojos?|saches?|unidades?)'
                    r'\s+(?:(?:de|com|d[aeo]s?)\s+)?(?:(\d+)\s+)?(.+)$')
# depois da embalagem vem algo que mostra que ela É o produto ("caixa organizadora", "garrafa térmica", "lata de lixo", "kit escolar")
_PROPRIO = re.compile(r'(?:organizador|termic|plastic|hermetic|decorativ|descartave|vazi|grande|pequen|medi[oa]\b|retangular|redond|transparente|dobrave|registradora|'
                      r'postal|acustic|forte\b|papelao|madeira|mdf|vidro|metal|aluminio|isopor|acrilic|inox|temperad|som\b|lixo|ferramenta|correio|presente|entrada|'
                      r'gordura|agua\b|luz\b|areia|descarga|pintura|la\b|espuma|escolar|higiene|primeiros|costura|limpeza|arquivo|multiuso|bau\b|box\b|squeeze)')
VARIAS_UNIDADES = set('caixa pacote kit fardo cartela blister estojo'.split())   # embalagem que costuma trazer VÁRIAS unidades do produto
_memo_lider, _memo_pedido = {}, {}


def _lider(desc):
    """(embalagem, quantidade, resto) quando o pedido começa pela embalagem e ela não é o próprio produto; senão None."""
    if desc not in _memo_lider:
        txt = re.sub(r'\s+', ' ', desc or '').strip()
        b = sa(txt)
        if len(b) != len(txt):
            txt = b
        m = _LIDER.match(b)
        if not m or _PROPRIO.match(b[m.start(3):]) or not re.search(r'[a-z]{3,}', b[m.start(3):]):
            _memo_lider[desc] = None
        else:
            _memo_lider[desc] = (singular(m.group(1)), m.group(2), txt[m.start(3):])
    return _memo_lider[desc]


def embalagem_lider(desc):
    """A embalagem escrita NA FRENTE do pedido ('Caixa de canetas azuis' → 'caixa'), ou None."""
    for pad, por in _ABREV[:5]:
        desc = re.sub(pad, por, desc or '', flags=re.I)
    l = _lider(desc)
    return l[0] if l else None


def normalizar_pedido(desc):
    """O pedido na forma das lojas: abreviações por extenso e o tipo do produto na frente ('Caixa Caneta Esferográfica Azul' →
    'Caneta Esferográfica Azul caixa'; 'Sardinha Enlatada' → 'Sardinha em lata'). Aplicar duas vezes dá o mesmo resultado."""
    if desc not in _memo_pedido:
        txt = re.sub(r'\s+', ' ', desc or '').strip()
        for pad, por in _ABREV:
            txt = re.sub(pad, por, txt, flags=re.I)
        txt = re.sub(r'\s+', ' ', txt).strip()
        l = _lider(txt)
        if l:
            txt = f'{l[2]} {l[0]}' + (f' com {l[1]}' if l[1] else '')
        _memo_pedido[desc] = txt
    return _memo_pedido[desc]


# outros NOMES do mesmo produto, vindos da interpretação do pedido pela IA (cesta.py registra; as regras daqui é que decidem)
_DINAMICOS = {}


def definir_sinonimos(desc, tipo, nomes):
    """Registra, para um pedido, o tipo do produto (um trecho do próprio pedido) e outros nomes que as lojas usam para ele."""
    d, t = sa(normalizar_pedido(desc)), re.sub(r'\s+', ' ', sa(tipo or '')).strip()
    nomes = [re.sub(r'\s+', ' ', sa(x)).strip() for x in nomes or []]
    nomes = [x for x in nomes if x and x != t and not re.search(r'\d', x) and len(x.split()) <= 4]
    if t and t in d and nomes:
        _DINAMICOS[d] = (t, [t] + nomes)
        return True
    return False


_VARIAS = {}   # pedido → o pedido é de uma embalagem com VÁRIAS unidades? (interpretação da IA; sem ela, vale a regra da embalagem na frente)


def definir_varias_unidades(desc, valor):
    if isinstance(valor, bool):
        _VARIAS[sa(normalizar_pedido(desc))] = valor


def quer_varias_unidades(desc):
    """True/False quando se sabe; None quando depende do produto (peso/volume = embalagem normal; contagem = várias unidades)."""
    v = _VARIAS.get(sa(normalizar_pedido(desc)))
    if v is not None:
        return v
    return None if embalagem_lider(desc) in VARIAS_UNIDADES else False


_EMB_VARIAS = re.compile(r'\b(caixa|cx|pacote|pct|kit|fardo|estojo|blister|cartela|display)\b')


def embalagem_nao_atendida(desc, titulos):
    """O pedido é de uma embalagem com VÁRIAS unidades ("Caixa Caneta Esferográfica Azul") e algum dos anúncios é da unidade avulsa? Devolve a
    embalagem pedida ('caixa') ou None. Produto vendido por peso ou volume não conta ("Caixa de leite 1L" é a embalagem normal dele), nem o
    pedido que já diz quantas unidades quer e foi atendido."""
    lid, quer = embalagem_lider(desc), quer_varias_unidades(desc)
    titulos = [t for t in titulos or [] if t]
    if quer is False or not titulos or not (lid or quer):
        return None
    if quer is None and any(medida(t) for t in titulos):
        return None
    if all((unidades_emb(t) or 1) > 1 or _EMB_VARIAS.search(sa(t)) for t in titulos):
        return None
    return lid or 'várias unidades'


def _sinonimos(d):
    chave = next((k for k in SINONIMOS if k in d), None)
    if chave:
        return chave, SINONIMOS[chave]
    return _DINAMICOS.get(d) or (None, [])


def _frase_no_anuncio(frase, n, raizes_n):
    return frase in n or all(raiz(w) in raizes_n for w in frase.split() if w not in ('de', 'da', 'do', 'para', 'com', 'e', 'em'))


# família (tipo do produto) dos itens mais comuns; para os demais, a primeira palavra da descrição (editável na tela)
FAMILIAS = [(r'\bcafe soluvel', 'cafe soluvel'), (r'\bcafe\b', 'cafe'), (r'\bagua de coco', 'agua de coco'), (r'\bagua sanitaria', 'agua sanitaria'),
            (r'\bpao de forma', 'pao de forma'), (r'\bbisnaguinha', 'bisnaguinha'), (r'\bsucos?\b', 'suco'), (r'\bleite\b', 'leite'),
            (r'\bmanteiga', 'manteiga'), (r'\bgeleia', 'geleia'), (r'\bmaionese', 'maionese'), (r'\bsardinha', 'sardinha'), (r'\bbanana chips|\bchips\b', 'chips'),
            (r'\bdesinfetante', 'desinfetante'), (r'\bsabao em po', 'sabao em po'), (r'\bdetergente', 'detergente'), (r'\balcool', 'alcool'),
            (r'\bsacos? (de|para) lixo', 'saco de lixo'), (r'\bbloco de notas adesiv|\bbloco adesiv|post-it', 'bloco adesivo'), (r'\bpasta sanfonada', 'pasta sanfonada'),
            (r'\b(papel|folha) sulfite', 'papel sulfite'), (r'\bgrampeador', 'grampeador'), (r'\bgrampos?\b', 'grampo'), (r'\bperfurador', 'perfurador'),
            (r'\blapis\b', 'lapis'), (r'\bclips|\bclipes', 'clips'), (r'\bcaneta esferografica', 'caneta esferografica'), (r'\bcaneta', 'caneta')]
CABECAS = {'bloco adesivo': ['bloco', 'notas', 'post'], 'clips': ['clips', 'clipes', 'clipe'], 'saco de lixo': ['saco', 'sacos'], 'chips': ['chips', 'banana'],
           'bisnaguinha': ['bisnaguinha', 'pao'], 'papel sulfite': ['papel', 'sulfite', 'folha'], 'sabao em po': ['sabao', 'lava'], 'detergente': ['detergente', 'lava'],
           'agua sanitaria': ['agua', 'alvejante'], 'cafe soluvel': ['cafe'], 'caneta esferografica': ['caneta'], 'caneta': ['caneta'], 'agua de coco': ['agua'], 'pao de forma': ['pao']}


def familia_padrao(desc):
    d = sa(normalizar_pedido(desc))
    for pad, fam in FAMILIAS:
        if re.search(pad, d):
            return fam
    pt = palavras_tipo(desc)
    return pt[0] if pt else d.split()[0] if d.split() else ''


# ------------------------------------------------------------------ medidas e quantidades
def qtd_extra(s):
    """Medidas de papelaria/utensílios: furos, divisórias, 26/6."""
    s = sa(s); out = {}
    for pat, dim in ((r'(\d+)\s*furos?', 'furos'), (r'(\d+)\s*(?:divisorias?|divisoes|divis)', 'divisorias'), (r'\b(\d{2})\s*/\s*(\d)\b', 'grampo')):
        achados = {'/'.join(m.groups()) for m in re.finditer(pat, s)}
        if achados:
            out[dim] = achados
    return out


def medidas(s):
    q = {k: set(map(str, v)) for k, v in qty(cnorm(s)).items()}
    q.update(qtd_extra(s)); return q


def numeros(s):
    return {int(x) for x in re.findall(r'\d+', sa(s))}


def unidades_emb(nome):
    """Quantidade de UNIDADES na embalagem ('caixa com 50', 'c/ 4', 'kit 3', '4 unidades'); None se não informada.
    Folhas, gramas, mm etc. não são unidades de embalagem ('com 500 folhas' → None)."""
    n = sa(nome)
    for pad in (r'\b(?:caixa|cx|pacote|pct|kit|fardo|display|pack|blister|cartela)\s*(?:com|c/)?\s*(\d+)' + MEDIDA_NAO_UNIDADE,
                r'\b(\d+)\s*(?:un|und|unid|unidades|pecas|pcs)\b', r'\bc/\s*(\d+)' + MEDIDA_NAO_UNIDADE,
                r'\bcom\s*(\d+)' + MEDIDA_NAO_UNIDADE + r'\s*(?:un|und|unid|unidades|pecas)?\b'):
        m = re.search(pad, n)
        if m:
            return int(m.group(1))
    return None


def medida(s):
    m = MED.search(sa(s))
    if not m:
        return None
    v, u = float(m.group(1).replace(',', '.')), m.group(2)
    return (v * 1000 if u in ('kg', 'l', 'lt', 'litro', 'litros') else v), ('g' if u in ('kg', 'g', 'gr', 'gramas') else 'ml')


def razao_medida(desc, nome):
    a, b = medida(desc), medida(nome)
    return b[0] / a[0] if a and b and a[1] == b[1] and a[0] else None


def razao_unid(desc, nome):
    d = normalizar_pedido(desc)
    m = re.search(r'(\d+)\s*unidades?', sa(d))
    pedido = int(m.group(1)) if m else unidades_emb(d)
    if not pedido and quer_varias_unidades(desc) is not False:   # "Caixa de canetas", sem dizer quantas: qualquer caixa serve
        return 1.0
    return (unidades_emb(nome) or 1) / (pedido or 1)


def modelos(nome):
    """Números de modelo ('Nº 2/0', 'NR 1', 'nr.5'); '0'/'00' equivalem a '1/0'/'2/0' (numeração de clips)."""
    out = set()
    for a, b in MODELO.findall(sa(nome)):
        m = a or b
        out.add(f'{len(m)}/0' if set(m) == {'0'} else m)
    return out


def tamanhos(nome):
    """Tamanhos escritos como fração ('26/6', '24/8', '23/08' = '23/8'): grampo, grampeador. Os de clips ('2/0') ficam em modelos()."""
    return {f'{int(a)}/{int(b)}' for a, b in re.findall(r'(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])', sa(nome)) if int(b) != 0}


def palavras_tipo(desc):
    """Palavras que definem o tipo do item (sem números, medidas e conectores). Atributos como 'integral', 'po', 'sal' ficam."""
    return [w for w in re.findall(r'[a-z]{2,}', sa(normalizar_pedido(desc))) if w not in CONECTORES and not re.fullmatch(r'(ml|kg|g|l|mm|cm|un)', w)]


# ------------------------------------------------------------------ o anúncio atende o item?
def _descrito(desc, nome):
    """Nível 0: o anúncio é o item COMO DESCRITO (mesmo tipo, atributos e medidas)."""
    d, n = sa(normalizar_pedido(desc)), sa(nome)
    chave, sinon = _sinonimos(d)
    toks_n = re.findall(r'[a-z0-9]+', n)
    inicio = ' '.join(toks_n[:4])
    raizes_n = {raiz(t) for t in toks_n}
    primeira = re.findall(r'[a-z]{3,}', d)[0] if re.findall(r'[a-z]{3,}', d) else ''
    primeira = primeira[:-1] if len(primeira) > 4 and primeira.endswith('s') else primeira   # "Sucos de laranja" → suco
    if chave:
        if not any(t.split()[0] in inicio for t in sinon):
            return False
    elif primeira[:5] not in inicio:
        return False
    if re.search(r'\bsem\s+' + re.escape(primeira[:5]), n):
        return False
    if chave:
        # o próprio tipo vale com as palavras em qualquer ordem, plural ou gênero; um OUTRO nome do produto só vale escrito inteiro e junto
        # ("lápis preto" em "Lápis Preto HB", mas não "lápis escolar" em "Lápis de Cor Escolar")
        if not any((x in n) or (i == 0 and _frase_no_anuncio(x, n, raizes_n)) for i, x in enumerate(sinon)):
            return False
        resto = d.replace(chave, '')
    else:
        resto = d
    for w in re.findall(r'[a-z]{3,}', resto):
        if w in EMBALAGEM or w in ('unidades', 'folhas', 'cores', 'mesa'):
            continue
        w2 = w[:-1] if len(w) > 4 and w.endswith('s') else w
        if w2[:6] not in n and raiz(w) not in raizes_n:   # plural e gênero não contam: "azuis" = "azul", "preta" = "preto"
            return False
    ed, en = embalagem_tipo(d), embalagem_tipo(n)   # pedido "em lata" × anúncio "vidro"; pedido "refil" × anúncio sem "refil" (e o contrário)
    if (ed and en and not (ed & en)) or ((ed - en) & EXCLUSIVAS) or ((en - ed) & {'refil'}):
        return False
    if re.search(r'\b(kit|fardo|combo|leve \d|c/\s?\d+\s?un|caixa com \d|cx com \d|\d+\s?x\s?\d+\s?(ml|g|l)\b|pack)', n) \
            and not re.search(r'\b(kit|caixa|cx|pacote|fardo|estojo|cartela|blister)\b', d):
        return False
    md, mn = medidas(desc), medidas(nome)
    for k in set(md) & set(mn):
        if not (md[k] & mn[k]):
            return False
    return not (set(md) - set(mn) - {'pack'})


def compativel(desc, nome, nivel, familia=None):
    """nível 0: como descrito · 1: mesmo tipo (tamanho/variante pode mudar) · 2: mesma família."""
    desc = normalizar_pedido(desc)
    d, n = sa(desc), sa(nome)
    fam = (familia or familia_padrao(desc)).split() or ['']
    inicio = ' '.join(re.findall(r'[a-z0-9]+', n)[:5])
    for w in set(palavras_tipo(desc)) | {fam[0]}:
        if w and re.search(r'\bsem\s+' + re.escape(w[:5]), n) and not re.search(r'\bsem\s+' + re.escape(w[:5]), d):
            return False
    if nivel == 0:
        if _descrito(desc, nome):
            return True
        m = EMBALAGEM_N.search(n)  # "caixa com 50", "C/5000": aceitável quando N é a quantidade pedida
        return bool(m and int(m.group(1) or m.group(2)) in numeros(d)
                    and _descrito(re.sub(r'\d+\s*unidades?', '', desc, flags=re.I), EMBALAGEM_N.sub('', n)))
    if KIT.search(n):
        return False
    if fam[0][:4] not in inicio:
        return False
    if nivel == 1:
        return all(w[:5] in n for w in palavras_tipo(desc))
    return all(w[:5] in n for w in fam)


def cabeca_ok(desc, nome, familia=None):
    """O produto COMEÇA pelo tipo do item (evita 'Porta objetos, canetas, clips...' como clips)."""
    fam = familia or familia_padrao(desc)
    heads = CABECAS.get(fam, [fam.split()[0]] if fam.split() else [])
    din = _DINAMICOS.get(sa(normalizar_pedido(desc)))
    if din:   # outros nomes do mesmo produto: o anúncio pode começar por um deles
        heads = list(heads) + [x.split()[0] for x in din[1]]
    toks = re.findall(r'[a-z]+', sa(nome))
    if toks and toks[0] in MARCAS:
        toks = toks[1:]
    return any(t.startswith(h[:4]) for t in toks[:2] for h in heads)


def negado(desc, nome, familia=None):
    """'Zero álcool', 'sem sal', 'livre de lactose': o produto NEGA algo que o item pede."""
    desc = normalizar_pedido(desc)
    d, n = sa(desc), sa(nome)
    for w in set(palavras_tipo(desc)) | set((familia or familia_padrao(desc)).split()):
        if len(w) > 2 and re.search(NEGA + re.escape(w[:5]), n) and not re.search(NEGA + re.escape(w[:5]), d):
            return True
    return False


def troca_ok(desc, nome, nivel, familia=None):
    """Travas das trocas (níveis 1 e 2): tipo no início do nome, mesma forma (g × mL), tamanho e unidades entre metade e o dobro,
    especificação de encaixe mantida (26/6, furos, divisórias no nível 1)."""
    desc = normalizar_pedido(desc)
    if not cabeca_ok(desc, nome, familia):
        return False
    ma, mn = medida(desc), medida(nome)
    if ma and mn and ma[1] != mn[1]:
        return False
    r = razao_medida(desc, nome)
    if r is not None and not TOL[0] <= r <= TOL[1]:
        return False
    if not TOL[0] <= razao_unid(desc, nome) <= TOL[1]:
        return False
    qd, qn = qtd_extra(desc), qtd_extra(nome)
    if nivel == 1 and any(k not in qn or not (qd[k] & qn[k]) for k in qd):
        return False
    if 'grampo' in qd and not ('grampo' in qn and qd['grampo'] & qn['grampo']):
        return False
    return True


def nivel(desc, nome, outros_itens=(), familia=None):
    """Nível do anúncio para o item (0/1/2) ou None. Um substituto nunca é outro item da mesma cesta."""
    if not cabeca_ok(desc, nome, familia) or negado(desc, nome, familia):
        return None
    for nv in (0, 1, 2):
        if not compativel(desc, nome, nv, familia):
            continue
        if nv and any(compativel(o, nome, 0) for o in outros_itens if o != desc):
            return None
        if nv and not troca_ok(desc, nome, nv, familia):
            continue
        return nv
    return None


# ------------------------------------------------------------------ dois anúncios são o mesmo produto?
def _sem_apostrofo(s):
    return re.sub(r"['’‘`´]", '', s)


MARCAS_N = {_sem_apostrofo(m) for m in MARCAS}


def marca_de(o):
    """Marca pelo nome (lista de marcas) ou pelo campo da loja, ignorando quando a loja põe o PRÓPRIO nome como marca (ex.: 'LC').
    Apóstrofos não contam: Hellmann's = Hellmann’s = Hellmanns."""
    n = ' ' + re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9&\- ]', ' ', _sem_apostrofo(sa(o.get('titulo') or o['nome'])))) + ' '
    achadas = [m for m in MARCAS_N if f' {m} ' in n]
    if achadas:
        return max(achadas, key=len)
    campo = _sem_apostrofo(sa(o.get('marca') or ''))
    return None if not campo or campo in MARCA_DA_LOJA or campo in ('nao disponivel', 'generico', 'outras', 'sem marca') else campo


def embalagem_tipo(nome):
    """Tipos de embalagem que o anúncio cita (vácuo, almofada/pouch, lata, vidro, sachê, refil)."""
    return {TIPO_EMBALAGEM[t] for t in re.findall(r'[a-z]{2,}', sa(nome)) if t in TIPO_EMBALAGEM}


def embalagem_diferente(na, nb):
    ea, eb = embalagem_tipo(na), embalagem_tipo(nb)
    return bool((ea and eb and ea != eb) or ((ea ^ eb) & EXCLUSIVAS))


def conflito(a, b):
    """Diferença EXPLÍCITA entre dois anúncios: marcas, cores, variantes ou tipos de embalagem citados nos dois e diferentes (ou um tipo de
    embalagem exclusivo citado em um só). Um anúncio assim não entra num grupo nem quando outro membro do grupo combina com ele."""
    na, nb = a.get('titulo') or a['nome'], b.get('titulo') or b['nome']
    ma, mb = marca_de(a), marca_de(b)
    if ma and mb and ma != mb:
        return True
    if embalagem_diferente(na, nb):
        return True
    ta = set(re.findall(r'[a-z]{2,}', sa(na))); tb = set(re.findall(r'[a-z]{2,}', sa(nb)))
    for grupo in (CORES, VARIANTES - PADRAO - {'extra', 'super'}):
        ca, cb = ta & grupo, tb & grupo
        if ca and cb and not (ca & cb):
            return True
    return False


def identidade_nome(a, b, desc):
    """Mesmo produto pela DESCRIÇÃO (falta EAN em uma das lojas) → 'Y' (🟡) ou 'R'."""
    na, nb = a.get('titulo') or a['nome'], b.get('titulo') or b['nome']
    ma, mb = marca_de(a), marca_de(b)
    if not ma or ma != mb:
        return 'R'
    if embalagem_diferente(na, nb):
        return 'R'
    if (unidades_emb(na) or 1) != (unidades_emb(nb) or 1):
        return 'R'
    qa, qb = medidas(na), medidas(nb)
    if any(qa[k] != qb[k] for k in set(qa) & set(qb)):
        return 'R'
    fa, fb = set(FORMATO.findall(sa(na))), set(FORMATO.findall(sa(nb)))
    if fa and fb and fa != fb:
        return 'R'
    oa, ob = modelos(na), modelos(nb)
    if oa and ob and oa != ob:
        return 'R'
    if tamanhos(na) != tamanhos(nb):   # grampo 26/6 × 24/8: tamanhos diferentes (ou um anúncio sem o tamanho) não são o mesmo produto
        return 'R'
    mesmo_modelo = bool(oa and oa == ob)
    ta = set(re.findall(r'[a-z]{2,}', sa(na))); tb = set(re.findall(r'[a-z]{2,}', sa(nb)))
    for grupo in (CORES, VARIANTES):
        ca, cb = ta & grupo, tb & grupo
        if ca and cb and ca != cb:
            return 'R'
    if (ta ^ tb) & LINHAS:
        return 'R'
    if (ta ^ tb) & (VARIANTES | CORES) - PADRAO:
        return 'R'
    base = set(re.findall(r'[a-z]{2,}', sa(desc))) | set(re.findall(r'[a-z]+', ma)) | GENERICAS | CORES
    da, db = ta - base, tb - base
    if not da or not db or mesmo_modelo:
        return 'Y'
    return 'Y' if len(da & db) / min(len(da), len(db)) >= 0.5 else 'R'


def identidade(a, b, desc):
    """'G' mesmo EAN (e mesmas unidades) · 'Y' mesmo produto pela descrição · 'R' diferente."""
    if a.get('ean') and b.get('ean'):
        if a['ean'].lstrip('0') != b['ean'].lstrip('0'):
            return 'R'
        ta = set(re.findall(r'[a-z]{2,}', sa(a.get('titulo') or a['nome']))); tb = set(re.findall(r'[a-z]{2,}', sa(b.get('titulo') or b['nome'])))
        for grupo in (CORES, VARIANTES - {'extra', 'super'}):   # mesmo EAN mas "Limão" × "Neutro": erro de cadastro de alguma loja
            if (ta & grupo) and (tb & grupo) and not (ta & tb & grupo):
                return 'R'
        ea, eb = embalagem_tipo(a.get('titulo') or a['nome']), embalagem_tipo(b.get('titulo') or b['nome'])
        if ea and eb and ea != eb:   # mesmo EAN mas "a vácuo" × "pouch": erro de cadastro de alguma loja
            return 'R'
        ua, ub = unidades_emb(a.get('titulo') or a['nome']), unidades_emb(b.get('titulo') or b['nome'])
        if ua and ub:
            return 'G' if ua == ub else 'R'
        u, outro = (ua, b['nome']) if ua else (ub, a['nome'])
        return 'G' if not u or u == 1 or str(u) in re.findall(r'\d+', outro) else 'R'
    return identidade_nome(a, b, desc)


def agrupar(ofertas, desc):
    """Grupos de ofertas que são o MESMO produto (no máximo uma oferta por loja em cada grupo).
    Membros ligados pelo mesmo EAN são certamente o mesmo produto, mesmo quando uma loja escreve o nome de outro jeito ("26.6" por "26/6"):
    para entrar num grupo assim, basta o anúncio conferir com UM dos membros com EAN (e com todos os que entraram só pela descrição)."""
    grupos = []
    for o in sorted(ofertas, key=lambda x: (not x.get('ean'), x['preco'])):
        for g in grupos:
            if o['loja'] in g['por_loja']:
                continue
            membros = list(g['por_loja'].values())
            ids = [identidade(o, x, desc) for x in membros]
            certos = [i for i, x in zip(ids, membros) if x.get('ean') and g.get('ean') and x['ean'].lstrip('0') == g['ean']]
            outros = [i for i, x in zip(ids, membros) if not (x.get('ean') and g.get('ean') and x['ean'].lstrip('0') == g['ean'])]
            if all(i in 'GY' for i in ids) or (len(certos) >= 2 and any(i in 'GY' for i in certos) and all(i in 'GY' for i in outros)
                                               and not (o.get('ean') and o['ean'].lstrip('0') != g['ean'])
                                               and not any(conflito(o, x) for x in membros)):
                g['por_loja'][o['loja']] = o; g['amarelo'] |= 'Y' in ids
                if 'G' in ids and o.get('ean'):
                    g['ean'] = o['ean'].lstrip('0')
                break
        else:
            grupos.append(dict(por_loja={o['loja']: o}, amarelo=False, ean=None))
    return sorted(grupos, key=lambda g: (-len(g['por_loja']), sum(x['preco'] for x in g['por_loja'].values()) / len(g['por_loja'])))


MINI = set('mini miniatura bolso infantil'.split())


def chave_espec(nome, desc='', cor_sempre=False):
    """Especificação do anúncio SEM a marca, para o degrau "produto igual de outra marca". O que o pedido descreve (medidas, atributos) já
    confere em todo anúncio de nível 0; aqui entram os atributos que mudam o produto mesmo quando o pedido não os cita: unidades na
    embalagem, formato (A4 × ofício), tamanho/numeração (grampo 26/6, clips 2/0), linha (kids, profissional, mini) e variante.
    Cor e medidas só entram quando o pedido as cita (pasta azul ou verde é a mesma especificação se o plano não pede cor)."""
    n, d = sa(nome), sa(desc)
    t = set(re.findall(r'[a-z]{2,}', n))
    td = set(re.findall(r'[a-z]{2,}', d))
    med = medidas(nome)
    dims = set(medidas(desc)) | {'grampo'}
    return (tuple(sorted((k, tuple(sorted(v))) for k, v in med.items() if k in dims)), unidades_emb(nome) or 1, tuple(sorted(set(FORMATO.findall(n)))),
            tuple(sorted(tamanhos(nome))), tuple(sorted(modelos(nome))), tuple(sorted(t & CORES)) if (td & CORES or cor_sempre) else (),
            tuple(sorted((t & (VARIANTES | LINHAS | MINI)) - PADRAO)))


def agrupar_espec(ofertas, desc='', cor_sempre=False):
    """Grupos de MESMA ESPECIFICAÇÃO, com marcas que podem ser diferentes (decisão da OSC, 27/09/2026: quando o mesmo produto não existe em
    3 lojas, vale o produto igual de outra marca — forma já aceita pela SEJC em itens de papelaria). A mais barata de cada loja."""
    grupos = {}
    for o in sorted(ofertas, key=lambda x: x['preco']):
        g = grupos.setdefault(chave_espec(o.get('titulo') or o['nome'], desc, cor_sempre), dict(por_loja={}, amarelo=True, misto=True, mesma_cor=cor_sempre))
        g['por_loja'].setdefault(o['loja'], o)
    return sorted(grupos.values(), key=lambda g: (-len(g['por_loja']), sum(x['preco'] for x in g['por_loja'].values()) / len(g['por_loja'])))


def distancia(desc, g, nv, lojas, familia=None, peso_ean=3):
    """Quanto o produto se afasta do pedido: nível, atributos perdidos (sabor, cor, 'integral'...), tamanho, unidades, falta de EAN
    (EAN tem prioridade — decisão D10). Devolve (distância, atributos perdidos)."""
    ofs = [g['por_loja'][l] for l in lojas]
    nome = next((x['nome'] for x in ofs if x.get('ean')), ofs[0]['nome'])
    fam = set((familia or familia_padrao(desc)).split())
    todos = ' '.join(sa(x.get('titulo') or x['nome']) for x in ofs)   # atributo presente em qualquer anúncio do mesmo produto conta
    perdidos = [w for w in palavras_tipo(desc) if w not in fam and w[:4] not in todos]
    m = re.search(r'\b(\d+)\s*cores\b', sa(desc))   # "4 cores" é atributo do item (bloco, caneta, lápis de cor)
    if m and not re.search(r'\b' + m.group(1) + r'\s*cores\b', todos):
        perdidos.append(f'{m.group(1)} cores')
    r = razao_medida(desc, nome); u = razao_unid(desc, nome)
    lid, quer = embalagem_lider(desc) or 'várias unidades', quer_varias_unidades(desc)
    if quer or (quer is None and not any(medida(x['nome']) for x in ofs)):   # "Caixa de canetas": o pedido é de uma embalagem com várias unidades
        varias = re.compile(r'\b(caixa|cx|pacote|pct|kit|fardo|estojo|blister|cartela|display)\b')
        if not all((unidades_emb(x.get('titulo') or x['nome']) or 1) > 1 or varias.search(sa(x.get('titulo') or x['nome'])) for x in ofs):
            perdidos.append(lid)
    return (10 * nv + 4 * len(perdidos) + 3 * (abs(math.log2(r)) if r else 0) + 2 * abs(math.log2(u))
            + peso_ean * sum(1 for x in ofs if not x.get('ean'))), perdidos
