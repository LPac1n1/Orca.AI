"""Comprovante de Inscrição e de Situação Cadastral da Receita Federal (D-13, D-14).

A página da Receita tem captcha. Na janela aberta pelo sistema (captura assistida), a
Receita recusa a verificação mesmo resolvida pela pessoa ("Erro ao validar captcha",
piloto, 24/09/2026), e o sistema não se disfarça (D-67). Por isso o caminho padrão é:
a pessoa abre a página no próprio navegador (com o CNPJ já preenchido), resolve a
verificação, salva o comprovante em PDF e envia; o sistema confere o PDF.
"""

import io
import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import Page

from orca.coleta.captura import Captura, Navegador
from orca.dominio import formatar_cnpj, normalizar_cnpj

BRASILIA = ZoneInfo("America/Sao_Paulo")
_EMITIDO = re.compile(r"emitido no dia\s*(\d{2})/(\d{2})/(\d{4})\s*(?:as|a)\s*(\d{2}):(\d{2})(?::(\d{2}))?")
LIMITE_PDF_COMPROVANTE = 5 * 1024 * 1024


class ErroComprovante(ValueError):
    pass


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def ler_comprovante_pdf(pdf: bytes, cnpj: str, agora_: datetime) -> tuple[datetime, tuple[str, ...]]:
    """Confere que o PDF é o comprovante da Receita deste CNPJ e devolve a data de emissão.

    Recusa o arquivo se não for PDF, se não for o comprovante ou se for de outro CNPJ.
    Sem a data de emissão escrita, usa a hora do envio e avisa.
    """
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    cnpj = normalizar_cnpj(cnpj)
    if len(pdf) > LIMITE_PDF_COMPROVANTE:
        raise ErroComprovante("O PDF passa de 5 MB: não parece ser o comprovante da Receita.")
    try:
        texto = "\n".join(pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(pdf)).pages)
    except (PdfReadError, ValueError, OSError) as e:
        raise ErroComprovante("O arquivo não é um PDF válido.") from e
    simples = _sem_acento(texto)
    if "comprovante de inscricao e de situacao cadastral" not in " ".join(simples.split()):
        raise ErroComprovante("O PDF não é o “Comprovante de Inscrição e de Situação Cadastral” da Receita.")
    if formatar_cnpj(cnpj) not in " ".join(texto.upper().split()):
        raise ErroComprovante(f"O comprovante não é do CNPJ {formatar_cnpj(cnpj)}.")
    avisos = []
    achado = _EMITIDO.search(" ".join(simples.split()))
    if achado:
        d, m, a, h, mi, se = achado.groups()
        emitido = datetime(int(a), int(m), int(d), int(h), int(mi), int(se or 0), tzinfo=BRASILIA)
        if emitido > agora_ + timedelta(hours=1):
            raise ErroComprovante("A data de emissão do comprovante está no futuro.")
    else:
        emitido = agora_
        avisos.append("a data de emissão não aparece no PDF: vale a data do envio")
    if "receita.fazenda.gov.br" not in simples:
        avisos.append("o endereço da Receita não aparece no PDF: salve com cabeçalho e rodapé do navegador ligados")
    return emitido, tuple(avisos)

URL_SOLICITACAO = (
    "https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpjreva_Solicitacao.asp?cnpj={cnpj}"
)


def url_do_comprovante(cnpj: str) -> str:
    return URL_SOLICITACAO.format(cnpj=normalizar_cnpj(cnpj))


def comprovante_na_tela(url: str, texto: str, cnpj: str) -> bool:
    """O comprovante do CNPJ está na tela (e não mais a página de solicitação, que tem o mesmo título)."""
    if "solicitacao" in url.lower():
        return False
    texto = texto.upper()
    return formatar_cnpj(cnpj) in texto and "SITUAÇÃO CADASTRAL" in texto and "NÚMERO DE INSCRIÇÃO" in texto


def emitir_comprovante(navegador: Navegador, cnpj: str, tempo_maximo_s: float = 600) -> Captura:
    """Abre a Receita com o CNPJ preenchido e captura o comprovante quando o usuário concluir."""
    cnpj = normalizar_cnpj(cnpj)

    def pronto(pagina: Page) -> bool:
        return comprovante_na_tela(pagina.url, pagina.evaluate("document.body ? document.body.innerText : ''"), cnpj)

    return navegador.capturar_assistido(url_do_comprovante(cnpj), pronto, tempo_maximo_s=tempo_maximo_s)
