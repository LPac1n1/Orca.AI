"""Situação cadastral por APIs gratuitas: respostas simuladas (sem rede) e um teste real opcional."""

import os

import httpx
import pytest

from orca.coleta import ErroCnpj, consultar_cnpj

CNPJ = "43283811000150"  # Kalunga

OPENCNPJ = {
    "cnpj": CNPJ,
    "razao_social": "KALUNGA S.A.",
    "nome_fantasia": "KALUNGA",
    "situacao_cadastral": "Ativa",
    "data_situacao_cadastral": "2005-11-03",
    "matriz_filial": "Matriz",
    "natureza_juridica": "Sociedade Anônima Fechada",
    "cnae_principal": "4761003",
    "uf": "SP",
    "municipio": "São Paulo",
    "email": "contato@exemplo.com",
    "telefones": [{"ddd": "11", "numero": "40000000"}],
    "QSA": [{"nome_socio": "FULANO"}],
}
BRASILAPI = {
    "cnpj": CNPJ,
    "razao_social": "KALUNGA S.A.",
    "nome_fantasia": "",
    "situacao_cadastral": 8,
    "descricao_situacao_cadastral": "",
    "data_situacao_cadastral": "2020-01-10",
    "identificador_matriz_filial": 1,
    "municipio": "SAO PAULO",
    "uf": "SP",
    "cnae_fiscal": 4761003,
    "qsa": [{"nome_socio": "FULANO"}],
}


def _cliente(respostas: dict[str, httpx.Response]):
    pedidos = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(str(pedido.url))
        for trecho, resposta in respostas.items():
            if trecho in pedido.url.host:
                return resposta
        return httpx.Response(500)

    return httpx.Client(transport=httpx.MockTransport(responder)), pedidos


def test_opencnpj_ativo_sem_dados_pessoais():
    cliente, pedidos = _cliente({"opencnpj": httpx.Response(200, json=OPENCNPJ)})
    d = consultar_cnpj("43.283.811/0001-50", ["opencnpj", "brasilapi"], cliente)
    assert pedidos == [f"https://api.opencnpj.org/{CNPJ}"]
    assert d.ativo and d.situacao == "ATIVA" and d.provedor == "opencnpj"
    assert (d.razao_social, d.municipio, d.uf, d.data_situacao.isoformat()) == ("KALUNGA S.A.", "São Paulo", "SP", "2005-11-03")
    assert set(d.resumo) == {
        "cnpj", "razao_social", "nome_fantasia", "situacao", "data_situacao",
        "municipio", "uf", "cnae_principal", "natureza_juridica", "matriz_filial",
    }
    assert "FULANO" not in str(d.resumo) and "contato@" not in str(d.resumo)  # LGPD


def test_cai_para_o_segundo_provedor_e_le_codigo_numerico():
    cliente, pedidos = _cliente({"opencnpj": httpx.Response(429), "brasilapi": httpx.Response(200, json=BRASILAPI)})
    d = consultar_cnpj(CNPJ, ["opencnpj", "brasilapi"], cliente)
    assert len(pedidos) == 2 and d.provedor == "brasilapi"
    assert d.situacao == "BAIXADA" and not d.ativo
    assert d.nome_fantasia is None and d.resumo["matriz_filial"] == "Matriz"


def test_nenhum_provedor_responde():
    cliente, _ = _cliente({"opencnpj": httpx.Response(404), "brasilapi": httpx.Response(200, text="<html>")})
    with pytest.raises(ErroCnpj, match="Não foi possível validar automaticamente") as erro:
        consultar_cnpj(CNPJ, ["opencnpj", "brasilapi", "outro"], cliente)
    mensagem = str(erro.value)
    assert "CNPJ não encontrado" in mensagem and "resposta inválida" in mensagem and "provedor desconhecido" in mensagem


def test_cnpj_invalido_nem_consulta():
    cliente, pedidos = _cliente({})
    with pytest.raises(ValueError):
        consultar_cnpj("43.283.811/0001-51", ["opencnpj"], cliente)
    assert pedidos == []


@pytest.mark.rede
@pytest.mark.skipif(os.environ.get("ORCA_TESTES_REDE") != "1", reason="acessa a internet (ORCA_TESTES_REDE=1)")
@pytest.mark.parametrize("provedor", ["opencnpj", "brasilapi"])
def test_consulta_real(provedor):
    d = consultar_cnpj(CNPJ, [provedor])
    assert d.cnpj == CNPJ and d.razao_social and d.situacao
