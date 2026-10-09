"""Apagar todas as pesquisas de um projeto para refazer do zero (pedido da OSC, 05/10/2026).

O que a OSC pediu: "apagar todas as pesquisas já feitas dentro de um projeto, de uma vez (…) que toda a pesquisa seja refeita, com os mesmos
itens, do zero. Sem pegar pesquisas já realizadas."

Os ITENS ficam (cargos, rubricas, descrições, quantidades, horas, faixas, tetos); o que sai é o RESULTADO das pesquisas:
- nos cargos: as 3 vagas e o valor mensal;
- nos itens: as 3 lojas, os preços, os comprovantes ligados ao item, o valor no plano e a troca que a pesquisa tenha feito — o item volta a ser
  o que foi PEDIDO (descrição, marca e especificação originais; a quantidade que a pesquisa ajustou volta à pedida);
- a marca que a própria pesquisa preencheu (quem diz é o histórico: a marca apareceu numa versão gravada pela pesquisa automática).

E, para a pesquisa nova não reaproveitar nada: as opções guardadas no banco de produtos do projeto, as vagas guardadas destes cargos no banco de
vagas e as buscas guardadas do dia (zerar_bancos).

Nada disso some de vez: o projeto ganha UMA versão nova, e a anterior — com todas as pesquisas e os PDFs — continua no histórico e pode ser
restaurada. O que a OSC fez à mão e a busca não sabe refazer (PDF anexado, valores digitados, propostas de serviço) só sai se ela pedir.
As vagas que o sistema achou e a OSC CONFIRMOU (informou o CNPJ da empresa) saem como as outras — senão voltariam para o cargo na hora, vindas
do banco de vagas, e a pesquisa não recomeçaria do zero (foi o que o teste na cópia mostrou) —, a não ser que ela peça para ficarem.
Os comprovantes de CNPJ emitidos na Receita ficam sempre: valem para a empresa, não para a pesquisa."""
import datetime as dt
import re

from . import db
from .modelo import Fonte, PesquisaSalarial, RubricaRH, descricao_completa, fontes_do_subitem, pedido_do_subitem

AUTOMATICAS = ('navegador', 'api')   # como a busca automática grava a origem de um comprovante


def tem_dado(f, preco=None):
    ev = f.evidencia
    return bool(preco or f.nome or f.cnpj or ev.arquivo or ev.url)


def a_mao(f, preco=None, da_busca=()):
    """Pesquisa que a OSC fez à mão (digitou os dados ou anexou o PDF), e não a que a busca automática gravou. da_busca: os links que
    entraram no projeto pela pesquisa automática (urls_da_pesquisa) — a pesquisa sem arquivo com um desses links é da busca."""
    if not f.evidencia.arquivo and f.evidencia.url and f.evidencia.url in da_busca:
        return False
    return tem_dado(f, preco) and f.evidencia.origem not in AUTOMATICAS


def urls_da_pesquisa(pid):
    """Os links de pesquisa que entraram no projeto numa versão gravada pela PESQUISA AUTOMÁTICA (quem diz é o histórico). Servem para
    reconhecer a pesquisa automática cujo comprovante não pôde ser guardado: sem arquivo, ela ficava gravada com a origem "manual", o "apagar e
    refazer" a tomava por feita à mão e o item inteiro ficava. Na pesquisa completa de 09/10/2026, dois itens sobreviveram assim ao apagar — um
    deles uma troca antiga, com um preço errado de R$ 1,98. O link que a OSC digitou (versão gravada por ela) continua sendo dela."""
    import json
    with db.conectar() as c:
        versoes = c.execute('SELECT autor, json FROM versao WHERE projeto_id=? ORDER BY numero', (pid,)).fetchall()
    antes, out = set(), set()
    for v in versoes:
        try:
            j = json.loads(v['json'])
        except ValueError:
            continue
        agora = set()
        for r in j.get('rubricas') or []:
            for f in list(r.get('fontes') or []) + [f for s in r.get('subitens') or [] for f in s.get('fontes') or []]:
                u = (f.get('evidencia') or {}).get('url')
                if u:
                    agora.add(u)
        if 'pesquisa automática' in (v['autor'] or ''):
            out |= agora - antes
        antes = agora
    return out


def _n(texto):
    from .produtos.identidade import sa
    return re.sub(r'\s+', ' ', sa(texto or '')).strip()


def marcas_da_pesquisa(pid, p):
    """{(item da rubrica, posição do subitem)} dos itens cuja MARCA foi preenchida pela pesquisa, e não pela OSC. Quem diz é o histórico: o item
    existia sem marca e ela apareceu numa versão gravada pela pesquisa automática. Se depois a OSC trocou a marca, vale a dela."""
    with db.conectar() as c:
        versoes = [dict(r) for r in c.execute('SELECT numero, autor, json FROM versao WHERE projeto_id=? ORDER BY numero', (pid,))]
    from .modelo import Projeto
    visto, posta = {}, {}   # (rubrica, item) -> última marca vista · marca que a pesquisa pôs
    for v in versoes:
        try:
            antigo = Projeto.model_validate_json(v['json'])
        except Exception:
            continue
        da_pesquisa = 'pesquisa automática' in (v['autor'] or '')
        for r in antigo.rubricas:
            for s in getattr(r, 'subitens', []) or []:
                if s.descricao_original:   # item trocado: a marca é a do produto achado, e o item volta ao pedido original de qualquer jeito
                    continue
                k, m = (_n(r.descricao), _n(s.descricao)), _n(s.marca)
                if k in visto and m != visto[k]:
                    if da_pesquisa and not visto[k] and m:
                        posta[k] = m
                    else:   # a OSC mexeu na marca (escreveu, trocou ou apagou): deixa de ser "a que a pesquisa pôs"
                        posta.pop(k, None)
                visto[k] = m
    out = set()
    for r in p.rubricas:
        for i, s in enumerate(getattr(r, 'subitens', []) or []):
            if not s.descricao_original and s.marca and posta.get((_n(r.descricao), _n(s.descricao))) == _n(s.marca):
                out.add((r.item, i))
    return out


def vagas_confirmadas_pela_osc():
    """Endereços das vagas do banco cuja empresa a OSC confirmou à mão (informou o CNPJ quando o sistema ficou em dúvida)."""
    from .vagas import CONFIRMADA_PELA_OSC
    with db.conectar() as c:
        return {r['url'] for r in c.execute('SELECT url FROM vaga_banco WHERE cnpj_motivo LIKE ?', (CONFIRMADA_PELA_OSC + '%',))}


def _limpar_subitem(s):
    s.fontes, s.precos, s.produtos, s.eans = [], [None, None, None], [None, None, None], [None, None, None]
    s.valor_plano, s.nivel, s.confirmacao, s.justificativa = None, 0, None, None
    s.descricao_original = s.marca_original = s.especificacao_original = None


def zerar(p, pid=None, com_a_mao=False, com_marcas=True, com_confirmadas=True):
    """Tira do projeto as pesquisas já feitas (ver o texto no alto do arquivo). Muda `p` e devolve o resumo do que saiu e do que ficou:
    cargos, itens (com o que volta ao pedido), o que foi feito à mão, e as chaves para zerar_bancos.
    com_a_mao: sai também o que a OSC anexou ou digitou · com_marcas: sai a marca que a pesquisa preencheu · com_confirmadas: saem também as
    vagas cuja empresa a OSC confirmou."""
    from . import servico, vagas as V
    marcas_sis = marcas_da_pesquisa(pid, p) if pid is not None else set()
    da_busca = urls_da_pesquisa(pid) if pid is not None else set()
    da_osc = vagas_confirmadas_pela_osc() if pid is not None else set()
    res = dict(cargos=[], itens=[], automaticas=0, a_mao=0, a_mao_mantidas=0, confirmadas=0, confirmadas_mantidas=0, voltam=[], marcas=[], quantidades=[],
               mantidos=[], pedidos=[], rubricas_inteiras=[], chaves_de_vaga=[], itens_tocados=[], com_confirmadas=com_confirmadas)
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            val = lambda q: q.valor if q.valor is not None else q.faixa_min
            auto = [k for k, q in enumerate(r.pesquisas) if tem_dado(q, val(q)) and not a_mao(q, val(q))]
            mao = [k for k, q in enumerate(r.pesquisas) if a_mao(q, val(q))]
            conf = [k for k in auto if r.pesquisas[k].evidencia.url in da_osc]   # a vaga veio da busca, mas a empresa foi confirmada pela OSC
            sair = (set(auto) - (set() if com_confirmadas else set(conf))) | (set(mao) if com_a_mao else set())
            res['automaticas'] += len(auto); res['a_mao'] += len(mao); res['a_mao_mantidas'] += 0 if com_a_mao else len(mao)
            res['confirmadas'] += len(conf); res['confirmadas_mantidas'] += 0 if com_confirmadas else len(conf)
            fica = ([f'{len(mao)} pesquisa(s) feita(s) à mão'] if mao and not com_a_mao else []) + \
                   ([f'{len(conf)} vaga(s) confirmada(s) por você'] if conf and not com_confirmadas else [])
            if fica:
                res['mantidos'].append(f'Item {r.item} – {r.cargo}: ' + ' e '.join(fica))
            if not sair:
                continue
            r.pesquisas = [PesquisaSalarial() if k in sair else q for k, q in enumerate(r.pesquisas)]
            if not any(tem_dado(q, val(q)) for q in r.pesquisas):
                r.pesquisas = []
            r.valor_mensal_plano = None
            res['cargos'].append(dict(item=r.item, cargo=r.cargo, apagadas=len(sair), ficam=len(set(auto) | set(mao)) - len(sair)))
            res['chaves_de_vaga'] += [V.chave_cargo(r.cargo)] + [V.chave_cargo(t) for t in servico.similares_do_cargo(r)]
            res['itens_tocados'].append(r.item)
            continue
        tipo = servico.tipo_da_rubrica(r)
        tocou, ficou = False, False
        for i, s in enumerate(r.subitens):
            fs = (list(fontes_do_subitem(r, s)) + [Fonte(), Fonte(), Fonte()])[:3]
            precos = (list(s.precos or []) + [None, None, None])[:3]
            auto = [k for k in range(3) if tem_dado(fs[k], precos[k]) and not a_mao(fs[k], precos[k], da_busca)]
            mao = [k for k in range(3) if a_mao(fs[k], precos[k], da_busca)]
            res['automaticas'] += len(auto); res['a_mao'] += len(mao)
            nome = f'Item {r.item} – {r.descricao} / {descricao_completa(s)}'
            pesquisado = bool(auto or mao or s.valor_plano or s.nivel or s.descricao_original)
            if not pesquisado:
                continue
            if tipo == 'sistema' and mao and not com_a_mao:
                # sistema: cada cotação é de um fornecedor diferente — a que a OSC deixou (digitada ou anexada) fica no lugar; as automáticas saem
                res['a_mao_mantidas'] += len(mao); ficou = True
                if auto:
                    if len(s.fontes) != 3:
                        s.fontes = fs
                    for k in auto:
                        s.fontes[k] = Fonte(); precos[k] = None
                        s.produtos = (list(s.produtos or []) + [None] * 3)[:3]; s.eans = (list(s.eans or []) + [None] * 3)[:3]
                        s.produtos[k] = s.eans[k] = None
                    s.precos, s.valor_plano, s.confirmacao, s.justificativa = precos, None, None, None
                    res['itens'].append(dict(nome=nome, apagadas=len(auto), ficam=len(mao))); tocou = True
                    res['pedidos'].append((r.item, pedido_do_subitem(s)))
                else:
                    res['mantidos'].append(f'{nome}: as cotações foram deixadas por você')
                continue
            if mao and not com_a_mao:
                # produto ou serviço com pesquisa feita à mão: as 3 pesquisas são do MESMO produto, então o item fica inteiro como está
                res['a_mao_mantidas'] += len(mao); ficou = True
                res['mantidos'].append(f'{nome}: {len(mao)} pesquisa(s) feita(s) à mão' + (f' (as outras {len(auto)} ficam junto: são do mesmo produto)' if auto else ''))
                continue
            res['pedidos'].append((r.item, pedido_do_subitem(s)))
            linha = dict(nome=nome, apagadas=len(auto) + len(mao), ficam=0)
            if s.descricao_original:
                esp = s.especificacao if s.especificacao_original is None else s.especificacao_original   # None: item trocado antes de 03/10/2026
                antes = descricao_completa(s)
                s.descricao, s.marca, s.especificacao = s.descricao_original, (s.marca_original or None), (esp or None)
                s.nivel = 0   # (descricao_completa olha o nível)
                s.descricao_original = s.marca_original = s.especificacao_original = None
                linha['volta'] = (antes, descricao_completa(s)); res['voltam'].append(linha['volta'])
            elif com_marcas and (r.item, i) in marcas_sis:
                res['marcas'].append((s.descricao, s.marca)); linha['marca'] = s.marca
                s.marca = None
            m = re.search(r'quantidade ajustada de (\d+) para (\d+)', s.justificativa or '')
            if m and s.qtd == int(m.group(2)):
                res['quantidades'].append((s.descricao, s.qtd, int(m.group(1)))); linha['qtd'] = (s.qtd, int(m.group(1)))
                s.qtd = int(m.group(1))
            _limpar_subitem(s)
            res['pedidos'].append((r.item, pedido_do_subitem(s)))   # e o que estiver guardado com o nome que o item volta a ter
            res['itens'].append(linha); tocou = True
        if tocou:
            res['itens_tocados'].append(r.item)
            dependem = [s for s in r.subitens if len(s.fontes) != 3 and any(x is not None for x in (s.precos or []))]   # ainda usam as lojas da rubrica
            if not dependem:
                r.fontes, r.fontes_por_subitem = [Fonte(), Fonte(), Fonte()], {}
            if not ficou:
                res['rubricas_inteiras'].append(r.item)
    # pontos já marcados como revisados nos itens que mudaram: a revisão era das pesquisas antigas
    antes = len(p.revisados)
    for chave in [k for k in p.revisados if re.match(r'Item (\d+) ', (k.split('|', 2) + [''])[1]) and
                  int(re.match(r'Item (\d+) ', k.split('|', 2)[1]).group(1)) in res['itens_tocados']]:
        del p.revisados[chave]
    res['revisados'] = antes - len(p.revisados)
    res['chaves_de_vaga'] = sorted(set(res['chaves_de_vaga']))
    res['pedidos'] = sorted(set(res['pedidos']))
    res['apagadas'] = sum(x['apagadas'] for x in res['cargos']) + sum(x['apagadas'] for x in res['itens'])
    return res


def _onde_vagas(chaves, com_confirmadas):
    """Vagas guardadas destes cargos: saem TODAS — também as que a OSC tinha descartado (decisão de 06/10/2026: a vaga que for encontrada de
    novo não é descartada; passa por todo o processo outra vez) —, menos, se ela pedir para ficarem, as que ela mesma confirmou."""
    from .vagas import CONFIRMADA_PELA_OSC
    q = f"cargo_chave IN ({','.join('?' * len(chaves))})"
    args = list(chaves)
    if not com_confirmadas:
        q += ' AND (cnpj_motivo IS NULL OR cnpj_motivo NOT LIKE ?)'; args.append(CONFIRMADA_PELA_OSC + '%')
    return q, args


def contar_bancos(pid, res):
    """O que zerar_bancos vai tirar: (opções de produto guardadas, vagas guardadas destes cargos)."""
    with db.conectar() as c:
        prods = sum(c.execute("SELECT count(*) FROM produto_banco WHERE projeto_id=? AND item=? AND descricao NOT LIKE '% |em 2 lojas|'", (pid, item)).fetchone()[0]
                    for item in res['rubricas_inteiras'])
        prods += sum(c.execute('SELECT count(*) FROM produto_banco WHERE projeto_id=? AND item=? AND descricao=?', (pid, item, d)).fetchone()[0]
                     for item, d in res['pedidos'] if item not in res['rubricas_inteiras'])
        vagas = 0
        if res['chaves_de_vaga']:
            q, args = _onde_vagas(res['chaves_de_vaga'], res['com_confirmadas'])
            vagas = c.execute('SELECT count(*) FROM vaga_banco WHERE ' + q, args).fetchone()[0]
    return prods, vagas


def zerar_bancos(pid, res):
    """Para a pesquisa nova não reaproveitar nada: tira as opções de produto guardadas dos itens zerados, as vagas guardadas dos cargos zerados
    (o banco de vagas é comum a todos os projetos: as pesquisas já GRAVADAS em outros projetos não mudam) e as buscas guardadas do dia."""
    prods, vagas = contar_bancos(pid, res)
    with db.conectar() as c:
        for item in res['rubricas_inteiras']:
            c.execute('DELETE FROM produto_banco WHERE projeto_id=? AND item=?', (pid, item))
        for item, d in res['pedidos']:
            c.execute('DELETE FROM produto_banco WHERE projeto_id=? AND item=? AND descricao IN (?, ?)', (pid, item, d, d + ' |em 2 lojas|'))
        if res['chaves_de_vaga']:
            from .cnpj_busca import sa
            q, args = _onde_vagas(res['chaves_de_vaga'], res['com_confirmadas'])
            # a consulta de CNPJ guardada de cada empresa também sai: a vaga reencontrada tem o CNPJ conferido de novo
            for row in c.execute('SELECT empresa, cidade, uf FROM vaga_banco WHERE ' + q, args).fetchall():
                c.execute('DELETE FROM empresa_cnpj WHERE chave=?', (f"{sa(row['empresa'])}|{sa(row['cidade'])}|{sa(row['uf'])}",))
            c.execute('DELETE FROM vaga_banco WHERE ' + q, args)
    db.cache_limpar_tudo()
    return prods, vagas


def resumo_em_texto(res, prods=0, vagas=0):
    """Uma frase para o histórico do projeto."""
    partes = [f'{res["apagadas"]} pesquisa(s) apagada(s) em {len(res["cargos"])} cargo(s) e {len(res["itens"])} item(ns)']
    if res['voltam']:
        partes.append(f'{len(res["voltam"])} item(ns) trocado(s) voltaram ao pedido original')
    if res['marcas']:
        partes.append(f'{len(res["marcas"])} marca(s) posta(s) pela pesquisa apagada(s)')
    if res['a_mao_mantidas']:
        partes.append(f'{res["a_mao_mantidas"]} pesquisa(s) feita(s) à mão mantida(s)')
    if res['confirmadas_mantidas']:
        partes.append(f'{res["confirmadas_mantidas"]} vaga(s) confirmada(s) pela OSC mantida(s)')
    if prods or vagas:
        partes.append(f'{prods} opção(ões) de produto e {vagas} vaga(s) guardadas saíram dos bancos')
    return 'pesquisas zeradas para refazer do zero em ' + dt.date.today().strftime('%d/%m/%Y') + ': ' + '; '.join(partes)
