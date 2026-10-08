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


def otimizar(p: Projeto, ajustar_horas=True, limite_segundos=30):
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
