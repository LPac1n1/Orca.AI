"""Regras estabelecidas pela SEJC-SP e utilidades numéricas. Todos os valores em centavos inteiros."""
import datetime as dt
import re
import unicodedata

REGRAS = {
    'R01': ('Média = soma dos 3 orçamentos ÷ 3, calculada com exatidão', 'regra da SEJC'),
    'R02': ('Valor unitário/mensal do plano não pode ultrapassar a média da grade', 'regra da SEJC'),
    'R03': ('Valor abaixo do menor orçamento exige justificativa por ofício', 'regra da SEJC'),
    'R04': ('Total da rubrica = valor unitário × período, sem divergência de centavos', 'regra da SEJC'),
    'R05': ('Soma do plano não pode ultrapassar o recurso (teto)', 'regra da SEJC'),
    'R06': ('Pesquisas em sites/plataformas valem 180 dias', 'regra da SEJC'),
    'R07': ('CNPJ válido e com situação cadastral ATIVA', 'regra da SEJC'),
    'R08': ('A grade identifica a EMPRESA ofertante (nome + CNPJ), nunca a plataforma', 'regra da SEJC'),
    'R09': ('Não usar duas pesquisas da mesma empresa para o mesmo serviço', 'regra da SEJC'),
    'R10': ('Mesmas quantidades e especificações nas 3 simulações de compra', 'regra da SEJC'),
    'R11': ('Faixa salarial: usar o menor valor da faixa', 'regra da SEJC'),
    'R12': ('Pesquisa com várias opções de valor: adotar o menor, salvo justificativa', 'regra da SEJC'),
    'R13': ('Materiais discriminados por subitem, com o valor de cada produto', 'regra da SEJC'),
    'R14': ('Frete não pode constar no plano', 'regra da SEJC'),
    'R15': ('Vaga publicada por site agregador (não pela empresa recrutadora) não vale', 'regra da SEJC'),
    'R16': ('Descrição da rubrica igual à descrição das pesquisas', 'regra da SEJC'),
    'R17': ('Horas mensais inteiras (horas fracionadas geraram divergência de centavos)', 'regra da SEJC'),
    'S01': ('O valor de cada item no plano deve ser o menor dos 3 preços ou a média dos 3 (modo "valores defensáveis")', 'recomendação do sistema'),
    'S02': ('Item trocado por outro parecido ou relacionado à rubrica, com justificativa registrada', 'regra do sistema'),
    'S03': ('Mesmo produto nas 3 lojas confirmado pela descrição (sem código de barras em alguma loja)', 'regra do sistema'),
    'S04': ('Vaga com título similar ao cargo, usada porque não havia 3 vagas com o título exato', 'regra do sistema'),
    'S05': ('A página da vaga guardada como comprovante deve mostrar as informações da empresa', 'regra da SEJC'),
    'S06': ('Rubrica de sistema: o valor no plano é o menor das 3 cotações', 'regra do sistema'),
    'S07': ('O comprovante da vaga deve ser a página do próprio anúncio (não a lista de vagas do site)', 'regra do sistema'),
    'S08': ('Dois itens da mesma rubrica não podem ser o mesmo produto', 'regra do sistema'),
    'S09': ('O valor mensal do cargo segue a faixa salarial pretendida, ajustando as horas (até a jornada inteira do mês)', 'configuração da rubrica'),
    'S10': ('Pedido de uma embalagem com várias unidades (caixa, pacote, kit) atendido com a embalagem, não com a unidade avulsa', 'regra do sistema'),
    'S11': ('As 3 pesquisas de um cargo são de vagas com o MESMO título (o do cargo ou um título similar; nunca dois juntos)', 'regra do sistema'),
    'S12': ('Horas por mês de um cargo: até o limite do projeto (padrão 90 h) e nunca acima da jornada legal do cargo', 'regra do sistema'),
    'D09': ('Teto mensal da rubrica definido pela OSC', 'configuração da rubrica'),
}

# CNPJs de plataformas: nunca podem ser atribuídos ao empregador/fornecedor (R08)
CNPJ_PLATAFORMAS = {'03.753.088/0001-00': 'Catho'}

# Jornadas legais semanais (textos conferidos no planalto.gov.br). Horas mensais = semanais ÷ 6 × 30.
JORNADAS = [
    ('assistente_social', [r'assistente social'], 30, 'Lei 8.662/1993, art. 5º-A'),
    ('fisioterapeuta', [r'fisioterapeut'], 30, 'Lei 8.856/1994, art. 1º'),
    ('terapeuta_ocupacional', [r'terapeuta ocupacional'], 30, 'Lei 8.856/1994, art. 1º'),
    ('tecnico_radiologia', [r'radiolog'], 24, 'Lei 7.394/1985, art. 14'),
    ('telefonista', [r'telefonist', r'telemarketing'], 36, 'CLT art. 227'),
    ('jornalista', [r'jornalist', r'reporter'], 30, 'CLT art. 303 (5h/dia)'),
    ('musico', [r'music', r'instrumentist'], 30, 'Lei 3.857/1960, art. 41 (5h/dia)'),
    ('advogado', [r'advogad'], 40, 'Lei 8.906/1994, art. 20 (red. Lei 14.365/2022)'),
    ('radialista', [r'locutor', r'radialista'], 30, 'Lei 6.615/1978, art. 18, I (5h/dia)'),
]
JORNADA_GERAL = ('geral', [], 44, 'CF art. 7º, XIII')
EM_TRAMITACAO = {'psicolog': 'PL 1.214/2019 (30h) pendente no Senado', 'enferm': 'PEC 19/2024 (30h) em análise',
                 'educador social': 'PLS 328/2015 sem jornada especial'}
# Prática já aceita pela SEJC (várias análises sem objeção ao divisor)
DIVISOR_PRATICADO = {'assistente_social': 120, 'geral': 180}


def norm(s):
    s = unicodedata.normalize('NFKD', (s or '').lower())
    return re.sub(r'\s+', ' ', ''.join(c for c in s if not unicodedata.combining(c))).strip()


def enquadrar(cargo):
    c = norm(cargo)
    for jid, pats, h, base in JORNADAS:
        if any(re.search(p, c) for p in pats):
            return dict(jornada=jid, semanais=h, base_legal=base, alerta=None)
    alerta = next((v for k, v in EM_TRAMITACAO.items() if k in c), None)
    return dict(jornada='geral', semanais=44, base_legal=JORNADA_GERAL[3],
                alerta=alerta or 'sem jornada especial em lei: confirmar convenção coletiva ou edital')


def divisor_horas(cargo, modo):
    """modo 'legal': semanais ÷ 6 × 30 (44h → 220; 30h → 150). modo 'praticado': 180 (Assistente Social 120)."""
    e = enquadrar(cargo)
    if modo == 'praticado':
        return DIVISOR_PRATICADO['assistente_social' if e['jornada'] == 'assistente_social' else 'geral'], e
    return e['semanais'] * 5, e


def horas_maximas(cargo, cfg):
    """O máximo de horas por mês que um cargo pode ter no plano: o limite do projeto (padrão 90 h — decisão da OSC, 06/10/2026) e nunca mais
    que a jornada do mês definida em lei para o cargo (44 h semanais → 220 h; Assistente Social, 30 h → 150 h…)."""
    div, e = divisor_horas(cargo, cfg.divisor_horas)
    legal = div if cfg.divisor_horas == 'praticado' else e['semanais'] * 5
    return max(1, min(legal, getattr(cfg, 'horas_max_mes', None) or legal))


def media(precos):
    """Arredondamento comercial (meio para cima) em centavos; reproduz a grade da SEJC."""
    s, n = sum(precos), len(precos)
    return (2 * s + n) // (2 * n)


def valores_do_plano(precos):
    """Valores que o plano pode ter para um item (decisão da OSC, 03/10/2026): o MENOR dos 3 preços ou a MÉDIA dos 3. O preço do meio
    (nem o menor, nem a média) não vale, e o maior fica sempre acima da média."""
    return sorted({min(precos), media(precos)})


def valor_hora(media_mensal, divisor):
    """Valor-hora arredondado ao centavo (prática aceita pela SEJC)."""
    return (2 * media_mensal + divisor) // (2 * divisor)


def cnpj_digitos(c):
    return re.sub(r'\D', '', c or '')


def cnpj_dv_ok(c):
    c = cnpj_digitos(c)
    if len(c) != 14 or len(set(c)) == 1:
        return False
    def d(base, w):
        r = sum(int(x) * y for x, y in zip(base, w)) % 11
        return '0' if r < 2 else str(11 - r)
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return c[12] == d(c[:12], w1) and c[13] == d(c[:12] + c[12], [6] + w1)


def cnpj_formatar(c):
    c = cnpj_digitos(c)
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}' if len(c) == 14 else c


def vencimento(data_iso, dias=180):
    return dt.date.fromisoformat(data_iso) + dt.timedelta(days=dias)


def brl(c):
    if c is None:
        return '—'
    s = f'{abs(c) / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if c < 0 else '') + 'R$ ' + s
