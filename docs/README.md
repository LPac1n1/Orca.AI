# Orca.AI — Especificação

**Situação:** Fase 0 (especificação). Nada foi implementado ainda.
**Última atualização:** 22/09/2026

## O que é

Um sistema gratuito e de código aberto que monta orçamentos de projetos sociais (termos de fomento, colaboração, emendas parlamentares) com o máximo de automação possível, sem abrir mão de uma regra: **todo valor precisa ser comprovável perante a secretaria**.

O sistema pesquisa produtos e vagas, confere se os produtos são idênticos, valida CNPJs, monta as cotações e os três orçamentos comparativos, calcula as médias, fecha o orçamento final exatamente no teto do projeto e gera o pacote de evidências.

Ele é **genérico**: serve para qualquer OSC, secretaria ou edital. As diferenças entre eles ficam nos **perfis de regras**, nunca no código.

## Documentos

| Arquivo | Conteúdo |
|---|---|
| [01-decisoes.md](01-decisoes.md) | Registro de todas as decisões tomadas, com a origem de cada uma |
| [02-especificacao-funcional.md](02-especificacao-funcional.md) | O que o sistema faz, etapa por etapa, e as regras de negócio |
| [03-modelo-matematico.md](03-modelo-matematico.md) | Arredondamento, cálculo de mão de obra e a otimização que fecha o teto exato |
| [04-arquitetura-e-dados.md](04-arquitetura-e-dados.md) | Tecnologias, módulos, estrutura de dados e coletores |
| [05-regras-padrao.md](05-regras-padrao.md) | Perfil de regras padrão, tabela de jornadas por cargo e níveis de automação |
| [06-roadmap-e-testes.md](06-roadmap-e-testes.md) | Fases de construção, casos de teste e critérios de aceite |
| [07-levantamento-lojas.md](07-levantamento-lojas.md) | Como coletar dados de cada loja usada pela OSC, e as perguntas de preço que surgiram |

## Glossário

| Termo | Significado |
|---|---|
| **Projeto** | A proposta de parceria. Tem um **teto** (ex.: valor da emenda), duração em meses e um perfil de regras. |
| **Orçamento** | Uma rubrica do projeto (ex.: Mão de obra, Material pedagógico, Alimentação). Um projeto tem quantos orçamentos precisar. |
| **Lote** | Grupo de itens de um orçamento que é cotado no mesmo trio de fontes. Normalmente um orçamento tem um lote. |
| **Item** | Um produto ou serviço, com especificação exata (marca, modelo, apresentação). |
| **Cargo** | Uma função de mão de obra (ex.: Assistente Social), com um ou mais postos. |
| **Fonte** | De onde vem um preço: loja (identificada pelo CNPJ do vendedor), empresa que anunciou a vaga, fornecedor que enviou proposta, ou fonte pública. |
| **Observação** | Um preço ou salário encontrado numa fonte, num momento, com evidência. Nunca é alterada depois de gravada. |
| **Cotação** | As 3 observações usadas para um item ou cargo, com a média. |
| **Orçamentos comparativos (1, 2 e 3)** | Cada um com todos os itens do lote cotados numa única fonte. O Orçamento 1 é o de menor total. |
| **Orçamento final** | O que vai no plano de aplicação: preços pela regra A ou B e quantidades/horas que fecham o teto exato. |
| **Evidência** | Arquivos que provam uma observação: PDF com print, link, data e hora; imagem; HTML; impressão digital (SHA-256). |
| **Comprovante** | O Comprovante de Inscrição e de Situação Cadastral da Receita Federal de cada empresa usada. |
| **Perfil de regras** | Conjunto de parâmetros (validade, nº de fontes, regra de preço, arredondamento, jornadas etc.) com versão registrada. |

## Princípios invioláveis

1. **Nada é inventado.** Nenhum preço, produto, vaga, CNPJ, URL ou evidência é criado pelo sistema. Sem evidência suficiente, a mensagem é: *"Não foi possível validar automaticamente."*
2. **Todo número é rastreável** até a evidência de origem, a regra aplicada (com versão) e as decisões humanas envolvidas.
3. **A IA propõe, o algoritmo confere e calcula, o humano aprova.** A IA nunca é a origem de um número.
4. **A IA pode rebaixar a confiança, nunca aumentar.** Se a conferência automática encontra conflito, nenhum argumento da IA o desfaz.
5. **Preços encontrados nunca são alterados.** Para mudar um preço, muda-se o produto ou a fonte, com registro.
6. **Nada é apagado.** Toda alteração gera um novo registro; o histórico é completo.
7. **As fontes são escolhidas por critério objetivo e fixo.** O sistema nunca escolhe ou troca uma fonte para aumentar uma média.
8. **Nenhuma substituição é silenciosa.** Toda troca de produto ou fonte é justificada, apresentada e aprovada.
9. **Custo zero.** Nenhuma funcionalidade essencial pode depender de serviço pago.
