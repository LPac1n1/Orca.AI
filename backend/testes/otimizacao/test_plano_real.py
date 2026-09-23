"""Caso real completo (T-06 com dados reais): teto de R$ 150.000,00.

Junta seleção (Regra B, loja de menor total por lote), cálculo de mão de obra e otimização.
1. Com os divisores antigos do plano (180/120), o planejado já fecha 150.000,00: nada muda.
2. Com a regra atual (jornada legal × 5), a mão de obra cai; o otimizador ajusta horas e
   quantidades (±20%) e fecha 150.000,00 exatos, mantendo cada loja escolhida como a mais barata.
(Os 14 itens acima da média continuam lá: resolvê-los é tarefa da seleção, não do otimizador.)
"""

from pathlib import Path

import pytest
import yaml

from orca.calculo import calcular_mao_de_obra, centavos_de_texto, centesimos_de_horas
from orca.dominio import normalizar_cnpj
from orca.otimizacao import ProblemaTeto, SolucaoTeto, fechar_teto, linha_de_cargo, linhas_do_lote
from orca.regras import camada_padrao, resolver
from orca.selecao import ItemLote, Loja, Oferta, ParametrosSelecao, analisar_lote

DADOS = Path(__file__).parents[1] / "dados" / "casos"
GRADE = yaml.safe_load((DADOS / "grade_real_2026.yaml").read_text(encoding="utf-8"))
PLANO = yaml.safe_load((DADOS / "plano_real_2026.yaml").read_text(encoding="utf-8"))
REGRAS = resolver([camada_padrao()]).regras


def _materiais():
    linhas, lotes = [], []
    for n, lote in enumerate(GRADE["lotes"]):
        meses = PLANO["meses_por_lote"][lote["nome"]]
        itens = [ItemLote(f"l{n}i{k}", i["nome"], i["qtd"], meses) for k, i in enumerate(lote["itens"])]
        lojas = [
            Loja(
                id=chave,
                nome=GRADE["lojas"][chave]["nome"],
                cnpj=normalizar_cnpj(GRADE["lojas"][chave]["cnpj"]),
                ofertas={it.id: Oferta(centavos_de_texto(b["precos"][pos])) for it, b in zip(itens, lote["itens"])},
            )
            for pos, chave in enumerate(lote["lojas"])
        ]
        analise = analisar_lote(itens, lojas, ParametrosSelecao.de_regras(REGRAS))
        novas, restricao = linhas_do_lote(analise, REGRAS, orcamento=lote["rubrica"], lote=lote["nome"])
        linhas += novas
        lotes.append(restricao)
    return tuple(linhas), tuple(lotes)


def _mao_de_obra(jornada: str):
    linhas = []
    for n, c in enumerate(PLANO["cargos"]):
        calculo = calcular_mao_de_obra(
            [centavos_de_texto(s) for s in c["salarios"]], c[jornada], centesimos_de_horas(c["horas"]), c["meses"], c["postos"]
        )
        linhas.append(linha_de_cargo(f"c{n}", c["nome"], "Recursos Humanos", calculo, REGRAS))
    return tuple(linhas)


def _problema(jornada: str) -> ProblemaTeto:
    materiais, lotes = _materiais()
    return ProblemaTeto(centavos_de_texto(PLANO["teto"]), materiais=materiais, mao_de_obra=_mao_de_obra(jornada), lotes=lotes)


def test_plano_original_ja_fecha_e_nada_muda():
    r = fechar_teto(_problema("jornada_antiga"))
    assert isinstance(r, SolucaoTeto)
    assert r.total_centavos == 15_000_000
    assert r.alteracoes == ()
    assert r.verificacao_ok


@pytest.mark.parametrize("execucao", [1, 2])
def test_com_divisor_legal_fecha_150_mil_exatos(execucao):
    p = _problema("jornada_legal")
    planejado = sum(l.preco_centavos * l.quantidade_planejada * l.meses for l in p.materiais)
    assert planejado > 0
    r = fechar_teto(p, tempo_limite_s=60)
    assert isinstance(r, SolucaoTeto), getattr(r, "mensagem", "")
    assert r.total_centavos == 15_000_000
    assert r.verificacao_ok, r.verificacao  # inclui C3: cada loja escolhida continua a mais barata
    assert r.alteracoes  # a mão de obra caiu; algo precisou subir
    for linha in p.mao_de_obra:  # nenhuma hora acima da margem nem da jornada legal
        assert linha.horas_min_centesimos <= r.horas_centesimos[linha.id] <= linha.horas_max_centesimos
