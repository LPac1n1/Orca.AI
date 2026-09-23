"""Gravação das execuções do otimizador: entradas, resultado, linhas finais e imutabilidade."""

import pytest
from sqlalchemy import select

from orca.auditoria import ErroAuditoria, historico_do_projeto
from orca.banco import ExecucaoOtimizacao, LinhaFinal, Projeto, perfil_do_projeto, registrar_execucao, sessao_como
from orca.otimizacao import LinhaMaoDeObra, LinhaMaterial, ProblemaTeto, fechar_teto

USUARIO = "usuario:Leonardo"


def _problema(teto):
    return ProblemaTeto(
        teto,
        materiais=(LinhaMaterial("a", "Item A", "mat", 1250, 20, 1, 16, 24), LinhaMaterial("c", "Item C", "mat", 2500, 14, 1, 12, 16)),
        mao_de_obra=(LinhaMaoDeObra("h", "Cargo H", "mo", 2273, 9150, 1, 1, 9150, 9150, 22000),),
    )


def test_registra_solucao_com_linhas_finais(fabrica, projeto_id):
    problema = _problema(25_000 + 35_000 + 207_980 + 2_500)  # Item C sobe de 14 para 15
    resultado = fechar_teto(problema)
    with sessao_como(fabrica, USUARIO) as s:
        projeto = s.get(Projeto, projeto_id)
        execucao = registrar_execucao(s, projeto, problema, resultado, perfil_do_projeto(s, projeto).impressao)
        s.flush()
        execucao_id = execucao.id
    with sessao_como(fabrica, USUARIO) as s:
        e = s.get(ExecucaoOtimizacao, execucao_id)
        assert e.status == "otima" and e.verificacao_ok and e.total_centavos == problema.teto_centavos
        assert e.autor == USUARIO and e.versao_otimizador.startswith("ortools-")
        assert e.entradas["teto_centavos"] == problema.teto_centavos
        assert e.resultado["alteracoes"][0]["linha"] == "c"
        linhas = {l.linha_id: l for l in s.scalars(select(LinhaFinal).where(LinhaFinal.execucao_id == execucao_id))}
        assert linhas["c"].quantidade == 15 and linhas["c"].total_centavos == 37_500
        assert linhas["h"].valor_mensal_centavos == 207_980 and linhas["h"].alvo_tipo == "cargo"
        assert sum(l.total_centavos for l in linhas.values()) == problema.teto_centavos
        assert {"execucao_otimizacao", "linha_final"} <= {ev.entidade for ev in historico_do_projeto(s, projeto_id)}


def test_registra_sem_solucao_sem_linhas(fabrica, projeto_id):
    problema = _problema(1_000_000_00)
    resultado = fechar_teto(problema)
    with sessao_como(fabrica, USUARIO) as s:
        execucao = registrar_execucao(s, s.get(Projeto, projeto_id), problema, resultado, "x" * 64)
        s.flush()
        assert execucao.status == "sem_solucao" and not execucao.verificacao_ok
        assert execucao.resultado["motivo"] == "limites"
        assert s.scalars(select(LinhaFinal)).all() == []


def test_execucao_e_imutavel(fabrica, projeto_id):
    problema = _problema(25_000 + 35_000 + 207_980)
    with sessao_como(fabrica, USUARIO) as s:
        execucao = registrar_execucao(s, s.get(Projeto, projeto_id), problema, fechar_teto(problema), "x" * 64)
        s.flush()
        execucao_id = execucao.id
    with pytest.raises(ErroAuditoria, match="imutável"):
        with sessao_como(fabrica, USUARIO) as s:
            s.get(ExecucaoOtimizacao, execucao_id).status = "viavel"
