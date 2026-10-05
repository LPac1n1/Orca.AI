"""Modelo de dados de um projeto (Plano de Trabalho + Grade Comparativa). Valores em centavos inteiros.

Rastreabilidade: cada preço guarda de onde veio (loja/empresa, CNPJ, data, URL, arquivo de evidência e seu SHA-256,
e como foi obtido: 'pdf' lido automaticamente, 'api', 'navegador' ou 'manual').
"""
from typing import Annotated, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class Evidencia(BaseModel):
    arquivo: Optional[str] = None      # caminho relativo dentro da pasta do projeto
    sha256: Optional[str] = None
    url: Optional[str] = None
    capturado_em: Optional[str] = None
    origem: Literal['manual', 'pdf', 'api', 'navegador', 'transcrito'] = 'manual'
    problema: Optional[str] = None     # o comprovante foi guardado, mas não serve (ex.: o preço não aparece no PDF): a pesquisa fica pendente


class Fonte(BaseModel):
    """Uma das 3 fontes de uma rubrica: empresa ofertante (vaga) ou loja (carrinho/orçamento)."""
    nome: str = ''
    cnpj: str = ''
    data_pesquisa: Optional[str] = None       # AAAA-MM-DD
    plataforma: Optional[str] = None          # Catho, InfoJobs… (só vagas)
    evidencia: Evidencia = Field(default_factory=Evidencia)


class PesquisaSalarial(Fonte):
    faixa_min: Optional[int] = None
    faixa_max: Optional[int] = None
    valor: Optional[int] = None               # valor considerado = menor da faixa (R11)
    titulo_vaga: Optional[str] = None         # título do anúncio (pode ser um título similar ao cargo, aceito na tela do cargo)


class RubricaRH(BaseModel):
    tipo: Literal['rh'] = 'rh'
    item: int
    cargo: str
    regime: Literal['RECIBO_MEI', 'PJ', 'CLT'] = 'RECIBO_MEI'
    horas_mes: int
    meses: int
    pesquisas: List[PesquisaSalarial] = Field(default_factory=list)
    valor_mensal_plano: Optional[int] = None  # o que está (ou estará) no Plano de Aplicação (por profissional)
    quantidade: int = 1                       # quantos profissionais com este cargo e esta carga (ex.: 3 assistentes sociais = 1 item, quantidade 3)
    titulos_similares: Optional[List[str]] = None   # títulos aceitos quando faltam vagas com o título exato; None = as sugestões do sistema
    # Faixa salarial pretendida (decisão da OSC, 05/10/2026): quanto se quer pagar por mês a cada profissional. As vagas são as de menor salário
    # cuja média ainda chega nela, e as HORAS do mês são ajustadas para o valor do plano ficar o mais perto possível dela.
    faixa_pretendida: Optional[int] = None


class Subitem(BaseModel):
    descricao: str
    qtd: int
    precos: List[Optional[int]] = Field(default_factory=lambda: [None, None, None])     # unitário em cada fonte
    produtos: List[Optional[str]] = Field(default_factory=lambda: [None, None, None])   # nome do produto no carrinho
    palavras: List[str] = Field(default_factory=list)                                   # identificação no carrinho (opcional)
    valor_plano: Optional[int] = None
    # v0.3 — orçamento POR ITEM: cada subitem com as suas 3 lojas (regra padrão; a SEJC aceita, ver FASE1B §11)
    fontes: List[Fonte] = Field(default_factory=list)          # vazio = usa as 3 fontes da rubrica
    eans: List[Optional[str]] = Field(default_factory=lambda: [None, None, None])
    familia: Optional[str] = None                             # tipo do produto, para trocas por item parecido/relacionado
    nivel: int = 0                                            # 0 como descrito · 1 parecido · 2 relacionado · 3 produto da categoria da rubrica
    descricao_original: Optional[str] = None                  # o que o plano pedia, quando houve troca
    justificativa: Optional[str] = None                       # por que a troca (ou a escolha) foi feita
    confirmacao: Optional[str] = None                         # 'EAN nas 3 lojas' | 'descrição' | 'manual'
    especificacao: Optional[str] = None                       # tamanho, peso, volume ou embalagem pedidos (250 g, 1 L, 5000 unidades, 26/6); opcional
    marca: Optional[str] = None                               # marca pedida pela OSC ou preenchida pelo sistema depois da pesquisa (a das 3 lojas)
    # quando a pesquisa TROCA o item, a especificação e a marca passam a ser as do produto achado; aqui fica o que a OSC tinha escrito
    # ('' = estava em branco). Com descricao_original, formam o PEDIDO original (a chave das pesquisas e do banco de produtos).
    especificacao_original: Optional[str] = None
    marca_original: Optional[str] = None


class RubricaMaterial(BaseModel):
    tipo: Literal['material'] = 'material'
    item: int
    descricao: str
    meses: int
    fontes: List[Fonte] = Field(default_factory=list)
    subitens: List[Subitem] = Field(default_factory=list)
    fontes_por_subitem: dict = Field(default_factory=dict)   # (v0.2) subitem cotado em lojas próprias; na v0.3 use Subitem.fontes
    teto_mensal: Optional[int] = None                        # D9: limite mensal da rubrica (vazio = sem limite próprio)
    extras: List[str] = Field(default_factory=list)          # itens da rubrica que podem ser ACRESCENTADOS se sobrar muito
    regra: Optional[str] = None                              # tipo escolhido pela OSC ('mercado', 'material', 'sistema', 'servico'); vazio = automático
    referencia: Optional[str] = None                         # rubrica de sistema: ferramentas de referência (o plano de cada sistema é escolhido por elas)


class Config(BaseModel):
    divisor_horas: Literal['legal', 'praticado'] = 'legal'
    valores_defensaveis: bool = True
    validade_dias: int = 180
    modo_cesta: Literal['por_item', 'trio'] = 'por_item'     # por item: cada subitem com as suas 3 lojas (padrão)
    marcas_diferentes: bool = False                          # DESLIGADO (03/10/2026): as 3 pesquisas têm de ser exatamente o mesmo produto; o campo fica só para ler projetos antigos
    folga_teto: float = 0.05                                  # D9: sobra acima disso = "muito longe do teto" → acrescentar itens
    usar_ia: bool = True                                      # Gemini só nos casos de dúvida (se houver chave)
    trocar_pela_categoria: bool = True                        # item sem o mesmo produto em 3 lojas (nem parecido): trocar por um produto da categoria da rubrica
    lojas_desligadas: List[str] = Field(default_factory=list)


def _juntar(base, *partes):
    """base + cada parte que ainda não está escrita nela (sem repetir a marca ou a medida que já fazem parte da descrição)."""
    for x in partes:
        x = (x or '').strip()
        if x and x.lower() not in base.lower():
            base = f'{base} {x}'
    return base


def pedido_do_subitem(s: Subitem) -> str:
    """O que se pede à pesquisa: descrição + marca + especificação que a OSC escreveu (as originais, se o produto foi trocado).
    É também a chave do subitem nas pesquisas e no banco de produtos."""
    if s.descricao_original:
        esp = s.especificacao if s.especificacao_original is None else s.especificacao_original   # None: item trocado antes de 03/10/2026
        return _juntar(s.descricao_original, s.marca_original, esp)
    return _juntar(s.descricao, s.marca, s.especificacao)


def descricao_completa(s: Subitem) -> str:
    """Descrição que vai para a grade e o plano: descrição + marca + especificação (o que já está na descrição não se repete)."""
    if s.nivel and s.especificacao_original is None:   # item trocado antes de 03/10/2026: a descrição já é a do produto, e a especificação é a antiga
        return s.descricao
    return _juntar(s.descricao, s.marca, s.especificacao)


def fontes_do_subitem(r: 'RubricaMaterial', s: Subitem) -> List[Fonte]:
    """As 3 fontes que valem para o subitem: as dele (por item), a exceção antiga (fontes_por_subitem) ou as da rubrica."""
    if len(s.fontes) == 3:
        return s.fontes
    fx = r.fontes_por_subitem.get(s.descricao)
    if fx:
        return [f if isinstance(f, Fonte) else Fonte(**{k: v for k, v in f.items() if k in Fonte.model_fields}) for f in fx]
    return r.fontes


class Projeto(BaseModel):
    nome: str
    processo: str = ''
    proponente: str = ''
    orgao: str = 'Secretaria da Justiça e Cidadania (SP)'
    teto: int
    cep: str = ''
    config: Config = Field(default_factory=Config)
    rubricas: List[Annotated[Union[RubricaRH, RubricaMaterial], Field(discriminator='tipo')]] = Field(default_factory=list)
    # comprovante oficial da Receita de cada CNPJ: {CNPJ formatado: dict(arquivo, sha256, situacao, emitido_em, razao, importado_em)}
    comprovantes_cnpj: dict = Field(default_factory=dict)
    # pontos "para revisar" que a OSC já conferiu: {regra|onde|mensagem: dict(em=data e hora)}. Se o ponto mudar, ele volta a aparecer.
    revisados: dict = Field(default_factory=dict)
