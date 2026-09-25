"""Busca automática (Fase 2, etapa 10; D-68): lojas, escolha dos candidatos e leitura das respostas."""

import json

import httpx

from orca.busca import (
    Candidato,
    Consulta,
    avaliar_candidatos,
    buscar_vtex,
    candidatos_da_pagina,
    lojas_de_busca,
    ordem_dos_itens,
    termo_de_busca,
    titulo_do_endereco,
)
from orca.coleta import ler_atributos_dados, ler_catalogo_dados
from orca.correspondencia import Especificacao, Vocabulario

VOCABULARIO = Vocabulario.de_dados(ler_atributos_dados())
PAPEL = Especificacao("Papel sulfite A4 75g 500 folhas", "papel", "Chamex")


def test_lojas_com_busca_no_catalogo():
    lojas = {l.id: l for l in lojas_de_busca(ler_catalogo_dados())}
    assert lojas["atacadao"].modo == "api_vtex" and lojas["kalunga"].modo == "pagina"
    assert lojas["extra_mercado"].modo == "assistida" and not lojas["extra_mercado"].automatica
    assert "carrefour_mercado" not in lojas  # recusa até a janela: só o PDF do navegador da pessoa
    assert lojas["kalunga"].endereco("papel a4") == "https://www.kalunga.com.br/busca/1?q=papel%20a4"
    assert lojas["kalunga"].atende({"papel", "caneta"}) and not lojas["tenda_atacado"].atende({"papel"})
    assert "mercado_livre" not in lojas  # exige login: só colando o link


def test_escolhe_o_candidato_mais_parecido_e_nunca_o_outro_produto():
    candidatos = [
        Candidato("https://loja/a", "Papel Sulfite A4 75g 300 folhas Chamex"),     # outro produto (300 folhas)
        Candidato("https://loja/b", "Papel Sulfite A4 Report 75g 500 folhas", marca="Report"),  # outra marca
        Candidato("https://loja/c", "Resma de papel A4"),                           # 🟡: pouca informação
        Candidato("https://loja/d", "Papel Sulfite A4 75g 500 folhas Chamex", marca="Chamex"),
    ]
    avaliados = avaliar_candidatos(PAPEL, candidatos, VOCABULARIO)
    assert avaliados[0].candidato.url == "https://loja/d"
    assert {a.candidato.url for a in avaliados} <= {"https://loja/c", "https://loja/d"}


def test_titulo_pelo_endereco_quando_o_cartao_nao_tem_texto():
    url = "https://www.kalunga.com.br/prod/papel-sulfite-a4-75g-210mmx297mm-chamex-pt-500-fl/476102"
    assert titulo_do_endereco(url) == "papel sulfite a4 75g 210mmx297mm chamex pt 500 fl"
    avaliados = avaliar_candidatos(PAPEL, [Candidato(url, "")], VOCABULARIO)
    assert avaliados and avaliados[0].status in ("verde", "amarelo")


def test_termo_e_ordem():
    assert termo_de_busca(Especificacao("Café 500g", "alimento", "Café Pilão")) == "Café 500g Pilão"
    assert ordem_dos_itens([("a", True), ("b", False), ("c", False)], {"b": 2}) == ["c", "a", "b"]


def test_cartoes_da_pagina_de_busca():
    candidatos = candidatos_da_pagina([
        {"href": "https://loja/p/1", "titulo": "  Papel Chamex   A4 ", "texto": "Papel Chamex A4 R$ 28,90 no Pix"},
        {"href": "https://loja/p/2", "titulo": "", "texto": "sem preço"},
    ])
    assert candidatos[0].titulo == "Papel Chamex A4"
    assert candidatos[0].preco_centavos == 2890 and candidatos[1].preco_centavos is None


def test_api_vtex_por_codigo_de_barras_e_por_texto():
    pedidos = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(dict(pedido.url.params))
        produto = {"productName": "Papel Sulfite Chamex A4 75g 500 folhas", "brand": "Chamex",
                   "link": "https://secure.atacadao.com.br/papel-sulfite-chamex-a4-75g-4901/p",
                   "items": [{"ean": "7891173023001", "sellers": [{"commertialOffer": {"Price": 31.9}}]}]}
        return httpx.Response(206, text=json.dumps([produto]))

    loja = next(l for l in lojas_de_busca(ler_catalogo_dados()) if l.id == "atacadao")
    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        por_ean = buscar_vtex(cliente, loja, Consulta("papel chamex", "7891173023001"))
        buscar_vtex(cliente, loja, Consulta("papel chamex"))
    assert pedidos == [{"fq": "alternateIds_Ean:7891173023001"}, {"ft": "papel chamex"}]
    c = por_ean[0]
    assert c.url == "https://www.atacadao.com.br/papel-sulfite-chamex-a4-75g-4901/p"  # no site da loja
    assert (c.ean, c.marca, c.preco_centavos) == ("7891173023001", "Chamex", 3190)


def test_busca_configurada_pela_osc_e_conferida():
    import pytest

    from orca.fluxo.catalogos import ErroCatalogo, validar_lojas

    base = ler_catalogo_dados()
    validar_lojas(base)  # o catálogo do sistema está certo
    loja = {"id": "papelaria_x", "nome": "Papelaria X", "dominio": "www.papelariax.com.br", "coleta": "C1",
            "busca": {"modo": "pagina", "url": "https://www.papelariax.com.br/busca?q=papel"}}
    with pytest.raises(ErroCatalogo, match="termo") as erro:
        validar_lojas({"lojas": [loja]})
    assert "/produto/" in str(erro.value)  # também falta dizer como são os endereços de produto
    loja["busca"] = {"modo": "pagina", "url": "https://www.papelariax.com.br/busca?q={termo}", "produto": "/p/"}
    validar_lojas({"lojas": [loja]})
    assert lojas_de_busca({"lojas": [loja]})[0].endereco("caneta azul").endswith("q=caneta%20azul")


def test_variacao_com_palavras_a_mais_perde_para_o_produto_comum():
    """Ensaio real na Kalunga (24/09/2026): o reciclado "Eco" vinha antes do Chamex comum."""
    candidatos = [
        Candidato("https://k/eco", "Papel Sulfite Sustentável Reciclado Chamex Eco A4, 75g, 210x297mm, Pacote 500 folhas"),
        Candidato("https://k/comum", "Papel Sulfite A4 75g 210mmx297mm Chamex PT 500 FL"),
    ]
    assert avaliar_candidatos(PAPEL, candidatos, VOCABULARIO)[0].candidato.url == "https://k/comum"


def test_segunda_busca_mais_curta():
    from orca.busca import CandidatoAvaliado, bom_o_bastante, termo_curto

    assert termo_curto(PAPEL) == "Papel sulfite A4 Chamex"
    assert termo_curto(Especificacao("Leite condensado 395g", "alimento", "Moça")) == "Leite condensado Moça"
    fraco = CandidatoAvaliado(Candidato("u", "Papel"), "amarelo", 0.4, ())
    assert not bom_o_bastante([]) and not bom_o_bastante([fraco])
    assert bom_o_bastante([CandidatoAvaliado(Candidato("u", "Papel"), "verde", 0.1, ())])
