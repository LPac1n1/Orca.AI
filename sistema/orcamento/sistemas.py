"""Rubricas de SISTEMA (software de gestão). Decisões da OSC:
- 27/09/2026: não precisa ser o mesmo sistema; valem 3 sistemas DIFERENTES com ferramentas parecidas (o último orçamento usou
  F&D Solutions, Ongsys e OngFácil);
- 01/10/2026: o plano de cada sistema NÃO é o mais barato: é o que está de acordo com as FERRAMENTAS DE REFERÊNCIA (as da proposta da
  F&D Solutions); proposta em PDF vale como comprovante mesmo sem endereço (link).

Regras desta categoria:
- 3 fornecedores diferentes (raiz do CNPJ), cada um com CNPJ ativo na base oficial da Receita;
- cotação que a OSC já tem em PDF (proposta comercial, sem link) é mantida como está, enquanto estiver válida;
- os outros fornecedores são cotados pela página de preços do próprio fornecedor, guardada em PDF; a IA lê os planos e escolhe o que
  atende às ferramentas de referência (o de escopo mais próximo, quando nenhum plano tem exatamente as mesmas ferramentas). O sistema só
  aceita preço que APARECE na página: no texto ou, quando a tabela é uma imagem, em duas leituras iguais da imagem;
- sem IA (ou sem acordo entre as leituras), o fornecedor não é cotado automaticamente.

Fornecedores (ordem de preferência: primeiro os do último orçamento). CNPJ: do site do fornecedor, conferido na base
oficial. Ongsys, OngFácil, Any3 e Economato publicam preço; F&D Solutions manda proposta; HYB e Auditus, só sob consulta."""
import re

FORNECEDORES = [
    dict(chave='fdsolutions', nome='F&D Solutions', razao='F & D SOLUTIONS LTDA', cnpj='42.274.849/0001-01', origem='base oficial da Receita',
         precos=None, contato='https://fdsolutions.com.br/'),
    dict(chave='ongsys', nome='Ongsys', razao='ONGSYS SISTEMAS LTDA', cnpj='29.335.055/0001-34', origem='base oficial da Receita',
         precos='https://site.ongsys.com.br/precos', contato='https://site.ongsys.com.br/precos'),
    dict(chave='ongfacil', nome='OngFácil', razao='INSTITUTO EKLOOS', cnpj='11.285.430/0001-13',
         origem='base oficial da Receita; o site não publica o CNPJ',
         precos='https://www.ongfacil.org.br/registre-se', contato='https://www.ongfacil.org.br/'),
    dict(chave='any3', nome='Any3 Gestão', razao='FP2 TECNOLOGIA LTDA', cnpj='07.931.921/0001-17', origem='rodapé do site (FP2 Tecnologia Ltda) + base da Receita',
         precos='http://www.any3.com.br/Any3-Gestao-Planos.aspx', contato='http://www.any3.com.br/Any3-Gestao-Contato.aspx',
         obs='a página condiciona o preço com desconto a um link do Any3 no site da instituição (sem o link vale o preço cheio, riscado na página)'),
    dict(chave='economato', nome='Economato', razao='BH BIT SISTEMAS LTDA', cnpj='07.609.769/0001-50', origem='termos de uso do site + base da Receita',
         precos='https://economato.com.br/planos/', contato='https://economato.com.br/'),
    dict(chave='hyb', nome='HYB', razao=None, cnpj=None, origem=None, precos=None, contato='https://hyb.com.br/planos/'),
    dict(chave='auditus', nome='Auditus', razao=None, cnpj=None, origem=None, precos=None, contato='https://www.auditustec.com.br/'),
]

NOME_PLANO = re.compile(r'\b(gr[aá]tis|gratuito|b[aá]sico|essencial|iniciante|start|starter|standard|padr[aã]o|intermedi[aá]rio|avan[cç]ado|profissional|'
                        r'premium|completo|plus|pro|prata|ouro|bronze)\b', re.I)
PRECO_MES = re.compile(r'R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*(?:/\s*m[eê]s|por\s+m[eê]s|ao\s+m[eê]s)', re.I)


def valor(txt):
    t = txt.strip()
    return int(t.replace('.', '').replace(',', '')) if ',' in t else int(t.replace('.', '')) * 100


def planos(texto, a_partir=True):
    """Planos pagos com preço mensal escrito no TEXTO da página: [(nome do plano, centavos)], do mais barato ao mais caro.
    a_partir=False deixa de fora os planos "a partir de R$ X" (preço não definido: depende de proposta)."""
    t = re.sub(r'\s+', ' ', texto or '')
    out = {}
    for m in PRECO_MES.finditer(t):   # cada "R$ X por mês" fica com o nome de plano mais próximo antes dele
        nomes = list(NOME_PLANO.finditer(t[max(0, m.start() - 160):m.start()]))
        v = valor(m.group(1))
        if not a_partir and re.search(r'a partir de\s*$', t[max(0, m.start() - 20):m.start()], re.I):
            continue
        if nomes and v > 0:
            nome = nomes[-1].group(1).capitalize()
            out.setdefault(nome, v)
    return sorted(out.items(), key=lambda kv: kv[1])


def preco_no_texto(texto, centavos):
    """O preço aparece no texto da página? ('R$299/mês', 'R$ 79,90', '1.250,00')"""
    r, c = divmod(int(centavos), 100)
    milhar = f'{r:,}'.replace(',', '.')
    pad = r'(?<![\d.,])(?:' + re.escape(milhar) + '|' + str(r) + ')' + (r'(?:,00)?' if c == 0 else f',{c:02d}') + r'(?!\d|,\d|\.\d{3})'   # 299 não é 299,90
    return re.search(pad, (texto or '').replace('\xa0', ' ')) is not None


def escopo_do_texto(texto):
    """Ferramentas (módulos e funções) de uma proposta comercial em PDF: linhas 'Módulo: ...' e itens numerados '1.1 - ...'."""
    linhas = [re.sub(r'\s+', ' ', l).strip() for l in (texto or '').splitlines()]
    out, atual = [], None
    for l in linhas:
        if re.match(r'm[oó]dulo\s*:', l, re.I):
            atual = l; out.append(l)
        elif re.match(r'\d+\.\d+\s*[-–]', l):
            atual = l; out.append(l)
        elif atual and l and not re.match(r'(escopo|custo|plano|obs|emitimos|cnpj|n\s*º)', l, re.I) and len(l) < 110 and not l.isupper():
            out[-1] += ' ' + l   # continuação da linha anterior
        else:
            atual = None
    return '\n'.join(dict.fromkeys(out))


def ferramentas(referencia):
    """Lista das ferramentas de referência: as linhas numeradas ('1.1 - ...'); sem numeração, todas as linhas menos 'Módulo: ...'."""
    linhas = [re.sub(r'\s+', ' ', l).strip() for l in (referencia or '').splitlines() if l.strip()]
    numeradas = [l for l in linhas if re.match(r'\d+(?:\.\d+)*\s*[-–.)]', l)]
    return numeradas or [l for l in linhas if not re.match(r'm[oó]dulo\s*:', l, re.I)]


def sem_numero(ferramenta):
    return re.sub(r'^\d+(?:\.\d+)*\s*[-–.)]\s*', '', ferramenta).rstrip(' ;.')


def escolher_plano(mapa, planos, lista):
    """Regra fixa (decisão da OSC, 01/10/2026): o plano de acordo com as ferramentas de referência, não o mais barato.
    mapa: [dict(n, recurso, planos)] — para cada ferramenta de referência (n a partir de 1), o recurso equivalente da página e os planos que o
    incluem; planos: [(nome, centavos)] com preço definido; lista: as ferramentas de referência.
    Escolhe o plano que cobre MAIS ferramentas de referência; no empate, o mais barato (não sobe de plano por recurso que a referência não
    pede). Nenhuma ferramenta coberta: o plano pago mais simples. Devolve dict(plano, preco, atende, nao_atende, cobertura, motivo) ou None."""
    if not planos:
        return None
    por_n = {m['n']: m for m in mapa or [] if isinstance(m, dict) and isinstance(m.get('n'), int)}
    nomes = {nm.casefold(): nm for nm, _ in planos}

    def cobre(nome):
        return [n for n in range(1, len(lista) + 1)
                if por_n.get(n, {}).get('recurso') and nome.casefold() in {str(x).casefold() for x in por_n[n].get('planos') or []}]
    cob = {nm: cobre(nm) for nm, _ in planos}
    nome, preco = min(planos, key=lambda x: (-len(cob[x[0]]), x[1]))
    atende = [f'{sem_numero(lista[n - 1])} = {por_n[n]["recurso"]}' for n in cob[nome]]
    nao = [sem_numero(lista[n - 1]) for n in range(1, len(lista) + 1) if n not in cob[nome]]
    em_outro = [n for n in range(1, len(lista) + 1) if n not in cob[nome] and por_n.get(n, {}).get('recurso')
                and any(str(x).casefold() not in nomes for x in por_n[n].get('planos') or [])]   # só em plano sem preço definido ("a partir de")
    menores = [(nm, v) for nm, v in planos if v < preco]
    if not cob[nome]:
        motivo = 'nenhum plano tem as ferramentas de referência; fica o plano pago mais simples'
    elif menores:
        nm, _ = max(menores, key=lambda x: (len(cob[x[0]]), -x[1]))
        motivo = f'menor plano com {len(cob[nome])} das {len(lista)} ferramentas de referência (o plano {nm}, mais barato, tem {len(cob[nm])})'
    else:
        motivo = f'{len(cob[nome])} das {len(lista)} ferramentas de referência já estão no plano pago mais simples; os planos maiores não acrescentam nenhuma'
    if em_outro:
        motivo += f'; {len(em_outro)} ferramenta(s) só em plano sem preço definido'
    return dict(plano=nome, preco=preco, atende=atende, nao_atende=nao, cobertura=len(cob[nome]), motivo=motivo)


def com_preco_publico():
    return [f for f in FORNECEDORES if f['precos'] and f['cnpj']]


def sob_consulta():
    return [f for f in FORNECEDORES if not f['precos']]


def do_cnpj(cnpj):
    d = re.sub(r'\D', '', cnpj or '')[:8]
    return next((f for f in FORNECEDORES if f['cnpj'] and re.sub(r'\D', '', f['cnpj'])[:8] == d), None)
