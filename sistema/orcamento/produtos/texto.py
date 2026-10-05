"""Como o item é ESCRITO (pedidos da OSC de 03/10/2026):

- unidades de medida com as letras certas: 1L, 500mL, 1kg, 30cm — nunca "1l" ou "1KG" (formatar_medidas);
- descrição simples e sem marca: "Manteiga com Sal", "Pão de Forma Integral", "Caneta Esferográfica" (nome_simples). A marca fica no campo
  Marca; a medida, a quantidade na embalagem e a cor ficam na Especificação (especificacao_do_produto);
- o que a pessoa digita com a marca ou a medida dentro da descrição vai para o campo certo (arrumar_item).
Nada aqui inventa palavra: o nome simples só usa palavras que estão nos anúncios (ou no pedido)."""
import re

from . import identidade as ID

sa = ID.sa

# ------------------------------------------------------------------ unidades de medida
SIMBOLOS = {'mg': 'mg', 'g': 'g', 'gr': 'g', 'grs': 'g', 'grama': 'g', 'gramas': 'g', 'kg': 'kg', 'kgs': 'kg', 'quilo': 'kg', 'quilos': 'kg', 'kilo': 'kg', 'kilos': 'kg',
            'ml': 'mL', 'mls': 'mL', 'l': 'L', 'lt': 'L', 'lts': 'L', 'litro': 'L', 'litros': 'L',
            'mm': 'mm', 'cm': 'cm', 'm': 'm', 'mt': 'm', 'mts': 'm', 'metro': 'm', 'metros': 'm', 'km': 'km', 'm2': 'm²', 'm3': 'm³',
            'w': 'W', 'kw': 'kW', 'v': 'V', 'gb': 'GB', 'mb': 'MB', 'tb': 'TB', 'un': 'un', 'und': 'un', 'unid': 'un'}
_UNIDADES = '|'.join(sorted((re.escape(u) for u in list(SIMBOLOS) + ['m²', 'm³']), key=len, reverse=True))
_MEDIDA = re.compile(r'(?<![\d.,/])(?<![A-WYZa-wyz])(\d+(?:[.,]\d+)?)([  ]?)(' + _UNIDADES + r')(?![\w²³/])', re.I)


def _simbolo(m):
    n, esp, u = m.group(1), m.group(2), m.group(3)
    if u == 'G' and n in ('3', '4', '5'):   # 4G, 5G: rede de celular, não grama
        return m.group(0)
    s = SIMBOLOS[sa(u)]
    if s == 'un':
        return f'{n} {s}'
    return f'{n}{s}' if len(u) > 3 else f'{n}{esp}{s}'   # palavra inteira ("2 litros") vira o símbolo junto do número; o espaço digitado antes do símbolo fica


def formatar_medidas(texto):
    """'1l' → '1L' · '500ML' → '500mL' · '1 Kg' → '1 kg' · '2 litros' → '2L' · '30CM' → '30cm'. Só as letras da unidade mudam: o espaço que a
    pessoa pôs (ou não) entre o número e a unidade fica, e palavras como Unidades e Folhas ficam como estão."""
    return _MEDIDA.sub(_simbolo, texto) if texto else texto


_FIM = re.compile(r'(\d+(?:[.,]\d+)?\s?(?:kg|mg|g|gr|ml|l|lt|litros?|cm|mm|m|metros?|unidades|un|und|folhas|fls))\.?$', re.I)


def separar_medida(nome):
    """('Pão de Forma Artesano Pullman Pacote', '500g') a partir do nome do produto; sem medida no fim do nome: (nome, None)."""
    nome = re.sub(r'\s+', ' ', nome or '').strip()
    m = _FIM.search(nome)
    if not m or m.start() == 0:
        return nome, None
    return re.sub(r'[\s,\-–|]+$', '', nome[:m.start()]), formatar_medidas(m.group(1))


# ------------------------------------------------------------------ palavras de um anúncio
CONECTORES = set('de da do das dos com sem para e em a o ao no na'.split())
# embalagem, unidade de venda e propaganda: nunca fazem parte do nome simples
FORA_DO_NOME = set("""pacote pct pt caixa cx frasco fr galao garrafa gf pet lata vidro sache refil squeeze embalagem economica un und unid unidade unidades bisnaga pote
tetra pak tp saco sacola rolo rolos resma bandeja pouch almofada vacuo gatilho tubo blister cartela display promocao gratis leve pague oferta kit fardo tampa novo nova
folhas folha fls fl furos tamanho ref cod codigo""".split())
SABORES = set("""uva maca laranja limao maracuja caju pessego morango abacaxi goiaba manga tangerina coco chocolate baunilha menta hortela framboesa amora cereja banana
tomate azeite oleo molho mel leite cafe canela cebola alho queijo presunto frango carne peixe atum milho ervilha feijao arroz aveia""".split())
# marcas que também são palavras comuns: não são tiradas de uma descrição DIGITADA só por estarem na lista de marcas
AMBIGUAS = set('brilhante veja neve assim report personal comfort fofo magnum minuano zulu tupi urca eagle evolution spiral post-it candida uniao condor scotch'.split())
_MINUSCULAS = CONECTORES | {'sem'}
_LINHAS = ID.LINHAS - {'concentrado', 'profissional'}   # nome de linha do fabricante (não entra no nome simples)


def _tokens(titulo):
    """[(palavra como escrita, chave sem acento)] sem a pontuação das pontas."""
    out = []
    for bruto in re.split(r'\s+', titulo or ''):
        w = bruto.strip('.,;:()[]{}|"\'*')
        if w and w not in ('-', '–', '+', '/'):
            out.append((w, sa(w)))
        elif w in ('-', '–', '|'):
            out.append((w, '|'))   # separador de loja: acaba a "cabeça" do nome
    return out


def marcas_no_texto(texto, extras=()):
    """Palavras que são MARCA no texto: as marcas conhecidas que aparecem nele e as informadas (campo Marca, marca dita pela loja)."""
    n = ' ' + re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9&\- ]', ' ', ID._sem_apostrofo(sa(texto)))) + ' '
    achadas = {m for m in ID.MARCAS_N if f' {m} ' in n}
    for e in extras:
        e = re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9&\- ]', ' ', ID._sem_apostrofo(sa(e or '')))).strip()
        if e and f' {e} ' in n:
            achadas.add(e)
    return achadas


def _palavras_de_marca(titulos, extras=()):
    out = set()
    for t in titulos:
        for m in marcas_no_texto(t, extras):
            out |= set(m.split())
    return out


def _fora(chave, marcas):
    return chave in marcas or chave in FORA_DO_NOME or chave in _LINHAS or bool(re.search(r'\d', chave)) or chave == '|'


def _cabeca(toks, marcas):
    """As palavras do começo do anúncio, antes da marca, de um número ou da embalagem: é onde as lojas escrevem o tipo do produto."""
    i = 0
    while i < len(toks) and toks[i][1] in marcas:   # anúncio que começa pela marca ("BIC Caneta...")
        i += 1
    out = []
    for w, k in toks[i:]:
        if k not in CONECTORES and _fora(k, marcas):
            break
        out.append((w, k))
    while out and out[-1][1] in CONECTORES:
        out.pop()
    return out


def _titulo(palavras):
    out = []
    for i, w in enumerate(palavras):
        out.append(w.lower() if i and sa(w) in _MINUSCULAS else (w[:1].upper() + w[1:].lower() if w.isupper() or w.islower() else w))
    return ' '.join(out)


def nome_simples(titulos, pedido=None, marca=None, marcas_extras=()):
    """Nome simples do produto orçado, a partir dos anúncios das lojas (o MESMO produto): sem marca, linha, embalagem nem medida.
    - mesmo tipo do pedido (todas as palavras do pedido estão nos anúncios): o nome é o do pedido, mais a variante ou o sabor que os anúncios
      citam e o pedido não ("Suco de Maçã" orçado como uva e maçã → "Suco de Uva e Maçã"). Nome de linha ("Artesano") não entra;
    - outro tipo (troca): as palavras do começo dos anúncios em que a maioria concorda ("Bloco Adesivo", "Lápis de Cor").
    Sem anúncios, devolve o pedido."""
    titulos = [t for t in (titulos or []) if t and t.strip()]
    if not titulos:
        return (pedido or '').strip()
    marcas = _palavras_de_marca(titulos, [marca] + list(marcas_extras))
    T = [_tokens(t) for t in titulos]
    R = ID.raiz
    comuns = set.intersection(*[{R(k) for _, k in t} for t in T])
    cabecas = [_cabeca(t, marcas) for t in T]
    minimo = len(T) if len(T) < 3 else 2
    conta = {}
    for c in cabecas:
        for r in {R(k) for _, k in c if k not in CONECTORES}:
            conta[r] = conta.get(r, 0) + 1
    maioria = {r for r, n in conta.items() if n >= minimo}
    vocab = {R(w) for w in (ID.VARIANTES | SABORES) - ID.PADRAO - ID.SUAVES}   # "tradicional", "original": variante de sempre, não entra
    do_pedido = [R(w) for w in ID.palavras_tipo(pedido)] if pedido else []
    do_pedido = [r for r in do_pedido if r not in {R(m) for m in marcas} and r not in {R(x) for x in FORA_DO_NOME}]
    mesmo_tipo = bool(do_pedido) and all(r in comuns for r in do_pedido)
    if mesmo_tipo:
        manter = set(do_pedido) | (comuns & vocab)
    else:
        manter = maioria | (comuns & (vocab | set(do_pedido)))
    manter = {r for r in manter if not _fora(r, {R(m) for m in marcas}) and r not in {R(x) for x in FORA_DO_NOME | _LINHAS}}
    if not mesmo_tipo:   # cor só fica no nome quando faz parte do tipo (vem no começo dos anúncios: "Feijão Preto"); senão vai para a especificação
        manter -= {R(c) for c in ID.CORES} - maioria
    if not manter:
        return (pedido or '').strip() or titulos[0]

    def montar(toks):
        saida, usadas, pendente = [], set(), None
        for w, k in toks:
            r = R(k)
            if k in CONECTORES and k not in manter:
                pendente = w if saida else None   # só entra se a palavra seguinte ficar
                continue
            if r in manter and r not in usadas and k not in marcas:
                if pendente:
                    saida.append(pendente)
                saida.append(w); usadas.add(r)
            pendente = None
        return saida, usadas
    melhor = max((montar(t) for t in T), key=lambda x: (len(x[1]), sum(1 for w in x[0] if sa(w) in CONECTORES), -len(x[0])))
    palavras = melhor[0]
    if not palavras:
        return (pedido or '').strip() or titulos[0]
    if mesmo_tipo and pedido:   # "Suco de Maçã" → "Suco de Uva e Maçã": o "de" que o pedido tinha depois da primeira palavra
        pp = [w for w in re.split(r'\s+', pedido.strip()) if w]
        if len(pp) > 2 and sa(pp[1]) in ('de', 'da', 'do') and R(sa(pp[0])) == R(sa(palavras[0])) and len(palavras) > 1 and sa(palavras[1]) not in CONECTORES:
            palavras.insert(1, pp[1].lower())
    return _titulo(palavras)


_QTD = re.compile(r'(\d+(?:[.,]\d+)?)\s?(kg|mg|g|gr|ml|l|lt|litros?|cm|mm|m|metros?)(?![\w/])', re.I)
_BASE = {'kg': ('g', 1000), 'mg': ('g', .001), 'g': ('g', 1), 'gr': ('g', 1), 'ml': ('ml', 1), 'l': ('ml', 1000), 'lt': ('ml', 1000), 'litro': ('ml', 1000),
         'litros': ('ml', 1000), 'cm': ('mm', 10), 'mm': ('mm', 1), 'm': ('mm', 1000), 'metro': ('mm', 1000), 'metros': ('mm', 1000)}
_CONTAGEM = re.compile(r'(\d+)\s?(folhas|fls|fl|cores|furos|rolos|divisorias)\b')
_ROTULO = {'folhas': 'Folhas', 'fls': 'Folhas', 'fl': 'Folhas', 'cores': 'Cores', 'furos': 'Furos', 'rolos': 'Rolos', 'divisorias': 'Divisórias'}


def _medidas(titulo):
    out = {}
    for m in _QTD.finditer(titulo):
        d, f = _BASE[m.group(2).lower()]
        out.setdefault((d, round(float(m.group(1).replace(',', '.')) * f, 3)), formatar_medidas(m.group(0)))
    return out


def especificacao_do_produto(titulos, nome=''):
    """Especificação do produto orçado, tirada dos anúncios: peso/volume (ou comprimento), contagem ("400 Folhas", "12 Cores", "50 Unidades"),
    tamanho de encaixe ("26/6") e a cor que os 3 anúncios citam. None se os anúncios não dizem nada disso."""
    titulos = [t for t in (titulos or []) if t and t.strip()]
    if not titulos:
        return None
    minimo = len(titulos) if len(titulos) < 3 else 2
    partes = []
    meds = [_medidas(t) for t in titulos]
    todas = {}
    for md in meds:
        for k, v in md.items():
            todas.setdefault(k, v)
    comuns = [k for k in todas if sum(1 for md in meds if k in md) >= minimo]
    peso = [k for k in comuns if k[0] in ('g', 'ml')]
    for k in (peso[:1] or [k for k in comuns if k[0] == 'mm'][:1]):
        partes.append(todas[k])
    conta = {}
    for t in titulos:
        for n, u in set(_CONTAGEM.findall(sa(t))):
            conta[(n, _ROTULO[u])] = conta.get((n, _ROTULO[u]), 0) + 1
    partes += [f'{n} {u}' for (n, u), q in conta.items() if q >= minimo]
    us = [ID.unidades_emb(t) or 1 for t in titulos]
    if us[0] > 1 and us.count(us[0]) >= minimo and not any(p.startswith(f'{us[0]} ') for p in partes):
        partes.append(f'{us[0]} Unidades')
    tam = set.intersection(*[ID.tamanhos(t) for t in titulos])
    partes += sorted(tam)
    cores = set.intersection(*[{k for _, k in _tokens(t)} & ID.CORES for t in titulos]) - {sa(w) for w in nome.split()}
    for t in _tokens(titulos[0]):
        if t[1] in cores:
            partes.append(t[0][:1].upper() + t[0][1:].lower())
    return ' '.join(dict.fromkeys(partes)) or None


# ------------------------------------------------------------------ o que a pessoa digitou
def _tirar(texto, frase):
    """Tira a frase (sem diferença de maiúsculas e acentos) do texto; devolve (texto novo, a frase como estava escrita) ou (texto, None)."""
    base = sa(texto)
    m = re.search(r'(?<![a-z0-9])' + r'\s+'.join(re.escape(p) for p in sa(frase).split()) + r'(?![a-z0-9])', base)
    if not m or len(base) != len(texto):
        return texto, None
    escrito = texto[m.start():m.end()]
    novo = re.sub(r'\s+', ' ', texto[:m.start()] + ' ' + texto[m.end():]).strip()
    return re.sub(r'(?:\s*[-–|,]\s*)+$|^(?:\s*[-–|,]\s*)+', '', novo).strip(), escrito


def marca_conhecida(desc):
    """A marca conhecida (e que não é palavra comum) escrita dentro de uma descrição, ou None."""
    achadas = [m for m in marcas_no_texto(desc) if m not in AMBIGUAS]
    return max(achadas, key=len) if achadas else None


def arrumar_item(desc, marca=None, esp=None):
    """O que a pessoa digitou, nos campos certos: a marca sai da descrição (e vai para Marca, se estava em branco) e as unidades de medida
    ficam com as letras certas. O resto fica como foi escrito. Devolve (descrição, marca, especificação)."""
    desc = formatar_medidas(re.sub(r'\s+', ' ', desc or '').strip())
    marca = re.sub(r'\s+', ' ', marca or '').strip() or None
    esp = formatar_medidas(re.sub(r'\s+', ' ', esp or '').strip()) or None
    if marca:
        novo, achou = _tirar(desc, marca)
        if achou and ID.palavras_tipo(novo):
            desc = novo
    else:
        m = marca_conhecida(desc)
        if m:
            novo, escrito = _tirar(desc, m)
            if escrito and ID.palavras_tipo(novo):
                desc, marca = novo, escrito
    return desc, marca, esp


def precisa_arrumar(desc, marca=None, trocado=False):
    """A descrição ainda não é simples? (tem a marca do item, uma marca conhecida, a unidade escrita errado ou — em item trocado pela
    pesquisa — números do anúncio)"""
    if marca and _tirar(desc, marca)[1]:
        return True
    if marca_conhecida(desc) or formatar_medidas(desc) != desc:
        return True
    return bool(trocado and re.search(r'\d', desc))
