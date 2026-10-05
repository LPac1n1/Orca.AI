"""Órgãos (secretarias, ministérios, fundos, emendas) e as regras de cada um — pedido da OSC, 05/10/2026.

O sistema nasceu para a SEJC-SP, mas o orçamento de um projeto social muda de órgão para órgão: quantas pesquisas, quem pode ser fornecedor,
o que pode ser comprado, como se chega ao valor do plano. Aqui cada órgão é um cadastro, feito e mantido PELA TELA, com:

- os dados dele (nome, sigla, esfera, estado);
- as regras do catálogo do sistema (regras.REGRAS) que valem para ele: ligada ou desligada, e a gravidade (pendência, para revisar, informação);
- as regras PRÓPRIAS: cada uma é um TIPO que o sistema sabe conferir (regras_dinamicas.TIPOS) mais os parâmetros que a pessoa escreveu
  — "só empresas de SP", "material permanente não pode", "mão de obra até 60% do total" — ou um texto conferido por uma pessoa ou pela IA;
- como o orçamento é feito (validade das pesquisas, valor do plano, jornada) e o modelo de planilha.

Nada disso está no código: mudar a regra de um órgão é editar o cadastro. calculo.verificar aplica o órgão do projeto por cima do que já confere.
Projeto sem órgão (os anteriores a esta versão) segue o padrão do sistema, que é o comportamento de sempre."""
import json
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from . import db
from .regras import REGRAS

GRAVIDADES = {'erro': 'Pendência (bloqueia o envio)', 'atencao': 'Para revisar', 'info': 'Só informação'}
ESFERAS = {'estadual': 'Estadual', 'municipal': 'Municipal', 'federal': 'Federal', 'outro': 'Outro'}
# regras que garantem que o orçamento está inteiro e é verdadeiro: valem para qualquer órgão e não podem ser desligadas
FIXAS = {'R01', 'R05', 'R10', 'S07', 'S08'}
MODELOS = {'sejc': 'Plano de Aplicação, cronogramas, etapas e fases e Comparativo de Preço (modelo de pré-cálculos)',
           'simples': 'Só o Plano de Aplicação e o Comparativo de Preço'}
DESEMBOLSOS = {'unica': 'Parcela única, no 1º mês', 'mensal': 'Mês a mês, conforme o cronograma físico-financeiro'}
SIGLA_PADRAO = 'SEJC-SP'


class AjusteRegra(BaseModel):
    ativa: bool = True
    gravidade: Optional[Literal['erro', 'atencao', 'info']] = None   # None = a gravidade que a regra já tem


class RegraPropria(BaseModel):
    codigo: str                                   # P01, P02... (único dentro do órgão)
    tipo: str                                     # um dos regras_dinamicas.TIPOS
    titulo: str
    gravidade: Literal['erro', 'atencao', 'info'] = 'atencao'
    parametros: dict = Field(default_factory=dict)
    ativa: bool = True


class Parametros(BaseModel):
    """Como o orçamento é feito neste órgão (vira a configuração inicial dos projetos dele)."""
    validade_dias: int = 180
    valor_do_plano: Literal['menor_ou_media', 'ate_media'] = 'menor_ou_media'   # menor dos 3 preços ou a média · qualquer valor até a média
    divisor_horas: Literal['legal', 'praticado'] = 'legal'
    desembolso: Literal['unica', 'mensal'] = 'unica'                             # o repasse: tudo no 1º mês · mês a mês, conforme o cronograma


class Orgao(BaseModel):
    nome: str
    sigla: str = ''
    esfera: Literal['estadual', 'municipal', 'federal', 'outro'] = 'estadual'
    uf: str = ''
    observacoes: str = ''
    concedente: str = ''                          # como o órgão aparece na coluna "Concedente (…)" do Plano de Aplicação; em branco, a sigla
    regras: Dict[str, AjusteRegra] = Field(default_factory=dict)      # só as que diferem do padrão
    proprias: List[RegraPropria] = Field(default_factory=list)
    parametros: Parametros = Field(default_factory=Parametros)
    modelo_planilha: str = 'sejc'

    def rotulo(self):
        return self.sigla or self.nome

    def no_plano(self):
        return self.concedente or self.sigla or 'órgão'

    def ajuste(self, codigo):
        return self.regras.get(codigo) or AjusteRegra()

    def proximo_codigo(self):
        usados = {r.codigo for r in self.proprias}
        return next(f'P{n:02d}' for n in range(1, 1000) if f'P{n:02d}' not in usados)


def padrao_embutido():
    """O órgão padrão do sistema: a SEJC-SP, com todas as regras do catálogo como sempre foram."""
    return Orgao(nome='Secretaria da Justiça e Cidadania do Estado de São Paulo', sigla=SIGLA_PADRAO, esfera='estadual', uf='SP', concedente='SJC',
                 observacoes='Órgão padrão do sistema. As regras vieram do levantamento das exigências da Secretaria.')


# ------------------------------------------------------------------ cadastro (tabela orgao)
def _linha(r):
    return dict(id=r['id'], criado_em=r['criado_em'], alterado_em=r['alterado_em'], removido_em=r['removido_em'], orgao=Orgao(**json.loads(r['json'])))


def listar(removidos=False):
    padrao()
    with db.conectar() as c:
        return [_linha(r) for r in c.execute('SELECT * FROM orgao WHERE removido_em IS ' + ('NOT NULL' if removidos else 'NULL') + ' ORDER BY id')]


def ler(oid):
    """O órgão de número oid (mesmo removido), ou None."""
    if oid is None:
        return None
    with db.conectar() as c:
        r = c.execute('SELECT * FROM orgao WHERE id=?', (oid,)).fetchone()
    return Orgao(**json.loads(r['json'])) if r else None


def criar(o: Orgao):
    padrao()   # o órgão padrão é sempre o primeiro do cadastro, mesmo que alguém crie outro antes de abrir a lista
    return _inserir(o)


def _inserir(o: Orgao):
    with db.conectar() as c:
        return c.execute('INSERT INTO orgao (nome, json, criado_em, alterado_em) VALUES (?,?,?,?)', (o.nome, o.model_dump_json(), db.agora(), db.agora())).lastrowid


def salvar(oid, o: Orgao):
    with db.conectar() as c:
        c.execute('UPDATE orgao SET nome=?, json=?, alterado_em=? WHERE id=?', (o.nome, o.model_dump_json(), db.agora(), oid))


def remover(oid, remover_=True):
    """Tira o órgão da lista (ou devolve). Nada é apagado: os projetos dele continuam com as regras dele."""
    with db.conectar() as c:
        c.execute('UPDATE orgao SET removido_em=? WHERE id=?', (db.agora() if remover_ else None, oid))


def padrao():
    """O número do órgão padrão (SEJC-SP) no cadastro; cria na primeira vez."""
    with db.conectar() as c:
        r = c.execute('SELECT id FROM orgao ORDER BY id LIMIT 1').fetchone()
    return r['id'] if r else _inserir(padrao_embutido())


def projetos_do_orgao(oid):
    """Quantos projetos em uso estão ligados ao órgão (para avisar antes de remover)."""
    n = 0
    for x in db.listar():
        p, _ = db.carregar(x['id'])
        n += 1 if p is not None and (p.orgao_id == oid or (p.orgao_id is None and oid == padrao())) else 0   # projeto ainda sem órgão: é do padrão
    return n


def do_projeto(p):
    """O órgão do projeto. Projeto sem órgão (anterior a esta versão, ou criado fora da tela): o padrão embutido, sem consultar o banco."""
    if getattr(p, 'orgao_id', None) is None:
        return padrao_embutido()
    try:
        return ler(p.orgao_id) or padrao_embutido()
    except Exception:
        return padrao_embutido()


# ------------------------------------------------------------------ o texto de cada regra, para as telas
def texto_da_regra(codigo, orgao=None):
    """(descrição, origem) da regra: do catálogo do sistema ou das regras próprias do órgão."""
    if codigo in REGRAS:
        desc, origem = REGRAS[codigo]
        if orgao is not None and origem == 'regra da SEJC' and orgao.sigla != SIGLA_PADRAO:
            origem = f'regra de {orgao.rotulo()}'
        return desc, origem
    for r in (orgao.proprias if orgao is not None else []):
        if r.codigo == codigo:
            return r.titulo, f'regra própria de {orgao.rotulo()}'
    return codigo, 'regra do órgão'


def catalogo(orgao):
    """As regras do sistema como a tela do órgão mostra: código, descrição, origem, se pode desligar, e o ajuste do órgão."""
    from .calculo import GRAVIDADE_PADRAO
    out = []
    for cod, (desc, origem) in REGRAS.items():
        a = orgao.ajuste(cod)
        out.append(dict(codigo=cod, descricao=desc, origem=texto_da_regra(cod, orgao)[1], fixa=cod in FIXAS, ativa=a.ativa or cod in FIXAS,
                        gravidade=a.gravidade, padrao=GRAVIDADE_PADRAO.get(cod), ajustavel=cod in GRAVIDADE_PADRAO and cod not in FIXAS))
    return out


# ------------------------------------------------------------------ aplicar o órgão à verificação
def aplicar(p, alertas, fabrica):
    """Os alertas do projeto segundo o órgão dele: regra desligada some, gravidade ajustada troca, e entram as regras próprias.
    fabrica(regra, gravidade, onde, mensagem) cria o alerta (calculo.Alerta). Projeto sem órgão: os alertas ficam como estão."""
    if getattr(p, 'orgao_id', None) is None:
        return alertas
    o = do_projeto(p)
    out = []
    from .calculo import GRAVIDADE_PADRAO
    ordem = {'info': 0, 'atencao': 1, 'erro': 2}
    for a in alertas:
        aj = o.regras.get(a.regra)
        if aj and not aj.ativa and a.regra not in FIXAS:
            continue
        if aj and aj.gravidade and a.gravidade in ordem and a.regra not in FIXAS:
            pad = GRAVIDADE_PADRAO.get(a.regra, a.gravidade)
            if ordem[aj.gravidade] < ordem[pad] and ordem[a.gravidade] > ordem[aj.gravidade]:   # regra abrandada: nenhum ponto dela fica mais forte que isso
                a.gravidade = aj.gravidade
            elif ordem[aj.gravidade] > ordem[pad] and a.gravidade == pad:                         # regra endurecida: o ponto principal sobe
                a.gravidade = aj.gravidade
        out.append(a)
    from . import regras_dinamicas
    try:
        out += [fabrica(*x) for x in regras_dinamicas.conferir(p, o)]
    except Exception as e:   # uma regra própria mal preenchida não pode derrubar a tela do projeto
        out.append(fabrica('P00', 'atencao', 'Plano', f'não foi possível conferir as regras próprias de {o.rotulo()} ({type(e).__name__}): revise o cadastro do órgão'))
    return out
