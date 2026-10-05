"""Lê o PDF de um carrinho impresso (qualquer loja) e extrai, para cada subitem, preço unitário, subtotal e nome do produto.

Validado nos 6 carrinhos reais aceitos pela SEJC (45/45 preços corretos). Só aceita um preço com conferência:
 a) unitário × quantidade = subtotal, os dois impressos;
 b) quantidade 1: o mesmo valor impresso como unitário e como subtotal;
 c) valor rotulado 'Subtotal' e divisível pela quantidade.
Sem conferência → REVISAO_HUMANA (nunca um preço presumido). PDF sem texto (imagem) → REVISAO_HUMANA.
"""
import io
import re
import unicodedata
import pymupdf

DINHEIRO = re.compile(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})')
CNPJ = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')
PROMO = re.compile(r'(leve\s+\d+\s+ou\s*\+|a partir de|de:)\s*$', re.I)
PARADAS = set('de da do das dos com para e em a o c un und unid pct pacote cx caixa kit tipo cor cores unidades folhas folha'.split())


def _norm(s):
    s = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in s if not unicodedata.combining(c))


def _centavos(s):
    return int(s.replace('.', '').replace(',', ''))


def palavras_padrao(descricao):
    """Palavra de identificação padrão: a primeira palavra significativa da descrição (o usuário pode ajustar)."""
    toks = [t for t in re.findall(r'[a-z]+', _norm(descricao)) if len(t) >= 3 and t not in PARADAS]
    # singular simples ("sacos" → "saco"), para achar "Saco de Lixo" quando a descrição diz "Sacos de Lixo"
    return [t[:-1] if len(t) > 4 and t.endswith('s') and not t.endswith('ss') else t for t in toks[:1]]


def texto_pdf(conteudo: bytes):
    return '\n'.join(pg.get_text() for pg in pymupdf.open(stream=io.BytesIO(conteudo), filetype='pdf'))


def ler(conteudo: bytes, subitens):
    """subitens: lista de objetos com .descricao, .qtd e .palavras. Devolve dict com itens, cnpj, data, total_impresso."""
    texto = texto_pdf(conteudo)
    if len(texto.strip()) < 50:
        return dict(sem_texto=True, itens={s.descricao: dict(status='REVISAO_HUMANA', motivo='PDF sem texto (imagem)') for s in subitens},
                    cnpjs=[], datas=[], valores_impressos=[])
    t = _norm(texto)
    valores = []
    for m in DINHEIRO.finditer(texto):
        antes = t[max(0, m.start() - 25):m.start()]; depois = t[m.end():m.end() + 8]
        if PROMO.search(antes) or depois.strip().startswith('cada'):
            continue
        valores.append((m.start(), _centavos(m.group(1)), 'subtotal' in antes))
    pos = {}
    for s in subitens:
        pal = [_norm(w) for w in (s.palavras or palavras_padrao(s.descricao))]
        if not pal:
            continue
        for m in re.finditer(re.escape(pal[0]), t):
            if all(w in t[m.start():m.start() + 160] for w in pal[1:]):
                pos[s.descricao] = m.start(); break
    ordem = sorted(pos, key=pos.get)
    itens = {}
    for s in subitens:
        if s.descricao not in pos:
            itens[s.descricao] = dict(status='REVISAO_HUMANA', motivo='produto não localizado no carrinho: ajuste as palavras de identificação'); continue
        i = ordem.index(s.descricao); ini = pos[s.descricao]
        fim = pos[ordem[i + 1]] if i + 1 < len(ordem) else ini + 500
        janela = [(v, rot) for p, v, rot in valores if ini <= p < fim and v > 0]
        vals = [v for v, _ in janela]; qtd = s.qtd
        achado = conf = None
        for u in vals:
            if qtd > 1 and u * qtd in vals:
                achado, conf = (u, u * qtd), 'unitário × quantidade = subtotal'; break
        if not achado and qtd == 1:
            rep = [v for v in vals if vals.count(v) >= 2]
            if rep:
                achado, conf = (rep[0], rep[0]), 'valor impresso como unitário e subtotal'
        if not achado:
            rot = [v for v, r in janela if r and v % qtd == 0]
            if rot:
                achado, conf = (rot[0] // qtd, rot[0]), 'subtotal rotulado ÷ quantidade'
        # nome do produto: texto original desde a palavra até o primeiro preço (no máximo 2 linhas)
        prim = next((p for p, v, _ in valores if p > ini), ini + 120)
        nome = ' '.join(texto[ini:min(prim, ini + 160)].split('\n')[:2]).strip()
        itens[s.descricao] = dict(status='OK' if achado else 'REVISAO_HUMANA', unitario=achado[0] if achado else None,
                                  subtotal=achado[1] if achado else None, conferencia=conf, produto=nome[:120],
                                  motivo=None if achado else 'preço sem conferência aritmética')
    return dict(sem_texto=False, itens=itens, cnpjs=list(dict.fromkeys(CNPJ.findall(texto))),
                datas=re.findall(r'\b\d{2}/\d{2}/\d{4}\b', texto)[:3], valores_impressos=[v for _, v, _ in valores])
