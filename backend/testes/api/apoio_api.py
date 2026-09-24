"""Páginas falsas de lojas e vagas, navegador falso e serviço de CNPJ simulado, para os testes da API."""

import io
import json
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime

import httpx
from pypdf import PdfWriter

from orca.coleta import Captura
from orca.dominio import formatar_cnpj, normalizar_cnpj

COLETA = datetime(2026, 9, 23, 14, 0, tzinfo=UTC)
PAPEL, LEITE = "7891173023001", "7891000100103"
LOJAS = {  # domínio: (CNPJ, preço do papel, preço do leite) — o mesmo cenário dos testes do fluxo
    "kalunga.com.br": ("43283811000150", 3600, 1100),
    "gimba.com.br": ("54651716001150", 3400, 1100),
    "lepok.com.br": ("19576717000104", 3500, 1000),
    "tendaatacado.com.br": ("01157555001186", 3450, 1050),
    "loja-x.com.br": ("45543915073650", 3000, 800),  # o CNPJ não é encontrado nas APIs
}


def cnpj_de_teste(n: int) -> str:
    base = f"{n:08d}0001"
    for dv in range(100):
        try:
            return normalizar_cnpj(f"{base}{dv:02d}")
        except ValueError:
            continue
    raise AssertionError


VAGAS = {  # url: (CNPJ, salário mín., salário máx.)
    "https://www.catho.com.br/vagas/1": (cnpj_de_teste(701), 250_000, 300_000),
    "https://www.catho.com.br/vagas/2": (cnpj_de_teste(702), 260_000, None),
    "https://www.infojobs.com.br/vaga/3": (cnpj_de_teste(703), 270_000, None),
}


def pdf_valido(texto: str) -> bytes:
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    escritor.add_metadata({"/Title": texto})
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def _reais(centavos: int) -> str:
    return f"{centavos // 100},{centavos % 100:02d}"


def pagina_produto(url: str) -> Captura:
    dominio = url.split("/")[2].removeprefix("www.")
    cnpj, preco_papel, preco_leite = LOJAS[dominio]
    ean = url.rstrip("/").split("/")[-1]
    nome, marca, preco = (("Papel Sulfite A4 75g 500 folhas", "Chamex", preco_papel) if ean == PAPEL
                          else ("Leite Condensado 395g", "Moça", preco_leite))
    produto = {"@type": "Product", "name": nome, "brand": marca, "gtin13": ean,
               "offers": {"price": f"{preco // 100}.{preco % 100:02d}", "priceCurrency": "BRL"}}
    html = f'<script type="application/ld+json">{json.dumps(produto)}</script>'
    texto = f"{nome} por R$ {_reais(preco)} · Loja CNPJ {formatar_cnpj(cnpj)}"
    marca_arquivo = url.encode()
    return Captura(url, url, COLETA, nome, 200, html, (), texto, pdf_valido(url), b"PNG-" + marca_arquivo,
                   b"MHTML-" + marca_arquivo, None, "C1", None)


def pagina_vaga(url: str) -> Captura:
    cnpj, smin, smax = VAGAS[url]
    valor = {"minValue": f"{smin // 100}.00", "unitText": "MONTH"}
    if smax:
        valor["maxValue"] = f"{smax // 100}.00"
    vaga = {"@type": "JobPosting", "title": "Educador Social", "datePosted": "2026-09-10",
            "baseSalary": {"currency": "BRL", "value": valor},
            "jobLocation": {"address": {"addressLocality": "São Paulo", "addressRegion": "SP"}}}
    html = f'<script type="application/ld+json">{json.dumps(vaga)}</script>'
    faixa = f"R$ {_reais(smin)}" + (f" a R$ {_reais(smax)}" if smax else "")
    texto = f"Educador Social · {faixa} · Empresa CNPJ {formatar_cnpj(cnpj)}"
    return Captura(url, url, COLETA, "Educador Social", 200, html, (), texto, pdf_valido(url),
                   b"PNG-" + url.encode(), b"MHTML-" + url.encode(), None, "C1", None)


class NavegadorFalso:
    def __init__(self):
        self.pedidas: list[str] = []

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        self.pedidas.append(url)
        return pagina_vaga(url) if url in VAGAS else pagina_produto(url)


def abrir_navegador_falso(navegador: NavegadorFalso):
    @contextmanager
    def abrir():
        yield navegador
    return abrir


def cliente_cnpj() -> httpx.Client:
    """OpenCNPJ simulado: todos ativos, menos a loja X (não encontrada)."""
    def responder(pedido: httpx.Request) -> httpx.Response:
        cnpj = pedido.url.path.rstrip("/").split("/")[-1]
        if cnpj == LOJAS["loja-x.com.br"][0]:
            return httpx.Response(404)
        return httpx.Response(200, json={"razao_social": f"Empresa {cnpj[:8]} Ltda", "situacao_cadastral": "Ativa",
                                         "municipio": "São Paulo", "uf": "SP"})
    return httpx.Client(transport=httpx.MockTransport(responder))


def pdf_com_texto(linhas: list[str]) -> bytes:
    """PDF de uma página com texto de verdade (como o que o navegador imprime), só ASCII."""
    conteudo = "BT /F1 11 Tf 40 800 Td 14 TL " + " ".join(
        "(" + linha.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)") + ") '" for linha in linhas) + " ET"
    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(conteudo)} >>\nstream\n{conteudo}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    saida, posicoes = b"%PDF-1.4\n", []
    for n, objeto in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += f"{n} 0 obj\n{objeto}\nendobj\n".encode("latin-1")
    xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    saida += "".join(f"{p:010d} 00000 n \n" for p in posicoes).encode()
    saida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return saida


class PaginaFalsa:
    def __init__(self, url: str, texto: str = ""):
        self.url, self.texto = url, texto

    def evaluate(self, _script: str) -> str:
        return self.texto


class NavegadorVisivelFalso:
    """A janela visível da captura assistida: o teste faz o papel da pessoa (troca a página, clica)."""

    def __init__(self):
        self.pagina: PaginaFalsa | None = None
        self.abertas: list[str] = []

    def capturar_assistido(self, url: str, pronto, cep: str | None = None, tempo_maximo_s: float = 600) -> Captura:
        self.abertas.append(url)
        self.pagina = PaginaFalsa(url)
        limite = time.monotonic() + 10
        while not pronto(self.pagina):
            if time.monotonic() > limite:
                raise TimeoutError("a página não ficou pronta")
            time.sleep(0.01)
        final = self.pagina.url
        if final in VAGAS:
            return replace(pagina_vaga(final), metodo="C4")
        if final.split("/")[2].removeprefix("www.") in LOJAS:
            return replace(pagina_produto(final), metodo="C4")
        return Captura(url, final, COLETA, "Comprovante", 200, "", (), self.pagina.texto, pdf_valido(final),
                       b"PNG-" + final.encode(), b"MHTML-" + final.encode(), None, "C4", None)
