"""Saída 1 com busca (D-23; Fase 2, etapa 14): alternativas de outra marca nas lojas do trio (sem rede)."""

import pytest

from orca.busca import Candidato
from orca.busca.alternativas import especificacao_sem_marca, produtos_nas_lojas
from orca.coleta import ler_vocabulario
from orca.correspondencia import Especificacao


@pytest.fixture(scope="module")
def vocabulario():
    return ler_vocabulario()


@pytest.mark.parametrize(("descricao", "marca", "esperada"), [
    ("Café torrado e moído Pilão 500g", "Pilão", "Café torrado e moído 500g"),
    ("Café 3 Corações 500g", "3 Corações", "Café 500g"),
    ("Leite condensado 395g", "Moça", "Leite condensado 395g"),
    ("Papel sulfite A4 75g 500 folhas", "Chamex", "Papel sulfite A4 75g 500 folhas"),
])
def test_item_sem_a_marca(descricao, marca, esperada):
    generico = especificacao_sem_marca(Especificacao(descricao, "x", marca, modelo="Tradicional", ean="7891000100103",
                                                     atributos={"sabor": "tradicional"}))
    assert generico.descricao == esperada
    assert generico.marca is None and generico.modelo is None and generico.ean is None
    assert generico.atributos == {"sabor": "tradicional"}  # a finalidade não muda


def test_alternativas_que_aparecem_nas_tres_lojas(vocabulario):
    item = Especificacao("Leite condensado 395g", "alimento", "Moça")
    candidatos = {
        "g": [Candidato("g/moca", "Leite Condensado Moça 395g", preco_centavos=1100),  # a marca de antes
              Candidato("g/italac", "Leite Condensado Italac 395g", preco_centavos=950),
              Candidato("g/italac-1kg", "Leite Condensado Italac 1kg", preco_centavos=2500),  # outro tamanho
              Candidato("g/pira", "Leite Condensado Piracanjuba 395g", preco_centavos=1080),
              Candidato("g/camp", "Leite Condensado Camponesa 395g", preco_centavos=990)],
        "t": [Candidato("t/pira", "Leite condensado Piracanjuba 395g", preco_centavos=1000),
              Candidato("t/italac", "Leite Condensado ITALAC Lata 395 g", preco_centavos=1000)],
        "l": [Candidato("l/pira", "Leite Condensado Piracanjuba 395 gramas", preco_centavos=990),
              Candidato("l/italac", "Leite condensado Italac 395g")],  # a busca não mostrou o preço
    }
    produtos = {p.titulo: p for p in produtos_nas_lojas(item, "g", candidatos, vocabulario)}
    assert set(produtos) == {"Leite Condensado Italac 395g", "Leite Condensado Piracanjuba 395g",
                             "Leite Condensado Camponesa 395g"}
    italac = produtos["Leite Condensado Italac 395g"]
    assert italac.urls == {"g": "g/italac", "t": "t/italac", "l": "l/italac"}  # nunca a Piracanjuba no lugar
    assert italac.precos == {"g": 950, "t": 1000, "l": None}
    assert produtos["Leite Condensado Piracanjuba 395g"].precos == {"g": 1080, "t": 1000, "l": 990}
    assert produtos["Leite Condensado Camponesa 395g"].urls == {"g": "g/camp"}  # só numa loja


def test_titulo_sem_palavra_que_distinga_nao_e_juntado(vocabulario):
    item = Especificacao("Leite condensado 395g", "alimento", "Moça")
    candidatos = {"g": [Candidato("g/1", "Leite condensado 395g", preco_centavos=900)],
                  "t": [Candidato("t/1", "Leite condensado Italac 395g", preco_centavos=1000)]}
    [produto] = produtos_nas_lojas(item, "g", candidatos, vocabulario)
    assert produto.urls == {"g": "g/1"}  # não dá para saber que é o mesmo produto
