"""Captura real com o Microsoft Edge, numa loja sintética servida no próprio computador (sem internet).

Confere: rolagem até o fim (conteúdo tardio), quadros incorporados (iframe preguiçoso),
PDF com cabeçalho (data e hora de Brasília, URL, impressão digital do MHTML), imagem,
MHTML, detecção de bloqueio e captura assistida.
"""

import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pypdf import PdfReader

from orca.coleta import ErroCaptura, Navegador, comprovante_na_tela, extrair_produto, preco_aparece
from orca.evidencias import impressao

pytestmark = pytest.mark.navegador

PRODUTO = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Papel A4 — Loja Teste</title>
<script type="application/ld+json">{"@type":"Product","name":"Papel Sulfite A4","gtin13":"7891000100103",
"offers":{"price":"25.29","priceCurrency":"BRL"}}</script></head>
<body><h1>Papel Sulfite A4</h1><p>por R$ 25,29</p>
<div style="height:3000px">…</div>
<iframe loading="lazy" src="/quadro" width="600" height="120"></iframe>
<script>
window.addEventListener("scroll", () => {
  if (!document.getElementById("tardio") && innerHeight + scrollY >= document.body.scrollHeight - 50) {
    const p = document.createElement("p"); p.id = "tardio"; p.textContent = "Conteúdo tardio: frete à parte";
    document.body.appendChild(p);
  }
});
</script></body></html>"""

QUADRO = "<html><body><p>Loja Teste Ltda — CNPJ 43.283.811/0001-50</p></body></html>"

SOLICITACAO = """<html><head><meta charset="utf-8"><title>Solicitação</title></head><body>
<p>COMPROVANTE DE INSCRIÇÃO E DE SITUAÇÃO CADASTRAL</p><p>CNPJ: 43.283.811/0001-50</p>
<script>setTimeout(() => location.href = "/Cnpjreva_Comprovante.asp", 1500)</script></body></html>"""

COMPROVANTE = """<html><head><meta charset="utf-8"><title>Comprovante</title></head><body>
<p>COMPROVANTE DE INSCRIÇÃO E DE SITUAÇÃO CADASTRAL</p>
<p>NÚMERO DE INSCRIÇÃO 43.283.811/0001-50 MATRIZ</p><p>SITUAÇÃO CADASTRAL ATIVA</p></body></html>"""

PAGINAS = {
    "/produto": (200, PRODUTO),
    "/quadro": (200, QUADRO),
    "/bloqueado": (403, "<html><body>Acesso negado</body></html>"),
    "/Cnpjreva_Solicitacao.asp": (200, SOLICITACAO),
    "/Cnpjreva_Comprovante.asp": (200, COMPROVANTE),
}


class _Loja(BaseHTTPRequestHandler):
    def do_GET(self):
        status, corpo = PAGINAS.get(self.path.split("?")[0], (404, "não encontrado"))
        dados = corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *_):
        pass


@pytest.fixture(scope="module")
def loja():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Loja)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()


@pytest.fixture(scope="module")
def navegador():
    try:
        with Navegador() as nav:
            yield nav
    except ErroCaptura as e:
        pytest.skip(f"Microsoft Edge indisponível: {e}")


def _texto_pdf(pdf: bytes) -> str:
    return "\n".join(pagina.extract_text() for pagina in PdfReader(io.BytesIO(pdf)).pages)


def test_captura_completa(loja, navegador):
    c = navegador.capturar(f"{loja}/produto", cep="03977015")
    assert c.status_http == 200 and c.bloqueio is None and c.metodo == "C1"
    assert c.titulo == "Papel A4 — Loja Teste" and c.url_final == f"{loja}/produto"
    assert "Conteúdo tardio" in c.texto_visivel  # rolou até o fim
    assert "43.283.811/0001-50" in c.texto_visivel  # texto do quadro preguiçoso
    assert any("Loja Teste Ltda" in q for q in c.html_quadros)
    assert extrair_produto(c.html).preco_centavos == 2529 and preco_aparece(2529, c.texto_visivel)

    assert c.png.startswith(b"\x89PNG")
    assert b"multipart/related" in c.mhtml[:2000]
    assert c.pdf.startswith(b"%PDF-")
    texto = _texto_pdf(c.pdf)
    assert "capturado em" in texto and "horário de Brasília" in texto and "CEP 03977-015" in texto
    assert impressao(c.mhtml)[:16] in texto
    assert "127.0.0.1" in texto and "R$ 25,29" in texto


def test_bloqueio_e_detectado(loja, navegador):
    c = navegador.capturar(f"{loja}/bloqueado")
    assert c.bloqueio == "o site respondeu com o código 403"


def test_captura_assistida_espera_o_comprovante(loja, navegador):
    """A página de solicitação tem o mesmo título do comprovante: só a página certa é capturada."""
    cnpj = "43283811000150"

    def pronto(pagina):
        return comprovante_na_tela(pagina.url, pagina.evaluate("document.body.innerText"), cnpj)

    c = navegador.capturar_assistido(f"{loja}/Cnpjreva_Solicitacao.asp?cnpj={cnpj}", pronto, tempo_maximo_s=20)
    assert c.metodo == "C4" and c.url_final.endswith("/Cnpjreva_Comprovante.asp")
    assert "SITUAÇÃO CADASTRAL ATIVA" in c.texto_visivel
    assert "NÚMERO DE INSCRIÇÃO" in _texto_pdf(c.pdf)


def test_captura_assistida_desiste_no_tempo_maximo(loja, navegador):
    with pytest.raises(ErroCaptura, match="não ficou pronta"):
        navegador.capturar_assistido(f"{loja}/produto", lambda _p: False, tempo_maximo_s=1, intervalo_s=0.2)
