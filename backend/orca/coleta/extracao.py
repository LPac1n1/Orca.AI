"""Extração de dados de páginas (sem rede): produto, vaga, preços visíveis e CNPJs.

Fontes, em ordem: dados estruturados da página (JSON-LD schema.org), microdados e
metadados. Preços nunca passam por float. O preço extraído só é aceito se aparecer
no texto visível da página (docs/04 §5.3).
"""

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from orca.calculo import centavos_de_decimal, centavos_de_texto
from orca.dominio import normalizar_cnpj, normalizar_gtin

_JSONLD = re.compile(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)
_ATRIBUTO_PRECO = re.compile(
    r"<[^>]+(?:itemprop=[\"']price[\"']|property=[\"'](?:product|og):price:amount[\"'])[^>]*>", re.I
)
_CONTEUDO = re.compile(r"content=[\"']([^\"']+)[\"']", re.I)
_PRECO_BRL = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})(?!\d)")
_CNPJ_FORMATADO = re.compile(r"(?<![0-9A-Z])([0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-\d{2})(?!\d)", re.I)
_CNPJ_ROTULADO = re.compile(r"CNPJ[^0-9A-Z]{0,12}([0-9A-Z]{14})(?![0-9A-Z])", re.I)


@dataclass(frozen=True)
class ProdutoExtraido:
    titulo: str | None
    marca: str | None
    ean: str | None
    sku: str | None
    preco_centavos: int | None
    moeda: str | None
    disponivel: bool | None
    vendedor: str | None
    origem: str  # "jsonld", "microdados"
    avisos: tuple[str, ...] = ()


@dataclass(frozen=True)
class VagaExtraida:
    titulo: str | None
    empresa: str | None
    salario_min_centavos: int | None
    salario_max_centavos: int | None
    periodo: str | None  # MONTH, HOUR…
    cidade: str | None
    uf: str | None
    data_publicacao: str | None
    identificador: str | None
    avisos: tuple[str, ...] = field(default=())


# --- JSON-LD ------------------------------------------------------------------


def objetos_jsonld(html: str) -> list[dict[str, Any]]:
    """Todos os objetos JSON-LD da página (inclusive dentro de @graph e listas)."""
    objetos: list[dict[str, Any]] = []
    for bloco in _JSONLD.findall(html):
        texto = html_lib.unescape(bloco.strip())
        try:
            dados = json.loads(texto, parse_float=Decimal)
        except json.JSONDecodeError:
            continue
        pilha = [dados]
        while pilha:
            atual = pilha.pop()
            if isinstance(atual, list):
                pilha.extend(atual)
            elif isinstance(atual, dict):
                objetos.append(atual)
                if isinstance(atual.get("@graph"), list):
                    pilha.extend(atual["@graph"])
    return objetos


def _tipo(obj: dict, nome: str) -> bool:
    tipo = obj.get("@type")
    tipos = tipo if isinstance(tipo, list) else [tipo]
    return any(isinstance(t, str) and t.split("/")[-1] == nome for t in tipos)


def _texto(valor: Any) -> str | None:
    if isinstance(valor, dict):
        valor = valor.get("name")
    if isinstance(valor, list):
        valor = valor[0] if valor else None
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _centavos(valor: Any) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        if isinstance(valor, (int, Decimal)):
            return centavos_de_decimal(valor)
        texto = str(valor).strip()
        return centavos_de_decimal(texto) if "," not in texto else centavos_de_texto(texto)
    except (ValueError, TypeError):
        return None


def _ofertas(produto: dict) -> list[dict]:
    ofertas = produto.get("offers")
    if isinstance(ofertas, dict):
        ofertas = [ofertas]
    lista = [o for o in ofertas or [] if isinstance(o, dict)]
    resultado = []
    for oferta in lista:  # AggregateOffer pode trazer "offers" dentro
        internas = oferta.get("offers")
        if isinstance(internas, list):
            resultado.extend(o for o in internas if isinstance(o, dict))
        elif isinstance(internas, dict):
            resultado.append(internas)
        else:
            resultado.append(oferta)
    return resultado


def _preco_oferta(oferta: dict) -> int | None:
    """Preço da oferta; zero conta como "sem preço" (lojas que só mostram o preço depois do CEP)."""
    preco = _centavos(oferta.get("price"))
    if preco is not None and preco <= 0:
        preco = None
    if preco is None:
        especificacao = oferta.get("priceSpecification")
        if isinstance(especificacao, dict):
            preco = _centavos(especificacao.get("price"))
    if preco is None:
        preco = _centavos(oferta.get("lowPrice"))
    return preco


def _disponivel(oferta: dict) -> bool | None:
    valor = oferta.get("availability")
    if not isinstance(valor, str):
        return None
    nome = valor.rsplit("/", 1)[-1].lower()
    if nome in ("instock", "limitedavailability", "onlineonly", "instoreonly"):
        return True
    if nome in ("outofstock", "soldout", "discontinued"):
        return False
    return None


def _ean(produto: dict) -> tuple[str | None, list[str]]:
    for chave in ("gtin13", "gtin", "gtin14", "gtin12", "gtin8", "ean"):
        bruto = produto.get(chave)
        if bruto:
            try:
                return normalizar_gtin(str(bruto)), []
            except ValueError:
                return None, [f"código de barras inválido na página: {bruto}"]
    return None, []


def extrair_produto(html: str) -> ProdutoExtraido | None:
    produtos = [o for o in objetos_jsonld(html) if _tipo(o, "Product")]
    if produtos:
        produto = produtos[0]
        ofertas = _ofertas(produto)
        precos = [p for p in (_preco_oferta(o) for o in ofertas) if p is not None]
        avisos = []
        if len(set(precos)) > 1:
            avisos.append("a página tem mais de uma oferta com preços diferentes")
        oferta = ofertas[0] if ofertas else {}
        ean, avisos_ean = _ean(produto)
        return ProdutoExtraido(
            titulo=_texto(produto.get("name")),
            marca=_texto(produto.get("brand")),
            ean=ean,
            sku=_texto(produto.get("sku")),
            preco_centavos=precos[0] if precos else None,
            moeda=_texto(oferta.get("priceCurrency")),
            disponivel=_disponivel(oferta),
            vendedor=_texto(oferta.get("seller")),
            origem="jsonld",
            avisos=tuple(avisos + avisos_ean),
        )
    for marcador in _ATRIBUTO_PRECO.findall(html):
        conteudo = _CONTEUDO.search(marcador)
        preco = _centavos(conteudo.group(1)) if conteudo else None
        if preco is not None:
            return ProdutoExtraido(None, None, None, None, preco, None, None, None, "microdados")
    return None


_OG_IMAGE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"']og:image[\"'][^>]*content=[\"']([^\"']+)[\"']"
    r"|<meta[^>]+content=[\"']([^\"']+)[\"'][^>]*(?:property|name)=[\"']og:image[\"']", re.I)


def _primeira_imagem(valor: Any) -> str | None:
    if isinstance(valor, str):
        return valor
    if isinstance(valor, list):
        return next((i for i in (_primeira_imagem(v) for v in valor) if i), None)
    if isinstance(valor, dict):
        return _primeira_imagem(valor.get("url") or valor.get("contentUrl"))
    return None


def imagem_da_pagina(html: str, url_base: str) -> str | None:
    """A foto do produto, para mostrar ao lado das outras lojas (D-73): dos dados do produto ou do og:image.

    Só ajuda a pessoa a decidir; nunca decide sozinha (a mesma foto serve para 395 g e 1 kg).
    """
    from urllib.parse import urljoin

    candidatas = [_primeira_imagem(o.get("image")) for o in objetos_jsonld(html) if _tipo(o, "Product")]
    candidatas += [a or b for a, b in _OG_IMAGE.findall(html[:300_000])]
    for imagem in candidatas:
        if imagem:
            endereco = urljoin(url_base, html_lib.unescape(imagem.strip()))
            if endereco.startswith(("https://", "http://")):
                return endereco
    return None


def extrair_vaga(html: str) -> VagaExtraida | None:
    vagas = [o for o in objetos_jsonld(html) if _tipo(o, "JobPosting")]
    if not vagas:
        return None
    vaga = vagas[0]
    salario_min = salario_max = None
    periodo = None
    avisos = []
    base = vaga.get("baseSalary")
    if isinstance(base, dict):
        valor = base.get("value")
        if isinstance(valor, dict):
            salario_min = _centavos(valor.get("minValue", valor.get("value")))
            salario_max = _centavos(valor.get("maxValue", valor.get("value")))
            periodo = _texto(valor.get("unitText"))
        else:
            salario_min = salario_max = _centavos(valor)
        periodo = periodo or _texto(base.get("unitText"))
        moeda = _texto(base.get("currency"))
        if moeda and moeda.upper() != "BRL":
            avisos.append(f"salário em outra moeda: {moeda}")
    if periodo and periodo.upper() != "MONTH":
        avisos.append(f"salário não é mensal ({periodo})")
    local = vaga.get("jobLocation")
    if isinstance(local, list):
        local = local[0] if local else None
    endereco = local.get("address") if isinstance(local, dict) else None
    cidade = uf = None
    if isinstance(endereco, dict):
        cidade = _texto(endereco.get("addressLocality"))
        uf = _texto(endereco.get("addressRegion"))
    identificador = vaga.get("identifier")
    if isinstance(identificador, dict):
        identificador = identificador.get("value")
    return VagaExtraida(
        titulo=_texto(vaga.get("title")),
        empresa=_texto(vaga.get("hiringOrganization")),
        salario_min_centavos=salario_min,
        salario_max_centavos=salario_max,
        periodo=periodo,
        cidade=cidade,
        uf=uf,
        data_publicacao=_texto(vaga.get("datePosted")),
        identificador=_texto(identificador),
        avisos=tuple(avisos),
    )


# --- Texto visível ------------------------------------------------------------


def precos_visiveis(texto: str) -> list[int]:
    """Todos os valores "R$ x,yy" do texto, em centavos, na ordem em que aparecem."""
    return [int(inteiro.replace(".", "")) * 100 + int(cent) for inteiro, cent in _PRECO_BRL.findall(texto)]


def _procurar_preco(preco_centavos: int, texto: str) -> re.Match | None:
    reais, cent = divmod(preco_centavos, 100)
    com_milhar = f"{reais:,}".replace(",", ".") + f",{cent:02d}"
    sem_milhar = f"{reais},{cent:02d}"
    return re.search(rf"(?<![\d.,])(?:{re.escape(com_milhar)}|{re.escape(sem_milhar)})(?!\d)", texto)


def preco_aparece(preco_centavos: int, texto: str) -> bool:
    """O preço aparece no texto, no formato brasileiro (com ou sem separador de milhar)."""
    return _procurar_preco(preco_centavos, texto) is not None


def precos_perto(preco_centavos: int, texto: str, antes: int = 200, depois: int = 500) -> list[int]:
    """Outros valores "R$" logo antes ou depois do preço (Pix, clube, "leve 5", "de/por").

    Valores distantes (produtos recomendados, rodapé) não entram.
    """
    achado = _procurar_preco(preco_centavos, texto)
    if achado is None:
        return []
    trecho = texto[max(0, achado.start() - antes - 3) : achado.end() + depois]
    return sorted({p for p in precos_visiveis(trecho) if p != preco_centavos})


# --- Forma de pagamento de cada preço (D-60) --------------------------------------

# Depois do valor: "R$ 16,59 no boleto ou PIX", "R$ 19,30 no PIX (3% desc.)", "R$ 10,38 3% OFF no boleto ou PIX".
_DEPOIS_A_VISTA = re.compile(
    r"^\s*(?:\(?\s*\d{1,2}\s*%\s*(?:off|de desconto|desconto|desc\.?)\s*\)?\s*)?(?:à vista\s*)?"
    r"(?:no|pelo|via|com|pagando no|pagando com|em)\s+(?:o\s+)?(pix|boleto)(?:\s+(?:ou|e)\s+(?:no\s+)?(pix|boleto))?",
    re.I,
)
# Antes do valor: "No PIX: R$ 19,30", "Pix por R$ 19,30", "à vista no boleto R$ 19,30".
_ANTES_A_VISTA = re.compile(r"(pix|boleto)\s*(?:\(\s*\d{1,2}\s*%[^)]{0,15}\))?\s*(?:por|:|-)?\s*$", re.I)
# Parcelado: "R$ 17,10 em 1x", "em até 10x de R$ 7,80", "3x de R$ 5,00", "no cartão".
_DEPOIS_PARCELADO = re.compile(r"^\s*(?:em\s+(?:até\s+)?\d{1,2}\s*x|no cartão|parcelad|sem juros)", re.I)
_ANTES_PARCELADO = re.compile(r"(?:\d{1,2}\s*x\s*(?:de|sem juros de)?|parcelas? de|no cartão)\s*$", re.I)


@dataclass(frozen=True)
class PrecoRotulado:
    """Um valor perto do preço do produto e a forma de pagamento escrita junto dele."""

    centavos: int
    forma: str | None  # "pix", "boleto", "pix_ou_boleto", "parcelado" ou None (sem rótulo)
    trecho: str
    distancia: int = 0  # em letras, até o preço lido nos dados da página


def _forma(depois: str, antes: str) -> str | None:
    if (m := _DEPOIS_A_VISTA.match(depois)) is not None:
        formas = {f.lower() for f in m.groups() if f}
        return "pix_ou_boleto" if len(formas) == 2 else formas.pop()
    if _DEPOIS_PARCELADO.match(depois) or _ANTES_PARCELADO.search(antes):
        return "parcelado"
    if (m := _ANTES_A_VISTA.search(antes)) is not None:
        return m.group(1).lower()
    return None


def precos_rotulados(preco_centavos: int, texto: str, antes: int = 150, depois: int = 250) -> list[PrecoRotulado]:
    """Os valores em volta do preço do produto (na primeira vez que ele aparece), com a forma de pagamento."""
    achado = _procurar_preco(preco_centavos, texto)
    if achado is None:
        return []
    inicio = max(0, achado.start() - antes - 3)
    trecho = texto[inicio : achado.end() + depois]
    ancora = achado.start() - inicio
    resultado = []
    for m in _PRECO_BRL.finditer(trecho):
        valor = int(m.group(1).replace(".", "")) * 100 + int(m.group(2))
        pos_antes, pos_depois = trecho[max(0, m.start() - 25) : m.start()], trecho[m.end() : m.end() + 45]
        contexto = " ".join(trecho[max(0, m.start() - 25) : m.end() + 45].split())
        resultado.append(PrecoRotulado(valor, _forma(pos_depois, pos_antes), contexto, abs(m.start() - ancora)))
    return resultado


@dataclass(frozen=True)
class EscolhaDoPreco:
    centavos: int
    forma: str  # "pix", "boleto" ou "pix_ou_boleto"
    trecho: str


def preco_a_vista(preco_centavos: int, texto: str) -> EscolhaDoPreco | None:
    """D-60 (revisada no piloto, 24/09/2026): o preço no Pix; sem Pix, o do boleto; nunca o parcelado.

    Procura, perto do preço lido nos dados da página, um valor com "Pix" ou "boleto" escrito junto.
    Só aceita valores entre 70% e 100% do preço lido (o desconto à vista é pequeno); fora disso, é de
    outro produto da página. Sem rótulo, devolve None e vale o preço lido.
    """
    candidatos = [
        p for p in precos_rotulados(preco_centavos, texto)
        if p.forma in ("pix", "pix_ou_boleto", "boleto") and preco_centavos * 7 <= p.centavos * 10 <= preco_centavos * 10
    ]
    for formas in (("pix", "pix_ou_boleto"), ("boleto",)):
        escolhidos = [p for p in candidatos if p.forma in formas]
        if escolhidos:
            melhor = min(escolhidos, key=lambda p: p.distancia)  # o mais perto: é o bloco de preço do produto
            return EscolhaDoPreco(melhor.centavos, melhor.forma, melhor.trecho)
    return None


def cnpjs_no_texto(texto: str) -> list[str]:
    """CNPJs válidos (numéricos ou alfanuméricos) escritos no texto, sem repetição."""
    encontrados: list[str] = []
    candidatos = _CNPJ_FORMATADO.findall(texto) + _CNPJ_ROTULADO.findall(texto)
    for candidato in candidatos:
        try:
            cnpj = normalizar_cnpj(candidato)
        except ValueError:
            continue
        if cnpj not in encontrados:
            encontrados.append(cnpj)
    return encontrados
