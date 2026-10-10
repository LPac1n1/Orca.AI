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


SEM_ORTOOLS = 'OTIMIZADOR_PROPRIO'   # status de quando o OR-Tools não pôde ser carregado e a conta foi feita pelo otimizador próprio


def _otimizar_proprio(itens, teto=None, extras=(), folga=0.05, defensaveis=True):
    """O mesmo problema, com as mesmas regras e os mesmos pesos, sem o OR-Tools (Python puro) — para quando o Windows bloqueia as bibliotecas
    dele (aconteceu em 09/10/2026: o sistema inteiro deixou de abrir). Programação dinâmica sobre o total da rubrica:
    - sem teto, cada item fica com a 1ª opção na média (nada a apertar);
    - com teto, sai o menor número possível de itens pedidos (só quando nem os valores mais baixos cabem); entre os que ficam, a combinação
      de opção e valor que cabe no teto, fica dentro da folga e custa menos (valor perto da média, opção mais perto do pedido);
    - os itens extras só entram se ainda sobrar mais que a folga, um de cada vez, o menor número possível.
    Diferença para o OR-Tools: no modo sem "valores defensáveis" o valor é o menor preço ou a média (não um valor qualquer entre os dois)."""
    qmax = max([i['qtd'] for i in itens] + [1])

    def escolhas(it):   # (custo, subtotal, opção, valor) de cada opção × valor permitido
        out = []
        for k, o in enumerate(it.get('opcoes') or []):
            med, dom = dominio(o['precos'], defensaveis)
            for p in (dom if dom is not None else sorted({min(o['precos']), med})):
                out.append(((med - p) * 1000 // max(1, med) + int(o.get('distancia', 0) * 1000) + k * 300, p * it['qtd'], k, p))
        return out
    esc = [escolhas(it) for it in itens]
    fica = [bool(e) for e in esc]
    escolhido = {}   # posição do item -> (custo, subtotal, opção, valor)
    if teto is None:
        for i, e in enumerate(esc):
            if e:
                escolhido[i] = min(e, key=lambda c: c[0])
    else:
        # tirar item pedido é o último recurso: ficam os de menor valor mínimo, enquanto couberem (é o que deixa mais itens na rubrica)
        soma = 0
        for i in sorted((i for i in range(len(itens)) if esc[i]), key=lambda i: min(c[1] for c in esc[i])):
            mn = min(c[1] for c in esc[i])
            if soma + mn <= teto:
                soma += mn
            else:
                fica[i] = False
        ficam = [i for i in range(len(itens)) if fica[i]]
        resto = [0] * (len(ficam) + 1)   # o mínimo que os itens seguintes ainda vão somar
        for n in range(len(ficam) - 1, -1, -1):
            resto[n] = resto[n + 1] + min(c[1] for c in esc[ficam[n]])
        estados = {0: (0, None, None)}   # total -> (custo, estado anterior, escolha)
        for n, i in enumerate(ficam):
            novo, lim = {}, teto - resto[n + 1]
            for tot, reg in estados.items():
                for c in esc[i]:
                    t2 = tot + c[1]
                    if t2 > lim:
                        continue
                    custo = reg[0] + c[0]
                    a = novo.get(t2)
                    if a is None or custo < a[0]:
                        novo[t2] = (custo, reg, c)
            estados = novo
        tol = int(teto * folga)
        total, reg = min(estados.items(), key=lambda e: (e[1][0] + 200 * max(0, teto - e[0] - tol), -e[0]))
        for i in reversed(ficam):
            escolhido[i] = reg[2]; reg = reg[1]
    linhas, tot = [], 0
    for i, it in enumerate(itens):
        if i not in escolhido:
            linhas.append(dict(acao='RETIRADO', desc=it['desc'], qtd=it['qtd'],
                               motivo='sem o mesmo produto em 3 lojas' if not it.get('opcoes') else 'retirado para caber no teto da rubrica'))
            continue
        _, sub, k, v = escolhido[i]
        o = it['opcoes'][k]
        linhas.append(dict(acao='mantido', desc=it['desc'], qtd=it['qtd'], opcao=k, valor=v, media=media(o['precos']), precos=o['precos'], subtotal=sub, motivo=''))
        tot += sub
    if teto is not None and extras:
        tol, livres = int(teto * folga), list(extras)
        while teto - tot > tol and livres:
            melhor = None
            for it in livres:
                qe = min(it.get('qmax') or qmax, qmax)
                for k, o in enumerate(it.get('opcoes') or []):
                    med, dom = dominio(o['precos'], defensaveis)
                    for p in (dom or [med]):
                        if p <= 0 or p > teto - tot:
                            continue
                        cabe = min(qe, (teto - tot) // p)
                        basta = min(cabe, -(-(teto - tot - tol) // p))   # a menor quantidade que já deixa a sobra dentro da folga
                        for y in {cabe, max(1, basta)}:
                            ganho = 200 * (teto - tot - tol - max(0, teto - tot - p * y - tol)) - 50 * y - int(o.get('distancia', 0) * 1000) \
                                - 10_000 - (3 - o.get('ean_em', 0)) * 2_000
                            if ganho > 0 and (melhor is None or ganho > melhor[0]):
                                melhor = (ganho, it, k, o, p, y)
            if melhor is None:
                break
            _, it, k, o, p, y = melhor
            livres.remove(it)
            linhas.append(dict(acao='ACRESCENTADO', desc=it['desc'], qtd=y, opcao=k, valor=p, media=media(o['precos']), precos=o['precos'], subtotal=p * y,
                               motivo='sobra acima da folga do teto'))
            tot += p * y
    return dict(status=SEM_ORTOOLS, total=tot, teto=teto, sobra=(teto - tot) if teto is not None else None, linhas=linhas)


def otimizar(itens, teto=None, extras=(), folga=0.05, defensaveis=True, limite=30):
    """itens: [dict(desc, qtd, opcoes=[dict(precos=[3], distancia, ean_em, ...)])]; extras: idem, com qtd máxima em 'qmax'.
    Devolve dict(status, total, linhas=[...]) — cada linha diz o que aconteceu com o item e por quê."""
    if cp_model is None:   # o Windows bloqueou o OR-Tools: o otimizador próprio faz a mesma conta
        return _otimizar_proprio(itens, teto, extras, folga, defensaveis)
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
