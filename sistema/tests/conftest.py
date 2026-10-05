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
