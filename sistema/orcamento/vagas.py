"""Pesquisa salarial por vagas publicadas (v0.3), seguindo as regras da SEJC e as decisões da OSC.

- Vagas de QUALQUER região do Brasil (decisão de 25/09): InfoJobs, Catho, Vagas.com, BNE, Empregos.com.br, Trabalha Brasil e LinkedIn (páginas públicas).
- Título EXATO: só variações das mesmas palavras do cargo (gênero, número, "(a)"); "Coordenador de Projetos de TI" não vale.
- Dados do bloco estruturado JobPosting (JSON-LD) da página: título, empresa, faixa salarial, data, cidade/UF, site da empresa.
- Filtros: empresa identificada (sem confidencial, sem agregador — R15), salário mensal ≥ R$ 1.000; valor considerado = MENOR da faixa (R11).
- CNPJ do empregador: base da Receita primeiro, online só quando precisa, com as travas (ver cnpj_busca.py).
- Ordem neutra: as vagas mais recentes primeiro (nunca pelo salário). Três empresas DIFERENTES (R09).
- BANCO DE VAGAS (decisão D7): cada vaga apta com CNPJ 🟢 é guardada com o PDF da página (data, URL e SHA-256), válida por 180 dias;
  a coleta pode rodar todo dia e cargos com poucas vagas (título raro) acumulam vagas com o tempo."""
import asyncio
import datetime as dt
import hashlib
import html as H
import json
import os
import re
from urllib.parse import quote, quote_plus

from .regras import norm

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'
PARADAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'a', 'o', 'para', 'recibo', 'ou', 'mei', 'pj', 'clt'}
CONFIDENCIAL = ('confidencial', 'sigilos', 'nao divulgad', 'não divulgad', '****')
AGREGADORES = ('oemprego', 'vagas brasil', 'emprego ligado', 'trabalha brasil', 'jooble', 'talent.com', 'indeed', 'catho', 'infojobs', 'bne ', 'vagas.com', 'empregos.com')
VALIDADE_DIAS = 180
# "Empresa localizada no bairro X", "Empresa do ramo alimentício", "Empresa nacional": não é o nome de ninguém — é a empresa que não quis se
# identificar, descrita de outro jeito (pesquisa completa de 09/10/2026: o sistema gastava minutos procurando o CNPJ de "Empresa Localizada No
# Bairro…", e uma "Empresa nacional" chegou a casar com uma empresa de verdade que tem esse nome)
EMPRESA_SEM_NOME = re.compile(r'^(?:uma\s+|nossa\s+|grande\s+|renomada\s+)?(?:empresa|industria|loja|escritorio|clinica|instituicao|cliente|companhia)\s+'
                              r'(?:localizad[ao]|situad[ao]|d[oe]\s+ramo|no\s+ramo|d[oe]\s+segmento|no\s+segmento|d[oe]\s+setor|d[ae]\s+area|de\s+(?:pequeno|medio|grande)\s+porte|'
                              r'nacional|multinacional|familiar|parceir[ao]|em\s+expansao|lider|renomad[ao]|conceituad[ao]|solid[ao]|tradicional|privad[ao]|contrata)\b'
                              r'|^(?:nosso|nossa)\s+client|^empresa$|^cliente$')


def _slug(s):
    return re.sub(r'[^a-z0-9]+', '-', norm(s)).strip('-')


# ------------------------------------------------------------------ título exato (regra da OSC, 33/33 casos)
_CONECT = {'de': 'de', 'da': 'de', 'do': 'de', 'das': 'de', 'dos': 'de', 'e': 'e'}
_INVAR = {'assistente', 'auxiliar', 'designer', 'social', 'gerente', 'agente', 'docente', 'estudante', 'recepcionista', 'analista', 'motorista',
          'jornalista', 'artista', 'educador', 'geral', 'tecnico', 'pedagogo'}


def _canonico(t):
    if t in _CONECT:
        return _CONECT[t]
    if t.endswith('oes') or t.endswith('aes'):
        t = t[:-3] + 'ao'
    elif t.endswith('ais') and len(t) > 4:
        t = t[:-3] + 'al'
    elif t.endswith('eis') and len(t) > 4:
        t = t[:-3] + 'el'
    elif t.endswith('res') or t.endswith('zes'):
        t = t[:-2]
    elif t.endswith('s') and len(t) > 3 and not t.endswith('ss'):
        t = t[:-1]
    if t in _INVAR:
        return t
    if t.endswith('ora'):
        return t[:-1]
    if t.endswith('a') and len(t) > 3:
        return t[:-1] + 'o'
    return t


# Entender o título (pedido da OSC, 03/10/2026): o anúncio pode abreviar ("Aux. Administrativo"), pôr a cidade ou o regime junto do título
# ("Auxiliar Administrativo - Zona Sul", "(temporário)", "PCD") ou começar por "Vaga de". Nada disso muda o cargo. Nível (júnior, pleno, I, II),
# especialidade ("Psicólogo Clínico") e chefia continuam sendo OUTRO título.
ABREVIACOES = {'aux': 'auxiliar', 'assist': 'assistente', 'asst': 'assistente', 'adm': 'administrativo', 'admin': 'administrativo', 'coord': 'coordenador',
               'tec': 'tecnico', 'op': 'operador', 'oper': 'operador', 'superv': 'supervisor', 'enc': 'encarregado', 'serv': 'servicos', 'prof': 'professor',
               'enf': 'enfermeiro', 'psic': 'psicologo', 'educ': 'educador', 'orient': 'orientador', 'instr': 'instrutor'}
RUIDO_TITULO = {'vaga', 'urgente', 'pcd', 'clt', 'pj', 'temporario', 'efetivo', 'presencial', 'hibrido', 'remoto', 'home', 'office', 'imediato', 'inicio'}
UFS = set('ac al ap am ba ce df es go ma mt ms mg pa pb pr pe pi rj rn rs ro rr sc sp se to'.split())
_SOLTAS = {'de', 'e'}


def _por_extenso(palavras):
    out = []
    for w in palavras:
        if w == 'ger':   # "Serv. Ger." = serviços gerais; no começo, gerente
            w = 'gerais' if out and out[-1] in ('servicos', 'servico') else 'gerente'
        out.append(ABREVIACOES.get(w, w))
    return out


def tokens_titulo(s):
    s = norm(s)
    s = re.sub(r'\((?:a|o|as|os|es|e)\)|/(?:a|as|o|os)\b', '', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return [_canonico(t) for t in _por_extenso(s.split())]


SEPARADOR_TITULO = r'\s+[-–—]\s+|\s*[|•·]\s*|\s*[()]\s*|\s+/\s+|\s*:\s+'   # o que separa o cargo do resto do título do anúncio


def _sem_vaga_de(titulo):
    t = re.sub(r'\((?:a|o|as|os|es|e)\)', '', norm(titulo))
    return re.sub(r'^\s*vagas?\s+(?:de|para)\s+', '', t)


def titulo_limpo(titulo, cidade=None, uf=None):
    """O título sem o que não faz parte do cargo: "Vaga de", cidade/UF/zona e regime ou modalidade escritos depois de um traço ou entre parênteses."""
    t = _sem_vaga_de(titulo)
    locais = {norm(x) for x in (cidade, uf) if x}
    fica = []
    for i, parte in enumerate(re.split(SEPARADOR_TITULO, t)):
        parte = parte.strip(' -–|/')
        if not parte:
            continue
        palavras = set(_canonico(w) for w in re.findall(r'[a-z0-9]+', parte))
        if i and (palavras <= RUIDO_TITULO or parte in locais or parte in UFS or re.fullmatch(r'zona (norte|sul|leste|oeste)|centro|regiao .{3,30}|grande .{3,30}', parte)
                  or (locais and all(p in ' '.join(locais) for p in parte.split()))):
            continue
        fica.append(parte)
    return ' '.join(fica)


def extensao_do_titulo(titulo):
    """('coordenador de projetos', 'sao paulo') para "Coordenador de Projetos | São Paulo": o começo do título e a "extensão" que vem depois
    de um separador (traço, barra, dois-pontos, parênteses). ('…', '') quando o título não tem extensão."""
    partes = [p.strip(' -–—|/:') for p in re.split(SEPARADOR_TITULO, _sem_vaga_de(titulo))]
    partes = [p for p in partes if p]
    return (partes[0], ' - '.join(partes[1:])) if partes else ('', '')


def titulo_exato(titulo, cargo, cidade=None, uf=None):
    """O título do anúncio é o cargo? Mesmas palavras, na mesma ordem — sem contar gênero, plural, "de"/"e", abreviações e o que titulo_limpo tira.
    Vale também o cargo seguido de uma EXTENSÃO qualquer (decisão da OSC, 06/10/2026): "Coordenador de Projetos | São Paulo",
    "Psicólogo - Coca-Cola", "Orientador Socioeducativo - Educação". Palavra a mais ANTES do separador continua sendo outro título
    ("Psicólogo Clínico - Hospital", "Coordenador de Projetos de TI")."""
    c = [t for t in tokens_titulo(cargo) if t not in _SOLTAS]
    ruido = RUIDO_TITULO - set(c)
    limpo = lambda s: [t for t in tokens_titulo(s) if t not in _SOLTAS and t not in ruido]
    if limpo(titulo_limpo(titulo, cidade, uf)) == c:
        return True
    comeco, extensao = extensao_do_titulo(titulo)
    return bool(extensao) and limpo(comeco) == c


def cargo_para_busca(cargo):
    """O cargo como se digita na busca dos sites de vagas: sem "(a)", sem o que está entre parênteses, sem regime e carga horária, e por extenso."""
    t = re.sub(r'\((?:a|o|as|os|es|e)\)', '', cargo or '', flags=re.I)
    t = re.sub(r'\([^)]*\)', ' ', t)
    t = re.sub(r'\b\d+\s*(?:h|hs|horas?)\b(?:\s*(?:semanais|mensais|por semana|por m[eê]s))?', ' ', t, flags=re.I)
    t = re.sub(r'\b(?:recibo|mei|pj|clt)\b(?:\s+ou\s+(?:recibo|mei|pj|clt)\b)*', ' ', t, flags=re.I)
    palavras = [ABREVIACOES.get(norm(w.strip('.')), w) if w.endswith('.') or norm(w) in ('aux', 'adm', 'coord', 'assist') else w for w in t.split()]
    return re.sub(r'\s+', ' ', ' '.join(palavras)).strip(' -–|/,.') or (cargo or '').strip()


def chave_cargo(cargo):
    return ' '.join(tokens_titulo(cargo))


def palavras_cargo(cargo):
    return [w for w in re.findall(r'[a-z]+', norm(cargo)) if w not in PARADAS and len(w) > 2]


def titulo_confere(titulo, cargo):
    """Pré-filtro barato (todas as palavras do cargo no texto do link); a decisão final é titulo_exato()."""
    t = ' '.join(_por_extenso(re.findall(r'[a-z0-9]+', norm(titulo))))
    return all(re.search(r'\b' + w[:max(5, len(w) - 2)], t) for w in palavras_cargo(cargo_para_busca(cargo)))


# ------------------------------------------------------------------ leitura da vaga
def _jobposting(html):
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        itens = d if isinstance(d, list) else ([d] + d.get('@graph', []) if isinstance(d, dict) else [])
        for x in itens:
            if isinstance(x, dict) and 'JobPosting' in str(x.get('@type')):
                return x
    return None


def _cent(v):
    try:
        return round(float(str(v).replace(',', '.')) * 100)
    except Exception:
        return None


SALARIO_TXT = re.compile(r'sal[aá]rio(?:\s+(?:base|mensal|fixo))?\s*(?:de|:|-)?\s*R\$\s?(\d{1,3}(?:\.\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)(?!\d)', re.I)


def valor_texto(t):
    """'1.727,27' → 172727; '1.727.27' (ponto no lugar da vírgula, como aparece em anúncios) → 172727; '2000' → 200000."""
    t = t.strip()
    if re.fullmatch(r'\d{1,3}(\.\d{3})*,\d{2}|\d+,\d{2}', t):
        return int(t.replace('.', '').replace(',', ''))
    if re.fullmatch(r'\d{1,3}(\.\d{3})+\.\d{2}|\d+\.\d{2}', t):
        return int(t.replace('.', ''))
    if re.fullmatch(r'\d{1,3}(\.\d{3})+|\d+', t):
        return int(t.replace('.', '')) * 100
    return None


A_COMBINAR = re.compile(r'(sal[aá]rio|remunera[cç][aã]o|faixa salarial|valor)[^.\n]{0,25}\ba\s+combinar|\ba\s+combinar\b[^.\n]{0,15}sal[aá]rio', re.I)


def a_combinar(texto):
    """'Salário: a combinar' (vaga sem salário definido: não pode entrar no orçamento — decisão da OSC, 27/09/2026)."""
    return bool(A_COMBINAR.search(re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', texto or '')))))


def a_combinar_na_vaga(texto, centavos=None):
    """A página guardada diz 'salário a combinar' para ESTA vaga? Páginas de vaga listam vagas parecidas no fim, e uma delas pode ser
    'a combinar': se o salário registrado aparece na página ANTES do primeiro 'a combinar', o 'a combinar' é de outra vaga."""
    t = re.sub(r'\s+', ' ', texto or '')
    m = A_COMBINAR.search(t)
    if not m:
        return False
    return not (centavos and salario_no_texto(t[:m.start()], centavos))


_PDF_COMBINAR = {}


def _texto_pdf(pdf=None, caminho=None):
    try:
        import pymupdf
        d = pymupdf.open(caminho) if caminho else pymupdf.open(stream=pdf, filetype='pdf')
        return re.sub(r'\s+', ' ', ''.join(pg.get_text() for pg in d))
    except Exception:
        return ''


_TEXTO_PDF = {}

# A SEJC pede que a página da vaga mostre as informações da empresa (pedido de 02/10/2026). A Catho só as mostra para quem está logado:
# sem login, a página traz o nome e "Cadastre-se gratuitamente para ver mais informações da empresa".
EMPRESA_OCULTA = re.compile(r'cadastre-se gratuitamente para ver mais informa[cç][oõ]es da empresa', re.I)
MOTIVO_OCULTA = 'a página da vaga não mostra as informações da empresa (a Catho só as mostra para quem está logado)'


def sessao_ok():
    from . import sessao_catho as SC
    return SC.tem_sessao()


async def recapturar_no_banco(url, ctx=None):
    """Guarda de novo, com a sessão da Catho, a página de uma vaga do banco cujo PDF escondia a empresa. Confere salário, "a combinar" e vaga
    encerrada. Devolve o caminho do PDF novo, ou levanta ValueError com o motivo."""
    from . import db, sessao_catho as SC
    if not SC.tem_sessao():
        raise ValueError('não há sessão da Catho neste computador: entre na Catho pela tela do projeto')
    with db.conectar() as c:
        row = c.execute('SELECT * FROM vaga_banco WHERE url=?', (url,)).fetchone()
    if not row:
        raise ValueError('a vaga não está mais no banco de vagas')
    v = dict(row)
    pdf, _ = await asyncio.wait_for(SC.capturar(url, f"{v['cargo']} | {v['empresa']} | {v['plataforma']}", v['empresa']), 150)
    t = _texto_pdf(pdf)
    if pagina_nao_e_a_vaga(t):
        raise ValueError(pagina_nao_e_a_vaga(t))
    if empresa_oculta(pdf):
        SC.marcar_expirada()
        raise ValueError('a sessão da Catho expirou (a página continua escondendo a empresa): entre na Catho de novo')
    if _pdf_bytes_a_combinar(pdf, v.get('faixa_min')):
        raise ValueError('a página da vaga diz "salário a combinar"')
    fmin, fmax = v['faixa_min'], v['faixa_max']
    achado = conferir_salario_pdf(pdf, fmin)
    if isinstance(achado, tuple):
        fmin, fmax = achado
    elif achado is False:
        raise ValueError('o salário registrado não aparece mais na página da vaga')
    sha = hashlib.sha256(pdf).hexdigest()
    rel = '/'.join(['banco_vagas', f'{sha[:12]}_{_slug(v["empresa"])[:30]}.pdf'])
    ab = os.path.join(_pasta_banco(), os.path.basename(rel))
    if not os.path.exists(ab):
        with open(ab, 'wb') as f:
            f.write(pdf)
    with db.conectar() as c:
        c.execute('UPDATE vaga_banco SET pdf=?, sha256=?, faixa_min=?, faixa_max=?, coletada_em=?, valida_ate=? WHERE url=?',
                  (rel, sha, fmin, fmax, db.agora(), (dt.date.today() + dt.timedelta(days=VALIDADE_DIAS)).isoformat(), url))
    return rel


def empresa_oculta(pdf=None, caminho=None):
    """A página guardada esconde as informações da empresa? (texto do PDF; a evidência guardada é lida uma vez só)"""
    if caminho and pdf is None:
        if caminho not in _TEXTO_PDF:
            _TEXTO_PDF[caminho] = _texto_pdf(None, caminho)
        t = _TEXTO_PDF[caminho]
    else:
        t = _texto_pdf(pdf, caminho)
    return bool(EMPRESA_OCULTA.search(t))


def conferir_salario_pdf(pdf=None, centavos=None, caminho=None):
    """Confere o salário com a página guardada. True = o valor aparece; (min, max) = a página mostra OUTRO salário no bloco "Salário"
    (vale o da página); False = o valor não aparece; None = PDF sem texto (não dá para conferir)."""
    if caminho and pdf is None:   # evidência guardada não muda (o nome traz o SHA-256): o texto é lido uma vez só
        if caminho not in _TEXTO_PDF:
            _TEXTO_PDF[caminho] = _texto_pdf(None, caminho)
        t = _TEXTO_PDF[caminho]
    else:
        t = _texto_pdf(pdf, caminho)
    if len(t) < 200:
        return None
    if centavos and centavos in salarios_no_texto(t):   # o valor está escrito na página como salário (no campo do site ou no texto da vaga)
        return True
    m = SALARIO_PDF.search(t)
    exib = ler_salario(m.group(1)) if m else None
    if isinstance(exib, tuple) and centavos and exib[0] != centavos:
        return exib
    if centavos and salario_no_texto(t, centavos):
        return True
    return False if centavos else None


def corrigir_banco_pela_pagina():
    """Vagas já guardadas: se a página (PDF) mostra um salário diferente do registrado, vale o da página. Devolve quantas mudaram."""
    from . import db
    n = 0
    with db.conectar() as c:
        linhas = [dict(r) for r in c.execute('SELECT url, faixa_min, faixa_max, pdf FROM vaga_banco WHERE pdf IS NOT NULL')]
    for r in linhas:
        achado = conferir_salario_pdf(caminho=db.caminho_absoluto(r['pdf']), centavos=r['faixa_min'])
        if isinstance(achado, tuple):
            with db.conectar() as c:
                c.execute('UPDATE vaga_banco SET faixa_min=?, faixa_max=? WHERE url=?', (achado[0], achado[1], r['url']))
            n += 1
    return n


def _pdf_bytes_a_combinar(pdf, centavos=None):
    try:
        import pymupdf
        return a_combinar_na_vaga(''.join(pg.get_text() for pg in pymupdf.open(stream=pdf, filetype='pdf')), centavos)
    except Exception:
        return False


def pdf_a_combinar(caminho, centavos=None):
    """A página guardada da vaga diz 'salário a combinar'? (vale para vagas coletadas antes desta regra)"""
    k = (caminho, centavos)
    if k not in _PDF_COMBINAR:
        try:
            import pymupdf
            _PDF_COMBINAR[k] = a_combinar_na_vaga(''.join(pg.get_text() for pg in pymupdf.open(caminho)), centavos)
        except Exception:
            _PDF_COMBINAR[k] = False
    return _PDF_COMBINAR[k]


NAO_MENSAL = re.compile(r'\s*(?:reais\s*)?(?:/|por|a|ao|p/)\s*(?:hora|h\b|dia|di[aá]ria|aula|plant[aã]o|semana|quinzena|ano)', re.I)


def salarios_no_texto(descricao):
    """Salários MENSAIS escritos no texto da vaga ("Salário: R$ 1.727,27"), em centavos. "R$ 25,00 por hora" (ou por dia, aula, plantão,
    semana) não é salário mensal e fica de fora."""
    txt = re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', descricao or '')))
    out = []
    for m in SALARIO_TXT.finditer(txt):
        v = valor_texto(m.group(1))
        if v and not NAO_MENSAL.match(txt[m.end():m.end() + 25]):
            out.append(v)
    return out


def usar_salario_do_texto(v):
    """Decisão da OSC (06/10/2026): quando o TEXTO da vaga cita o salário, vale o do texto (é o que a empresa escreveu), mesmo que o campo
    de salário do site diga outro valor. Com mais de um valor no texto, a faixa vai do menor ao maior (R11: conta o menor)."""
    txt = [x for x in v.get('salarios_texto') or [] if x]
    if txt and not v.get('a_combinar') and (min(txt), max(txt)) != (v.get('faixa_min'), v.get('faixa_max')):
        v['faixa_min'], v['faixa_max'], v['salario_da'], v['unidade'] = min(txt), max(txt), 'texto', None
    return v


SALARIO_TEXTO = r'(A combinar|A partir de R\$\s?[\d.]+(?:,\d{2})?|De R\$\s?[\d.]+(?:,\d{2})? a R\$\s?[\d.]+(?:,\d{2})?|At[eé] R\$\s?[\d.]+(?:,\d{2})?|R\$\s?[\d.]+(?:,\d{2})?)'
# Catho: o bloco do salário da vaga (ícone i_salary); os dados estruturados só trazem a FAIXA cadastrada (2.001 a 3.000), e a página
# mostra o salário real ("R$ 2.300", "A partir de R$ 3.000,00"). Caso real apontado pela OSC em 01/10/2026.
SALARIO_HTML = re.compile(r'class="icon i_salary"></span>\s*(?:<strong>)?\s*' + SALARIO_TEXTO, re.I)
SALARIO_PDF = re.compile(r'Sal[aá]rio\s+' + SALARIO_TEXTO, re.I)


def ler_salario(texto):
    """'R$ 2.300' → (230000, 230000); 'A partir de R$ 3.000,00' → (300000, 300000); 'De R$ 2.001,00 a R$ 3.000,00' → (200100, 300000);
    'A combinar' → 'a combinar'; 'Até R$ 3.000' → 'sem mínimo' (não define o salário). None se não for um salário."""
    t = (texto or '').strip()
    if re.match(r'a combinar', t, re.I):
        return 'a combinar'
    vs = [valor_texto(v) for v in re.findall(r'R\$\s?([\d.]+(?:,\d{2})?)', t)]
    vs = [v for v in vs if v]
    if not vs:
        return None
    if re.match(r'at[eé]', t, re.I):
        return 'sem mínimo'
    return (vs[0], vs[1]) if len(vs) > 1 else (vs[0], vs[0])


def salario_exibido(html):
    """Salário que a PÁGINA da vaga mostra (hoje: Catho). None se a página não tiver um bloco de salário reconhecido."""
    m = SALARIO_HTML.search(html or '')
    return ler_salario(m.group(1)) if m else None


def salario_no_texto(texto, centavos):
    """O valor aparece no texto da página? ('2.300', '2.300,00', '2300', 'R$2300,00')"""
    r, c = divmod(int(centavos), 100)
    milhar = f'{r:,}'.replace(',', '.')
    pad = r'(?<![\d.,])(?:' + re.escape(milhar) + '|' + str(r) + ')' + (r'(?:,00)?' if c == 0 else f',{c:02d}') + r'(?!\d|,\d|\.\d{3})'   # 2.300 não é 2.300,50
    t = (texto or '').replace('\xa0', ' ')
    if re.search(pad, t) is not None:
        return True
    # há site que escreve o valor do jeito americano: "R$2,295.00" (vírgula no milhar, ponto nos centavos) — Empregos.com.br, 08/10/2026
    return r >= 1000 and re.search(r'(?<![\d.,])' + re.escape(f'{r:,}') + rf'\.{c:02d}(?!\d)', t) is not None


def _extrai(jp):
    org = jp.get('hiringOrganization') or {}
    loc = jp.get('jobLocation') or {}
    loc = loc[0] if isinstance(loc, list) and loc else loc
    addr = (loc or {}).get('address') or {}
    sal = jp.get('baseSalary') or {}
    val = sal.get('value') if isinstance(sal, dict) else None
    if isinstance(val, dict):
        vmin, vmax, unid = val.get('minValue') or val.get('value'), val.get('maxValue') or val.get('value'), val.get('unitText')
    else:
        vmin = vmax = val; unid = None
    site = org.get('sameAs') or org.get('url') if isinstance(org, dict) else None
    return dict(titulo=(jp.get('title') or '').strip(), empresa=(org.get('name') if isinstance(org, dict) else org) or '',
                cidade=addr.get('addressLocality') if isinstance(addr, dict) else None,
                uf=addr.get('addressRegion') if isinstance(addr, dict) else None,
                site_empresa=(site[0] if isinstance(site, list) and site else site) or None,
                faixa_min=_cent(vmin), faixa_max=_cent(vmax), unidade=(unid or '').upper() or None, faixa_bruta=[vmin, vmax],
                data=(jp.get('datePosted') or '')[:10] or None, tipo=jp.get('employmentType'),
                salarios_texto=salarios_no_texto(jp.get('description')), a_combinar=a_combinar(jp.get('description')),
                cnpjs_texto=cnpjs_no_texto(jp.get('description')))


def cnpjs_no_texto(descricao):
    """CNPJs escritos no texto da vaga (a empresa às vezes se identifica ali): só números, sem repetir."""
    txt = H.unescape(re.sub(r'<[^>]+>', ' ', descricao or ''))
    return list(dict.fromkeys(re.sub(r'\D', '', x) for x in re.findall(r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b', txt)))


def texto_visivel(html):
    """O texto que a pessoa vê na página: sem os blocos de programa e de estilo (onde os números dos dados da vaga também aparecem) e sem as marcações."""
    return H.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>', ' ', html or '')))


PISO_PLAUSIVEL = 10000   # R$ 100,00: abaixo disso não é salário mensal — é erro de leitura do anúncio


def milhar_com_ponto(v, texto_da_pagina):
    """Há site que põe nos dados da vaga "2.2" para R$ 2.200 (o ponto do milhar virou vírgula decimal — Empregos.com.br, 08/10/2026). Um salário
    mensal de menos de R$ 100 é lido de novo como milhar SÓ se a página mostrar esse valor por extenso (R$ 2.200,00 ou R$2,200.00); senão, a
    vaga fica sem salário (não entra)."""
    if not v.get('faixa_min') or v['faixa_min'] >= PISO_PLAUSIVEL or v.get('salario_da') or (v.get('unidade') or 'MONTH') not in ('MONTH', 'MES', 'MÊS'):
        return v
    def mil(bruto, cent):   # 2.295 (o valor como veio) → 229500 centavos; sem o valor como veio, o que foi lido × 1000
        try:
            return round(float(str(bruto).replace(',', '.')) * 100000)
        except (TypeError, ValueError):
            return cent * 1000
    bruta = v.get('faixa_bruta') or [None, None]
    mn, mx = mil(bruta[0], v['faixa_min']), mil(bruta[1], v.get('faixa_max') or v['faixa_min'])
    if salario_no_texto(texto_da_pagina, mn):
        v['faixa_min'], v['faixa_max'], v['salario_da'] = mn, mx if salario_no_texto(texto_da_pagina, mx) else mn, 'página (milhar)'
    else:
        v['faixa_min'] = v['faixa_max'] = None
    return v


def avaliar(v, cargo):
    """Motivo de exclusão (ou None se a vaga serve como pesquisa salarial)."""
    if not titulo_exato(v['titulo'], cargo, v.get('cidade'), v.get('uf')):
        return f'título "{v["titulo"]}" não é exatamente o cargo'
    e = norm(v['empresa'])
    if not v['empresa'] or any(k in e for k in CONFIDENCIAL) or EMPRESA_SEM_NOME.search(e):
        return 'empresa confidencial/não identificada'
    if any(k in e for k in AGREGADORES):
        return 'publicada por agregador, não pela empresa (R15)'
    usar_salario_do_texto(v)
    if not v['faixa_min']:
        return 'sem salário informado'
    if v.get('a_combinar'):
        return 'salário a combinar (não pode entrar no orçamento)'
    if v.get('faixa_max') and v['faixa_max'] > 5 * v['faixa_min']:   # ex.: BNE "a combinar" publica R$ 1.000 a R$ 15.000
        return f'faixa salarial genérica (R$ {v["faixa_min"] // 100} a R$ {v["faixa_max"] // 100}): provável "a combinar"'
    if v['unidade'] and v['unidade'] not in ('MONTH', 'MES', 'MÊS'):
        return f'salário por {v["unidade"]}, não mensal'
    if v['faixa_min'] < PISO_PLAUSIVEL:
        return 'salário mensal de menos de R$ 100: erro de leitura do anúncio'
    return None   # qualquer salário mensal vale (decisão da OSC, 06/10/2026: não há mais o mínimo de R$ 1.000); o salário do texto já foi aplicado


def sugerir(vagas, n=3):
    """Sugestão neutra: as mais recentes de empresas distintas (R09). Não escolhe pelos maiores salários."""
    escolha, empresas = [], set()
    for i, v in enumerate(vagas):
        e = norm(re.sub(r'\b(ltda|s/?a|me|eireli|epp)\b', '', v['empresa'], flags=re.I))
        if v['apta'] and e not in empresas:
            escolha.append(i); empresas.add(e)
        if len(escolha) == n:
            break
    return escolha


# ------------------------------------------------------------------ busca no Brasil
CIDADES_TRABALHA_BRASIL = ['sao-paulo-sp', 'rio-de-janeiro-rj', 'belo-horizonte-mg', 'curitiba-pr', 'porto-alegre-rs', 'salvador-ba', 'brasilia-df', 'fortaleza-ce']


def fontes(cargo, profundo=False):
    cargo = cargo_para_busca(cargo)
    s = _slug(cargo); q = quote(cargo); L = []
    for pg in ((4, 5, 6) if profundo else (1, 2, 3)):
        L.append(('InfoJobs', f'https://www.infojobs.com.br/vagas-de-emprego-{s}.aspx' + (f'?page={pg}' if pg > 1 else ''), r'infojobs\.com\.br/vaga-de-.+__\d+\.aspx'))
    for pg in ((3, 4, 5) if profundo else (1, 2)):
        L.append(('Catho', f'https://www.catho.com.br/vagas/{s}/' + (f'?page={pg}' if pg > 1 else ''), r'catho\.com\.br/vagas/[^/]+/\d+'))
        L.append(('Vagas.com', f'https://www.vagas.com.br/vagas-de-{s}' + (f'?pagina={pg}' if pg > 1 else ''), r'vagas\.com\.br/vagas/v\d+'))
    if not profundo:
        L.append(('BNE', f'https://www.bne.com.br/vagas-de-emprego-para-{s}', r'bne\.com\.br/vaga-de-emprego-na-area-[^?#]+/\d+'))
        # incluído em 08/10/2026 (pedido da OSC: melhorar a busca): a página da vaga traz título, empresa e salário, e abre sem verificação humana.
        # Sondados e deixados de fora: Indeed e Glassdoor (a página não traz os dados da vaga de forma legível) e Jooble (recusa o acesso)
        L.append(('Empregos.com.br', f'https://www.empregos.com.br/vagas/{s}', r'empregos\.com\.br/vaga/\d+'))
    # Trabalha Brasil (incluído em 08/10/2026, depois de nova sondagem pedida pela OSC): a busca é por CIDADE; a página da vaga traz título,
    # empresa e salário (6 de 6 na amostra) e abre sem verificação humana. Gupy (quase nunca informa salário) e Sólides (a lista de vagas não é
    # legível sem o aplicativo do site) ficaram de fora.
    for cid in (CIDADES_TRABALHA_BRASIL[4:] if profundo else CIDADES_TRABALHA_BRASIL[:4]):
        L.append(('Trabalha Brasil', f'https://www.trabalhabrasil.com.br/vagas-de-emprego-em-{cid}/{s}', r'trabalhabrasil\.com\.br/vagas-de-emprego-em-[^/]+/[^/?#]+/\d+'))
    for st in ((75, 100, 125) if profundo else (0, 25, 50)):
        L.append(('LinkedIn', f'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={q}&location={quote("Brasil")}&start={st}',
                  r'linkedin\.com/jobs/view/[^?#]+'))
    return L


def titulo_do_endereco(url):
    """O último trecho do endereço de uma vaga, com espaços no lugar dos traços ('.../vaga/123/auxiliar-administrativo-em-atibaia-sp')."""
    trecho = [x for x in re.split(r'[/?#]', url or '') if re.search(r'[a-z]{4,}-[a-z]', x)]
    return re.sub(r'[-_]+', ' ', trecho[-1]) if trecho else ''


INTERVALO_PLATAFORMA = 3.0   # segundos entre acessos à mesma plataforma de vagas


async def buscar_brasil(br, cargo, ctx=None, profundo=False, ignorar=(), pct=(0, 50)):
    """Lê as listas das plataformas e as páginas das vagas candidatas. Devolve todas as vagas lidas, com 'apta' e 'motivo'."""
    sem = asyncio.Semaphore(6)
    fs = fontes(cargo, profundo)
    feitas = 0

    def prog(etapa):
        if ctx:
            ctx.progresso(pct[0] + (pct[1] - pct[0]) * feitas / max(1, total), etapa)
    travas, prox = {}, {}

    async def vez(plat):
        """Intervalo mínimo entre acessos à MESMA plataforma (rajadas fazem o site bloquear o endereço, inclusive para o navegador da OSC)."""
        import time
        async with travas.setdefault(plat, asyncio.Lock()):
            espera = prox.get(plat, 0) - time.monotonic()
            if espera > 0:
                await asyncio.sleep(espera)
            prox[plat] = time.monotonic() + INTERVALO_PLATAFORMA

    async def lista(plat, url, pat):
        nonlocal feitas
        async with sem:
            c = await br.new_context(locale='pt-BR', user_agent=UA); p = await c.new_page()
            try:
                await vez(plat)
                await asyncio.wait_for(p.goto(url, timeout=40000, wait_until='domcontentloaded'), 50); await p.wait_for_timeout(3500)
                pares = await p.eval_on_selector_all('a[href]', 'els=>els.map(e=>[e.href,(e.innerText||"").trim()])')
                out = [(plat, h.split('?')[0], t) for h, t in pares if re.search(pat, h)]
                if ctx:
                    ctx.fonte(plat, 'ok')
            except Exception as e:
                out = []
                if ctx:
                    ctx.fonte(plat, 'falhou', type(e).__name__)
            await c.close()
        feitas += 1; prog(f'Lendo as listas de vagas ({feitas}/{total})')
        return out
    total = len(fs)
    brutos = sum(await asyncio.gather(*[lista(*f) for f in fs]), [])
    vistos = {}
    for plat, u, t in brutos:
        vistos.setdefault(u, (plat, t))
    # o título costuma estar no texto do link; há site em que o link só diz "Mais detalhes" e o título está no próprio endereço
    # (empregos.com.br/vaga/123/auxiliar-administrativo-em-atibaia-sp): vale o que conferir
    cands = [(p, u) for u, (p, t) in vistos.items() if u not in ignorar and (not t or titulo_confere(t.split('\n')[0], cargo) or titulo_confere(t, cargo) or titulo_confere(titulo_do_endereco(u), cargo))]
    feitas, total = 0, len(cands)

    async def detalhe(plat, u):
        nonlocal feitas
        async with sem:
            c = await br.new_context(locale='pt-BR', user_agent=UA); p = await c.new_page()
            html = ''
            try:
                await vez(plat)
                await asyncio.wait_for(p.goto(u, timeout=40000, wait_until='domcontentloaded'), 50); await p.wait_for_timeout(1800)
                html = await p.content()
                jp = _jobposting(html)
            except Exception:
                jp = None
            await c.close()
        feitas += 1; prog(f'Lendo as vagas candidatas ({feitas}/{total})')
        if not jp:
            return None
        v = dict(_extrai(jp), plataforma=plat, url=u)
        exib = salario_exibido(html)   # vale o salário que a página mostra (é o que o PDF comprova)
        if exib == 'a combinar':
            v['a_combinar'] = True
        elif exib == 'sem mínimo':
            v['faixa_min'] = None
        elif exib:
            v['faixa_min'], v['faixa_max'], v['salario_da'] = exib[0], exib[1], 'página'
        texto = texto_visivel(html)
        milhar_com_ponto(v, texto)
        if plat == 'Trabalha Brasil' and v.get('faixa_min') and not v.get('salario_da') and not salario_no_texto(texto, v['faixa_min']):
            # quando a empresa não informa o salário ("a combinar"), este site põe nos dados da vaga uma faixa ESTIMADA para o cargo (a mesma
            # faixa em vagas de empresas diferentes): só vale o salário que a página da vaga mostra
            v['faixa_min'] = v['faixa_max'] = None
        v['motivo'] = avaliar(v, cargo); v['apta'] = v['motivo'] is None
        return v
    res = [v for v in await asyncio.gather(*[detalhe(p, u) for p, u in cands]) if v]
    aptas = sorted([v for v in res if v['apta']], key=lambda v: v['data'] or '', reverse=True)   # mais recentes primeiro (neutro)
    return aptas + [v for v in res if not v['apta']], len(vistos)


# ------------------------------------------------------------------ evidência
class VagaEncerrada(ValueError):
    """O endereço da vaga não mostra mais o anúncio (o site redirecionou para a busca, mostrou a lista de vagas ou avisou que encerrou)."""


LISTA_DE_VAGAS = re.compile(r'\b\d+\s+resultados\b|Salvar busca|Vagas de emprego de \w|Filtrar vagas', re.I)


def pagina_nao_e_a_vaga(texto, empresa=None):
    """None se o texto é o da página do anúncio; senão, o motivo (vaga encerrada, lista de vagas no lugar do anúncio, empresa ausente)."""
    t = texto or ''
    if VAGA_ENCERRADA.search(t):
        return 'a vaga foi encerrada no site'
    if LISTA_DE_VAGAS.search(t[:4000]):
        return 'o site mostrou a lista de vagas no lugar do anúncio (vaga encerrada)'
    if empresa:
        palavras = [w for w in re.findall(r'[a-z0-9]+', norm(empresa)) if len(w) > 2 and w not in ('ltda', 'eireli', 'epp', 'the')][:2]
        if palavras and not all(w in norm(t) for w in palavras):
            return f'a página guardada não mostra a empresa do anúncio ({empresa})'
    return None


_PDF_VAGA = {}


def pdf_nao_e_a_vaga(caminho):
    """O PDF guardado NÃO é a página do anúncio? Devolve o motivo ou None (PDF sem texto: não dá para dizer, então None)."""
    if caminho not in _PDF_VAGA:
        t = _texto_pdf(None, caminho)
        _PDF_VAGA[caminho] = pagina_nao_e_a_vaga(t) if len(t) >= 200 else None
    return _PDF_VAGA[caminho]


# Propaganda no MEIO do anúncio (InfoJobs: a faixa "Assine a Conta Premium", com imagem, entre a descrição e as exigências da vaga). Não é
# uma janela por cima, então o LIMPAR não a tira; ela atrapalha a leitura do comprovante. É só ocultada: nada é clicado. Vale para faixa
# com imagem e quase sem texto, cujo endereço ou classe diz que é promoção, plano pago ou publicidade.
SEM_PROPAGANDA = r"""()=>{const fora=[];
for(const a of document.querySelectorAll('a[class*=promo i],a[href*=premium i],a[class*=banner i],a[class*=publi i],a[class*=advert i],[class*=publicidade i],[data-ad-slot]')){
  if(a.id==='faixa-orcamento'||a.closest('#faixa-orcamento'))continue;
  const r=a.getBoundingClientRect(), txt=(a.innerText||'').trim();
  if(r.width>=250&&r.height>=60&&txt.length<60&&(a.querySelector('img,picture,svg,iframe')||a.tagName==='IFRAME')){a.style.setProperty('display','none','important');fora.push((a.className||a.tagName).toString().slice(0,40));}
}
return fora;}"""


async def capturar_no_contexto(c, url, rotulo, empresa=None):
    """PDF da página da vaga, num contexto de navegador já aberto, com faixa de identificação (data/hora + URL). Devolve (bytes, capturado_em).
    A página é guardada como aparece na tela, sem os avisos sobrepostos (cookies, propaganda: são só ocultados, nada é clicado), e só
    vale se for a do anúncio: se o site redirecionar para a busca ou mostrar a lista de vagas, levanta VagaEncerrada."""
    from .produtos.evidencia import limpar, FAIXA
    p = await c.new_page()
    try:
        await asyncio.wait_for(p.goto(url, timeout=60000, wait_until='domcontentloaded'), 70); await p.wait_for_timeout(3500)
        ids = re.findall(r'\d{5,}', url)
        if ids and ids[-1] not in p.url:
            raise VagaEncerrada('o site redirecionou o endereço da vaga para outra página (vaga encerrada)')
        problema = pagina_nao_e_a_vaga(await p.inner_text('body'), empresa)
        if problema:
            raise VagaEncerrada(problema)
        agora = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        try:
            await p.emulate_media(media='screen')
        except Exception:
            pass
        await limpar(p)
        await p.evaluate(FAIXA, f'PESQUISA SALARIAL | {rotulo} | capturado em {agora} | {url}')
        await p.wait_for_timeout(700)
        await limpar(p)   # aviso que aparece com atraso
        try:
            await p.evaluate(SEM_PROPAGANDA)
        except Exception:
            pass
        return await p.pdf(print_background=True, page_ranges='1-2'), agora
    finally:
        await p.close()


async def capturar_pdf(br, url, rotulo, empresa=None):
    """PDF da página da vaga. Catho com a sessão da OSC (feita por ela): só assim a página mostra as informações da empresa."""
    from . import sessao_catho as SC
    if SC.eh_catho(url) and SC.tem_sessao():
        return await SC.capturar(url, rotulo, empresa)
    c = await br.new_context(locale='pt-BR', user_agent=UA, viewport={'width': 1280, 'height': 1000})
    try:
        return await capturar_no_contexto(c, url, rotulo, empresa)
    finally:
        await c.close()


async def capturar(url, rotulo, empresa=None):
    from playwright.async_api import async_playwright
    from . import sessao_catho as SC
    if SC.eh_catho(url) and SC.tem_sessao():
        return await SC.capturar(url, rotulo, empresa)
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        try:
            return await capturar_pdf(br, url, rotulo, empresa)
        finally:
            await br.close()


def link_busca_cnpj(empresa):
    return 'https://www.google.com/search?q=' + quote_plus(f'CNPJ "{empresa}"')


# ------------------------------------------------------------------ banco de vagas
def _pasta_banco():
    from . import db
    p = os.path.join(db.PASTA_DADOS, 'banco_vagas'); os.makedirs(p, exist_ok=True)
    return p


def guardar_no_banco(cargo, v, cnpj=None, pdf=None):
    from . import db
    sha = rel = None
    if pdf:
        sha = hashlib.sha256(pdf).hexdigest()
        rel = '/'.join(['banco_vagas', f'{sha[:12]}_{_slug(v["empresa"])[:30]}.pdf'])
        ab = os.path.join(_pasta_banco(), os.path.basename(rel))   # cria a pasta na primeira vaga guardada
        if not os.path.exists(ab):
            with open(ab, 'wb') as f:
                f.write(pdf)
    hoje = dt.date.today()
    with db.conectar() as c:
        antes = c.execute('SELECT cnpj_motivo, descartada_em FROM vaga_banco WHERE url=?', (v['url'],)).fetchone()
        if antes and (antes['descartada_em'] or (antes['cnpj_motivo'] or '').startswith(CONFIRMADA_PELA_OSC)):
            return   # a OSC já decidiu sobre esta vaga (confirmou o CNPJ ou descartou): a coleta não muda a decisão
        c.execute("""INSERT OR REPLACE INTO vaga_banco (url, cargo_chave, cargo, titulo, empresa, cidade, uf, faixa_min, faixa_max, plataforma, data_vaga,
                     coletada_em, valida_ate, cnpj, cnpj_status, cnpj_motivo, razao, pdf, sha256, json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (v['url'], chave_cargo(cargo), cargo, v['titulo'], v['empresa'], v.get('cidade'), v.get('uf'), v.get('faixa_min'), v.get('faixa_max'),
                   v['plataforma'], v.get('data'), db.agora(), (hoje + dt.timedelta(days=VALIDADE_DIAS)).isoformat(),
                   (cnpj or {}).get('cnpj'), (cnpj or {}).get('status'), (cnpj or {}).get('motivo'), (cnpj or {}).get('razao_social'),
                   rel, sha, json.dumps(dict(v, cnpj_resultado=cnpj), ensure_ascii=False, default=str)))


_banco_corrigido = False


def vagas_do_banco(cargo, so_validas=True, so_verdes=True, descartadas=False):
    from . import db
    global _banco_corrigido
    if not _banco_corrigido:   # uma vez por execução: salários do banco conferidos com a página guardada
        _banco_corrigido = True
        try:
            corrigir_banco_pela_pagina()
        except Exception:
            pass
    q = 'SELECT * FROM vaga_banco WHERE cargo_chave=?' + ('' if descartadas else ' AND descartada_em IS NULL')
    args = [chave_cargo(cargo)]
    if so_validas:
        q += ' AND valida_ate >= ?'; args.append(dt.date.today().isoformat())
    if so_verdes:
        q += " AND cnpj_status='🟢' AND pdf IS NOT NULL"
    q += ' ORDER BY coletada_em DESC, data_vaga DESC'
    with db.conectar() as c:
        return [dict(r) for r in c.execute(q, args)]


def candidatas(cargo):
    """Vagas do banco que podem entrar no orçamento (válidas, CNPJ 🟢, PDF, salário definido), da de MENOR salário para a maior."""
    from . import db
    for v in sorted(vagas_do_banco(cargo), key=lambda v: (v['faixa_min'] or 10 ** 9, v['coletada_em'] or '')):
        if v.get('pdf') and pdf_a_combinar(db.caminho_absoluto(v['pdf']), v.get('faixa_min')):
            continue
        try:
            j = json.loads(v.get('json') or '{}')
        except ValueError:
            j = {}
        if j.get('titulo') and avaliar(j, cargo):   # reavaliada com as regras atuais (vaga guardada antes de uma regra nova)
            continue
        if v.get('pdf') and empresa_oculta(caminho=db.caminho_absoluto(v['pdf'])):   # a SEJC pede as informações da empresa visíveis
            continue
        if v.get('pdf') and pdf_nao_e_a_vaga(db.caminho_absoluto(v['pdf'])):          # o PDF guardado é a lista de vagas, não o anúncio
            continue
        yield v


def _raiz(cnpj):
    return re.sub(r'\D', '', cnpj or '')[:8]


def tres_do_banco(cargo):
    """As 3 vagas de MENOR salário do banco (decisão da OSC, 27/09/2026), de empresas DIFERENTES (raiz do CNPJ), válidas e com CNPJ 🟢."""
    escolhidas, raizes = [], set()
    for v in candidatas(cargo):
        r = _raiz(v['cnpj'])
        if r and r not in raizes:
            raizes.add(r); escolhidas.append(v)
        if len(escolhidas) == 3:
            break
    return escolhidas


# ------------------------------------------------------------------ títulos similares (pedido da OSC, 02/10/2026)
# Cargo de título difícil de achar (ex.: orientador socioeducativo): vagas de títulos com a mesma função completam as 3 pesquisas.
# O título exato vem sempre primeiro; o similar só entra quando falta vaga, e a verificação aponta cada um (regra S04) para a OSC conferir.
SIMILARES = {
    'Orientador socioeducativo': ['Educador social', 'Orientador social', 'Agente social', 'Educador socioeducativo', 'Facilitador de oficinas', 'Oficineiro'],
    'Educador social': ['Orientador socioeducativo', 'Orientador social', 'Agente social', 'Educador socioeducativo'],
    'Orientador social': ['Educador social', 'Orientador socioeducativo', 'Agente social'],
    'Agente social': ['Educador social', 'Orientador social', 'Orientador socioeducativo'],
    'Educador socioeducativo': ['Orientador socioeducativo', 'Educador social', 'Agente socioeducativo'],
    'Oficineiro': ['Instrutor de oficinas', 'Facilitador de oficinas', 'Arte educador', 'Educador social'],
    'Facilitador de oficinas': ['Oficineiro', 'Instrutor de oficinas', 'Educador social'],
    'Instrutor de oficinas': ['Oficineiro', 'Facilitador de oficinas', 'Arte educador'],
    'Arte educador': ['Oficineiro', 'Instrutor de artes', 'Educador social'],
    'Coordenador de projetos': ['Coordenador de projetos sociais', 'Coordenador de programas', 'Gerente de projetos'],
    'Coordenador pedagógico': ['Coordenador educacional', 'Supervisor pedagógico'],
    'Auxiliar de serviços gerais': ['Auxiliar de limpeza', 'Agente de limpeza'],
    'Auxiliar administrativo': ['Assistente administrativo'],
    'Assistente administrativo': ['Auxiliar administrativo'],
    'Designer gráfico': ['Designer', 'Diagramador'],
    'Instrutor de informática': ['Professor de informática', 'Monitor de informática'],
}
_SIMILARES = {chave_cargo(k): v for k, v in SIMILARES.items()}


def sugestoes_similares(cargo):
    """Títulos com a mesma função: os da lista do sistema e, para os outros cargos, os que a IA já sugeriu (a OSC é quem aceita)."""
    fixos = list(_SIMILARES.get(chave_cargo(cargo or ''), []))
    if fixos or not cargo:
        return fixos
    from . import ia
    return [t for t in ia.titulos_similares_guardados(cargo) if chave_cargo(t) != chave_cargo(cargo)]


def outros_titulos(cargo, similares):
    """Os títulos similares aceitos, sem repetir o próprio cargo nem títulos iguais."""
    vistos, out = {chave_cargo(cargo or '')}, []
    for t in similares or ():
        k = chave_cargo(t)
        if t.strip() and k not in vistos:
            vistos.add(k); out.append(t.strip())
    return out


def alcanca_a_faixa(vagas, faixa):
    """As 3 vagas têm média igual ou maior que a faixa pretendida? (sem faixa: basta serem 3)"""
    from .regras import media
    return len(vagas) == 3 and (not faixa or media([v['faixa_min'] for v in vagas]) >= faixa)


def tres_do_titulo(titulo, faixa=None):
    """As (até) 3 vagas de UM título — o cargo ou um título similar —, de empresas diferentes: as de menor salário. Com faixa pretendida
    (decisão da OSC, 05/10/2026): as de menor salário cuja média ainda chega na faixa; se nenhuma combinação chega, as 3 de menor salário
    (quem chama avisa). Vagas de títulos diferentes NUNCA entram juntas (decisão da OSC, 06/10/2026)."""
    import itertools
    from .regras import media
    padrao = tres_do_banco(titulo)
    if not faixa or alcanca_a_faixa(padrao, faixa):
        return padrao
    cands = [v for v in candidatas(titulo) if v.get('faixa_min') and _raiz(v['cnpj'])]
    cands.sort(key=lambda v: abs(v['faixa_min'] - faixa))   # as mais próximas da faixa bastam para achar a menor média que chega nela
    melhor = None
    for trio in itertools.combinations(cands[:40], 3):
        sal = sorted(v['faixa_min'] for v in trio)
        if len({_raiz(v['cnpj']) for v in trio}) < 3 or media(sal) < faixa:
            continue
        chave = (sum(sal), sal)
        if melhor is None or chave < melhor[0]:
            melhor = (chave, trio)
    return sorted(melhor[1], key=lambda v: v['faixa_min']) if melhor else padrao


def tres_na_faixa(cargo, similares=(), faixa=None):
    """As 3 vagas do TÍTULO DO CARGO para a faixa pretendida (os títulos similares são outros grupos: ver grupos_de_titulos)."""
    return tres_do_titulo(cargo, faixa)


def grupos_de_titulos(cargo, similares=(), faixa=None):
    """Um grupo por título: o do cargo primeiro, depois cada título similar aceito. Cada grupo traz as suas (até) 3 vagas — as que iriam para
    o orçamento se o grupo fosse o escolhido. Só grupo COMPLETO (3 vagas de empresas diferentes) pode ser oferecido como opção."""
    out = []
    for t, similar in [(cargo, False)] + [(t, True) for t in outros_titulos(cargo, similares)]:
        tres = [dict(v, similar=similar, titulo_busca=t) for v in tres_do_titulo(t, faixa)]
        out.append(dict(titulo=t, similar=similar, vagas=tres, completo=len(tres) == 3, chega=alcanca_a_faixa(tres, faixa)))
    return out


def grupo_do_titulo(titulo_vaga, cargo, similares=()):
    """De que grupo é uma vaga, pelo título do anúncio: o cargo, um dos títulos similares aceitos, ou None (não é de nenhum)."""
    for t in [cargo] + outros_titulos(cargo, similares):
        if titulo_vaga and titulo_exato(titulo_vaga, t):
            return t
    return None


def banco_com_similares(cargo, similares=(), so_verdes=False, descartadas=False):
    """Vagas guardadas do cargo e dos títulos similares aceitos (tabela da tela do cargo). 'similar' marca as de outro título."""
    vistas, out = set(), []
    for t, similar in [(cargo, False)] + [(t, True) for t in outros_titulos(cargo, similares)]:
        for v in vagas_do_banco(t, so_verdes=so_verdes, descartadas=descartadas):
            if v['url'] not in vistas:
                vistas.add(v['url']); out.append(dict(v, similar=similar, titulo_busca=t))
    return out


# ------------------------------------------------------------------ decisão da OSC sobre uma vaga do banco (pedido de 02/10/2026)
CONFIRMADA_PELA_OSC = 'confirmado pela OSC'
VAGA_ENCERRADA = re.compile(r'vaga (n[aã]o est[aá] mais dispon[ií]vel|encerrada|expirada)|esta vaga (foi )?(encerrada|expirou)|'
                            r'n[aã]o est[aá] mais dispon[ií]vel|an[uú]ncio (encerrado|expirado)', re.I)


def descartar_vaga(url, descartar=True):
    """A OSC descarta (ou volta a mostrar) uma vaga do banco. A vaga descartada não aparece na tela nem entra nas pesquisas."""
    from . import db
    with db.conectar() as c:
        n = c.execute('UPDATE vaga_banco SET descartada_em=? WHERE url=?', (db.agora() if descartar else None, url)).rowcount
    if not n:
        raise ValueError('a vaga não está mais no banco de vagas')


def mostrar_descartadas(cargo, similares=()):
    """Volta a mostrar as vagas descartadas do cargo (e dos títulos similares). Devolve quantas."""
    from . import db
    chaves = [chave_cargo(cargo)] + [chave_cargo(t) for t in outros_titulos(cargo, similares)]
    with db.conectar() as c:
        return c.execute(f'UPDATE vaga_banco SET descartada_em=NULL WHERE descartada_em IS NOT NULL AND cargo_chave IN ({",".join("?" * len(chaves))})',
                         chaves).rowcount


def contar_descartadas(cargo, similares=()):
    from . import db
    chaves = [chave_cargo(cargo)] + [chave_cargo(t) for t in outros_titulos(cargo, similares)]
    with db.conectar() as c:
        return c.execute(f'SELECT count(*) FROM vaga_banco WHERE descartada_em IS NOT NULL AND cargo_chave IN ({",".join("?" * len(chaves))})',
                         chaves).fetchone()[0]


async def confirmar_vaga(url, cnpj, ctx=None):
    """A OSC confirma a empresa de uma vaga "em dúvida" (ou sem CNPJ encontrado): o CNPJ tem de ser válido e ATIVO, e a página da vaga é
    guardada em PDF agora (se ainda não estava), com o salário conferido. Só então a vaga passa a poder entrar no orçamento."""
    from . import db, cnpj_base
    from . import cnpj as cnpjmod
    from .regras import cnpj_dv_ok, cnpj_formatar
    with db.conectar() as c:
        row = c.execute('SELECT * FROM vaga_banco WHERE url=?', (url,)).fetchone()
    if not row:
        raise ValueError('a vaga não está mais no banco de vagas')
    v = dict(row)
    num = re.sub(r'\D', '', cnpj or v.get('cnpj') or '')
    if len(num) != 14 or not cnpj_dv_ok(num):
        raise ValueError('CNPJ inválido: confira os 14 números (o dígito verificador não confere)')
    if ctx:
        ctx.progresso(10, f'Conferindo a situação do CNPJ {cnpj_formatar(num)}')
    base = cnpj_base.por_cnpj(num)
    if base:
        situacao, razao, origem = 'ATIVA', base.get('razao') or base.get('fantasia'), 'base oficial da Receita'
    else:
        q = await asyncio.to_thread(cnpjmod.consultar, num, True)
        situacao, razao, origem = q.get('situacao'), q.get('razao_social'), q.get('fonte') or 'consulta pública'
    if situacao != 'ATIVA':
        raise ValueError(f'o CNPJ {cnpj_formatar(num)} está com situação {(situacao or "não confirmada (nenhuma consulta respondeu)").lower()}: '
                         f'só entra empresa ATIVA (R07)')
    faixa_min, faixa_max, rel, sha = v['faixa_min'], v['faixa_max'], v.get('pdf'), v.get('sha256')
    if not rel:
        if ctx:
            ctx.progresso(40, 'Guardando a página da vaga em PDF')
        try:
            pdf, _ = await asyncio.wait_for(capturar(url, f"{v['cargo']} | {v['empresa']} | {v['plataforma']}", v['empresa']), 150)
        except VagaEncerrada as ex:
            raise ValueError(f'{ex}: a página já não mostra o anúncio e, sem ela, não há comprovante. Use outra vaga')
        texto = _texto_pdf(pdf)
        if pagina_nao_e_a_vaga(texto):
            raise ValueError('a vaga foi encerrada no site: a página já não mostra o anúncio e, sem ela, não há comprovante. Use outra vaga')
        if _pdf_bytes_a_combinar(pdf, faixa_min):
            raise ValueError('a página da vaga diz "salário a combinar": não pode entrar no orçamento')
        if empresa_oculta(pdf):
            raise ValueError(MOTIVO_OCULTA + ': a SEJC pede essas informações visíveis. Use outra vaga ou anexe a página impressa com o login feito')
        achado = conferir_salario_pdf(pdf, faixa_min)
        if isinstance(achado, tuple):
            faixa_min, faixa_max = achado
        elif achado is False:
            valor = f'{faixa_min / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
            raise ValueError(f'o salário registrado (R$ {valor}) não aparece na página da vaga: confira no site')
        sha = hashlib.sha256(pdf).hexdigest()
        rel = '/'.join(['banco_vagas', f'{sha[:12]}_{_slug(v["empresa"])[:30]}.pdf'])
        ab = os.path.join(_pasta_banco(), os.path.basename(rel))
        if not os.path.exists(ab):
            with open(ab, 'wb') as f:
                f.write(pdf)
    motivo = (f'{CONFIRMADA_PELA_OSC} em {dt.date.today().strftime("%d/%m/%Y")}: CNPJ ATIVO ({origem})'
              + (f'; a busca automática tinha ficado em dúvida: {v["cnpj_motivo"]}' if v.get('cnpj_motivo') else ''))
    with db.conectar() as c:
        c.execute('UPDATE vaga_banco SET cnpj=?, cnpj_status=?, cnpj_motivo=?, razao=?, pdf=?, sha256=?, faixa_min=?, faixa_max=?, descartada_em=NULL '
                  'WHERE url=?', (num, '🟢', motivo, razao or v.get('razao'), rel, sha, faixa_min, faixa_max, url))
    if ctx:
        ctx.progresso(100, 'Concluído')
    return dict(empresa=v['empresa'], cnpj=cnpj_formatar(num), razao=razao, salario=faixa_min)


async def coletar(cargo, ctx=None, alvo=3, parar=None, faixa=None):
    """Busca no Brasil + CNPJ + PDF das vagas aptas com CNPJ 🟢, guardando tudo no banco de vagas.
    Para quando o banco tiver `alvo` vagas válidas de empresas diferentes; se faltar, lê as páginas seguintes das plataformas.
    faixa: o cargo tem faixa salarial pretendida — as vagas de salário mais perto dela (primeiro as que chegam nela) são conferidas antes."""
    import httpx
    from playwright.async_api import async_playwright
    import time
    from . import tarefas
    from .cnpj_busca import Api, cnpj_do_empregador, cnpj_pela_base
    lidas, tentadas, verdes, urls = 0, 0, 0, set()
    corrigir_banco_pela_pagina()
    async with async_playwright() as pw, httpx.AsyncClient(timeout=20, headers={'User-Agent': 'orcamento-osc/0.3'}) as c:
        br = await pw.chromium.launch(); api = Api(c)
        try:
            for profundo in (False, True):
                ja = len(tres_do_banco(cargo))
                if (parar() if parar else ja >= alvo):   # parar: condição própria de quem chamou (ex.: já há outra vaga para trocar uma pesquisa)
                    break
                vs, n_links = await buscar_brasil(br, cargo, ctx, profundo, urls, pct=(0, 45) if not profundo else (70, 80))
                aptas = [v for v in vs if v['apta']]
                lidas += len(vs); urls |= {v['url'] for v in vs}
                empresas_vistas = set()
                # menores salários primeiro; a Catho por último: sem login, a página dela esconde as informações da empresa (não serve para a SEJC)
                aptas.sort(key=lambda v: (v['plataforma'] == 'Catho' and not sessao_ok(),
                                          ((v['faixa_min'] or 0) < faixa, abs((v['faixa_min'] or 0) - faixa)) if faixa else (v['faixa_min'] or 10 ** 9)))
                # Primeiro as empresas que a base da Receita resolve NA HORA (a consulta online leva minutos por empresa); depois as outras, e só
                # enquanto puderem mudar o resultado: sem faixa, uma vaga de salário igual ou maior que o das 3 já confirmadas não entra em nenhum
                # caso, então não é consultada. As 3 escolhidas continuam sendo as de MENOR salário entre as válidas (teste real de 08/10/2026:
                # 11 empresas consultadas online para um cargo, 2 a 4 minutos cada, e só 1 confirmada).
                rapidas, lentas = [], []
                for v in aptas:
                    try:
                        na_hora = bool(v.get('cnpjs_texto')) or cnpj_pela_base(v['empresa'], v.get('cidade'), v.get('uf')) is not None
                    except Exception:
                        na_hora = False
                    (rapidas if na_hora else lentas).append(v)
                for i, v in enumerate(rapidas + lentas):
                    tres = tres_do_banco(cargo)
                    if parar:
                        if parar():
                            break
                    elif len(tres) >= alvo and (v['faixa_min'] or 0) >= max(t['faixa_min'] or 0 for t in tres):
                        continue   # não melhora o resultado: fica sem consulta
                    e = norm(v['empresa'])
                    if e in empresas_vistas:
                        continue
                    empresas_vistas.add(e)
                    if ctx:
                        ctx.progresso((45 if not profundo else 80) + (25 if not profundo else 15) * i / max(1, len(aptas)),
                                      f'Conferindo o CNPJ de "{v["empresa"]}" ({i + 1}/{len(aptas)} vagas aptas)')
                    for volta in (0, 1):
                        inicio = time.time()
                        try:
                            k = await asyncio.wait_for(cnpj_do_empregador(br, api, v['empresa'], v.get('cidade'), v.get('uf'), v.get('site_empresa'), ctx,
                                                                          cnpjs_texto=v.get('cnpjs_texto') or ()), 240)
                            break
                        except Exception as ex:
                            k = dict(status='🔴', cnpj=None, motivo=f'erro {type(ex).__name__}')
                            if volta or not await tarefas.depois_da_espera(inicio):   # o computador entrou em modo de espera no meio: a consulta é refeita
                                break
                    tentadas += 1
                    pdf = None
                    if k.get('status') == '🟢':
                        verdes += 1
                        for volta in (0, 1):
                            inicio = time.time()
                            try:
                                pdf, _ = await asyncio.wait_for(capturar_pdf(br, v['url'], f"{cargo} | {v['empresa']} | {v['plataforma']}", v['empresa']), 90)
                                break
                            except VagaEncerrada as ex:
                                pdf = None; k = dict(k, status='🔴', motivo=str(ex)); verdes -= 1
                                break
                            except Exception:
                                pdf = None
                                if volta or not await tarefas.depois_da_espera(inicio):
                                    break
                        if pdf and _pdf_bytes_a_combinar(pdf, v.get('faixa_min')):   # a página diz "salário a combinar" (os dados da vaga não dizem)
                            k = dict(k, status='🔴', motivo='a página da vaga diz "salário a combinar"'); verdes -= 1
                        elif pdf:
                            if v['plataforma'] == 'Catho' and empresa_oculta(pdf) and sessao_ok():   # com sessão e a empresa escondida: a sessão expirou
                                from . import sessao_catho as SC
                                SC.marcar_expirada()
                                if ctx:
                                    ctx.aviso('A sessão da Catho expirou: as páginas da Catho voltaram a esconder a empresa. Entre na Catho de novo pela tela do projeto.')
                            achado = conferir_salario_pdf(pdf, v['faixa_min'])
                            if isinstance(achado, tuple):      # a página mostra outro salário: vale o da página
                                v['faixa_min'], v['faixa_max'], v['salario_da'] = achado[0], achado[1], 'página (PDF)'
                            elif achado is False:
                                k = dict(k, status='🔴', motivo=f'o salário registrado (R$ {v["faixa_min"] / 100:.2f}) não aparece na página da vaga'); verdes -= 1
                    try:
                        guardar_no_banco(cargo, v, k, pdf)
                    except OSError as ex:   # falha de disco numa vaga não derruba a coleta inteira
                        if ctx:
                            ctx.aviso(f'Não foi possível guardar a vaga de "{v["empresa"]}" no banco: {type(ex).__name__} — {ex}')
        finally:
            await br.close()
    tres = tres_do_banco(cargo)
    if ctx:
        ctx.progresso(100, 'Concluído')
        if len(tres) < alvo and not parar:
            ctx.aviso(f'Só {len(tres)} vaga(s) com título exato e CNPJ confirmado no banco para "{cargo}". O sistema continua procurando '
                      f'nas próximas coletas (vagas válidas por {VALIDADE_DIAS} dias).')
    return dict(cargo=cargo, lidas=lidas, cnpj_consultados=tentadas, cnpj_verdes=verdes, no_banco=len(tres), vagas=tres)
