"""Motor da cesta: acha o MESMO produto em 3 lojas para cada item (padrão) ou um trio de lojas para a rubrica inteira (opção).

Etapas (com progresso na tela):
 1. busca de cada item em cada loja (descrição e família);            5. estoque e preço no CEP (lojas VTEX);
 2. busca direcionada pelas marcas mais presentes;                     6. grupos de mesmo produto (EAN 🟢 / descrição 🟡);
 3. EAN pela página do produto (Lepok, Kalunga, Carrefour);            7. escolha das 3 lojas de cada item (ou do trio)
 4. "ponte" de EAN: o mesmo código procurado nas outras lojas;            e das opções para o teto da rubrica.
Critério NEUTRO e registrado (decisão da OSC, 27/09/2026): o MENOR PREÇO. Para um item, valem as 3 lojas mais baratas que têm o
MESMO produto (EAN ou descrição conferida pela IA), sempre de empresas diferentes (raiz do CNPJ — R09); entre os produtos que
atendem o item, o mais próximo do pedido e, empatando, o mais barato.
Trocas, em degraus: outra marca do mesmo produto → parecido (outro tamanho/variante) → relacionado (mesma família) →
produto da CATEGORIA da rubrica (categorias.py). Loja que pede CAPTCHA é descartada por 30 dias."""
import asyncio
import itertools
import time
from collections import Counter, defaultdict

from .. import db
from . import categorias as C
from . import identidade as ID
from . import lojas as L

LIMITE_BUSCA, LIMITE_PAGINA, K_EAN, K_PONTE, N_OPCOES = 75, 60, 8, 6, 5
# intervalo mínimo (s) entre acessos à MESMA loja: páginas abertas no navegador disparam o anti-robô se vierem em rajada
INTERVALO = dict(render=4.0, tenda=0.7, gimba=1.0, nuvemshop=2.5, vtex=0.3, gpa=0.3)
MAX_CATEGORIA = 12   # produtos da categoria procurados quando um item não existe igual em 3 lojas


def _sem_espaco(u):
    import re
    return re.sub(r'\s', '%20', (u or '').strip())


def chaves_da_opcao(o):
    """O que identifica o produto de uma opção: as páginas (loja, endereço) e os códigos de barras das ofertas."""
    return {(x['loja'], _sem_espaco(x['url'])) for x in o['ofertas']} | {x['ean'].lstrip('0') for x in o['ofertas'] if x.get('ean')}


class Motor:
    def __init__(self, itens, lojas, cep, ctx=None, modo='por_item', usar_ia=True, projeto_id=None, setor=None, extras=(), marcas_diferentes=False,
                 outros=(), usados=()):
        """itens: [dict(desc, qtd, familia, valor_ref)]; lojas: códigos de LOJAS; setor/extras: para as trocas pela categoria da rubrica.
        outros/usados (pesquisa de PARTE da rubrica): descrições dos itens que não estão sendo pesquisados e os produtos que eles já usam
        ((loja, endereço) e códigos de barras). Um item nunca é trocado por algo que já é outro item da rubrica, nem usa o produto de outro."""
        self.setor, self.extras = setor, list(extras or [])
        self.outros = [d for d in outros if d]
        self.usados = {(k[0], _sem_espaco(k[1])) if isinstance(k, tuple) else str(k).lstrip('0') for k in usados if k}
        self.marcas_diferentes = marcas_diferentes   # aceitar a MESMA ESPECIFICAÇÃO com marcas diferentes quando o mesmo produto não existe em 3 lojas
        self.gpa_loja = {}                        # loja do GPA que atende o CEP
        self.itens = [dict(i, familia=i.get('familia') or ID.familia_padrao(i['desc'])) for i in itens]
        self.descs = [i['desc'] for i in self.itens] + [d for d in self.outros if d not in [i['desc'] for i in self.itens]]
        self.lojas, self.cep, self.ctx, self.modo = lojas, cep, ctx, modo
        self.usar_ia, self.projeto_id = usar_ia, projeto_id
        self.buscas_loja, self.falhas_loja = Counter(), Counter()
        self.ofertas = defaultdict(list)          # (desc, nível) -> ofertas
        self.memo_sim = {}
        self.filial = None                        # filial do Tenda que atende o CEP
        self.bloqueadas = {}                      # loja -> motivo (pediu verificação humana: sai da tarefa)
        self.rejeitadas_ia = defaultdict(list)    # item -> opções que a IA disse NÃO serem o mesmo produto (com o motivo)
        self.indisp_hoje = set()                  # 'loja|url' que o comprovante de hoje achou indisponível (não volta a ser escolhido)
        self._travas, self._prox = {}, {}         # ritmo de acesso por loja
        self.grupos_categoria = {}                # produto da categoria da rubrica -> grupos (último degrau das trocas)
        self.brutos = defaultdict(list)           # item -> todos os anúncios achados nas buscas dele (para a IA montar o trio)
        # o que se digita na busca das lojas: o pedido na forma das lojas (tipo do produto na frente); a IA pode acrescentar outras formas
        self.buscas = {i['desc']: [ID.normalizar_pedido(i['desc'])] for i in self.itens}
        self.entendido = {}                       # item -> como o pedido foi entendido (para a proposta mostrar)

    def _entender(self):
        """Interpretação dos pedidos pela IA (uma pergunta para a rubrica): outros nomes do mesmo produto, outras buscas e se o pedido é de uma
        embalagem com várias unidades. A resposta é CONFERIDA aqui: o tipo tem de ser um trecho do próprio pedido, e nome ou busca com marca
        que o pedido não cita é descartado. As regras de identidade continuam decidindo o que atende o item."""
        from .. import ia
        from . import texto as T
        for it in self.itens:
            self.entendido[it['desc']] = dict(busca=self.buscas[it['desc']][0], embalagem=ID.embalagem_lider(it['desc']))
        if not (self.usar_ia and ia.disponivel()):
            return
        self._prog(1, 'Entendendo os pedidos (IA)')
        try:
            resp = ia.entender_pedidos([it['desc'] for it in self.itens], self.projeto_id)
        except Exception:
            return
        for it in self.itens:
            e, d = resp.get(it['desc']), it['desc']
            if not e:
                continue
            do_pedido = T.marcas_no_texto(d)
            sem_marca = lambda t: not (T.marcas_no_texto(t) - do_pedido)
            outros = [o for o in self.descs if o != d]
            palavras = {ID.raiz(w) for w in ID.sa(ID.normalizar_pedido(d)).split()}
            novo = lambda t: bool({ID.raiz(w) for w in ID.sa(t).split()} - palavras)   # outro NOME traz palavra nova; o pedido sem uma palavra ("caneta azul") é só um pedido mais largo
            nomes = [n for n in e['sinonimos'] if sem_marca(n) and novo(n) and not any(ID.compativel(o, n, 0) for o in outros)]   # nunca o nome de OUTRO item da rubrica
            if ID.definir_sinonimos(d, e['produto'], nomes):
                self.entendido[d]['nomes'] = nomes
            ID.definir_varias_unidades(d, e['varias_unidades'])
            self.entendido[d]['varias_unidades'] = e['varias_unidades']
            for q in e['buscas']:
                q = L.consulta(q)
                if q and sem_marca(q) and ID.sa(q) not in [ID.sa(x) for x in self.buscas[d]] and len(self.buscas[d]) < 3:
                    self.buscas[d].append(q)
            self.entendido[d]['buscas'] = self.buscas[d][1:]

    # ---------------------------------------------------------------- andamento
    def _prog(self, pct, etapa=None):
        if self.ctx:
            self.ctx.progresso(pct, etapa)

    def _fonte(self, loja, estado, det=''):
        if self.ctx:
            self.ctx.fonte(L.LOJAS[loja]['nome'], estado, det)

    # ---------------------------------------------------------------- buscas com cache e limite de tempo
    async def _vez(self, loja):
        """Espera a vez de acessar a loja (intervalo mínimo entre acessos, para não parecer um robô em rajada)."""
        trava = self._travas.setdefault(loja, asyncio.Lock())
        async with trava:
            espera = self._prox.get(loja, 0) - time.monotonic()
            if espera > 0:
                await asyncio.sleep(espera)
            self._prox[loja] = time.monotonic() + INTERVALO.get(L.LOJAS[loja]['plataforma'], 1.0)

    async def _buscar(self, loja, q):
        q = L.consulta(q)
        chave = f'busca|{loja}|{q}' + (f'|filial{self.filial}' if loja == 'tenda' else f'|loja{self.gpa_loja.get(loja)}' if loja in self.gpa_loja else '')
        r = db.cache_ler(chave)
        if r is not None:
            return r
        if loja in self.bloqueadas:
            return []
        await self._vez(loja)
        async with self.sem:
            if loja in self.bloqueadas:
                return []
            self.buscas_loja[loja] += 1
            for tentativa in range(2):
                if tentativa:
                    await self._vez(loja)
                try:
                    plat = L.LOJAS[loja]['plataforma']
                    co = (L.vtex(self.c, loja, q) if plat == 'vtex' else L.tenda(self.c, q, self.filial) if plat == 'tenda' else L.gimba(self.c, q) if plat == 'gimba'
                          else L.nuvemshop(self.c, loja, q) if plat == 'nuvemshop' else L.gpa(self.c, loja, q, self.gpa_loja[loja]) if plat == 'gpa'
                          else L.render(self.br, loja, q))
                    out = await asyncio.wait_for(co, LIMITE_BUSCA)
                    db.cache_gravar(chave, out)
                    self._fonte(loja, 'ok', f'{self.buscas_loja[loja]} buscas')
                    return out
                except L.Bloqueada as e:
                    self._bloquear(loja, str(e))
                    return []
                except Exception as e:
                    self.falhas_loja[loja] += 1
                    self._fonte(loja, 'repetindo' if tentativa == 0 else 'falhou', f'{type(e).__name__ if not isinstance(e, asyncio.TimeoutError) else "sem resposta"}')
            return []

    def _bloquear(self, loja, motivo):
        if loja in self.bloqueadas:
            return
        self.bloqueadas[loja] = motivo
        if '(429)' in motivo:   # limite de acessos NÃO é CAPTCHA: a loja só descansa até amanhã (não é descartada por 30 dias)
            db.loja_bloquear(loja, motivo, dias=1)
            self._fonte(loja, 'falhou', f'fora até amanhã: {motivo}')
            if self.ctx:
                self.ctx.aviso(f'{L.LOJAS[loja]["nome"]}: {motivo}. A loja fica de fora até amanhã e as outras lojas cobrem os itens dela. '
                               f'Dá para reativá-la antes na configuração do projeto.')
            return
        db.loja_bloquear(loja, motivo)
        self._fonte(loja, 'falhou', f'descartada: {motivo}')
        if self.ctx:
            self.ctx.aviso(f'{L.LOJAS[loja]["nome"]}: {motivo}. O sistema não resolve CAPTCHA: a loja foi DESCARTADA por {db.DIAS_BLOQUEIO} dias '
                           f'e as outras lojas cobrem os itens dela. Dá para reativá-la na configuração do projeto.')

    async def _ean_pagina(self, loja, url):
        chave = f'eanurl|{url}'
        r = db.cache_ler(chave)
        if r is not None:
            return r or None
        await self._vez(loja)
        async with self.sem:
            if loja in self.bloqueadas:
                return None
            try:
                e = await asyncio.wait_for(L.ean_da_pagina(self.br, self.c, loja, url), LIMITE_PAGINA)
            except L.Bloqueada as ex:
                self._bloquear(loja, str(ex))
                return None
            except Exception:
                return None
        db.cache_gravar(chave, e or '')
        return e

    async def _ponte_vtex(self, loja, ean):
        chave = f'ean|{loja}|{ean}'
        r = db.cache_ler(chave)
        if r is not None:
            return r
        async with self.sem:
            try:
                out = await asyncio.wait_for(L.vtex(self.c, loja, ean=ean), 30)
            except Exception:
                return []
        db.cache_gravar(chave, out)
        return out

    # ---------------------------------------------------------------- classificação
    def _classificar(self, loja, x, so_item=None):
        if not (x.get('simular') or (x.get('disp') and x.get('preco'))):
            return
        if f"{loja}|{x.get('url')}" in self.indisp_hoje:
            return
        for it in self.itens:
            if so_item and it['desc'] not in so_item:
                continue
            nv = ID.nivel(it['desc'], x['nome'], self.descs, it['familia'])  # o título completo só serve para comparar produtos
            if nv is not None:
                self.ofertas[(it['desc'], nv)].append(dict(x, loja=loja))

    # ---------------------------------------------------------------- execução
    async def rodar(self):
        import httpx
        from playwright.async_api import async_playwright
        self.sem = asyncio.Semaphore(3)
        self._entender()
        async with async_playwright() as pw, httpx.AsyncClient(headers={'User-Agent': L.UA, 'Accept': 'application/json'}, timeout=25, follow_redirects=True) as c:
            self.c = c; self.br = await pw.chromium.launch()
            self.indisp_hoje = {k.split('|', 1)[1] for k in db.cache_prefixo('indisp|')}
            for lj in [l for l in self.lojas if L.LOJAS[l]['plataforma'] == 'gpa']:
                sid = db.cache_ler(f'gpa_loja|{lj}|{self.cep}') or await L.gpa_loja(c, lj, self.cep)
                if sid:   # entrega no CEP: os preços são os da loja padrão do site (os que a página pública do produto mostra)
                    self.gpa_loja[lj] = L.LOJAS[lj].get('loja_padrao') or sid
                    db.cache_gravar(f'gpa_loja|{lj}|{self.cep}', sid)
                    L._GPA_LOJA[(lj, ''.join(ch for ch in self.cep if ch.isdigit()))] = sid
                else:
                    self.lojas = [l for l in self.lojas if l != lj]
                    if self.ctx:
                        self.ctx.aviso(f'{L.LOJAS[lj]["nome"]} não entrega no CEP {self.cep}: fica de fora desta pesquisa.')
            if 'tenda' in self.lojas:
                self.filial = db.cache_ler(f'tenda_filial|{self.cep}') or await L.tenda_filial(c, self.cep)
                if self.filial:
                    db.cache_gravar(f'tenda_filial|{self.cep}', self.filial)
                elif self.ctx:
                    self.ctx.aviso('Tenda: não foi possível saber a filial que atende o CEP; o estoque do Tenda não foi conferido para o CEP.')
            try:
                await self._etapas()
                self._sem_bloqueadas()
                await self._categoria()
            finally:
                await self.br.close()
        self._sem_bloqueadas()
        return self._resultado()

    def _sem_bloqueadas(self):
        """Loja que barrou no meio da pesquisa (CAPTCHA ou limite de acessos): os anúncios já lidos dela não entram nas opções, porque o
        comprovante exigiria voltar à loja."""
        if not self.bloqueadas:
            return
        for k in list(self.ofertas):
            self.ofertas[k] = [x for x in self.ofertas[k] if x['loja'] not in self.bloqueadas]
        for k in list(self.brutos):
            self.brutos[k] = [x for x in self.brutos[k] if x['loja'] not in self.bloqueadas]

    async def _etapas(self):
        # 1. busca de cada item em cada loja (descrição e família)
        consultas = [(l, it['desc'], q) for l in self.lojas for it in self.itens for q in self.buscas[it['desc']]]
        consultas += [(l, it['desc'], it['familia']) for l in self.lojas for it in self.itens if it['familia'] != ID.sa(it['desc'])]
        feitas = 0

        async def uma(l, d, q):
            nonlocal feitas
            out = await self._buscar(l, q)
            feitas += 1
            self._prog(40 * feitas / len(consultas), f'Buscando os itens nas lojas ({feitas}/{len(consultas)})')
            return l, d, out
        for l, d, out in await asyncio.gather(*[uma(*x) for x in consultas]):
            for x in out:
                self._classificar(l, x)
                self.brutos[d].append(dict(x, loja=l))
        # 2. busca direcionada pelas marcas mais presentes (em lojas onde a marca não apareceu)
        conf = {}
        for it in self.itens:
            for nv in (0, 1, 2):
                presentes = defaultdict(set)
                for x in self.ofertas[(it['desc'], nv)]:
                    mk = ID.marca_de(x)
                    if mk:
                        presentes[mk].add(x['loja'])
                for mk, ls in sorted(presentes.items(), key=lambda kv: -len(kv[1]))[:3]:
                    for l in self.lojas:
                        if l not in ls:
                            conf.setdefault((l, f"{it['desc'] if nv == 0 else it['familia']} {mk}"), set()).add(it['desc'])
        feitas = 0

        async def dir_(l, q, ds):
            nonlocal feitas
            out = await self._buscar(l, q)
            feitas += 1
            self._prog(40 + 15 * feitas / max(1, len(conf)), f'Buscando as marcas mais presentes em outras lojas ({feitas}/{len(conf)})')
            return l, out, ds
        for l, out, ds in await asyncio.gather(*[dir_(l, q, ds) for (l, q), ds in conf.items()]):
            for x in out:
                self._classificar(l, x, ds)
        # 3. EAN pela página do produto: as mais baratas com marca, por item/nível/loja
        alvo = {}
        for (d, nv), ofs in self.ofertas.items():
            por_loja = defaultdict(list)
            for x in ofs:
                if L.LOJAS[x['loja']].get('ean') and not x.get('ean') and x.get('url') and ID.marca_de(x):
                    por_loja[x['loja']].append(x)
            for l, xs in por_loja.items():
                for x in sorted(xs, key=lambda x: x['preco'] or 0)[:K_EAN]:
                    alvo.setdefault((l, x['url']), []).append(x)
        feitas = 0

        async def pag(l, u):
            nonlocal feitas
            e = await self._ean_pagina(l, u)
            feitas += 1
            self._prog(55 + 15 * feitas / max(1, len(alvo)), f'Lendo o código de barras nas páginas dos produtos ({feitas}/{len(alvo)})')
            return e
        for ((l, u), xs), e in zip(alvo.items(), await asyncio.gather(*[pag(l, u) for l, u in alvo])):
            for x in xs:
                x['ean'] = e
        # 4. ponte de EAN: o mesmo código procurado nas lojas VTEX que ainda não o têm
        ponte = {}
        for (d, nv), ofs in self.ofertas.items():
            freq = Counter(x['ean'].lstrip('0') for x in ofs if x.get('ean'))
            com = defaultdict(set)
            for x in ofs:
                if x.get('ean'):
                    com[x['ean'].lstrip('0')].add(x['loja'])
            for ean, _ in freq.most_common(K_PONTE):
                for l in self.lojas:
                    if L.LOJAS[l]['plataforma'] == 'vtex' and l not in com[ean]:
                        ponte.setdefault((l, ean), set()).add(d)
        feitas = 0

        async def pon(l, e):
            nonlocal feitas
            out = await self._ponte_vtex(l, e)
            feitas += 1
            self._prog(70 + 10 * feitas / max(1, len(ponte)), f'Procurando o mesmo código de barras em outras lojas ({feitas}/{len(ponte)})')
            return out
        for ((l, e), ds), out in zip(ponte.items(), await asyncio.gather(*[pon(l, e) for l, e in ponte])):
            for x in out:
                self._classificar(l, x, ds)
        # 5. estoque e preço REAIS no CEP (VTEX)
        self._prog(80, 'Conferindo estoque e preço para o CEP')
        por_loja = defaultdict(list)
        for ofs in self.ofertas.values():
            for x in ofs:
                if x.get('simular'):
                    por_loja[x['loja']].append(x)
        memo = db.cache_ler(f'sim|{self.cep}') or {}
        await asyncio.gather(*[asyncio.wait_for(L.simular(self.c, l, xs, self.cep, memo), 120) for l, xs in por_loja.items()], return_exceptions=True)
        db.cache_gravar(f'sim|{self.cep}', memo)
        for k in list(self.ofertas):
            vistos = set()
            self.ofertas[k] = [x for x in self.ofertas[k] if x.get('disp') and x.get('preco') and not x.get('simular')
                               and not ((x['loja'], x.get('url')) in vistos or vistos.add((x['loja'], x.get('url'))))]
        self._prog(90, 'Agrupando os anúncios que são o mesmo produto')

    async def _categoria(self):
        """Último degrau das trocas: para os itens sem o mesmo produto em 3 lojas (nem parecido, nem relacionado), procura produtos
        da CATEGORIA da rubrica (extras da rubrica + catálogo), com as mesmas regras de identidade, estoque e preço no CEP."""
        self.grupos_categoria = {}
        grupos = self._grupos()
        faltam = [it for it in self.itens if not any(len(self._ordem_lojas(g)[0]) == 3 for nv in (0, 1, 2) for g in grupos[(it['desc'], nv)])
                  and not (self.marcas_diferentes and any(len(self._ordem_lojas(g)[0]) == 3 for g in ID.agrupar_espec(self.ofertas[(it['desc'], 0)], it['desc'])))]
        def garantido(it):   # mesmo EAN em 3 lojas de empresas diferentes: a IA não precisa conferir, não há risco de o item ficar sem opção
            for g in grupos[(it['desc'], 0)]:
                tres, _ = self._ordem_lojas(g)
                if len(tres) == 3 and len({(g['por_loja'][l].get('ean') or l).lstrip('0') for l in tres}) == 1:
                    return True
            return False
        if all(garantido(it) for it in self.itens) or not (self.setor or self.extras):
            return
        termos = C.candidatos(self.setor, self.descs, self.extras)[:MAX_CATEGORIA]
        if not termos:
            return
        # só lojas lidas sem navegador (APIs e HTML): o degrau da categoria faz muitas buscas, e páginas abertas em rajada disparam o anti-robô
        consultas = [(l, t) for t in termos for l in self.lojas if L.LOJAS[l]['plataforma'] != 'render']
        feitas = 0

        async def uma(l, t):
            nonlocal feitas
            out = await self._buscar(l, t)
            feitas += 1
            self._prog(90 + 4 * feitas / len(consultas), f'Itens sem o mesmo produto em 3 lojas: procurando produtos da categoria ({feitas}/{len(consultas)})')
            return l, t, out
        por_termo = defaultdict(list)
        for l, t, out in await asyncio.gather(*[uma(l, t) for l, t in consultas]):
            for x in out:
                if not (x.get('simular') or (x.get('disp') and x.get('preco'))) or f"{l}|{x.get('url')}" in self.indisp_hoje:
                    continue
                if ID.nivel(t, x['nome'], termos + self.descs, ID.familia_padrao(t)) == 0:
                    por_termo[t].append(dict(x, loja=l))
        por_loja = defaultdict(list)
        for ofs in por_termo.values():
            for x in ofs:
                if x.get('simular'):
                    por_loja[x['loja']].append(x)
        memo = db.cache_ler(f'sim|{self.cep}') or {}
        await asyncio.gather(*[asyncio.wait_for(L.simular(self.c, l, xs, self.cep, memo), 120) for l, xs in por_loja.items()], return_exceptions=True)
        db.cache_gravar(f'sim|{self.cep}', memo)
        for t, ofs in por_termo.items():
            ofs = [x for x in ofs if x.get('disp') and x.get('preco') and not x.get('simular')]
            self.grupos_categoria[t] = ID.agrupar(ofs, t) + (ID.agrupar_espec(ofs, t) if self.marcas_diferentes else [])
        if self.ctx and faltam:
            self.ctx.aviso(f'{len(faltam)} item(ns) sem o mesmo produto em 3 lojas: o sistema procurou {len(termos)} produtos da categoria da rubrica '
                           f'para substituí-los ({", ".join(it["desc"] for it in faltam)}).')

    # ---------------------------------------------------------------- escolha
    def _grupos(self):
        g = {}
        for it in self.itens:
            for nv in (0, 1, 2):
                ofs = [x for n in range(nv + 1) for x in self.ofertas[(it['desc'], n)]]
                g[(it['desc'], nv)] = ID.agrupar(ofs, it['familia'] if nv else it['desc'])
        return g

    @staticmethod
    def _ordem_lojas(g):
        """Critério neutro: as lojas mais baratas com o produto, cada uma de uma empresa diferente (raiz do CNPJ).
        Devolve (as 3 escolhidas, as reservas na mesma ordem)."""
        ordem = sorted(g['por_loja'], key=lambda l: (g['por_loja'][l]['preco'], not g['por_loja'][l].get('ean'), not L.LOJAS[l]['carrinho']))
        tres, raizes = [], set()
        for l in ordem:
            if len(tres) < 3 and L.raiz(l) not in raizes:
                tres.append(l); raizes.add(L.raiz(l))
        return tres, [l for l in ordem if l not in tres]

    @classmethod
    def _opcao(cls, it, g, nv, lojas, reservas=(), substituto=None, misto=False):
        if nv == 3:
            dist, perdidos = 30.0, [it['desc']]
        else:
            dist, perdidos = ID.distancia(it['desc'], g, nv, lojas, it['familia'], peso_ean=0)   # EAN confirma a identidade; o preço decide
        ofs = [g['por_loja'][l] for l in lojas]
        n_ean = sum(1 for x in ofs if x.get('ean'))
        campos = ('loja', 'nome', 'titulo', 'marca', 'ean', 'preco', 'url', 'sku', 'seller', 'vendedor', 'loja_gpa')
        return dict(nivel=nv, distancia=round(dist, 1), perdidos=perdidos, lojas=list(lojas), ean_em=n_ean, substituto=substituto, misto=misto,
                    confirmacao='mesma especificação, marcas diferentes' if misto
                    else 'EAN nas 3 lojas' if n_ean == 3 and len({x['ean'].lstrip('0') for x in ofs}) == 1 else 'descrição',
                    ofertas=[{k: x.get(k) for k in campos} for x in ofs],
                    # outras lojas com o MESMO produto: entram no lugar de uma loja cujo comprovante falhar (carrinho indisponível, página com erro)
                    reservas=[{k: g['por_loja'][l].get(k) for k in campos} for l in reservas],
                    lojas_com_o_produto=len(g['por_loja']))

    @staticmethod
    def _chave(o, valor_ref=None):
        """Ordem das opções de um item: o mais próximo do pedido e, empatando, o MENOR PREÇO (no degrau da categoria, o preço mais
        próximo do valor que o item tinha no plano, para não desequilibrar a rubrica)."""
        media = sum(x['preco'] for x in o['ofertas']) / 3
        misto = 1 if o.get('misto') else 0   # o MESMO produto vem antes do produto igual de outra marca
        if o['nivel'] == 3 and valor_ref:
            return (3, misto, 0, abs(media - valor_ref))
        return (o['nivel'], misto, o['distancia'], media)

    def _opcoes_por_item(self, grupos):
        """Para cada item, as melhores opções (mesmo produto em 3 lojas de empresas diferentes)."""
        out = {}
        for it in self.itens:
            cands = []
            for nv in (0, 1, 2):
                for g in grupos[(it['desc'], nv)]:
                    tres, res = self._ordem_lojas(g)
                    if len(tres) == 3:
                        cands.append(self._opcao(it, g, nv, tuple(tres), res))
            if self.marcas_diferentes:   # produto IGUAL (como descrito) de marcas diferentes, quando o mesmo produto não fecha 3 lojas
                for cor_sempre in (True, False):   # de preferência com a mesma cor; depois, com cores diferentes (se o pedido não cita cor)
                    for g in ID.agrupar_espec(self.ofertas[(it['desc'], 0)], it['desc'], cor_sempre):
                        tres, res = self._ordem_lojas(g)
                        if len(tres) == 3 and len({ID.marca_de(g['por_loja'][l]) for l in tres}) > 1:
                            o = self._opcao(it, g, 0, tuple(tres), res, misto=True)
                            o['distancia'] += 0 if cor_sempre else 0.5
                            cands.append(o)
            cat = []   # último degrau: produto da categoria da rubrica (fica sempre como reserva, para o caso de a IA reprovar as opções acima)
            for t, gs in self.grupos_categoria.items():
                for g in gs:
                    tres, res = self._ordem_lojas(g)
                    if len(tres) == 3:
                        cat.append(self._opcao(it, g, 3, tuple(tres), res, substituto=t, misto=bool(g.get('misto'))))

            def unicas(lista, n, por_termo=False):
                lista.sort(key=lambda o: self._chave(o, it.get('valor_ref')))
                vistos, uniq = set(), []
                for o in lista:  # uma opção por produto (na categoria, uma por tipo de produto: a IA escolhe o substituto mais razoável)
                    k = o.get('substituto') if por_termo else tuple(sorted((x['loja'], x['url']) for x in o['ofertas']))
                    if k not in vistos:
                        vistos.add(k); uniq.append(o)
                return uniq[:n]
            # produto que já é de outro item da rubrica (fora desta pesquisa) não é opção para este
            out[it['desc']] = [o for o in unicas(cands, N_OPCOES) + unicas(cat, 8, por_termo=True) if not (chaves_da_opcao(o) & self.usados)]
        return out

    def escolher(self, opcoes, itens):
        """Uma opção por item; itens com menos opções escolhem antes; o mesmo produto nunca atende dois itens (nem o produto que outro item
        da rubrica já usa), e dois itens nunca são trocados pelo mesmo tipo de produto da categoria."""
        usados, termos, escolha = set(self.usados), set(), {}
        for it in sorted(itens, key=lambda i: len(opcoes.get(i['desc'], []))):
            escolha[it['desc']] = None
            for o in opcoes.get(it['desc'], []):
                chaves = chaves_da_opcao(o)
                if chaves & usados or (o['nivel'] == 3 and o.get('substituto') in termos):
                    continue
                usados |= chaves; escolha[it['desc']] = o
                if o['nivel'] == 3:
                    termos.add(o.get('substituto'))
                break
        return {i['desc']: escolha[i['desc']] for i in itens}

    def _melhor_trio(self, grupos):
        melhor = None
        for trio in itertools.combinations(self.lojas, 3):
            if len({L.raiz(l) for l in trio}) < 3:   # R09: 3 empresas diferentes
                continue
            opc = {}
            for it in self.itens:
                cs = []
                for nv in (0, 1, 2):
                    for g in grupos[(it['desc'], nv)]:
                        if set(trio) <= set(g['por_loja']):
                            cs.append(self._opcao(it, g, nv, trio))
                opc[it['desc']] = sorted(cs, key=self._chave)[:N_OPCOES]
            esc = self.escolher(opc, self.itens)
            ok = [o for o in esc.values() if o]
            chave = (-len(ok), sum(o['distancia'] for o in ok), sum(1 for l in trio if not L.LOJAS[l]['carrinho']),
                     sum(sum(x['preco'] for x in o['ofertas']) for o in ok))
            if melhor is None or chave < melhor[0]:
                melhor = (chave, trio, opc, esc)
        return melhor or (None, (), {}, {i['desc']: None for i in self.itens})

    def _conferir_com_ia(self, opcoes, escolha, volta=0):
        """Casos em dúvida (mesmo produto confirmado só pela descrição) vão para a IA; se ela disser que não é o mesmo produto,
        a opção sai e o item fica com a próxima opção válida. Trocas 'relacionadas': a IA escolhe a mais razoável."""
        from .. import ia
        if not (self.usar_ia and ia.disponivel()):
            return escolha
        sem_resposta = 0
        for _ in range(5):
            mudou = False
            for d, o in escolha.items():
                if not o or o.get('ia') or o.get('ia_sem_resposta') or o['confirmacao'] == 'EAN nas 3 lojas':
                    continue
                self._prog(95, 'Conferindo com a IA os produtos confirmados só pela descrição')
                nomes = [x.get('titulo') or x['nome'] for x in o['ofertas']]
                eans = Counter(x['ean'].lstrip('0') for x in o['ofertas'] if x.get('ean'))
                if not o.get('misto') and eans and eans.most_common(1)[0][1] == 2:   # 2 lojas com o MESMO EAN: são certamente o mesmo produto;
                    e = eans.most_common(1)[0][0]                                     # a IA só compara o anúncio sem EAN com o nome mais completo dos 2
                    com = [x.get('titulo') or x['nome'] for x in o['ofertas'] if x.get('ean') and x['ean'].lstrip('0') == e]
                    nomes = [max(com, key=len)] + [x.get('titulo') or x['nome'] for x in o['ofertas'] if not (x.get('ean') and x['ean'].lstrip('0') == e)]
                r = ia.mesma_especificacao(o.get('substituto') or d, nomes, self.projeto_id) if o.get('misto') else ia.mesmo_produto(nomes, self.projeto_id)
                if r is None:   # uma resposta ruim não pode desligar a conferência dos outros itens
                    o['ia_sem_resposta'] = True
                    sem_resposta += 1
                    if sem_resposta >= 3:
                        if self.ctx:
                            self.ctx.aviso('A IA não respondeu (cota, rede ou formato); os produtos confirmados só pela descrição ficaram '
                                           'sem a conferência dela — confira os marcados com 🟡.')
                        return escolha
                    continue
                o['ia'] = dict(mesmo_produto=r[0], motivo=r[1])
                if not r[0]:
                    opcoes[d] = [x for x in opcoes[d] if x is not o]; mudou = True
                    self.rejeitadas_ia[d].append(dict(produtos=[x.get('titulo') or x['nome'] for x in o['ofertas']], motivo=r[1]))
            if not mudou:
                break
            escolha = self.escolher(opcoes, self.itens)
        if self.marcas_diferentes:
            for it in self.itens:
                o = escolha.get(it['desc'])
                if o is None or o['nivel'] == 3:   # nada fechou pelas regras (ou só a categoria): a IA monta o trio de produtos equivalentes
                    novo = self._trio_pela_ia(it, {k for d2, o2 in escolha.items() if o2 and d2 != it['desc'] for x in o2['ofertas'] for k in [(x['loja'], x['url'])]})
                    if novo:
                        opcoes[it['desc']].insert(0, novo); escolha[it['desc']] = novo
        for it in self.itens:
            o = escolha.get(it['desc'])
            rel = [x for x in opcoes.get(it['desc'], []) if o and x['nivel'] == o['nivel']]
            if o and o['nivel'] >= 2 and len(rel) > 1 and not o.get('ia_subst'):   # troca relacionada ou da categoria: a IA escolhe a mais razoável
                nomes = [x.get('substituto') or x['ofertas'][0]['nome'] for x in rel]
                r = (ia.substituto_da_categoria(it['desc'], self.setor or 'material', nomes, self.projeto_id) if o['nivel'] == 3
                     else ia.melhor_substituto(it['desc'], nomes, self.projeto_id))
                if r and r[0] is not None:
                    rel[r[0]]['ia_subst'] = r[1]
                    if rel[r[0]] is not o:
                        opcoes[it['desc']].remove(rel[r[0]]); opcoes[it['desc']].insert(0, rel[r[0]])
                        escolha = self.escolher(opcoes, self.itens)
        # opção que entrou depois (trio, substituto) e ainda não foi conferida: confere também (no máximo 3 voltas)
        pendente = any(o and not o.get('ia') and not o.get('ia_sem_resposta') and o['confirmacao'] != 'EAN nas 3 lojas' for o in escolha.values())
        if pendente and volta < 3:
            return self._conferir_com_ia(opcoes, escolha, volta + 1)
        return escolha

    @staticmethod
    def _outro_item(nome, outros):
        """O anúncio é OUTRO item da cesta? Compara a palavra inteira do tipo ("grampeador" não é "grampo")."""
        import re
        toks = re.findall(r'[a-z]+', ID.sa(nome))[:2]
        for o in outros:
            ps = re.findall(r'[a-z]{3,}', ID.sa(o))
            if not ps:
                continue
            h = ps[0][:-1] if len(ps[0]) > 4 and ps[0].endswith('s') else ps[0]
            if any(t == h or t == h + 's' for t in toks) and ID.compativel(o, nome, 0):
                return True
        return False

    def _trio_pela_ia(self, it, usados):
        """Produto similar em 3 lojas, escolhido pela IA entre os anúncios do tipo do item (níveis 0 a 2) e VALIDADO aqui: 3 lojas de
        empresas diferentes, anúncios existentes e ainda não usados por outro item. None se a IA não achar (ou não estiver disponível)."""
        from .. import ia
        por_loja = defaultdict(list)
        for nv in (0, 1, 2):
            for x in self.ofertas[(it['desc'], nv)]:
                if (x['loja'], x['url']) not in usados and not any(y['url'] == x['url'] for y in por_loja[x['loja']]):
                    por_loja[x['loja']].append(dict(x, nivel=nv))
        # mais os anúncios do MESMO TIPO de produto que as regras deixaram de fora por não citarem um detalhe do pedido (ex.: grampeador de
        # mesa anunciado sem o "26/6"): a IA decide quais são equivalentes; estoque e preço são conferidos depois, no comprovante
        outros = [d for d in self.descs if d != it['desc']]
        for x in self.brutos.get(it['desc'], []):
            if not (x.get('preco') and x.get('disp') and x.get('url')) or (x['loja'], x['url']) in usados or f"{x['loja']}|{x['url']}" in self.indisp_hoje:
                continue
            if any(y['url'] == x['url'] for y in por_loja[x['loja']]):
                continue
            if not ID.cabeca_ok(it['desc'], x['nome'], it['familia']) or ID.negado(it['desc'], x['nome'], it['familia']):
                continue
            if self._outro_item(x['nome'], outros):
                continue
            por_loja[x['loja']].append(dict(x, nivel=2))
        cands = [x for l, xs in por_loja.items() for x in sorted(xs, key=lambda x: (x['nivel'], x['preco']))[:6]]
        if len({L.raiz(x['loja']) for x in cands}) < 3:
            return None
        cands = sorted(cands, key=lambda x: (x['nivel'], x['preco']))[:45]
        self._prog(96, f'Pedindo à IA 3 produtos equivalentes em lojas diferentes para "{it["desc"]}"')
        r = ia.montar_trio(it['desc'], [dict(i=i, loja=L.LOJAS[x['loja']]['nome'], nome=x.get('titulo') or x['nome'], preco=x['preco'] / 100)
                                        for i, x in enumerate(cands)], self.projeto_id)
        if not r or not r[0] or any(not 0 <= i < len(cands) for i in r[0]):
            return None
        tres = [cands[i] for i in r[0]]
        if len({L.raiz(x['loja']) for x in tres}) < 3:
            return None
        g = dict(por_loja={x['loja']: x for x in tres}, amarelo=True, misto=True)
        raizes, reservas = {L.raiz(x['loja']) for x in tres}, []
        for i in (r[2] if len(r) > 2 else []):   # reservas indicadas pela IA: outro anúncio equivalente, de empresa que não está no trio
            if 0 <= i < len(cands) and L.raiz(cands[i]['loja']) not in raizes and len(reservas) < 3:
                raizes.add(L.raiz(cands[i]['loja'])); reservas.append(cands[i]['loja']); g['por_loja'][cands[i]['loja']] = cands[i]
        nv = 0 if all(x['nivel'] == 0 for x in tres) else 1   # equivalentes ao pedido; nível 1 quando algum anúncio não cita todos os detalhes
        o = self._opcao(it, g, nv, tuple(x['loja'] for x in sorted(tres, key=lambda x: x['preco'])), reservas=tuple(reservas), misto=True)
        o['perdidos'] = []
        o['ia'] = dict(mesmo_produto=True, motivo=r[1]); o['trio_ia'] = True
        o['confirmacao'] = 'mesma especificação, marcas diferentes'
        return o

    def _resultado(self):
        grupos = self._grupos()
        if self.modo == 'trio' and len(self.lojas) >= 3:
            _, trio, opcoes, escolha = self._melhor_trio(grupos)
        else:
            trio, opcoes = None, self._opcoes_por_item(grupos)
            escolha = self.escolher(opcoes, self.itens)
        escolha = self._conferir_com_ia(opcoes, escolha)
        incompletas = {L.LOJAS[l]['nome']: f'{self.falhas_loja[l]} falhas em {self.buscas_loja[l]} buscas'
                       for l in self.lojas if self.falhas_loja[l] and self.falhas_loja[l] >= 0.2 * max(1, self.buscas_loja[l])}
        incompletas.update({L.LOJAS[l]['nome']: f'bloqueada — {m}' for l, m in self.bloqueadas.items()})
        if incompletas and self.ctx:
            self.ctx.aviso('RESULTADO INCOMPLETO — lojas com muitas falhas de busca (itens podem existir e não ter sido lidos): '
                           + '; '.join(f'{k} ({v})' for k, v in incompletas.items()))
        self._prog(100, 'Concluído')
        return dict(modo=self.modo, trio=list(trio) if trio else None, itens=self.itens, escolha=escolha, opcoes=opcoes, entendido=self.entendido,
                    lojas=self.lojas, lojas_incompletas=incompletas, rejeitadas_ia=dict(self.rejeitadas_ia), buscas=sum(self.buscas_loja.values()), falhas=sum(self.falhas_loja.values()))


async def pesquisar(itens, lojas, cep, ctx=None, modo='por_item', usar_ia=True, projeto_id=None, setor=None, extras=(), marcas_diferentes=False,
                    outros=(), usados=()):
    return await Motor(itens, lojas, cep, ctx, modo, usar_ia, projeto_id, setor, extras, marcas_diferentes, outros, usados).rodar()
