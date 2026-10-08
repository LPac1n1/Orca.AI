"""Interface web local do sistema de orçamentos (roda só neste computador: http://127.0.0.1:8000).
Iniciar: python -m uvicorn app:app --host 127.0.0.1 --port 8000"""
import asyncio
import datetime as dt
import json
import os
import re
import tempfile
from typing import List
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from orcamento import db, tarefas, servico, orgaos
from orcamento import sistemas as sistemas_mod
from orcamento import sessao_catho
from orcamento import cnpj as cnpjmod
from orcamento.calculo import (verificar, resumo, periodo_texto, media_rh, mensal_maximo_rh, media_subitem, total_rubrica, nivelar_pela_faixa, horas_pela_faixa,
                               unitario_rubrica, totais_fontes, valores_pesquisa, chave_alerta, chave_titulo)
from orcamento.exportar import exportar
from orcamento.leitor_pdf import ler as ler_pdf, palavras_padrao
from orcamento.modelo import (Projeto, Config, RubricaRH, RubricaMaterial, PesquisaSalarial, Fonte, Subitem, Evidencia, fontes_do_subitem,
                              pedido_do_subitem, descricao_completa)
from orcamento.otimizador import otimizar
from orcamento.produtos.identidade import familia_padrao
from orcamento.produtos import texto
from orcamento.produtos.lojas import LOJAS, setor_da_rubrica
from orcamento.regras import brl, cnpj_formatar, divisor_horas, enquadrar, REGRAS, CNPJ_PLATAFORMAS
from orcamento.servico import replicar_pesquisas

AQUI = os.path.dirname(__file__)


from contextlib import asynccontextmanager


@asynccontextmanager
async def _ciclo(_app):
    ao_abrir()
    yield


app = FastAPI(title='Orça.AI', lifespan=_ciclo)
tpl = Jinja2Templates(directory=os.path.join(AQUI, 'templates'))
tpl.env.filters['brl'] = brl
tpl.env.filters['cnpj'] = cnpj_formatar


# ------------------------------------------------------------------ apoio à interface (formatos, ícones)
def moeda(c):
    """centavos -> '1.234,56' (valor de um campo com máscara de moeda; o 'R$' fica fora do campo)."""
    if c is None or c == '':
        return ''
    return ('-' if c < 0 else '') + f'{abs(c) / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def data_br(iso, hora=True):
    """'2026-10-02T15:28:00-03:00' -> '02/10/2026 15:28'; '2026-10-02' -> '02/10/2026'."""
    s = str(iso or '')
    if len(s) < 10:
        return s or '—'
    d = f'{s[8:10]}/{s[5:7]}/{s[:4]}'
    return d + (' ' + s[11:16] if hora and len(s) >= 16 else '')


def duracao(seg):
    """segundos -> '45 s' | '3 min 05 s' | '1 h 12 min'."""
    seg = int(seg or 0)
    if seg < 60:
        return f'{seg} s'
    if seg < 3600:
        return f'{seg // 60} min {seg % 60:02d} s'
    return f'{seg // 3600} h {seg % 3600 // 60:02d} min'


def tarefas_ativas():
    with db.conectar() as c:
        return c.execute("SELECT COUNT(*) FROM tarefa WHERE estado IN ('rodando', 'na fila')").fetchone()[0]


ICONES = {   # desenhos de traço, 24×24, sem arquivos externos (o sistema funciona sem internet)
    'certo': '<path d="M20 6 9 17l-5-5"/>',
    'alerta': '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4"/><path d="M12 17.5v.01"/>',
    'erro': '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 7.5v.01"/>',
    'ajuda': '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.3a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1 1-1.1 1.8"/><path d="M12 17v.01"/>',
    'ponto': '<circle cx="12" cy="12" r="4"/>',
    'fechar': '<path d="M18 6 6 18M6 6l12 12"/>',
    'relogio': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'externo': '<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    'mais': '<path d="M12 5v14M5 12h14"/>',
    'busca': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    'baixar': '<path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>',
    'enviar': '<path d="M12 20V9"/><path d="m7 13 5-5 5 5"/><path d="M5 4h14"/>',
    'lixeira': '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
    'editar': '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m13.5 6.5 4 4"/>',
    'pdf': '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6M10 17h6"/>',
    'pasta': '<path d="M3 6h6l2 2h10v11H3z"/>',
    'pessoas': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.5 3.2-5.5 6.5-5.5s5.9 2 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/><path d="M18 14.8c2 .7 3.2 2.4 3.6 5.2"/>',
    'caixa': '<path d="M3 8l9-5 9 5v8l-9 5-9-5z"/><path d="M3 8l9 5 9-5"/><path d="M12 13v8"/>',
    'escudo': '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    'ajustes': '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/>',
    'historico': '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/>',
    'casa': '<path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    'planilha': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/>',
    'seta': '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    'desfazer': '<path d="M4 8h10a6 6 0 0 1 0 12H8"/><path d="M8 4 4 8l4 4"/>',
    'banco': '<path d="M3 10 12 4l9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/><path d="M3 20h18"/>',
    'alvo': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12v.01"/>',
    'lista': '<path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6v.01M4 12v.01M4 18v.01"/>',
    'lua': '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    'sol': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/>',
    'vassoura': '<path d="M14 4l6 6"/><path d="M17 7 9 15"/><path d="M9 15c-3 0-5 2-6 5h8c2-1 3-3 2-5z"/>',
}
tpl.env.filters.update(moeda=moeda, data_br=data_br, duracao=duracao)
tpl.env.globals.update(ICONES=ICONES, tarefas_ativas=tarefas_ativas, periodo_texto=periodo_texto)


def cent(s):
    """'1.234,56' | '1234,56' | '1234.56' | '150.000' | '' -> centavos (ou None)."""
    s = (s or '').strip().replace('R$', '').replace(' ', '')
    if not s:
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(\.\d{3})+', s):   # só pontos de milhar ("150.000"): é cento e cinquenta mil, não 150,00
        s = s.replace('.', '')
    return round(float(s) * 100)


def inteiro(v, padrao):
    """Número inteiro de um campo de formulário; vazio ou inválido -> o valor que já estava."""
    d = re.sub(r'\D', '', str(v or ''))
    return int(d) if d else padrao


def cesta_atende(o):
    """Para as telas: a opção guardada é o item como foi pedido (o mesmo produto nas 3 lojas)? Opções antigas não têm a marca gravada."""
    from orcamento.produtos import cesta
    return cesta.atende_o_pedido(o)


def guia_do_projeto(p, res):
    """Os passos do orçamento com a situação de cada um (visão geral do projeto): o que já está pronto e o que fazer agora."""
    rh = [r for r in p.rubricas if isinstance(r, RubricaRH)]
    mat = [r for r in p.rubricas if not isinstance(r, RubricaRH)]
    subs = [s for r in mat for s in r.subitens]
    prontos = sum(1 for r in rh if servico.rh_pronto(r)) + sum(1 for s in subs if servico.subitem_pronto(s))
    total = len(rh) + len(subs)
    cnpjs = set(usos_cnpj(p))
    com_comp = sum(1 for c in cnpjs if p.comprovantes_cnpj.get(c))
    tem_plano = total > 0
    passos = [
        dict(chave='plano', feito=tem_plano, titulo='Monte o plano',
             texto=(f'{len(rh)} cargo(s) de mão de obra ({sum(max(1, r.quantidade or 1) for r in rh)} profissional(is)) e {len(mat)} rubrica(s) de '
                    f'materiais e serviços, com {len(subs)} item(ns).' if tem_plano else
                    'Cadastre os cargos (mão de obra) e as rubricas de materiais e serviços do Plano de Aplicação.')),
        dict(chave='pesquisa', feito=tem_plano and prontos == total, titulo='Pesquise vagas e preços',
             texto=f'{prontos} de {total} itens com as 3 pesquisas comprovadas em PDF.' if tem_plano else 'Depois de montar o plano, o sistema procura as 3 pesquisas de cada item.'),
        dict(chave='cnpjs', feito=bool(cnpjs) and com_comp == len(cnpjs), titulo='Confira os CNPJs das empresas',
             texto=f'{com_comp} de {len(cnpjs)} empresas com o comprovante oficial da Receita Federal.' if cnpjs else 'As empresas aparecem aqui depois das pesquisas.'),
        dict(chave='pendencias', feito=tem_plano and res['erros'] == 0, titulo='Resolva as pendências',
             texto=(f'{res["erros"]} pendência(s) que bloqueiam o envio e {res["atencao"]} ponto(s) para revisar.' if res['erros'] or res['atencao'] else
                    'Nenhuma pendência encontrada pelas regras da SEJC.')),
        dict(chave='teto', feito=tem_plano and res['saldo'] == 0, titulo='Feche o plano no teto',
             texto=('O total do plano é exatamente o teto.' if tem_plano and res['saldo'] == 0 else
                    f'O total passa do teto em {brl(-res["saldo"])}.' if res['saldo'] < 0 else f'Faltam {brl(res["saldo"])} para o total chegar ao teto.')),
        dict(chave='exportar', feito=False, titulo='Exporte o Excel',
             texto='Gera a Grade Comparativa e o Plano de Aplicação no formato aceito pela SEJC.'),
    ]
    atual = next((x['chave'] for x in passos if not x['feito']), 'exportar')
    for x in passos:
        x['atual'] = x['chave'] == atual
    return passos


def cnpjs_do_projeto(p):
    cs = []
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            cs += [f.cnpj for f in r.pesquisas if f.cnpj]
        else:
            cs += [f.cnpj for f in r.fontes if f.cnpj]
            cs += [f.cnpj for s in r.subitens for f in fontes_do_subitem(r, s) if f.cnpj]
    return list(dict.fromkeys(cnpj_formatar(c) for c in cs))


def situacao_dos_cnpjs(p):
    """({CNPJ: consulta}, {CNPJ: situação}). O que ainda não foi consultado nas APIs é resolvido pela base oficial da Receita guardada neste
    computador (só tem empresas ATIVAS): o sistema não deixa como "ainda não consultado" o que ele mesmo consegue conferir."""
    from orcamento import cnpj_base
    cnpjs = cnpjs_do_projeto(p)
    cache = cnpjmod.do_cache(cnpjs)
    for c in cnpjs:
        if not (cache.get(c) or {}).get('situacao'):
            try:
                b = cnpj_base.por_cnpj(c)
            except Exception:
                b = None
            if b:
                cache[c] = dict(cnpj=c, situacao='ATIVA', razao_social=b.get('razao'), fonte='base oficial da Receita (neste computador)', consultado_em='')
    return cache, {c: (v.get('situacao') if v else None) for c, v in cache.items()}


def abrir(pid):
    """Carrega o projeto com os acertos automáticos de escrita (pedido da OSC, 03/10/2026): descrição simples e sem marca, marca e medida nos
    campos certos, unidades com as letras certas (1L, 500mL). Se algo mudou, grava uma nova versão (a anterior fica no histórico) e leva junto
    as opções guardadas no banco de produtos. Projeto removido só é acertado na tela, sem gravar."""
    p, v = db.carregar(pid)
    if p is None:
        return p, v
    n = servico.acertar_trocados(p)
    m, chaves = servico.arrumar_descricoes(p)
    sem_orgao = p.orgao_id is None   # projeto anterior ao cadastro de órgãos: passa a pertencer ao órgão padrão (as regras são as mesmas)
    if (n or m or sem_orgao) and not db.removido_em(pid):
        motivos = ([f'{max(n, m)} item(ns): descrição simples (sem marca), marca e especificação nos campos certos e unidades de medida com as letras certas'] if (n or m) else [])
        if sem_orgao:
            p.orgao_id = orgaos.padrao()
            motivos.append('projeto ligado ao órgão padrão do cadastro (as regras continuam as mesmas)')
        v = db.salvar(pid, p, autor='sistema', motivo='; '.join(motivos))
        servico.migrar_banco(pid, chaves)
    return p, v


def contexto(p, pid, versao):
    cache, status = situacao_dos_cnpjs(p)
    alertas = verificar(p, status)
    por_item = {}
    for a in alertas:
        por_item.setdefault(a.item.split(' / ')[0].split(' – ')[0], []).append(a)
        if ' / ' in a.item or ' – ' in a.item:
            por_item.setdefault(a.item, []).append(a)

    def st(chave):
        g = [a.gravidade for a in por_item.get(chave, [])]
        return 'erro' if 'erro' in g else ('atencao' if 'atencao' in g else 'ok')

    def pontos(chave, so_dele=False):
        """Pendências e pontos para revisar de um item (chave "Item N") ou de um subitem (chave completa), para mostrar na própria tela de
        edição. so_dele: só os pontos do item em si, sem os dos subitens."""
        return [a for a in por_item.get(chave, []) if a.gravidade in ('erro', 'atencao', 'revisado') and not (so_dele and ' / ' in a.item)]
    from orcamento import ia, cnpj_base
    tipos = {r.item: ('rh' if isinstance(r, RubricaRH) else 'mat') for r in p.rubricas}

    por_num = {r.item: r for r in p.rubricas}

    def link_alerta(a):
        """Tela onde se corrige o ponto, já no item certo (subitem da rubrica ou pesquisa do cargo)."""
        m = re.match(r'Item (\d+)', a.item or '')
        if not m or int(m.group(1)) not in tipos:
            return None
        n = int(m.group(1)); url = f'/p/{pid}/{tipos[n]}/{n}'
        if tipos[n] == 'mat' and ' / ' in a.item:
            sub = a.item.split(' / ', 1)[1]
            i = next((i for i, x in enumerate(por_num[n].subitens) if x.descricao == sub), None)
            url += f'#sub{i}' if i is not None else ''
        elif tipos[n] == 'rh':
            k = re.match(r'pesquisa (\d)', a.mensagem or '')
            url += f'#pesquisa{int(k.group(1)) - 1}' if k else ''
        return url
    orgao = orgaos.do_projeto(p)
    return dict(p=p, pid=pid, versao=versao, alertas=alertas, res=resumo(p, alertas), cache=cache, st=st, link_alerta=link_alerta, pontos=pontos,
                orgao=orgao, orgao_id=p.orgao_id, orgaos_lista=orgaos.listar(), regra_texto=lambda cod: orgaos.texto_da_regra(cod, orgao),
                regras_ia=[r for r in orgao.proprias if r.tipo == 'ia' and r.ativa],
                produtos_diferentes=servico.produtos_diferentes,
                RubricaRH=RubricaRH, media_rh=media_rh, mensal_maximo_rh=mensal_maximo_rh, media_subitem=media_subitem,
                total_rubrica=total_rubrica, unitario_rubrica=unitario_rubrica, totais_fontes=totais_fontes, fontes_do_subitem=fontes_do_subitem,
                valores_pesquisa=valores_pesquisa, divisor_horas=divisor_horas, enquadrar=enquadrar, REGRAS=REGRAS, LOJAS=LOJAS,
                chave_alerta=chave_alerta, descricao_completa=descricao_completa, pedido_do_subitem=pedido_do_subitem, mesmo_titulo=mesmo_titulo,
                cargos_repetidos=servico.cargos_repetidos(p), meses_padrao=meses_padrao(p), catho=sessao_catho.estado(),
                familia_padrao=familia_padrao, setor_da_rubrica=setor_da_rubrica, ia_ok=ia.disponivel(), base=cnpj_base.situacao(),
                tarefas_rodando=[t for t in tarefas.listar(pid, 10) if t['estado'] in ('rodando', 'na fila')],
                tipo_da_rubrica=servico.tipo_da_rubrica, TIPOS_RUBRICA=servico.TIPOS_RUBRICA, subitem_pronto=servico.subitem_pronto, pesquisa_comprovada=servico.pesquisa_comprovada,
                comprovantes=p.comprovantes_cnpj, bloqueadas=db.lojas_bloqueadas(), removido_em=db.removido_em(pid))


def mesmo_titulo(a, b):
    """Dois títulos de cargo iguais (sem diferença de plural, gênero ou acento)?"""
    return chave_titulo(a) == chave_titulo(b)


def meses_padrao(p):
    """Duração mais comum entre as rubricas do projeto (sugestão para a próxima); vazio se ainda não há rubricas."""
    ms = [r.meses for r in p.rubricas if r.meses]
    return max(set(ms), key=ms.count) if ms else ''


def secao_do_item(r):
    return 'mao-de-obra' if isinstance(r, RubricaRH) else 'materiais'


def voltar_ao_projeto(pid, msg, ancora=''):
    """Volta para a tela do projeto, na parte de onde a pessoa veio (mão de obra, materiais, verificação…), com a mensagem."""
    return RedirectResponse(f'/p/{pid}?msg={quote(msg)}' + (f'#{ancora}' if ancora else ''), status_code=303)


# ------------------------------------------------------------------ ao abrir: tarefas interrompidas, base da Receita, vagas do dia
def ao_abrir():
    tarefas.marcar_interrompidas()
    if os.environ.get('ORCAMENTO_SEM_ROTINAS'):
        return
    try:
        db.cache_limpar_antigos()
    except Exception:
        pass
    marca = os.path.join(db.PASTA_LOCAL, 'ultima_verificacao.json')
    try:
        feito = json.load(open(marca, encoding='utf-8'))
    except Exception:
        feito = {}
    hoje = dt.date.today().isoformat()
    if feito.get('receita') != hoje:          # uma vez por dia: há pasta nova na Receita? (a atualização é mensal)
        feito['receita'] = hoje
        tarefas.iniciar('base_receita', 'Base da Receita: verificar/atualizar', lambda ctx: servico.base_receita(ctx))
    if feito.get('vagas') != hoje:            # coleta diária para os cargos que ainda não têm 3 vagas no banco (D7)
        feito['vagas'] = hoje
        tarefas.iniciar('vagas_diaria', 'Coleta diária de vagas (banco de vagas)', coleta_diaria)
    os.makedirs(db.PASTA_LOCAL, exist_ok=True)
    json.dump(feito, open(marca, 'w', encoding='utf-8'))


async def coleta_diaria(ctx):
    """Cargos sem 3 vagas no banco: busca o título exato e, se ainda faltar, os títulos similares aceitos em cada projeto."""
    from orcamento import vagas as V
    cargos = {}
    for x in db.listar():
        p, _ = db.carregar(x['id'])
        for r in p.rubricas:
            if isinstance(r, RubricaRH):
                c = cargos.setdefault(V.chave_cargo(r.cargo), [r.cargo, []])
                c[1] += [t for t in servico.similares_do_cargo(r) if t not in c[1]]
    faltam = [(c, sim) for c, sim in cargos.values() if len(V.tres_do_banco(c)) < 3]
    out = {}
    for i, (cargo, sim) in enumerate(faltam):   # cada título é um grupo à parte: o do cargo e, enquanto ele não tiver 3 vagas, cada similar aceito
        ctx.etapa(f'Cargo {i + 1} de {len(faltam)}: {cargo}')
        await V.coletar(cargo, None)
        for t in sim:
            if len(V.tres_do_banco(cargo)) >= 3:
                break
            if len(V.tres_do_banco(t)) < 3:
                ctx.etapa(f'Cargo {i + 1} de {len(faltam)}: {cargo} (título similar: {t})')
                await V.coletar(t, None)
        out[cargo] = len(V.tres_do_banco(cargo))
        ctx.progresso(100 * (i + 1) / max(1, len(faltam)))
    return dict(cargos=out)


# ------------------------------------------------------------------ tarefas (progresso)
def nomes_dos_projetos():
    return {x['id']: x['nome'] for x in db.listar() + db.listar(removidos=True)}


@app.get('/tarefa/{tid}', response_class=HTMLResponse)
def tarefa_tela(request: Request, tid: int):
    t = tarefas.ler(tid)
    return tpl.TemplateResponse(request, 'tarefa.html', dict(t=t, projeto_nome=nomes_dos_projetos().get(t['projeto_id']) if t else None),
                                status_code=200 if t else 404)


@app.get('/api/cnpj/{numero}')
def api_cnpj(numero: str):
    """Empresa de um CNPJ, pela base oficial guardada neste computador (nada vai para a internet). Usado pelas telas para preencher o
    nome da empresa e mostrar a situação assim que o CNPJ é digitado."""
    from orcamento import cnpj_base
    from orcamento.regras import cnpj_dv_ok
    d = re.sub(r'\D', '', numero)
    if not cnpj_dv_ok(d):
        return JSONResponse({'ok': False, 'motivo': 'CNPJ inválido'})
    try:
        b = cnpj_base.por_cnpj(d)
    except Exception:
        b = None
    if not b:
        return JSONResponse({'ok': False, 'motivo': 'não encontrado na base da Receita deste computador'})
    return JSONResponse({'ok': True, 'razao': b.get('razao'), 'situacao': b.get('situacao') or 'ATIVA', 'municipio': b.get('municipio'), 'uf': b.get('uf')})


@app.get('/ajuda', response_class=HTMLResponse)
def ajuda_tela(request: Request):
    return tpl.TemplateResponse(request, 'ajuda.html', dict(REGRAS=REGRAS))


@app.get('/guia-de-interface', response_class=HTMLResponse)
def guia_interface(request: Request):
    """Mostruário dos componentes da interface (design system), para conferência visual."""
    return tpl.TemplateResponse(request, 'guia.html', {})


async def erro_inesperado(request: Request, exc: Exception):
    """Qualquer erro não previsto vira uma página que explica o que fazer, em vez de 'Internal Server Error'."""
    valor = isinstance(exc, (ValueError, KeyError))
    return tpl.TemplateResponse(request, 'erro.html', dict(valor=valor, detalhe=f'{type(exc).__name__}: {exc}'[:600]), status_code=400 if valor else 500)


@app.get('/api/tarefa/{tid}')
def tarefa_api(tid: int):
    return JSONResponse(tarefas.ler(tid))


@app.post('/api/tarefa/{tid}/cancelar')
def tarefa_cancelar(tid: int):
    tarefas.cancelar(tid)
    return JSONResponse({'ok': True})


@app.get('/tarefas', response_class=HTMLResponse)
def tarefas_lista(request: Request, msg: str = ''):
    return tpl.TemplateResponse(request, 'tarefas.html', dict(lista=tarefas.listar(limite=60), nomes=nomes_dos_projetos(), msg=msg,
                                                              n_terminadas=tarefas.contar_terminadas()))


@app.post('/tarefas/limpar')
def tarefas_limpar():
    """Limpa o registro das tarefas que já terminaram (as que estão rodando ficam)."""
    n = tarefas.limpar_concluidas()
    return RedirectResponse('/tarefas?msg=' + quote(f'{n} tarefa(s) terminada(s) saíram do registro.' if n else 'Não havia tarefas terminadas para limpar.'), status_code=303)


# ------------------------------------------------------------------ projetos
@app.middleware('http')
async def projeto_removido(request: Request, call_next):
    """Projeto removido fica só para consulta: nenhuma alteração ou pesquisa é aceita até ele ser restaurado."""
    m = re.match(r'/p/(\d+)(/|$)', request.url.path)
    if m and not db.existe(int(m.group(1))):
        return HTMLResponse('Projeto não encontrado (pode ter sido apagado). <a href="/">Voltar à página inicial</a>', status_code=404)
    if (m and request.method == 'POST' and not request.url.path.endswith(('/restaurar-projeto', '/apagar-de-vez'))
            and db.removido_em(int(m.group(1)))):
        return RedirectResponse(f'/p/{m.group(1)}', status_code=303)
    return await call_next(request)


@app.get('/', response_class=HTMLResponse)
def inicio(request: Request, msg: str = ''):
    from orcamento import cnpj_base, ia
    return tpl.TemplateResponse(request, 'index.html', dict(projetos=db.listar(), removidos=db.listar(removidos=True), msg=msg,
                                                            orgaos_lista=orgaos.listar(), orgao_padrao=orgaos.padrao(),
                                                            base=cnpj_base.situacao(), ia_ok=ia.disponivel(),
                                                            rodando=[t for t in tarefas.listar(limite=10) if t['estado'] in ('rodando', 'na fila')]))


@app.post('/projetos')
def novo_projeto(nome: str = Form(...), teto: str = Form(...), processo: str = Form(''), proponente: str = Form(''), cep: str = Form(''), orgao_id: str = Form('')):
    oid = inteiro(orgao_id, 0) or orgaos.padrao()
    o = orgaos.ler(oid) or orgaos.padrao_embutido()
    cfg = Config(validade_dias=o.parametros.validade_dias, divisor_horas=o.parametros.divisor_horas, valores_defensaveis=o.parametros.valor_do_plano == 'menor_ou_media')
    pid = db.criar(Projeto(nome=nome, teto=cent(teto), processo=processo, proponente=proponente, cep=cep, orgao_id=oid, orgao=o.nome, config=cfg))
    return RedirectResponse(f'/p/{pid}', status_code=303)


@app.get('/p/{pid}', response_class=HTMLResponse)
def projeto(request: Request, pid: int, msg: str = ''):
    p, v = abrir(pid)
    if p is None:
        return HTMLResponse('Projeto não encontrado. <a href="/">Voltar</a>', status_code=404)
    ctx = contexto(p, pid, v)
    return tpl.TemplateResponse(request, 'projeto.html', dict(ctx, msg=msg, guia=guia_do_projeto(p, ctx['res']), n_cnpjs=len(usos_cnpj(p))))


@app.post('/p/{pid}/remover')
def projeto_remover(pid: int):
    """Remove o projeto da lista (pedido da OSC, 02/10/2026). Nada é apagado: ele vai para "Projetos removidos" e pode ser restaurado."""
    p, _ = db.carregar(pid)
    if p is None:
        return HTMLResponse('Projeto não encontrado. <a href="/">Voltar</a>', status_code=404)
    if any(t['estado'] in ('rodando', 'na fila') for t in tarefas.listar(pid, 20)):
        return RedirectResponse(f'/p/{pid}?msg=' + quote('Há uma tarefa em andamento neste projeto: espere terminar (ou cancele) antes de remover.'),
                                status_code=303)
    db.remover_projeto(pid)
    return RedirectResponse('/?msg=' + quote(f'Projeto "{p.nome}" removido da lista. Ele fica em "Projetos removidos" e pode ser restaurado.'),
                            status_code=303)


@app.post('/p/{pid}/apagar-de-vez')
def projeto_apagar(pid: int, confirmacao: str = Form('')):
    """Apaga de vez um projeto já removido da lista (pedido da OSC, 02/10/2026). Exige o nome do projeto digitado. Não tem volta."""
    p, _ = db.carregar(pid)
    if not db.removido_em(pid):
        return RedirectResponse(f'/p/{pid}?msg=' + quote('Para apagar de vez, primeiro remova o projeto da lista.'), status_code=303)
    limpo = lambda t: re.sub(r'\s+', ' ', t or '').strip()
    na_lista = next((x['nome'] for x in db.listar(removidos=True) if x['id'] == pid), p.nome)
    if limpo(confirmacao) not in (limpo(p.nome), limpo(na_lista)):
        return RedirectResponse('/?msg=' + quote(f'Nada foi apagado: o nome digitado não é igual ao nome do projeto ("{na_lista}").'), status_code=303)
    try:
        r = db.apagar_projeto(pid)
    except ValueError as e:
        return RedirectResponse('/?msg=' + quote(f'Nada foi apagado: {e}.'), status_code=303)
    msg = f'Projeto "{r["nome"]}" apagado de vez: {r["versoes"]} versão(ões) e {r["arquivos"]} arquivo(s) de comprovantes.'
    if r['sobraram']:
        msg += (f' {r["sobraram"]} arquivo(s) não puderam ser apagados (abertos em outro programa): feche-os e apague a pasta '
                f'sistema/dados/projetos/{pid} pelo Windows.')
    return RedirectResponse('/?msg=' + quote(msg), status_code=303)


@app.post('/p/{pid}/restaurar-projeto')
def projeto_restaurar(pid: int):
    p, _ = db.carregar(pid)
    if p is None:
        return HTMLResponse('Projeto não encontrado. <a href="/">Voltar</a>', status_code=404)
    db.restaurar_projeto(pid)
    return RedirectResponse(f'/p/{pid}?msg=' + quote('Projeto restaurado.'), status_code=303)


@app.post('/p/{pid}/config')
async def config(request: Request, pid: int):
    f = await request.form()
    p, _ = db.carregar(pid)
    folga = cent(f.get('folga_teto') or '5')
    p.config = Config(divisor_horas=f['divisor_horas'], horas_max_mes=max(1, min(220, inteiro(f.get('horas_max_mes'), p.config.horas_max_mes))),
                      valores_defensaveis=bool(f.get('valores_defensaveis')), validade_dias=int(f.get('validade_dias') or 180),
                      modo_cesta=f.get('modo_cesta') or 'por_item', folga_teto=(folga or 500) / 10000, usar_ia=bool(f.get('usar_ia')), marcas_diferentes=False,
                      trocar_pela_categoria=bool(f.get('trocar_pela_categoria')), comprovante='carrinho' if f.get('comprovante') == 'carrinho' else 'pagina',
                      lojas_desligadas=[k for k in LOJAS if not f.get(f'loja_{k}')])
    p.teto, p.nome, p.processo, p.proponente, p.cep = cent(f['teto']), f['nome'], f.get('processo', ''), f.get('proponente', ''), f.get('cep', '')
    novo_orgao = inteiro(f.get('orgao_id'), 0)
    if novo_orgao and orgaos.ler(novo_orgao) is not None:
        p.orgao_id, p.orgao = novo_orgao, orgaos.ler(novo_orgao).nome
    db.salvar(pid, p, motivo='configuração alterada', config=p.config.model_dump(), teto=p.teto, orgao=p.orgao_id)
    with db.conectar() as c:
        c.execute('UPDATE projeto SET nome=? WHERE id=?', (p.nome, pid))
    return voltar_ao_projeto(pid, 'Configuração salva.', 'configuracao')


@app.post('/p/{pid}/cnpj')
def consultar_cnpjs(pid: int):
    p, _ = db.carregar(pid)
    res = {c: cnpjmod.consultar(c, forcar=True).get('situacao') for c in cnpjs_do_projeto(p)}
    with db.conectar() as c:
        db.evento(c, pid, 'CNPJ_CONSULTADOS', resultado=res)
    return voltar_ao_projeto(pid, f'Situação de {len(res)} CNPJ(s) consultada. O resultado já está na verificação.', 'verificacao')


@app.post('/p/{pid}/pesquisar-tudo')
def pesquisar_tudo(pid: int):
    """Tudo automático, cada rubrica com as regras do seu tipo (mão de obra, produtos de mercado, sistema...). O que já foi pesquisado e
    continua válido NÃO é refeito (decisão da OSC, 27/09/2026): cargos com 3 vagas válidas e subitens com os 3 comprovantes ficam como estão."""
    async def rodar(ctx):
        p, _ = db.carregar(pid)
        n_links = servico.consertar_links(p, pid)   # comprovante de um item só, mas com o endereço do carrinho: passa a abrir o produto
        if n_links:
            db.salvar(pid, p, autor='sistema', motivo=f'{n_links} endereço(s) de carrinho trocado(s) pelo endereço da página do produto')
        p, _ = abrir(pid)   # itens antigos: descrição simples, marca e especificação nos campos certos (grava se mudar)
        sal = servico.corrigir_salarios_pela_pagina(p)   # o salário da pesquisa é o que a página guardada mostra
        for x in p.rubricas:   # cargo com faixa pretendida e salário corrigido: as horas acompanham a nova média
            if isinstance(x, RubricaRH) and x.item in {i for i, *_ in sal}:
                nivelar_pela_faixa(x, p.config)
        if sal:
            db.salvar(pid, p, autor='sistema', motivo=f'{len(sal)} salário(s) corrigido(s) pelo valor que a página da vaga mostra',
                      salarios=[f'item {i}: {n} de {a / 100:.2f} para {d / 100:.2f}' for i, n, a, d in sal])
            ctx.aviso(f'{len(sal)} salário(s) de pesquisas já gravadas foram corrigidos pelo valor que a página da vaga mostra (ex.: {sal[0][1]}: '
                      f'R$ {sal[0][2] / 100:.2f} → R$ {sal[0][3] / 100:.2f}).')
        por_item = {r.item: r for r in p.rubricas}
        cargos, mats, sistemas_, servicos = {}, [], [], []
        for r in p.rubricas:
            t = servico.tipo_da_rubrica(r)
            if t == 'rh':
                cargos.setdefault(r.cargo.lower(), []).append(r.item)
            elif t in ('mercado', 'material') and r.subitens:
                mats.append(r.item)
            elif t == 'sistema':   # sem item cadastrado, o próprio sistema cria o item da rubrica
                sistemas_.append(r.item)
            elif r.subitens:
                servicos.append(r.item)
        passos = max(1, len(cargos) + 2 * len(mats) + len(sistemas_)); n = 0
        resumo_, a_decidir = {}, []
        for cargo, itens_c in cargos.items():
            if all(servico.rh_pronto(por_item[i]) for i in itens_c):
                resumo_[f'vagas {cargo}'] = 'já pesquisado (3 vagas válidas): não refeito'; n += 1; continue
            ctx.progresso(100 * n / passos, f'Vagas: {cargo}')
            r = await servico.vagas_do_cargo(pid, itens_c[0], _Sub(ctx, n, passos)); n += 1
            resumo_[f'vagas {cargo}'] = f"{r['no_banco']} de 3"
        for item in mats:
            try:   # pesquisa sem comprovante (página vazia, loja sem estoque): tenta de novo e, se preciso, outra loja com o mesmo produto
                await servico.consertar_pendentes(pid, item, _Sub(ctx, n, passos))
            except tarefas.Cancelada:
                raise
            except Exception as e:
                ctx.aviso(f'Item {item}: não foi possível resolver sozinho as pesquisas sem comprovante ({type(e).__name__}); o item será pesquisado de novo.')
            r = db.carregar(pid)[0]
            rub = next(x for x in r.rubricas if x.item == item)
            pend = [pedido_do_subitem(s) for s in servico.subitens_a_pesquisar(rub)]
            if not pend:
                resumo_[f'item {item}'] = 'já pesquisado (todos os subitens com 3 comprovantes): não refeito'; n += 2; continue
            ctx.progresso(100 * n / passos, f'Produtos: item {item} ({len(pend)} de {len(rub.subitens)} subitens a pesquisar)')
            prop = await servico.pesquisar_rubrica(pid, item, _Sub(ctx, n, passos), somente=pend if len(pend) < len(rub.subitens) else None); n += 1
            ctx.progresso(100 * n / passos, f'Comprovantes: item {item}')
            ap = await servico.aplicar_proposta(pid, item, prop, _Sub(ctx, n, passos)); n += 1
            decidir = [l['desc'] for l in prop['linhas'] if l.get('decidir')]
            nada = [l['desc'] for l in prop['linhas'] if l.get('sem_opcao')]
            a_decidir += [(item, d) for d in decidir + nada]
            resumo_[f'item {item}'] = (f"{sum(1 for l in prop['linhas'] if l['acao'] != 'RETIRADO')} de {len(pend)} pesquisados (versão {ap['versao']})"
                                       + (f'; {len(decidir)} não achado(s) como pedido(s): aguardam a sua decisão (nada foi substituído)' if decidir else '')
                                       + (f'; {len(nada)} não achado(s) em 3 lojas, sem opção de substituição (nada foi substituído)' if nada else '')
                                       + (f'; {len(rub.subitens) - len(pend)} já prontos, mantidos' if len(pend) < len(rub.subitens) else ''))
        for item in sistemas_:
            rub = next(x for x in db.carregar(pid)[0].rubricas if x.item == item)
            if servico.sistema_pronto(rub):
                resumo_[f'item {item}'] = 'sistemas já cotados (3 comprovantes): não refeito'; n += 1; continue
            ctx.progresso(100 * n / passos, f'Sistemas: item {item}')
            r = await servico.pesquisar_sistema(pid, item, _Sub(ctx, n, passos)); n += 1
            resumo_[f'item {item}'] = f"sistemas: {r['cotados']} com preço público (versão {r['versao']})"
        for item in servicos:
            resumo_[f'item {item}'] = 'serviço: fica com os 3 fornecedores do serviço (sem pesquisa automática)'
        consultar_cnpjs_que_faltam(db.carregar(pid)[0], ctx)
        if a_decidir:   # a pesquisa completa NUNCA substitui um item (decisão da OSC, 06/10/2026): o que não foi achado como pedido fica para ela decidir
            ctx.aviso(f'{len(a_decidir)} item(ns) não foram achados iguais em 3 lojas. NADA foi substituído: abra cada um e escolha uma opção de substituição '
                      '(quando houver), mude o pedido e pesquise de novo, ou preencha à mão — ' + '; '.join(f'item {i}: {d}' for i, d in a_decidir[:12])
                      + ('…' if len(a_decidir) > 12 else '') + '.')
        return dict(resumo=resumo_, ir_para=f'/p/{pid}')
    tid = tarefas.iniciar('tudo', 'Pesquisar tudo (vagas e produtos)', rodar, pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.get('/p/{pid}/zerar-pesquisas', response_class=HTMLResponse)
def zerar_pesquisas_tela(request: Request, pid: int):
    """O que vai sair e o que fica, ANTES de apagar as pesquisas do projeto para refazer do zero. Nada é mudado aqui."""
    from orcamento import zerar
    p, v = abrir(pid)
    if p is None:
        raise HTTPException(404)
    previa = zerar.zerar(p.model_copy(deep=True), pid)                      # como ficaria, guardando o que foi feito à mão
    tudo = zerar.zerar(p.model_copy(deep=True), pid, com_a_mao=True)        # e apagando também o que foi feito à mão
    banco_prods, banco_vagas = zerar.contar_bancos(pid, previa)
    confirmadas_no_banco = banco_vagas - zerar.contar_bancos(pid, dict(previa, com_confirmadas=False))[1]
    return tpl.TemplateResponse(request, 'zerar.html', dict(contexto(p, pid, v), previa=previa, tudo=tudo, banco_prods=banco_prods, banco_vagas=banco_vagas,
                                                            confirmadas_no_banco=confirmadas_no_banco))


@app.post('/p/{pid}/zerar-pesquisas')
def zerar_pesquisas(pid: int, a_mao: str = Form(''), marcas: str = Form(''), confirmadas: str = Form(''), depois: str = Form('')):
    """Apaga as pesquisas do projeto (uma versão nova; a anterior fica no histórico) e esvazia o que a pesquisa nova poderia reaproveitar: as
    opções de produto guardadas, as vagas guardadas destes cargos e as buscas do dia. Com depois=pesquisar, já começa o "Pesquisar tudo"."""
    from orcamento import zerar
    p, v = abrir(pid)
    if p is None:
        raise HTTPException(404)
    if db.removido_em(pid):
        return voltar_ao_projeto(pid, 'Nada foi apagado: o projeto está na área de removidos. Restaure o projeto antes.')
    if any(t['estado'] in ('rodando', 'na fila') for t in tarefas.listar(pid, 10)):
        return voltar_ao_projeto(pid, 'Nada foi apagado: há uma tarefa em andamento neste projeto. Espere terminar ou cancele em "Tarefas".')
    res = zerar.zerar(p, pid, com_a_mao=bool(a_mao), com_marcas=bool(marcas), com_confirmadas=bool(confirmadas))
    if not res['apagadas'] and not res['voltam']:
        return voltar_ao_projeto(pid, 'Nada foi apagado: o projeto não tinha pesquisas para apagar.')
    servico.arrumar_descricoes(p)   # os pedidos que voltaram já saem com a escrita acertada (1Kg → 1kg), na mesma versão
    prods, vagas = zerar.contar_bancos(pid, res)
    nova = db.salvar(pid, p, motivo=zerar.resumo_em_texto(res, prods, vagas))   # primeiro a versão; só depois os bancos (se a gravação falhar, nada some)
    zerar.zerar_bancos(pid, res)
    if depois == 'pesquisar':
        return pesquisar_tudo(pid)
    return voltar_ao_projeto(pid, f'{res["apagadas"]} pesquisa(s) apagada(s). O projeto está na versão {nova}; a versão {v}, com as pesquisas, continua no histórico. '
                                  'Quando quiser, use "Pesquisar tudo automaticamente".')


def consultar_cnpjs_que_faltam(p, ctx=None):
    """Consulta sozinho a situação dos CNPJs que ainda não têm consulta nem estão na base oficial deste computador."""
    cache, status = situacao_dos_cnpjs(p)
    faltam = [c for c in cnpjs_do_projeto(p) if not status.get(c)]
    for n, c in enumerate(faltam[:60]):
        if ctx:
            ctx.etapa(f'Consultando a situação do CNPJ {c} ({n + 1} de {len(faltam)})')
        try:
            cnpjmod.consultar(c)
        except Exception:
            pass
    return len(faltam)


class _Sub:
    """Contexto de uma subtarefa: repassa progresso proporcional, fontes e avisos para a tarefa principal."""

    def __init__(self, ctx, n, passos):
        self.ctx, self.n, self.passos, self.id = ctx, n, passos, ctx.id

    def progresso(self, pct, etapa=None):
        self.ctx.progresso(100 * (self.n + pct / 100) / self.passos, etapa)

    def etapa(self, t):
        self.ctx.etapa(t)

    def fonte(self, *a, **k):
        self.ctx.fonte(*a, **k)

    def aviso(self, m):
        self.ctx.aviso(m)


# ------------------------------------------------------------------ rubricas
@app.post('/p/{pid}/rubrica')
async def nova_rubrica(request: Request, pid: int):
    """Cria um cargo ou uma rubrica com o que a pessoa escreveu no quadro "Adicionar" (o nome é obrigatório; nada vem escrito por padrão)."""
    f = await request.form()
    tipo = 'rh' if f.get('tipo') == 'rh' else 'material'
    secao = 'novo-cargo' if tipo == 'rh' else 'nova-rubrica'
    nome = re.sub(r'\s+', ' ', f.get('nome') or '').strip()
    p, _ = db.carregar(pid)
    horas, meses = inteiro(f.get('horas_mes'), 0), inteiro(f.get('meses'), 0)
    faixa = cent(f.get('faixa_pretendida')) if tipo == 'rh' else None
    if tipo == 'rh' and faixa and not horas:   # com faixa pretendida as horas são calculadas depois; até lá, o máximo de horas do cargo
        from orcamento.regras import horas_maximas
        horas = horas_maximas(nome, p.config) if nome else 0
    falta = [x for x, ok in (('o nome ' + ('do cargo' if tipo == 'rh' else 'da rubrica'), nome), ('as horas por mês (ou a faixa salarial pretendida)', horas or tipo != 'rh'),
                             ('a duração em meses', meses)) if not ok]
    if falta:
        return voltar_ao_projeto(pid, 'Nada foi adicionado: falta ' + ' e '.join(falta) + '.', secao)
    n = max([r.item for r in p.rubricas] or [0]) + 1
    if tipo == 'rh':
        q = max(1, inteiro(f.get('quantidade'), 1))
        p.rubricas.append(RubricaRH(item=n, cargo=nome, quantidade=q, horas_mes=min(horas, 744), meses=min(meses, 60), faixa_pretendida=faixa or None,
                                    pesquisas=[PesquisaSalarial() for _ in range(3)]))
        motivo = f'item {n} criado: {nome} ({q} profissional(is), ' + (f'faixa pretendida de {brl(faixa)}' if faixa else f'{horas} h por mês') + f', {meses} meses)'
    else:
        regra = f.get('regra') if f.get('regra') in servico.TIPOS_RUBRICA else None
        p.rubricas.append(RubricaMaterial(item=n, descricao=nome, meses=min(meses, 60), regra=regra, fontes=[Fonte() for _ in range(3)]))
        motivo = f'item {n} criado: rubrica {nome} ({meses} meses)'
    db.salvar(pid, p, motivo=motivo)
    return RedirectResponse(f'/p/{pid}/{"rh" if tipo == "rh" else "mat"}/{n}?novo=1', status_code=303)


@app.post('/p/{pid}/excluir/{item}')
def excluir_rubrica(pid: int, item: int):
    p, _ = db.carregar(pid)
    r = next((x for x in p.rubricas if x.item == item), None)
    if r is None:
        return voltar_ao_projeto(pid, f'O item {item} já não estava no plano.')
    p.rubricas = [x for x in p.rubricas if x.item != item]
    db.salvar(pid, p, motivo=f'rubrica {item} excluída (versões anteriores preservadas)')
    nome = r.cargo if isinstance(r, RubricaRH) else r.descricao
    return voltar_ao_projeto(pid, f'Item {item} ({nome}) excluído. Para voltar atrás, use "Desfazer a última alteração", na visão geral.', secao_do_item(r))


@app.post('/p/{pid}/juntar-cargos')
def juntar_cargos(pid: int):
    """Itens de mão de obra repetidos (mesmo cargo e mesma carga) viram um item só, com a quantidade de profissionais."""
    p, _ = db.carregar(pid)
    feitos = servico.juntar_cargos(p, pid)
    if not feitos:
        return voltar_ao_projeto(pid, 'Não há cargos repetidos para juntar.', 'mao-de-obra')
    txt = '; '.join(f'itens {", ".join(str(x) for x in [a] + b)} → 1 item com {q} profissionais' for a, b, q in feitos)
    db.salvar(pid, p, motivo=f'cargos repetidos juntados ({txt}); itens renumerados em sequência')
    return voltar_ao_projeto(pid, f'Cargos repetidos juntados: {txt}. Os itens foram renumerados em sequência; o total do plano não mudou.', 'mao-de-obra')


@app.post('/p/{pid}/revisar')
async def marcar_revisado(request: Request, pid: int):
    """A OSC confere pontos "para revisar" e marca como revisados (ou desfaz): um só (botão da linha ou da tela do item) ou vários de uma
    vez (os marcados na lista). Depois volta para a tela de onde veio. Mudança só de valor não desfaz a revisão."""
    from orcamento.calculo import chave_sem_valores
    f = await request.form()
    p, _ = db.carregar(pid)
    chaves = [f['uma']] if f.get('uma') else [c for c in f.getlist('chave') if c]
    chaves = list(dict.fromkeys(c[:2000] for c in chaves))
    acao = f.get('acao') or 'marcar'
    volta = f.get('volta') or ''
    def voltar(msg):   # só caminhos deste projeto (nunca para fora do sistema)
        if re.fullmatch(rf'/p/{pid}(/(rh|mat)/\d+)?(#[\w\-]+)?', volta) and volta != f'/p/{pid}':
            caminho, _, ancora = volta.partition('#')
            extra = ('?ok=1&msg=' if '/rh/' in caminho else '?leitura=') if caminho != f'/p/{pid}' else '?msg='
            return RedirectResponse(caminho + extra + quote(msg) + (f'#{ancora}' if ancora else ''), status_code=303)
        return voltar_ao_projeto(pid, msg, 'verificacao')
    if not chaves:
        return voltar('Nenhum ponto foi marcado: escolha ao menos um na lista.')
    nomes = [' — '.join((c.split('|') + ['', ''])[:2]) for c in chaves]
    if acao == 'desmarcar':
        alvo = {chave_sem_valores(c) for c in chaves}
        for k in [k for k in p.revisados if chave_sem_valores(k) in alvo]:
            p.revisados.pop(k, None)
        db.salvar(pid, p, motivo=f'{len(chaves)} ponto(s) voltaram para "para revisar": ' + '; '.join(nomes)[:300])
        return voltar(f'{len(chaves)} ponto(s) voltaram para a lista "Para revisar".' if len(chaves) > 1 else f'{nomes[0]}: voltou para a lista "Para revisar".')
    for c in chaves:
        p.revisados[c] = dict(em=db.agora())
    db.salvar(pid, p, motivo=(f'{len(chaves)} pontos marcados como revisados: ' if len(chaves) > 1 else 'ponto marcado como revisado: ') + '; '.join(nomes)[:300])
    return voltar(f'{len(chaves)} pontos marcados como revisados.' if len(chaves) > 1 else f'{nomes[0]}: marcado como revisado.')


@app.get('/p/{pid}/rh/{item}', response_class=HTMLResponse)
def rh_form(request: Request, pid: int, item: int, msg: str = '', ok: str = '', novo: str = ''):
    from orcamento import vagas as V
    p, v = db.carregar(pid)
    r = next((x for x in p.rubricas if x.item == item), None)
    if r is None or not isinstance(r, RubricaRH):
        return voltar_ao_projeto(pid, f'O item {item} não é um cargo deste projeto (pode ter sido excluído ou renumerado).', 'mao-de-obra')
    while len(r.pesquisas) < 3:
        r.pesquisas.append(PesquisaSalarial())
    similares = servico.similares_do_cargo(r)
    titulo_uso = servico.titulo_em_uso(r)
    em_uso = {q.evidencia.url: k for k, q in enumerate(r.pesquisas[:3]) if q.evidencia and q.evidencia.url}
    banco = V.banco_com_similares(r.cargo, similares)
    for x in banco:   # só entra no orçamento vaga com CNPJ confirmado, PDF guardado, salário definido e a empresa visível na página
        combinar = bool(x.get('pdf')) and V.pdf_a_combinar(db.caminho_absoluto(x['pdf']), x.get('faixa_min'))
        oculta = bool(x.get('pdf')) and V.empresa_oculta(caminho=db.caminho_absoluto(x['pdf']))
        errada = bool(x.get('pdf')) and V.pdf_nao_e_a_vaga(db.caminho_absoluto(x['pdf']))
        outro_titulo = V.chave_cargo(x['titulo_busca']) != V.chave_cargo(titulo_uso)   # vagas de títulos diferentes não vão juntas para o orçamento
        x['outro_titulo'] = outro_titulo
        x['usavel'] = x['cnpj_status'] == '🟢' and bool(x.get('pdf')) and not combinar and not oculta and not errada and not outro_titulo
        x['oculta'] = oculta
        x['motivo_nao'] = ('salário a combinar' if combinar else 'a página não mostra as informações da empresa (a Catho só mostra com login)' if oculta
                           else f'o PDF guardado não é a página da vaga: {errada}' if errada
                           else ('sem PDF' if x['cnpj_status'] == '🟢' and not x.get('pdf') else 'CNPJ não confirmado' if x['cnpj_status'] != '🟢'
                                 else f'é de outro título ({x["titulo_busca"]}): para usar, escolha esse título em "Títulos com vagas"'))
        x['em_uso'] = em_uso.get(x['url'])
        motivo = x.get('cnpj_motivo') or ''
        x['confirmavel'] = not combinar and not oculta and (x['cnpj_status'] == '🟡' or (x['cnpj_status'] != '🟢' and 'BAIXADA' not in motivo and 'INAPTA' not in motivo
                                                                        and 'SUSPENSA' not in motivo and 'a combinar' not in motivo))
        if x['confirmavel']:   # empresas da base da Receita com esse nome, para a OSC escolher com um clique (as da cidade e da UF da vaga primeiro)
            try:
                from orcamento import cnpj_busca
                x['candidatos'] = cnpj_busca.candidatos_da_base(x['empresa'], x.get('cidade'), x.get('uf'), limite=6)
            except Exception:
                x['candidatos'] = []
    banco.sort(key=lambda x: (x['em_uso'] is None, x['cnpj_status'] != '🟢', x['cnpj_status'] != '🟡', x['faixa_min'] or 10 ** 9))
    opcoes_similares = list(dict.fromkeys(V.sugestoes_similares(r.cargo) + similares))
    tres = V.tres_do_titulo(titulo_uso, r.faixa_pretendida)
    grupos = V.grupos_de_titulos(r.cargo, similares, r.faixa_pretendida)
    for g in grupos:
        g['em_uso'] = V.chave_cargo(g['titulo']) == V.chave_cargo(titulo_uso)
        g['media'] = (sum(x['faixa_min'] for x in g['vagas']) // len(g['vagas'])) if g['vagas'] else None
    return tpl.TemplateResponse(request, 'rh.html', dict(contexto(p, pid, v), r=r, banco=banco[:80], tres=tres, tres_alcanca=V.alcanca_a_faixa(tres, r.faixa_pretendida),
                                                         grupos=grupos, titulo_uso=titulo_uso, titulos_misturados=servico.titulos_misturados(r),
                                                         horas_pela_faixa=horas_pela_faixa(r, p.config),
                                                         msg=msg, ok=ok, novo=novo, similares=similares, opcoes_similares=opcoes_similares,
                                                         descartadas=V.contar_descartadas(r.cargo, similares), link_busca_cnpj=V.link_busca_cnpj,
                                                         empresa_oculta=lambda rel: V.empresa_oculta(caminho=db.caminho_absoluto(rel))))


@app.post('/p/{pid}/rh/{item}')
async def rh_salvar(request: Request, pid: int, item: int):
    from orcamento import vagas as V
    f = await request.form()
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    cargo_antes = r.cargo
    r.cargo, r.regime = (re.sub(r'\s+', ' ', f.get('cargo') or '').strip() or r.cargo), f.get('regime') or r.regime
    r.quantidade = max(1, min(999, inteiro(f.get('quantidade'), r.quantidade)))
    if 'similares_enviados' in f:   # títulos similares aceitos: os marcados + os escritos (um por linha)
        marcados = list(f.getlist('similar'))
        escritos = [x.strip() for x in re.split(r'[\n;]+', f.get('outros_similares') or '') if x.strip()]
        if not escritos and set(marcados) == set(V.sugestoes_similares(cargo_antes)) and V.chave_cargo(r.cargo) == V.chave_cargo(cargo_antes):
            r.titulos_similares = None if r.titulos_similares is None else V.outros_titulos(r.cargo, marcados)
        else:
            r.titulos_similares = V.outros_titulos(r.cargo, marcados + escritos)
    antes = (r.faixa_pretendida, valores_pesquisa(r), divisor_horas(cargo_antes, p.config.divisor_horas)[0])
    r.horas_mes, r.meses = inteiro(f.get('horas_mes'), r.horas_mes), inteiro(f.get('meses'), r.meses)
    if 'mes_inicio' in f:
        r.mes_inicio = min(max(inteiro(f.get('mes_inicio'), 0), 0), 60) or None
    if 'faixa_pretendida' in f:
        r.faixa_pretendida = cent(f.get('faixa_pretendida')) or None
    pes = []
    for k in range(3):
        fmin, fmax = cent(f.get(f'faixa_min{k}')), cent(f.get(f'faixa_max{k}'))
        url = servico.url_limpa(f.get(f'url{k}'))
        antiga = r.pesquisas[k] if k < len(r.pesquisas) else None
        ev = antiga.evidencia if antiga and antiga.evidencia.arquivo and antiga.evidencia.url == url else Evidencia(url=url, origem='manual')
        mesma_vaga = antiga and antiga.evidencia and antiga.evidencia.url == url
        pes.append(PesquisaSalarial(nome=f.get(f'nome{k}', '').strip(), cnpj=cnpj_formatar(f.get(f'cnpj{k}', '')),
                                    plataforma=f.get(f'plataforma{k}') or None, data_pesquisa=f.get(f'data{k}') or None,
                                    faixa_min=fmin, faixa_max=fmax, valor=fmin, evidencia=ev, titulo_vaga=antiga.titulo_vaga if mesma_vaga else None))
    r.pesquisas = pes
    maxm, _, _ = mensal_maximo_rh(r, p.config)
    r.valor_mensal_plano = cent(f.get('valor_mensal_plano')) if f.get('valor_mensal_plano') else maxm
    # faixa pretendida: quando a faixa, os salários das pesquisas ou a jornada mudam, as horas são recalculadas para o valor chegar na faixa.
    # Se nada disso mudou, ficam as horas que estão na tela (as que o "Fechar no teto" pôs, ou as que a pessoa escreveu).
    nivelado = antes != (r.faixa_pretendida, valores_pesquisa(r), divisor_horas(r.cargo, p.config.divisor_horas)[0]) and nivelar_pela_faixa(r, p.config)
    outros = replicar_pesquisas(p, r)
    db.salvar(pid, p, motivo=f'item {item} (mão de obra) editado' + (f'; horas ajustadas à faixa pretendida ({r.horas_mes} h)' if nivelado else '') + (f'; pesquisas replicadas para os itens {outros} (mesmo cargo)' if outros else ''))
    msg = 'Alterações salvas.' + (f' As mesmas pesquisas foram copiadas para os itens {", ".join(map(str, outros))} (mesmo cargo).' if outros else '')
    if f.get('depois') == 'ficar':
        return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(msg)}', status_code=303)
    depois = f.get('depois') or ''
    if depois == 'buscar':
        tid = tarefas.iniciar('vagas', f'Vagas: {r.cargo} (Brasil, CNPJ)', lambda ctx: servico.vagas_do_cargo(pid, item, ctx), pid)
        return RedirectResponse(f'/tarefa/{tid}', status_code=303)
    if re.fullmatch(r'(outra|pagina)-[0-2]', depois):   # nova pesquisa de UMA das 3 pesquisas (as outras duas ficam como estão)
        k = int(depois[-1])
        if depois.startswith('outra'):
            tid = tarefas.iniciar('vagas', f'Outra vaga para a pesquisa {k + 1}: {r.cargo}', lambda ctx: servico.outra_vaga(pid, item, k, ctx), pid)
        else:
            tid = tarefas.iniciar('vagas', f'Guardar de novo a página da vaga (pesquisa {k + 1}): {r.cargo}', lambda ctx: servico.recapturar_vaga(pid, item, k, ctx), pid)
        return RedirectResponse(f'/tarefa/{tid}', status_code=303)
    return voltar_ao_projeto(pid, f'Item {item} ({r.cargo}): {msg}', f'item{item}')


@app.post('/p/{pid}/rh/{item}/vagas')
def vagas_iniciar(pid: int, item: int):
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    tid = tarefas.iniciar('vagas', f'Vagas: {r.cargo} (Brasil, CNPJ)', lambda ctx: servico.vagas_do_cargo(pid, item, ctx), pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.post('/p/{pid}/rh/{item}/vagas/banco')
def vagas_do_banco(pid: int, item: int):
    """Usa as vagas do banco (sem nova busca): as 3, ou as que houver (1 ou 2), deixando as outras posições como estavam ou em branco."""
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    novas, outros = servico.aplicar_vagas(p, pid, r)
    if not novas:
        return RedirectResponse(f'/p/{pid}/rh/{item}?msg={quote("Não há vaga confirmada no banco para este cargo.")}', status_code=303)
    db.salvar(pid, p, motivo=f'item {item}: {len(novas)} vaga(s) do banco (CNPJ confirmado)' + (f'; replicadas para {outros}' if outros else ''))
    msg = f'{len(novas)} vaga(s) do banco nas pesquisas.' + ('' if len(novas) == 3 else ' As outras posições ficaram como estavam (ou em branco).')
    return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(msg)}#t-pesq', status_code=303)


@app.post('/p/{pid}/rh/{item}/usar-titulo')
def rh_usar_titulo(pid: int, item: int, titulo: str = Form(...)):
    """Troca as 3 pesquisas do cargo pelas vagas de UM título: o do próprio cargo ou um título similar com 3 vagas (nunca dois juntos)."""
    p, _ = db.carregar(pid)
    r = next((x for x in p.rubricas if x.item == item and isinstance(x, RubricaRH)), None)
    if r is None:
        return voltar_ao_projeto(pid, f'O item {item} não é um cargo deste projeto.', 'mao-de-obra')
    try:
        novas, outros = servico.usar_titulo(p, pid, r, titulo)
    except ValueError as e:
        return RedirectResponse(f'/p/{pid}/rh/{item}?msg={quote(str(e))}#t-titulos', status_code=303)
    em_uso = servico.titulo_em_uso(r)
    db.salvar(pid, p, motivo=f'item {item}: as pesquisas passaram a ser das vagas com o título "{em_uso}" ({len(novas)} vaga(s)), por escolha da OSC'
                             + (f'; replicadas para {outros}' if outros else ''))
    msg = (f'As pesquisas agora são das vagas com o título "{em_uso}" ({len(novas)} de 3).'
           + ('' if len(novas) == 3 else ' As posições que faltam ficaram em branco.'))
    return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(msg)}#t-pesq', status_code=303)


@app.post('/p/{pid}/rh/{item}/usar-vaga')
async def rh_usar_vaga(request: Request, pid: int, item: int):
    f = await request.form()
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    k = int(f['k'])
    antes = next((j for j, q in enumerate(r.pesquisas[:3]) if q.evidencia and q.evidencia.url == f['url']), None)
    try:
        nova = servico.usar_vaga(p, pid, r, f['url'], k)
    except ValueError as e:
        return RedirectResponse(f'/p/{pid}/rh/{item}?msg={quote(str(e))}#t-banco', status_code=303)
    maxm, _, _ = mensal_maximo_rh(r, p.config)
    if maxm is not None and len([q for q in r.pesquisas if q.faixa_min]) == 3:
        r.valor_mensal_plano = maxm
    outros = replicar_pesquisas(p, r)
    if antes is not None and antes != k:
        motivo, msg = f'item {item}: pesquisas {antes + 1} e {k + 1} trocadas de lugar', f'A vaga de {nova.nome} passou para a pesquisa {k + 1}.'
    elif antes == k:
        return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(f"A vaga de {nova.nome} já é a pesquisa {k + 1}.")}#t-banco', status_code=303)
    else:
        motivo, msg = f'item {item}: pesquisa {k + 1} trocada por vaga do banco ({nova.nome})', f'A vaga de {nova.nome} entrou na pesquisa {k + 1}.'
    db.salvar(pid, p, motivo=motivo + (f'; replicada para {outros}' if outros else ''))
    return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(msg)}#t-banco', status_code=303)


@app.post('/p/{pid}/catho/entrar')
def catho_entrar(pid: int):
    """Abre a janela do navegador do sistema no login da Catho. Quem entra é a pessoa (o sistema não digita nada nem resolve verificações).
    Depois que a janela é fechada, confere o login e guarda de novo as páginas da Catho do projeto."""
    from orcamento import sessao_catho as SC

    async def rodar(ctx):
        ctx.aviso('Uma janela do navegador do sistema foi aberta na página de login da Catho (se não aparecer, procure na barra de tarefas). '
                  'Entre com a sua conta; se a Catho pedir uma verificação, resolva na própria janela. Quando a sua conta aparecer, feche a janela.')
        await SC.entrar(ctx)
        p, _ = db.carregar(pid)
        urls = [r.pesquisas[k].evidencia.url for r, k in servico.pesquisas_catho_ocultas(p)]
        with db.conectar() as c:
            urls += [row['url'] for row in c.execute("SELECT url FROM vaga_banco WHERE plataforma='Catho' ORDER BY coletada_em DESC LIMIT 4")]
        ok = await SC.conferir(list(dict.fromkeys(urls)), ctx)
        if ok is False:
            ctx.aviso('A Catho não reconheceu o login: as páginas continuam escondendo a empresa. Clique em "Entrar na Catho" de novo e, antes de '
                      'fechar a janela, confira se a sua conta aparece no alto da página.')
            ctx.progresso(100, 'Concluído')
            return dict(ir_para=f'/p/{pid}#catho')
        if ok is None:
            SC._gravar(ok=True, mensagem='sessão ainda não conferida (não havia vaga da Catho aberta para conferir)')
        return await servico.recapturar_catho(pid, ctx)
    tid = tarefas.iniciar('catho', 'Entrar na Catho e guardar de novo as páginas das vagas', rodar, pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.post('/p/{pid}/catho/recapturar')
def catho_recapturar(pid: int):
    tid = tarefas.iniciar('catho', 'Guardar de novo as páginas da Catho (com a empresa visível)', lambda ctx: servico.recapturar_catho(pid, ctx), pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.post('/catho/sair')
def catho_sair(request: Request):
    """Apaga a sessão da Catho deste computador (o perfil do navegador do sistema)."""
    from urllib.parse import urlparse
    from orcamento import sessao_catho as SC
    SC.sair()
    volta = urlparse(request.headers.get('referer') or '/').path or '/'   # só o caminho: nunca redireciona para fora do sistema
    return RedirectResponse(volta + '?msg=' + quote('Você saiu da Catho neste computador: a sessão foi apagada.') + '#catho', status_code=303)


@app.post('/p/{pid}/rh/{item}/pesquisa/{k}/pdf')
async def rh_pdf(pid: int, item: int, k: int, arquivo: UploadFile = File(...)):
    """A OSC anexa a página da vaga em PDF numa pesquisa de salário (ex.: impressa da Catho com o login feito). Guarda a evidência (SHA-256)."""
    p, _ = db.carregar(pid)
    r = next((x for x in p.rubricas if x.item == item), None)
    if r is None or not isinstance(r, RubricaRH) or not 0 <= k < 3:
        return HTMLResponse('Pesquisa não encontrada.', status_code=404)
    try:
        msg = servico.anexar_pdf_vaga(p, pid, r, k, arquivo.filename, await arquivo.read())
    except ValueError as e:
        return RedirectResponse(f'/p/{pid}/rh/{item}?msg={quote("Não anexado: " + str(e) + ".")}#pesquisa{k}', status_code=303)
    outros = replicar_pesquisas(p, r)
    db.salvar(pid, p, motivo=f'item {item}: PDF da vaga anexado à pesquisa {k + 1} ({r.pesquisas[k].nome})' + (f'; replicado para {outros}' if outros else ''),
              arquivo=arquivo.filename, sha256=r.pesquisas[k].evidencia.sha256)
    return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(msg)}#pesquisa{k}', status_code=303)


@app.post('/p/{pid}/rh/{item}/vaga/confirmar')
def rh_confirmar_vaga(pid: int, item: int, url: str = Form(...), cnpj: str = Form(''), cnpj_escolhido: str = Form('')):
    """A OSC confirma a empresa de uma vaga "em dúvida" — escolhendo uma das empresas com esse nome na base da Receita ou digitando o CNPJ:
    confere o CNPJ (ATIVO), guarda a página da vaga em PDF e, se o cargo tiver pesquisa em branco (e a vaga for do título em uso), já a coloca."""
    from orcamento import vagas as V
    cnpj = cnpj_escolhido or cnpj

    async def rodar(ctx):
        res = await V.confirmar_vaga(url, cnpj, ctx)
        p, _ = db.carregar(pid)
        r = next(x for x in p.rubricas if x.item == item)
        while len(r.pesquisas) < 3:
            r.pesquisas.append(PesquisaSalarial())
        vaga = next((k for k, q in enumerate(r.pesquisas[:3]) if not servico.pesquisa_completa(q)), None)
        do_titulo = any(v['url'] == url for v in V.vagas_do_banco(servico.titulo_em_uso(r), so_verdes=False))   # vaga de outro título não entra junto
        if vaga is not None and do_titulo and not any(servico._raiz(q.cnpj) == servico._raiz(res['cnpj']) for q in r.pesquisas):
            servico.usar_vaga(p, pid, r, url, vaga)
            maxm, _, _ = mensal_maximo_rh(r, p.config)
            if maxm is not None:
                r.valor_mensal_plano = maxm
            outros = replicar_pesquisas(p, r)
            db.salvar(pid, p, motivo=f'item {item}: vaga de {res["empresa"]} confirmada pela OSC (CNPJ {res["cnpj"]}) e usada na pesquisa {vaga + 1}'
                      + (f'; replicada para {outros}' if outros else ''))
            ctx.aviso(f'Vaga de {res["empresa"]} confirmada (CNPJ {res["cnpj"]}, ATIVO) e colocada na pesquisa {vaga + 1}, que estava em branco.')
        else:
            ctx.aviso(f'Vaga de {res["empresa"]} confirmada (CNPJ {res["cnpj"]}, ATIVO). '
                      + ('Para usá-la, clique no número da pesquisa na tabela do banco de vagas.' if do_titulo else
                         'Ela é de outro título: conta para o grupo desse título em "Títulos com vagas" (vagas de títulos diferentes não vão juntas).'))
        return dict(res, ir_para=f'/p/{pid}/rh/{item}#t-banco')
    tid = tarefas.iniciar('vaga_confirmar', 'Confirmar a empresa de uma vaga', rodar, pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.post('/p/{pid}/rh/{item}/vaga/descartar')
def rh_descartar_vaga(pid: int, item: int, url: str = Form(...), desfazer: str = Form('')):
    from orcamento import vagas as V
    try:
        V.descartar_vaga(url, descartar=not desfazer)
    except ValueError as e:
        return RedirectResponse(f'/p/{pid}/rh/{item}?msg={quote(str(e))}#t-banco', status_code=303)
    msg = 'Vaga descartada: ela não aparece mais nem entra nas pesquisas.' if not desfazer else 'A vaga voltou para o banco.'
    return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(msg)}#t-banco', status_code=303)


@app.post('/p/{pid}/rh/{item}/vaga/mostrar-descartadas')
def rh_mostrar_descartadas(pid: int, item: int):
    from orcamento import vagas as V
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    n = V.mostrar_descartadas(r.cargo, servico.similares_do_cargo(r))
    return RedirectResponse(f'/p/{pid}/rh/{item}?ok=1&msg={quote(f"{n} vaga(s) descartada(s) voltaram para o banco.")}#t-banco', status_code=303)


@app.get('/vaga/pdf')
def vaga_pdf(url: str):
    """Abre o PDF guardado de uma vaga do banco (a página como estava no dia da pesquisa)."""
    with db.conectar() as c:
        row = c.execute('SELECT pdf FROM vaga_banco WHERE url=?', (url,)).fetchone()
    base = os.path.realpath(os.path.join(db.PASTA_DADOS, 'banco_vagas'))
    alvo = os.path.realpath(os.path.join(db.PASTA_DADOS, row['pdf'])) if row and row['pdf'] else ''
    if not alvo or not alvo.startswith(base + os.sep) or not os.path.isfile(alvo):
        return HTMLResponse('PDF da vaga não encontrado.', status_code=404)
    return FileResponse(alvo, media_type='application/pdf')


TELA_DO_TIPO = {'sistema': 'sistema.html', 'servico': 'servico.html'}   # produtos (mercado e outros materiais): mat.html


@app.get('/p/{pid}/mat/{item}', response_class=HTMLResponse)
def mat_form(request: Request, pid: int, item: int, leitura: str = '', novo: str = '', extra: dict = None):
    p, v = abrir(pid)
    r = next((x for x in p.rubricas if x.item == item), None)
    if r is None or isinstance(r, RubricaRH):
        return voltar_ao_projeto(pid, f'O item {item} não é uma rubrica de materiais ou serviços deste projeto (pode ter sido excluído ou renumerado).', 'materiais')
    while len(r.fontes) < 3:
        r.fontes.append(Fonte())
    servico.acertar_trocados(p)   # item trocado antes de 03/10/2026: especificação e marca passam a ser as do produto (gravado ao salvar)
    tipo = servico.tipo_da_rubrica(r)
    if tipo == 'sistema' and not r.subitens:   # o sistema é um item só: aparece pronto para preencher (é gravado ao salvar)
        r.subitens = [Subitem(descricao=r.descricao, qtd=1)]
    return tpl.TemplateResponse(request, TELA_DO_TIPO.get(tipo, 'mat.html'),
                                dict(contexto(p, pid, v), r=r, tipo=tipo, palavras_padrao=palavras_padrao, leitura=leitura, novo=novo,
                                     banco=db.produtos_do_banco(pid, item), sistemas=sistemas_mod, atende_o_pedido=cesta_atende,
                                     aguarda_decisao=servico.aguarda_decisao, nao_achado=servico.nao_achado, perto_do_pedido=servico.perto_do_pedido, **(extra or {})))


@app.post('/p/{pid}/mat/{item}/sugerir', response_class=HTMLResponse)
def mat_sugerir(request: Request, pid: int, item: int, para_que: str = Form('')):
    """A IA sugere itens e quantidades por mês para a rubrica, a partir do que a OSC descreveu. NADA é gravado: a tela mostra a sugestão
    conferida, e a pessoa marca o que quer acrescentar. A IA recebe o nome da rubrica, a descrição e os nomes dos itens que já existem."""
    from orcamento import ia
    p, _ = abrir(pid)
    r = next((x for x in p.rubricas if x.item == item and not isinstance(x, RubricaRH)), None)
    if r is None:
        return voltar_ao_projeto(pid, f'O item {item} não é uma rubrica de materiais deste projeto.', 'materiais')
    para_que = re.sub(r'\s+', ' ', para_que).strip()
    if len(para_que) < 15:
        return mat_form(request, pid, item, leitura='Não deu para sugerir: descreva a atividade com um pouco mais de detalhe (quantas pessoas, com que frequência).',
                        extra=dict(para_que=para_que))
    if not ia.disponivel():
        return mat_form(request, pid, item, leitura='Não deu para sugerir: a IA gratuita não está configurada neste computador. Cadastre os itens no quadro "Adicionar itens".',
                        extra=dict(para_que=para_que))
    bruto = ia.sugerir_itens(r.descricao, para_que, [descricao_completa(s) for s in r.subitens], pid)
    if bruto is None:
        return mat_form(request, pid, item, leitura='Não foi possível consultar a IA agora (limite gratuito ou falha de rede). Tente de novo em alguns minutos.',
                        extra=dict(para_que=para_que))
    sugestoes = servico.sugestoes_conferidas(r, bruto)
    return mat_form(request, pid, item, extra=dict(para_que=para_que, sugestoes=sugestoes, sugestoes_json=json.dumps(sugestoes, ensure_ascii=False)))


@app.post('/p/{pid}/mat/{item}/sugerir/aplicar')
async def mat_sugerir_aplicar(request: Request, pid: int, item: int):
    """Acrescenta à rubrica os itens sugeridos que a pessoa marcou (com a quantidade que ela deixou). Os preços vêm depois, da pesquisa."""
    f = await request.form()
    p, _ = abrir(pid)
    r = next((x for x in p.rubricas if x.item == item and not isinstance(x, RubricaRH)), None)
    if r is None:
        return voltar_ao_projeto(pid, f'O item {item} não é uma rubrica de materiais deste projeto.', 'materiais')
    try:
        bruto = json.loads(f.get('dados') or '[]')
    except ValueError:
        bruto = []
    marcados = {inteiro(x, -1) for x in f.getlist('sugestao')}
    escolhidos = []
    for k, x in enumerate(bruto if isinstance(bruto, list) else []):
        if k in marcados and isinstance(x, dict):
            escolhidos.append(dict(x, quantidade=inteiro(f.get(f'qtd{k}'), x.get('quantidade') if isinstance(x.get('quantidade'), int) else 0)))
    novos = servico.sugestoes_conferidas(r, escolhidos)   # conferidas de novo: o que volta da tela não é aceito sem conferir
    if not novos:
        return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote("Não foi acrescentado nenhum item: nenhuma sugestão estava marcada.")}', status_code=303)
    for x in novos:
        r.subitens.append(Subitem(descricao=x['descricao'], especificacao=x['especificacao'] or None, qtd=x['quantidade']))
    db.salvar(pid, p, motivo=f'item {item}: {len(novos)} item(ns) sugerido(s) pela IA e aceito(s) pela OSC ({", ".join(x["descricao"] for x in novos)[:160]})')
    msg = f'{len(novos)} item(ns) acrescentado(s). Confira as quantidades e clique em "Salvar e pesquisar os preços".'
    return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote(msg)}#t-itens', status_code=303)


@app.post('/p/{pid}/mat/{item}')
async def mat_salvar(request: Request, pid: int, item: int):
    f = await request.form()
    p, _ = abrir(pid)   # com o mesmo acerto que a tela mostrou (senão a especificação nova pareceria uma mudança feita pela OSC)
    r = next(x for x in p.rubricas if x.item == item)
    de_produtos = servico.tipo_da_rubrica(r) not in ('sistema', 'servico')
    chaves_antes = {id(x): pedido_do_subitem(x) for x in r.subitens}
    r.descricao, r.meses = (f.get('descricao') or '').strip() or r.descricao, inteiro(f.get('meses'), r.meses)
    if 'mes_inicio' in f:
        r.mes_inicio = min(max(inteiro(f.get('mes_inicio'), 0), 0), 60) or None
    # cada tipo de rubrica tem a sua tela: só muda o que a tela mostrou (sistema e serviço não têm teto, itens extras nem fornecedores padrão)
    if 'teto_mensal' in f:
        r.teto_mensal = cent(f.get('teto_mensal'))
    if 'extras' in f:
        r.extras = [x.strip() for x in re.split(r'[\n;]+', f.get('extras', '')) if x.strip()]
    if 'regra' in f:
        r.regra = f.get('regra') or None
    if 'referencia' in f:
        r.referencia = f.get('referencia').strip() or None
    while len(r.fontes) < 3:
        r.fontes.append(Fonte())
    for k in range(3):
        if f'fnome{k}' in f:
            r.fontes[k].nome = f.get(f'fnome{k}', '').strip(); r.fontes[k].cnpj = cnpj_formatar(f.get(f'fcnpj{k}', ''))
            r.fontes[k].data_pesquisa = f.get(f'fdata{k}') or None
    novos, por_indice, excluidos = [], {}, 0
    for i in range(int(f.get('n_sub', 0)) + 1):
        d = re.sub(r'\s+', ' ', f.get(f'sdesc{i}') or '').strip()
        if f.get(f'sdel{i}'):
            excluidos += 1
            continue
        if not d:
            continue
        antigo = r.subitens[i] if i < len(r.subitens) else Subitem(descricao=d, qtd=1)
        esp = (re.sub(r'\s+', ' ', f.get(f'sesp{i}') or '').strip() or None) if f'sesp{i}' in f else antigo.especificacao
        marca = (re.sub(r'\s+', ' ', f.get(f'smarca{i}') or '').strip() or None) if f'smarca{i}' in f else antigo.marca
        if antigo.descricao_original and (d != antigo.descricao or texto.formatar_medidas(esp) != antigo.especificacao or marca != antigo.marca):
            # a OSC reescreveu um item que a pesquisa tinha trocado: o que ela escreveu agora é o novo pedido
            antigo.descricao_original, antigo.especificacao_original, antigo.marca_original, antigo.nivel = None, None, None, 0
        if de_produtos and not antigo.descricao_original:   # o que foi digitado, nos campos certos: marca fora da descrição, medida na especificação, 1L e não 1l
            d, marca, esp = texto.arrumar_item(d, marca, esp)
        elif esp:
            esp = texto.formatar_medidas(esp)
        antigo.especificacao, antigo.marca = esp, marca
        antigo.descricao, antigo.qtd = d, inteiro(f.get(f'sqtd{i}'), 1) or 1
        por_indice[i] = antigo
        if f'sfam{i}' in f:
            antigo.familia = (f.get(f'sfam{i}') or '').strip() or None
        if f'spal{i}' in f:
            antigo.palavras = [w for w in re.split(r'[,;]\s*', f.get(f'spal{i}', '')) if w.strip()]
        antigo.precos = [cent(f.get(f'sp{i}_{k}')) for k in range(3)]
        antigo.valor_plano = cent(f.get(f'splano{i}'))
        if f'sfn{i}_0' in f:   # fornecedor de cada pesquisa do subitem (editável)
            atuais = fontes_do_subitem(r, antigo)
            novas = [(f.get(f'sfn{i}_{k}', '').strip(), cnpj_formatar(f.get(f'sfc{i}_{k}', '')), f.get(f'sfd{i}_{k}') or None) for k in range(3)]
            mudou = any(k >= len(atuais) or (atuais[k].nome, cnpj_formatar(atuais[k].cnpj), atuais[k].data_pesquisa) != novas[k] for k in range(3))
            if mudou and any(n or c for n, c, _ in novas):
                if len(antigo.fontes) != 3:   # o subitem passa a ter as suas 3 pesquisas
                    antigo.fontes = ([x.model_copy(deep=True) for x in atuais] + [Fonte(), Fonte(), Fonte()])[:3]
                for k, (nome, cnpj, data) in enumerate(novas):
                    fonte = antigo.fontes[k]
                    if nome != fonte.nome:
                        fonte.plataforma = None   # o nome comercial era do fornecedor anterior
                    fonte.nome, fonte.cnpj, fonte.data_pesquisa = nome, cnpj, data
            while len(antigo.produtos) < 3:
                antigo.produtos.append(None)
            for k in range(3):
                if f'sfp{i}_{k}' in f:
                    antigo.produtos[k] = f.get(f'sfp{i}_{k}').strip() or None
        if len(antigo.fontes) != 3 and any((f.get(f'surl{i}_{k}') or '').strip() for k in range(3)):   # link digitado: o item passa a ter as suas 3 pesquisas
            antigo.fontes = ([x.model_copy(deep=True) for x in fontes_do_subitem(r, antigo)] + [Fonte(), Fonte(), Fonte()])[:3]
        for k, fonte in enumerate(antigo.fontes[:3]):   # link editável e OPCIONAL (proposta em PDF não tem link)
            url = servico.url_limpa(f.get(f'surl{i}_{k}'))
            if f'surl{i}_{k}' in f and url != fonte.evidencia.url:
                if url is None or fonte.evidencia.origem == 'pdf':   # link apagado, ou PDF anexado pela OSC: o PDF continua valendo
                    fonte.evidencia.url = url
                else:                                                  # outro endereço: o PDF antigo era de outra página
                    fonte.evidencia = Evidencia(url=url, origem='manual')
        novos.append(antigo)
    # vários itens novos de uma vez (cada linha do quadro "Adicionar itens"): descrição, especificação (opcional) e quantidade
    pedidos = {pedido_do_subitem(x) for x in novos}
    adicionados, repetidos = [], []
    nd = f.getlist('ndesc')
    for d, marca, esp, q in zip(nd, f.getlist('nmarca') or [''] * len(nd), f.getlist('nesp') or [''] * len(nd), f.getlist('nqtd') or [''] * len(nd)):
        d, esp = re.sub(r'\s+', ' ', d or '').strip(), re.sub(r'\s+', ' ', esp or '').strip() or None
        if not d:
            continue
        marca = re.sub(r'\s+', ' ', marca or '').strip() or None
        if de_produtos:
            d, marca, esp = texto.arrumar_item(d, marca, esp)
        elif esp:
            esp = texto.formatar_medidas(esp)
        x = Subitem(descricao=d, marca=marca, especificacao=esp, qtd=max(1, inteiro(q, 1)))
        if pedido_do_subitem(x) in pedidos:
            repetidos.append(d); continue
        pedidos.add(pedido_do_subitem(x)); novos.append(x); adicionados.append(x)
    r.subitens = novos
    if servico.tipo_da_rubrica(r) == 'sistema':   # sistema: o valor no plano é sempre o menor das 3 cotações
        for x in r.subitens:
            x.valor_plano = servico.valor_do_sistema(x)
    partes = [f'{len(adicionados)} item(ns) adicionado(s)' if adicionados else '', f'{excluidos} excluído(s)' if excluidos else '']
    db.salvar(pid, p, motivo=f'item {item} (material) editado' + ''.join(f'; {x}' for x in partes if x))
    servico.migrar_banco(pid, [(item, chaves_antes[id(x)], pedido_do_subitem(x)) for x in r.subitens if id(x) in chaves_antes])   # item reescrito: as opções guardadas acompanham
    msg = 'Alterações salvas' + ''.join(f'; {x}' for x in partes if x) + '.' + (
        f' Não repetido (já está na rubrica): {", ".join(repetidos)}.' if repetidos else '')
    depois = f.get('depois') or 'voltar'
    if depois == 'pesquisar' or depois.startswith('repesquisar-'):
        return iniciar_pesquisa_da_rubrica(pid, item, r, depois, f, por_indice)
    m = re.fullmatch(r'trocarloja-(\d+)-([0-2])', depois)   # nova pesquisa de UMA das 3 pesquisas do item: outra loja, mesmo produto
    if m and por_indice.get(int(m.group(1))) is not None:
        i, k = r.subitens.index(por_indice[int(m.group(1))]), int(m.group(2))
        tid = tarefas.iniciar('produtos', f'Outra loja para a pesquisa {k + 1}: {pedido_do_subitem(r.subitens[i])}',
                              lambda ctx: servico.trocar_loja(pid, item, i, k, ctx), pid)
        return RedirectResponse(f'/tarefa/{tid}', status_code=303)
    m = re.fullmatch(r'pagina-(\d+)-([0-2])', depois)       # guardar de novo o comprovante de UMA pesquisa (mesma loja, mesma página)
    if m and por_indice.get(int(m.group(1))) is not None:
        i, k = r.subitens.index(por_indice[int(m.group(1))]), int(m.group(2))
        tid = tarefas.iniciar('comprovantes', f'Guardar de novo a página da pesquisa {k + 1}: {pedido_do_subitem(r.subitens[i])}',
                              lambda ctx: servico.recapturar_pesquisa(pid, item, i, k, ctx), pid)
        return RedirectResponse(f'/tarefa/{tid}', status_code=303)
    m = re.fullmatch(r'cotar-([0-2])', depois)                 # sistema: cota de novo só uma das 3 cotações
    if m and servico.tipo_da_rubrica(r) == 'sistema':
        k = int(m.group(1))
        tid = tarefas.iniciar('sistemas', f'Cotar de novo a cotação {k + 1}: item {item} — {r.descricao}',
                              lambda ctx: servico.pesquisar_sistema(pid, item, ctx, somente_k=k), pid)
        return RedirectResponse(f'/tarefa/{tid}', status_code=303)
    if depois == 'ficar':
        return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote(msg)}', status_code=303)
    return voltar_ao_projeto(pid, f'Item {item} ({r.descricao}): {msg}', f'item{item}')


def _rubrica_de(p, item):
    return next(x for x in p.rubricas if x.item == item)


@app.post('/p/{pid}/mat/{item}/desfazer-substituicao')
async def mat_desfazer_substituicao(request: Request, pid: int, item: int):
    """A OSC não quer a substituição que está num item (ou em todos os da rubrica): ele volta a ser o que foi pedido, sem pesquisas."""
    f = await request.form()
    p, _ = abrir(pid)
    r = next((x for x in p.rubricas if x.item == item and not isinstance(x, RubricaRH)), None)
    if r is None:
        return voltar_ao_projeto(pid, f'O item {item} não é uma rubrica de materiais deste projeto.', 'materiais')
    alvo = f.get('desc')
    feitos = []
    for s in r.subitens:
        if s.descricao_original and (alvo == '*' or pedido_do_subitem(s) == alvo):
            era = servico.desfazer_substituicao(s)
            feitos.append(f'{era} → {descricao_completa(s)}')
    if not feitos:
        return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote("Não havia substituição para desfazer.")}', status_code=303)
    db.salvar(pid, p, motivo=f'item {item}: {len(feitos)} substituição(ões) desfeita(s) pela OSC ({"; ".join(feitos)[:200]})')
    msg = (f'{len(feitos)} substituição(ões) desfeita(s): o item voltou a ser o que foi pedido, sem pesquisas. '
           'Agora mude o pedido se quiser e use "Pesquisar de novo só este item", ou preencha à mão.')
    return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote(msg)}#t-itens', status_code=303)


def iniciar_pesquisa_da_rubrica(pid, item, r, depois, f, por_indice):
    """Depois de salvar: pesquisa a rubrica toda, ou só um item ("Pesquisar de novo só este item", nas mesmas lojas ou em outras)."""
    if depois == 'pesquisar':
        if servico.tipo_da_rubrica(r) == 'sistema':
            tid = tarefas.iniciar('sistemas', f'Sistemas: item {item} — {r.descricao}', lambda ctx: servico.pesquisar_sistema(pid, item, ctx), pid)
        elif not r.subitens:
            return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote("Não pesquisado: cadastre ao menos um item.")}', status_code=303)
        else:
            tid = tarefas.iniciar('produtos', f'Produtos: item {item} — {r.descricao}', lambda ctx: servico.pesquisar_rubrica(pid, item, ctx), pid)
        return RedirectResponse(f'/tarefa/{tid}', status_code=303)
    i = inteiro(depois.split('-', 1)[1], -1)
    s = por_indice.get(i)
    if s is None:
        return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote("Não pesquisado: o item foi excluído ou ficou sem descrição.")}', status_code=303)
    pedido = pedido_do_subitem(s)
    nomes = {l['nome']: k for k, l in LOJAS.items()}
    sem = [nomes[x.plataforma] for x in s.fontes if x.plataforma in nomes] if f.get(f'modo{i}') == 'outras' else []
    ancora = r.subitens.index(s)

    async def rodar(ctx):
        prop = await servico.pesquisar_rubrica(pid, item, _Sub(ctx, 0, 2), somente=[pedido], sem_lojas=sem, respeitar_teto=False)
        linha = next((l for l in prop['linhas'] if l['desc'] == pedido), None)
        if linha and (linha.get('decidir') or linha.get('sem_opcao')):   # não achou o item pedido: nada é substituído; a OSC decide na tela do item
            perto = (servico.PERTO + servico.texto_do_quase(linha['quase']) + servico.FALTA_A_TERCEIRA) if linha.get('quase') else ''
            ctx.aviso(f'"{pedido}": o item pedido não foi achado igual em 3 lojas' + (' diferentes das atuais' if sem else '') + '. NADA foi substituído. '
                      + (f'Há {linha["decidir"]} opção(ões) de substituição na tela do item: escolha uma, ou mude a descrição, a marca ou a especificação '
                         'e pesquise de novo.' if linha.get('decidir') else
                         'Também não há opção de substituição: mude a descrição, a marca ou a especificação e pesquise de novo, ou preencha as 3 pesquisas à mão.')
                      + perto)
            p2, _ = db.carregar(pid)
            s2 = next((x for x in _rubrica_de(p2, item).subitens if pedido_do_subitem(x) == pedido), None)
            if s2 is not None and not servico.subitem_pronto(s2):   # item ainda sem pesquisa: fica dito no próprio item por que está pendente
                s2.justificativa = linha['motivo']
                db.salvar(pid, p2, autor='sistema (pesquisa automática)', motivo=f'item {item}: "{pedido}" não achado igual em 3 lojas; nada foi substituído', tarefa=ctx.id)
            ctx.progresso(100, 'Concluído')
            return dict(ir_para=f'/p/{pid}/mat/{item}#decidir{ancora}')
        if not linha or linha['acao'] == 'RETIRADO' or not linha.get('opcao_dados'):
            ctx.aviso(f'"{pedido}": nenhuma nova opção com o mesmo produto em 3 lojas' + (' diferentes das atuais' if sem else '')
                      + (f' ({linha["motivo"]})' if linha and linha.get('motivo') else '') + '. As pesquisas do item ficaram como estavam. '
                      'Tente mudar a descrição ou a especificação, ou preencha as pesquisas à mão.')
            ctx.progresso(100, 'Concluído')
            return dict(ir_para=f'/p/{pid}/mat/{item}#sub{ancora}')
        await servico.aplicar_proposta(pid, item, prop, _Sub(ctx, 1, 2))
        return dict(ir_para=f'/p/{pid}/mat/{item}#sub{ancora}')
    tid = tarefas.iniciar('produtos', f'Nova pesquisa: {pedido}' + (' (outras lojas)' if sem else ''), rodar, pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.post('/p/{pid}/mat/{item}/sub/{i}/pdf/{k}')
async def mat_pdf(pid: int, item: int, i: int, k: int, arquivo: UploadFile = File(...)):
    """Anexa o PDF de uma pesquisa (proposta comercial sem link, página impressa…). Guarda a evidência (SHA-256)."""
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    if not r.subitens and i == 0 and servico.tipo_da_rubrica(r) == 'sistema':   # o item do sistema ainda não tinha sido gravado
        r.subitens = [Subitem(descricao=r.descricao, qtd=1)]
    if not (0 <= i < len(r.subitens) and 0 <= k < 3):
        return HTMLResponse('Pesquisa não encontrada.', status_code=404)
    try:
        msg = servico.anexar_pdf(p, pid, r, i, k, arquivo.filename, await arquivo.read())
    except ValueError as e:
        return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote("Não anexado: " + str(e))}', status_code=303)
    db.salvar(pid, p, motivo=f'item {item}: PDF anexado à pesquisa {k + 1} de "{r.subitens[i].descricao}"', arquivo=arquivo.filename,
              sha256=r.subitens[i].fontes[k].evidencia.sha256)
    return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={quote(msg)}', status_code=303)


@app.post('/p/{pid}/mat/{item}/pesquisar')
def mat_pesquisar(pid: int, item: int):
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    if servico.tipo_da_rubrica(r) == 'sistema':
        tid = tarefas.iniciar('sistemas', f'Sistemas: item {item} — {r.descricao}', lambda ctx: servico.pesquisar_sistema(pid, item, ctx), pid)
    else:
        tid = tarefas.iniciar('produtos', f'Produtos: item {item} — {r.descricao}', lambda ctx: servico.pesquisar_rubrica(pid, item, ctx), pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.post('/p/{pid}/mat/{item}/trocar')
async def mat_trocar(request: Request, pid: int, item: int):
    """Troca o produto de um subitem por outra opção do banco de produtos (com novos comprovantes)."""
    f = await request.form()
    desc, idx = f['desc'], int(f['opcao'])
    tid = tarefas.iniciar('troca', f'Trocar produto: {desc}', lambda ctx: servico.trocar_produto(pid, item, desc, idx, ctx), pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


@app.get('/p/{pid}/mat/{item}/proposta/{tid}', response_class=HTMLResponse)
def mat_proposta(request: Request, pid: int, item: int, tid: int):
    p, v = db.carregar(pid)
    t = tarefas.ler(tid)
    r = next(x for x in p.rubricas if x.item == item)
    return tpl.TemplateResponse(request, 'proposta.html', dict(contexto(p, pid, v), r=r, t=t, prop=(t or {}).get('resultado')))


@app.post('/p/{pid}/mat/{item}/proposta/{tid}/aplicar')
def mat_aplicar(pid: int, item: int, tid: int):
    prop = tarefas.ler(tid)['resultado']
    novo = tarefas.iniciar('comprovantes', f'Comprovantes e grade: item {item}', lambda ctx: servico.aplicar_proposta(pid, item, prop, ctx), pid)
    return RedirectResponse(f'/tarefa/{novo}', status_code=303)


@app.post('/p/{pid}/mat/{item}/carrinho/{k}')
async def carrinho(pid: int, item: int, k: int, arquivo: UploadFile = File(...)):
    """Lê o PDF do carrinho impresso da fonte k e preenche preços, produtos, CNPJ e data. Guarda a evidência (SHA-256)."""
    p, _ = db.carregar(pid)
    r = next(x for x in p.rubricas if x.item == item)
    conteudo = await arquivo.read()
    sha, rel = db.guardar_arquivo(pid, arquivo.filename, conteudo)
    res = ler_pdf(conteudo, r.subitens)
    ok = rev = 0
    for s in r.subitens:
        x = res['itens'].get(s.descricao, {})
        if x.get('status') == 'OK':
            s.precos[k] = x['unitario']; s.produtos[k] = x['produto']; ok += 1
        else:
            rev += 1
    fonte = r.fontes[k]
    cnpjs = [c for c in res['cnpjs'] if c not in CNPJ_PLATAFORMAS]
    if not fonte.cnpj and cnpjs:
        fonte.cnpj = cnpjs[0]
    if res['datas']:
        d, m, a = res['datas'][0].split('/'); fonte.data_pesquisa = f'{a}-{m}-{d}'
    fonte.evidencia = Evidencia(arquivo=rel, sha256=sha, origem='pdf', capturado_em=db.agora())
    db.salvar(pid, p, motivo=f'carrinho da fonte {k + 1} lido (item {item})', arquivo=arquivo.filename, sha256=sha, lidos=ok, revisao=rev)
    msg = f'Fonte {k + 1}: {ok} preço(s) lido(s) com conferência; {rev} para revisão humana' + (' (PDF sem texto: preencha manualmente)' if res['sem_texto'] else '')
    return RedirectResponse(f'/p/{pid}/mat/{item}?leitura={msg}', status_code=303)


@app.get('/p/{pid}/arquivo')
def arquivo(pid: int, rel: str):
    """Abre uma evidência guardada (somente arquivos deste projeto)."""
    base = os.path.realpath(os.path.join(db.PASTA_DADOS, 'projetos', str(pid)))
    alvo = os.path.realpath(os.path.join(db.PASTA_DADOS, rel))
    if not alvo.startswith(base + os.sep) or not os.path.isfile(alvo):
        return HTMLResponse('Arquivo não encontrado.', status_code=404)
    return FileResponse(alvo)


# ------------------------------------------------------------------ base da Receita
def usos_cnpj(p):
    """{CNPJ: [onde é usado]} para a tela de comprovantes."""
    out = {}
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            for q in r.pesquisas:
                if q.cnpj:
                    out.setdefault(cnpj_formatar(q.cnpj), []).append(f'item {r.item} ({r.cargo}): {q.nome}')
        else:
            for s_ in r.subitens:
                for f_ in fontes_do_subitem(r, s_):
                    if f_.cnpj:
                        out.setdefault(cnpj_formatar(f_.cnpj), []).append(f'item {r.item}: {f_.plataforma or f_.nome}')
    return {c: list(dict.fromkeys(v)) for c, v in out.items()}


@app.post('/lojas/{loja}/reativar')
def loja_reativar(request: Request, loja: str):
    from urllib.parse import urlparse
    db.loja_liberar(loja)
    volta = urlparse(request.headers.get('referer') or '/').path or '/'   # só o caminho: nunca redireciona para fora do sistema
    return RedirectResponse(volta, status_code=303)


@app.get('/p/{pid}/cnpjs', response_class=HTMLResponse)
def cnpjs_pagina(request: Request, pid: int, msg: str = ''):
    from orcamento import cnpj_base, comprovante_receita as CR
    p, v = db.carregar(pid)
    usos = usos_cnpj(p)
    pasta = CR.pasta_dos_comprovantes(criar=True)   # "Orça.AI", em Documentos: já existe quando a pessoa for salvar o primeiro PDF
    na_pasta = CR.baixados()   # comprovantes já salvos na pasta e ainda não importados
    linhas = [dict(cnpj=c, base=cnpj_base.por_cnpj(c), comp=p.comprovantes_cnpj.get(c), url=CR.url_emissao(c), usos=u, baixado=na_pasta.get(c)) for c, u in usos.items()]
    linhas.sort(key=lambda l: (bool(l['comp']), l['cnpj']))
    return tpl.TemplateResponse(request, 'cnpjs.html', dict(contexto(p, pid, v), linhas=linhas, msg=msg, pasta_comprovantes=pasta))


@app.post('/pasta-comprovantes/abrir')
def pasta_comprovantes_abrir(request: Request):
    """Abre no Explorador de Arquivos a pasta dos comprovantes (para a pessoa ver onde salvar e o que já salvou)."""
    from urllib.parse import urlparse
    from orcamento import comprovante_receita as CR
    pasta = CR.pasta_dos_comprovantes(criar=True)
    try:
        os.startfile(pasta)
    except (AttributeError, OSError):   # fora do Windows, ou pasta inacessível: a tela continua mostrando o caminho
        pass
    volta = urlparse(request.headers.get('referer') or '/').path or '/'   # só o caminho: nunca redireciona para fora do sistema
    return RedirectResponse(volta, status_code=303)


@app.get('/p/{pid}/cnpjs/baixados')
def cnpjs_baixados(pid: int):
    """Para a tela de comprovantes se atualizar sozinha: quais CNPJs do projeto já têm o comprovante salvo na pasta "Orça.AI"."""
    from orcamento import comprovante_receita as CR
    p, _ = db.carregar(pid)
    na_pasta = CR.baixados()
    return {c: dict(na_pasta[c], importado=c in p.comprovantes_cnpj) for c in usos_cnpj(p) if c in na_pasta}


def _msg_importacao(ok, prob):
    return (f'{len(ok)} comprovante(s) importado(s)' + (f': {", ".join(ok)}' if ok else '') + ('. ' + ' | '.join(prob) if prob else '.'))


@app.post('/p/{pid}/cnpjs/enviar')
async def cnpjs_enviar(pid: int, arquivos: List[UploadFile] = File(...)):
    p, _ = db.carregar(pid)
    ok, prob = servico.importar_comprovantes(p, pid, [(a.filename, await a.read()) for a in arquivos], set(usos_cnpj(p)))
    if ok:
        db.salvar(pid, p, motivo=f'comprovantes oficiais da Receita importados: {", ".join(ok)}')
    return RedirectResponse(f'/p/{pid}/cnpjs?msg={quote(_msg_importacao(ok, prob))}', status_code=303)


@app.post('/p/{pid}/cnpjs/importar')
def cnpjs_importar(pid: int):
    """Procura os comprovantes salvos na pasta "Orça.AI", em Documentos."""
    from orcamento import comprovante_receita as CR
    p, _ = db.carregar(pid)
    arquivos = []
    for a in CR.pdfs_recentes():
        try:
            with open(a, 'rb') as fh:
                arquivos.append((os.path.basename(a), fh.read()))
        except OSError:
            pass
    ok, prob = servico.importar_comprovantes(p, pid, arquivos, set(usos_cnpj(p)), avisar_outros=False)
    if ok:
        db.salvar(pid, p, motivo=f'comprovantes oficiais da Receita importados da pasta Orça.AI (Documentos): {", ".join(ok)}')
    return RedirectResponse(f'/p/{pid}/cnpjs?msg={quote(_msg_importacao(ok, prob) + f" ({len(arquivos)} PDF(s) lidos na pasta Orça.AI, em Documentos)")}', status_code=303)


@app.get('/base-receita', response_class=HTMLResponse)
def base_tela(request: Request):
    from orcamento import cnpj_base
    return tpl.TemplateResponse(request, 'base_receita.html', dict(base=cnpj_base.situacao(),
                                                                   tarefas_base=[t for t in tarefas.listar(limite=60) if t['tipo'] == 'base_receita'][:5]))


@app.post('/base-receita/atualizar')
def base_atualizar(forcar: str = Form(None)):
    tid = tarefas.iniciar('base_receita', 'Base da Receita: atualizar', lambda ctx: servico.base_receita(ctx, bool(forcar)))
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


# ------------------------------------------------------------------ órgãos e as regras de cada um
def _orgao_ou_404(oid):
    o = orgaos.ler(oid)
    if o is None:
        raise HTTPException(404, 'Órgão não encontrado.')
    return o


def _tela_do_orgao(request, oid, msg='', propostas=None, texto_ia=''):
    from orcamento import ia, regras_dinamicas as RD
    o = _orgao_ou_404(oid)
    with db.conectar() as c:
        removido = bool(c.execute('SELECT removido_em FROM orgao WHERE id=?', (oid,)).fetchone()['removido_em'])
    return tpl.TemplateResponse(request, 'orgao.html', dict(
        o=o, oid=oid, msg=msg, regras=orgaos.catalogo(o), TIPOS=RD.TIPOS, campos=RD.campos_do_formulario, resumo=RD.resumo_da_regra, ESFERAS=orgaos.ESFERAS,
        MODELOS=orgaos.MODELOS, DESEMBOLSOS=orgaos.DESEMBOLSOS, padrao=orgaos.padrao(), n_projetos=orgaos.projetos_do_orgao(oid), removido=removido, ia_ok=ia.disponivel(),
        propostas=propostas, propostas_json=json.dumps(propostas, ensure_ascii=False) if propostas else '', texto_ia=texto_ia))


@app.get('/orgaos', response_class=HTMLResponse)
def orgaos_lista(request: Request, msg: str = ''):
    lista = [dict(x, projetos=orgaos.projetos_do_orgao(x['id'])) for x in orgaos.listar()]
    return tpl.TemplateResponse(request, 'orgaos.html', dict(lista=lista, removidos=orgaos.listar(removidos=True), padrao=orgaos.padrao(), ESFERAS=orgaos.ESFERAS, msg=msg))


@app.post('/orgaos')
async def orgao_novo(request: Request):
    f = await request.form()
    nome = re.sub(r'\s+', ' ', f.get('nome') or '').strip()
    if not nome:
        return RedirectResponse(f'/orgaos?msg={quote("Nada foi adicionado: falta o nome do órgão.")}#novo', status_code=303)
    base = orgaos.ler(inteiro(f.get('copiar'), 0)) if f.get('copiar') else None
    o = (base.model_copy(deep=True) if base else orgaos.Orgao(nome=nome))
    o.nome, o.sigla, o.uf = nome, (f.get('sigla') or '').strip(), (f.get('uf') or '').strip().upper()[:2]
    o.esfera = f.get('esfera') if f.get('esfera') in orgaos.ESFERAS else 'estadual'
    if base:
        o.concedente, o.observacoes = '', ''
    oid = orgaos.criar(o)
    return RedirectResponse(f'/orgaos/{oid}?msg={quote("Órgão adicionado. Ajuste as regras que forem diferentes.")}', status_code=303)


@app.get('/orgaos/{oid}', response_class=HTMLResponse)
def orgao_tela(request: Request, oid: int, msg: str = ''):
    return _tela_do_orgao(request, oid, msg)


@app.post('/orgaos/{oid}')
async def orgao_salvar(request: Request, oid: int):
    from orcamento.calculo import GRAVIDADE_PADRAO
    f = await request.form()
    o = _orgao_ou_404(oid)
    o.nome = re.sub(r'\s+', ' ', f.get('nome') or '').strip() or o.nome
    o.sigla, o.uf, o.concedente = (f.get('sigla') or '').strip(), (f.get('uf') or '').strip().upper()[:2], (f.get('concedente') or '').strip()
    o.esfera = f.get('esfera') if f.get('esfera') in orgaos.ESFERAS else o.esfera
    o.observacoes = (f.get('observacoes') or '').strip()
    o.parametros.validade_dias = max(1, inteiro(f.get('validade_dias'), o.parametros.validade_dias))
    o.parametros.valor_do_plano = f.get('valor_do_plano') if f.get('valor_do_plano') in ('menor_ou_media', 'ate_media') else o.parametros.valor_do_plano
    o.parametros.divisor_horas = f.get('divisor_horas') if f.get('divisor_horas') in ('legal', 'praticado') else o.parametros.divisor_horas
    o.modelo_planilha = f.get('modelo_planilha') if f.get('modelo_planilha') in orgaos.MODELOS else o.modelo_planilha
    o.parametros.desembolso = f.get('desembolso') if f.get('desembolso') in orgaos.DESEMBOLSOS else o.parametros.desembolso
    ajustes = {}
    for cod in REGRAS:
        if cod in orgaos.FIXAS:
            continue
        ativa = bool(f.get(f'ativa_{cod}'))
        grav = f.get(f'grav_{cod}') if cod in GRAVIDADE_PADRAO and f.get(f'grav_{cod}') in ('erro', 'atencao', 'info') else None
        if not ativa or grav:   # só guarda o que difere do padrão
            ajustes[cod] = orgaos.AjusteRegra(ativa=ativa, gravidade=grav)
    o.regras = ajustes
    orgaos.salvar(oid, o)
    return RedirectResponse(f'/orgaos/{oid}?msg={quote("Órgão salvo. As regras já valem para os projetos dele.")}', status_code=303)


@app.post('/orgaos/{oid}/regra')
async def orgao_regra(request: Request, oid: int):
    """Cria ou altera uma regra própria do órgão: um tipo que o sistema sabe conferir + o que a pessoa preencheu."""
    from orcamento import regras_dinamicas as RD
    f = await request.form()
    o = _orgao_ou_404(oid)
    tipo, codigo = f.get('tipo'), (f.get('codigo') or '').strip()
    if tipo not in RD.TIPOS:
        return RedirectResponse(f'/orgaos/{oid}?msg={quote("Não gravado: tipo de regra desconhecido.")}#proprias', status_code=303)
    titulo = re.sub(r'\s+', ' ', f.get('titulo') or '').strip()
    try:
        if not titulo:
            raise ValueError('dê um nome à regra')
        par = RD.ler_parametros(tipo, f, cent, inteiro)
    except ValueError as e:
        return RedirectResponse(f'/orgaos/{oid}?msg={quote("Não gravado: " + str(e) + ".")}#{("regra-" + codigo) if codigo else ("novo-" + tipo)}', status_code=303)
    grav = f.get('gravidade') if f.get('gravidade') in ('erro', 'atencao', 'info') else 'atencao'
    atual = next((r for r in o.proprias if r.codigo == codigo), None)
    if atual:
        atual.titulo, atual.gravidade, atual.parametros, atual.ativa = titulo, grav, par, bool(f.get('ativa'))
    else:
        codigo = o.proximo_codigo()
        o.proprias.append(orgaos.RegraPropria(codigo=codigo, tipo=tipo, titulo=titulo, gravidade=grav, parametros=par))
    orgaos.salvar(oid, o)
    return RedirectResponse(f'/orgaos/{oid}?msg={quote(f"Regra {codigo} gravada: já está sendo conferida nos projetos deste órgão.")}#regra-{codigo}', status_code=303)


@app.post('/orgaos/{oid}/regra/{codigo}/excluir')
def orgao_regra_excluir(oid: int, codigo: str):
    o = _orgao_ou_404(oid)
    o.proprias = [r for r in o.proprias if r.codigo != codigo]
    orgaos.salvar(oid, o)
    return RedirectResponse(f'/orgaos/{oid}?msg={quote(f"Regra {codigo} excluída.")}#proprias', status_code=303)


@app.post('/orgaos/{oid}/remover')
def orgao_remover(oid: int):
    if oid == orgaos.padrao():
        return RedirectResponse(f'/orgaos/{oid}?msg={quote("Não removido: o órgão padrão do sistema não pode ser removido.")}', status_code=303)
    _orgao_ou_404(oid)
    orgaos.remover(oid)
    return RedirectResponse(f'/orgaos?msg={quote("Órgão removido da lista. Os projetos dele continuam como estão; dá para restaurar abaixo.")}', status_code=303)


@app.post('/orgaos/{oid}/restaurar')
def orgao_restaurar(oid: int):
    _orgao_ou_404(oid)
    orgaos.remover(oid, False)
    return RedirectResponse(f'/orgaos?msg={quote("Órgão restaurado.")}', status_code=303)


def _propostas_conferidas(o, bruto):
    """As propostas da IA que o sistema consegue usar: tipo conhecido, campos válidos, código do catálogo que existe. O resto é descartado."""
    from orcamento import regras_dinamicas as RD

    class _Form(dict):
        def get(self, k, d=None):
            return super().get(k, d)
    proprias, desligar = [], []
    for x in bruto.get('proprias', []):
        tipo, par = x.get('tipo'), x.get('parametros') if isinstance(x.get('parametros'), dict) else {}
        titulo = re.sub(r'\s+', ' ', str(x.get('titulo') or '')).strip()[:140]
        if tipo not in RD.TIPOS or not titulo:
            continue
        como_form = _Form({f'p_{k}': (', '.join(map(str, v)) if isinstance(v, list) else str(v).replace('.', ',') if isinstance(v, float) else str(v)) for k, v in par.items()})
        try:
            limpo = RD.ler_parametros(tipo, como_form, cent, inteiro)
        except (ValueError, TypeError):
            continue
        r = orgaos.RegraPropria(codigo='P00', tipo=tipo, titulo=titulo, gravidade=x.get('gravidade') if x.get('gravidade') in ('erro', 'atencao', 'info') else 'atencao', parametros=limpo)
        proprias.append(dict(tipo=tipo, titulo=titulo, gravidade=r.gravidade, parametros=limpo, resumo=RD.resumo_da_regra(r), trecho=str(x.get('trecho') or '').strip()[:300]))
    for x in bruto.get('desligar', []):
        cod = str(x.get('codigo') or '').strip().upper()
        if cod in REGRAS and cod not in orgaos.FIXAS and o.ajuste(cod).ativa:
            desligar.append(dict(codigo=cod, descricao=REGRAS[cod][0], trecho=str(x.get('trecho') or '').strip()[:300]))
    return dict(proprias=proprias, desligar=desligar)


@app.post('/orgaos/{oid}/ia', response_class=HTMLResponse)
def orgao_ia(request: Request, oid: int, texto: str = Form('')):
    """A IA lê o texto do órgão e PROPÕE regras. Nada é gravado aqui: a tela mostra as propostas, com o trecho de onde saíram, para a pessoa decidir."""
    from orcamento import ia, regras_dinamicas as RD
    o = _orgao_ou_404(oid)
    texto = (texto or '').strip()
    if len(texto) < 40:
        return _tela_do_orgao(request, oid, 'Não lido: cole um trecho maior do edital ou do manual do órgão.', texto_ia=texto)
    tipos = {k: dict(nome=t['nome'], descricao=t['descricao'], campos={c[0]: c[1] + (' — ' + c[3] if c[3] else '') + (' — opções: ' + c[2].split(':', 1)[1] if c[2].startswith('opcao:') else '')
                                                                        for c in t['campos']}) for k, t in RD.TIPOS.items()}
    try:
        bruto = ia.propor_regras(texto, tipos, {k: v[0] for k, v in REGRAS.items()})
    except Exception:
        bruto = None
    if bruto is None:
        return _tela_do_orgao(request, oid, 'Não foi possível consultar a IA agora (sem chave, sem internet ou limite gratuito atingido). Tente mais tarde ou cadastre as regras à mão.', texto_ia=texto)
    return _tela_do_orgao(request, oid, propostas=_propostas_conferidas(o, bruto), texto_ia=texto)


@app.post('/orgaos/{oid}/ia/aplicar')
async def orgao_ia_aplicar(request: Request, oid: int):
    f = await request.form()
    o = _orgao_ou_404(oid)
    try:
        dados = _propostas_conferidas(o, json.loads(f.get('dados') or '{}'))   # confere de novo o que voltou da tela
    except ValueError:
        dados = dict(proprias=[], desligar=[])
    marcadas = {inteiro(x, -1) for x in f.getlist('propria')}
    n = 0
    for i, x in enumerate(dados['proprias']):
        if i in marcadas:
            o.proprias.append(orgaos.RegraPropria(codigo=o.proximo_codigo(), tipo=x['tipo'], titulo=x['titulo'], gravidade=x['gravidade'], parametros=x['parametros'])); n += 1
    desl = [x['codigo'] for x in dados['desligar'] if x['codigo'] in f.getlist('desligar')]
    for cod in desl:
        o.regras[cod] = orgaos.AjusteRegra(ativa=False, gravidade=o.ajuste(cod).gravidade)
    orgaos.salvar(oid, o)
    return RedirectResponse(f'/orgaos/{oid}?msg={quote(f"{n} regra(s) adicionada(s) e {len(desl)} regra(s) do sistema desligada(s), a partir do texto.")}#proprias', status_code=303)


@app.post('/p/{pid}/regras-ia')
def regras_ia_conferir(pid: int):
    """Confere, com a IA, as regras em texto do órgão para o plano como está agora (o resultado fica guardado e vira pontos da verificação)."""
    from orcamento import regras_dinamicas as RD

    def rodar(ctx):
        p, _ = db.carregar(pid)
        o = orgaos.do_projeto(p)
        ctx.progresso(10, f'Conferindo as regras em texto de {o.rotulo()} com a IA')
        ok, falhou = RD.conferir_com_a_ia(p, o, pid)
        if falhou:
            ctx.aviso(f'{falhou} regra(s) ficaram sem resposta da IA (sem chave, sem internet ou limite gratuito atingido). Tente de novo mais tarde.')
        ctx.progresso(100, 'Concluído')
        return dict(conferidas=ok, sem_resposta=falhou, ir_para=f'/p/{pid}#verificacao')
    tid = tarefas.iniciar('regras', 'Conferir as regras do órgão com a IA', rodar, pid)
    return RedirectResponse(f'/tarefa/{tid}', status_code=303)


# ------------------------------------------------------------------ fechar no teto
@app.post('/p/{pid}/otimizar', response_class=HTMLResponse)
def otimizar_previa(request: Request, pid: int, ajustar_horas: str = Form(None)):
    p, v = db.carregar(pid)
    res = otimizar(p, ajustar_horas=bool(ajustar_horas))
    return tpl.TemplateResponse(request, 'otimizar.html', dict(contexto(p, pid, v), resultado=res, ajustar=bool(ajustar_horas)))


@app.post('/p/{pid}/otimizar/aplicar')
def otimizar_aplicar(pid: int, ajustar_horas: str = Form(None)):
    p, _ = db.carregar(pid)
    res = otimizar(p, ajustar_horas=bool(ajustar_horas))
    if res['status'] == 'OK':
        db.salvar(pid, res['projeto'], autor='sistema (otimizador)', motivo='plano fechado no teto', mudancas=res['mudancas'])
    return RedirectResponse(f'/p/{pid}', status_code=303)


# ------------------------------------------------------------------ exportar e histórico
def _nome_de_arquivo(texto):
    return re.sub(r'\s+', ' ', re.sub(r'[\\/:*?"<>|\r\n\t]+', ' ', texto or '')).strip(' .')[:80] or 'projeto'


@app.get('/p/{pid}/planilhas')
def baixar_planilhas(pid: int):
    """Plano de Aplicação + Comparativo de Preço, na formatação da planilha de pré-cálculos."""
    from orcamento import pacote
    p, v = abrir(pid)
    nome = f'{_nome_de_arquivo(p.nome)} - Plano de Aplicação e Comparativo de Preço.xlsx'
    caminho = os.path.join(tempfile.gettempdir(), f'orca_planilhas_{pid}_{v}.xlsx')
    pacote.planilhas(p, caminho)
    with db.conectar() as c:
        db.evento(c, pid, 'EXPORTADO', arquivo=nome, versao=v)
    return FileResponse(caminho, filename=nome)


@app.get('/p/{pid}/planilhas-pdf')
def baixar_planilhas_pdf(pid: int):
    """As planilhas do pacote em PDF: as mesmas abas e a mesma formatação da planilha, prontas para imprimir ou anexar."""
    from orcamento import pacote
    p, v = abrir(pid)
    if p is None:
        raise HTTPException(404)
    nome = f'{_nome_de_arquivo(p.nome)} - Plano de Aplicação e Comparativo de Preço.pdf'
    caminho = os.path.join(tempfile.gettempdir(), f'orca_planilhas_{pid}_{v}.pdf')
    try:
        dados = pacote.planilhas_pdf(p)
    except Exception as e:
        return voltar_ao_projeto(pid, f'Não foi possível gerar o PDF agora ({type(e).__name__}): o navegador do sistema não abriu. A planilha (.xlsx) continua disponível.')
    with open(caminho, 'wb') as fh:
        fh.write(dados)
    with db.conectar() as c:
        db.evento(c, pid, 'EXPORTADO', arquivo=nome, versao=v)
    return FileResponse(caminho, filename=nome, media_type='application/pdf')


@app.get('/p/{pid}/pacote')
def baixar_pacote(pid: int):
    """Tudo pronto para a Secretaria num .zip: as planilhas e o PDF de cada pesquisa, por rubrica, já com o comprovante de CNPJ da empresa."""
    from orcamento import pacote
    p, v = abrir(pid)
    nome = f'{_nome_de_arquivo(p.nome)} - para a Secretaria ({dt.date.today():%d-%m-%Y}).zip'
    caminho = os.path.join(tempfile.gettempdir(), f'orca_pacote_{pid}_{v}.zip')
    res = pacote.montar(p, pid, caminho)
    with db.conectar() as c:
        db.evento(c, pid, 'EXPORTADO', arquivo=nome, versao=v, pdfs=res['arquivos'], sem_pdf=len(res['sem_pdf']), sem_cnpj=len(res['sem_cnpj']))
    return FileResponse(caminho, filename=nome, media_type='application/zip')


@app.get('/p/{pid}/exportar')
def exportar_xlsx(pid: int):
    p, v = db.carregar(pid)
    cache, status = situacao_dos_cnpjs(p)
    alertas = verificar(p, status)
    nome = f'Orcamento_projeto{pid}_v{v}_{dt.date.today():%Y%m%d}.xlsx'
    caminho = os.path.join(tempfile.gettempdir(), nome)
    exportar(p, alertas, cache, caminho)
    with db.conectar() as c:
        db.evento(c, pid, 'EXPORTADO', arquivo=nome, versao=v)
    return FileResponse(caminho, filename=nome)


@app.get('/p/{pid}/historico', response_class=HTMLResponse)
def historico(request: Request, pid: int):
    p, v = db.carregar(pid)
    versoes, eventos = db.historico(pid)
    return tpl.TemplateResponse(request, 'historico.html', dict(contexto(p, pid, v), versoes=versoes, eventos=eventos))


@app.post('/p/{pid}/restaurar/{numero}')
def restaurar(pid: int, numero: int):
    antigo, _ = db.carregar(pid, numero)
    db.salvar(pid, antigo, motivo=f'restaurada a versão {numero} (as versões posteriores continuam no histórico)')
    return voltar_ao_projeto(pid, f'O projeto voltou a ficar como na versão {numero}. A versão anterior continua no histórico.')


app.add_exception_handler(Exception, erro_inesperado)
