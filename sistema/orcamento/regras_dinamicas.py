"""Regras PRÓPRIAS de um órgão: tipos de regra que o sistema sabe conferir, preenchidos pela tela (pedido da OSC, 05/10/2026).

Uma regra própria é um TIPO daqui mais os parâmetros que a pessoa escreveu no cadastro do órgão. Não há regra de órgão no código: para
"só empresas de SP", cria-se uma regra do tipo `uf_empresas` com `ufs = SP`. Para o que nenhum tipo cobre, há dois tipos em texto livre:
`lembrete` (uma pessoa confere em cada projeto) e `ia` (a IA gratuita confere o plano contra o texto, e o resultado fica guardado — a IA nunca
é consultada ao abrir uma tela, só quando a pessoa pede ou numa tarefa).

conferir(p, orgao) devolve [(código, gravidade, onde, mensagem)]; calculo.verificar transforma em pontos da verificação."""
import hashlib
import json
import re

from .modelo import RubricaRH, descricao_completa, fontes_do_subitem
from .regras import brl, cnpj_formatar

UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split()
PERMANENTES = ('computador, notebook, tablet, celular, impressora, scanner, projetor, televisor, televisão, monitor, câmera, caixa de som, microfone, '
               'geladeira, freezer, fogão, micro-ondas, bebedouro, ventilador, ar-condicionado, móvel, móveis, mesa, cadeira, armário, estante, sofá, arquivo de aço, '
               'veículo, bicicleta, instrumento musical, máquina de costura, ferramenta elétrica')

# campos de cada tipo: (nome, rótulo, forma, ajuda) — forma: lista | texto | longo | inteiro | moeda | percentual | opcao:a=Rótulo;b=Rótulo
TIPOS = {
    'uf_empresas': dict(
        nome='Empresas só de determinados estados',
        descricao='As empresas das pesquisas (quem contrata, a loja, o fornecedor) precisam ser dos estados indicados. O estado vem do cadastro oficial do CNPJ.',
        campos=[('ufs', 'Estados aceitos', 'lista', 'As siglas, separadas por vírgula. Ex.: SP, RJ'),
                ('aplica', 'Vale para', 'opcao:todos=Vagas, produtos e serviços;rh=Só mão de obra;materiais=Só materiais e serviços', '')]),
    'palavras_proibidas': dict(
        nome='Itens que não podem constar (ex.: material permanente)',
        descricao='Nenhum item do plano pode ter estas palavras na descrição. Serve para material permanente, bebida alcoólica, premiação em dinheiro etc.',
        campos=[('palavras', 'Palavras', 'longo', 'Separadas por vírgula. Plural e acento não fazem diferença. Para material permanente, uma lista pronta: ' + PERMANENTES),
                ('alvo', 'Onde procurar', 'opcao:itens=Nos itens das rubricas;cargos=Nos cargos;ambos=Nos dois', '')]),
    'percentual_maximo': dict(
        nome='Um grupo não pode passar de uma parte do total',
        descricao='A soma de um grupo de despesas (toda a mão de obra, todos os materiais, ou as rubricas cujo nome tem um texto) fica até um percentual do total do plano.',
        campos=[('grupo', 'Grupo', 'opcao:rh=Mão de obra;materiais=Materiais, sistemas e serviços;rubrica=Rubricas cujo nome contém o texto abaixo', ''),
                ('texto', 'Texto do nome da rubrica', 'texto', 'Só para o grupo "rubricas cujo nome contém". Ex.: alimentação'),
                ('pct', 'Percentual máximo', 'percentual', 'Ex.: 60')]),
    'valor_maximo': dict(
        nome='Valor máximo',
        descricao='Teto de valor para cada item (valor unitário), cada cargo (valor mensal por profissional) ou cada rubrica (valor mensal).',
        campos=[('alvo', 'O que tem teto', 'opcao:item=Cada item (unitário);cargo=Cada cargo (mensal por profissional);rubrica=Cada rubrica (mensal)', ''),
                ('valor', 'Valor máximo', 'moeda', ''),
                ('texto', 'Só nos que têm este texto no nome', 'texto', 'Opcional. Em branco, vale para todos.')]),
    'duracao_maxima': dict(
        nome='Duração máxima',
        descricao='Nenhum cargo ou rubrica pode durar mais que um número de meses.',
        campos=[('meses', 'Meses', 'inteiro', 'Ex.: 12')]),
    'lembrete': dict(
        nome='Regra em texto, conferida por uma pessoa',
        descricao='Para o que o sistema não consegue conferir sozinho. O texto aparece na verificação de todo projeto do órgão, e alguém marca como revisado.',
        campos=[('texto', 'O que precisa ser conferido', 'longo', 'Ex.: O plano de trabalho precisa trazer a assinatura do responsável técnico.')]),
    'ia': dict(
        nome='Regra em texto, conferida pela IA',
        descricao='A IA gratuita lê a regra e a lista de itens do plano e aponta o que parece descumprir. É um apoio: o ponto entra sempre como "para revisar", '
                  'com o motivo. A IA recebe os itens, quantidades, valores e nomes das empresas do plano (não o nome da organização nem o do projeto).',
        campos=[('texto', 'A regra, com as palavras do órgão', 'longo', 'Ex.: Não são permitidas despesas com coffee break que passem de R$ 20,00 por pessoa.')]),
}


def _sa(s):
    from .produtos.identidade import sa
    return sa(s)


def _raizes(texto):
    from .produtos.identidade import raiz
    return [raiz(w) for w in re.findall(r'[a-z0-9]+', _sa(texto))]


def _lista(v):
    return [x.strip() for x in re.split(r'[,;\n]+', v if isinstance(v, str) else ','.join(map(str, v or []))) if x.strip()]


def campos_do_formulario(tipo, parametros=None):
    """Os campos do tipo prontos para a tela: nome, rótulo, forma, ajuda, opções e o valor atual."""
    out = []
    for nome, rotulo, forma, ajuda in TIPOS[tipo]['campos']:
        v = (parametros or {}).get(nome)
        opcoes = [tuple(o.split('=', 1)) for o in forma.split(':', 1)[1].split(';')] if forma.startswith('opcao:') else []
        if forma in ('lista', 'longo') and isinstance(v, list):
            v = ', '.join(map(str, v))
        out.append(dict(nome=nome, rotulo=rotulo, forma=forma.split(':')[0], ajuda=ajuda, opcoes=opcoes, valor='' if v is None else v))
    return out


def ler_parametros(tipo, form, centavos, inteiro):
    """O que a tela mandou, no formato de cada campo. centavos/inteiro: os leitores de valor do sistema. ValueError se faltar o essencial."""
    p = {}
    for nome, rotulo, forma, _ in TIPOS[tipo]['campos']:
        bruto = (form.get(f'p_{nome}') or '').strip()
        if forma == 'lista':
            p[nome] = [x.upper() for x in _lista(bruto)]
        elif forma == 'inteiro':
            p[nome] = inteiro(bruto, 0)
        elif forma == 'percentual':
            p[nome] = float(bruto.replace('%', '').replace(',', '.') or 0)
        elif forma == 'moeda':
            p[nome] = centavos(bruto) or 0
        elif forma.startswith('opcao:'):
            validas = [o.split('=')[0] for o in forma.split(':', 1)[1].split(';')]
            p[nome] = bruto if bruto in validas else validas[0]
        else:
            p[nome] = bruto
    faltam = {'uf_empresas': not p.get('ufs'), 'palavras_proibidas': not _lista(p.get('palavras', '')), 'percentual_maximo': not p.get('pct'),
              'valor_maximo': not p.get('valor'), 'duracao_maxima': not p.get('meses'), 'lembrete': not p.get('texto'), 'ia': not p.get('texto')}
    if faltam.get(tipo):
        raise ValueError('preencha os campos da regra')
    if tipo == 'uf_empresas' and [u for u in p['ufs'] if u not in UFS]:
        raise ValueError('estado que não existe: ' + ', '.join(u for u in p['ufs'] if u not in UFS))
    return p


def resumo_da_regra(r):
    """Uma linha dizendo o que a regra confere (para a lista de regras do órgão)."""
    p, t = r.parametros, r.tipo
    if t == 'uf_empresas':
        return 'empresas de ' + ', '.join(p.get('ufs', [])) + {'rh': ' (mão de obra)', 'materiais': ' (materiais e serviços)'}.get(p.get('aplica'), '')
    if t == 'palavras_proibidas':
        ps = _lista(p.get('palavras', ''))
        return f'{len(ps)} palavra(s) proibida(s): ' + ', '.join(ps[:6]) + ('…' if len(ps) > 6 else '')
    if t == 'percentual_maximo':
        g = {'rh': 'mão de obra', 'materiais': 'materiais, sistemas e serviços'}.get(p.get('grupo'), f'rubricas com "{p.get("texto", "")}"')
        return f'{g} até {str(p.get("pct", 0)).rstrip("0").rstrip(".").replace(".", ",")}% do total'
    if t == 'valor_maximo':
        a = {'item': 'cada item', 'cargo': 'cada cargo (mensal)', 'rubrica': 'cada rubrica (mensal)'}.get(p.get('alvo'), 'cada item')
        return f'{a} até {brl(p.get("valor", 0))}' + (f', nos que têm "{p["texto"]}"' if p.get('texto') else '')
    if t == 'duracao_maxima':
        return f'até {p.get("meses", 0)} meses'
    return (p.get('texto') or '')[:140]


# ------------------------------------------------------------------ o plano em resumo (para a IA) e o resultado guardado
def resumo_do_plano(p):
    """Itens do plano, sem o nome da organização nem do projeto: é o que a IA recebe."""
    itens = []
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            itens.append(dict(n=r.item, tipo='mão de obra', nome=r.cargo, quantidade=r.quantidade, horas_por_mes=r.horas_mes, meses=r.meses,
                              valor_mensal=(r.valor_mensal_plano or 0) / 100, empresas=[q.nome for q in r.pesquisas if q.nome]))
        else:
            itens.append(dict(n=r.item, tipo='rubrica', nome=r.descricao, meses=r.meses,
                              itens=[dict(nome=descricao_completa(s), quantidade=s.qtd, valor_unitario=(s.valor_plano or 0) / 100) for s in r.subitens]))
    return dict(teto=p.teto / 100, itens=itens)


def chave_ia(texto, p):
    return hashlib.sha256((texto + json.dumps(resumo_do_plano(p), ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:20]


def resultado_ia(texto, p):
    """O que a IA já respondeu para esta regra e ESTE plano: {'violacoes': [...]} ou None (ainda não conferido). Só lê o banco."""
    from . import db
    try:
        with db.conectar() as c:
            row = c.execute("SELECT resposta FROM ia_log WHERE tipo='regra_orgao' AND pergunta LIKE ? ORDER BY id DESC LIMIT 1", (chave_ia(texto, p) + '|%',)).fetchone()
        return json.loads(row['resposta']) if row else None
    except Exception:
        return None


def conferir_com_a_ia(p, orgao, projeto_id=None):
    """Pergunta à IA cada regra do tipo `ia` do órgão que ainda não foi conferida para este plano. Devolve (conferidas, sem resposta)."""
    from . import db, ia
    ok = falhou = 0
    for r in orgao.proprias:
        if r.tipo != 'ia' or not r.ativa or resultado_ia(r.parametros.get('texto', ''), p) is not None:
            continue
        resp = ia.conferir_regra(r.parametros.get('texto', ''), resumo_do_plano(p), projeto_id)
        if resp is None:
            falhou += 1; continue
        with db.conectar() as c:
            c.execute('INSERT INTO ia_log (quando, projeto_id, tipo, modelo, pergunta, resposta) VALUES (?,?,?,?,?,?)',
                      (db.agora(), projeto_id, 'regra_orgao', 'regra do órgão', chave_ia(r.parametros.get('texto', ''), p) + '|' + r.parametros.get('texto', '')[:300],
                       json.dumps(resp, ensure_ascii=False)))
        ok += 1
    return ok, falhou


# ------------------------------------------------------------------ a conferência
def _uf_do_cnpj(cnpj):
    from . import cnpj_base
    x = cnpj_base.por_cnpj(cnpj)
    return (x or {}).get('uf')


def conferir(p, orgao, uf_do_cnpj=None):
    """[(código, gravidade, onde, mensagem)] das regras próprias ligadas do órgão."""
    from .calculo import total_projeto, total_rubrica
    uf_do_cnpj = uf_do_cnpj or _uf_do_cnpj
    out = []
    onde_r = lambda r: f'Item {r.item} – {r.cargo if isinstance(r, RubricaRH) else r.descricao}'
    for regra in orgao.proprias:
        if not regra.ativa or regra.tipo not in TIPOS:
            continue
        par, t = regra.parametros, regra.tipo
        ponto = lambda onde, msg, g=None: out.append((regra.codigo, g or regra.gravidade, onde, msg))
        if t == 'uf_empresas':
            ufs = [u.upper() for u in par.get('ufs', [])]
            for r in p.rubricas:
                rh = isinstance(r, RubricaRH)
                if (par.get('aplica') == 'rh' and not rh) or (par.get('aplica') == 'materiais' and rh):
                    continue
                grupos = [(onde_r(r), [(q.nome, q.cnpj) for q in r.pesquisas])] if rh else \
                    [(f'{onde_r(r)} / {s.descricao}', [(f.plataforma or f.nome, f.cnpj) for f in fontes_do_subitem(r, s)]) for s in r.subitens]
                for onde, empresas in grupos:
                    sem = []
                    for nome, cnpj in empresas:
                        if not cnpj:
                            continue
                        uf = uf_do_cnpj(cnpj)
                        if uf is None:
                            sem.append(nome or cnpj_formatar(cnpj))
                        elif uf.upper() not in ufs:
                            ponto(onde, f'{nome or "empresa"} ({cnpj_formatar(cnpj)}) é de {uf.upper()}: {regra.titulo} (aceitos: {", ".join(ufs)})')
                    if sem:
                        ponto(onde, f'não foi possível saber o estado de {", ".join(sem)} (CNPJ fora da base da Receita deste computador): confira à mão — {regra.titulo}', 'atencao')
        elif t == 'palavras_proibidas':
            proibidas = {tuple(_raizes(w)): w for w in _lista(par.get('palavras', '')) if _raizes(w)}

            def achadas(texto):
                rz = _raizes(texto)
                return [w for chave, w in proibidas.items() if any(tuple(rz[i:i + len(chave)]) == chave for i in range(len(rz) - len(chave) + 1))]
            for r in p.rubricas:
                rh = isinstance(r, RubricaRH)
                if rh and par.get('alvo') in ('cargos', 'ambos'):
                    for w in achadas(r.cargo):
                        ponto(onde_r(r), f'"{w}" não pode constar: {regra.titulo}')
                if not rh and par.get('alvo', 'itens') in ('itens', 'ambos'):
                    for w in achadas(r.descricao):
                        ponto(onde_r(r), f'"{w}" no nome da rubrica não pode constar: {regra.titulo}')
                    for s in r.subitens:
                        for w in achadas(descricao_completa(s)):
                            ponto(f'{onde_r(r)} / {s.descricao}', f'"{w}" não pode constar: {regra.titulo}')
        elif t == 'percentual_maximo':
            total = total_projeto(p)
            texto = _sa(par.get('texto', ''))
            do_grupo = [r for r in p.rubricas if (par.get('grupo') == 'rh' and isinstance(r, RubricaRH)) or (par.get('grupo') == 'materiais' and not isinstance(r, RubricaRH))
                        or (par.get('grupo') == 'rubrica' and not isinstance(r, RubricaRH) and texto and texto in _sa(r.descricao))]
            soma = sum(total_rubrica(r) for r in do_grupo)
            if total and soma * 100 > float(par.get('pct', 0)) * total:
                ponto('Plano', f'{resumo_da_regra(regra)}: está em {brl(soma)}, que é {str(round(soma * 100 / total, 1)).replace(".", ",")}% do total ({brl(total)})')
        elif t == 'valor_maximo':
            teto, texto = int(par.get('valor', 0)), _sa(par.get('texto', ''))
            for r in p.rubricas:
                rh = isinstance(r, RubricaRH)
                if par.get('alvo') == 'cargo' and rh and (not texto or texto in _sa(r.cargo)) and (r.valor_mensal_plano or 0) > teto:
                    ponto(onde_r(r), f'valor mensal de {brl(r.valor_mensal_plano)} passa do máximo de {brl(teto)}: {regra.titulo}')
                if par.get('alvo') == 'rubrica' and not rh and (not texto or texto in _sa(r.descricao)):
                    mensal = sum((s.valor_plano or 0) * s.qtd for s in r.subitens)
                    if mensal > teto:
                        ponto(onde_r(r), f'valor mensal de {brl(mensal)} passa do máximo de {brl(teto)}: {regra.titulo}')
                if par.get('alvo', 'item') == 'item' and not rh:
                    for s in r.subitens:
                        if (not texto or texto in _sa(descricao_completa(s))) and (s.valor_plano or 0) > teto:
                            ponto(f'{onde_r(r)} / {s.descricao}', f'valor unitário de {brl(s.valor_plano)} passa do máximo de {brl(teto)}: {regra.titulo}')
        elif t == 'duracao_maxima':
            for r in p.rubricas:
                if r.meses > int(par.get('meses', 0) or 0):
                    ponto(onde_r(r), f'{r.meses} meses: passa da duração máxima de {par.get("meses")} meses — {regra.titulo}')
        elif t == 'lembrete':
            ponto('Plano', f'{par.get("texto", "")} (conferência por uma pessoa)')
        elif t == 'ia':
            resp = resultado_ia(par.get('texto', ''), p)
            if resp is None:
                ponto('Plano', f'"{regra.titulo}" ainda não foi conferida pela IA para este plano: use "Conferir regras com a IA", na verificação', 'info')
            else:
                por_num = {r.item: onde_r(r) for r in p.rubricas}
                for v in resp.get('violacoes', []):
                    ponto(por_num.get(v.get('n'), 'Plano'), f'a IA apontou: {v.get("motivo", "")} — {regra.titulo}', 'atencao' if regra.gravidade == 'erro' else regra.gravidade)
    return out
