"""IA gratuita (Google Gemini, camada gratuita) como APOIO às decisões em dúvida (decisão D12 da OSC).

- A chave é lida da variável de ambiente GEMINI_API_KEY (criada pela própria OSC; ver GEMINI_PASSO_A_PASSO.md). Nunca é exibida ou gravada.
- As REGRAS decidem; a IA só é consultada nos casos 🟡 e a resposta fica registrada (pergunta, resposta, modelo, data).
- Só dados públicos são enviados (nomes de produtos anunciados, nome e atividade de empresas). Na camada gratuita o Google pode usar
  o conteúdo para melhorar os produtos dele.
- Teste de 27/09/2026: 13/15 acertos; os 2 erros foram por excesso de cautela (nunca afrouxou uma regra).
- Instrução "mesmo produto" revisada (E17, com anúncios reais da pesquisa): 19/21, os 2 erros por cautela, em casos que o EAN resolve.
Sem chave ou sem internet, todas as funções devolvem None e o sistema segue só com as regras."""
import hashlib
import json
import os
import re
import sys
import time

from . import db

API = 'https://generativelanguage.googleapis.com/v1beta'
# para a tarefa mais difícil (montar o trio de produtos equivalentes), um modelo mais capaz da camada gratuita, se a conta tiver
FORTES = ['gemini-3.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash', 'gemini-flash-latest']
_nomes = None
PREFERIDOS = ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash', 'gemini-flash-lite-latest', 'gemini-flash-latest']
_modelo = None
_ultimo = 0.0

# instrução revisada e testada em fase1/e17_gemini_instrucao.py: 19/21 contra 16/21 da anterior, sem afrouxar nenhum caso "diferente"
# (a anterior aceitou leite Desnatado junto de Integral e recusou "PT 1 UN" e "Coperalcool + Bacfree" como se fossem diferenças)
MESMO_PRODUTO = (
    'Você confere orçamentos públicos: os anúncios abaixo, de lojas diferentes, precisam ser EXATAMENTE o mesmo produto. '
    'Responda false se houver uma diferença CONCRETA: marca diferente; linha ou modelo diferente (ex.: Primavera × Maciez, Nº1 × Nº2, '
    'A4 × Ofício, Reforçado × Super Econômico); variante diferente (sabor, fragrância, cor, com × sem sal, concentração, teor); '
    'tamanho, peso ou volume diferente; número diferente de unidades DENTRO da embalagem; TIPO de embalagem diferente (a vácuo × almofada/pouch/saco, '
    'refil × embalagem normal, sachê × pote, lata × vidro × caixa); ou uma linha, variante ou tipo de embalagem citado em um só anúncio '
    'que indica outro produto (ex.: "Oceano", "Zero", "Integral", "a Vácuo", "Refil"). O critério é rigoroso: o produto tem de ser idêntico, '
    'a ponto de ter a mesma embalagem na prateleira. '
    'NÃO são diferenças: o jeito de escrever (1,6kg = 1.6kg = 1600g; 50 un = C/50 = 50 unidades; 1L = 1 Litro); o fabricante citado junto '
    'da marca (ex.: Coperalcool e Bacfree, Bombril e Limpol, Ypê e Tixan); a unidade de venda ("1 UN", "PT 1 UN", "CX 1 UN", "Frasco", '
    '"Galão"), que só diz que se vende 1 embalagem; números soltos que são códigos das lojas (ex.: "348"); palavras que só descrevem a '
    'categoria (líquido, etílico, desinfetante, para limpeza, uso geral); e "Clássico"/"Tradicional" quando os outros não citam variante. '
    'Se faltar informação que PODE indicar outro produto, responda false. '
    'Responda com UM objeto JSON (não uma lista): {"mesmo_produto": true|false, "motivo": "curto"}')
MESMA_ESPEC = (
    'Você confere orçamentos públicos. O item pedido está em "pedido". Os anúncios, de lojas diferentes, PODEM ser de marcas diferentes, mas '
    'precisam ser o MESMO TIPO de produto, com a MESMA ESPECIFICAÇÃO: mesma função, mesmo tamanho/peso/volume, mesmo número de unidades na '
    'embalagem, mesmo formato, mesma numeração ou modelo de encaixe (ex.: grampo 26/6) e mesma cor ou variante quando o pedido ou os anúncios a '
    'citam. Responda false se algum anúncio for outro tipo de produto, tiver tamanho, quantidade, formato, numeração ou variante diferente, '
    'ou for de categoria/qualidade claramente diferente (ex.: profissional × escolar, mini × de mesa). Marca diferente NÃO é motivo para false. '
    'COR diferente só é motivo para false quando o PEDIDO cita a cor. Detalhes que o pedido não cita e que não mudam o uso (espessura da ponta, '
    'estampa, acabamento) também não são motivo para false. '
    'Responda com UM objeto JSON (não uma lista): {"mesma_especificacao": true|false, "motivo": "curto"}')
SUBSTITUTO = ('Você monta uma cesta de compras para um projeto social. O item pedido não foi encontrado igual nas lojas. '
              'Entre os candidatos, escolha o substituto mais razoável (mesma finalidade, mais parecido com o pedido) ou nenhum. '
              'Responda só JSON: {"escolha": <índice ou null>, "motivo": "curto"}')
EMPREGADOR = ('Uma vaga de emprego foi anunciada pela empresa abaixo. Diga se é plausível que o CNPJ encontrado seja do empregador '
              '(nome, atividade econômica e local). Responda só JSON: {"plausivel": true|false, "motivo": "curto"}')


def chave():
    k = os.environ.get('GEMINI_API_KEY', '').strip()
    if not k and sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as h:
                k = str(winreg.QueryValueEx(h, 'GEMINI_API_KEY')[0]).strip()
        except OSError:
            k = ''
    return k or None


def disponivel():
    return chave() is not None


def _cliente():
    import httpx
    return httpx.Client(timeout=60, headers={'x-goog-api-key': chave(), 'Content-Type': 'application/json'})


def modelo():
    global _modelo
    if _modelo:
        return _modelo
    with _cliente() as c:
        r = c.get(f'{API}/models', params={'pageSize': 200})
        if r.status_code != 200:
            return None
        nomes = [m['name'].split('/')[-1] for m in r.json().get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])]
    global _nomes
    _nomes = nomes
    _modelo = next((p for p in PREFERIDOS if p in nomes), nomes[0] if nomes else None)
    return _modelo


def modelo_forte():
    m = modelo()
    return next((p for p in FORTES if p in (_nomes or [])), m)


_esgotados = {}   # modelo → dia em que a cota diária gratuita acabou (volta a ser tentado no dia seguinte)


def modelos_para(forte=False):
    """Modelos a tentar, em ordem: o preferido (o mais forte, se pedido) e os seguintes da lista, sem os que já esgotaram a cota de hoje."""
    m = modelo()
    if not m:
        return []
    hoje = time.strftime('%Y-%m-%d')
    lista = ([p for p in FORTES if p in (_nomes or [])] if forte else []) + [m] + [p for p in PREFERIDOS if p in (_nomes or [])]
    return [x for x in dict.fromkeys(lista) if _esgotados.get(x) != hoje]


def perguntar(tipo, instrucao, dados, projeto_id=None, tentativas=4, forte=False):
    """Pergunta com resposta JSON; respostas iguais ficam guardadas (não gasta cota de novo). None se indisponível.
    Cota diária do modelo esgotada, ou modelo sobrecarregado duas vezes seguidas: a pergunta segue no modelo seguinte."""
    global _ultimo
    if not disponivel():
        return None
    pergunta = json.dumps(dados, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha256((tipo + instrucao + pergunta).encode()).hexdigest()[:16]
    with db.conectar() as c:
        row = c.execute('SELECT resposta FROM ia_log WHERE tipo=? AND pergunta LIKE ? ORDER BY id DESC LIMIT 1', (tipo, f'{h}|%')).fetchone()
    if row:
        return _objeto(json.loads(row['resposta']))
    fila = modelos_para(forte)
    if not fila:
        return None
    corpo = {'contents': [{'role': 'user', 'parts': [{'text': instrucao + '\n\nDADOS:\n' + pergunta}]}],
             'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json'}}
    with _cliente() as c:
        for m in fila:
            sobrecarga = 0
            for k in range(tentativas):
                espera = 4.1 - (time.monotonic() - _ultimo)   # ~15 perguntas por minuto no máximo
                if espera > 0:
                    time.sleep(espera)
                _ultimo = time.monotonic()
                try:
                    r = c.post(f'{API}/models/{m}:generateContent', json=corpo)
                except Exception:
                    time.sleep(5); continue
                if r.status_code == 429:
                    if 'PerDay' in r.text:   # acabou a cota gratuita de hoje para este modelo
                        _esgotados[m] = time.strftime('%Y-%m-%d'); break
                    sobrecarga += 1   # limite por minuto: espera e tenta de novo; na segunda vez, passa para o modelo seguinte
                    if sobrecarga >= 2 and m != fila[-1]:
                        break
                    time.sleep(15 * (k + 1)); continue
                if r.status_code >= 500:   # sobrecarga passageira do serviço: tenta de novo; na segunda, passa para o modelo seguinte
                    sobrecarga += 1
                    if sobrecarga >= 2 and m != fila[-1]:
                        break
                    time.sleep(8 * (k + 1)); continue
                if r.status_code != 200:
                    if r.status_code == 404:   # modelo listado, mas não mais oferecido: não é tentado de novo hoje
                        _esgotados[m] = time.strftime('%Y-%m-%d')
                    break
                try:
                    txt = r.json()['candidates'][0]['content']['parts'][0]['text']
                    resp = json.loads(re.sub(r'^```(json)?|```$', '', txt.strip()))
                except Exception:   # resposta cortada ou fora do formato: pergunta de novo
                    time.sleep(2); continue
                with db.conectar() as c2:
                    c2.execute('INSERT INTO ia_log (quando, projeto_id, tipo, modelo, pergunta, resposta) VALUES (?,?,?,?,?,?)',
                               (db.agora(), projeto_id, tipo, m, f'{h}|{pergunta}', json.dumps(resp, ensure_ascii=False)))
                return _objeto(resp)
    return None


def _objeto(resp):
    """O modelo às vezes devolve o objeto pedido dentro de uma lista ([{...}]): desembrulha. Lista com vários itens não é aceita."""
    if isinstance(resp, list) and len(resp) == 1 and isinstance(resp[0], dict):
        return resp[0]
    return resp


def mesmo_produto(nomes, projeto_id=None):
    """nomes: 2 ou mais anúncios. True/False, ou None se a IA não estiver disponível."""
    r = perguntar('mesmo_produto', MESMO_PRODUTO, {f'anuncio_{i + 1}': n for i, n in enumerate(nomes)}, projeto_id)
    return (bool(r.get('mesmo_produto')), r.get('motivo')) if isinstance(r, dict) and 'mesmo_produto' in r else None


def mesma_especificacao(pedido, nomes, projeto_id=None):
    """Produto igual de marcas diferentes: mesmo tipo e mesma especificação? (True/False, motivo) ou None se a IA não estiver disponível."""
    r = perguntar('mesma_especificacao', MESMA_ESPEC, dict({'pedido': pedido}, **{f'anuncio_{i + 1}': n for i, n in enumerate(nomes)}), projeto_id)
    return (bool(r.get('mesma_especificacao')), r.get('motivo')) if isinstance(r, dict) and 'mesma_especificacao' in r else None


MONTAR_TRIO = (
    'Você monta a pesquisa de preços de UM item de um orçamento público. O item está em "pedido". Em "anuncios" há produtos de várias lojas '
    '(i = índice, loja, nome, preco em reais). Escolha 3 anúncios, de 3 LOJAS DIFERENTES, que sejam o mesmo tipo de produto e tenham a mesma '
    'especificação ENTRE SI (mesma função, mesmo tamanho, mesma quantidade na embalagem, mesma numeração ou modelo de encaixe); podem ser de marcas '
    'e cores diferentes (prefira a mesma cor nos 3). Um detalhe que o pedido NÃO cita e que não muda o uso não impede o trio: um anúncio que não '
    'informa o detalhe que outro informa, ou pequenas diferenças como espessura da ponta (0,7 mm × 1,0 mm), estampa ou acabamento. O que o pedido '
    'cita (quantidade, tamanho, numeração) tem de ser igual nos 3. O trio deve atender o pedido ou ser o mais próximo possível dele (mesma '
    'finalidade). Entre os trios válidos, prefira o mais barato. Não escolha kits, refis, acessórios nem produtos de outro tipo. Se não houver 3 '
    'anúncios equivalentes em 3 lojas diferentes, '
    'responda com indices null. Em "reservas", liste os índices de OUTROS anúncios equivalentes aos 3 escolhidos (mesma especificação), de lojas '
    'que não estão no trio, do mais barato ao mais caro ([] se não houver): eles entram no lugar de uma loja do trio que ficar sem estoque. '
    'Responda com UM objeto JSON (não uma lista): {"indices": [i, j, k] ou null, "reservas": [índices], "motivo": "curto"}')


def montar_trio(pedido, anuncios, projeto_id=None):
    """anuncios: [dict(i, loja, nome, preco)]. Devolve ([i, j, k], motivo, reservas), (None, motivo, []) se a IA não achou trio, ou None se
    indisponível. reservas: índices de outros anúncios equivalentes, de outras lojas (para quando um comprovante do trio falhar)."""
    r = perguntar('montar_trio', MONTAR_TRIO, {'pedido': pedido, 'anuncios': anuncios}, projeto_id, forte=True)
    if not isinstance(r, dict) or 'indices' not in r:
        return None
    ix = r.get('indices')
    ok = isinstance(ix, list) and len(ix) == 3 and all(isinstance(i, int) for i in ix)
    rv = [i for i in (r.get('reservas') or []) if isinstance(i, int)] if ok and isinstance(r.get('reservas'), list) else []
    return (ix if ok else None), r.get('motivo'), rv


DA_CATEGORIA = ('Um orçamento de projeto social pedia o item em "pedido", que não existe igual em 3 lojas (nem parecido). A OSC decidiu trocá-lo '
                'por outro produto da MESMA CATEGORIA da rubrica (em "categoria"). Entre os candidatos, escolha o de uso mais próximo do item pedido '
                '(mesma ocasião de consumo ou mesma função: um salgadinho no lugar de um salgadinho, uma bebida no lugar de uma bebida, um material '
                'de escrita no lugar de um material de escrita). Sempre escolha um. '
                'Responda com UM objeto JSON (não uma lista): {"escolha": <índice>, "motivo": "curto"}')


def substituto_da_categoria(pedido, categoria, candidatos, projeto_id=None):
    r = perguntar('da_categoria', DA_CATEGORIA, {'pedido': pedido, 'categoria': categoria, 'candidatos': candidatos}, projeto_id)
    if isinstance(r, dict) and isinstance(r.get('escolha'), int) and 0 <= r['escolha'] < len(candidatos):
        return r['escolha'], r.get('motivo')
    return None


PLANO_SISTEMA = (
    'Uma OSC (projeto social) vai contratar um sistema (software) de gestão e compara 3 sistemas DIFERENTES com ferramentas parecidas. Em '
    '"ferramentas" está a lista numerada das ferramentas do sistema de REFERÊNCIA (a proposta que a OSC já tem). Em "pagina" está o texto da '
    'página de preços de OUTRO sistema ("sistema"), com os planos e o que cada um inclui (✓ = incluído, ✗ ou — = não incluído; numa tabela, as '
    'marcas de cada linha seguem a ordem das colunas dos planos). Em "planos" estão os nomes dos planos dessa página. Para CADA ferramenta de '
    'referência, diga qual recurso da página faz a MESMA FUNÇÃO e em quais planos esse recurso está incluído. Regras: (1) compare pela função, '
    'não pelo nome (ex.: "cadastro de atendidos" equivale a "cadastro de beneficiários"; "relatório com gráficos" equivale a "dashboards"; '
    '"controle de frequência" equivale a "lista de presença"); (2) só vale recurso ESCRITO na página: não suponha; se a página não tem recurso '
    'com essa função, "recurso": null e "planos": []; na dúvida, null; (3) recurso financeiro, contábil, de captação ou de doações não equivale '
    'a ferramenta de atendimento, turmas, frequência ou pesquisa; limite de usuários, filiais ou armazenamento não é ferramenta; (4) plano que '
    '"inclui os recursos do plano anterior" também tem o recurso; (5) em "planos" use só nomes da lista "planos", escritos igual. Responda só '
    'com JSON: {"ferramentas": [{"n": número da ferramenta, "recurso": nome do recurso na página ou null, "planos": [nomes]}], "resumo": uma '
    'frase curta dizendo que tipo de sistema é esse}. A lista da resposta tem de ter uma entrada para cada ferramenta de referência.')


def _mapa_de_ferramentas(lista, sistema, pagina, planos, projeto_id):
    """Uma leitura: [dict(n, recurso, planos)] com uma entrada por ferramenta de referência, ou None."""
    nomes = {str(x['plano']).casefold(): x['plano'] for x in planos}
    r = perguntar('plano_sistema_mapa', PLANO_SISTEMA, dict(ferramentas=[dict(n=i + 1, ferramenta=t) for i, t in enumerate(lista)], sistema=sistema,
                                                             planos=[x['plano'] for x in planos], pagina=(pagina or '')[:12000]), projeto_id, forte=True)
    if not isinstance(r, dict) or not isinstance(r.get('ferramentas'), list):
        return None, ''
    mapa = {}
    for m in r['ferramentas']:
        if not isinstance(m, dict) or not isinstance(m.get('n'), int) or not 1 <= m['n'] <= len(lista):
            continue
        rec = m.get('recurso')
        rec = str(rec).strip()[:120] if rec and str(rec).strip().lower() not in ('null', 'none', 'não encontrado', 'nao encontrado') else None
        pls = [nomes[str(x).casefold()] for x in (m.get('planos') or []) if str(x).casefold() in nomes] if rec else []
        mapa[m['n']] = dict(n=m['n'], recurso=rec if pls else None, planos=pls)
    if len(mapa) < len(lista):   # resposta incompleta: não serve
        return None, ''
    return mapa, str(r.get('resumo') or '')[:200]


def plano_do_sistema(lista, sistema, pagina, planos, projeto_id=None):
    """Para cada ferramenta de referência (lista), o recurso equivalente na página de preços do sistema e os planos que o incluem. A ESCOLHA
    do plano não é da IA: é a regra fixa de sistemas.escolher_plano. planos: [dict(plano, preco_mensal)].
    DUAS leituras da página (a segunda com os blocos em outra ordem): só vale a equivalência que aparece nas duas, nos planos em que as
    duas concordam — equivalência duvidosa, que a IA ora vê, ora não vê, fica de fora. A resposta fica guardada por (ferramentas, sistema,
    planos e preços): enquanto isso não mudar, é a mesma (não oscila de um dia para o outro).
    Devolve dict(ferramentas=[dict(n, recurso, planos)], resumo) ou None (IA indisponível ou resposta inválida)."""
    if not disponivel():
        return None
    fixo = json.dumps(dict(lista=lista, sistema=sistema, planos=planos), ensure_ascii=False, sort_keys=True)
    hk = hashlib.sha256(fixo.encode()).hexdigest()[:16]
    with db.conectar() as c:
        row = c.execute("SELECT resposta FROM ia_log WHERE tipo='plano_sistema_fixo' AND pergunta LIKE ? ORDER BY id DESC LIMIT 1", (f'{hk}|%',)).fetchone()
    if row:
        return json.loads(row['resposta'])
    blocos = [x for x in re.split(r'\n\s*\n', pagina or '') if x.strip()]
    outra = '\n\n'.join(blocos[len(blocos) // 2:] + blocos[:len(blocos) // 2])
    m1, resumo = _mapa_de_ferramentas(lista, sistema, pagina, planos, projeto_id)
    m2, _ = _mapa_de_ferramentas(lista, sistema, outra, planos, projeto_id) if m1 else (None, '')
    if not m1 or not m2:
        return None
    mapa = []
    for n in range(1, len(lista) + 1):
        pls = [x for x in m1[n]['planos'] if x in m2[n]['planos']]
        mapa.append(dict(n=n, recurso=m1[n]['recurso'] if pls else None, planos=pls))
    resp = dict(ferramentas=mapa, resumo=resumo)
    with db.conectar() as c:
        c.execute('INSERT INTO ia_log (quando, projeto_id, tipo, modelo, pergunta, resposta) VALUES (?,?,?,?,?,?)',
                  (db.agora(), projeto_id, 'plano_sistema_fixo', '(duas leituras)', f'{hk}|{fixo}', json.dumps(resp, ensure_ascii=False)))
    return resp


ENTENDER_PEDIDOS = (
    'Uma organização social vai pesquisar preços em lojas virtuais (supermercado, papelaria, limpeza). Em "pedidos" estão os itens como uma pessoa '
    'escreveu: podem vir fora de ordem, abreviados, com a embalagem na frente ("Caixa Caneta Esferográfica Azul" = canetas esferográficas azuis '
    'vendidas em caixa) ou com um adjetivo de embalagem ("Sardinha Enlatada" = sardinha, em lata). Para CADA pedido, sem inventar nada que não '
    'esteja nele, responda: "produto": o tipo do produto com as MESMAS palavras do pedido que dizem o que ele é, em minúsculas, sem embalagem, sem '
    'marca e sem medida (ex.: "caneta esferográfica", "sardinha", "pão de forma integral"); "sinonimos": até 4 OUTROS NOMES que as lojas usam para '
    'exatamente o mesmo tipo de produto (ex.: lápis grafite = "lápis preto"; papel sulfite = "papel a4"), ou [] — nunca produto parecido, marca '
    'nem medida; "buscas": de 1 a 3 textos curtos para digitar na busca das lojas, do mais completo ao mais simples, sem marca que o pedido não '
    'cita; "varias_unidades": true se o pedido é de UMA EMBALAGEM COM VÁRIAS UNIDADES do produto (caixa de canetas, pacote de lápis, kit), false '
    'se é uma unidade do produto na embalagem normal dele (sardinha em lata, leite em caixa, pacote de café, garrafa de água). Responda com UM '
    'objeto JSON: {"itens": [{"n": número do pedido, "produto": "...", "sinonimos": [...], "buscas": [...], "varias_unidades": true|false}]}')


def entender_pedidos(pedidos, projeto_id=None):
    """Interpretação dos pedidos de uma rubrica (uma pergunta só): {pedido: dict(produto, sinonimos, buscas, varias_unidades)}.
    {} se a IA não estiver disponível. Quem usa (cesta.py) confere a resposta: as regras de identidade continuam decidindo."""
    pedidos = list(dict.fromkeys(pedidos))
    r = perguntar('entender_pedidos', ENTENDER_PEDIDOS, {'pedidos': [dict(n=i + 1, pedido=d) for i, d in enumerate(pedidos)]}, projeto_id) if pedidos else None
    out = {}
    for x in (r.get('itens') if isinstance(r, dict) and isinstance(r.get('itens'), list) else []):
        if isinstance(x, dict) and isinstance(x.get('n'), int) and 1 <= x['n'] <= len(pedidos):
            texto = lambda v: [str(s).strip()[:80] for s in (v if isinstance(v, list) else []) if isinstance(s, str) and s.strip()]
            out[pedidos[x['n'] - 1]] = dict(produto=str(x.get('produto') or '').strip()[:60], sinonimos=texto(x.get('sinonimos'))[:4], buscas=texto(x.get('buscas'))[:3],
                                            varias_unidades=x.get('varias_unidades') if isinstance(x.get('varias_unidades'), bool) else None)
    return out


TITULOS_SIMILARES = (
    'Uma organização social pesquisa salários em sites de vagas para o cargo em "cargo". Quando há poucas vagas com esse título exato, valem vagas '
    'de OUTROS TÍTULOS usados no mercado para a MESMA função, com a mesma formação exigida e o mesmo nível (nunca um cargo de chefia no lugar de '
    'um operacional, nem estágio, nem outra profissão). Liste até 5 títulos assim, como aparecem nos anúncios, ou [] se não houver. '
    'Responda com UM objeto JSON: {"titulos": ["..."]}')


def _titulos(r):
    return [str(t).strip()[:60] for t in (r.get('titulos') if isinstance(r, dict) and isinstance(r.get('titulos'), list) else []) if isinstance(t, str) and t.strip()][:5]


def titulos_similares(cargo, projeto_id=None):
    """Sugestões de títulos com a mesma função (a OSC é quem aceita, na tela do cargo). [] se a IA não estiver disponível."""
    return _titulos(perguntar('titulos_similares', TITULOS_SIMILARES, {'cargo': cargo}, projeto_id))


def titulos_similares_guardados(cargo):
    """As sugestões que a IA já deu para o cargo, lidas do registro (sem consultar a internet): para montar a tela."""
    pergunta = json.dumps({'cargo': cargo}, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha256(('titulos_similares' + TITULOS_SIMILARES + pergunta).encode()).hexdigest()[:16]
    try:
        with db.conectar() as c:
            row = c.execute("SELECT resposta FROM ia_log WHERE tipo='titulos_similares' AND pergunta LIKE ? ORDER BY id DESC LIMIT 1", (f'{h}|%',)).fetchone()
        return _titulos(_objeto(json.loads(row['resposta']))) if row else []
    except Exception:
        return []


CONFERIR_REGRA = (
    'Você confere o orçamento de um projeto social contra UMA regra do órgão que vai analisá-lo. A regra está em "regra", com as palavras do órgão. '
    'O plano está em "plano": "itens" traz cada item numerado (n) — cargos de mão de obra (quantidade de profissionais, horas por mês, meses, '
    'valor mensal por profissional, empresas das pesquisas de salário) e rubricas (com os itens, a quantidade por mês e o valor unitário de cada um). '
    'Aponte SÓ o que claramente descumpre a regra, pelo que está escrito no plano; se a regra não puder ser conferida com esses dados, ou se nada a '
    'descumpre, devolva a lista vazia. Não invente fatos. Responda com UM objeto JSON: {"violacoes": [{"n": número do item (ou null se for do plano '
    'inteiro), "motivo": "uma frase curta dizendo o que descumpre"}]}')


def conferir_regra(regra, plano, projeto_id=None):
    """A IA aponta o que no plano parece descumprir a regra em texto: {'violacoes': [{'n', 'motivo'}]} ou None (IA indisponível ou resposta inválida)."""
    r = perguntar('conferir_regra', CONFERIR_REGRA, {'regra': regra, 'plano': plano}, projeto_id, forte=True)
    if not isinstance(r, dict) or not isinstance(r.get('violacoes'), list):
        return None
    return dict(violacoes=[dict(n=v.get('n') if isinstance(v.get('n'), int) else None, motivo=str(v.get('motivo') or '').strip()[:240])
                           for v in r['violacoes'] if isinstance(v, dict) and str(v.get('motivo') or '').strip()][:30])


PROPOR_REGRAS = (
    'Você ajuda uma organização social a cadastrar, num sistema de orçamentos, as regras de um órgão público (secretaria, ministério, fundo) para a '
    'pesquisa de preços e o plano de aplicação de um projeto. Em "texto" está um trecho do edital, manual ou parecer do órgão. Em "tipos" estão os '
    'TIPOS de regra que o sistema sabe conferir, cada um com os campos que precisa. Em "catalogo" estão as regras que o sistema já tem (código e '
    'descrição). Leia o texto e proponha: (1) "proprias": regras novas, cada uma com "tipo" (um dos tipos), "titulo" (frase curta), "gravidade" '
    '("erro" se o órgão proíbe ou exige; "atencao" se recomenda) e "parametros" com os campos do tipo — use o tipo "lembrete" ou "ia" (com o campo '
    '"texto") para o que nenhum outro tipo cobre; (2) "desligar": códigos do catálogo que o texto mostra que NÃO valem para este órgão. Para cada '
    'proposta inclua "trecho": a frase do texto em que ela se baseia, copiada. Só proponha o que o texto diz: se o texto não fala de um assunto, não '
    'crie regra sobre ele. Responda com UM objeto JSON: {"proprias": [...], "desligar": [{"codigo": "...", "trecho": "..."}]}')


def propor_regras(texto, tipos, catalogo, projeto_id=None):
    """Regras propostas pela IA a partir do texto do órgão. Devolve dict(proprias=[...], desligar=[...]) ainda SEM conferir — quem confere e
    quem decide é a tela do órgão. None se a IA não estiver disponível."""
    r = perguntar('propor_regras', PROPOR_REGRAS, {'texto': (texto or '')[:14000], 'tipos': tipos, 'catalogo': catalogo}, projeto_id, forte=True)
    if not isinstance(r, dict):
        return None
    return dict(proprias=[x for x in (r.get('proprias') or []) if isinstance(x, dict)][:25], desligar=[x for x in (r.get('desligar') or []) if isinstance(x, dict)][:25])


def melhor_substituto(pedido, candidatos, projeto_id=None):
    r = perguntar('substituto', SUBSTITUTO, {'pedido': pedido, 'candidatos': candidatos}, projeto_id)
    if isinstance(r, dict) and 'escolha' in r:
        e = r.get('escolha')
        return (e if isinstance(e, int) and 0 <= e < len(candidatos) else None), r.get('motivo')
    return None


def empregador_plausivel(dados, projeto_id=None):
    r = perguntar('empregador', EMPREGADOR, dados, projeto_id)
    return (bool(r.get('plausivel')), r.get('motivo')) if isinstance(r, dict) and 'plausivel' in r else None
