"""T-11: conjunto de referência de correspondência (pares reais rotulados).

Critério da especificação: nenhum falso 🟢; taxa de 🟡 medida e registrada
(docs/06 §3). Os limites abaixo também protegem contra regressões: se uma mudança
no vocabulário criar um 🔴 errado entre produtos iguais, ou baixar muito a
detecção de produtos diferentes, o teste acusa.
"""

import csv
from collections import Counter
from pathlib import Path

import pytest

from orca.coleta import ler_vocabulario
from orca.correspondencia import Anuncio, Especificacao, comparar

ARQUIVO = Path(__file__).parents[1] / "dados" / "correspondencia" / "pares_referencia.csv"


@pytest.fixture(scope="module")
def pares():
    with ARQUIVO.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def vocabulario():
    return ler_vocabulario()


def _avaliar(pares, vocabulario, com_ean: bool) -> tuple[Counter, list[str]]:
    contagem, falsos_verdes = Counter(), []
    for p in pares:
        item = Especificacao(p["titulo_a"], p["categoria"] or None, p["marca_a"] or None,
                             ean=p["ean_a"] or None if com_ean else None)
        anuncio = Anuncio(p["titulo_b"], p["marca_b"] or None, p["ean_b"] or None if com_ean else None)
        status = comparar(item, anuncio, vocabulario).status.value
        contagem[(p["rotulo"], status)] += 1
        if p["rotulo"] == "diferente" and status == "verde":
            falsos_verdes.append(f"{p['id']}: {p['titulo_a']} × {p['titulo_b']}")
    return contagem, falsos_verdes


def test_conjunto_tem_o_tamanho_da_meta(pares):
    rotulos = Counter(p["rotulo"] for p in pares)
    assert 200 <= len(pares) <= 500  # meta da Fase 0 (docs/06)
    assert rotulos["mesmo"] >= 50 and rotulos["diferente"] >= 150
    assert len({p["id"] for p in pares}) == len(pares)


@pytest.mark.parametrize("com_ean", [False, True], ids=["sem_codigo_de_barras", "com_codigo_de_barras"])
def test_t11_nenhum_falso_verde(pares, vocabulario, com_ean):
    contagem, falsos_verdes = _avaliar(pares, vocabulario, com_ean)
    assert falsos_verdes == []
    diferentes = sum(n for (rotulo, _), n in contagem.items() if rotulo == "diferente")
    iguais = sum(n for (rotulo, _), n in contagem.items() if rotulo == "mesmo")
    assert contagem[("mesmo", "vermelho")] == 0  # nenhum produto igual recusado
    assert contagem[("diferente", "vermelho")] / diferentes >= 0.85  # detecção medida: 88% em 23/09/2026
    if com_ean:
        com_codigo_igual = sum(1 for p in pares if p["rotulo"] == "mesmo" and p["ean_a"] and p["ean_a"] == p["ean_b"])
        assert contagem[("mesmo", "verde")] >= com_codigo_igual
    print(f"\nT-11 ({'com' if com_ean else 'sem'} código de barras): {iguais} iguais, {diferentes} diferentes: {dict(contagem)}")


def test_o_mesmo_texto_e_sempre_verde(pares, vocabulario):
    """Reflexividade: a página com o mesmo título e marca do item é 🟢."""
    for p in pares:
        if not p["marca_a"] or not p["categoria"]:
            continue
        item = Especificacao(p["titulo_a"], p["categoria"], p["marca_a"])
        resultado = comparar(item, Anuncio(p["titulo_a"], p["marca_a"]), vocabulario)
        assert resultado.status.value == "verde", (p["titulo_a"], resultado.motivos)
