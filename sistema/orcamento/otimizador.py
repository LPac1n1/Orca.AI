"""Fecha o Plano de Aplicação exatamente no teto (OR-Tools CP-SAT), respeitando as regras da SEJC.

Variáveis: horas mensais inteiras de cada cargo (R17) e valor de cada subitem entre o menor orçamento e a média (R02, R03),
ou, no modo "valores defensáveis", apenas o MENOR dos 3 preços ou a MÉDIA dos 3 (S01; decisão da OSC, 03/10/2026: nunca o preço do meio).
Objetivo: mínima alteração em relação ao plano atual (poucas mudanças, pequenas). Cargos com FAIXA pretendida: o valor fica o mais perto possível
da faixa e, quando as faixas não cabem no teto, a diferença é repartida por igual entre eles, em proporção da faixa de cada um (nunca num cargo só).
Quando não há solução, devolve a prova (faixa alcançável × teto) em vez de forçar números.
"""
import copy
from .cp import cp_model

from .modelo import Projeto, RubricaRH
from .calculo import media_rh, media_subitem
from .regras import valor_hora, divisor_horas, horas_maximas, brl, valores_do_plano


def tipo_da_rubrica(r):
    from .servico import tipo_da_rubrica as tipo
    return tipo(r)


SEM_ORTOOLS = 'otimizador próprio (o OR-Tools não pôde ser carregado)'
NIVEIS = 9          # itens mudados de valor: 0 a 7, e "8 ou mais" (o otimizador próprio prefere mudar poucos itens)
RAIO = 2            # horas para cima e para baixo, em volta de cada ponto de partida, que o otimizador próprio experimenta em cada cargo
MAX_COMBINACOES = 600_000


def _todas_as_horas(livres, resto, alcance, itens):
    """Busca COMPLETA, para quando nenhuma combinação perto dos pontos de partida fecha: todas as somas que as horas dos cargos podem dar
    (um conjunto de bits por cargo) cruzadas com todas as somas dos itens (`itens`: bit i ligado = os itens alcançam "base + i"). Se existe um
    jeito de fechar no centavo, ele é achado aqui; se esta busca não acha, NÃO EXISTE — é o que a tela afirma. Entre as soluções, fica a de
    soma de cargos mais perto do plano (alvo de cada cargo), e as horas são reconstruídas de trás para a frente, as mais perto do alvo primeiro.
    Devolve (horas dos cargos livres, deslocamento dos itens) ou None."""
    if resto < 0:
        return None
    mascara = (1 << (resto + 1)) - 1
    camadas = [1]   # bit s ligado = os cargos já vistos conseguem somar s
    for c in livres:
        ant, nova = camadas[-1], 0
        for h in range(1, c['hmax'] + 1):
            if c['a'] * h > resto:
                break
            nova |= ant << (c['a'] * h)
        camadas.append(nova & mascara)
    # os itens "espelhados": bit s ligado = os itens alcançam o que falta (resto - s) quando os cargos somam s
    largura = alcance + 1
    espelho = int(bin(itens)[2:].zfill(largura)[::-1], 2)
    espelho = espelho << (resto - alcance) if resto >= alcance else espelho >> (alcance - resto)
    fecham = camadas[-1] & espelho
    if not fecham:
        return None
    perto = max(0, min(resto, sum(c['a'] * c['alvo'] for c in livres)))
    acima, abaixo = fecham >> perto, fecham & ((1 << perto) - 1)
    cand = ([perto + (acima & -acima).bit_length() - 1] if acima else []) + ([abaixo.bit_length() - 1] if abaixo else [])
    s = min(cand, key=lambda x: abs(x - perto))
    i, hs = resto - s, []
    for j in range(len(livres) - 1, -1, -1):
        c = livres[j]
        h = next(h for h in sorted(range(1, c['hmax'] + 1), key=lambda h: abs(h - c['alvo'])) if s - c['a'] * h >= 0 and (camadas[j] >> (s - c['a'] * h)) & 1)
        hs.append(h); s -= c['a'] * h
    return tuple(reversed(hs)), i


def _otimizar_proprio(p: Projeto, ajustar_horas=True):
    """O mesmo problema de `otimizar`, com as mesmas regras e os mesmos pesos, sem o OR-Tools (Python puro) — para quando o Windows bloqueia as
    bibliotecas dele (09/10/2026: o sistema inteiro deixou de abrir). O total tem de bater com o teto no centavo:
    1. ITENS — todas as somas que os itens podem dar (cada um no menor preço ou na média), separadas por quantos itens mudam de valor:
       conjuntos de bits, um por "número de mudanças". Saber se uma soma existe, e com quantas mudanças, é uma consulta.
    2. CARGOS — as horas partem do ponto mais perto das faixas (ou do plano atual); se o total não couber no intervalo que os itens alcançam,
       todos os cargos com faixa sobem ou descem na MESMA proporção (ninguém fica longe da faixa sozinho). Em volta de cada ponto de partida
       são experimentadas as combinações de RAIO horas a mais e a menos por cargo; fica a de menor custo (os pesos do modelo do OR-Tools).
    3. Os valores dos itens da soma escolhida são reconstruídos mudando o menor número de itens.
    Diferenças para o OR-Tools: a solução é boa, não necessariamente a ótima; no modo sem "valores defensáveis" o item fica no menor preço, na
    média ou no valor atual (não num valor qualquer entre o menor e a média)."""
    cargos, mats, fixo = [], [], 0
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            med = media_rh(r)
            if med is None:
                return dict(status='DADOS_INCOMPLETOS', motivo=f'Item {r.item}: faltam as 3 pesquisas salariais')
            div, enq = divisor_horas(r.cargo, p.config.divisor_horas)
            vh = valor_hora(med, div)
            hmax = max(horas_maximas(r.cargo, p.config), 1)
            c = dict(r=r, vh=vh, a=vh * r.meses * (r.quantidade or 1), hmax=hmax, faixa=None, fixo=None)
            if ajustar_horas and r.faixa_pretendida:
                c['faixa'] = r.faixa_pretendida
                c['alvo'] = min(range(1, hmax + 1), key=lambda h: (abs(vh * h - r.faixa_pretendida), h))   # as horas mais perto da faixa
            elif ajustar_horas:
                c['alvo'] = max(1, min(hmax, round((r.valor_mensal_plano or vh * r.horas_mes) / vh)))
            else:
                c['fixo'] = r.horas_mes; fixo += r.horas_mes * c['a']
            cargos.append(c)
        else:
            sistema = tipo_da_rubrica(r) == 'sistema'
            for s in r.subitens:
                med = media_subitem(s)
                if med is None:
                    return dict(status='DADOS_INCOMPLETOS', motivo=f'Item {r.item} / {s.descricao}: faltam preços nas 3 fontes')
                mn = min(s.precos)
                alvo = min(s.valor_plano, med) if s.valor_plano is not None else med
                vals = [mn] if sistema else valores_do_plano(s.precos) if p.config.valores_defensaveis else sorted({mn, max(mn, alvo), med})
                mats.append(dict(r=r, s=s, vals=vals, alvo=alvo, coef=s.qtd * r.meses, base=min(vals)))

    def custo_do_cargo(c, h):   # (peso na soma, desvio da faixa em centésimos de 1%)
        if c['faixa']:
            return 0, -(-abs(c['vh'] * h - c['faixa']) * 10000 // c['faixa'])
        d = abs(h - c['alvo'])
        return (5000 if d else 0) + 1000 * d, None

    # 1. as somas que os itens alcançam, por número de itens mudados (bit i ligado = soma "base + i" alcançável)
    base_mat = sum(m['base'] * m['coef'] for m in mats)
    alcance = sum((max(m['vals']) - m['base']) * m['coef'] for m in mats)
    niveis = NIVEIS if alcance * (len(mats) + 1) * NIVEIS < 1_600_000_000 else 1   # (muita memória: só "existe ou não existe")
    camadas = [[1] + [0] * (niveis - 1)]
    for m in mats:
        ant, nova = camadas[-1], [0] * niveis
        for v in m['vals']:
            desl, muda = (v - m['base']) * m['coef'], int(v != m['alvo']) if niveis > 1 else 0
            for n in range(niveis):
                if ant[n]:
                    nova[min(niveis - 1, n + muda)] |= ant[n] << desl
        camadas.append(nova)
    fim = camadas[-1]
    alvo_mat = sum((min(m['vals'], key=lambda v: abs(v - m['alvo'])) - m['base']) * m['coef'] for m in mats)   # a soma dos itens como estão
    meses_ref = max(1, min([m['r'].meses for m in mats] or [1]))

    fim_b = [x.to_bytes(alcance // 8 + 1, 'little') for x in fim]   # (em bytes: consultar um bit não copia o número inteiro)

    def mudancas_para(i):   # o menor número de itens mudados que dá a soma base + i (None: essa soma não existe)
        if i < 0 or i > alcance:
            return None
        return next((n for n in range(niveis) if fim_b[n][i >> 3] >> (i & 7) & 1), None)

    # 2. as horas dos cargos
    livres = [c for c in cargos if c['fixo'] is None]
    resto = p.teto - fixo - base_mat          # o que os cargos ajustáveis e os deslocamentos dos itens têm de somar
    partidas, vistos, fora = [], set(), []

    def partida(t, todos):   # os cargos com faixa (ou todos, se `todos`) deslocados na mesma proporção t — em relação à faixa, não às horas
        return tuple(max(1, min(c['hmax'], round(c['faixa'] * (1 + t) / c['vh']))) if c['faixa']
                     else max(1, min(c['hmax'], round(c['alvo'] * (1 + t)))) if todos else c['alvo'] for c in livres)
    for todos in (False, True):
        for k in range(0, 1001):
            for t in ((k / 1000,) if k == 0 else (-k / 1000, k / 1000, -k / 100, k / 100)):
                if t <= -1:
                    continue
                hs = partida(t, todos)
                if hs in vistos:
                    continue
                vistos.add(hs)
                falta = resto - sum(c['a'] * h for c, h in zip(livres, hs))
                if 0 <= falta <= alcance:
                    partidas.append(hs)
                else:
                    fora.append((-falta if falta < 0 else falta - alcance, len(fora), hs))
            if len(partidas) >= 6:
                break
        if partidas:
            break
    if not livres:
        partidas = [()]
    elif not partidas:   # nenhuma proporção cai no intervalo dos itens (poucos itens para ajustar): parte das mais próximas dele
        partidas = [hs for _, _, hs in sorted(fora)[:6]]
    raio = RAIO
    while raio > 1 and len(partidas) * (2 * raio + 1) ** len(livres) > MAX_COMBINACOES:
        raio -= 1
    partidas = partidas[:max(1, MAX_COMBINACOES // max(1, (2 * raio + 1) ** len(livres)))]
    melhor, testadas = None, set()

    def experimentar(hs):
        nonlocal melhor
        if hs in testadas:
            return
        testadas.add(hs)
        i = resto - sum(c['a'] * h for c, h in zip(livres, hs))
        n = mudancas_para(i)
        if n is None:
            return
        soma, desvios = 0, []
        for c, h in zip(livres, hs):
            peso, desvio = custo_do_cargo(c, h)
            soma += peso
            if desvio is not None:
                desvios.append(desvio)
        custo = soma + (200 * max(desvios) + sum(desvios) if desvios else 0) + 100 * n + abs(i - alvo_mat) // meses_ref
        if melhor is None or custo < melhor[0]:
            melhor = (custo, hs, i, n)

    def vizinhos(hs, pos=0, atual=()):
        if pos == len(livres):
            experimentar(atual)
            return
        c = livres[pos]
        for h in range(max(1, hs[pos] - raio), min(c['hmax'], hs[pos] + raio) + 1):
            vizinhos(hs, pos + 1, atual + (h,))
    for hs in partidas:
        vizinhos(hs)
    if melhor is None and livres:   # nada perto dos pontos de partida: a busca completa diz se existe solução
        tudo = 0
        for x in fim:
            tudo |= x
        achado = _todas_as_horas(livres, resto, alcance, tudo)
        if achado:
            melhor = (None, achado[0], achado[1], mudancas_para(achado[1]))
    if melhor is None:
        return dict(status='SEM_SOLUCAO', solver=SEM_ORTOOLS, prova=_prova(p, ajustar_horas) + (
            '' if p.config.valores_defensaveis else ' (Neste computador o otimizador próprio do sistema está em uso, e ele só experimenta, para cada item, o menor '
                                                    'preço, a média e o valor atual.)'))
    _, hs, i, n = melhor
    # 3. os valores dos itens que dão a soma escolhida, mudando o menor número de itens (de trás para a frente, pelas camadas)
    valores = [None] * len(mats)
    for j in range(len(mats) - 1, -1, -1):
        m, ant = mats[j], camadas[j]
        for v in sorted(m['vals'], key=lambda v: (v != m['alvo'], abs(v - m['alvo']))):
            desl, muda = (v - m['base']) * m['coef'], int(v != m['alvo']) if niveis > 1 else 0
            if i - desl < 0:
                continue
            de = [n - muda] + ([n] if muda and n == niveis - 1 else []) if n - muda >= 0 else []
            de = next((x for x in de if (ant[x] >> (i - desl)) & 1), None)
            if de is not None:
                valores[j], i, n = v, i - desl, de
                break
    horas = dict(zip((id(c) for c in livres), hs))
    novo = copy.deepcopy(p); mudancas = []; faixas = []
    itc, itm = iter(cargos), iter(valores)
    for rn in novo.rubricas:
        if isinstance(rn, RubricaRH):
            c = next(itc); vh = c['vh']; hv = c['fixo'] if c['fixo'] is not None else horas[id(c)]
            if hv != rn.horas_mes or vh * hv != rn.valor_mensal_plano:
                mudancas.append(dict(item=rn.item, alvo=rn.cargo, campo='horas/mensal', antes=f'{rn.horas_mes} h / {brl(rn.valor_mensal_plano)}', depois=f'{hv} h / {brl(vh * hv)}'))
            if rn.faixa_pretendida:
                faixas.append(dict(item=rn.item, cargo=rn.cargo, faixa=rn.faixa_pretendida, horas=hv, valor=vh * hv, diferenca=vh * hv - rn.faixa_pretendida,
                                   pct=round(1000 * (vh * hv - rn.faixa_pretendida) / rn.faixa_pretendida) / 10))
            rn.horas_mes = hv; rn.valor_mensal_plano = vh * hv
        else:
            for sn in rn.subitens:
                vv = next(itm)
                if vv != sn.valor_plano:
                    mudancas.append(dict(item=rn.item, alvo=sn.descricao, campo='valor', antes=brl(sn.valor_plano), depois=brl(vv)))
                sn.valor_plano = vv
    return dict(status='OK', projeto=novo, mudancas=mudancas, solver=SEM_ORTOOLS, faixas=faixas, sobra_das_faixas=_sobra_das_faixas(p) if faixas else None)


def otimizar(p: Projeto, ajustar_horas=True, limite_segundos=30):
    if cp_model is None:   # o Windows bloqueou o OR-Tools: o otimizador próprio fecha o plano
        return _otimizar_proprio(p, ajustar_horas)
    m = cp_model.CpModel(); termos = []; custo = []; vars_ = []
    desvios = []   # cargos com faixa pretendida: quanto o valor mensal se afasta da faixa, em centésimos de 1% da faixa
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            med = media_rh(r)
            if med is None:
                return dict(status='DADOS_INCOMPLETOS', motivo=f'Item {r.item}: faltam as 3 pesquisas salariais')
            div, enq = divisor_horas(r.cargo, p.config.divisor_horas)
            vh = valor_hora(med, div)
            hmax = max(horas_maximas(r.cargo, p.config), 1)   # o limite de horas do projeto (padrão 90 h) e nunca acima da jornada legal
            if ajustar_horas and r.faixa_pretendida:
                # Cargo com faixa pretendida: conta o desvio do valor mensal em PROPORÇÃO da faixa (e não em horas). Em horas, o corte ia todo para
                # o cargo em que cada hora vale mais dinheiro no total (caso real de 05/10/2026: Assistente Social de 47 h para 27 h, 43% abaixo
                # da faixa, com os outros cargos intactos).
                h = m.NewIntVar(1, hmax, f'h{r.item}')
                dev = m.NewIntVar(0, max(vh * hmax, r.faixa_pretendida), ''); m.AddAbsEquality(dev, vh * h - r.faixa_pretendida)
                di = m.NewIntVar(0, 1_000_000, ''); m.Add(dev * 10000 <= di * r.faixa_pretendida)
                desvios.append(di)
            elif ajustar_horas:
                h = m.NewIntVar(1, hmax, f'h{r.item}')
                alvo = max(1, min(hmax, round((r.valor_mensal_plano or vh * r.horas_mes) / vh)))
                d = m.NewIntVar(0, hmax, ''); m.AddAbsEquality(d, h - alvo)
                mudou = m.NewBoolVar(''); m.Add(d == 0).OnlyEnforceIf(mudou.Not()); m.Add(d >= 1).OnlyEnforceIf(mudou)
                custo += [mudou * 5000, d * 1000]
            else:
                h = r.horas_mes
            termos.append(h * vh * r.meses * (r.quantidade or 1)); vars_.append(('rh', r, vh, h))   # × quantidade de profissionais
        else:
            sistema = tipo_da_rubrica(r) == 'sistema'
            for s in r.subitens:
                med = media_subitem(s)
                if med is None:
                    return dict(status='DADOS_INCOMPLETOS', motivo=f'Item {r.item} / {s.descricao}: faltam preços nas 3 fontes')
                mn = min(s.precos)
                alvo = min(s.valor_plano, med) if s.valor_plano is not None else med
                if sistema:   # rubrica de sistema: o valor é sempre o menor das 3 cotações (não entra no ajuste)
                    v = m.NewIntVar(mn, mn, '')
                elif p.config.valores_defensaveis:
                    v = m.NewIntVarFromDomain(cp_model.Domain.FromValues(valores_do_plano(s.precos)), '')
                else:
                    v = m.NewIntVar(mn, med, '')
                d = m.NewIntVar(0, med, ''); m.AddAbsEquality(d, v - alvo)
                mudou = m.NewBoolVar(''); m.Add(d == 0).OnlyEnforceIf(mudou.Not()); m.Add(d >= 1).OnlyEnforceIf(mudou)
                custo += [mudou * 100, d * s.qtd]
                termos.append(v * s.qtd * r.meses); vars_.append(('mat', (r, s), None, v))
    if desvios:   # primeiro o MAIOR desvio entre os cargos (ninguém fica muito longe da faixa); depois a soma (ninguém se afasta sem precisar)
        maior = m.NewIntVar(0, 1_000_000, '')
        for di in desvios:
            m.Add(di <= maior)
        custo += [maior * 200] + desvios
    m.Add(sum(termos) == p.teto)
    m.Minimize(sum(custo))
    sv = cp_model.CpSolver(); sv.parameters.max_time_in_seconds = limite_segundos; sv.parameters.num_workers = 8
    st = sv.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return dict(status='SEM_SOLUCAO', prova=_prova(p, ajustar_horas), solver=sv.StatusName(st))
    novo = copy.deepcopy(p); mudancas = []; faixas = []
    it = iter(vars_)
    for rn in novo.rubricas:
        if isinstance(rn, RubricaRH):
            _, r0, vh, h = next(it); hv = h if isinstance(h, int) else sv.Value(h)
            if hv != rn.horas_mes or vh * hv != rn.valor_mensal_plano:
                mudancas.append(dict(item=rn.item, alvo=rn.cargo, campo='horas/mensal', antes=f'{rn.horas_mes} h / {brl(rn.valor_mensal_plano)}', depois=f'{hv} h / {brl(vh * hv)}'))
            if rn.faixa_pretendida:
                faixas.append(dict(item=rn.item, cargo=rn.cargo, faixa=rn.faixa_pretendida, horas=hv, valor=vh * hv, diferenca=vh * hv - rn.faixa_pretendida,
                                   pct=round(1000 * (vh * hv - rn.faixa_pretendida) / rn.faixa_pretendida) / 10))
            rn.horas_mes = hv; rn.valor_mensal_plano = vh * hv
        else:
            for sn in rn.subitens:
                _, (r0, s0), _, v = next(it); vv = sv.Value(v)
                if vv != sn.valor_plano:
                    mudancas.append(dict(item=rn.item, alvo=sn.descricao, campo='valor', antes=brl(sn.valor_plano), depois=brl(vv)))
                sn.valor_plano = vv
    return dict(status='OK', projeto=novo, mudancas=mudancas, solver=sv.StatusName(st), faixas=faixas, sobra_das_faixas=_sobra_das_faixas(p) if faixas else None)


def _sobra_das_faixas(p):
    """Com todos os cargos exatamente na faixa pretendida (os sem faixa, como estão no plano): (total, o que passa do teto com os materiais como
    estão, o que ainda passa com todos os materiais no menor preço). Diz se as faixas CABEM no teto — se não cabem, nenhum ajuste de horas resolve."""
    from .calculo import horas_pela_faixa
    cargos = sum(((horas_pela_faixa(r, p.config) or (0, r.valor_mensal_plano or 0))[1]) * r.meses * (r.quantidade or 1) for r in p.rubricas if isinstance(r, RubricaRH))
    mat = [(r, s) for r in p.rubricas if not isinstance(r, RubricaRH) for s in r.subitens if media_subitem(s) is not None]
    atual = sum((s.valor_plano if s.valor_plano is not None else media_subitem(s)) * s.qtd * r.meses for r, s in mat)
    minimo = sum(min(s.precos) * s.qtd * r.meses for r, s in mat)
    return dict(total=cargos + atual, excesso=cargos + atual - p.teto, excesso_minimo=cargos + minimo - p.teto)


def _prova(p, ajustar_horas):
    """Faixa alcançável dentro das regras, para mostrar por que o teto não fecha."""
    lo = hi = 0
    for r in p.rubricas:
        if isinstance(r, RubricaRH):
            div, enq = divisor_horas(r.cargo, p.config.divisor_horas)
            vh = valor_hora(media_rh(r), div)
            hmax = horas_maximas(r.cargo, p.config)
            lo += vh * (1 if ajustar_horas else r.horas_mes) * r.meses * (r.quantidade or 1)
            hi += vh * (hmax if ajustar_horas else r.horas_mes) * r.meses * (r.quantidade or 1)
        else:
            for s in r.subitens:
                lo += min(s.precos) * s.qtd * r.meses
                hi += (min(s.precos) if tipo_da_rubrica(r) == 'sistema' else media_subitem(s)) * s.qtd * r.meses
    if hi < p.teto:
        return f'Máximo alcançável dentro das regras: {brl(hi)}. Faltam {brl(p.teto - hi)} para o teto {brl(p.teto)}. ' + \
               ('Permita ajustar horas, inclua despesas ou reduza o teto.' if not ajustar_horas else 'Inclua despesas ou reduza o teto.')
    if lo > p.teto:
        return f'Mínimo alcançável dentro das regras: {brl(lo)}, acima do teto {brl(p.teto)} em {brl(lo - p.teto)}.'
    return (f'O teto {brl(p.teto)} está entre o mínimo {brl(lo)} e o máximo {brl(hi)}, mas nenhuma combinação exata foi encontrada '
            'com os valores permitidos. Tente liberar o ajuste de horas ou desligar o modo "valores defensáveis".')
