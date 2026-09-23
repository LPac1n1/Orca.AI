"""Comprovante de Inscrição e de Situação Cadastral da Receita Federal (D-13, D-14).

A página da Receita tem captcha: o sistema abre a janela com o CNPJ já preenchido,
o usuário resolve o captcha e clica em "Consultar", e o sistema captura o
comprovante sozinho assim que ele aparece (captura assistida, C4).
"""

from playwright.sync_api import Page

from orca.coleta.captura import Captura, Navegador
from orca.dominio import formatar_cnpj, normalizar_cnpj

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
