Quero que você atue como um **arquiteto sênior de sistemas de automação baseados em IA**, com especialização simultânea em:

* gestão e administração de OSCs/ONGs;
* elaboração de projetos sociais;
* prestação de contas de recursos públicos;
* emendas parlamentares;
* termos de fomento e colaboração;
* parcerias com governos municipais e estaduais;
* pesquisa e composição de orçamentos;
* pesquisa de preços na internet;
* automação de processos;
* agentes de IA;
* web research;
* web scraping;
* matching semântico de produtos;
* otimização matemática;
* bancos de dados;
* sistemas web;
* no-code e low-code;
* geração e organização de documentos;
* auditoria e rastreabilidade.

## IMPORTANTE

**Não comece construindo o sistema.**

Antes de propor qualquer implementação, faça uma análise profunda de todas as possibilidades tecnológicas existentes para resolver este problema.

Quero que você primeiro descubra:

1. quais partes podem ser automatizadas;
2. quais partes podem ser automatizadas por IA;
3. quais partes precisam de APIs;
4. quais partes precisam de scraping/web research;
5. quais partes exigem programação própria;
6. quais partes podem ser resolvidas por ferramentas no-code/low-code;
7. quais partes exigem intervenção humana;
8. quais arquiteturas seriam possíveis;
9. quais ferramentas existentes podem ser combinadas;
10. quais soluções gratuitas existem;
11. quais soluções pagas existem;
12. quais são as limitações de cada alternativa;
13. qual seria a arquitetura mais robusta;
14. qual seria a arquitetura mais barata;
15. qual seria a arquitetura com maior nível de automação;
16. qual seria a arquitetura mais fácil de manter;
17. e, principalmente, qual combinação mais se aproxima da **solução ideal/perfeita para este problema**.

Não quero que você escolha uma ferramenta previamente.

Primeiro compreenda completamente o problema.

Depois compare as alternativas.

Só então proponha a solução.

---

# 1. OBJETIVO DO SISTEMA

Quero criar uma plataforma web de inteligência e automação para elaboração de orçamentos de projetos sociais.

O sistema deverá ser capaz de receber as informações de um projeto e, utilizando IA e outras tecnologias necessárias, realizar automaticamente o máximo possível do processo de:

* planejamento do orçamento;
* pesquisa de produtos;
* pesquisa de preços;
* pesquisa de vagas;
* identificação de empresas;
* validação de CNPJ;
* comparação de produtos;
* identificação de produtos realmente equivalentes;
* seleção das melhores fontes;
* construção dos três orçamentos comparativos;
* cálculo das médias;
* construção do orçamento final;
* otimização matemática;
* geração de evidências;
* geração de PDFs;
* organização documental;
* auditoria;
* rastreabilidade;
* revisão pelo usuário;
* exportação do orçamento final.

O sistema deverá ser desenvolvido pensando em **diferentes projetos, diferentes secretarias, diferentes editais e diferentes regras**.

Portanto, não deverá existir uma única regra fixa.

Cada orçamento deverá possuir seu próprio conjunto de regras configuráveis.

---

# 2. CONCEITO FUNDAMENTAL

O sistema deverá funcionar como um **motor inteligente de orçamentação**.

Ele deverá ser capaz de:

> pesquisar → identificar → comparar → validar → selecionar → calcular → otimizar → documentar → apresentar para revisão → corrigir → finalizar.

A IA deverá tomar decisões automaticamente quando as regras permitirem.

Quando uma decisão depender de uma escolha administrativa do usuário, deverá solicitar sua intervenção.

Quando houver uma situação que não possa ser resolvida com segurança, deverá sinalizar o problema em vez de inventar uma solução.

---

# 3. ESTRUTURA DO SISTEMA

A estrutura deverá seguir aproximadamente:

**Projeto**
→ pode conter vários **Orçamentos**

Cada **Orçamento** deverá possuir:

* nome;
* descrição;
* rubrica/categoria;
* valor/teto;
* período;
* regras próprias;
* quantidade de fontes a pesquisar;
* fontes escolhidas;
* materiais;
* mão de obra;
* resultados da pesquisa;
* orçamento 1;
* orçamento 2;
* orçamento 3;
* orçamento final;
* evidências;
* histórico;
* auditoria.

O usuário deverá poder:

* criar orçamento;
* editar orçamento;
* duplicar orçamento;
* excluir orçamento;
* alterar regras;
* revisar resultados;
* aprovar itens;
* substituir itens;
* alterar quantidades;
* alterar produtos;
* alterar fontes;
* executar novamente a pesquisa;
* gerar novamente os cálculos;
* gerar novamente os documentos.

Um único projeto poderá conter **quantos orçamentos forem necessários**.

---

# 4. MOTOR DE REGRAS

Cada orçamento deverá possuir um **motor de regras configurável**.

Esse motor será responsável por determinar o comportamento da automação.

As regras poderão definir, por exemplo:

* teto do orçamento;
* número mínimo de fontes;
* número desejado de fontes;
* número obrigatório de fontes;
* quantidade de orçamentos comparativos;
* necessidade de três lojas;
* necessidade de mesma marca;
* necessidade de mesmo modelo;
* necessidade de mesmo produto;
* regras de quantidade;
* regras de arredondamento;
* regras de mão de obra;
* carga horária;
* regras de CNPJ;
* validade das pesquisas;
* necessidade de evidência;
* regras de substituição;
* regras de aprovação;
* regras específicas da secretaria;
* regras específicas do edital.

O motor de regras deverá ser configurável sem precisar reconstruir o sistema.

---

# 5. RUBRICAS

O sistema deverá inicialmente contemplar:

### A. Mão de obra

### B. Material pedagógico e escritório

### C. Alimentação

### D. Limpeza e utensílios

### E. Sistema de gestão de dados

Entretanto, o sistema deverá permitir criar novas rubricas ou alterar as já existentes.

---

# 6. PESQUISA DE LOJAS

Para materiais, o usuário poderá:

### Opção A

Selecionar manualmente as lojas que deseja pesquisar.

### Opção B

Informar uma quantidade X de lojas/fontes que deseja que a automação pesquise.

### Opção C

Não indicar quantidade ou lojas, permitindo que a IA determine uma estratégia de pesquisa adequada às regras daquele orçamento.

O usuário poderá fornecer mais de três lojas.

Por exemplo:

> Pesquisar em 10 lojas.

A IA deverá pesquisar os produtos em todas as fontes possíveis.

Depois deverá identificar quais lojas possuem **todos os produtos necessários**.

Somente as lojas que possuírem todos os produtos poderão participar dos três orçamentos finais.

---

# 7. SELEÇÃO AUTOMÁTICA DAS TRÊS LOJAS

Suponha que o sistema pesquise 10 lojas.

Depois da pesquisa:

* Loja A possui todos os produtos;
* Loja B possui todos;
* Loja C possui todos;
* Loja D possui todos;
* Loja E não possui um produto;
* Loja F não possui dois;
* etc.

As lojas E e F deverão ser descartadas.

Entre A, B, C e D, o sistema deverá selecionar três.

Se houver mais de três lojas que possuam todos os produtos, a IA deverá selecionar as três mais adequadas de acordo com critérios configuráveis.

Por padrão, deverá considerar:

1. disponibilidade de todos os produtos;
2. equivalência dos produtos;
3. validade e confiabilidade da fonte;
4. menor valor total possível considerando todos os produtos;
5. qualidade da evidência;
6. acessibilidade da página;
7. demais regras do orçamento.

O sistema deverá explicar ao usuário por que escolheu aquelas três lojas.

---

# 8. REGRA FUNDAMENTAL: MESMO PRODUTO

Essa é uma das regras mais importantes de todo o sistema.

Os três orçamentos deverão utilizar **exatamente os mesmos produtos**.

Não basta serem produtos semelhantes.

Não basta terem a mesma finalidade.

Não basta terem preços próximos.

O produto deverá ser efetivamente o mesmo.

Diferenças meramente textuais poderão ser ignoradas.

Por exemplo:

> "Papel Sulfite A4 75g Chamex 500 folhas"

e

> "Chamex Papel Sulfite A4 75g - 500 fls"

podem representar o mesmo produto.

Entretanto:

> Chamex A4 75g 500 folhas

e

> Report A4 75g 500 folhas

não deverão ser considerados o mesmo produto se a regra exigir a mesma marca.

Da mesma forma, não deverão ser considerados equivalentes produtos com diferenças relevantes de:

* marca;
* modelo;
* quantidade;
* capacidade;
* tamanho;
* dimensão;
* gramatura;
* voltagem;
* unidade de venda;
* composição;
* especificações técnicas;
* características relevantes.

A IA deverá possuir um mecanismo de **matching de produtos** capaz de analisar:

* título;
* descrição;
* marca;
* modelo;
* especificações;
* embalagem;
* quantidade;
* unidade;
* características técnicas.

O sistema deverá classificar cada correspondência como, por exemplo:

🟢 **Mesmo produto — alta confiança**

🟡 **Possível correspondência — revisão necessária**

🔴 **Produtos diferentes**

A IA nunca deverá considerar produtos diferentes como iguais apenas para conseguir fechar o orçamento.

---

# 9. AUSÊNCIA DE UM PRODUTO EM UMA LOJA

Se uma loja não possuir determinado produto, ela não poderá participar daquele conjunto de três orçamentos.

A automação deverá continuar pesquisando outras lojas.

Se não conseguir encontrar pelo menos três lojas que tenham todos os produtos, deverá:

1. informar o problema;
2. mostrar qual produto está impedindo a formação dos três orçamentos;
3. identificar quantas lojas possuem o produto;
4. sugerir produtos alternativos;
5. explicar quais características tornam a alternativa equivalente;
6. permitir que o usuário aprove a substituição.

Se o usuário autorizar a substituição, o sistema deverá refazer a pesquisa.

---

# 10. QUANTIDADE DOS PRODUTOS

O usuário poderá informar a quantidade necessária de cada material.

Se informar, a IA deverá respeitar essa quantidade, salvo se as regras do orçamento permitirem alteração.

Se o usuário não informar a quantidade, a IA poderá sugerir ou definir uma quantidade com base em:

* número de participantes;
* número de oficinas;
* duração;
* frequência;
* atividades previstas;
* consumo estimado;
* regras do projeto;
* experiência histórica;
* parâmetros fornecidos pelo usuário.

A quantidade utilizada deverá ser apresentada para aprovação.

---

# 11. SUBSTITUIÇÃO DE PRODUTOS

A IA poderá sugerir substituições quando:

* não existirem três lojas com o produto;
* o produto impedir a formação dos três orçamentos;
* o produto tornar matematicamente impossível atingir o teto;
* existir alternativa compatível com as regras.

Entretanto, a substituição deverá ser:

* identificada;
* justificada;
* apresentada ao usuário;
* aprovada quando necessário;
* registrada no histórico.

A IA não deverá substituir silenciosamente um produto.

---

# 12. TRÊS ORÇAMENTOS COMPARATIVOS

Depois de selecionar as três lojas, deverá ser criado:

### Orçamento 1

Todos os produtos utilizando exclusivamente os preços da Loja 1.

### Orçamento 2

Todos os produtos utilizando exclusivamente os preços da Loja 2.

### Orçamento 3

Todos os produtos utilizando exclusivamente os preços da Loja 3.

Não poderá haver mistura de preços.

Exemplo inválido:

Loja 1 para papel + Loja 2 para caneta dentro do mesmo orçamento.

Cada orçamento comparativo deverá representar integralmente uma única fonte.

---

# 13. MÉDIAS

Para cada produto, o sistema deverá calcular:

* preço unitário Loja 1;
* preço unitário Loja 2;
* preço unitário Loja 3;
* média unitária.

Também deverá calcular:

* total Loja 1;
* total Loja 2;
* total Loja 3;
* média dos totais.

Todos os cálculos deverão ser transparentes.

---

# 14. ORÇAMENTO FINAL / QUARTO ORÇAMENTO

O orçamento final será tratado como um **quarto orçamento**.

Ele deverá:

* utilizar os mesmos produtos aprovados;
* respeitar as regras do orçamento;
* possuir preços unitários iguais ou inferiores aos limites estabelecidos;
* respeitar as médias;
* atingir exatamente o teto definido.

O sistema deverá utilizar um algoritmo de otimização para encontrar uma combinação válida.

---

# 15. OTIMIZAÇÃO MATEMÁTICA

Essa parte é essencial.

O sistema não deverá simplesmente somar preços.

Deverá resolver um problema de otimização.

Variáveis que poderão ser consideradas:

* produtos;
* quantidades;
* preços;
* substituições permitidas;
* limites por categoria;
* regras do edital;
* teto;
* médias;
* arredondamentos.

Objetivo:

**encontrar uma composição válida cujo valor final seja exatamente igual ao teto.**

Exemplo:

Teto:

R$ 20.000,00

Resultado obrigatório:

R$ 20.000,00

Não:

R$ 19.999,99

Nem:

R$ 20.000,01.

Caso não exista solução, a IA deverá demonstrar matematicamente por que não existe e sugerir alterações possíveis.

Nunca deverá inventar ou manipular preços.

---

# 16. AUDITORIA HUMANA

Embora o sistema tenha alto nível de automação, o usuário deverá possuir controle completo.

A revisão deverá ser:

* dinâmica;
* rápida;
* visual;
* item por item;
* fácil de entender.

Para cada item, o usuário deverá conseguir visualizar:

### Produto

Nome e descrição.

### Loja 1

Produto + preço + evidência.

### Loja 2

Produto + preço + evidência.

### Loja 3

Produto + preço + evidência.

### Média

Cálculo automático.

### Resultado

Valor utilizado no orçamento final.

### Status

🟢 Aprovado

🟡 Revisão necessária

🔴 Problema

O usuário deverá conseguir aprovar, rejeitar ou solicitar nova pesquisa sem precisar reconstruir o orçamento.

---

# 17. MÃO DE OBRA

A mão de obra seguirá regras próprias.

Cada cargo deverá possuir três pesquisas de vagas.

A mesma vaga da mesma empresa não poderá ser utilizada duas vezes, mesmo que seja encontrada em plataformas diferentes.

Exemplo:

LinkedIn:
Auxiliar de limpeza — Empresa X

InfoJobs:
Auxiliar de limpeza — Empresa X

Se for a mesma vaga, deverá ser considerada apenas uma fonte.

Entretanto, vagas diferentes da mesma plataforma poderão ser utilizadas normalmente.

---

# 18. PESQUISA DE VAGAS

O sistema deverá pesquisar automaticamente cada cargo e trazer 1 orçamento com 3 vagas de cada um em fontes como:

* LinkedIn;
* Indeed;
* InfoJobs;
* Catho;
* sites de empresas;
* plataformas de emprego;
* outras fontes relevantes.

Deverá identificar:

* cargo;
* empresa;
* CNPJ, quando disponível;
* salário;
* localização;
* descrição;
* URL;
* data;
* plataforma;
* identificação da vaga.

Também deverá tentar detectar duplicidades.

---

# 19. CÁLCULO DE MÃO DE OBRA

O sistema deverá calcular a média das três pesquisas.

Para cargos gerais:

180 horas/mês.

Para Assistente Social:

120 horas/mês.

Ele deve identificar automaticamente qual cargo se enquadra em qual modelo de horas mensais, de acordo com as regras definidas por lei.

Depois deverá calcular proporcionalmente as horas do projeto.

Exemplo:

Vaga 1:
R$ 4.001,00

Vaga 2:
R$ 5.000,00

Vaga 3:
R$ 6.001,00

Média:
R$ 5.000,67

Se o projeto utilizar 90 horas:

R$ 5.000,67 / 180 × 90

Cada cargo terá horas trabalhadas separadas. Caso o usuário não defina as horas, o IA pode defini-las, seguindo a função de cada cargo.

O sistema deverá apresentar a fórmula e todos os valores intermediários.

As regras de carga horária deverão ser configuráveis pelo motor de regras.

---

# 20. CNPJ

Para cada empresa utilizada, o sistema deverá:

* identificar CNPJ;
* consultar fonte oficial;
* verificar situação cadastral;
* confirmar atividade/regularidade conforme a regra configurada;
* salvar a evidência;
* relacionar o CNPJ ao item;
* impedir utilização quando a regra exigir CNPJ ativo e ele não estiver ativo.

---

# 21. EVIDÊNCIAS

Cada item deverá possuir sua própria evidência.

Para produtos:

* URL;
* nome da loja;
* produto;
* marca;
* preço;
* data/hora;
* página salva;
* PDF ou captura, quando possível.

Para vagas:

* URL;
* plataforma;
* empresa;
* cargo;
* salário;
* data;
* evidência.

Para empresas:

* CNPJ;
* razão social;
* situação;
* fonte oficial;
* evidência.

---

# 22. PRESERVAÇÃO DAS PÁGINAS

Como páginas podem mudar ou desaparecer, o sistema deverá tentar preservar uma evidência da situação encontrada no momento da pesquisa.

Sempre que tecnicamente possível:

* salvar PDF;
* salvar captura;
* registrar HTML;
* registrar data/hora;
* registrar URL;
* registrar informações essenciais.

O objetivo é permitir que, meses depois, a OSC consiga demonstrar de onde veio aquele valor.

---

# 23. VALIDADE DAS PESQUISAS

Cada pesquisa deverá registrar:

* data;
* horário;
* fonte;
* validade.

O motor de regras deverá permitir definir por quanto tempo uma pesquisa pode ser utilizada.

Se uma pesquisa estiver vencida, o sistema deverá sinalizar e permitir nova pesquisa.

---

# 24. RASTREABILIDADE

Cada valor deverá ser rastreável até sua origem.

Exemplo:

R$ 18,90

↓

Produto X

↓

Loja Y

↓

URL

↓

Data da pesquisa

↓

Página salva

↓

CNPJ da empresa

↓

Preço encontrado

↓

Regra aplicada

↓

Valor utilizado

O usuário deverá conseguir navegar por essa cadeia.

---

# 25. HISTÓRICO

O sistema deverá registrar:

* criação;
* alterações;
* substituições;
* alterações de quantidade;
* alterações de regras;
* alterações de fontes;
* aprovações;
* rejeições;
* novas pesquisas;
* alterações realizadas pela IA;
* alterações realizadas pelo usuário.

A IA não deverá apagar silenciosamente versões anteriores.

---

# 26. PROJETO COM VÁRIOS ORÇAMENTOS

Um projeto poderá conter vários orçamentos.

Exemplo:

Projeto:
"Vozes da Juta"

Orçamentos:

1. Mão de obra
2. Material pedagógico
3. Alimentação
4. Limpeza
5. Sistema de gestão
6. Evento final

O usuário deverá conseguir:

* criar;
* duplicar;
* editar;
* renomear;
* arquivar;
* excluir;
* recalcular;

cada orçamento independentemente.

As regras poderão ser diferentes entre eles.

---

# 27. INTELIGÊNCIA ARTIFICIAL

A IA deverá ser utilizada como agente de decisão e pesquisa, não apenas como chatbot.

Ela deverá ser capaz de:

* interpretar regras;
* pesquisar fontes;
* analisar produtos;
* comparar descrições;
* identificar equivalências;
* identificar diferenças;
* detectar duplicidades;
* sugerir produtos;
* sugerir quantidades;
* sugerir lojas;
* detectar problemas;
* explicar decisões;
* interagir com o usuário;
* auxiliar na otimização.

Entretanto, decisões críticas deverão ser rastreáveis.

---

# 28. NÍVEIS DE AUTOMAÇÃO

Quero que o sistema tenha pelo menos três níveis:

### Automático

A IA executa sem perguntar.

### Automático com aprovação

A IA executa e apresenta para o usuário aprovar.

### Manual

O usuário assume o controle.

O motor de regras deverá determinar quais ações pertencem a cada nível.

---

# 29. INTERFACE

Quero uma interface web simples.

O usuário não deve precisar entender programação.

O fluxo ideal seria:

**Projeto**

↓

**Criar orçamento**

↓

**Definir regras**

↓

**Informar necessidades**

↓

**IA pesquisa**

↓

**IA valida**

↓

**IA encontra três fontes**

↓

**IA monta os três orçamentos**

↓

**IA calcula médias**

↓

**IA otimiza o quarto orçamento**

↓

**Usuário revisa**

↓

**Usuário aprova**

↓

**IA gera documentação**

↓

**Exportar**

---

# 30. DASHBOARD

O usuário deverá conseguir visualizar rapidamente:

* valor do teto;
* valor atual;
* diferença para o teto;
* quantidade de itens;
* itens aprovados;
* itens pendentes;
* itens inválidos;
* fontes utilizadas;
* CNPJs validados;
* documentos disponíveis;
* problemas encontrados.

---

# 31. ALERTAS

O sistema deverá alertar quando:

* não houver três fontes;
* produtos não forem equivalentes;
* CNPJ estiver irregular;
* vaga estiver duplicada;
* página estiver indisponível;
* preço estiver vencido;
* orçamento não fechar;
* existir conflito de regras;
* existir informação insuficiente;
* existir necessidade de aprovação humana.

---

# 32. EXPORTAÇÃO

O sistema deverá ser capaz de gerar:

* PDF;
* Excel;
* planilha;
* Word, quando necessário;
* relatório de memória de cálculo;
* relatório de pesquisa;
* relatório de auditoria;
* pacote de evidências.

Idealmente deverá ser possível gerar um único arquivo ZIP organizado:

```text
ORCAMENTO/
│
├── 01_ORCAMENTOS/
│   ├── Orcamento_1.pdf
│   ├── Orcamento_2.pdf
│   ├── Orcamento_3.pdf
│   └── Orcamento_Final.pdf
│
├── 02_PRODUTOS/
│   ├── Produto_001/
│   ├── Produto_002/
│   └── Produto_003/
│
├── 03_VAGAS/
│
├── 04_CNPJ/
│
├── 05_MEMORIA_CALCULO/
│
└── 06_AUDITORIA/
```

---

# 33. PESQUISA DE TECNOLOGIAS

Antes de qualquer implementação, pesquise profundamente soluções existentes.

Analise pelo menos:

### IA/agentes

* modelos de IA;
* agentes autônomos;
* ferramentas de pesquisa;
* ferramentas com navegação web;
* sistemas de browser automation.

### Automação

* n8n;
* Make;
* Zapier;
* Power Automate;
* outras soluções relevantes.

### Bancos de dados

* Supabase;
* Airtable;
* PostgreSQL;
* Google Sheets;
* outras alternativas.

### Interfaces

* Bubble;
* Retool;
* AppSheet;
* Softr;
* outras ferramentas.

### Pesquisa/web scraping

* Apify;
* Browser automation;
* APIs;
* scraping;
* ferramentas de pesquisa.

### Documentos

* geração de PDF;
* captura de páginas;
* armazenamento de evidências;
* geração automática de relatórios.

### CNPJ

Pesquisar APIs e fontes oficiais disponíveis para consulta cadastral.

### Otimização

Pesquisar bibliotecas e ferramentas capazes de resolver problemas de:

* otimização;
* programação linear;
* programação inteira;
* constraint solving;
* combinação de quantidades;
* fechamento exato de orçamento.

---

# 34. SOLUÇÃO GRATUITA

Identifique se é possível construir uma primeira versão praticamente gratuita.

Mostre exatamente:

* ferramentas;
* limitações;
* número de pesquisas;
* limites de automação;
* armazenamento;
* custos ocultos;
* necessidade de programação.

---

# 36. COMPARAÇÃO

Para cada arquitetura encontrada, apresente:

| Critério                   | Solução |
| -------------------------- | ------- |
| Complexidade               |         |
| Automação                  |         |
| IA                         |         |
| Pesquisa web               |         |
| Scraping                   |         |
| CNPJ                       |         |
| Matching de produtos       |         |
| Otimização                 |         |
| PDFs                       |         |
| Auditoria                  |         |
| Escalabilidade             |         |
| Manutenção                 |         |
| Dependência de programação |         |
| Limitações                 |         |

Não faça uma classificação simplista.

Explique o que cada solução resolve e o que deixa a desejar.

---

# 37. ARQUITETURA IDEAL

Depois de analisar todas as possibilidades, proponha a arquitetura que mais se aproxima da solução ideal.

Não necessariamente deverá ser uma única ferramenta.

Pode ser uma combinação.

Por exemplo:

IA
+
pesquisa web
+
browser automation
+
n8n
+
banco de dados
+
API de CNPJ
+
motor de matching
+
motor de otimização
+
gerador de PDF
+
interface web.

Mas não assuma essa arquitetura.

Determine-a com base na análise.

---

# 38. CRITÉRIO FUNDAMENTAL

A solução deverá priorizar:

1. confiabilidade;
2. cumprimento das regras;
3. rastreabilidade;
4. capacidade de auditoria;
5. automação;
6. facilidade de uso;
7. baixo custo;
8. flexibilidade;
9. possibilidade de expansão.

Não priorize apenas velocidade.

Um orçamento que seja produzido rapidamente, mas não consiga ser comprovado perante uma secretaria, não atende ao objetivo.

---

# 39. PRINCÍPIO DE SEGURANÇA

A IA nunca deverá:

* inventar preços;
* inventar produtos;
* inventar vagas;
* inventar CNPJs;
* inventar URLs;
* considerar produtos diferentes como iguais;
* reutilizar uma vaga duplicada;
* criar uma evidência falsa;
* alterar artificialmente um preço;
* manipular uma média;
* criar uma fonte inexistente;
* afirmar que uma pesquisa foi realizada quando não foi.

Quando não possuir evidência suficiente, deverá informar:

**"Não foi possível validar automaticamente."**

---

# 40. PRINCÍPIO DE TRANSPARÊNCIA

Toda decisão automatizada relevante deverá possuir uma explicação curta e objetiva.

Exemplo:

> "Loja X foi selecionada porque possui os 17 produtos necessários e apresentou o menor valor total entre as 6 lojas que possuíam todos os produtos."

Ou:

> "Produto Y foi marcado para revisão porque a descrição da Loja 2 não informa a gramatura."

Ou:

> "Não foi possível formar três orçamentos porque apenas duas lojas possuem o produto exatamente equivalente."

---

# 41. PRIMEIRA RESPOSTA QUE ESPERO DE VOCÊ

**Não construa nada ainda.**

Sua primeira tarefa é realizar uma análise estratégica e tecnológica completa deste problema.

Quero que você:

### 1.

Reformule o problema em termos de arquitetura de software e automação.

### 2.

Identifique todos os módulos que o sistema precisará possuir.

### 3.

Identifique quais módulos são simples e quais são tecnicamente difíceis.

### 4.

Pesquise ferramentas e soluções existentes.

### 5.

Pesquise soluções gratuitas.

### 6.

Pesquise soluções pagas.

### 7.

Analise soluções no-code.

### 8.

Analise soluções low-code.

### 9.

Analise desenvolvimento próprio.

### 10.

Analise arquiteturas híbridas.

### 11.

Identifique quais partes podem ser executadas por agentes de IA.

### 12.

Identifique quais partes precisam de algoritmos tradicionais.

### 13.

Identifique quais partes precisam de intervenção humana.

### 14.

Identifique os principais riscos.

### 15.

Proponha diferentes arquiteturas possíveis.

### 16.

Compare as arquiteturas.

### 17.

Explique exatamente o que cada arquitetura resolveria e o que deixaria a desejar.

### 18.

Estime custos.

### 19.

Estime dificuldade de implementação.

### 20.

Proponha a arquitetura que mais se aproxima da solução ideal.

### 21.

Proponha também a arquitetura de menor custo possível.

### 22.

Proponha um caminho evolutivo:

**MVP → versão intermediária → sistema completo.**

### 23.

Identifique quais partes devem ser construídas primeiro.

### 24.

Identifique quais decisões precisam ser tomadas antes da implementação.

### 25.

Não comece a construir o sistema até que essa análise seja concluída.

O objetivo é descobrir **qual é a melhor maneira de construir esse sistema**, e não simplesmente escolher uma ferramenta e tentar encaixar o problema nela.

**IMPORTANTE:** a análise não deverá ser puramente teórica. As tecnologias críticas consideradas para a solução deverão ser testadas na prática sempre que isso for tecnicamente possível. A resposta deverá separar claramente o que foi **testado e validado**, o que foi **parcialmente validado**, o que é apenas **suportado pela documentação** e o que permanece **não validado**.

Não recomende uma tecnologia como componente crítico da arquitetura ideal apenas porque sua documentação afirma que ela possui determinada capacidade. Sempre que possível, faça uma pequena prova de conceito antes da recomendação.

A arquitetura final deverá ser baseada não apenas em "o que deveria funcionar", mas em **o que demonstrou funcionar, quais limitações foram encontradas e quais pontos ainda precisam de validação antes da implementação**.

# 42. VALIDAÇÃO PRÁTICA OBRIGATÓRIA

As soluções, ferramentas, APIs, plataformas, arquiteturas e combinações de tecnologias propostas deverão ser **testadas na prática antes de serem recomendadas como parte da arquitetura ideal**.

Não quero uma análise baseada apenas em documentação, marketing, exemplos teóricos ou naquilo que uma ferramenta afirma ser capaz de fazer.

Existe uma diferença importante entre:

> "A ferramenta teoricamente consegue fazer isso"

e

> "A ferramenta foi testada e realmente consegue fazer isso neste projeto."

Portanto, sempre que tecnicamente possível, realize **testes práticos, provas de conceito (PoC), experimentos ou validações reais** das principais tecnologias consideradas.

## 42.1. O que deverá ser testado

Dependendo da tecnologia analisada, os testes deverão verificar, na prática:

* capacidade real de pesquisa na web;
* capacidade de acessar páginas de lojas;
* capacidade de acessar páginas com JavaScript;
* capacidade de lidar com páginas dinâmicas;
* capacidade de realizar scraping;
* capacidade de utilizar browser automation;
* capacidade de extrair produtos e preços;
* capacidade de identificar marca, modelo, quantidade e especificações;
* capacidade de comparar produtos;
* capacidade de detectar produtos realmente diferentes;
* capacidade de encontrar três fontes para o mesmo conjunto de produtos;
* capacidade de identificar páginas indisponíveis;
* capacidade de preservar evidências;
* capacidade de gerar PDFs ou capturas;
* capacidade de consultar CNPJ;
* capacidade de pesquisar vagas;
* capacidade de detectar vagas duplicadas;
* capacidade de utilizar APIs;
* capacidade de integrar diferentes sistemas;
* capacidade de executar workflows automaticamente;
* capacidade de utilizar modelos de IA;
* capacidade de manter contexto entre etapas;
* capacidade de armazenar histórico;
* capacidade de executar cálculos determinísticos;
* capacidade de executar algoritmos de otimização;
* capacidade de encontrar uma solução cujo valor final seja exatamente igual ao teto;
* capacidade de gerar documentos;
* capacidade de exportar os resultados;
* capacidade de registrar logs e evidências;
* capacidade de funcionar de forma confiável sem intervenção humana excessiva.

## 42.2. Testes com dados reais ou representativos

Sempre que possível, os testes deverão utilizar **casos reais ou dados representativos do problema**, e não apenas exemplos artificiais extremamente simples.

Por exemplo, para validar uma ferramenta de pesquisa de preços, não basta testar:

> "Encontre uma caneta."

Deverá ser realizado um teste mais próximo do cenário real:

> "Encontre determinado conjunto de 10, 20 ou mais produtos, identifique marca, modelo, embalagem, quantidade e preço, pesquise em múltiplas lojas e verifique quais lojas possuem todos os produtos exatamente equivalentes."

Para matching de produtos, deverão ser testados casos como:

* mesmo produto com descrição diferente;
* mesmo produto com ordem de palavras diferente;
* mesmo produto com abreviações;
* mesma marca e modelo;
* marcas diferentes;
* modelos diferentes;
* tamanhos diferentes;
* gramaturas diferentes;
* quantidades diferentes;
* embalagens diferentes;
* unidades de venda diferentes;
* produtos visualmente semelhantes, mas tecnicamente diferentes.

Para otimização, deverão ser testados:

* casos fáceis;
* casos com solução;
* casos com múltiplas soluções;
* casos sem solução;
* casos com arredondamento;
* casos em que o valor precisa fechar exatamente no teto;
* casos em que alterações de quantidade são permitidas;
* casos em que alterações de quantidade são proibidas.

## 42.3. Provas de conceito

Para as tecnologias críticas, deverá ser criada uma pequena **prova de conceito (PoC)** antes de recomendar sua adoção definitiva.

As PoCs deverão responder perguntas objetivas, como:

* "Essa ferramenta consegue realmente pesquisar as lojas que precisamos?"
* "Consegue acessar páginas protegidas por JavaScript?"
* "Consegue extrair o preço correto?"
* "Consegue preservar a página como evidência?"
* "Consegue distinguir dois produtos diferentes?"
* "Consegue identificar uma mesma vaga publicada em plataformas diferentes?"
* "A API de CNPJ fornece os dados necessários?"
* "O mecanismo de otimização consegue fechar exatamente o orçamento?"
* "O workflow consegue executar todas as etapas sem intervenção?"
* "Qual é a taxa de falha?"
* "Quanto tempo leva?"
* "Quanto custa por orçamento?"
* "Quais etapas ainda exigem intervenção humana?"

## 42.4. Separar teoria de capacidade comprovada

Em toda recomendação tecnológica, diferencie claramente:

### 🟢 Validado na prática

A capacidade foi testada e funcionou no cenário analisado.

### 🟡 Parcialmente validado

Foi realizado um teste, mas existem limitações ou o teste não cobriu todas as situações relevantes.

### 🔵 Suportado pela documentação

A ferramenta declara possuir a capacidade, mas ela ainda não foi validada na prática neste projeto.

### 🔴 Não validado / incerto

Não foi possível confirmar que a solução funciona adequadamente.

Não apresente uma capacidade como garantida apenas porque ela aparece na documentação da ferramenta.

## 42.5. Registrar resultados dos testes

Para cada tecnologia crítica testada, apresente:

* tecnologia;
* função testada;
* cenário de teste;
* entrada utilizada;
* resultado esperado;
* resultado obtido;
* taxa de sucesso, quando mensurável;
* limitações encontradas;
* erros encontrados;
* tempo de execução;
* custo estimado;
* necessidade de intervenção humana;
* conclusão;
* nível de confiança;
* possibilidade de utilização em produção.

## 42.6. Testar a integração, não apenas as ferramentas isoladamente

Não basta testar cada ferramenta separadamente.

Sempre que possível, deverão ser testadas também as **integrações entre elas**.

Por exemplo:

> Pesquisa web → extração do produto → matching → banco de dados → cálculo → otimização → geração de evidência.

Ou:

> Pesquisa de vaga → identificação da empresa → CNPJ → validação → armazenamento → cálculo de remuneração.

A arquitetura deverá ser avaliada considerando o funcionamento do **fluxo completo**, porque uma ferramenta pode funcionar perfeitamente isoladamente e ainda assim apresentar problemas quando integrada às demais.

## 42.7. Testar limites e situações de falha

Também deverão ser realizados testes de:

* página bloqueada;
* CAPTCHA;
* timeout;
* site fora do ar;
* produto sem preço;
* preço oculto;
* preço dependente de login;
* preço promocional;
* produto esgotado;
* página alterada;
* URL quebrada;
* dados incompletos;
* CNPJ não encontrado;
* CNPJ inativo;
* vaga removida;
* vaga duplicada;
* API indisponível;
* limite de requisições;
* erro de integração;
* falha do modelo de IA;
* resposta incorreta da IA;
* ausência de solução matemática.

O sistema deverá possuir estratégias de fallback quando forem tecnicamente viáveis.

## 42.8. Não considerar uma arquitetura "ideal" sem validação

Uma arquitetura somente deverá ser apresentada como **arquitetura recomendada/ideal** depois que suas partes críticas tiverem sido avaliadas e, quando possível, testadas.

Caso uma parte importante não possa ser testada no momento, isso deverá ser explicitamente informado.

Não quero uma arquitetura "perfeita no papel".

Quero uma arquitetura que tenha **evidência prática de que consegue funcionar no mundo real**.

## 42.9. Relatório de validação

Ao final da análise tecnológica, inclua uma seção:

### "O que foi testado na prática"

Nessa seção, apresente:

| Tecnologia   | O que foi testado | Resultado   | Limitações  | Status          |
| ------------ | ----------------- | ----------- | ----------- | --------------- |
| Tecnologia X | Função Y          | Funcionou   | Limitação Z | 🟢 Validado     |
| Tecnologia A | Função B          | Parcial     | ...         | 🟡 Parcial      |
| Tecnologia C | Função D          | Não testado | ...         | 🔵 Não validado |

A recomendação final deverá considerar **tanto a capacidade teórica quanto os resultados dos testes práticos**.

---

# 43. REGRA FINAL: NÃO CONFUNDIR POSSIBILIDADE COM FUNCIONAMENTO

Este projeto deverá seguir o seguinte princípio:

> **"Se funciona na teoria, investigue. Se funciona na prática, valide. Se funciona de forma confiável em um fluxo integrado, considere para produção."**

A análise deverá buscar reduzir ao máximo as suposições.

Quando houver dúvida entre duas tecnologias, priorize aquela que possuir **maior evidência prática, maior previsibilidade e maior capacidade de auditoria**, mesmo que a alternativa teoricamente pareça mais sofisticada.

Se uma tecnologia parecer excelente no papel, mas apresentar limitações importantes durante os testes, essas limitações deverão pesar na recomendação final.

O objetivo não é encontrar a tecnologia mais moderna.

O objetivo é encontrar a combinação de tecnologias que **realmente consiga executar o processo de forma confiável, auditável, sustentável e economicamente viável**.
