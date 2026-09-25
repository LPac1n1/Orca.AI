"""Captura de páginas com o navegador (Playwright + Microsoft Edge do Windows).

Para cada página: rola até o fim (conteúdo tardio), junta o texto dos quadros
incorporados (iframes) e gera a evidência: PDF com cabeçalho (URL, data e hora de
Brasília, CEP e impressão digital da página salva), imagem da página inteira e MHTML
(a página completa, com os quadros).

Dois modos:
- C1 `capturar`: o sistema abre a página sozinho, sem janela;
- C4 `capturar_assistido`: abre a janela para o usuário (captcha, CEP, bloqueio) e
  captura quando a página fica pronta. O sistema nunca resolve captcha.
"""

import base64
import html as html_lib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import Page, sync_playwright

from orca.evidencias import impressao

BRASILIA = ZoneInfo("America/Sao_Paulo")
_SINAIS_BLOQUEIO = re.compile(
    r"captcha|verifique que você é humano|não sou um robô|access denied|acesso negado|"
    r"account-verification|para continuar, acesse|are you a robot|unusual traffic",
    re.I,
)


class ErroCaptura(RuntimeError):
    pass


@dataclass(frozen=True)
class Captura:
    url_pedida: str
    url_final: str
    capturado_em: datetime  # UTC, com fuso
    titulo: str
    status_http: int | None
    html: str
    html_quadros: tuple[str, ...]
    texto_visivel: str  # página + quadros
    pdf: bytes
    png: bytes
    mhtml: bytes
    cep: str | None
    metodo: str  # C1 = navegador do sistema; C4 = captura assistida pelo usuário
    bloqueio: str | None  # motivo, se o site parece ter bloqueado o acesso automático


def horario_brasilia(momento: datetime) -> str:
    return momento.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M:%S")


def cabecalho_pdf(url: str, momento: datetime, cep: str | None, sha256_pagina: str) -> str:
    cep_texto = f"CEP {cep[:5]}-{cep[5:]}" if cep else "CEP não informado"
    return (
        '<div style="font-size:7px;width:100%;padding:0 8mm;font-family:Arial,sans-serif;">'
        f"<div>Orça.AI — capturado em {horario_brasilia(momento)} (horário de Brasília) · {cep_texto}</div>"
        f'<div style="word-break:break-all;">{html_lib.escape(url)}</div>'
        f"<div>SHA-256 da página salva (MHTML): {sha256_pagina}</div></div>"
    )


_RODAPE = (
    '<div style="font-size:7px;width:100%;text-align:right;padding:0 8mm;font-family:Arial,sans-serif;">'
    'página <span class="pageNumber"></span> de <span class="totalPages"></span></div>'
)
_MARGENS = {"top": "24mm", "bottom": "12mm", "left": "8mm", "right": "8mm"}


_ALTURA = "document.documentElement.scrollHeight"
_NO_FIM = f"window.innerHeight + window.scrollY >= {_ALTURA} - 2"


def _rolar_ate_o_fim(pagina: Page, maximo_telas: int = 40) -> None:
    """Desce uma tela por vez até o fim; no fim, espera um pouco para ver se carregou mais conteúdo."""
    for _ in range(maximo_telas):
        pagina.evaluate("window.scrollBy(0, window.innerHeight)")
        pagina.wait_for_timeout(300)
        if pagina.evaluate(_NO_FIM):
            altura = pagina.evaluate(_ALTURA)
            pagina.wait_for_timeout(500)
            if pagina.evaluate(_ALTURA) == altura:
                break
    try:
        pagina.wait_for_load_state("networkidle", timeout=5000)
    except ErroPlaywright:
        pass
    pagina.evaluate("window.scrollTo(0, 0)")


def detectar_bloqueio(status: int | None, url: str, texto: str) -> str | None:
    if status in (401, 403, 429, 503):
        return f"o site respondeu com o código {status}"
    sinal = _SINAIS_BLOQUEIO.search(url + " " + texto[:3000])
    return f"a página pede verificação ({sinal.group(0)})" if sinal else None


ESCALA_PDF = 0.7  # 70%: a página cabe na folha no formato de computador e o preço aparece (pedido no piloto, 24/09/2026)


def _pdf(pagina: Page, cabecalho: str) -> bytes:
    pagina.emulate_media(media="screen")
    try:
        return pagina.pdf(
            format="A4", print_background=True, display_header_footer=True, scale=ESCALA_PDF,
            header_template=cabecalho, footer_template=_RODAPE, margin=_MARGENS,
        )
    except ErroPlaywright:  # versões antigas só geram PDF sem janela: usa o protocolo do navegador
        cdp = pagina.context.new_cdp_session(pagina)
        resposta = cdp.send("Page.printToPDF", {
            "paperWidth": 8.27, "paperHeight": 11.69, "printBackground": True, "displayHeaderFooter": True,
            "headerTemplate": cabecalho, "footerTemplate": _RODAPE, "scale": ESCALA_PDF,
            "marginTop": 0.95, "marginBottom": 0.48, "marginLeft": 0.32, "marginRight": 0.32,
        })
        return base64.b64decode(resposta["data"])


def _registrar_pagina(pagina: Page, url_pedida: str, status: int | None, cep: str | None, metodo: str) -> Captura:
    _rolar_ate_o_fim(pagina)
    momento = datetime.now(UTC)
    quadros_html, quadros_texto = [], []
    for quadro in pagina.frames[1:]:
        try:
            quadros_html.append(quadro.content())
            quadros_texto.append(quadro.evaluate("document.body ? document.body.innerText : ''"))
        except ErroPlaywright:
            continue
    texto = pagina.evaluate("document.body ? document.body.innerText : ''")
    texto_total = "\n".join([texto, *quadros_texto])
    cdp = pagina.context.new_cdp_session(pagina)
    mhtml = cdp.send("Page.captureSnapshot", {"format": "mhtml"})["data"].encode("utf-8")
    png = pagina.screenshot(full_page=True)
    pdf = _pdf(pagina, cabecalho_pdf(pagina.url, momento, cep, impressao(mhtml)))
    return Captura(
        url_pedida=url_pedida,
        url_final=pagina.url,
        capturado_em=momento,
        titulo=pagina.title(),
        status_http=status,
        html=pagina.content(),
        html_quadros=tuple(quadros_html),
        texto_visivel=texto_total,
        pdf=pdf,
        png=png,
        mhtml=mhtml,
        cep=cep,
        metodo=metodo,
        bloqueio=detectar_bloqueio(status, pagina.url, texto_total) if metodo == "C1" else None,
    )


# Links de produto da página de busca: endereço, título e o texto do "cartão" (onde aparece o preço).
_JS_RESULTADOS = """([padrao, seletor]) => {
    const vistos = new Map();
    const raizes = seletor ? [...document.querySelectorAll(seletor)] : [document];
    const links = raizes.flatMap((r) => [...r.querySelectorAll('a[href]')]);
    for (const a of links) {
        const href = a.href;
        if (!href || !href.startsWith('http') || !href.includes(padrao) || href.includes("'+")) continue;
        const img = a.querySelector('img');
        const titulo = (a.getAttribute('title') || a.innerText || (img && img.alt) || '').trim();
        if (vistos.has(href)) {
            if (!vistos.get(href).titulo && titulo) vistos.get(href).titulo = titulo;
            continue;
        }
        let cartao = a;
        for (let i = 0; i < 6 && cartao.parentElement && !(cartao.innerText || '').includes('R$'); i++) {
            cartao = cartao.parentElement;
        }
        vistos.set(href, {href, titulo, texto: (cartao.innerText || '').slice(0, 600)});
    }
    return [...vistos.values()];
}"""


class Navegador:
    """Use com `with Navegador() as nav: nav.capturar(url)`.

    `sem_janela=False` mostra a janela (necessário para a captura assistida).
    """

    def __init__(self, canal: str = "msedge", sem_janela: bool = True, tempo_limite_ms: int = 45_000):
        self.canal, self.sem_janela, self.tempo_limite_ms = canal, sem_janela, tempo_limite_ms

    def __enter__(self) -> "Navegador":
        self._playwright = sync_playwright().start()
        try:
            self._navegador = self._playwright.chromium.launch(channel=self.canal, headless=self.sem_janela)
        except ErroPlaywright as e:
            self._playwright.stop()
            raise ErroCaptura(f"Não foi possível abrir o navegador ({self.canal}): {e}") from e
        self._contexto = self._navegador.new_context(
            locale="pt-BR", timezone_id="America/Sao_Paulo", viewport={"width": 1366, "height": 900}
        )
        return self

    def __exit__(self, *_erro) -> None:
        self._contexto.close()
        self._navegador.close()
        self._playwright.stop()

    def capturar(self, url: str, cep: str | None = None) -> Captura:
        """C1: abre a página e captura."""
        pagina = self._contexto.new_page()
        try:
            resposta = pagina.goto(url, wait_until="domcontentloaded", timeout=self.tempo_limite_ms)
            try:
                pagina.wait_for_load_state("load", timeout=15_000)
            except ErroPlaywright:
                pass
            return _registrar_pagina(pagina, url, resposta.status if resposta else None, cep, "C1")
        except ErroPlaywright as e:
            raise ErroCaptura(f"Não foi possível capturar {url}: {e}") from e
        finally:
            pagina.close()

    def resultados_de_busca(self, url: str, padrao_produto: str, seletor: str | None = None) -> tuple[int | None, list[dict]]:
        """Fase 2: abre a página de busca da loja e lê os links de produto (com o texto do cartão de cada um).

        `seletor` restringe a leitura à lista de resultados (sem menus nem "sugestões").
        Não gera prova: a prova é a página do produto, capturada depois.
        """
        pagina = self._contexto.new_page()
        try:  # página de busca: limite menor (a loja que não responde é pulada, não trava a busca toda)
            resposta = pagina.goto(url, wait_until="domcontentloaded", timeout=min(self.tempo_limite_ms, 25_000))
            try:
                pagina.wait_for_load_state("networkidle", timeout=10_000)
            except ErroPlaywright:
                pass
            for _ in range(3):  # os resultados podem carregar ao rolar
                pagina.evaluate("window.scrollBy(0, window.innerHeight)")
                pagina.wait_for_timeout(400)
            return (resposta.status if resposta else None), pagina.evaluate(_JS_RESULTADOS, [padrao_produto, seletor])
        except ErroPlaywright as e:
            raise ErroCaptura(f"Não foi possível abrir a busca {url}: {e}") from e
        finally:
            pagina.close()

    def capturar_assistido(
        self,
        url: str,
        pronto: Callable[[Page], bool],
        cep: str | None = None,
        tempo_maximo_s: float = 600,
        intervalo_s: float = 1.0,
    ) -> Captura:
        """C4: abre a página para o usuário agir (captcha, CEP, login não) e captura quando `pronto` for verdadeiro.

        Quem decide que está pronto é `pronto(pagina)` — um sinal da própria página
        (ex.: o comprovante da Receita apareceu) ou o botão "Capturar agora" da interface.
        """
        pagina = self._contexto.new_page()
        try:
            resposta = pagina.goto(url, wait_until="domcontentloaded", timeout=self.tempo_limite_ms)
            limite = time.monotonic() + tempo_maximo_s
            while not _pronto(pronto, pagina):
                if pagina.is_closed():
                    raise ErroCaptura("A janela foi fechada antes da captura.")
                if time.monotonic() > limite:
                    raise ErroCaptura(f"A página não ficou pronta em {tempo_maximo_s:.0f} segundos: {url}")
                pagina.wait_for_timeout(int(intervalo_s * 1000))
            try:
                pagina.wait_for_load_state("load", timeout=15_000)
            except ErroPlaywright:
                pass
            return _registrar_pagina(pagina, url, resposta.status if resposta else None, cep, "C4")
        except ErroPlaywright as e:
            raise ErroCaptura(f"Não foi possível capturar {url}: {e}") from e
        finally:
            pagina.close()


def _pronto(pronto: Callable[[Page], bool], pagina: Page) -> bool:
    try:
        return bool(pronto(pagina))
    except ErroPlaywright:  # a página pode estar no meio de uma navegação
        return False
