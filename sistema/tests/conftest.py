"""Nos testes, o sistema não dispara as rotinas automáticas ao abrir (base da Receita, coleta diária de vagas)."""
import os

import pytest

os.environ['ORCAMENTO_SEM_ROTINAS'] = '1'


@pytest.fixture(autouse=True)
def _pasta_dos_comprovantes(tmp_path, monkeypatch):
    """Nos testes, a pasta dos comprovantes da Receita ("Orça.AI", em Documentos) é uma pasta temporária: nada é lido nem criado na pasta de verdade."""
    pasta = tmp_path / 'Documentos' / 'Orça.AI'
    pasta.mkdir(parents=True)
    monkeypatch.setenv('ORCAMENTO_COMPROVANTES', str(pasta))

@pytest.fixture(autouse=True)
def _pdf_das_planilhas_sem_navegador(request, monkeypatch):
    """O PDF das planilhas é impresso pelo navegador do sistema (vários segundos, e nem todo computador de teste o tem). Nos testes, um PDF de
    uma página no lugar — menos no teste marcado com `navegador`, que confere a impressão de verdade."""
    if 'navegador' in request.keywords:
        return
    import pymupdf
    from orcamento import pacote_pdf

    def falso(wb):
        d = pymupdf.open(); d.new_page().insert_text((40, 60), 'PLANILHAS: ' + ', '.join(wb.sheetnames))
        return d.tobytes()
    monkeypatch.setattr(pacote_pdf, 'pdf_da_planilha', falso)


@pytest.fixture(autouse=True)
def _fotos_sem_internet(request, monkeypatch):
    """A conferência por IA leva as fotos dos produtos (lidas das lojas). Nos testes, nenhuma foto é buscada na internet — o teste que
    confere as fotos põe as suas no lugar."""
    from orcamento import ia
    monkeypatch.setattr(ia, 'foto_da_pagina', lambda url: None)
    monkeypatch.setattr(ia, 'baixar_foto', lambda url: None)


def formularios_soltos(html):
    """O que está errado nos formulários de uma página: (1) <form> aberto DENTRO de outro — o navegador ignora a abertura do de dentro, e o
    </form> dele fecha o de fora antes da hora; (2) botão de enviar que ficou fora de qualquer formulário (sem o atributo form) — clicar nele não
    faz nada. Devolve a lista dos problemas (vazia = página certa)."""
    from html.parser import HTMLParser

    class Leitor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.abertos, self.problemas, self.botao = [], [], None

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == 'form':
                quem = a.get('id') or a.get('action') or '?'
                if self.abertos:
                    self.problemas.append(f'<form {quem}> dentro de <form {self.abertos[-1]}>')
                self.abertos.append(quem)
            elif tag == 'button' and a.get('type', 'submit') == 'submit' and not self.abertos and 'form' not in a and 'data-sem-formulario' not in a:
                self.botao = ''

        def handle_data(self, data):
            if self.botao is not None:
                self.botao += data

        def handle_endtag(self, tag):
            if tag == 'form' and self.abertos:
                self.abertos.pop()
            elif tag == 'button' and self.botao is not None:
                self.problemas.append('botão de enviar fora de formulário: "' + ' '.join(self.botao.split())[:50] + '"')
                self.botao = None
    leitor = Leitor()
    leitor.feed(html)
    return leitor.problemas


@pytest.fixture(autouse=True)
def _formularios_inteiros(monkeypatch):
    """Toda página que um teste abre é conferida: nenhum formulário dentro de outro, nenhum botão de enviar solto. Em 10/10/2026 os botões
    "Salvar e continuar aqui" e "Salvar e voltar para…" deixaram de funcionar nos cargos com vagas de outro título: o quadro "Títulos com vagas"
    tinha um <form> dentro do formulário do cargo, que fechava o de fora — e tudo que vinha depois (pesquisas e botões de salvar) ficava solto."""
    from starlette.testclient import TestClient
    original = TestClient.request

    def conferido(self, method, url, *a, **k):
        r = original(self, method, url, *a, **k)
        if r.status_code == 200 and 'text/html' in r.headers.get('content-type', ''):
            problemas = formularios_soltos(r.text)
            assert not problemas, f'{method} {url}: ' + '; '.join(problemas[:5])
        return r
    monkeypatch.setattr(TestClient, 'request', conferido)


@pytest.fixture(autouse=True)
def _na_tomada(monkeypatch):
    """As tarefas longas avisam quando o notebook está fora da tomada. Nos testes o computador está sempre "na tomada": o resultado não pode
    depender de onde a suíte roda (em 09/10/2026 dois testes falharam só porque o notebook estava na bateria). O teste do aviso põe o dele."""
    from orcamento import tarefas
    monkeypatch.setattr(tarefas, 'na_bateria', lambda: None)


PT8 = os.path.join(os.path.dirname(__file__), '..', '..', 'fase0', 'sejc', 'pt8_dados.json')


def registrar_exemplo(appmod):
    """Rota SÓ DOS TESTES: carrega o caso real do Parecer Técnico 8 (regressão). No sistema em uso essa rota não existe: o sistema não
    traz dados de nenhuma OSC (decisão de 02/10/2026)."""
    from fastapi.responses import RedirectResponse
    from orcamento import db
    from orcamento.importar_pt8 import carregar

    @appmod.app.post('/exemplo')
    def exemplo():
        pid = db.criar(carregar(PT8), motivo='importado do Parecer Técnico 8 (plano enviado à SEJC)')
        return RedirectResponse(f'/p/{pid}', status_code=303)
