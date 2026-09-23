# Conjunto de referência de correspondência

Pares de produtos reais, rotulados por uma pessoa, usados para medir o módulo de correspondência (caso T-11, [docs/06](../../../../docs/06-roadmap-e-testes.md)). Meta: 200 a 500 pares, com **nenhum falso 🟢**.

| Coluna | Significado |
|---|---|
| `rotulo` | `mesmo` ou `diferente` (só pares com rótulo certo entram aqui) |
| `motivo` | o que decide o rótulo (EAN, marca, variante, gramatura, apresentação…) |
| `origem_titulos` | `pagina`/`api` = título copiado da loja; `endereco` = título lido do endereço da página (minúsculas, sem acentos) |

Situação: 10 pares iniciais do levantamento de 23/09/2026 ([docs/07](../../../../docs/07-levantamento-lojas.md)). O restante será coletado na etapa 7 da Fase 1, quando o módulo de correspondência for construído. Faltam, principalmente, pares `mesmo` sem EAN.
