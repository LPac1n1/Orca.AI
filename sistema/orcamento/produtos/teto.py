"""Teto por rubrica (decisão D9 da OSC): "o preço de todos os itens não deve ultrapassar o teto; se ultrapassar, tirar itens;
se estiver muito longe, adicionar itens".

Para cada rubrica (OR-Tools CP-SAT):
- cada item pedido escolhe UMA das opções válidas (produto idêntico em 3 lojas) e o valor do plano (o menor dos 3 preços ou a
  média — valores defensáveis — ou qualquer valor entre o menor orçamento e a média, se o modo estiver desligado);
- soma da rubrica ≤ teto e o mais perto possível dele;
- tira item pedido só se nem com as opções e valores mais baixos couber;
- acrescenta item extra da rubrica só se a sobra passar da folga (padrão 5 %), com quantidade até a maior já pedida;
- prefere opções mais próximas do pedido e, entre elas, as mais baratas (ordem do motor); valores perto da média.
O fechamento exato em centavos do projeto inteiro continua no otimizador do plano (que também ajusta as horas de RH)."""
from ..cp import cp_model

from ..regras import media, valores_do_plano


def dominio(precos, defensaveis=True):
    med = media(precos)
    if defensaveis:
        return med, valores_do_plano(precos)
    return med, None


def otimizar(itens, teto=None, extras=(), folga=0.05, defensaveis=True, limite=30):
    """itens: [dict(desc, qtd, opcoes=[dict(precos=[3], distancia, ean_em, ...)])]; extras: idem, com qtd máxima em 'qmax'.
    Devolve dict(status, total, linhas=[...]) — cada linha diz o que aconteceu com o item e por quê."""
    m = cp_model.CpModel(); termos, custo, vars_ = [], [], []
    qmax = max([i['qtd'] for i in itens] + [1])
    for grupo, lista in (('pedido', itens), ('extra', extras)):
        for it in lista:
            usa = m.NewBoolVar('')
            escolhas = []
            for k, o in enumerate(it.get('opcoes') or []):
                med, dom = dominio(o['precos'], defensaveis)
                mn = min(o['precos'])
                if grupo == 'pedido':
                    q = it['qtd']
                    if dom is not None:
                        xs = [m.NewBoolVar('') for _ in dom]
                        termos += [p * q * x for p, x in zip(dom, xs)]
                        custo += [((med - p) * 1000 // max(1, med)) * x for p, x in zip(dom, xs)]   # sem aperto do teto, fica na média
                        sel = m.NewBoolVar(''); m.Add(sum(xs) == sel)
                        escolhas.append((k, o, sel, ('dom', dom, xs), None))
                    else:
                        sel = m.NewBoolVar(''); v = m.NewIntVar(0, med, '')
                        m.Add(v >= mn).OnlyEnforceIf(sel); m.Add(v == 0).OnlyEnforceIf(sel.Not())
                        termos.append(v * q)
                        escolhas.append((k, o, sel, ('livre', v), None))
                else:
                    qe = min(it.get('qmax') or qmax, qmax)
                    dom = dom or [med]
                    xs = [m.NewBoolVar('') for _ in dom]; ys = [m.NewIntVar(0, qe, '') for _ in dom]
                    for x, y in zip(xs, ys):
                        m.Add(y <= qe * x); m.Add(y >= x)
                    termos += [p * y for p, y in zip(dom, ys)]
                    sel = m.NewBoolVar(''); m.Add(sum(xs) == sel)
                    custo += [y * 50 for y in ys]
                    escolhas.append((k, o, sel, ('dom', dom, xs), ys))
                custo.append(sel * int(o.get('distancia', 0) * 1000))
                if grupo == 'pedido':
                    custo.append(sel * k * 300)   # a ordem do motor (mais próximo do pedido e, empatando, o MENOR PREÇO) desempata
                if grupo == 'extra':
                    custo.append(sel * (10_000 + (3 - o.get('ean_em', 0)) * 2_000))
            m.Add(sum(e[2] for e in escolhas) == usa) if escolhas else m.Add(usa == 0)
            if grupo == 'pedido':
                custo.append((1 - usa) * 100_000_000)  # tirar um item pedido é o último recurso
            vars_.append((grupo, it, usa, escolhas))
    total = sum(termos) if termos else 0
    if teto is not None:
        m.Add(total <= teto)
        tol = int(teto * folga)
        excesso = m.NewIntVar(0, teto, ''); m.Add(excesso >= teto - total - tol)
        custo.append(excesso * 200)
    elif extras:
        for grupo, it, usa, esc in vars_:
            if grupo == 'extra':
                m.Add(usa == 0)  # sem teto, nada a acrescentar
    m.Minimize(sum(custo))
    sv = cp_model.CpSolver(); sv.parameters.max_time_in_seconds = limite; sv.parameters.num_workers = 8
    st = sv.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return dict(status='SEM_SOLUCAO', solver=sv.StatusName(st))
    linhas = []
    for grupo, it, usa, escolhas in vars_:
        if not sv.Value(usa):
            if grupo == 'pedido':
                motivo = 'sem o mesmo produto em 3 lojas' if not it.get('opcoes') else 'retirado para caber no teto da rubrica'
                linhas.append(dict(acao='RETIRADO', desc=it['desc'], qtd=it['qtd'], motivo=motivo))
            continue
        k, o, sel, forma, ys = next(e for e in escolhas if sv.Value(e[2]))
        if forma[0] == 'dom':
            idx = next(i for i, x in enumerate(forma[2]) if sv.Value(x))
            v = forma[1][idx]
            q = it['qtd'] if grupo == 'pedido' else sv.Value(ys[idx])
        else:
            v, q = sv.Value(forma[1]), it['qtd']
        linhas.append(dict(acao='mantido' if grupo == 'pedido' else 'ACRESCENTADO', desc=it['desc'], qtd=q, opcao=k, valor=v, media=media(o['precos']),
                           precos=o['precos'], subtotal=v * q, motivo='' if grupo == 'pedido' else 'sobra acima da folga do teto'))
    tot = sum(l.get('subtotal', 0) for l in linhas)
    return dict(status=sv.StatusName(st), total=tot, teto=teto, sobra=(teto - tot) if teto is not None else None, linhas=linhas)
