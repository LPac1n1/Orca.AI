"""Cálculos determinísticos e verificação das regras da SEJC. Nada aqui usa IA; tudo em centavos."""
import datetime as dt
import re
from dataclasses import dataclass, asdict

from .modelo import Projeto, RubricaRH, RubricaMaterial, Fonte, descricao_completa
from .regras import (REGRAS, CNPJ_PLATAFORMAS, media, valor_hora, divisor_horas, horas_maximas, cnpj_dv_ok, cnpj_formatar,
                     vencimento, brl, norm)
from .comparador import qty, norm as cnorm


# ------------------------------------------------------------------ valores derivados
def valores_pesquisa(r: RubricaRH):
    return [p.valor if p.valor is not None else p.faixa_min for p in r.pesquisas]


def media_rh(r: RubricaRH):
    v = valores_pesquisa(r)
    return media(v) if len(v) == 3 and None not in v else None


def mensal_maximo_rh(r: RubricaRH, cfg):
    """Maior valor mensal permitido: valor-hora da média × horas do mês."""
    m = media_rh(r)
    if m is None:
        return None, None, None
    div, enq = divisor_horas(r.cargo, cfg.divisor_horas)
    vh = valor_hora(m, div)
    return vh * r.horas_mes, vh, div


def horas_pela_faixa(r: RubricaRH, cfg):
    """Horas inteiras do mês (R17) que deixam o valor mensal o MAIS PRÓXIMO da faixa pretendida, até o máximo de horas do cargo
    (regras.horas_maximas: o limite do projeto, padrão 90 h, e nunca acima da jornada legal). Devolve (horas, valor mensal) ou None (cargo
    sem faixa ou sem as 3 pesquisas). Média abaixo da faixa: o máximo de horas (o mais perto possível)."""
    m = media_rh(r)
    if not r.faixa_pretendida or m is None:
        return None
    div, _ = divisor_horas(r.cargo, cfg.divisor_horas)
    vh = valor_hora(m, div)
    if vh <= 0:
        return None
    hmax = horas_maximas(r.cargo, cfg)
    baixo = max(1, min(hmax, r.faixa_pretendida // vh))
    h = min((baixo, min(hmax, baixo + 1)), key=lambda x: (abs(vh * x - r.faixa_pretendida), x))
    return h, vh * h


def nivelar_pela_faixa(r: RubricaRH, cfg):
    """Põe no cargo as horas e o valor mensal que chegam na faixa pretendida. False se o cargo não tem faixa (ou faltam pesquisas)."""
    x = horas_pela_faixa(r, cfg)
    if x:
        r.horas_mes, r.valor_mensal_plano = x
    return bool(x)


def media_subitem(s):
    return media(s.precos) if len(s.precos) == 3 and None not in s.precos else None


def total_rubrica(rub):
    if isinstance(rub, RubricaRH):   # valor mensal de um profissional × meses × quantidade de profissionais
        return (rub.valor_mensal_plano or 0) * rub.meses * (rub.quantidade or 1)
    return sum((s.valor_plano or 0) * s.qtd for s in rub.subitens) * rub.meses


def duracao_do_projeto(p):
    """Quantos meses o projeto dura: até o último mês de qualquer rubrica."""
    return max([(r.mes_inicio or 1) + r.meses - 1 for r in p.rubricas] or [0])


def periodo(p, rub):
    """(primeiro mês, último mês) da rubrica dentro do projeto, para os cronogramas. Sem mês de início escolhido, a rubrica mais curta que o
    projeto fica no MEIO dele — como na planilha de pré-cálculos: 10 meses num projeto de 12 vão do 2º ao 11º mês."""
    ini = rub.mes_inicio or (duracao_do_projeto(p) - rub.meses) // 2 + 1
    return ini, ini + rub.meses - 1


def periodo_texto(p, rub):
    a, b = periodo(p, rub)
    return f'{a}º mês' if a == b else f'{a}º ao {b}º mês'


def unitario_rubrica(rub):
    if isinstance(rub, RubricaRH):
        return (rub.valor_mensal_plano or 0) * (rub.quantidade or 1)
    return sum((s.valor_plano or 0) * s.qtd for s in rub.subitens)


def total_projeto(p: Projeto):
    return sum(total_rubrica(r) for r in p.rubricas)


def totais_fontes(rub: RubricaMaterial):
    """Total de cada orçamento comparativo (mesmas quantidades, R10)."""
    return [sum((s.precos[i] or 0) * s.qtd for s in rub.subitens) for i in range(3)]


# ------------------------------------------------------------------ verificação
@dataclass
class Alerta:
    regra: str
    gravidade: str      # 'erro' bloqueia; 'atencao' exige revisão; 'info'
    item: str
    mensagem: str

    def dict(self):
        d = asdict(self); d['descricao_regra'], d['origem'] = REGRAS.get(self.regra, ('', '')); return d


# a gravidade mais forte que cada regra do catálogo gera na verificação (as que não estão aqui valem na pesquisa e no cálculo, sem gerar ponto)
GRAVIDADE_PADRAO = {'D09': 'atencao', 'R01': 'erro', 'R02': 'erro', 'R03': 'atencao', 'R04': 'atencao', 'R05': 'erro', 'R06': 'erro', 'R07': 'erro', 'R08': 'erro',
                    'R09': 'erro', 'R10': 'erro', 'R11': 'erro', 'R16': 'erro', 'S01': 'atencao', 'S02': 'info', 'S03': 'info', 'S04': 'atencao', 'S05': 'erro', 'S10': 'atencao', 'S11': 'erro', 'S12': 'erro',
                    'S06': 'atencao', 'S07': 'erro', 'S08': 'erro', 'S09': 'atencao'}


def verificar(p: Projeto, cnpj_status: dict | None = None, hoje: dt.date | None = None):
    """cnpj_status: {cnpj_formatado: 'ATIVA' | 'BAIXADA' | ... | None (não consultado)}."""
    hoje = hoje or dt.date.today(); cnpj_status = cnpj_status or {}; A = []
    total = total_projeto(p)
    if total > p.teto:
        A.append(Alerta('R05', 'erro', 'Plano', f'total {brl(total)} ultrapassa o teto {brl(p.teto)} em {brl(total - p.teto)}'))
    elif total < p.teto:
        A.append(Alerta('R05', 'atencao', 'Plano', f'total {brl(total)} abaixo do teto {brl(p.teto)}: saldo {brl(p.teto - total)}'))

    def checa_fonte(f, rot):
        if not f.nome:
            A.append(Alerta('R08', 'erro', rot, 'fonte sem nome da empresa/loja'))
        c = cnpj_formatar(f.cnpj)
        if not f.cnpj:
            A.append(Alerta('R08', 'erro', rot, f'{f.nome}: CNPJ não informado'))
        elif not cnpj_dv_ok(c):
            A.append(Alerta('R07', 'erro', rot, f'{f.nome}: CNPJ {c} com dígito verificador inválido'))
        elif c in CNPJ_PLATAFORMAS:
            A.append(Alerta('R08', 'erro', rot, f'{f.nome}: {c} é o CNPJ da plataforma {CNPJ_PLATAFORMAS[c]}, não do ofertante'))
        else:
            st = cnpj_status.get(c)
            if st is None:
                A.append(Alerta('R07', 'atencao', rot, f'{f.nome}: CNPJ {c} ainda não consultado'))
            elif st != 'ATIVA':
                A.append(Alerta('R07', 'erro', rot, f'{f.nome}: CNPJ {c} com situação {st}: substituir a pesquisa'))
        if f.data_pesquisa:
            v = vencimento(f.data_pesquisa, p.config.validade_dias)
            if v < hoje:
                A.append(Alerta('R06', 'erro', rot, f'{f.nome}: pesquisa de {f.data_pesquisa} venceu em {v:%d/%m/%Y}'))
            elif (v - hoje).days <= 30:
                A.append(Alerta('R06', 'atencao', rot, f'{f.nome}: pesquisa vence em {v:%d/%m/%Y} ({(v - hoje).days} dias)'))
        else:
            A.append(Alerta('R06', 'atencao', rot, f'{f.nome}: sem data da pesquisa'))

    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            rot = f'Item {r.item} – {r.cargo}'
            if len(r.pesquisas) != 3:
                A.append(Alerta('R01', 'erro', rot, f'{len(r.pesquisas)} pesquisa(s); são necessárias 3')); continue
            for q in r.pesquisas:
                checa_fonte(q, rot)
                if q.faixa_min is not None and q.valor is not None and q.valor != q.faixa_min:
                    A.append(Alerta('R11', 'erro', rot, f'{q.nome}: faixa {brl(q.faixa_min)}–{brl(q.faixa_max)}, mas usado {brl(q.valor)} (deve ser o menor)'))
            chaves = [c for c in (cnpj_formatar(q.cnpj) or norm(q.nome) for q in r.pesquisas) if c]   # pesquisa em branco não conta como empresa repetida
            if len(set(chaves)) < len(chaves):
                A.append(Alerta('R09', 'erro', rot, 'a mesma empresa aparece em mais de uma pesquisa'))
            maxm, vh, div = mensal_maximo_rh(r, p.config)
            if maxm is not None and r.valor_mensal_plano is not None and r.valor_mensal_plano > maxm:
                A.append(Alerta('R02', 'erro', rot, f'mensal {brl(r.valor_mensal_plano)} > máximo {brl(maxm)} (média {brl(media_rh(r))} ÷ {div} = {brl(vh)}/h × {r.horas_mes} h)'))
            if r.valor_mensal_plano is None:
                A.append(Alerta('R04', 'atencao', rot, 'valor mensal do plano ainda não definido'))
            hmax = horas_maximas(r.cargo, p.config)
            if r.horas_mes and r.horas_mes > hmax:
                A.append(Alerta('S12', 'erro', rot, f'{r.horas_mes} horas por mês: o máximo para este cargo é {hmax} h ('
                                + (f'limite de horas do projeto' if hmax == p.config.horas_max_mes else f'jornada legal do cargo no mês') + '). Reduza as horas'))
            if r.faixa_pretendida and maxm is not None:
                cheio = vh * hmax
                if cheio + vh // 2 < r.faixa_pretendida:
                    A.append(Alerta('S09', 'atencao', rot, f'a média das 3 vagas ({brl(media_rh(r))}) não chega na faixa pretendida ({brl(r.faixa_pretendida)}): com o máximo '
                                    f'de horas ({hmax} h) o valor é {brl(cheio)}, faltam {brl(r.faixa_pretendida - cheio)}. Use vagas de salário maior (ou de outro título), '
                                    f'ou reduza a faixa'))
                elif r.valor_mensal_plano is not None and abs(r.valor_mensal_plano - r.faixa_pretendida) > vh:
                    A.append(Alerta('S09', 'info', rot, f'o valor no plano ({brl(r.valor_mensal_plano)}, {r.horas_mes} h) está a {brl(abs(r.valor_mensal_plano - r.faixa_pretendida))} '
                                    f'da faixa pretendida ({brl(r.faixa_pretendida)}): as horas foram mudadas à mão ou pelo "Fechar no teto"'))
            for k, q in enumerate(r.pesquisas):
                if q.evidencia and q.evidencia.arquivo and q.evidencia.origem != 'pdf' and pagina_errada(q.evidencia.arquivo):
                    A.append(Alerta('S07', 'erro', rot, f'pesquisa {k + 1} ({q.nome or "empresa não informada"}): o PDF guardado não é a página da vaga — '
                                    f'{pagina_errada(q.evidencia.arquivo)}. Use "Buscar outra vaga para esta pesquisa"'))
                if q.evidencia and q.evidencia.arquivo and empresa_oculta(q.evidencia.arquivo):
                    A.append(Alerta('S05', 'erro', rot, f'pesquisa {k + 1} ({q.nome or "empresa não informada"}): a página guardada da vaga não mostra as '
                                    f'informações da empresa (a Catho só as mostra para quem está logado)'))
                if q.titulo_vaga and not titulo_do_cargo(q.titulo_vaga, r.cargo):
                    A.append(Alerta('S04', 'atencao', rot, f'pesquisa {k + 1} ({q.nome or "empresa não informada"}): vaga com o título "{q.titulo_vaga}", '
                                    f'similar ao cargo (não havia 3 vagas com o título exato)'))
            mist = titulos_das_pesquisas(r)
            if mist:
                A.append(Alerta('S11', 'erro', rot, 'as pesquisas são de vagas com títulos diferentes (' + ' e '.join(f'"{t}"' for t in mist) + '): vagas de títulos '
                                'diferentes não vão juntas para o orçamento. Na tela do cargo, em "Títulos com vagas", escolha um título só'))
        else:
            rot = f'Item {r.item} – {r.descricao}'
            usa_fontes_da_rubrica = any(len(s.fontes) != 3 and s.descricao not in r.fontes_por_subitem for s in r.subitens) or not r.subitens
            if usa_fontes_da_rubrica:
                if len(r.fontes) != 3:
                    A.append(Alerta('R01', 'erro', rot, f'{len(r.fontes)} fonte(s); são necessárias 3'))
                for f in r.fontes:
                    checa_fonte(f, rot)
            for sid, fs in r.fontes_por_subitem.items():
                for f in fs:
                    checa_fonte(Fonte(**{k: v for k, v in f.items() if k in Fonte.model_fields}) if isinstance(f, dict) else f, f'{rot} / {sid}')
            if r.teto_mensal is not None and unitario_rubrica(r) > r.teto_mensal:
                A.append(Alerta('D09', 'atencao', rot, f'mensal {brl(unitario_rubrica(r))} passa do teto da rubrica {brl(r.teto_mensal)}'))
            repetidos = repetidos_da_rubrica(r)
            for n_sub, s in enumerate(r.subitens):
                rs = f'{rot} / {s.descricao}'
                if n_sub in repetidos:
                    A.append(Alerta('S08', 'erro', rs, f'item {n_sub + 1} da rubrica: é o mesmo produto do item {repetidos[n_sub] + 1} '
                                    f'({r.subitens[repetidos[n_sub]].descricao}). Use "Pesquisar de novo só este item": o sistema não repete mais um item da rubrica'))
                if len(s.fontes) == 3:  # orçamento POR ITEM: as 3 lojas do próprio subitem
                    for f in s.fontes:
                        checa_fonte(f, rs)
                    chaves = [cnpj_formatar(f.cnpj)[:10] or norm(f.nome) for f in s.fontes]  # raiz do CNPJ: filiais da mesma empresa contam como uma só
                    chaves = [c for c in chaves if c]   # pesquisa ainda em branco não é "a mesma empresa" de outra em branco
                    if len(set(chaves)) < len(chaves):
                        A.append(Alerta('R09', 'erro', rs, 'a mesma empresa aparece em mais de uma das 3 pesquisas do item'))
                if s.nivel:
                    A.append(Alerta('S02', 'info', rs, f'troca por item {"parecido" if s.nivel == 1 else "relacionado"}'
                                    + (f' (pedido: {s.descricao_original})' if s.descricao_original else '') + (f': {s.justificativa}' if s.justificativa else '')))
                if s.confirmacao == 'descrição':
                    A.append(Alerta('S03', 'info', rs, 'mesmo produto confirmado pela descrição (ao menos uma loja não publica o código de barras)'))
                elif (s.confirmacao or '').startswith('descrição'):   # opção que a OSC escolheu: mesma marca e descrição, códigos de barras diferentes
                    A.append(Alerta('S03', 'atencao', rs, 'as 3 pesquisas são da mesma marca e têm a mesma descrição, mas os códigos de barras não são iguais '
                                    '(podem ser linhas diferentes do fabricante): confira se é o produto que você quer'))
                if not s.nivel and any(s.produtos or []):   # pediu a caixa e a pesquisa achou a unidade (teste real de 05/10/2026: caneta avulsa por "caixa de canetas")
                    from .produtos.identidade import embalagem_nao_atendida
                    emb = embalagem_nao_atendida(s.descricao_original or s.descricao, s.produtos)
                    if emb:
                        exemplo = next((x for x in s.produtos if x), '')
                        A.append(Alerta('S10', 'atencao', rs, f'o pedido é de {emb}, mas a pesquisa achou a unidade avulsa ("{exemplo[:70]}"): não havia a {emb} do mesmo '
                                        f'produto em 3 lojas. Diga quantas unidades a {emb} tem (ex.: "{emb.capitalize()} com 50 unidades") e pesquise o item de novo, '
                                        f'ou troque a descrição e a quantidade para a unidade'))
                if 'marcas diferentes' in (s.confirmacao or ''):
                    A.append(Alerta('R10', 'erro', rs, 'as 3 pesquisas são de produtos de marcas diferentes: o produto tem de ser exatamente o mesmo nas 3 '
                                    'lojas (marca, cor, tipo e embalagem). Use "Pesquisar de novo só este item"'))
                par = par_em_conflito(s)
                if par:
                    A.append(Alerta('R10', 'erro', rs, f'as pesquisas não são do mesmo produto: "{par[0]}" × "{par[1]}" (marca, cor, variante ou tipo de embalagem '
                                    'diferente). Use "Pesquisar de novo só este item"'))
                if None in s.precos or len(s.precos) != 3:
                    espera = (s.justificativa or '').startswith('aguardando a sua decisão')
                    nada = (s.justificativa or '').startswith('não achado igual em 3 lojas')
                    if (s.justificativa or '').startswith('duas pesquisas feitas pelo sistema') and len([x for x in s.precos if x]) == 2:
                        A.append(Alerta('R10', 'erro', rs, 'falta a 3ª pesquisa: o sistema gravou 2 lojas com o produto pedido; preencha a 3ª à mão, com o MESMO produto em '
                                        'outra loja (empresa, CNPJ, preço e o PDF), em "Pesquisa 3 → Detalhes e comprovante"')); continue
                    A.append(Alerta('R10', 'erro', rs, 'o item pedido não foi achado igual em 3 lojas e o sistema não substituiu nada: abra o item e escolha uma das '
                                    'opções de substituição, mude o pedido e pesquise de novo, ou preencha as 3 pesquisas à mão' if espera else
                                    'o item pedido não foi achado igual em 3 lojas e o sistema não substituiu nada: abra o item, mude o pedido (a descrição, a '
                                    'marca ou a especificação) e pesquise de novo, ou preencha as 3 pesquisas à mão' if nada else
                                    'faltam preços: o subitem precisa existir nas 3 fontes')); continue
                m = media_subitem(s)
                if s.valor_plano is None:
                    A.append(Alerta('R04', 'atencao', rs, 'valor do plano ainda não definido'))
                    continue
                if s.valor_plano > m:
                    A.append(Alerta('R02', 'erro', rs, f'plano {brl(s.valor_plano)} > média {brl(m)} (diferença {brl(s.valor_plano - m)})'))
                if eh_sistema(r) and s.valor_plano != min(s.precos):
                    A.append(Alerta('S06', 'atencao', rs, f'o valor no plano ({brl(s.valor_plano)}) deve ser o menor das 3 cotações ({brl(min(s.precos))}): '
                                    'salve a tela do sistema ou use "Fechar no teto"'))
                if s.valor_plano < min(s.precos):
                    A.append(Alerta('R03', 'atencao', rs, f'plano {brl(s.valor_plano)} < menor orçamento {brl(min(s.precos))}: exige ofício'))
                if p.config.valores_defensaveis and s.valor_plano not in (min(s.precos), m) and s.valor_plano <= m and s.valor_plano >= min(s.precos):
                    A.append(Alerta('S01', 'atencao', rs, f'plano {brl(s.valor_plano)} não é o menor dos 3 preços ({brl(min(s.precos))}) nem a média ({brl(m)}): '
                                    'use "Fechar no teto" ou escolha um dos dois'))
                # R10/R16: produtos do carrinho com medidas diferentes da descrição ou entre si
                qd = qty(cnorm(descricao_completa(s)))
                for i, nome in enumerate(s.produtos):
                    if not nome:
                        continue
                    qn = qty(cnorm(nome))
                    for dim in set(qd) & set(qn):
                        if not (qd[dim] & qn[dim]):
                            A.append(Alerta('R16', 'erro', rs, f'fonte {i + 1}: "{nome}" tem medida {sorted(qn[dim])}, a descrição pede {sorted(qd[dim])}'))
    from . import orgaos   # o órgão do projeto: regras desligadas, gravidade ajustada e as regras próprias dele
    A = orgaos.aplicar(p, A, Alerta)
    revisados = {chave_sem_valores(k) for k in (p.revisados or {})}
    for a in A:   # ponto "para revisar" que a OSC já conferiu: continua revisado se só os valores do texto mudarem (ex.: depois do "Fechar no teto")
        if a.gravidade == 'atencao' and chave_alerta(a) in revisados:
            a.gravidade = 'revisado'
    return A


_VALORES = re.compile(r'R\$\s?\d[\d.]*(?:,\d+)?|\d[\d.,/-]*')


def chave_sem_valores(chave):
    """regra|onde|mensagem, com os números da mensagem trocados por # (valores, CNPJs, datas). Vale também para chaves antigas, com os números."""
    regra, onde, msg = (chave.split('|', 2) + ['', ''])[:3]
    return f'{regra}|{onde}|{_VALORES.sub("#", msg)}'


def chave_alerta(a):
    return chave_sem_valores(f'{a.regra}|{a.item}|{a.mensagem}')


def eh_sistema(r):
    from .servico import tipo_da_rubrica
    return tipo_da_rubrica(r) == 'sistema'


def empresa_oculta(rel):
    """A página da vaga guardada esconde as informações da empresa? (arquivo que não existe: não dá para dizer, então não)"""
    try:
        from . import db
        from .vagas import empresa_oculta as oculta
        return oculta(caminho=db.caminho_absoluto(rel))
    except Exception:
        return False


def repetidos_da_rubrica(r):
    try:
        from .servico import itens_repetidos
        return itens_repetidos(r)
    except Exception:
        return {}


def par_em_conflito(s):
    try:
        from .servico import produtos_em_conflito
        return produtos_em_conflito(s)
    except Exception:
        return None


def pagina_errada(rel):
    """O PDF guardado da vaga não é a página do anúncio? Devolve o motivo ou None (arquivo que não existe: None)."""
    try:
        from . import db
        from .vagas import pdf_nao_e_a_vaga
        return pdf_nao_e_a_vaga(db.caminho_absoluto(rel))
    except Exception:
        return None


def titulo_do_cargo(titulo_vaga, cargo):
    from .vagas import titulo_exato
    return titulo_exato(titulo_vaga, cargo)


def titulos_das_pesquisas(r):
    from .servico import titulos_misturados
    return titulos_misturados(r)


def chave_titulo(t):
    from .vagas import chave_cargo
    return chave_cargo(t or '')


def resumo(p: Projeto, alertas):
    return dict(total=total_projeto(p), teto=p.teto, saldo=p.teto - total_projeto(p),
                erros=sum(a.gravidade == 'erro' for a in alertas), atencao=sum(a.gravidade == 'atencao' for a in alertas),
                revisados=sum(a.gravidade == 'revisado' for a in alertas))
