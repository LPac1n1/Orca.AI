# Conjunto de referência de correspondência

Pares de produtos reais, rotulados, usados para medir o módulo de correspondência (caso T-11, [docs/06](../../../../docs/06-roadmap-e-testes.md)). Critério: **nenhum falso 🟢**; a taxa de 🟡 é medida e registrada.

Situação: **364 pares** (60 `mesmo`, 304 `diferente`), coletados em 23/09/2026.

| Coluna | Significado |
|---|---|
| `categoria` | categoria do item no catálogo `catalogos/atributos.yaml` (vazia = sem categoria) |
| `titulo_a`, `marca_a`, `ean_a` | o produto usado como **item pedido** |
| `titulo_b`, `marca_b`, `ean_b` | o produto encontrado na **página** |
| `rotulo` | `mesmo` ou `diferente` (só pares com rótulo seguro entram aqui) |
| `motivo` | o que decide o rótulo |
| `origem_titulos` | `pagina` = título copiado da loja; `api` = API pública da loja; `endereco` = título lido do endereço da página (minúsculas, sem acentos); `off` = Open Food Facts |

## De onde vieram e como foram rotulados

1. **Pares 1 a 10:** levantamento de lojas ([docs/07](../../../../docs/07-levantamento-lojas.md)), rotulados à mão.
2. **Papel sulfite (2 pares `mesmo`):** Kalunga, Amazon e Atacadão, mesma marca, formato, gramatura e nº de folhas (o Atacadão e a Kalunga têm o mesmo código de barras).
3. **`mesmo` (Atacadão × Open Food Facts):** o mesmo código de barras nas duas fontes, com nomes escritos de outro jeito. O título do Open Food Facts é o nome do produto mais a quantidade, quando o nome não a traz. Ficaram de fora: cadastros claramente errados (um filtro de café com o código de um biscoito), quantidades divergentes (400 g × 500 g) e nomes genéricos demais ("Café", "Tradicional").
4. **`diferente` (mesma marca):** dois produtos do Atacadão com códigos diferentes, em que **cada título tem uma característica que o outro não tem** — tamanho, sabor, tipo, fragrância, cor, medidas. Todos revisados um a um. Ficaram de fora os pares em que um título só omite uma palavra do outro ("Café Pilão Almofada 500g" × "Café Pilão Almofada Tradicional 500g"): a loja tem os dois com códigos diferentes, mas eles podem ser o mesmo café. Também saíram duas edições promocionais do mesmo filtro e um guardanapo "20x22 cm" × "22x20 cm".
5. **`diferente` (outra marca):** o mesmo título com marcas diferentes (ex.: óleo de soja 900 ml de duas marcas).

A ferramenta [`backend/ferramentas/montar_pares_referencia.py`](../../../ferramentas/montar_pares_referencia.py) refaz o conjunto (baixa os dados com poucas consultas e aplica as mesmas regras e exclusões). Refazer em outra data dá outros pares, porque os catálogos das lojas mudam.

## Fontes e licença

- **Atacadão:** API pública de busca da loja (coleta C0 do catálogo), 20 consultas. Só nome, marca, código de barras e categoria.
- **Open Food Facts** (<https://world.openfoodfacts.org>): nomes e quantidades de produtos, © colaboradores do Open Food Facts, base sob licença [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Os 57 nomes usados aqui são um trecho pequeno da base, usado só para teste.

## Resultado (23/09/2026)

| | 🟢 | 🟡 | 🔴 |
|---|---|---|---|
| Diferentes, sem código de barras | **0** | 35 (12%) | 269 (88%) |
| Iguais, sem código de barras | 8 (13%) | 52 (87%) | **0** |
| Iguais, com código de barras | 60 (100%) | 0 | 0 |

Sem código de barras, a maioria dos produtos iguais fica 🟡 porque um dos lados omite alguma coisa (o peso, "tradicional", "a vácuo"): o sistema não tem como confirmar sozinho, e uma pessoa confere. Faltam, principalmente, pares `mesmo` de papelaria e limpeza sem código de barras.
