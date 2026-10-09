"""Tarefas automáticas do sistema (rodam em segundo plano, com progresso na tela):
- pesquisar_rubrica: produtos de uma rubrica de material (por item ou por trio) + IA nos casos de dúvida + teto da rubrica → PROPOSTA;
- aplicar_proposta: comprovantes (carrinho real nas lojas VTEX; página do produto nas demais), fornecedores por item e nova versão;
- vagas_do_cargo: coleta de vagas no Brasil (título exato + CNPJ) no banco de vagas e preenchimento das 3 pesquisas;
- base_receita: atualização mensal da base oficial do CNPJ."""
import asyncio
import datetime as dt
import re

from . import db, ia
from .modelo import Fonte, Evidencia, Subitem, PesquisaSalarial, RubricaMaterial, RubricaRH, pedido_do_subitem, descricao_completa
from .produtos import cesta, lojas as L, teto, identidade as ID, texto as T
from .regras import media, cnpj_formatar, valores_do_plano


def _rubrica(p, item):
    return next(x for x in p.rubricas if x.item == item)


def _cep(p):
    """CEP de entrega do projeto: estoque e preço das lojas dependem dele. Não há CEP padrão (o sistema serve a qualquer OSC)."""
    if not re.sub(r'\D', '', p.cep or ''):
        raise ValueError('o projeto está sem o CEP de entrega. Informe o CEP na configuração do projeto: ele é usado para conferir estoque e preço nas lojas')
    return p.cep


def lojas_da_rubrica(p, r):
    setor = L.setor_da_rubrica(r.descricao)
    return L.lojas_para(setor, p.config.lojas_desligadas)


def _precos(o):
    return [x['preco'] for x in o['ofertas']]


# ------------------------------------------------------------------ pesquisa → proposta
def _valor_ref(s):
    """Valor unitário que o item tinha no plano (referência para a troca pela categoria da rubrica)."""
    return s.valor_plano or (media(s.precos) if s.precos and all(s.precos) else None)


CARRINHO_URL = re.compile(r'/checkout|/carrinho|/cart(?![a-z])', re.I)
CARRINHO_VARIOS = re.compile(r'_carrinho_[a-z]+_item[0-9]+(?:_[0-9]+)?[.]pdf$', re.I)   # nome dos PDFs antigos: um carrinho por loja, com vários itens


def comprovante_no_formato(ev):
    """Regras da OSC (01/10/2026): o endereço leva ao PRODUTO (não a um carrinho, que abre vazio) e o PDF tem só o item a que se refere.
    Endereço vazio é aceito (proposta em PDF sem link)."""
    if not ev or not ev.arquivo or ev.problema:
        return False
    return not (ev.url and CARRINHO_URL.search(ev.url)) and not CARRINHO_VARIOS.search(ev.arquivo)


_PRECO_PDF = {}


def preco_no_pdf(rel=None, centavos=None, conteudo=None):
    """O preço aparece no texto do PDF? True/False; None quando não dá para conferir (PDF sem texto ou ilegível)."""
    from . import sistemas as S
    if not centavos:
        return None
    k = (rel, centavos)
    if conteudo is not None or k not in _PRECO_PDF:
        t = texto_do_pdf(rel, conteudo)
        r = None if len(t.strip()) < 200 else S.preco_no_texto(t, centavos)
        if conteudo is not None:
            return r
        _PRECO_PDF[k] = r
    return _PRECO_PDF[k]


def pesquisa_comprovada(f, preco):
    """O comprovante está no formato pedido E prova o preço registrado. PDF anexado pela OSC não é conferido aqui (ela é avisada ao anexar)."""
    ev = f.evidencia
    if not comprovante_no_formato(ev):
        return False
    return ev.origem == 'pdf' or preco_no_pdf(ev.arquivo, preco) is not False


def consertar_links(p, pid):
    """Comprovante certo (PDF de um item só) mas com o endereço do CARRINHO, que abre vazio para quem clica: troca pelo endereço da página
    do produto, tirado do banco de produtos (mesma loja, mesmo anúncio). Não refaz a pesquisa. Devolve quantos endereços foram trocados."""
    loja_do_nome = {v['nome']: k for k, v in L.LOJAS.items()}
    n = 0
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            continue
        banco = None
        for s in r.subitens:
            for k, f in enumerate(s.fontes):
                ev = f.evidencia
                if not (ev and ev.arquivo and ev.url and CARRINHO_URL.search(ev.url)) or CARRINHO_VARIOS.search(ev.arquivo):
                    continue
                loja, prod = loja_do_nome.get(f.plataforma), (s.produtos[k] if k < len(s.produtos) else None)
                if not loja or not prod:
                    continue
                banco = db.produtos_do_banco(pid, r.item) if banco is None else banco
                urls = {x['url'] for b in banco.values() for o in b['opcoes'] for x in list(o.get('ofertas') or []) + list(o.get('reservas') or [])
                        if x.get('loja') == loja and (x.get('titulo') or x.get('nome')) == prod and x.get('url') and not CARRINHO_URL.search(x['url'])}
                if len(urls) == 1:
                    ev.url = urls.pop(); n += 1
    return n


MARCAS_DIFERENTES = 'marcas diferentes'   # confirmação das pesquisas antigas em que as 3 lojas tinham produtos de marcas diferentes


def produtos_em_conflito(s):
    """Dois produtos gravados nas pesquisas do item que NÃO são o mesmo produto (marca, cor, variante ou tipo de embalagem diferentes: café a
    vácuo × em pouch, bloco refil × bloco comum), ou None. Só os itens confirmados pela descrição (com o mesmo código de barras nas 3 lojas
    não há dúvida; em rubrica de sistema os 3 são diferentes de propósito)."""
    if not (s.confirmacao or '').startswith('descrição'):
        return None
    import itertools
    nomes = [x for x in (s.produtos or []) if x]
    for a, b in itertools.combinations(nomes, 2):
        if ID.conflito(dict(nome=a), dict(nome=b)):
            return a, b
    return None


def produtos_diferentes(s):
    """As 3 pesquisas do item NÃO são do mesmo produto? (pesquisa antiga "mesma especificação, marcas diferentes", ou nomes gravados que
    mostram produtos diferentes). Pedido da OSC (03/10/2026): o produto tem de ser exatamente o mesmo nas 3 lojas (marca, cor, tipo, embalagem)."""
    return MARCAS_DIFERENTES in (s.confirmacao or '') or bool(produtos_em_conflito(s))


def subitem_pronto(s):
    """Subitem com as 3 pesquisas completas: 3 fornecedores, 3 preços, o comprovante em PDF de cada um e o MESMO produto nas 3."""
    return (len(s.fontes) == 3 and len(s.precos or []) == 3 and all(s.precos) and not produtos_diferentes(s)
            and all(pesquisa_comprovada(f, pr) for f, pr in zip(s.fontes, s.precos)))


def produtos_em_uso(subitens):
    """O que identifica os produtos que os subitens já usam: páginas (loja, endereço) e códigos de barras."""
    chaves = set()
    for s in subitens:
        for k, f in enumerate(s.fontes or []):
            loja, url = _loja_da_fonte(f), url_limpa(f.evidencia.url)
            if loja and url:
                chaves.add((loja, url))
        chaves |= {e.lstrip('0') for e in (s.eans or []) if e}
    return chaves


def descricoes_do_item(subitens):
    """Como cada subitem aparece: o pedido, a descrição atual e os nomes dos produtos orçados (para o motor não trocar outro item por eles)."""
    out = []
    for s in subitens:
        for d in [pedido_do_subitem(s), descricao_completa(s)] + [x for x in (s.produtos or []) if x]:
            if d and d not in out:
                out.append(d)
    return out


def voltar_ao_pedido(s):
    """O subitem volta a ser o que a OSC pediu (descrição, marca e especificação originais), sem pesquisas nem valor: usado quando ele
    tinha sido trocado por um produto que já era outro item da rubrica e a nova pesquisa não achou o mesmo produto em 3 lojas."""
    if s.descricao_original:
        s.descricao = s.descricao_original
        s.marca = (s.marca_original or None) if s.marca_original is not None else None
        s.especificacao = (s.especificacao_original or None) if s.especificacao_original is not None else s.especificacao
    s.descricao_original = s.marca_original = s.especificacao_original = None
    s.nivel, s.confirmacao, s.valor_plano = 0, None, None
    s.fontes, s.precos, s.produtos, s.eans = [], [None, None, None], [None, None, None], [None, None, None]


def itens_repetidos(r):
    """{índice do subitem: índice do primeiro subitem com o MESMO produto} — dois itens da rubrica não podem ser o mesmo produto
    (mesma página numa loja, mesmo código de barras ou mesma descrição completa). O primeiro fica; os seguintes são os repetidos."""
    from .regras import norm
    vistos, out = [], {}
    for i, s in enumerate(r.subitens):
        chaves = produtos_em_uso([s]) | ({('descricao', norm(descricao_completa(s)))} if s.descricao else set())
        j = next((j for j, c in vistos if chaves & c), None)
        if j is None:
            vistos.append((i, chaves))
        else:
            out[i] = j
    return out


def item_repetido(r, s):
    return any(r.subitens[i] is s for i in itens_repetidos(r))


def subitens_a_pesquisar(r):
    """Subitens que o "Pesquisar tudo" precisa (re)fazer: sem as 3 pesquisas comprovadas do mesmo produto, ou repetindo outro item."""
    rep = itens_repetidos(r)
    return [s for i, s in enumerate(r.subitens) if i in rep or not subitem_pronto(s)]


def url_limpa(u):
    """Endereço sem espaços (algumas lojas publicam o endereço do produto com espaço no meio; o navegador aceita, a validação não)."""
    u = (u or '').strip()
    return re.sub(r'\s', '%20', u) or None


TIPOS_RUBRICA = {
    'rh': 'Mão de obra: 3 vagas com o título exato (ou, se faltar, com um título similar aceito), CNPJ ativo e salário mensal definido (as de menor salário)',
    'mercado': 'Produtos de mercado (alimentação, limpeza, escritório/pedagógico): o mesmo produto em 3 lojas, as mais baratas; trocas em degraus',
    'material': 'Outros materiais: o mesmo produto em 3 lojas (todas as lojas cadastradas)',
    'sistema': 'Sistema/software: 3 sistemas diferentes com ferramentas parecidas; o plano de cada um é o que está de acordo com as ferramentas de referência (não o mais barato); proposta em PDF sem link é aceita',
    'servico': 'Serviço: 3 propostas de fornecedores do serviço (sem pesquisa automática)',
}


def tipo_da_rubrica(r):
    """Cada tipo de rubrica tem as suas regras (decisão da OSC, 27/09/2026). A OSC pode escolher o tipo na tela da rubrica."""
    if isinstance(r, RubricaRH):
        return 'rh'
    if getattr(r, 'regra', None) in TIPOS_RUBRICA:
        return r.regra
    setor = L.setor_da_rubrica(r.descricao)
    if setor == 'servico':
        return 'sistema' if re.search(r'\b(sistemas?|software|plataforma)\b', r.descricao or '', re.I) else 'servico'
    return 'mercado' if setor else 'material'


CONF_SISTEMA = 'sistemas diferentes; plano pelas ferramentas de referência'


def valor_do_sistema(s):
    """Rubrica de sistema (pedido da OSC, 02/10/2026): o valor no plano é o MENOR das 3 cotações, não a média. None se faltar cotação."""
    return min(s.precos) if len(s.precos or []) == 3 and None not in s.precos else None


def anexada(f):
    """Cotação que a OSC anexou em PDF (proposta comercial, carrinho impresso…): fica como está; o endereço (link) é opcional."""
    ev = f.evidencia
    return bool(ev and ev.arquivo and ev.origem != 'navegador')


def sistema_pronto(r):
    """Sistema: 3 cotações com PDF; as automáticas, só se o plano foi escolhido pelas ferramentas de referência (regra de 01/10/2026)."""
    def ok(s):
        return subitem_pronto(s) and (all(anexada(f) for f in s.fontes) or 'referência' in (s.confirmacao or ''))
    return bool(r.subitens) and all(ok(s) for s in r.subitens)


def texto_do_pdf(rel=None, conteudo=None):
    try:
        import pymupdf
        d = pymupdf.open(stream=conteudo, filetype='pdf') if conteudo is not None else pymupdf.open(db.caminho_absoluto(rel))
        return '\n'.join(pg.get_text() for pg in d)
    except Exception:
        return ''


def _reais(v):
    return f'R$ {v / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def anexar_pdf(p, pid, r, i, k, nome_arquivo, conteudo):
    """A OSC anexa o PDF da pesquisa k do subitem i (proposta sem link, página impressa…). Não muda preço, CNPJ nem data: confere o que
    dá (preço e CNPJ no texto do PDF) e avisa. Em rubrica de sistema, lê as ferramentas de referência da proposta. Devolve a mensagem."""
    from . import sistemas as S
    from .modelo import fontes_do_subitem
    from .regras import cnpj_dv_ok
    if not conteudo.startswith(b'%PDF'):
        raise ValueError('o arquivo enviado não é um PDF')
    sub = r.subitens[i]
    if len(sub.fontes) != 3:   # o subitem passa a ter as suas 3 pesquisas (cópia das da rubrica)
        sub.fontes = ([f.model_copy(deep=True) for f in fontes_do_subitem(r, sub)] + [Fonte(), Fonte(), Fonte()])[:3]
    f = sub.fontes[k]
    sha, rel = db.guardar_arquivo(pid, nome_arquivo, conteudo)
    f.evidencia = Evidencia(arquivo=rel, sha256=sha, url=(f.evidencia.url if f.evidencia and f.evidencia.origem != 'navegador' else None),
                            origem='pdf', capturado_em=db.agora())
    msg = [f'PDF anexado à pesquisa {k + 1} de "{sub.descricao}" ({f.plataforma or f.nome or "sem fornecedor"})'
           + ('' if f.evidencia.url else ', sem link (o PDF é o comprovante)')]
    t = texto_do_pdf(conteudo=conteudo)
    if len(t.strip()) < 40:
        msg.append('o PDF não tem texto (é imagem): confira o preço e o CNPJ olhando o arquivo')
    else:
        pr = sub.precos[k] if k < len(sub.precos) else None
        if pr:
            msg.append(f'o preço {_reais(pr)} ' + ('aparece no PDF' if S.preco_no_texto(t, pr) else 'NÃO aparece no PDF: confira'))
        noPDF = list(dict.fromkeys(cnpj_formatar(c) for c in re.findall(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}', t)))
        meu = cnpj_formatar(f.cnpj) if f.cnpj else None
        if meu and meu in noPDF:
            msg.append(f'o CNPJ {meu} aparece no PDF')
        elif meu:
            mesma = [c for c in noPDF if re.sub(r'\D', '', c)[:8] == re.sub(r'\D', '', meu)[:8]]
            if mesma:
                msg.append(f'o PDF traz o CNPJ {mesma[0]}' + ('' if cnpj_dv_ok(mesma[0]) else ' (dígito verificador inválido: erro de digitação na proposta)')
                           + f'; a pesquisa fica com {meu}, que é o da base oficial da Receita')
            else:
                msg.append(f'o CNPJ da pesquisa ({meu}) não aparece no PDF' + (f' (o PDF traz {", ".join(noPDF[:3])})' if noPDF else '') + ': confira')
        if tipo_da_rubrica(r) == 'sistema':
            forn = identificar_cotacao(f, t)
            if forn:
                while len(sub.produtos) < 3:
                    sub.produtos.append(None)
                sub.produtos[k] = sub.produtos[k] or f'{forn["nome"]} — proposta comercial em PDF'
                msg.append(f'a proposta é de {forn["nome"]} ({forn["razao"]}, CNPJ {forn["cnpj"]}): nome e CNPJ preenchidos pelo PDF')
        if tipo_da_rubrica(r) == 'sistema' and not (r.referencia or '').strip():
            esc = S.escopo_do_texto(t)
            if esc:
                r.referencia = esc
                msg.append(f'ferramentas de referência lidas da proposta ({len(esc.splitlines())} linhas): o plano dos outros sistemas será escolhido por elas')
    return '; '.join(msg) + '.'


def fornecedor_no_texto(texto):
    """Fornecedor de sistema conhecido que aparece no texto de uma proposta (pelo nome ou pela raiz do CNPJ), ou None."""
    from . import sistemas as S
    from .regras import norm
    t = norm(texto or '')
    digitos = re.sub(r'\D', '', texto or '')
    for f in S.FORNECEDORES:
        if not f.get('cnpj'):
            continue
        if norm(f['nome']) in t or norm(f['razao'] or '') in t or re.sub(r'\D', '', f['cnpj'])[:8] in digitos:
            return f
    return None


def identificar_cotacao(f, texto, produto=None):
    """Cotação de sistema que a OSC deixou sem o nome ou sem o CNPJ: preenche com o fornecedor que aparece na proposta em PDF (se for um
    dos conhecidos). Devolve o fornecedor usado, ou None. Nada que a OSC escreveu é trocado."""
    if f.nome and f.cnpj:
        return None
    forn = fornecedor_no_texto(texto)
    if not forn:
        return None
    f.nome = f.nome or forn['razao']
    f.cnpj = f.cnpj or forn['cnpj']
    f.plataforma = f.plataforma or forn['nome']
    return forn


def cotacao_da_osc(f, preco, produto=None):
    """Cotação que a OSC deixou (digitada ou anexada), e não a que a cotação automática pôs: fica onde está."""
    ev = f.evidencia
    return bool((preco or f.nome or f.cnpj or ev.arquivo or ev.url) and ev.origem != 'navegador')


async def pesquisar_sistema(pid, item, ctx, somente_k=None):
    """Rubrica de sistema (decisões da OSC de 27/09, 01/10 e 03/10/2026): 3 sistemas DIFERENTES com ferramentas parecidas. O que a OSC
    deixou numa cotação (proposta anexada, sistema digitado) FICA, na posição em que está; só as cotações em branco ou as que a cotação
    automática tinha posto são cotadas, pela página de preços do fornecedor (guardada em PDF, CNPJ ativo na base oficial), com o plano
    de acordo com as FERRAMENTAS DE REFERÊNCIA (a IA compara; a regra escolhe) — não o mais barato.
    somente_k: cota de novo só a cotação dessa posição, com outro fornecedor (as outras duas ficam como estão)."""
    from playwright.async_api import async_playwright
    from . import cnpj_base, sistemas as S
    from .modelo import fontes_do_subitem
    from .produtos import evidencia as EV
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    if not r.subitens:   # rubrica de sistema é um item só (o sistema, por mês): criado aqui, sem a OSC precisar cadastrar
        r.subitens = [Subitem(descricao=r.descricao or 'Sistema de gestão', qtd=1)]
    hoje = dt.date.today().isoformat()
    raiz = lambda c: re.sub(r'\D', '', c or '')[:8]

    identificadas = 0
    for s in r.subitens:   # o subitem passa a ter as suas 3 cotações; proposta anexada sem nome/CNPJ: preenche pelo que o PDF diz
        if len(s.fontes) != 3:
            s.fontes = ([f.model_copy(deep=True) for f in fontes_do_subitem(r, s)] + [Fonte(), Fonte(), Fonte()])[:3]
        s.precos = (list(s.precos or []) + [None, None, None])[:3]
        s.produtos = (list(s.produtos or []) + [None, None, None])[:3]
        for j, f in enumerate(s.fontes):
            if anexada(f) and not (f.nome and f.cnpj):
                forn = identificar_cotacao(f, texto_do_pdf(f.evidencia.arquivo))
                if forn:
                    identificadas += 1
                    s.produtos[j] = s.produtos[j] or f'{forn["nome"]} — proposta comercial em PDF'
                    ctx.aviso(f'Cotação {j + 1}: a proposta anexada é de {forn["nome"]} ({forn["razao"]}, CNPJ {forn["cnpj"]}); o nome e o CNPJ foram '
                              f'preenchidos pelo que está no PDF.')
    ref0 = r.referencia
    ref = (r.referencia or '').strip()
    if not ref:   # as ferramentas de referência vêm da proposta que a OSC anexou
        for f in [f for s in r.subitens for f in s.fontes if anexada(f)]:
            ref = S.escopo_do_texto(texto_do_pdf(f.evidencia.arquivo))
            if ref:
                r.referencia = ref; break
    if not ref:
        ctx.aviso('A rubrica não tem as ferramentas de referência: anexe a proposta de referência em PDF ou escreva as ferramentas na tela da '
                  'rubrica. Nesta rodada, o plano foi escolhido pela descrição do item.')
    if not (p.config.usar_ia and ia.disponivel()):
        ctx.aviso('A escolha do plano pelas ferramentas de referência precisa da IA (chave GEMINI_API_KEY e IA ligada na configuração). '
                  'Nenhum sistema foi cotado automaticamente; as cotações atuais ficaram como estavam.')
        ctx.progresso(100, 'Concluído')
        return dict(versao=None, cotados=0, ir_para=f'/p/{pid}/mat/{item}')
    lista = S.ferramentas(ref) or [s.descricao for s in r.subitens]

    def fica(s, j):
        """A cotação j do subitem fica como está? (a da OSC sempre; na nova cotação de uma posição só, todas as outras)"""
        if somente_k is not None:
            return j != somente_k
        return cotacao_da_osc(s.fontes[j], s.precos[j])

    def do_fornecedor(f, forn):
        return (raiz(f.cnpj) and raiz(f.cnpj) == raiz(forn['cnpj'])) or norm_(forn['nome']) in norm_(f'{f.nome} {f.plataforma or ""}')
    from .regras import norm as norm_
    presentes = [f for s in r.subitens for j, f in enumerate(s.fontes) if fica(s, j) or somente_k is not None]   # na posição só, nem o atual volta
    fornecedores = [f for f in S.com_preco_publico() if not any(do_fornecedor(x, f) for x in presentes)]
    if somente_k is None and all(cotacao_da_osc(s.fontes[j], s.precos[j]) for s in r.subitens for j in range(3)):
        v = db.salvar(pid, p, autor='sistema (pesquisa automática)', tarefa=ctx.id,
                      motivo=f'item {item}: fornecedor da proposta anexada identificado pelo PDF') if (identificadas or r.referencia != ref0) else None
        ctx.aviso('As 3 cotações foram deixadas por você (digitadas ou anexadas): nenhuma foi trocada. Para cotar uma delas de novo com outro sistema, '
                  'use "Cotar de novo só esta cotação", na tela da rubrica.')
        ctx.progresso(100, 'Concluído')
        return dict(versao=v, cotados=0, ir_para=f'/p/{pid}/mat/{item}')
    cotas = []
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        try:
            for n, f in enumerate(fornecedores):
                ctx.progresso(85 * n / max(1, len(fornecedores)), f'Página de preços de {f["nome"]}')
                base = cnpj_base.por_cnpj(f['cnpj'])
                if base is not None and base.get('situacao') not in (None, 'ATIVA'):
                    ctx.aviso(f'{f["nome"]}: CNPJ {f["cnpj"]} não está ATIVO na base da Receita; fica de fora.'); continue
                try:
                    pdf, info = await asyncio.wait_for(EV.pagina(br, f['precos'], f'PESQUISA DE PREÇO | {f["nome"]} ({f["razao"]}) | planos', completa=True), 240)
                except asyncio.TimeoutError:
                    ctx.fonte(f['nome'], 'falhou', 'a página de preços não respondeu a tempo'); continue
                pl = S.planos(info['texto'], a_partir=False)
                if not pdf or not pl or info['problema'] and 'preço' not in info['problema']:
                    ctx.fonte(f['nome'], 'falhou', info['problema'] or 'nenhum plano com preço mensal definido na página'); continue
                definidos = dict(pl)
                mapa = await asyncio.to_thread(ia.plano_do_sistema, lista, f['nome'], info['texto'],
                                               [dict(plano=nm, preco_mensal=_reais(v) if nm in definidos else f'a partir de {_reais(v)}')
                                                for nm, v in S.planos(info['texto'])], pid)
                esc = S.escolher_plano(mapa['ferramentas'], pl, lista) if mapa else None   # a IA só compara; quem escolhe é a regra fixa
                if not esc:
                    ctx.fonte(f['nome'], 'falhou', 'a IA não respondeu à comparação das ferramentas desta página com as de referência'); continue
                nome_plano, preco = esc['plano'], esc['preco']
                if not S.preco_no_texto(texto_do_pdf(conteudo=pdf), preco):
                    ctx.fonte(f['nome'], 'falhou', f'o preço do plano {nome_plano} ({_reais(preco)}) não aparece no PDF da página'); continue
                sha, rel = db.guardar_arquivo(pid, f'sistema_{f["chave"]}_item{item}.pdf', pdf)
                ev = Evidencia(arquivo=rel, sha256=sha, url=f['precos'], capturado_em=info['capturado_em'], origem='navegador')
                texto = (f'{f["nome"]} — plano {nome_plano} ({_reais(preco)}/mês): {esc["motivo"]}.'
                         + (f' {mapa["resumo"].rstrip(".")}.' if mapa.get('resumo') else '')
                         + (f' Tem: {"; ".join(esc["atende"])}.' if esc['atende'] else '')
                         + (f' Não tem: {"; ".join(esc["nao_atende"])}.' if esc['nao_atende'] and esc['atende'] else '')
                         + f' Página de preços do fornecedor em PDF; CNPJ: {f["origem"]}.' + (f' Atenção: {f["obs"]}.' if f.get('obs') else ''))
                cotas.append(dict(fonte=Fonte(nome=f['razao'], cnpj=f['cnpj'], data_pesquisa=hoje, plataforma=f['nome'], evidencia=ev), preco=preco,
                                  produto=f'{f["nome"]} — plano {nome_plano} ({_reais(preco)}/mês)', texto=texto, atende=esc['cobertura'], ordem=n))
                ctx.fonte(f['nome'], 'ok', f'plano {nome_plano}: {_reais(preco)}/mês ({esc["cobertura"]} de {len(lista)} ferramentas de referência)')
        finally:
            await br.close()
    cotas.sort(key=lambda c: (c['atende'] == 0, c['ordem']))   # primeiro quem tem ferramentas da referência; depois, a ordem de preferência
    mudou = 0
    for s in r.subitens:
        textos, raizes, fila = {}, set(), list(cotas)
        for j, f in enumerate(s.fontes):   # 1º: o que fica (o que a OSC deixou; ou, na nova cotação de uma posição só, as outras duas)
            if fica(s, j) and (s.precos[j] or f.nome or f.cnpj or f.evidencia.arquivo):
                raizes.add(raiz(f.cnpj))
                if cotacao_da_osc(f, s.precos[j]):
                    if anexada(f) and (not s.produtos[j] or s.produtos[j].endswith('(cotação anterior)')):
                        s.produtos[j] = f'{f.plataforma or f.nome or "Proposta"} — proposta comercial em PDF'
                    textos[j] = (f'{f.plataforma or f.nome or "cotação " + str(j + 1)}: ' + ('proposta em PDF anexada pela OSC' if anexada(f) else 'cotação informada pela OSC')
                                 + ('' if f.evidencia.url else ' (sem link)') + (f', {_reais(s.precos[j])}/mês' if s.precos[j] else ''))
        novas = 0
        for j in range(3):                 # 2º: as outras posições recebem as páginas de preços, plano pelas ferramentas de referência
            if fica(s, j) and (s.precos[j] or s.fontes[j].nome or s.fontes[j].cnpj or s.fontes[j].evidencia.arquivo):
                continue
            c = next((c for c in fila if raiz(c['fonte'].cnpj) not in raizes), None)
            if c is None:                  # não há outra página de preços: fica o que já estava nessa posição (se havia)
                continue
            fila.remove(c); raizes.add(raiz(c['fonte'].cnpj))
            s.fontes[j], s.precos[j], s.produtos[j] = c['fonte'], c['preco'], c['produto']
            textos[j] = c['texto']; novas += 1
        completas = sum(1 for j in range(3) if s.precos[j] and s.fontes[j].nome)
        if completas < 3:
            ctx.aviso(f'"{s.descricao}": {completas} de 3 cotações. Peça proposta a um destes (não publicam preço) e anexe o PDF na tela da rubrica: '
                      + '; '.join(f'{f["nome"]} ({f["contato"]})' for f in S.sob_consulta()))
        if not novas and not identificadas:
            continue
        s.eans = [None, None, None]
        if completas == 3:
            s.confirmacao = CONF_SISTEMA
        if textos:
            s.justificativa = ('3 sistemas diferentes com ferramentas parecidas; o plano de cada sistema é o que está de acordo com as ferramentas de '
                               'referência, não o mais barato. O que a OSC deixou numa cotação foi mantido. '
                               + ' | '.join(textos[j] for j in sorted(textos)))
        s.valor_plano = valor_do_sistema(s)   # o menor das 3 cotações
        mudou += 1
    v = None
    if mudou or r.referencia != ref0:
        v = db.salvar(pid, p, autor='sistema (pesquisa automática)', tarefa=ctx.id,
                      motivo=f'item {item}: sistemas cotados pelo plano de acordo com as ferramentas de referência ({len(cotas)} página(s) de preços)')
    ctx.progresso(100, 'Concluído')
    return dict(versao=v, cotados=len(cotas), ir_para=f'/p/{pid}/mat/{item}')


def corrigir_salarios_pela_pagina(p):
    """Pesquisas salariais já gravadas: se a página guardada (PDF) mostra um salário diferente do registrado (Catho: a faixa cadastrada
    2.001–3.000 × o salário exibido R$ 2.300), vale o da página, na mesma vaga. O valor mensal do plano só muda se passar do novo máximo.
    Devolve [(item, empresa, antes, depois)]."""
    from . import vagas as V
    from .calculo import mensal_maximo_rh
    mud = []
    for r in p.rubricas:
        if not isinstance(r, RubricaRH):
            continue
        antes = len(mud)
        for q in r.pesquisas:
            ev = q.evidencia
            if not (q.faixa_min and ev and ev.arquivo):
                continue
            achado = V.conferir_salario_pdf(caminho=db.caminho_absoluto(ev.arquivo), centavos=q.faixa_min)
            if isinstance(achado, tuple):
                mud.append((r.item, q.nome, q.faixa_min, achado[0]))
                q.faixa_min, q.faixa_max, q.valor = achado[0], achado[1], achado[0]
        if len(mud) > antes:
            maxm, _, _ = mensal_maximo_rh(r, p.config)
            if maxm is not None and (r.valor_mensal_plano is None or r.valor_mensal_plano > maxm):
                r.valor_mensal_plano = maxm
    return mud


def rh_pronto(r):
    """Cargo com as 3 pesquisas completas e ainda válidas pelas regras atuais: CNPJ, salário mensal definido (não 'a combinar',
    nem faixa genérica) e a página da vaga guardada em PDF."""
    from . import vagas as V
    if len(r.pesquisas) != 3 or titulos_misturados(r):
        return False
    for q in r.pesquisas:
        ev = q.evidencia
        if not (q.cnpj and q.faixa_min and ev and ev.arquivo):
            return False
        if q.faixa_max and q.faixa_max > 5 * q.faixa_min:
            return False
        if V.pdf_a_combinar(db.caminho_absoluto(ev.arquivo), q.faixa_min):
            return False
        if V.conferir_salario_pdf(caminho=db.caminho_absoluto(ev.arquivo), centavos=q.faixa_min) not in (True, None):
            return False   # o salário da pesquisa não é o que a página guardada mostra (ex.: Catho: faixa cadastrada × salário exibido)
        if V.empresa_oculta(caminho=db.caminho_absoluto(ev.arquivo)):
            return False   # a página esconde as informações da empresa (Catho sem login): a SEJC pede essas informações visíveis
        if ev.origem != 'pdf' and V.pdf_nao_e_a_vaga(db.caminho_absoluto(ev.arquivo)):
            return False   # o PDF guardado é a lista de vagas do site (o anúncio tinha sido encerrado), não a página da vaga
    return True


AGUARDA_DECISAO = 'aguardando a sua decisão'   # como começa a justificativa do item que a pesquisa não achou igual e não substituiu
NAO_ACHADO = 'não achado igual em 3 lojas'    # idem, quando a pesquisa também não tem nenhuma opção de substituição para mostrar
PERTO, FALTA_A_TERCEIRA = ' O mais perto do pedido: ', ' — falta a 3ª loja.'   # o produto que existe, como pedido, em só 2 lojas
DUAS_LOJAS = 'duas pesquisas feitas pelo sistema'   # como começa a justificativa do item com 2 lojas achadas e a 3ª pesquisa por conta da OSC
_SUFIXO_2_LOJAS = ' |em 2 lojas|'                  # no banco de produtos: os produtos achados, como pedidos, em só 2 lojas (guardados à parte das opções)


def chave_das_duas_lojas(pedido):
    return pedido + _SUFIXO_2_LOJAS


def em_duas_lojas(pid, item, pedido):
    """Os produtos que a última pesquisa achou, como pedidos, em só 2 lojas: [dict(produto, ofertas=[2])] (lista vazia se não há)."""
    return (db.produtos_do_banco(pid, item).get(chave_das_duas_lojas(pedido)) or {}).get('opcoes') or []


async def usar_duas_lojas(pid, item, desc, idx, ctx):
    """Pedido da OSC (08/10/2026): o item existe, como pedido, em só 2 lojas — ela aceita essas 2 e completa a 3ª à mão (por exemplo, com uma
    loja que o sistema não consegue ler). O sistema guarda o comprovante das 2 e grava as 2 pesquisas; a 3ª fica em branco, para ela preencher
    em "Detalhes e comprovante". Nada é inventado: o item só fica pronto quando a 3ª pesquisa for preenchida e comprovada por ela."""
    from playwright.async_api import async_playwright
    achados = em_duas_lojas(pid, item, desc)
    if idx >= len(achados):
        raise ValueError('o produto em 2 lojas não está mais guardado: pesquise o item de novo')
    q = achados[idx]
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    s = next((x for x in r.subitens if pedido_do_subitem(x) == desc), None)
    if s is None:
        raise ValueError(f'o item "{desc}" não está mais na rubrica')
    cep, hoje = _cep(p), dt.date.today().isoformat()
    ctx.progresso(5, 'Guardando os comprovantes das 2 lojas')
    comp = {}
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        try:
            for n, x in enumerate(q['ofertas']):
                ctx.progresso(10 + 40 * n, f'Comprovante de {L.LOJAS[x["loja"]]["nome"]}')
                comp.update(await _comprovar(br, pid, item, x['loja'], [(dict(desc=desc, qtd=s.qtd), x)], cep, ctx, sufixo=f'_{_nome_arquivo(desc)}_2lojas{n + 1}'))
        finally:
            await br.close()
    ruins = [(x, comp.get((x['loja'], x['url']), {})) for x in q['ofertas'] if not comp.get((x['loja'], x['url']), {}).get('ev') or comp[(x['loja'], x['url'])].get('problema')]
    volta = f'/p/{pid}/mat/{item}#sub{r.subitens.index(s)}'
    if ruins:
        ctx.aviso('Não foi possível guardar o comprovante de ' + '; '.join(f'{L.LOJAS[x["loja"]]["nome"]} ({c.get("problema") or "sem PDF"})' for x, c in ruins)
                  + '. O item ficou como estava: pesquise de novo ou preencha as pesquisas à mão.')
        ctx.progresso(100, 'Concluído')
        return dict(versao=None, ir_para=volta)
    p, _ = db.carregar(pid)   # guardar os comprovantes demora: relê o projeto
    r = _rubrica(p, item)
    s = next((x for x in r.subitens if pedido_do_subitem(x) == desc), None)
    if s is None:
        raise ValueError(f'o item "{desc}" não está mais na rubrica')
    ofs = sorted(q['ofertas'], key=lambda x: comp[(x['loja'], x['url'])].get('preco') or x['preco'])
    precos = [comp[(x['loja'], x['url'])].get('preco') or x['preco'] for x in ofs]
    s.fontes = [_fonte_loja(x['loja'], hoje, comp[(x['loja'], x['url'])]['ev']) for x in ofs] + [Fonte()]
    s.precos = precos + [None]
    s.produtos = [x.get('titulo') or x['nome'] for x in ofs] + [None]
    s.eans = [x.get('ean') for x in ofs] + [None]
    s.nivel, s.valor_plano = 0, None
    mesmos = len({(x.get('ean') or '').lstrip('0') for x in ofs if x.get('ean')}) == 1 and all(x.get('ean') for x in ofs)
    s.confirmacao = 'EAN em 2 lojas; 3ª pesquisa à mão' if mesmos else 'descrição em 2 lojas; 3ª pesquisa à mão'
    s.justificativa = (f'{DUAS_LOJAS}, por escolha da OSC em {dt.date.today():%d/%m/%Y}: o produto pedido só foi achado em 2 lojas ('
                       + ' e '.join(L.LOJAS[x['loja']]['nome'] for x in ofs) + '); a 3ª pesquisa é preenchida à mão pela OSC, com o MESMO produto, em "Detalhes e comprovante"')
    ver = db.salvar(pid, p, autor='sistema (pesquisa automática)', tarefa=ctx.id,
                    motivo=f'item {item}: "{desc}" com 2 pesquisas do sistema ({", ".join(L.LOJAS[x["loja"]]["nome"] for x in ofs)}); a 3ª fica para a OSC preencher à mão')
    ctx.aviso(f'"{desc}": 2 pesquisas gravadas, com comprovante ({", ".join(L.LOJAS[x["loja"]]["nome"] + " " + _reais(pr) for x, pr in zip(ofs, precos))}). '
              'Falta a 3ª: abra "Pesquisa 3 → Detalhes e comprovante", informe a empresa, o CNPJ e o preço do MESMO produto em outra loja e anexe o PDF.')
    ctx.progresso(100, 'Concluído')
    return dict(versao=ver, ir_para=volta)


def aguarda_decisao(s, opcoes):
    """O item está à espera de a OSC decidir? A última pesquisa dele não achou o item pedido igual em 3 lojas (as opções guardadas são todas
    de substituição) e ele continua sem as 3 pesquisas. Item já substituído (pela pesquisa antiga ou por escolha da OSC) não está à espera:
    a tela dele mostra o que está orçado no lugar do pedido e o botão de desfazer."""
    opcoes = opcoes or []
    return bool(opcoes) and not any(cesta.atende_o_pedido(o) for o in opcoes) and not subitem_pronto(s)


def nao_achado(s):
    """A última pesquisa do item não achou o item pedido igual em 3 lojas, nem opção de substituição, e ele continua sem as 3 pesquisas."""
    return (s.justificativa or '').startswith(NAO_ACHADO) and not subitem_pronto(s)


def perto_do_pedido(s):
    """O trecho da justificativa que diz o que existe, como foi pedido, em só 2 lojas ('' quando a pesquisa não achou nada assim)."""
    j = s.justificativa or ''
    return j.split(PERTO, 1)[1].split(FALTA_A_TERCEIRA)[0] if PERTO in j and not subitem_pronto(s) else ''


def texto_do_quase(quase):
    """'"Papel Sulfite X A4 500 folhas" em 2 lojas (Loja A R$ 28,22 e Loja B R$ 32,90)': o que existe, como foi pedido, em só 2 lojas."""
    def preco(c):
        return f'R$ {c / 100:,.2f}'.replace(',', '#').replace('.', ',').replace('#', '.')
    return '; '.join(f'"{q["produto"][:90]}" em 2 lojas (' + ' e '.join(f'{L.LOJAS[x["loja"]]["nome"] if x["loja"] in L.LOJAS else x["loja"]} {preco(x["preco"])}'
                                                                        for x in q['ofertas']) + ')' for q in quase or [])


def desfazer_substituicao(s):
    """A OSC não quer a substituição: o item volta a ser o que ela pediu, sem pesquisas (para pesquisar de novo, mudar o pedido ou preencher à mão)."""
    era = descricao_completa(s)
    voltar_ao_pedido(s)
    s.justificativa = f'substituição desfeita pela OSC (estava: {era}): o item voltou ao pedido original, sem pesquisas'
    return era


def pedidos_mais_largos(s):
    """2ª etapa da pesquisa de um item (pedido da OSC, 08/10/2026): quando o item não existe igual em 3 lojas, procura-se o MESMO item pedido
    de forma mais larga — sem a marca, sem a especificação (tamanho, cor, tipo) e sem as duas —, do mais perto do pedido para o mais longe.
    Devolve [(pedido mais largo, [o que saiu do pedido])]. A marca escrita dentro da descrição e a medida no fim dela ("Suco de Uva 1L")
    contam como marca e especificação. O que for achado assim é OPÇÃO para a OSC: nada é trocado sem ela escolher."""
    from .modelo import _juntar
    if s.descricao_original:
        desc, marca, esp = s.descricao_original, s.marca_original, (s.especificacao if s.especificacao_original is None else s.especificacao_original)
    else:
        desc, marca, esp = s.descricao, s.marca, s.especificacao
    desc, marca, esp = T.arrumar_item(desc, marca, esp)
    if not esp:
        nome, medida = T.separar_medida(desc)
        if medida and ID.palavras_tipo(nome):
            desc, esp = nome, medida
    vistos, out = {ID.sa(pedido_do_subitem(s))}, []
    for novo, saiu in ((_juntar(desc, None, esp), [f'a marca {marca}'] if marca else None),
                       (_juntar(desc, marca, None), [f'a especificação {esp}'] if esp else None),
                       (desc, [f'a marca {marca}', f'a especificação {esp}'] if marca and esp else None)):
        if saiu and ID.sa(novo) not in vistos and ID.palavras_tipo(novo):
            vistos.add(ID.sa(novo)); out.append((novo, saiu))
    return out


class _Parte:
    """O andamento de uma etapa dentro do andamento da tarefa (a 2ª etapa da pesquisa ocupa só o fim da barra)."""

    def __init__(self, ctx, ini, fim):
        self.ctx, self.ini, self.fim, self.id = ctx, ini, fim, getattr(ctx, 'id', 0)

    def progresso(self, pct, etapa=None):
        self.ctx.progresso(self.ini + (self.fim - self.ini) * pct / 100, etapa)

    def etapa(self, t): self.ctx.etapa(t)
    def fonte(self, *a, **k): self.ctx.fonte(*a, **k)
    def aviso(self, m): self.ctx.aviso(m)


async def _etapa_mais_larga(res, subs, lojas, p, pid, ctx, outros, usados):
    """Acrescenta a res['opcoes'] de cada item que NÃO foi achado como pedido as opções "o mesmo item, de outra marca ou especificação":
    o mesmo produto nas 3 lojas, achado com o pedido mais largo (pedidos_mais_largos). Devolve quantos itens ganharam opções."""
    largos = {}
    for s in subs:
        pedido = pedido_do_subitem(s)
        if any(cesta.atende_o_pedido(o) for o in res['opcoes'].get(pedido, [])):
            continue
        for novo, saiu in pedidos_mais_largos(s):
            largos.setdefault(novo, dict(familia=s.familia, alvos=[]))['alvos'].append((pedido, saiu))
    if not largos:
        return 0
    ctx.etapa(f'{len({a[0] for v in largos.values() for a in v["alvos"]})} item(ns) não achado(s) como pedido(s): procurando o mesmo item de outra marca ou especificação')
    try:
        res2 = await cesta.pesquisar([dict(desc=d, qtd=1, familia=v['familia'], valor_ref=None) for d, v in largos.items()], lojas, _cep(p), _Parte(ctx, 92, 99),
                                     'por_item', p.config.usar_ia, pid, None, (), False, outros=list(outros) + [x[0] for v in largos.values() for x in v['alvos']],
                                     usados=usados)
    except Exception as e:   # a 2ª etapa é um acréscimo: se falhar, vale o resultado da 1ª
        ctx.aviso(f'A procura pelo mesmo item de outra marca ou especificação não terminou ({type(e).__name__}); valem as opções da primeira busca.')
        return 0
    ganharam = set()
    for novo, v in largos.items():
        for o in res2['opcoes'].get(novo, []):
            if o.get('nivel') or o.get('misto'):   # só o que É o pedido mais largo: o mesmo produto nas 3 lojas
                continue
            chave = tuple(sorted((x['loja'], x['url']) for x in o['ofertas']))
            for pedido, saiu in v['alvos']:
                ja = {tuple(sorted((x['loja'], x['url']) for x in y['ofertas'])) for y in res['opcoes'].get(pedido, [])}
                if chave not in ja and sum(1 for y in res['opcoes'].get(pedido, []) if y.get('mais_largo')) < 4:
                    res['opcoes'].setdefault(pedido, []).append(dict(o, nivel=1, perdidos=list(saiu), mais_largo=dict(pedido=novo, sem=list(saiu)),
                                                                     distancia=1.0 + 0.5 * len(saiu)))
                    ganharam.add(pedido)
    return len(ganharam)


async def pesquisar_rubrica(pid, item, ctx, somente=None, sem_lojas=(), respeitar_teto=True):
    """somente: pedidos dos subitens a pesquisar (os outros ficam como estão; o teto desconta o valor deles).
    sem_lojas: lojas que não entram nesta pesquisa (nova pesquisa de um item "em outras lojas").
    respeitar_teto=False: nova pesquisa de um item só — o item não é retirado para caber no teto da rubrica."""
    p, _ = db.carregar(pid)
    uso_ia = ia.marca()   # para a proposta dizer se a IA foi usada nesta pesquisa (e quantas perguntas ficaram sem resposta)
    r = _rubrica(p, item)
    subs = [s for s in r.subitens if somente is None or pedido_do_subitem(s) in somente]
    itens = [dict(desc=pedido_do_subitem(s), qtd=s.qtd, familia=s.familia, valor_ref=_valor_ref(s)) for s in subs]
    if not itens:
        raise ValueError('a rubrica ainda não tem itens: cadastre ao menos um item e salve antes de pesquisar')
    if L.setor_da_rubrica(r.descricao) == 'servico':
        raise ValueError(f'a rubrica "{r.descricao}" é de serviço, não de produtos de loja: o orçamento é feito com 3 fornecedores do serviço')
    lojas = [lj for lj in lojas_da_rubrica(p, r) if lj not in set(sem_lojas or ())]
    if len(lojas) < 3:
        raise ValueError(f'sobram só {len(lojas)} loja(s) para pesquisar (as outras estão desligadas na configuração ou foram excluídas desta pesquisa)')
    ctx.etapa(f'Pesquisando {len(itens)} itens em {len(lojas)} lojas ({ "cada item nas suas 3 lojas" if p.config.modo_cesta == "por_item" else "um trio para a rubrica" })')
    resto = [s for s in r.subitens if s not in subs and not item_repetido(r, s)]   # os itens que NÃO estão nesta pesquisa: nada pode repetir um deles
    outros, usados = descricoes_do_item(resto), produtos_em_uso(resto)
    categoria = p.config.trocar_pela_categoria
    res = await cesta.pesquisar(itens, lojas, _cep(p), ctx, p.config.modo_cesta, p.config.usar_ia, pid, L.setor_da_rubrica(r.descricao) if categoria else None,
                                r.extras if categoria else (), False,   # nunca marcas diferentes: as 3 lojas têm de ter exatamente o mesmo produto
                                outros=outros, usados=usados)
    # 2ª etapa: o que não foi achado como pedido é procurado de forma mais larga (outra marca, outra especificação) — vira opção, nunca troca
    await _etapa_mais_larga(res, subs, lojas, p, pid, ctx, outros, usados)
    ext = None
    if r.teto_mensal and r.extras:
        ctx.etapa('Pesquisando os itens extras da rubrica (para o caso de sobrar muito do teto)')
        ext = await cesta.pesquisar([dict(desc=d, qtd=1) for d in r.extras], lojas if not res['trio'] else res['trio'], _cep(p), None,
                                    'por_item', p.config.usar_ia, pid)
    # teto da rubrica: o otimizador escolhe, entre as opções válidas de cada item, a que cabe (e o valor do plano)
    usados = {}
    for d, o in res['escolha'].items():
        if o:
            for x in o['ofertas']:
                usados[(x['loja'], x['url'])] = d
    opc_itens, todas = [], {}
    for it in itens:
        ops = [o for o in res['opcoes'].get(it['desc'], []) if all(usados.get((x['loja'], x['url']), it['desc']) == it['desc'] for x in o['ofertas'])]
        # o item como foi pedido primeiro; depois, do mais perto do pedido para o mais longe (o mesmo item de outra marca antes do item parecido)
        ops.sort(key=lambda o: (not cesta.atende_o_pedido(o), o.get('nivel') or 0, not o.get('mais_largo'), o.get('distancia') or 0))
        esc = res['escolha'].get(it['desc'])
        if esc and esc in ops and cesta.atende_o_pedido(esc):  # a escolha do motor vem primeiro
            ops.remove(esc); ops.insert(0, esc)
        todas[it['desc']] = [dict(o, precos=_precos(o), atende=cesta.atende_o_pedido(o)) for o in ops]
        # O SISTEMA NUNCA SUBSTITUI SOZINHO (decisão da OSC, 06/10/2026): só entra na proposta o item achado COMO FOI PEDIDO, o mesmo produto
        # nas 3 lojas. O resto (parecido, relacionado, da categoria, códigos de barras diferentes) fica guardado como opção para ela decidir.
        opc_itens.append(dict(desc=it['desc'], qtd=it['qtd'], opcoes=[o for o in todas[it['desc']] if o['atende']]))
    opc_extras = [dict(desc=d, qtd=1, opcoes=[dict(o, precos=_precos(o)) for o in (ext['opcoes'].get(d) or [])[:2] if cesta.atende_o_pedido(o)])
                  for d in (r.extras if ext else [])]
    for d, ops in todas.items():   # banco de produtos: TODAS as opções ficam guardadas — as do pedido, para trocar de produto; as outras, para decidir
        db.produtos_guardar(pid, item, d, ops)
        # e, à parte, os produtos achados COMO PEDIDOS em só 2 lojas (para a OSC poder usar as 2 e completar a 3ª à mão); nada, se o item foi achado
        db.produtos_guardar(pid, item, chave_das_duas_lojas(d), [] if any(o['atende'] for o in ops) else (res.get('quase') or {}).get(d, []))
    if any(ops and not any(o['atende'] for o in ops) for ops in todas.values()):
        opc_extras = []   # há item à espera de decisão: a "sobra" do teto é só aparente, então nenhum item extra é acrescentado agora
    teto_r = r.teto_mensal if respeitar_teto else None
    if teto_r and somente is not None:   # os subitens que não foram pesquisados continuam com o valor deles
        teto_r = max(0, teto_r - sum((s.valor_plano or 0) * s.qtd for s in r.subitens if s not in subs))
    t = teto.otimizar(opc_itens, teto_r, opc_extras, p.config.folga_teto, p.config.valores_defensaveis)
    linhas = []
    for l in t.get('linhas', []):
        fonte = opc_itens if l['acao'] != 'ACRESCENTADO' else opc_extras
        it = next(x for x in fonte if x['desc'] == l['desc'])
        o = it['opcoes'][l['opcao']] if l.get('opcao') is not None and it['opcoes'] else None
        sem = l['acao'] == 'RETIRADO' and not it['opcoes'] and l['acao'] != 'ACRESCENTADO' and fonte is opc_itens   # o item não foi achado como pedido
        # só conta o que a IA recusou DO ITEM PEDIDO: o trio de um produto da categoria (uma troca) recusado não explica nada sobre o item
        rej = [x for x in res.get('rejeitadas_ia', {}).get(l['desc'], []) if not x.get('nivel')] if sem else []
        subst = [x for x in todas.get(l['desc'], []) if not x['atende']] if sem else []
        quase = (res.get('quase') or {}).get(l['desc'], []) if sem else []
        perto = f'{PERTO}{texto_do_quase(quase)}{FALTA_A_TERCEIRA}' if quase else ''
        if subst:   # o item pedido não foi achado igual em 3 lojas: NADA é substituído; as opções ficam para a OSC decidir na tela do item
            l = dict(l, decidir=len(subst), reprovadas_ia=rej, quase=quase,
                     motivo=f'{AGUARDA_DECISAO}: o item pedido não foi achado igual em 3 lojas. Nada foi substituído; há {len(subst)} '
                            f'opção(ões) de substituição para você escolher na tela do item.{perto}')
        elif sem:   # nem o item, nem opção de substituição: a OSC muda o pedido e pesquisa de novo, ou preenche à mão
            l = dict(l, sem_opcao=True, reprovadas_ia=rej, quase=quase,
                     motivo=f'{NAO_ACHADO}: o sistema não encontrou o mesmo produto, como foi pedido, em 3 lojas de empresas diferentes, com estoque '
                            f'e entrega no CEP do projeto. Nada foi substituído.{perto}'
                            + (f' {len(rej)} conjunto(s) de 3 anúncios foram descartados porque a IA viu produtos diferentes ({rej[0]["motivo"]}).' if rej else '')
                            + ' Mude a descrição, a marca ou a especificação e pesquise de novo, ou preencha as 3 pesquisas à mão.')
        alternativas = [x for x in it['opcoes'] if x is not o][:3] if l['acao'] == 'mantido' else []
        linhas.append(dict(l, opcao_dados=o, alternativas=alternativas))
    ctx.progresso(100, 'Proposta pronta')
    return dict(pid=pid, item=item, modo=res['modo'], trio=res['trio'], lojas=lojas, teto=teto_r, status_teto=t.get('status'), somente=somente,
                entendido=res.get('entendido') or {},
                total=t.get('total'), sobra=t.get('sobra'), linhas=linhas, lojas_incompletas=res['lojas_incompletas'],
                ia=dict(ia.desde(uso_ia), ligada=bool(p.config.usar_ia), chave=ia.disponivel()),
                buscas=res['buscas'], falhas=res['falhas'], ir_para=f'/p/{pid}/mat/{item}/proposta/{ctx.id}')


# ------------------------------------------------------------------ proposta → comprovantes e nova versão
def _fonte_loja(loja, data, ev):
    cnpj, razao, origem = L.CNPJ_LOJAS.get(loja, ('', L.LOJAS[loja]['nome'], ''))
    return Fonte(nome=razao, cnpj=cnpj, data_pesquisa=data, plataforma=L.LOJAS[loja]['nome'], evidencia=ev)


def descricao_do_produto(o):
    """Descrição do subitem quando houve troca (R16: a descrição do plano deve ser a do que foi orçado)."""
    x = next((x for x in o['ofertas'] if x.get('ean')), o['ofertas'][0])
    nome = re.sub(r'\s*[-|–]\s*(unidade|un|und)\b.*$', '', x.get('titulo') or x['nome'], flags=re.I)
    return re.sub(r'\s+', ' ', nome).strip()


separar_medida = T.separar_medida   # ('Pão de Forma Artesano Pullman Pacote', '500g'): a medida do fim do nome, já com a unidade escrita certo


def marca_do_produto(o):
    """Marca do produto escolhido, escrita como nos anúncios, quando é a mesma nas 3 lojas (senão None)."""
    marcas = {ID.marca_de(x) for x in o['ofertas']}
    if len(marcas) != 1 or None in marcas:
        return None
    m = marcas.pop(); n = len(m.split())
    for x in o['ofertas']:
        toks = re.findall(r"[\w'’&.\-]+", x.get('titulo') or x['nome'])
        for i in range(len(toks) - n + 1):
            cand = ' '.join(toks[i:i + n])
            if ID._sem_apostrofo(ID.sa(cand)).strip('.-') == m:
                return cand.strip('.-').title() if cand.isupper() or cand.islower() else cand.strip('.-')
    return m.title()


def campos_do_produto(s, o, pid=None, item=None, pedido=None):
    """Depois da pesquisa, a descrição, a marca e a especificação do item passam a dizer o que foi orçado (R16):
    - produto TROCADO (parecido, relacionado, da categoria): a descrição é o NOME SIMPLES do produto achado — sem marca, linha, embalagem nem
      medida ("Manteiga com Sal", "Pão de Forma"; pedido da OSC, 03/10/2026) —, a especificação é a medida dele e a marca é a dele; o que a
      OSC tinha escrito fica guardado como pedido original;
    - produto como pedido: descrição e especificação ficam; a marca, se estava em branco, é preenchida com a das 3 lojas."""
    marca = marca_do_produto(o)
    titulos = [x.get('titulo') or x['nome'] for x in o['ofertas']]
    if o['nivel']:
        if not s.descricao_original:
            s.descricao_original, s.marca_original, s.especificacao_original = s.descricao, s.marca or '', s.especificacao or ''
        elif s.especificacao_original is None:   # item trocado antes de 03/10/2026: a especificação guardada ainda era a pedida
            s.marca_original, s.especificacao_original = s.marca or '', s.especificacao or ''
        if o.get('misto'):
            s.descricao, s.marca, s.especificacao = (o.get('substituto') or s.descricao), None, None
        else:
            base = o.get('substituto') if o['nivel'] == 3 and o.get('substituto') else s.descricao_original   # troca pela categoria: o tipo é o do catálogo
            s.descricao = T.nome_simples(titulos, separar_medida(base)[0] if base else None, marca, [x.get('marca') for x in o['ofertas']])
            s.especificacao = T.especificacao_do_produto(titulos, s.descricao) or separar_medida(descricao_do_produto(o))[1]
            s.marca = marca
    else:
        if marca and not s.marca:
            s.marca = marca
        s.especificacao = T.formatar_medidas(s.especificacao)
        if pid is not None and pedido and pedido_do_subitem(s) != pedido:   # a chave do item mudou (ganhou a marca): o banco de produtos acompanha
            migrar_banco(pid, [(item, pedido, pedido_do_subitem(s))])


def migrar_banco(pid, mudancas):
    """O pedido (chave) de um item mudou de texto: as opções guardadas no banco de produtos acompanham. mudancas: [(item, antes, depois)]."""
    with db.conectar() as c:
        for item, antes, depois in mudancas:
            if antes != depois:
                c.execute('UPDATE OR REPLACE produto_banco SET descricao=? WHERE projeto_id=? AND item=? AND descricao=?', (depois, pid, item, antes))


def sugestoes_conferidas(r, bruto, limite=20):
    """As sugestões de itens da IA que o sistema aceita mostrar: nome simples e sem marca (a marca que vier é tirada), quantidade inteira de 1 a
    999, sem repetir o que a rubrica já tem nem umas às outras. A IA não sugere preço — e, se sugerir, ele é ignorado: preço só vem de pesquisa."""
    visto = {ID.sa(descricao_completa(s)) for s in r.subitens} | {ID.sa(s.descricao) for s in r.subitens}
    out = []
    for x in bruto or []:
        if not isinstance(x, dict):
            continue
        desc = re.sub(r'\s+', ' ', str(x.get('descricao') or '')).strip(' .;,')
        esp = re.sub(r'\s+', ' ', str(x.get('especificacao') or '')).strip(' .;,')
        q = x.get('quantidade')
        if (isinstance(q, float) and q.is_integer()) or (isinstance(q, str) and q.strip().isdigit()):
            q = int(q)
        if not desc or len(desc) > 80 or len(esp) > 60 or not isinstance(q, int) or isinstance(q, bool) or not 1 <= q <= 999:
            continue
        desc, _, esp = T.arrumar_item(desc, None, esp)   # marca sugerida não entra: a marca é a que a pesquisa achar nas 3 lojas
        chave = ID.sa(f'{desc} {esp or ""}'.strip())
        if not desc or chave in visto or ID.sa(desc) in visto:
            continue
        visto |= {chave, ID.sa(desc)}
        out.append(dict(descricao=T._titulo(desc.split()), especificacao=esp or '', quantidade=q, motivo=re.sub(r'\s+', ' ', str(x.get('motivo') or '')).strip()[:240]))
        if len(out) >= limite:
            break
    return out


def arrumar_descricoes(p):
    """Itens gravados antes de 03/10/2026 com a descrição do anúncio ("Manteiga de Primeira Qualidade com Sal Aviação Pote") ou com a unidade
    escrita errado ("1l"): a descrição passa a ser o nome simples do produto, sem marca; a marca vai para o campo Marca; a medida, para a
    Especificação, com as letras certas (1L, 500mL, 1kg). O pedido original não muda. Os pontos já marcados como revisados acompanham o
    novo nome. Devolve (quantos itens mudaram, [(item, pedido antes, pedido depois)] para o banco de produtos)."""
    n, chaves = 0, []
    for r in p.rubricas:
        if isinstance(r, RubricaRH) or tipo_da_rubrica(r) in ('sistema', 'servico'):
            continue
        for s in r.subitens:
            antes, chave = (s.descricao, s.marca, s.especificacao), pedido_do_subitem(s)
            trocado = bool(s.descricao_original)
            if s.especificacao:
                s.especificacao = T.formatar_medidas(s.especificacao)
            s.marca = T.fabricante_da_linha(s.marca, s.produtos or []) or s.marca   # "Evolution" (linha) -> "Bic" (o fabricante dos 3 anúncios)
            if T.precisa_arrumar(s.descricao, s.marca, trocado) and not (trocado and produtos_diferentes(s)):
                titulos = [x for x in (s.produtos or []) if x]
                do_anuncio = any(ID.sa(separar_medida(t)[0]).startswith(ID.sa(s.descricao)) or ID.sa(t).startswith(ID.sa(s.descricao)) for t in titulos)
                if len(titulos) >= 2 and (trocado or do_anuncio):
                    if not s.marca:
                        s.marca = marca_do_produto(dict(ofertas=[dict(nome=x) for x in titulos]))
                    s.descricao = T.nome_simples(titulos, separar_medida(s.descricao_original)[0] if trocado else None, s.marca) or s.descricao
                    if trocado:
                        s.especificacao = T.especificacao_do_produto(titulos, s.descricao) or s.especificacao
                else:
                    s.descricao, s.marca, s.especificacao = T.arrumar_item(s.descricao, s.marca, s.especificacao)
            if (s.descricao, s.marca, s.especificacao) == antes:
                continue
            n += 1
            if antes[0] != s.descricao:   # "revisado" é guardado pelo nome do item: acompanha o nome novo
                velho, novo = f'Item {r.item} – {r.descricao} / {antes[0]}', f'Item {r.item} – {r.descricao} / {s.descricao}'
                for k in [k for k in p.revisados if k.split('|', 2)[1:2] == [velho]]:
                    regra, _, resto = (k.split('|', 2) + [''])[:3]
                    p.revisados[f'{regra}|{novo}|{resto}'] = p.revisados.pop(k)
            if pedido_do_subitem(s) != chave:
                chaves.append((r.item, chave, pedido_do_subitem(s)))
    return n, chaves


def acertar_trocados(p):
    """Itens que a pesquisa trocou ANTES de 03/10/2026 ficaram com a descrição do produto achado e a especificação antiga (ex.: "Pão de
    Forma Artesano Pullman Pacote 500g" com especificação "480g"). Aqui a especificação passa a ser a medida do produto (e sai do texto da
    descrição), a marca é preenchida e o que a OSC tinha pedido fica guardado como pedido original. Devolve quantos itens mudaram."""
    n = 0
    for r in p.rubricas:
        if isinstance(r, RubricaRH) or tipo_da_rubrica(r) in ('sistema', 'servico'):
            continue
        for s in r.subitens:
            if not (s.nivel and s.descricao_original and s.especificacao_original is None) or produtos_diferentes(s):
                continue
            s.especificacao_original, s.marca_original = s.especificacao or '', s.marca or ''
            s.descricao, s.especificacao = separar_medida(s.descricao)
            nomes = [x for x in (s.produtos or []) if x]
            if len(nomes) == 3 and not s.marca:
                s.marca = marca_do_produto(dict(ofertas=[dict(nome=x) for x in nomes]))
            n += 1
    return n


LIMITE_QTD = re.compile(r'no máximo (\d+) unidade|quantidade no carrinho ficou (?=\d)(\d+)')


def _nome_arquivo(t):
    return re.sub(r'[^A-Za-z0-9]+', '_', t)[:30]


async def _carrinho_da_loja(br, pid, item, loja, pares, cep, ctx, sufixo=''):
    """Comprovante pelo CARRINHO real da loja (lojas VTEX e Tenda), com as quantidades do plano e o CEP do projeto. Devolve
    {(loja, url): dict(ev, preco, problema)} ou None se a loja não tem carrinho ou o carrinho falhou."""
    from .produtos import evidencia as EV
    out = {}
    plat = L.LOJAS[loja]['plataforma']
    if plat == 'vtex' and all(x.get('sku') for _, x in pares):
        try:
            carrinhos, indisp = await asyncio.wait_for(EV.carrinhos_vtex(br, loja, [dict(sku=x['sku'], seller=x['seller'], qtd=l['qtd'], nome=x['nome'])
                                                                                    for l, x in pares], cep), 300)
            for n, cr in enumerate(carrinhos, 1):
                ev = None
                if cr['pdf']:
                    sha, rel = db.guardar_arquivo(pid, f'carrinho_{loja}_item{item}{sufixo}' + (f'_{n}' if len(carrinhos) > 1 else '') + '.pdf', cr['pdf'])
                    ev = Evidencia(arquivo=rel, sha256=sha, url=cr['url'], capturado_em=cr['capturado_em'], origem='api')
                for l, x in pares:
                    if x['sku'] in cr['skus']:
                        if ev:   # o endereço guardado é o da PÁGINA DO PRODUTO (o do carrinho abre um carrinho vazio para quem clica)
                            ev = ev.model_copy(update=dict(url=x['url']))
                        prob = cr['problema'] or (_sem_preco(cr['pdf'], cr['precos'].get(x['sku']) or x['preco']) if ev else 'sem PDF do carrinho')
                        out[(loja, x['url'])] = dict(ev=ev, preco=cr['precos'].get(x['sku']), problema=prob, carrinho=True)
            for l, x in pares:
                if x['sku'] in indisp:
                    out[(loja, x['url'])] = dict(ev=None, preco=None, problema=f'indisponível no carrinho da loja ({indisp[x["sku"]]})', carrinho=True)
            if len(carrinhos) > 1:
                ctx.aviso(f'{L.LOJAS[loja]["nome"]}: a loja não junta todos os itens num carrinho só; foram feitos {len(carrinhos)} carrinhos.')
            return out
        except Exception as e:
            ctx.fonte(L.LOJAS[loja]['nome'], 'repetindo', f'carrinho: {type(e).__name__}')
            return None
    if plat == 'tenda':
        try:
            itens_t = [dict(nome=x['nome'], url=x['url'], qtd=l['qtd'], preco=x['preco']) for l, x in pares]
            try:
                pdf, info = await asyncio.wait_for(EV.carrinho_tenda(br, itens_t, cep), 400)
            except Exception:   # falha passageira do site (CEP não aceito, página lenta): uma nova tentativa depois de uma pausa
                await asyncio.sleep(20)
                pdf, info = await asyncio.wait_for(EV.carrinho_tenda(br, itens_t, cep), 400)
            if not info['precos']:   # nenhum produto entrou no carrinho: não guarda o PDF de um carrinho vazio
                return {(loja, x['url']): dict(ev=None, preco=None, problema=info['faltando'].get(x['url'], 'fora do carrinho'), carrinho=True) for l, x in pares}
            sha, rel = db.guardar_arquivo(pid, f'carrinho_tenda_item{item}{sufixo}.pdf', pdf)
            ev = Evidencia(arquivo=rel, sha256=sha, url=info['url'], capturado_em=info['capturado_em'], origem='navegador')
            for l, x in pares:
                if x['url'] in info['precos']:
                    prob = info['problema'] or _sem_preco(pdf, info['precos'][x['url']])
                    out[(loja, x['url'])] = dict(ev=ev.model_copy(update=dict(url=x['url'])), preco=info['precos'][x['url']], problema=prob, carrinho=True)
                else:
                    out[(loja, x['url'])] = dict(ev=None, preco=None, problema=info['faltando'].get(x['url'], 'fora do carrinho'), carrinho=True)
            return out
        except Exception as e:
            ctx.fonte(L.LOJAS[loja]['nome'], 'repetindo', f'carrinho: {type(e).__name__}')
            return None
    return None


async def _preco_muda_com_a_quantidade(loja, pares, cep):
    """As ofertas [(linha, oferta)] em que a loja cobra, pela quantidade do plano, um preço unitário diferente do de uma unidade — ou não
    vende a quantidade toda num pedido. Tenda (atacado: o preço cai a partir de N unidades e a busca não diz de quanto): toda quantidade maior que 1."""
    plat = L.LOJAS[loja]['plataforma']
    varias = [(l, x) for l, x in pares if (l.get('qtd') or 1) > 1]
    if plat == 'tenda' or not varias:
        return varias if plat == 'tenda' else []
    import httpx
    out = []
    async with httpx.AsyncClient(headers={'User-Agent': L.UA, 'Accept': 'application/json'}, timeout=25, follow_redirects=True) as c:
        for l, x in varias:
            r = await L.na_quantidade(c, loja, x, l['qtd'], cep)
            if r and (r[0] != x.get('preco') or r[1] < l['qtd']):
                out.append((l, x))
    return out


def tem_carrinho(loja, pares):
    plat = L.LOJAS[loja]['plataforma']
    return plat == 'tenda' or (plat == 'vtex' and all(x.get('sku') for _, x in pares))


async def _comprovar(br, pid, item, loja, pares, cep, ctx, sufixo='', bloqueadas=None, modo=None):
    """Comprovantes de uma loja para as ofertas [(linha, oferta)]. Devolve {(loja, url): dict(ev, preco, problema)}:
    ev = Evidencia guardada (ou None), preco = preço unitário que o comprovante mostra (ou None), problema = None se o comprovante serve.

    O comprovante é a PÁGINA DO PRODUTO, um PDF por produto, em todas as lojas (decisão da OSC, 06/10/2026) — a faixa do alto diz a quantidade,
    o preço unitário e o total. O CARRINHO só entra como último recurso, quando a página do produto não serve (não mostra o preço que vale
    para o CEP, deu erro ou a loja barrou a página) e a loja tem carrinho. modo='carrinho' (configuração do projeto): o carrinho primeiro."""
    from .produtos import evidencia as EV
    out = {}
    if bloqueadas and loja in bloqueadas:   # loja que barrou: não é acessada de novo
        return {(loja, x['url']): dict(ev=None, preco=None, problema=bloqueadas[loja]) for _, x in pares}
    if modo is None:
        try:
            modo = db.carregar(pid)[0].config.comprovante
        except Exception:
            modo = 'pagina'
    carrinho_antes = modo == 'carrinho' or bool(db.cache_ler(f'so_carrinho|{loja}'))   # hoje a página desta loja já foi barrada: direto ao carrinho
    if carrinho_antes and tem_carrinho(loja, pares):
        r = await _carrinho_da_loja(br, pid, item, loja, pares, cep, ctx, sufixo)
        if r is not None:
            return r
        ctx.fonte(L.LOJAS[loja]['nome'], 'repetindo', 'o carrinho falhou; tentando a página de cada produto')
    bloqueadas = {} if bloqueadas is None else bloqueadas
    falhos = []
    # A página mostra o preço de UMA unidade. Quando a loja cobra outro preço pela quantidade do plano (atacado "a partir de 3 un.", promoção,
    # limite por pedido), o total da quantidade não pode ser visto na página: aí — e só aí — o comprovante é o carrinho (decisão da OSC, 08/10/2026)
    pela_quantidade = await _preco_muda_com_a_quantidade(loja, pares, cep) if tem_carrinho(loja, pares) and not carrinho_antes else []
    if pela_quantidade:
        r = await _carrinho_da_loja(br, pid, item, loja, pela_quantidade, cep, ctx, sufixo)
        for k, v in (r or {}).items():
            out[k] = dict(v, pelo_carrinho='o preço da loja muda com a quantidade')
        pares = [(l, x) for l, x in pares if (loja, x['url']) not in out]   # (se o carrinho falhou, estes seguem para a página, com o preço unitário)
    for l, x in pares:
        if loja in bloqueadas:
            out[(loja, x['url'])] = dict(ev=None, preco=None, problema=bloqueadas[loja]); continue
        try:
            pdf, info = await asyncio.wait_for(EV.pagina_produto(br, loja, x['url'], l['desc'], cep, x.get('preco'), qtd=l.get('qtd')), 240)
        except Exception as e:
            pdf, info = None, dict(problema=f'{type(e).__name__} ao guardar a página')
        ev = None
        prob = info.get('problema') or (_sem_preco(pdf, info.get('preco_pagina') or x.get('preco')) if pdf else 'sem PDF da página')
        if pdf and not (prob and tem_carrinho(loja, pares) and not carrinho_antes):   # página com problema numa loja que tem carrinho: o PDF ruim não é guardado
            sha, rel = db.guardar_arquivo(pid, f'produto_{loja}_item{item}{sufixo or "_" + _nome_arquivo(l["desc"])}.pdf', pdf)
            ev = Evidencia(arquivo=rel, sha256=sha, url=x['url'], capturado_em=info['capturado_em'], origem='navegador')
        out[(loja, x['url'])] = dict(ev=ev, preco=info.get('preco_pagina'), problema=prob)
        if prob:
            falhos.append((l, x))
        if info.get('problema') == EV.BLOQUEIO:
            if tem_carrinho(loja, pares) and not carrinho_antes:
                # a loja barrou a PÁGINA, mas tem carrinho (que não passa por essa verificação): não é descartada; hoje, vai direto ao carrinho
                db.cache_gravar(f'so_carrinho|{loja}', True)
                falhos = [(l2, x2) for l2, x2 in pares if (loja, x2['url']) not in out or out[(loja, x2['url'])]['problema']]
                break
            bloqueadas[loja] = EV.BLOQUEIO
            db.loja_bloquear(loja, 'a loja pediu verificação humana (CAPTCHA/anti-robô)')   # decisão da OSC: loja com CAPTCHA é descartada
            ctx.aviso(f'{L.LOJAS[loja]["nome"]} pediu verificação humana (CAPTCHA). O sistema não resolve CAPTCHA: a loja foi descartada por '
                      f'{db.DIAS_BLOQUEIO} dias e os itens dela vão para outra loja com o mesmo produto, se houver.')
    if falhos and not carrinho_antes and tem_carrinho(loja, pares) and loja not in bloqueadas:   # último recurso: o carrinho da loja, só para o que a página não comprovou
        r = await _carrinho_da_loja(br, pid, item, loja, falhos, cep, ctx, sufixo)
        for k, v in (r or {}).items():
            if not v.get('problema') or not out.get(k, {}).get('ev'):
                out[k] = dict(v, pelo_carrinho=out.get(k, {}).get('problema'))
    return out


def _sem_preco(pdf, centavos):
    """Problema do comprovante quando o preço não aparece no PDF (ex.: preço oculto até informar o CEP); None se aparece ou não dá para conferir."""
    return 'o preço não aparece no PDF da página' if preco_no_pdf(centavos=centavos, conteudo=pdf) is False else None


def _lojas_utilizaveis(opcao, bloqueadas, comp):
    """As 3 ofertas da opção, trocando loja bloqueada ou já sem comprovante por uma reserva (mesmo produto). None se não fechar 3."""
    ruim = lambda x: x['loja'] in bloqueadas or comp.get((x['loja'], x['url']), {}).get('problema')
    boas = [x for x in opcao['ofertas'] if not ruim(x)]
    for rv in opcao.get('reservas') or []:
        if len(boas) >= 3:
            break
        if not ruim(rv) and rv['loja'] not in {x['loja'] for x in boas}:
            boas.append(rv)
    return boas if len(boas) == 3 else None


def valor_depois_do_comprovante(proposto, precos, menor_ou_media=True):
    """O valor do item no plano depois que os comprovantes confirmam os preços. O valor da proposta foi calculado com os preços da BUSCA; o
    comprovante (o carrinho da loja) pode mostrar outro preço, e aí a média muda. O valor nunca passa da média; e, quando o plano só aceita o
    menor dos 3 preços ou a média (teste real de 05/10/2026: ficava um valor que não era nenhum dos dois), ele volta a ser um deles:
    o menor, se a proposta estava abaixo dele; senão, a média."""
    m = media(precos)
    v = min(proposto or m, m)
    if menor_ou_media and v not in valores_do_plano(precos):
        v = min(precos) if v < min(precos) else m
    return v


async def aplicar_proposta(pid, item, proposta, ctx):
    from playwright.async_api import async_playwright
    from .produtos import evidencia as EV
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    cep = _cep(p); hoje = dt.date.today().isoformat()
    em_proposta = {l['desc'] for l in proposta['linhas']}
    em_uso = produtos_em_uso([s for s in r.subitens if pedido_do_subitem(s) not in em_proposta and not item_repetido(r, s)])
    for l in proposta['linhas']:   # produto que já é de outro item da rubrica nunca é gravado (seria um item repetido)
        if l.get('opcao_dados') and cesta.chaves_da_opcao(l['opcao_dados']) & em_uso:
            ctx.aviso(f'"{l["desc"]}": o produto achado ({l["opcao_dados"]["ofertas"][0]["nome"][:60]}) já é outro item desta rubrica; o item ficou como estava.')
            l.update(acao='RETIRADO', opcao_dados=None, motivo='o produto achado já é outro item desta rubrica')
    linhas = [l for l in proposta['linhas'] if l.get('opcao_dados')]
    # 1. comprovantes: carrinho real (VTEX e Tenda) ou página do produto (demais), conferidos; loja reserva quando um falha
    por_loja = {}
    for l in linhas:
        for x in l['opcao_dados']['ofertas']:
            por_loja.setdefault(x['loja'], []).append((l, x))
    comp, trocas, bloqueadas, trocas_opcao, ajustes_qtd = {}, [], {}, [], {}
    for lj, info in db.lojas_bloqueadas().items():   # lojas já descartadas por CAPTCHA (ou em descanso por limite de acessos)
        bloqueadas[lj] = f'loja fora de uso: {info.get("motivo") or "bloqueio"}'
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        try:
            for n, (lj, pares) in enumerate(por_loja.items()):
                nome_loja = L.LOJAS[lj]['nome']
                ctx.progresso(80 * n / max(1, len(por_loja)), f'Comprovantes em {nome_loja} ({len(pares)} itens)')
                res = {}
                for l, x in pares:   # decisão da OSC: cada PDF só com o item a que se refere (um carrinho por item)
                    res.update(await _comprovar(br, pid, item, lj, [(l, x)], cep, ctx, sufixo=f'_{_nome_arquivo(l["desc"])}', bloqueadas=bloqueadas))
                comp.update(res)
                ruins = [v['problema'] for v in res.values() if v['problema']]
                ctx.fonte(nome_loja, 'ok' if not ruins else 'falhou', f'{len(res) - len(ruins)}/{len(res)} comprovantes' + (f' — {ruins[0]}' if ruins else ''))
            # lojas reserva: outra loja com o MESMO produto entra no lugar da que não deu comprovante
            falhas = [(l, i, x) for l in linhas for i, x in enumerate(l['opcao_dados']['ofertas']) if comp.get((x['loja'], x['url']), {}).get('problema')]
            for k, (l, i, x) in enumerate(falhas):
                ctx.progresso(80 + 10 * k / max(1, len(falhas)), f'Procurando outra loja para "{l["desc"]}" (sem comprovante em {L.LOJAS[x["loja"]]["nome"]})')
                em_uso = {y['loja'] for y in l['opcao_dados']['ofertas']}
                for rv in l['opcao_dados'].get('reservas') or []:
                    if rv['loja'] in em_uso or rv['loja'] in bloqueadas:
                        continue
                    res = await _comprovar(br, pid, item, rv['loja'], [(l, rv)], cep, ctx, sufixo=f'_{_nome_arquivo(l["desc"])}', bloqueadas=bloqueadas)
                    v = res.get((rv['loja'], rv['url']))
                    if v and not v['problema']:
                        comp.update(res)
                        motivo = comp[(x['loja'], x['url'])]['problema']
                        l['opcao_dados']['ofertas'][i] = rv
                        trocas.append((l['desc'], x['loja'], rv['loja'], motivo))
                        ctx.fonte(L.LOJAS[rv['loja']]['nome'], 'ok', f'reserva para {l["desc"][:30]}')
                        break
            # QUANTIDADE (decisão da OSC, 27/09/2026): se a loja limita a quantidade por cliente e não há loja reserva, o item passa a ter
            # a quantidade que a loja aceita, nas 3 lojas (novos comprovantes); a diferença de valor é compensada no fechamento do teto
            for l in linhas:
                probs = [comp.get((x['loja'], x['url']), {}).get('problema') or '' for x in l['opcao_dados']['ofertas']]
                limites = [int(m.group(1) or m.group(2)) for pr in probs for m in [LIMITE_QTD.search(pr)] if m]
                if not limites or any(pr and not LIMITE_QTD.search(pr) for pr in probs):
                    continue
                nova, antiga = min(limites), l['qtd']
                if nova >= antiga or nova < max(1, (antiga + 1) // 2):   # só reduz, e no máximo até a metade
                    continue
                ctx.progresso(91, f'"{l["desc"]}": a loja aceita no máximo {nova} unidade(s); refazendo os 3 comprovantes com essa quantidade')
                l['qtd'] = nova
                novos = {}
                for x in l['opcao_dados']['ofertas']:
                    novos.update(await _comprovar(br, pid, item, x['loja'], [(l, x)], cep, ctx, sufixo=f'_{_nome_arquivo(l["desc"])}_qtd{nova}',
                                                  bloqueadas=bloqueadas))
                if all(v and not v['problema'] for v in (novos.get((x['loja'], x['url'])) for x in l['opcao_dados']['ofertas'])):
                    comp.update(novos); ajustes_qtd[l['desc']] = (antiga, nova)
                else:
                    l['qtd'] = antiga
            # outra OPÇÃO do item (outro produto em 3 lojas) quando nenhuma loja reserva resolveu — respeitando o teto da rubrica
            teto_r = proposta.get('teto')
            total = sum((l.get('valor') or 0) * l['qtd'] for l in linhas)
            for l in linhas:
                if not any(comp.get((x['loja'], x['url']), {}).get('problema') for x in l['opcao_dados']['ofertas']):
                    continue
                for alt in l.get('alternativas') or []:
                    if alt['nivel'] > l['opcao_dados']['nivel'] or not cesta.atende_o_pedido(alt):   # nunca uma substituição (nem 800 g no lugar de 1,6 kg) por falta de comprovante
                        continue
                    ofs = _lojas_utilizaveis(alt, bloqueadas, comp)
                    em_outros = {(y['loja'], y['url']) for o in linhas if o is not l for y in o['opcao_dados']['ofertas']}
                    if not ofs or any((x['loja'], x['url']) in em_outros for x in ofs):   # um produto não atende dois itens
                        continue
                    alt = dict(alt, ofertas=ofs)
                    med, dom = teto.dominio([x['preco'] for x in alt['ofertas']], True)
                    cabe = [v for v in dom if teto_r is None or total - (l.get('valor') or 0) * l['qtd'] + v * l['qtd'] <= teto_r]
                    if not cabe:
                        continue
                    if alt['confirmacao'] == 'descrição' and not alt.get('ia') and p.config.usar_ia and ia.disponivel():
                        # mesma regra da pesquisa: produto confirmado só pela descrição passa pela IA antes de ser usado
                        ctx.progresso(91, f'Conferindo com a IA outra opção para "{l["desc"]}"')
                        rr = ia.mesmo_produto([x.get('titulo') or x['nome'] for x in alt['ofertas']], pid)
                        if not rr or not rr[0]:
                            continue
                        alt['ia'] = dict(mesmo_produto=True, motivo=rr[1])
                    ctx.progresso(92, f'Tentando outra opção para "{l["desc"]}": {alt["ofertas"][0]["nome"][:50]}')
                    novos = {}
                    for x in alt['ofertas']:
                        novos.update(await _comprovar(br, pid, item, x['loja'], [(l, x)], cep, ctx, sufixo=f'_{_nome_arquivo(l["desc"])}_alt',
                                                      bloqueadas=bloqueadas))
                    comp.update({k: v for k, v in novos.items() if k not in comp or not v['problema']})
                    if all(v and not v['problema'] for v in (novos.get((x['loja'], x['url'])) for x in alt['ofertas'])):
                        antigo = l['opcao_dados']['ofertas'][0]['nome']
                        v = med if med in cabe else max(cabe)
                        total += (v - (l.get('valor') or 0)) * l['qtd']
                        l.update(opcao_dados=alt, valor=v, media=med)
                        trocas[:] = [t for t in trocas if t[0] != l['desc']]   # trocas de loja da opção antiga não valem mais
                        trocas_opcao.append((l['desc'], antigo, alt['ofertas'][0]['nome']))
                        break
        finally:
            await br.close()
    # anúncio sem comprovante hoje (indisponível, fora do catálogo): a próxima pesquisa do dia não o escolhe de novo
    for (lj, url), v in comp.items():
        if v['problema'] and v['problema'] != EV.BLOQUEIO and not v['problema'].startswith('loja fora de uso') and url:
            db.cache_gravar(f'indisp|{lj}|{url}', v['problema'])
    for d, (antiga, nova) in ajustes_qtd.items():
        ctx.aviso(f'"{d}": quantidade ajustada de {antiga} para {nova} (limite de compra por cliente da loja); os 3 comprovantes foram refeitos com '
                  f'{nova} unidade(s). Use "Fechar no teto" para compensar a diferença.')
    for d, antigo, novo in trocas_opcao:
        ctx.aviso(f'"{d}": o produto "{antigo[:60]}" ficou sem comprovante em alguma loja; usada a próxima opção válida, "{novo[:60]}", '
                  f'com comprovante nas 3 lojas.')
    for d, a, b, motivo in trocas:
        ctx.aviso(f'"{d}": {L.LOJAS[a]["nome"]} substituída por {L.LOJAS[b]["nome"]} (mesmo produto) — {motivo}.')
    for l in linhas:
        for x in l['opcao_dados']['ofertas']:
            v = comp.get((x['loja'], x['url']))
            if v and v['problema']:
                ctx.aviso(f'Comprovante com problema — "{l["desc"]}" em {L.LOJAS[x["loja"]]["nome"]}: {v["problema"]}. '
                          f'Nenhuma outra loja com o mesmo produto deu comprovante; confira manualmente ({x["url"]}).')
    # 2. subitens: fornecedores por item, preços (o do carrinho prevalece), produtos, EAN, nível e justificativa
    ctx.progresso(92, 'Preenchendo a grade e o plano')
    chaves = [(pedido_do_subitem(s), s) for s in r.subitens]   # a chave de cada subitem ANTES da pesquisa mexer na marca e na especificação
    repetiam = {id(r.subitens[i]) for i in itens_repetidos(r)}   # itens que estavam com o mesmo produto de outro item
    por_desc = {d: s for d, s in chaves}
    tratados, novos, retirados, divergencias = {}, [], [], []
    for l in proposta['linhas']:
        s = por_desc.get(l['desc'])
        if l['acao'] == 'RETIRADO':
            if s is not None:
                if l.get('motivo', '').startswith('retirado'):
                    retirados.append(l['desc'])      # tirado para caber no teto (D9)
                    continue
                if id(s) in repetiam:   # estava repetindo outro item e a nova pesquisa não achou nada: volta a ser o que a OSC pediu, sem pesquisas
                    voltar_ao_pedido(s)
                if not (s.justificativa or '').startswith(DUAS_LOJAS):   # (item com as 2 pesquisas do sistema e a 3ª à mão: continua como está)
                    s.justificativa = l.get('motivo')
                tratados[l['desc']] = s   # não achado em 3 lojas: fica, com pendência, para decisão
            continue
        o = l['opcao_dados']
        if s is None:  # item extra acrescentado
            s = Subitem(descricao=l['desc'], qtd=l['qtd'], justificativa='acrescentado: sobra da rubrica acima da folga do teto (D9)')
        fontes, precos, produtos, eans = [], [], [], []
        for x in o['ofertas']:
            v = comp.get((x['loja'], x['url'])) or {}
            ev = v.get('ev') or Evidencia(url=x['url'], origem='navegador')   # sem arquivo (o comprovante falhou), mas é da pesquisa automática — não "manual"
            ev = ev.model_copy(update=dict(url=url_limpa(ev.url)))
            if v.get('problema') and ev.arquivo:   # o PDF fica guardado para consulta, mas a pesquisa continua pendente
                ev = ev.model_copy(update=dict(problema=v['problema']))
            fontes.append(_fonte_loja(x['loja'], hoje, ev))
            pc = v.get('preco')
            if pc and pc != x['preco']:
                divergencias.append(f"{l['desc']} em {L.LOJAS[x['loja']]['nome']}: pesquisa {x['preco'] / 100:.2f}, carrinho {pc / 100:.2f} (vale o carrinho)")
            precos.append(pc or x['preco']); produtos.append(x.get('titulo') or x['nome']); eans.append(x.get('ean'))
        s.fontes, s.precos, s.produtos, s.eans = fontes, precos, produtos, eans
        s.nivel, s.confirmacao = o['nivel'], o['confirmacao']
        campos_do_produto(s, o, pid, item, l['desc'])
        just = [f"as 3 lojas mais baratas, de empresas diferentes, entre as {o['lojas_com_o_produto']} que têm o mesmo produto (critério neutro: menor preço)"]
        if o.get('misto'):
            just[0] = (f"mesma especificação com marcas diferentes entre as lojas: o mesmo produto não existe em 3 lojas (forma aceita pela SEJC na "
                       f"papelaria); as 3 lojas mais baratas, de empresas diferentes, entre as {o['lojas_com_o_produto']} com essa especificação")
        if o['nivel'] == 3:
            just.insert(0, f"troca por produto da categoria da rubrica ({o.get('substituto')}): o item pedido não existe igual em 3 lojas, nem de outra marca, "
                           f"nem parecido, nem da mesma família")
        elif o.get('mais_largo'):
            just.insert(0, f"o mesmo item, sem {' e sem '.join(o['mais_largo']['sem'])} (o item como foi pedido não existe igual em 3 lojas)")
        elif o['nivel'] and not o.get('trio_ia'):
            just.insert(0, f"troca por item {'parecido' if o['nivel'] == 1 else 'relacionado'}" + (f" (perdeu: {', '.join(o['perdidos'])})" if o['perdidos'] else ''))
        elif not o['nivel'] and o.get('perdidos'):
            just.insert(0, f"como pedido, mas sem: {', '.join(o['perdidos'])} (não existe assim em 3 lojas)")
        if o.get('codigos_diferentes'):
            just.insert(0, 'mesma marca e mesma descrição nas 3 lojas, com códigos de barras diferentes (podem ser linhas diferentes do fabricante)')
        if o.get('detalhe_nao_citado'):
            just.insert(0, 'o mesmo produto em 2 lojas e, na terceira, um anúncio da mesma marca com menos (ou mais) detalhes na descrição')
        if o.get('escolhida_pela_osc') and not cesta.atende_o_pedido(o):
            just.insert(0, f'opção escolhida pela OSC em {dt.date.today():%d/%m/%Y} (o item pedido não foi achado igual em 3 lojas; o sistema não substitui sozinho)')
        if o.get('trio_ia'):
            just.append('os 3 produtos equivalentes foram escolhidos pela IA entre os anúncios das lojas e validados pelo sistema (3 empresas diferentes)')
        if o.get('ia'):
            just.append(f"IA: {o['ia']['motivo']}")
        if o.get('ia_subst'):
            just.append(f"IA escolheu a troca: {o['ia_subst']}")
        if l['desc'] in ajustes_qtd:
            antiga, nova = ajustes_qtd[l['desc']]
            s.qtd = nova
            just.append(f'quantidade ajustada de {antiga} para {nova}: limite de compra por cliente da loja (a diferença é compensada no fechamento do teto)')
        for d, antigo, novo in trocas_opcao:
            if d == l['desc']:
                just.append(f'opção trocada ao gerar os comprovantes: "{antigo[:60]}" sem comprovante; usada "{novo[:60]}"')
        for d, a, b, motivo in trocas:
            if d == l['desc']:
                just.append(f"{L.LOJAS[a]['nome']} substituída por {L.LOJAS[b]['nome']} (mesmo produto): {motivo}")
        s.justificativa = '; '.join(just)
        s.valor_plano = valor_depois_do_comprovante(l.get('valor'), s.precos, p.config.valores_defensaveis)
        tratados[l['desc']] = s
    pesquisados = {l['desc'] for l in proposta['linhas']}
    for d, s0 in chaves:   # ordem original; os que não foram pesquisados ficam como estavam
        if d not in pesquisados:
            novos.append(s0)
        elif d in tratados:
            novos.append(tratados.pop(d))
    novos += list(tratados.values())   # itens extras acrescentados pelo teto
    r.subitens = novos
    for aviso in divergencias:
        ctx.aviso(aviso)
    motivo = (f'item {item}: pesquisa automática aplicada ({proposta["modo"].replace("_", " ")}; {sum(1 for l in linhas if l["acao"] == "mantido")} itens'
              + (f'; retirados para caber no teto: {", ".join(retirados)}' if retirados else '')
              + (f'; acrescentados: {", ".join(l["desc"] for l in linhas if l["acao"] == "ACRESCENTADO")}' if any(l['acao'] == 'ACRESCENTADO' for l in linhas) else '') + ')')
    v = db.salvar(pid, p, autor='sistema (pesquisa automática)', motivo=motivo, tarefa=ctx.id, divergencias=divergencias)
    ctx.progresso(100, 'Concluído')
    return dict(versao=v, retirados=retirados, divergencias=divergencias, ir_para=f'/p/{pid}/mat/{item}')


def _loja_da_fonte(f):
    nomes = {l['nome']: k for k, l in L.LOJAS.items()}
    return nomes.get(f.plataforma or '')


def _opcao_atual(opcoes, atuais, fora):
    """Entre as opções guardadas, a que é o produto das pesquisas atuais (tirando a pesquisa `fora`): mesmas páginas ou mesmo código de
    barras nas outras duas. Devolve todas as ofertas dessa opção (as 3 e as reservas), ou []."""
    outras = [x for j, x in enumerate(atuais) if j != fora and x[0]]
    for o in opcoes or []:
        if o.get('misto'):
            continue
        todas = o['ofertas'] + (o.get('reservas') or [])
        paginas = {(x['loja'], url_limpa(x['url'])) for x in todas}
        eans = {x['ean'].lstrip('0') for x in todas if x.get('ean')}
        if outras and all((l, u) in paginas or (e and e.lstrip('0') in eans) for l, u, e in outras):
            return todas
    return []


async def _nova_pesquisa(br, p, pid, r, s, k, ctx, mesma_primeiro, opcoes):
    """Troca a pesquisa k do subitem por outra com comprovante: a mesma oferta de novo (falha passageira da loja), depois outra loja com o
    MESMO produto, da mais barata para a mais cara. True se trocou."""
    item, pedido, hoje = r.item, pedido_do_subitem(s), dt.date.today().isoformat()
    atuais = [(_loja_da_fonte(f), url_limpa(f.evidencia.url), (s.eans[j] if j < len(s.eans) else None)) for j, f in enumerate(s.fontes)]
    todas = _opcao_atual(opcoes, atuais, k)
    if not todas:
        return False
    raizes = {L.raiz(l) for j, (l, _, _) in enumerate(atuais) if j != k and l}
    mesma = [x for x in todas if (x['loja'], url_limpa(x['url'])) == atuais[k][:2]] if mesma_primeiro else []
    novas = sorted((x for x in todas if x['loja'] not in {l for l, _, _ in atuais} and L.raiz(x['loja']) not in raizes), key=lambda x: x['preco'])
    bloqueadas = {lj: f'loja fora de uso: {i.get("motivo") or "bloqueio"}' for lj, i in db.lojas_bloqueadas().items()}
    linha = dict(desc=pedido, qtd=s.qtd)
    for x in mesma + novas:
        ctx.etapa(f'"{pedido}": comprovante em {L.LOJAS[x["loja"]]["nome"]}')
        res = await _comprovar(br, pid, item, x['loja'], [(linha, x)], _cep(p), ctx, sufixo=f'_{_nome_arquivo(pedido)}_p{k + 1}', bloqueadas=bloqueadas)
        v = res.get((x['loja'], x['url']))
        if not v or v['problema'] or not v['ev']:
            continue
        antes = s.fontes[k].plataforma or s.fontes[k].nome
        s.fontes[k] = _fonte_loja(x['loja'], hoje, v['ev'].model_copy(update=dict(url=url_limpa(v['ev'].url))))
        s.precos[k] = v['preco'] or x['preco']
        while len(s.produtos) < 3:
            s.produtos.append(None)
        while len(s.eans) < 3:
            s.eans.append(None)
        s.produtos[k], s.eans[k] = x.get('titulo') or x['nome'], x.get('ean')
        m = media(s.precos)
        s.valor_plano = min(s.valor_plano or m, m)
        s.justificativa = ((s.justificativa or '') + f'; pesquisa {k + 1}: ' + ('comprovante refeito em ' if x in mesma else f'{antes} trocada por ')
                           + f'{L.LOJAS[x["loja"]]["nome"]} (mesmo produto)').lstrip('; ')
        return True
    return False


async def trocar_loja(pid, item, i, k, ctx):
    """Pedido da OSC (03/10/2026): nova pesquisa de UMA das 3 pesquisas de um item, sem refazer as outras duas. Procura outra loja com o
    MESMO produto das outras duas (primeiro nas opções guardadas; se não houver, pesquisa o item de novo nas lojas)."""
    from playwright.async_api import async_playwright
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    s = r.subitens[i]
    pedido = pedido_do_subitem(s)
    volta = f'/p/{pid}/mat/{item}#sub{i}'
    if len(s.fontes) != 3 or produtos_diferentes(s):
        raise ValueError('as 3 pesquisas deste item ainda não são do mesmo produto: use "Pesquisar de novo só este item"')
    opcoes = (db.produtos_do_banco(pid, item).get(pedido) or {}).get('opcoes') or []
    atuais = [(_loja_da_fonte(f), url_limpa(f.evidencia.url), (s.eans[j] if j < len(s.eans) else None)) for j, f in enumerate(s.fontes)]
    loja_k = atuais[k][0]
    def ha_outra(ops):
        return any(x['loja'] not in {l for l, _, _ in atuais} for x in _opcao_atual(ops, atuais, k))
    if not ha_outra(opcoes):   # nada guardado: pesquisa o item de novo (todas as lojas) para achar quem mais tem o mesmo produto
        ctx.progresso(5, f'Procurando outras lojas com o mesmo produto de "{pedido}"')
        lojas = lojas_da_rubrica(p, r)
        res = await cesta.pesquisar([dict(desc=pedido, qtd=s.qtd, familia=s.familia, valor_ref=_valor_ref(s))], lojas, _cep(p), ctx, 'por_item',
                                    p.config.usar_ia, pid, L.setor_da_rubrica(r.descricao), r.extras, False)
        opcoes = [dict(o, precos=_precos(o)) for o in res['opcoes'].get(pedido, [])]
        if opcoes:
            db.produtos_guardar(pid, item, pedido, opcoes)
    ctx.progresso(70, f'Comprovante da nova loja para "{pedido}"')
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        try:
            ok = await _nova_pesquisa(br, p, pid, r, s, k, ctx, False, opcoes)
        finally:
            await br.close()
    ctx.progresso(100, 'Concluído')
    if not ok:
        ctx.aviso(f'"{pedido}", pesquisa {k + 1}: nenhuma outra loja tem o mesmo produto das outras duas pesquisas com comprovante. A pesquisa ficou como '
                  f'estava. Você pode usar "Pesquisar de novo só este item" (as 3 pesquisas podem mudar) ou preencher esta pesquisa à mão.')
        return dict(versao=None, ir_para=volta)
    v = db.salvar(pid, p, autor='sistema (pesquisa automática)', tarefa=ctx.id,
                  motivo=f'item {item}: pesquisa {k + 1} de "{pedido}" trocada de {L.LOJAS[loja_k]["nome"] if loja_k else "outra loja"} para '
                         f'{s.fontes[k].plataforma} (mesmo produto)')
    return dict(versao=v, ir_para=volta)


async def _recapturar(br, p, pid, r, s, k, ctx):
    """Guarda de novo o comprovante da pesquisa k do subitem, na MESMA loja e na mesma página. Devolve (ok, mensagem). O comprovante atual
    só é trocado se o novo servir (página sem erro, produto disponível, preço visível no PDF)."""
    from .produtos import evidencia as EV
    from . import sistemas as S
    f = s.fontes[k]
    url, preco = url_limpa(f.evidencia.url), (s.precos[k] if k < len(s.precos) else None)
    tipo, loja, pedido = tipo_da_rubrica(r), _loja_da_fonte(f), pedido_do_subitem(s)
    onde = f.plataforma or f.nome or 'a loja'
    novo_preco = None
    if tipo in ('mercado', 'material') and loja:   # como na pesquisa: carrinho da loja (quando ela tem) ou a página do produto
        guardadas = [x for o in (db.produtos_do_banco(pid, r.item).get(pedido) or {}).get('opcoes') or [] for x in o['ofertas'] + (o.get('reservas') or [])]
        x = next((x for x in guardadas if x['loja'] == loja and url_limpa(x['url']) == url), None) or dict(
            loja=loja, nome=(s.produtos[k] if k < len(s.produtos) else None) or pedido, url=f.evidencia.url, preco=preco)
        bloqueadas = {lj: f'loja fora de uso: {i.get("motivo") or "bloqueio"}' for lj, i in db.lojas_bloqueadas().items()}
        res = await _comprovar(br, pid, r.item, loja, [(dict(desc=pedido, qtd=s.qtd), x)], _cep(p), ctx, sufixo=f'_{_nome_arquivo(pedido)}_p{k + 1}', bloqueadas=bloqueadas)
        v = res.get((loja, x['url'])) or dict(ev=None, preco=None, problema='a loja não devolveu o comprovante')
        ev, novo_preco, problema = v['ev'], v['preco'], v['problema']
    else:                                           # sistema, serviço ou link digitado: a página do link
        faixa = f'PESQUISA DE PREÇO | {onde} | ' + ('planos' if tipo == 'sistema' else pedido)
        try:
            pdf, info = await asyncio.wait_for(EV.pagina(br, url, faixa, preco=preco, completa=(tipo == 'sistema')), 300)
        except asyncio.TimeoutError:
            pdf, info = None, dict(problema='a página não respondeu a tempo', capturado_em=db.agora())
        problema = info.get('problema') or (None if pdf else 'a página não pôde ser guardada')
        if pdf and not problema and preco and not S.preco_no_texto(texto_do_pdf(conteudo=pdf), preco):
            problema = f'o preço da pesquisa ({_reais(preco)}) não aparece na página'
        ev = None
        if pdf and not problema:
            sha, rel = db.guardar_arquivo(pid, f'pagina_{_nome_arquivo(onde)}_item{r.item}_p{k + 1}.pdf', pdf)
            ev = Evidencia(arquivo=rel, sha256=sha, url=url, capturado_em=info['capturado_em'], origem='navegador')
    if problema or not ev:
        return False, f'{onde}: {problema or "sem comprovante"}. O comprovante que já estava guardado foi mantido.'
    f.evidencia = ev.model_copy(update=dict(url=url_limpa(ev.url) or url))
    f.data_pesquisa = dt.date.today().isoformat()
    msg = f'{onde}: página guardada de novo.'
    if novo_preco and preco and novo_preco != preco:   # a loja mostra outro preço hoje: vale o do comprovante novo
        s.precos[k] = novo_preco
        msg += f' O preço mudou de {_reais(preco)} para {_reais(novo_preco)} (vale o do comprovante novo).'
    if len(s.precos) == 3 and None not in s.precos:
        m = media(s.precos)
        s.valor_plano = valor_do_sistema(s) if tipo == 'sistema' else min(s.valor_plano or m, m)
    return True, msg


async def recapturar_pesquisa(pid, item, i, k, ctx):
    """Pedido da OSC (03/10/2026): "Guardar a página de novo" também em materiais e serviços. Refaz o comprovante de UMA pesquisa, na mesma
    loja e na mesma página (por exemplo, para sair sem aviso ou propaganda por cima). As outras duas pesquisas não mudam."""
    from playwright.async_api import async_playwright
    from .modelo import fontes_do_subitem
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    s = r.subitens[i]
    volta = f'/p/{pid}/mat/{item}#sub{i}'
    if len(s.fontes) != 3:   # o subitem passa a ter as suas 3 pesquisas (cópia das da rubrica)
        s.fontes = ([f.model_copy(deep=True) for f in fontes_do_subitem(r, s)] + [Fonte(), Fonte(), Fonte()])[:3]
    f = s.fontes[k]
    if not f.evidencia.url:
        raise ValueError('esta pesquisa não tem link: sem ele não dá para guardar a página. Se o comprovante é uma proposta em PDF, anexe o arquivo')
    if f.evidencia.origem == 'pdf':
        raise ValueError('o comprovante desta pesquisa foi anexado por você, e o sistema nunca troca um PDF anexado. Para trocar, anexe outro arquivo')
    ctx.progresso(10, f'Abrindo a página de {f.plataforma or f.nome or "a loja"}')
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        try:
            ok, msg = await _recapturar(br, p, pid, r, s, k, ctx)
        finally:
            await br.close()
    ctx.progresso(100, 'Concluído')
    ctx.aviso(f'Pesquisa {k + 1} de "{pedido_do_subitem(s)}" — {msg}')
    if not ok:
        return dict(versao=None, ir_para=volta)
    v = db.salvar(pid, p, autor='sistema (pesquisa automática)', tarefa=ctx.id,
                  motivo=f'item {item}: comprovante da pesquisa {k + 1} de "{pedido_do_subitem(s)}" guardado de novo ({f.plataforma or f.nome})')
    return dict(versao=v, ir_para=volta)


async def consertar_pendentes(pid, item, ctx):
    """O próprio sistema resolve o que dá (pedido da OSC, 03/10/2026): para cada pesquisa sem comprovante válido (página vazia, loja sem
    estoque no carrinho, PDF que não mostra o preço), tenta o comprovante de novo e, se não der, outra loja com o MESMO produto — sem
    refazer as outras pesquisas do item. Devolve quantas pesquisas foram resolvidas."""
    from playwright.async_api import async_playwright
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    banco = db.produtos_do_banco(pid, item)
    alvos = [(s, k) for s in r.subitens if len(s.fontes) == 3 and not produtos_diferentes(s) and all(s.precos or [None])
             for k in range(3) if not pesquisa_comprovada(s.fontes[k], s.precos[k])]
    alvos = [(s, k) for s, k in alvos if (banco.get(pedido_do_subitem(s)) or {}).get('opcoes')]
    if not alvos:
        return 0
    feitas = []
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        try:
            for n, (s, k) in enumerate(alvos):
                ctx.progresso(100 * n / len(alvos), f'Resolvendo a pesquisa {k + 1} de "{pedido_do_subitem(s)}" ({n + 1} de {len(alvos)})')
                if await _nova_pesquisa(br, p, pid, r, s, k, ctx, True, banco[pedido_do_subitem(s)]['opcoes']):
                    feitas.append(f'{pedido_do_subitem(s)} (pesquisa {k + 1}: {s.fontes[k].plataforma})')
        finally:
            await br.close()
    if feitas:
        db.salvar(pid, p, autor='sistema (pesquisa automática)', tarefa=ctx.id,
                  motivo=f'item {item}: {len(feitas)} pesquisa(s) sem comprovante resolvida(s) pelo sistema: ' + '; '.join(feitas))
        ctx.aviso(f'Item {item}: {len(feitas)} pesquisa(s) que estavam sem comprovante foram resolvidas (comprovante refeito ou outra loja com o mesmo '
                  f'produto): ' + '; '.join(feitas) + '.')
    return len(feitas)


def importar_comprovantes(p, pid, arquivos, cnpjs, avisar_outros=True):
    """arquivos: [(nome, bytes)] — PDFs do Comprovante de Inscrição e de Situação Cadastral salvos pela OSC. Confere (é o oficial, CNPJ do
    projeto, ATIVA, emitido há até 180 dias) e guarda como evidência do CNPJ. Devolve (CNPJs importados, problemas)."""
    from . import comprovante_receita as CR
    ok, prob = [], []
    for nome, pdf in arquivos:
        info = CR.ler(pdf)
        problema = CR.conferir(info, cnpjs, p.config.validade_dias)
        if problema:
            if info or avisar_outros:   # na pasta dos comprovantes, PDFs que não são comprovantes são ignorados em silêncio
                prob.append(f'{nome}: {problema}')
            continue
        atual = p.comprovantes_cnpj.get(info['cnpj'])
        if atual and (atual.get('emitido_em') or '') >= (info['emitido_em'] or ''):
            continue   # já há um comprovante igual ou mais recente
        sha, rel = db.guardar_arquivo(pid, f'comprovante_cnpj_{re.sub(r"[^0-9]", "", info["cnpj"])}.pdf', pdf)
        p.comprovantes_cnpj[info['cnpj']] = dict(arquivo=rel, sha256=sha, situacao=info['situacao'], emitido_em=info['emitido_em'],
                                                 razao=info['razao'], importado_em=db.agora(), arquivo_original=nome)
        ok.append(info['cnpj'])
    return ok, prob


async def trocar_produto(pid, item, desc, idx, ctx):
    """A OSC escolheu outra opção do banco de produtos para o subitem: gera os comprovantes dela (com lojas reserva, se preciso) e grava."""
    banco = db.produtos_do_banco(pid, item).get(desc)
    if not banco or idx >= len(banco['opcoes']):
        raise ValueError('opção não encontrada no banco de produtos: pesquise a rubrica de novo')
    p, _ = db.carregar(pid)
    s = next((x for x in _rubrica(p, item).subitens if pedido_do_subitem(x) == desc), None)
    if s is None:
        raise ValueError(f'o subitem "{desc}" não está mais na rubrica')
    o = dict(banco['opcoes'][idx], escolhida_pela_osc=True)
    linha = dict(acao='mantido', desc=desc, qtd=s.qtd, opcao=idx, valor=None, opcao_dados=o, alternativas=[])
    return await aplicar_proposta(pid, item, dict(linhas=[linha], modo='escolha da OSC', teto=None), ctx)


def similares_do_cargo(r):
    """Títulos similares aceitos para o cargo: os que a OSC marcou na tela do cargo ou, se ela nunca mexeu, as sugestões do sistema."""
    from . import vagas as V
    return V.outros_titulos(r.cargo, V.sugestoes_similares(r.cargo) if r.titulos_similares is None else r.titulos_similares)


def titulo_em_uso(r):
    """O título cujas vagas vão para o orçamento do cargo: o do próprio cargo ou, se a OSC escolheu, UM título similar aceito. Vagas de
    títulos diferentes nunca entram juntas (decisão da OSC, 06/10/2026)."""
    from . import vagas as V
    t = getattr(r, 'titulo_em_uso', None)
    return t if t and any(V.chave_cargo(t) == V.chave_cargo(x) for x in similares_do_cargo(r)) else r.cargo


def do_titulo(q, titulo):
    """A pesquisa é de uma vaga desse título? Pesquisa sem título de vaga (preenchida à mão) não é de título nenhum: vale em qualquer grupo."""
    from . import vagas as V
    return not q.titulo_vaga or V.titulo_exato(q.titulo_vaga, titulo)


def titulos_misturados(r):
    """Os títulos (grupos) das pesquisas do cargo quando há mais de um — o que não pode. [] se as pesquisas são todas do mesmo título."""
    from . import vagas as V
    sim = similares_do_cargo(r)
    grupos = []
    for q in r.pesquisas[:3]:
        if q.titulo_vaga:
            g = V.grupo_do_titulo(q.titulo_vaga, r.cargo, sim) or q.titulo_vaga
            if not any(V.chave_cargo(g) == V.chave_cargo(x) for x in grupos):
                grupos.append(g)
    return grupos if len(grupos) > 1 else []


def usar_titulo(p, pid, r, titulo):
    """A OSC escolhe de que título são as 3 pesquisas do cargo: o do próprio cargo (as vagas que houver, 1 a 3) ou um título similar com
    3 vagas. As 3 pesquisas são trocadas de uma vez. Devolve (as pesquisas novas, itens do mesmo cargo que receberam as mesmas)."""
    from . import vagas as V
    from .calculo import mensal_maximo_rh, nivelar_pela_faixa
    proprio = V.chave_cargo(titulo or '') == V.chave_cargo(r.cargo)
    aceito = next((t for t in similares_do_cargo(r) if V.chave_cargo(t) == V.chave_cargo(titulo or '')), None)
    if not proprio and not aceito:
        raise ValueError(f'"{titulo}" não é um título similar aceito para este cargo')
    from .calculo import media_para_a_faixa
    tres = V.tres_do_titulo(r.cargo if proprio else aceito, media_para_a_faixa(r, p.config))
    if not proprio and len(tres) < 3:
        raise ValueError(f'o título "{aceito}" não tem 3 vagas válidas, de empresas diferentes, no banco de vagas')
    r.titulo_em_uso = None if proprio else aceito
    novas = [_pesquisa_da_vaga(pid, v) for v in tres]
    manuais = [q for q in r.pesquisas if not q.titulo_vaga and pesquisa_completa(q) and _raiz(q.cnpj) not in {_raiz(n.cnpj) for n in novas}]
    r.pesquisas = (novas + manuais + [PesquisaSalarial(), PesquisaSalarial(), PesquisaSalarial()])[:3]
    maxm, _, _ = mensal_maximo_rh(r, p.config)
    if not nivelar_pela_faixa(r, p.config) and maxm is not None:
        r.valor_mensal_plano = maxm
    return novas, replicar_pesquisas(p, r)


def _pesquisa_da_vaga(pid, v):
    """Pesquisa salarial a partir de uma vaga do banco (o PDF da vaga é copiado para as evidências do projeto)."""
    ev = Evidencia(url=v['url'], origem='navegador', capturado_em=v['coletada_em'])
    if v.get('pdf'):
        with open(db.caminho_absoluto(v['pdf']), 'rb') as f:
            sha, rel = db.guardar_arquivo(pid, f"vaga_{v['plataforma']}_{re.sub(r'[^A-Za-z0-9]+', '_', v['empresa'])[:30]}.pdf", f.read())
        ev = Evidencia(url=v['url'], arquivo=rel, sha256=sha, capturado_em=v['coletada_em'], origem='navegador')
    return PesquisaSalarial(nome=v['razao'] or v['empresa'], cnpj=cnpj_formatar(v['cnpj']), plataforma=v['plataforma'], titulo_vaga=v.get('titulo'),
                            data_pesquisa=v['coletada_em'][:10], faixa_min=v['faixa_min'], faixa_max=v['faixa_max'], valor=v['faixa_min'], evidencia=ev)


def _raiz(c):
    return re.sub(r'\D', '', c or '')[:8]


def usar_vaga(p, pid, r, url, k):
    """Coloca uma vaga do banco (CNPJ 🟢, PDF guardado) no lugar da pesquisa k do cargo. Se a vaga já está em outra pesquisa do cargo,
    as duas trocam de lugar (o número escolhido é a nova posição dela)."""
    from . import vagas as V
    while len(r.pesquisas) < 3:
        r.pesquisas.append(PesquisaSalarial())
    atual = next((j for j, q in enumerate(r.pesquisas[:3]) if q.evidencia and q.evidencia.url == url), None)
    if atual is not None:
        if atual != k:
            r.pesquisas[atual], r.pesquisas[k] = r.pesquisas[k], r.pesquisas[atual]
        return r.pesquisas[k]
    v = next((x for x in V.banco_com_similares(r.cargo, similares_do_cargo(r), so_verdes=True) if x['url'] == url), None)
    if v is None:
        raise ValueError('a vaga não está no banco (ou não tem CNPJ confirmado e PDF)')
    if V.chave_cargo(v['titulo_busca']) != V.chave_cargo(titulo_em_uso(r)):
        raise ValueError(f'essa vaga é do título "{v["titulo_busca"]}", e as pesquisas do cargo são do título "{titulo_em_uso(r)}": vagas de títulos diferentes '
                         f'não vão juntas para o orçamento. Para usar as vagas de "{v["titulo_busca"]}", escolha esse título em "Títulos com vagas"')
    if v.get('pdf') and V.pdf_a_combinar(db.caminho_absoluto(v['pdf']), v.get('faixa_min')):
        raise ValueError('a página da vaga diz "salário a combinar": não pode entrar no orçamento')
    outras = [_raiz(q.cnpj) for j, q in enumerate(r.pesquisas) if j != k]
    if _raiz(v['cnpj']) in outras:
        raise ValueError('essa empresa já está em outra pesquisa do cargo (as 3 precisam ser de empresas diferentes — R09)')
    nova = _pesquisa_da_vaga(pid, v)
    r.pesquisas[k] = nova
    from .calculo import nivelar_pela_faixa
    nivelar_pela_faixa(r, p.config)   # cargo com faixa pretendida: as horas acompanham a nova média
    return nova


# ------------------------------------------------------------------ Catho com a sessão da OSC (pedido de 02/10/2026)
def pesquisas_catho_ocultas(p):
    """[(rubrica, k)] das pesquisas de salário com página da Catho que esconde a empresa (ou sem PDF)."""
    from . import vagas as V, sessao_catho as SC
    out = []
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            for k, q in enumerate(r.pesquisas):
                ev = q.evidencia
                if ev and SC.eh_catho(ev.url) and (not ev.arquivo or V.empresa_oculta(caminho=db.caminho_absoluto(ev.arquivo))):
                    out.append((r, k))
    return out


async def recapturar_catho(pid, ctx, completar=True):
    """Com a sessão da Catho feita pela OSC: guarda de novo a página de cada vaga da Catho usada no projeto que escondia a empresa (a pesquisa
    fica com o PDF novo e a data de hoje) e, se completar=True, torna válidas as vagas da Catho do banco que faltam para os cargos sem as 3."""
    from . import vagas as V, sessao_catho as SC
    from .calculo import mensal_maximo_rh
    if not SC.tem_sessao():
        raise ValueError('não há sessão da Catho neste computador: use "Entrar na Catho", na tela do projeto')
    p, _ = db.carregar(pid)
    alvos = pesquisas_catho_ocultas(p)
    urls = list(dict.fromkeys(r.pesquisas[k].evidencia.url for r, k in alvos))
    novos, falhas, expirou = {}, {}, False
    for n, url in enumerate(urls):
        ctx.progresso(70 * n / max(1, len(urls)), f'Guardando de novo a página da vaga com a empresa visível ({n + 1} de {len(urls)})')
        try:
            novos[url] = await V.recapturar_no_banco(url, ctx)
        except ValueError as e:
            falhas[url] = str(e)
            if 'expirou' in str(e):
                expirou = True; break
    p, _ = db.carregar(pid)   # relê: a captura é demorada
    mudados = {}
    with db.conectar() as c:
        banco = {row['url']: dict(row) for row in c.execute('SELECT * FROM vaga_banco WHERE url IN (%s)' % ','.join('?' * len(novos)), list(novos))} if novos else {}
    for r, k in pesquisas_catho_ocultas(p):
        q, v = r.pesquisas[k], banco.get(r.pesquisas[k].evidencia.url)
        if not v:
            continue
        with open(db.caminho_absoluto(v['pdf']), 'rb') as f:
            sha, rel = db.guardar_arquivo(pid, f"vaga_Catho_{re.sub(r'[^A-Za-z0-9]+', '_', v['empresa'])[:30]}.pdf", f.read())
        q.evidencia = Evidencia(url=v['url'], arquivo=rel, sha256=sha, capturado_em=v['coletada_em'], origem='navegador')
        q.faixa_min, q.faixa_max, q.valor, q.data_pesquisa = v['faixa_min'], v['faixa_max'], v['faixa_min'], v['coletada_em'][:10]
        mudados[r.item] = r
    completados = []
    if completar and not expirou:   # cargos sem as 3 pesquisas: vagas da Catho do banco (menor salário primeiro), só as que faltam
        for r in [x for x in p.rubricas if isinstance(x, RubricaRH) and not rh_pronto(x)]:
            sim = similares_do_cargo(r)
            ocultas = sorted((v for v in V.banco_com_similares(r.cargo, sim, so_verdes=True)
                              if v['plataforma'] == 'Catho' and V.chave_cargo(v['titulo_busca']) == V.chave_cargo(titulo_em_uso(r))
                              and V.empresa_oculta(caminho=db.caminho_absoluto(v['pdf']))),
                             key=lambda v: v['faixa_min'] or 10 ** 9)
            tentativas = 0
            for v in ocultas:
                if len(V.tres_do_titulo(titulo_em_uso(r))) >= 3 or tentativas >= 6:
                    break
                tentativas += 1
                ctx.progresso(85, f'{r.cargo}: guardando a página de outra vaga da Catho ({v["empresa"]})')
                try:
                    await V.recapturar_no_banco(v['url'], ctx)
                except ValueError as e:
                    falhas[v['url']] = str(e)
                    if 'expirou' in str(e):
                        expirou = True; break
            if expirou:
                break
            antes = sum(1 for q in r.pesquisas if pesquisa_completa(q))
            novas, _ = aplicar_vagas(p, pid, r)
            if novas and sum(1 for q in r.pesquisas if pesquisa_completa(q)) > antes:
                completados.append(r.item); mudados[r.item] = r
    for r in mudados.values():
        maxm, _, _ = mensal_maximo_rh(r, p.config)
        if maxm is not None and (r.valor_mensal_plano is None or r.valor_mensal_plano > maxm):
            r.valor_mensal_plano = maxm
        replicar_pesquisas(p, r)
    v = None
    if mudados:
        v = db.salvar(pid, p, autor='sistema (Catho com login)', tarefa=ctx.id,
                      motivo=f'{len(novos)} página(s) da Catho guardada(s) de novo com as informações da empresa visíveis'
                             + (f'; cargos completados com vagas da Catho: itens {completados}' if completados else ''))
    if expirou:
        ctx.aviso('A sessão da Catho expirou durante o trabalho: entre na Catho de novo pela tela do projeto e repita.')
    for url, motivo in falhas.items():
        if 'expirou' not in motivo:
            ctx.aviso(f'Vaga {url}: {motivo}. Troque por outra vaga do banco na tela do cargo.')
    ctx.progresso(100, 'Concluído')
    return dict(versao=v, recapturadas=len(novos), falhas=len(falhas), completados=completados, ir_para=f'/p/{pid}#mao-de-obra')


# ------------------------------------------------------------------ cargos repetidos → um item com quantidade (pedido da OSC, 02/10/2026)
def cargos_repetidos(p):
    """Grupos de itens de mão de obra iguais (mesmo cargo, forma de contratação, horas, meses e valor no plano) que podem virar um item só."""
    from .regras import norm
    grupos = {}
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            grupos.setdefault((norm(r.cargo), r.regime, r.horas_mes, r.meses, r.valor_mensal_plano), []).append(r)
    return [g for g in grupos.values() if len(g) > 1]


def juntar_cargos(p, pid):
    """Junta os itens repetidos num item só, com a quantidade somada; o total do plano não muda. Os itens são renumerados em sequência
    (1, 2, 3…), e o banco de produtos de cada rubrica acompanha o novo número. Devolve [(item que ficou, itens juntados, quantidade)]."""
    feitos = []
    for g in cargos_repetidos(p):
        fica, saem = g[0], g[1:]
        fica.quantidade = sum(max(1, x.quantidade or 1) for x in g)
        if not any(pesquisa_completa(q) for q in fica.pesquisas):   # se o primeiro não tem pesquisas, fica com as de um repetido que tenha
            com = next((x for x in saem if any(pesquisa_completa(q) for q in x.pesquisas)), None)
            if com:
                fica.pesquisas = com.pesquisas
        ids = {id(x) for x in saem}
        p.rubricas = [x for x in p.rubricas if id(x) not in ids]
        feitos.append((fica.item, [x.item for x in saem], fica.quantidade))
    if feitos:
        mapa = {}
        for n, r in enumerate(p.rubricas, 1):
            if r.item != n:
                mapa[r.item] = n
            r.item = n
        with db.conectar() as c:   # do menor para o maior: o número novo nunca está ocupado por um item que ainda não mudou
            for antigo in sorted(mapa):
                c.execute('UPDATE produto_banco SET item=? WHERE projeto_id=? AND item=?', (mapa[antigo], pid, antigo))
    return feitos


# ------------------------------------------------------------------ vagas
def replicar_pesquisas(p, r):
    """Itens do mesmo cargo usam as mesmas 3 pesquisas (como na grade da SEJC). Horas e meses de cada item não mudam."""
    from .calculo import mensal_maximo_rh
    from .regras import norm
    outros = []
    for x in p.rubricas:
        if isinstance(x, RubricaRH) and x.item != r.item and norm(x.cargo) == norm(r.cargo):
            x.pesquisas = [q.model_copy(deep=True) for q in r.pesquisas]
            x.titulo_em_uso = r.titulo_em_uso
            from .calculo import nivelar_pela_faixa
            if nivelar_pela_faixa(x, p.config):   # o outro item tem a sua faixa: as horas dele seguem a nova média
                outros.append(x.item); continue
            maxm, _, _ = mensal_maximo_rh(x, p.config)
            if maxm is not None and (x.valor_mensal_plano is None or x.valor_mensal_plano > maxm):
                x.valor_mensal_plano = maxm
            outros.append(x.item)
    return outros


def usar_vagas_do_banco(p, pid, r):
    """As (até) 3 vagas do banco para o cargo, todas do TÍTULO EM USO — o do cargo ou o título similar que a OSC escolheu (copia os PDFs
    para o projeto)."""
    from . import vagas as V
    from .calculo import media_para_a_faixa
    return [_pesquisa_da_vaga(pid, v) for v in V.tres_do_titulo(titulo_em_uso(r), media_para_a_faixa(r, p.config))]


def pesquisa_completa(q):
    from . import vagas as V
    return bool(q and q.nome and q.cnpj and (q.faixa_min or q.valor) and q.evidencia and q.evidencia.arquivo
                and not V.empresa_oculta(caminho=db.caminho_absoluto(q.evidencia.arquivo))
                and not (q.evidencia.origem != 'pdf' and V.pdf_nao_e_a_vaga(db.caminho_absoluto(q.evidencia.arquivo))))


def anexar_pdf_vaga(p, pid, r, k, nome_arquivo, conteudo):
    """A OSC anexa a página da vaga em PDF (ex.: impressa da Catho com o login feito, para as informações da empresa aparecerem). Confere o
    que dá: as informações da empresa visíveis (senão recusa), o salário e o nome da empresa no texto. Devolve a mensagem."""
    from . import vagas as V
    from .regras import norm
    if not conteudo.startswith(b'%PDF'):
        raise ValueError('o arquivo enviado não é um PDF')
    if V.empresa_oculta(conteudo):
        raise ValueError(V.MOTIVO_OCULTA + '. Entre na sua conta da Catho, abra a vaga, imprima em PDF (Ctrl+P) e anexe de novo')
    while len(r.pesquisas) < 3:
        r.pesquisas.append(PesquisaSalarial())
    q = r.pesquisas[k]
    sha, rel = db.guardar_arquivo(pid, nome_arquivo, conteudo)
    q.evidencia = Evidencia(arquivo=rel, sha256=sha, url=q.evidencia.url if q.evidencia else None, origem='pdf', capturado_em=db.agora())
    msg = [f'PDF anexado à pesquisa {k + 1} ({q.nome or "empresa não informada"})']
    t = norm(V._texto_pdf(conteudo))
    if len(t) < 200:
        msg.append('o PDF não tem texto (é imagem): confira o salário e a empresa olhando o arquivo')
    else:
        sal = V.conferir_salario_pdf(conteudo, q.faixa_min or q.valor) if (q.faixa_min or q.valor) else None
        if isinstance(sal, tuple):
            msg.append(f'a página mostra outro salário ({_reais(sal[0])}): corrija o salário da pesquisa')
        elif sal is False:
            msg.append(f'o salário {_reais(q.faixa_min or q.valor)} não aparece no PDF: confira')
        elif sal:
            msg.append(f'o salário {_reais(q.faixa_min or q.valor)} aparece no PDF')
        palavras = [w for w in norm(q.nome or '').split() if len(w) > 3][:3]
        if palavras and not all(w in t for w in palavras):
            msg.append('o nome da empresa da pesquisa não aparece no PDF: confira')
    return '; '.join(msg) + '.'


def colocar_vagas(r, novas, titulo=None):
    """Coloca as vagas encontradas nas pesquisas do cargo (pedido da OSC, 02/10/2026: mesmo com 1 ou 2 vagas confirmadas, elas entram).
    Com 3, substituem as 3 pesquisas. Com menos, entram nas primeiras posições; as outras posições ficam com a pesquisa completa que já
    estava (de outra empresa e do MESMO título, ou preenchida à mão) ou em branco: pesquisa de vaga de outro título sai, porque títulos
    diferentes não vão juntos para o orçamento (06/10/2026). Devolve quantas pesquisas ficaram preenchidas."""
    titulo = titulo or r.cargo
    de_outro = [q for q in r.pesquisas if pesquisa_completa(q) and not do_titulo(q, titulo)]
    if not novas and not de_outro:
        return 0
    if len(novas) >= 3:
        r.pesquisas = list(novas[:3])
        return 3
    raizes = {_raiz(q.cnpj) for q in novas}
    mantidas = [q for q in r.pesquisas if pesquisa_completa(q) and _raiz(q.cnpj) not in raizes and do_titulo(q, titulo)]
    r.pesquisas = (list(novas) + mantidas + [PesquisaSalarial(), PesquisaSalarial(), PesquisaSalarial()])[:3]
    return sum(1 for q in r.pesquisas if pesquisa_completa(q))


def aplicar_vagas(p, pid, r):
    """Usa as vagas do banco no cargo (e nos outros itens do mesmo cargo). Devolve (quantas vagas do banco entraram, itens replicados)."""
    from .calculo import mensal_maximo_rh
    from .calculo import nivelar_pela_faixa
    novas = usar_vagas_do_banco(p, pid, r)
    antes = [q.model_dump() for q in r.pesquisas]
    colocar_vagas(r, novas, titulo_em_uso(r))
    maxm, _, _ = mensal_maximo_rh(r, p.config)
    if not nivelar_pela_faixa(r, p.config) and maxm is not None:   # com faixa pretendida, as horas mudam para o valor chegar nela
        r.valor_mensal_plano = maxm
    mudou = antes != [q.model_dump() for q in r.pesquisas]
    return novas, (replicar_pesquisas(p, r) if novas or mudou else [])


def _proxima_vaga(r, k, fora=(), alvo=None):
    """A próxima vaga válida do banco para a pesquisa k, do TÍTULO EM USO, da de menor salário para a maior; de empresa diferente das
    outras duas pesquisas e que não seja uma das vagas em `fora`."""
    from . import vagas as V
    usadas = {q.evidencia.url for j, q in enumerate(r.pesquisas) if j != k and q.evidencia and q.evidencia.url} | set(fora)
    raizes = {_raiz(q.cnpj) for j, q in enumerate(r.pesquisas) if j != k and q.cnpj}
    validas = [v for v in V.candidatas(titulo_em_uso(r)) if v['url'] not in usadas and _raiz(v['cnpj']) not in raizes]
    if r.faixa_pretendida and validas:   # com faixa pretendida: a de menor salário que deixa a média das 3 chegar na faixa (alvo: a média necessária)
        from .regras import media
        outras = [(q.valor if q.valor is not None else q.faixa_min) for j, q in enumerate(r.pesquisas) if j != k]
        if len(outras) == 2 and None not in outras:
            chegam = [v for v in validas if v.get('faixa_min') and media(outras + [v['faixa_min']]) >= (alvo or r.faixa_pretendida)]
            if chegam:
                return chegam[0]
    return validas[0] if validas else None


async def outra_vaga(pid, item, k, ctx):
    """Pedido da OSC (03/10/2026): nova pesquisa de UMA das 3 pesquisas do cargo, sem mexer nas outras duas. A vaga atual sai (é
    descartada do banco, para não voltar) e entra a próxima vaga válida; se o banco não tiver outra, o sistema busca nos sites."""
    from . import vagas as V
    from .calculo import mensal_maximo_rh
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    while len(r.pesquisas) < 3:
        r.pesquisas.append(PesquisaSalarial())
    atual = r.pesquisas[k].evidencia.url if r.pesquisas[k].evidencia else None
    from .calculo import media_para_a_faixa
    alvo = media_para_a_faixa(r, p.config)
    v = _proxima_vaga(r, k, [atual] if atual else [], alvo)
    if v is None:
        ctx.progresso(5, f'Não há outra vaga válida no banco para "{titulo_em_uso(r)}": buscando nos sites')
        tem_outra = lambda: _proxima_vaga(r, k, [atual] if atual else [], alvo) is not None
        await V.coletar(titulo_em_uso(r), ctx, parar=tem_outra)   # só o título em uso: vaga de outro título não entra junto
        v = _proxima_vaga(r, k, [atual] if atual else [], alvo)
    volta = f'/p/{pid}/rh/{item}#pesquisa{k}'
    ctx.progresso(100, 'Concluído')
    if v is None:
        ctx.aviso(f'Não foi encontrada outra vaga válida para a pesquisa {k + 1} de "{r.cargo}" com o título "{titulo_em_uso(r)}" (com CNPJ confirmado, salário '
                  f'definido e de empresa diferente das outras duas). A pesquisa ficou como estava. Você pode confirmar uma vaga "em dúvida", preencher à mão ou '
                  f'trocar as 3 pesquisas pelas vagas de outro título, em "Títulos com vagas".')
        return dict(versao=None, ir_para=volta)
    p, _ = db.carregar(pid)   # a busca é demorada: relê o projeto
    r = _rubrica(p, item)
    while len(r.pesquisas) < 3:
        r.pesquisas.append(PesquisaSalarial())
    antes = r.pesquisas[k].nome or 'em branco'
    if atual:
        try:
            V.descartar_vaga(atual)   # a vaga que a OSC não quis não volta a ser escolhida (dá para "mostrar de novo" no banco)
        except ValueError:
            pass
    r.pesquisas[k] = _pesquisa_da_vaga(pid, v)
    from .calculo import nivelar_pela_faixa
    maxm, _, _ = mensal_maximo_rh(r, p.config)
    if not nivelar_pela_faixa(r, p.config) and maxm is not None:
        r.valor_mensal_plano = maxm
    outros = replicar_pesquisas(p, r)
    ver = db.salvar(pid, p, autor='sistema (vagas)', tarefa=ctx.id,
                    motivo=f'item {item}: pesquisa {k + 1} trocada ({antes} → {r.pesquisas[k].nome}); as outras duas ficaram como estavam'
                           + (f'; replicada para {outros}' if outros else ''))
    return dict(versao=ver, ir_para=volta)


async def recapturar_vaga(pid, item, k, ctx):
    """Guarda de novo a página da vaga da pesquisa k (por exemplo, para sair sem o aviso de cookies por cima). Se o anúncio já foi
    encerrado, a pesquisa fica como estava e o sistema avisa."""
    from . import vagas as V
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    q = r.pesquisas[k]
    url = q.evidencia.url if q.evidencia else None
    volta = f'/p/{pid}/rh/{item}#pesquisa{k}'
    if not url:
        raise ValueError('a pesquisa não tem o link da vaga: sem ele não dá para guardar a página de novo')
    ctx.progresso(20, 'Abrindo a página da vaga')
    try:
        pdf, quando = await asyncio.wait_for(V.capturar(url, f'{r.cargo} | {q.nome} | {q.plataforma or ""}'), 150)
    except V.VagaEncerrada as e:
        ctx.aviso(f'Pesquisa {k + 1} ({q.nome}): {e}. A página guardada antes continua valendo como comprovante da data da pesquisa; '
                  f'se preferir, use "Buscar outra vaga para esta pesquisa".')
        ctx.progresso(100, 'Concluído')
        return dict(versao=None, ir_para=volta)
    problema = None
    if V.empresa_oculta(pdf):
        problema = V.MOTIVO_OCULTA + ' (entre na Catho pela tela do cargo)'
    elif V._pdf_bytes_a_combinar(pdf, q.faixa_min):
        problema = 'a página agora diz "salário a combinar"'
    else:
        sal = V.conferir_salario_pdf(pdf, q.faixa_min or q.valor)
        if sal is False:
            problema = 'o salário da pesquisa não aparece mais na página'
        elif isinstance(sal, tuple):
            q.faixa_min, q.faixa_max, q.valor = sal[0], sal[1], sal[0]
    ctx.progresso(100, 'Concluído')
    if problema:
        ctx.aviso(f'Pesquisa {k + 1} ({q.nome}): {problema}. A página guardada antes foi mantida.')
        return dict(versao=None, ir_para=volta)
    sha, rel = db.guardar_arquivo(pid, f"vaga_{q.plataforma or 'site'}_{re.sub(r'[^A-Za-z0-9]+', '_', q.nome)[:30]}.pdf", pdf)
    q.evidencia = Evidencia(url=url, arquivo=rel, sha256=sha, capturado_em=quando, origem='navegador')
    q.data_pesquisa = quando[:10]
    outros = replicar_pesquisas(p, r)
    ver = db.salvar(pid, p, autor='sistema (vagas)', tarefa=ctx.id,
                    motivo=f'item {item}: página da vaga da pesquisa {k + 1} ({q.nome}) guardada de novo' + (f'; replicada para {outros}' if outros else ''))
    return dict(versao=ver, ir_para=volta)


async def vagas_do_cargo(pid, item, ctx):
    """Busca as vagas do cargo (título exato). Se não chegar a 3 (ou à faixa pretendida), busca também CADA título similar aceito — cada
    título é um grupo à parte. Para o orçamento só vão vagas de UM título (decisão da OSC, 06/10/2026): as do título em uso — o do cargo,
    mesmo que sejam só 1 ou 2, ou o título similar que a OSC escolheu. Os títulos similares com 3 vagas ficam como opção, na tela do cargo."""
    from . import vagas as V
    p, _ = db.carregar(pid)
    r = _rubrica(p, item)
    from .calculo import media_para_a_faixa
    similares, faixa = similares_do_cargo(r), media_para_a_faixa(r, p.config)   # a média que as vagas precisam ter para o valor chegar na faixa
    # com faixa pretendida, a busca de um título só para quando ele tem 3 vagas cuja média chega nela (ou quando as páginas acabam)
    pronto = lambda t: (lambda: V.alcanca_a_faixa(V.tres_do_titulo(t, faixa), faixa)) if faixa else None
    completo = lambda t: V.alcanca_a_faixa(V.tres_do_titulo(t, faixa), faixa)
    res = await V.coletar(r.cargo, ctx, parar=pronto(r.cargo), faixa=faixa)
    usados = []
    if not completo(r.cargo):
        if not similares and r.titulos_similares is None and p.config.usar_ia:
            try:   # cargo fora da lista do sistema: a IA sugere títulos com a mesma função; eles são procurados e viram OPÇÃO (a OSC escolhe)
                ia.titulos_similares(r.cargo, pid)
            except Exception:
                pass
            similares = similares_do_cargo(r)
        for t in similares:
            if not completo(t):
                ctx.etapa(f'Faltam vagas com o título exato{" que cheguem na faixa" if faixa else ""}: buscando o título similar "{t}"')
                await V.coletar(t, ctx, parar=pronto(t), faixa=faixa)
            usados.append(t)
    p, _ = db.carregar(pid)   # a coleta é demorada: relê o projeto para não desfazer o que mudou nesse meio-tempo
    r = _rubrica(p, item)
    antes = [q.model_dump() for q in r.pesquisas]
    novas, outros = aplicar_vagas(p, pid, r)
    em_uso = titulo_em_uso(r)
    if novas or antes != [q.model_dump() for q in r.pesquisas]:
        res['versao'] = db.salvar(pid, p, autor='sistema (vagas)',
                                  motivo=f'item {item}: {len(novas)} vaga(s) do banco (CNPJ confirmado)'
                                  + (f', do título similar "{em_uso}" (escolhido pela OSC)' if V.chave_cargo(em_uso) != V.chave_cargo(r.cargo) else '')
                                  + (f'; replicadas para os itens {outros} (mesmo cargo)' if outros else ''), vagas=[q.evidencia.url for q in novas])
    grupos = [g for g in V.grupos_de_titulos(r.cargo, similares_do_cargo(r), faixa) if V.chave_cargo(g['titulo']) != V.chave_cargo(em_uso)]
    opcoes = [g for g in grupos if g['completo']]
    if len(novas) < 3:
        ctx.aviso(f'{len(novas)} de 3 vagas confirmadas com o título "{em_uso}"' + (f' (procurado também: {", ".join(usados)})' if usados else '')
                  + '. As que faltam ficaram em branco: o sistema continua procurando na coleta diária; você também pode preencher à mão ou '
                    'confirmar uma vaga "em dúvida" do banco.'
                  + (' Títulos com 3 vagas, para você escolher na tela do cargo (vagas de títulos diferentes não vão juntas para o orçamento): '
                     + '; '.join(f'{g["titulo"]} (salários de {_reais(g["vagas"][0]["faixa_min"])} a {_reais(g["vagas"][-1]["faixa_min"])})' for g in opcoes) + '.' if opcoes else '')
                  + (' Ainda sem 3 vagas: ' + ', '.join(f'{g["titulo"]} ({len(g["vagas"])})' for g in grupos if not g['completo'] and g['vagas']) + '.'
                     if any(not g['completo'] and g['vagas'] for g in grupos) else ''))
    elif V.chave_cargo(em_uso) != V.chave_cargo(r.cargo) and completo(r.cargo):
        ctx.aviso(f'O cargo está com as vagas do título similar "{em_uso}", que você escolheu, e agora já há 3 vagas com o título exato "{r.cargo}": '
                  'se quiser, volte para o título do cargo em "Títulos com vagas", na tela do cargo.')
    if r.faixa_pretendida and len(novas) == 3:
        from .calculo import media_rh, horas_pela_faixa
        from .regras import brl
        h = horas_pela_faixa(r, p.config)
        if media_rh(r) is not None and h and media_rh(r) < media_para_a_faixa(r, p.config):
            ctx.aviso(f'As vagas confirmadas de "{r.cargo}" não chegam na faixa pretendida de {brl(r.faixa_pretendida)}: a média das 3 é {brl(media_rh(r))} e, '
                      f'com o máximo de {h[0]} h por mês, o valor fica em {brl(h[1])} (para chegar na faixa, a média precisaria ser de {brl(media_para_a_faixa(r, p.config))}). '
                      f'Use vagas de salário maior (ou de outro título, em "Títulos com vagas"), reduza a faixa ou aumente o máximo de horas na configuração do projeto.')
        elif h:
            ctx.aviso(f'"{r.cargo}": faixa pretendida de {brl(r.faixa_pretendida)} → {h[0]} h por mês, {brl(h[1])} (média das 3 vagas: {brl(media_rh(r))}).')
    res['no_banco'] = len(novas)
    res['ir_para'] = f'/p/{pid}/rh/{item}'
    return res


def base_receita(ctx, forcar=False):
    from . import cnpj_base
    return cnpj_base.atualizar(ctx, forcar)
