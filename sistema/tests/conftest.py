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
