# 06 — Roadmap e testes

## 1. Fases

### Fase 0 — Especificação e levantamentos (atual)
- [x] Análise de alternativas e decisões ([01](01-decisoes.md)).
- [x] Especificação funcional, modelo matemático, arquitetura e regras padrão.
- [x] **Tabela de jornadas** revisada e aprovada pelo usuário (23/09/2026).
- [x] **Levantamento inicial das lojas** (12 lojas em 23/09/2026): [07-levantamento-lojas.md](07-levantamento-lojas.md) e `catalogos/lojas.yaml`. Ampliar conforme o uso.
- [x] Perguntas de preço Q1 a Q4 respondidas (D-60 a D-63).
- [x] **Conjunto de referência de correspondência:** 364 pares de produtos reais rotulados (60 mesmo / 304 diferente), em `backend/testes/dados/correspondencia/pares_referencia.csv` — 10 do levantamento, o restante montado na etapa 7 a partir da API pública do Atacadão e do Open Food Facts (como foi feito: `LEIAME.md` na mesma pasta).
- [x] Repositório [LPac1n1/Orca.AI](https://github.com/LPac1n1/Orca.AI) (AGPL-3.0) e `CLAUDE.md` com os princípios do projeto.

### Fase 1 — Núcleo mínimo: "a URL entra, o dossiê sai"
Objetivo: um orçamento completo e defensável, com coleta **semiautomática** (o usuário cola as URLs).

- Modelo de dados, migrações, eventos só de acréscimo, gatilhos de imutabilidade.
- Perfis de regras com herança e versão.
- Cadastro de projeto, orçamentos, lotes, itens e cargos.
- Coleta por URL: captura (PDF, PNG, HTML, SHA-256), extração por JSON-LD e conferência do preço no HTML.
- CNPJ: DV (inclusive alfanumérico), situação por API gratuita, fila de comprovantes com captura assistida.
- Correspondência por EAN e por atributos (sem IA).
- Cobertura, classificação, trio, Regra A e Regra B, conferência preço × média.
- Resolução do item acima da média (Saídas 1 e 2), com os dados que o usuário fornecer.
- Mão de obra: vagas por URL, faixa → menor valor, duplicidade básica, 3 menores salários, cálculo completo.
- Otimização CP-SAT com teto exato, C1 a C6, diagnóstico e verificação independente.
- Tela de revisão (matriz), painel e alertas.
- Saídas: grade comparativa (Excel com fórmulas), orçamentos em PDF, plano de aplicação e cronogramas (Excel), memória de cálculo, relatório de conformidade, ZIP com manifesto.

**Aceite da Fase 1:** todos os casos de teste T-01 a T-10 passam.

### Fase 2 — Coleta automática
- Conectores C0 (VTEX, JSON-LD) e C1 (busca do site) para as lojas do levantamento.
- Busca pelo item mais raro primeiro; busca por EAN.
- Conectores de vagas (Catho primeiro; depois Indeed, InfoJobs, Vagas.com); Google Jobs pelo plano grátis da SerpApi (opcional).
- Janela de captura assistida (C4), inclusive para LinkedIn; link de loja achado pelo código de barras num buscador (C2, D-67).
- Sugestões automáticas para o vocabulário e o catálogo de atributos a partir das decisões, aprovadas pelo usuário depois do teste de correspondência (D-65).
- IA opcional: extração, atributos, julgamento 🟡, alternativas de produto, enquadramento de cargo.
- Busca automática de alternativas para a Saída 1 e de novas lojas para a Saída 2.
- Alertas de validade com nova pesquisa em um clique.

### Fase 3 — Universal
- Agente de IA com navegador como camada C3 (opcional).
- Leitura de edital → perfil de regras sugerido, com citações.
- Sugestão de quantidades com base histórica.
- Instalador para Windows; atualizações.
- Compartilhamento de perfis de regras e catálogos entre OSCs.
- Versão hospedada (PostgreSQL), se houver interesse e recursos.

## 2. Ordem de construção dentro da Fase 1

1. ✅ `calculo` — dinheiro em centavos, arredondamento comercial, cotações, mão de obra (com testes de propriedade).
2. ✅ `regras` — perfis, herança, versões, origem de cada regra.
3. ✅ `dominio` + banco + auditoria (tabelas, migrações, gatilhos, histórico automático, regras gravadas por versão).
4. ✅ `selecao` — cobertura, classificação, trio, Regra A/B, conferência, resolução (Saídas 1 e 2), escolha das vagas, conferência de grade pronta.
5. ✅ `otimizacao` — modelo CP-SAT, diagnóstico (limites, divisibilidade, conflitos e sugestões), verificação independente, execuções gravadas.
6. ✅ `evidencias` + coleta por URL + CNPJ — captura com o Edge (PDF com cabeçalho, imagem, MHTML, SHA-256), leitura de produto e vaga (JSON-LD), conferência do preço na página, CNPJ do vendedor, situação cadastral (OpenCNPJ, BrasilAPI), comprovante da Receita por captura assistida, fila de comprovantes, validade com alertas, nova pesquisa, vagas repetidas. A janela da captura assistida ganha botões na etapa 9.
7. ✅ `correspondencia` sem IA — cascata EAN → marca → atributos (medidas e vocabulário) → palavras que sobram; decisões gravadas; confirmação humana; nível de automação do perfil.
8. ✅ `documentos` — dossiê único; grade comparativa e plano de aplicação (recursos, aplicação, cronograma físico-financeiro e de desembolso) em Excel com fórmulas vivas conferidas por teste; PDFs (resumo, conformidade, pesquisa, orçamentos 1, 2, 3 e final, grade, cotações com as páginas capturadas e comprovantes, memória de cálculo, histórico); pacote ZIP com manifesto SHA-256. Testado com o caso real (R$ 150.000,00). A montagem do dossiê a partir do banco entra na etapa 9, junto com a ligação das etapas.
9. API e interface, em quatro partes (cada uma com a sua aprovação):
   1. ✅ `fluxo` — liga as etapas a partir do banco: lojas de cada lote (site + CNPJ do vendedor) com as correspondências, CNPJs e validade; seleção com as lojas retiradas pelo usuário (Saída 2) e troca de produto (Saída 1) como decisões; vagas com repetidas e decisões; cálculo da mão de obra pela tabela de jornadas; otimização com margens e travas de cada linha; execução vigente (qualquer mudança a desatualiza); painel, status 🟢🟡🔴 de cada linha e alertas; dossiê a partir do banco.
   2. ✅ API local (FastAPI) e fila de tarefas: cadastro (organizações, projetos, orçamentos, lotes, itens, cargos), coleta de páginas de itens e vagas, consulta de CNPJ, decisões (correspondência, retirar/devolver loja, trocar produto, mesma vaga), matriz de revisão, painel, fechar o teto, exportar, histórico, regras, evidências e pacotes para baixar; comando `orca`.
   3. ✅ Telas principais (React): projetos; painel com alertas e próximos passos; itens e cargos; pesquisa e revisão (colar links, matriz item × lojas com prova, correspondência e decisões, simulação e retirada de loja, vagas e memória de cálculo); fechar o teto; documentos com a conformidade e os pacotes para baixar; histórico; tarefas em andamento.
   4. Telas de captura assistida e comprovantes (D-67), catálogos, vocabulário e pares com o teste de correspondência antes de salvar (D-64 a D-66), e regras.

O núcleo de cálculo e otimização vem primeiro porque é o que torna o orçamento defensável e não depende de como os dados foram coletados.

## 3. Casos de teste

Cada caso tem dados de entrada fixos (observações gravadas, sem acesso à internet) e resultado esperado exato. Casos reais servem só como teste (D-04); nenhum deles define o comportamento do sistema sozinho.

| Código | Cenário | Resultado esperado | Situação |
|---|---|---|---|
| T-01 | **Arredondamento:** valores terminados em ,xx4 / ,xx5 / ,xx6; médias com 1/3 e 2/3 de centavo | `R()` conforme D-21 em todos os casos; nenhum ponto flutuante | ✅ |
| T-02 | **Mão de obra:** 3 salários, divisor 220 e 150, horas com decimais | Valores da sequência D-43 idênticos ao exemplo de [03 §3](03-modelo-matematico.md) | ✅ |
| T-03 | **Regra B com itens acima da média** (caso real: Termo de Fomento SJC-SP, 2026, grade de 3 rubricas de materiais) | O sistema aponta exatamente os 14 itens da diligência e detecta o erro na média unitária do Álcool 1L | ✅ |
| T-04 | **Saída 1:** item acima da média com alternativa válida nas 3 lojas | Alternativa listada; após escolha, conferência ok e loja escolhida continua a de menor total | ✅ |
| T-05 | **Saída 2:** item acima da média; a próxima loja da classificação também tem problema; a seguinte resolve | Cadeia de 2 tentativas registrada; trio final correto; nenhuma loja trocada para subir média | ✅ |
| T-06 | **Teto exato viável** (materiais + mão de obra, projeto com várias rubricas) | Soma igual ao teto ao centavo; C3 e C4 respeitadas; verificação independente ok; mesma saída em execuções repetidas | ✅ |
| T-07 | **Teto inviável por divisibilidade** (itens múltiplos de R$ 2,50, teto terminado em 1,00) | Mensagem de divisibilidade e sugestão da menor mudança | ✅ |
| T-08 | **Teto inviável por limites** | Mensagem com o máximo possível e a diferença | ✅ |
| T-09 | **Vagas:** mesma vaga em 2 plataformas; vaga sem salário; empresa confidencial; faixa salarial | Duplicada conta 1 vez; as outras descartadas com motivo; faixa → menor valor | ✅ |
| T-10 | **Validade:** evidência que vence antes da data de entrega | Alerta gerado; nova pesquisa mantém a antiga no histórico | ✅ |
| T-11 | **Correspondência:** conjunto de referência | 🟢 sem nenhum falso positivo; taxa de 🟡 medida e registrada | ✅ 364 pares, nenhum falso 🟢 e nenhum 🔴 entre produtos iguais. Sem código de barras: diferentes 88% 🔴 e 12% 🟡; iguais 13% 🟢 e 87% 🟡. Com código de barras: iguais 100% 🟢 |
| T-12 | **Marketplace:** vendedor sem CNPJ identificável; dois produtos de vendedores diferentes | Anúncio descartado; orçamento comparativo exige vendedor único | ✅ |
| T-13 | **Regra A** num orçamento e **Regra B** em outro, no mesmo projeto | Cada orçamento com a sua base; teto do projeto exato | ✅ |
| T-14 | **Item bloqueador** (produto em só 2 lojas) | Item e nº de lojas informados; sugestões apresentadas | ✅ |
| T-15 | **CNPJ alfanumérico** e CNPJ não ativo | DV validado; fonte bloqueada quando não ativa | ✅ |

## 4. Critérios gerais de qualidade

- Nenhum número no orçamento sem observação e evidência de origem (checagem automática antes de exportar).
- Verificação independente obrigatória antes de qualquer exportação.
- Núcleo (`calculo`, `selecao`, `otimizacao`, `correspondencia`) com testes cobrindo todas as regras de [01](01-decisoes.md).
- Toda decisão citada no código pelo seu código (ex.: `# D-23`).
