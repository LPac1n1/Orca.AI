"""Leitura de páginas sem rede: produto, vaga, preços visíveis e CNPJs (páginas sintéticas)."""

import json

from orca.coleta import (
    cnpjs_no_texto,
    detectar_bloqueio,
    extrair_produto,
    extrair_vaga,
    objetos_jsonld,
    preco_aparece,
    precos_perto,
    precos_visiveis,
)

EAN = "7891000100103"


def _pagina(*objetos, extra: str = "") -> str:
    blocos = "".join(f'<script type="application/ld+json">{json.dumps(o)}</script>' for o in objetos)
    return f"<html><head>{blocos}</head><body>{extra}</body></html>"


def _produto(**oferta):
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Papel Sulfite A4 75g 500 folhas",
        "brand": {"@type": "Brand", "name": "Chamex"},
        "gtin13": EAN,
        "sku": "123",
        "offers": {"@type": "Offer", "priceCurrency": "BRL", "availability": "https://schema.org/InStock", **oferta},
    }


# --- Produto --------------------------------------------------------------------------


def test_produto_jsonld_completo():
    p = extrair_produto(_pagina(_produto(price="25.29", seller={"@type": "Organization", "name": "Loja X"})))
    assert p.origem == "jsonld"
    assert (p.titulo, p.marca, p.ean, p.sku) == ("Papel Sulfite A4 75g 500 folhas", "Chamex", EAN, "123")
    assert p.preco_centavos == 2529 and p.moeda == "BRL" and p.disponivel is True and p.vendedor == "Loja X"
    assert p.avisos == ()


def test_preco_numerico_no_json_nao_passa_por_float():
    html = '<script type="application/ld+json">{"@type":"Product","name":"X","offers":{"price":0.1}}</script>'
    assert extrair_produto(html).preco_centavos == 10  # 0.1 em float daria 10.000000000000002


def test_graph_lista_e_tipo_com_url():
    grafo = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, {**_produto(price="9.90"), "@type": ["http://schema.org/Product"]}]}
    assert extrair_produto(_pagina(grafo)).preco_centavos == 990
    assert len(objetos_jsonld(_pagina([{"@type": "A"}, {"@type": "B"}]))) == 2


def test_oferta_agregada_e_especificacao_de_preco():
    agregada = _produto()
    agregada["offers"] = {"@type": "AggregateOffer", "lowPrice": "10.00", "offers": [{"price": "12.00"}, {"price": "10.00"}]}
    p = extrair_produto(_pagina(agregada))
    assert p.preco_centavos == 1200
    assert "mais de uma oferta com preços diferentes" in p.avisos[0]

    so_baixo = _produto()
    so_baixo["offers"] = {"@type": "AggregateOffer", "lowPrice": "10.00"}
    assert extrair_produto(_pagina(so_baixo)).preco_centavos == 1000

    especificacao = _produto()
    especificacao["offers"] = {"priceSpecification": {"price": "7.5"}}
    assert extrair_produto(_pagina(especificacao)).preco_centavos == 750


def test_indisponivel_e_ean_invalido():
    produto = _produto(price="5.00", availability="https://schema.org/OutOfStock")
    produto["gtin13"] = "7891000100104"
    p = extrair_produto(_pagina(produto))
    assert p.disponivel is False and p.ean is None
    assert "código de barras inválido" in p.avisos[0]


def test_json_quebrado_e_ignorado_e_microdados_sao_usados():
    html = (
        '<script type="application/ld+json">{quebrado</script>'
        '<meta itemprop="price" content="1234.50"><span>R$ 1.234,50</span>'
    )
    p = extrair_produto(html)
    assert p.origem == "microdados" and p.preco_centavos == 123450 and p.titulo is None
    assert extrair_produto('<meta property="product:price:amount" content="3.99">').preco_centavos == 399
    assert extrair_produto("<html><body>nada</body></html>") is None


# --- Vaga -------------------------------------------------------------------------------


def _vaga(base_salary):
    return {
        "@type": "JobPosting",
        "title": "Educador Social",
        "hiringOrganization": {"@type": "Organization", "name": "Instituto Y"},
        "datePosted": "2026-09-10",
        "identifier": {"@type": "PropertyValue", "value": "V-99"},
        "jobLocation": {"@type": "Place", "address": {"addressLocality": "São Paulo", "addressRegion": "SP"}},
        "baseSalary": base_salary,
    }


def test_vaga_com_faixa_mensal():
    v = extrair_vaga(_pagina(_vaga({"currency": "BRL", "value": {"minValue": 2500, "maxValue": "3000.00", "unitText": "MONTH"}})))
    assert (v.titulo, v.empresa, v.cidade, v.uf) == ("Educador Social", "Instituto Y", "São Paulo", "SP")
    assert (v.salario_min_centavos, v.salario_max_centavos, v.periodo) == (250000, 300000, "MONTH")
    assert (v.data_publicacao, v.identificador, v.avisos) == ("2026-09-10", "V-99", ())


def test_vaga_por_hora_ou_outra_moeda_gera_aviso():
    v = extrair_vaga(_pagina(_vaga({"currency": "USD", "value": {"value": 20, "unitText": "HOUR"}})))
    assert v.salario_min_centavos == v.salario_max_centavos == 2000
    assert any("outra moeda" in a for a in v.avisos) and any("não é mensal" in a for a in v.avisos)


def test_vaga_sem_salario_e_pagina_sem_vaga():
    v = extrair_vaga(_pagina({k: val for k, val in _vaga(None).items() if k != "baseSalary"}))
    assert v.salario_min_centavos is None and v.salario_max_centavos is None
    assert extrair_vaga(_pagina(_produto(price="1.00"))) is None


# --- Texto visível ------------------------------------------------------------------------


def test_precos_visiveis_no_formato_brasileiro():
    texto = "de R$ 29,89 por R$25,29 · 3x de R$ 8,43 · R$ 1.234,56 · 12,90 sem símbolo · R$ 10,5"
    assert precos_visiveis(texto) == [2989, 2529, 843, 123456]


def test_preco_aparece_com_ou_sem_separador_de_milhar():
    assert preco_aparece(123456, "Total: R$ 1.234,56 à vista")
    assert preco_aparece(123456, "Total: 1234,56")
    assert preco_aparece(2529, "por R$ 25,29")
    assert not preco_aparece(2529, "por R$ 125,29")  # não é pedaço de outro número
    assert not preco_aparece(2529, "por R$ 25,299")
    assert not preco_aparece(2529, "por R$ 25.29")


def test_precos_perto_do_preco_principal():
    descricao = "Descrição: papel alcalino, alvura 99%, ideal para impressoras. " * 10  # ~620 caracteres
    recomendados = " · ".join(["outro produto R$ 9,90"] * 40)
    texto = (
        "Papel A4 R$ 34,50 LEVE MAIS POR MENOS Leve 5 ou + R$ 33,30 cada · Assinatura R$ 31,05 para assinantes "
        + descricao
        + recomendados
    )
    assert precos_perto(3450, texto) == [3105, 3330]
    assert precos_perto(3450, "de R$ 39,90 por R$ 34,50") == [3990]
    assert precos_perto(3450, "sem o preço") == []


def test_cnpjs_formatados_rotulados_e_invalidos():
    texto = (
        "Kalunga S.A. CNPJ 43.283.811/0001-50 · Filial CNPJ: 45543915073650 · "
        "repetido 43.283.811/0001-50 · inválido 43.283.811/0001-51 · telefone 11 4003-1234"
    )
    assert cnpjs_no_texto(texto) == ["43283811000150", "45543915073650"]


def test_detecta_bloqueio():
    assert detectar_bloqueio(403, "https://x", "") == "o site respondeu com o código 403"
    assert "verificação" in detectar_bloqueio(200, "https://x/account-verification", "")
    assert "(CAPTCHA)" in detectar_bloqueio(200, "https://x", "Resolva o CAPTCHA para continuar")
    assert detectar_bloqueio(200, "https://x/produto", "Papel A4 R$ 25,29") is None


def test_preco_zero_nos_dados_da_pagina_e_sem_preco():
    """Ensaio real no Atacadão (24/09/2026): sem CEP, os dados da página trazem preço 0."""
    import json as _json

    from orca.coleta import extrair_produto

    produto = {"@type": "Product", "name": "Papel", "offers": {"price": "0", "priceCurrency": "BRL"}}
    html = f'<script type="application/ld+json">{_json.dumps(produto)}</script>'
    assert extrair_produto(html).preco_centavos is None
