"""Armazém de arquivos (impressão digital, somente leitura, integridade) e validade (D-12, D-14)."""

import os
import stat
from datetime import UTC, date, datetime

import pytest

from orca.evidencias import (
    ArmazemArquivos,
    ErroIntegridade,
    SituacaoValidade,
    comprovante_reaproveitavel,
    dia_em_brasilia,
    impressao,
    validade,
)

# --- Armazém ------------------------------------------------------------------------


def test_guarda_pelo_conteudo_e_le_conferindo(tmp_path):
    armazem = ArmazemArquivos(tmp_path)
    g = armazem.guardar(b"%PDF-1.7 teste", "application/pdf")
    assert g.sha256 == impressao(b"%PDF-1.7 teste")
    assert g.caminho == f"evidencias/{g.sha256[:2]}/{g.sha256[2:4]}/{g.sha256}.pdf"
    assert g.tamanho == len(b"%PDF-1.7 teste")
    assert armazem.ler(g.caminho) == b"%PDF-1.7 teste"
    assert not os.access(tmp_path / g.caminho, os.W_OK)  # somente leitura


def test_mesmo_conteudo_nao_duplica(tmp_path):
    armazem = ArmazemArquivos(tmp_path)
    a = armazem.guardar(b"<html>x</html>", "text/html")
    b = armazem.guardar(b"<html>x</html>", "text/html")
    assert a == b
    assert len(list((tmp_path / "evidencias").rglob("*.html"))) == 1


def test_detecta_arquivo_alterado(tmp_path):
    armazem = ArmazemArquivos(tmp_path)
    g = armazem.guardar(b"original", "application/json")
    caminho = tmp_path / g.caminho
    caminho.chmod(stat.S_IWRITE | stat.S_IREAD)
    caminho.write_bytes(b"adulterado")
    with pytest.raises(ErroIntegridade, match="alterado"):
        armazem.ler(g.caminho)
    with pytest.raises(ErroIntegridade, match="alterado"):
        armazem.guardar(b"original", "application/json")


def test_recusa_tipo_desconhecido(tmp_path):
    with pytest.raises(ValueError, match="não aceito"):
        ArmazemArquivos(tmp_path).guardar(b"x", "application/x-msdownload")


# --- Validade -----------------------------------------------------------------------

# 23/09/2026 às 02:30 UTC ainda é 22/09 em Brasília (UTC−3).
COLETA = datetime(2026, 9, 23, 2, 30, tzinfo=UTC)


def test_dia_da_coleta_e_o_de_brasilia():
    assert dia_em_brasilia(COLETA) == date(2026, 9, 22)
    with pytest.raises(ValueError, match="fuso"):
        dia_em_brasilia(datetime(2026, 9, 23))


def test_180_dias_contando_o_dia_da_coleta():
    v = validade(COLETA, date(2026, 9, 22), 180, 30)
    assert v.valida_ate == date(2027, 3, 20)  # 22/09/2026 + 179 dias
    assert v.dias_restantes == 179 and v.situacao is SituacaoValidade.VALIDA
    assert validade(COLETA, date(2027, 3, 20), 180, 30).situacao is SituacaoValidade.VENCE_EM_BREVE
    assert validade(COLETA, date(2027, 3, 21), 180, 30).situacao is SituacaoValidade.VENCIDA


def test_aviso_antecipado():
    assert validade(COLETA, date(2027, 2, 18), 180, 30).situacao is SituacaoValidade.VALIDA  # faltam 30
    assert validade(COLETA, date(2027, 2, 19), 180, 30).situacao is SituacaoValidade.VENCE_EM_BREVE  # faltam 29


def test_vence_antes_da_entrega_tem_prioridade_sobre_em_breve():
    v = validade(COLETA, date(2026, 10, 1), 180, 30, data_entrega=date(2027, 3, 21))
    assert v.situacao is SituacaoValidade.VENCE_ANTES_DA_ENTREGA
    assert validade(COLETA, date(2026, 10, 1), 180, 30, date(2027, 3, 20)).situacao is SituacaoValidade.VALIDA


def test_comprovante_reaproveitado_por_30_dias():
    emitido = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)
    assert comprovante_reaproveitavel(emitido, date(2026, 9, 1), 30)
    assert comprovante_reaproveitavel(emitido, date(2026, 9, 30), 30)
    assert not comprovante_reaproveitavel(emitido, date(2026, 10, 1), 30)
    assert not comprovante_reaproveitavel(emitido, date(2026, 8, 31), 30)  # emitido "no futuro"
