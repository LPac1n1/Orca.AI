# Fase 1B — Testes das possibilidades gratuitas (25–26/09/2026)

Continuação de [`FASE1_AUTOMACAO_TOTAL.md`](FASE1_AUTOMACAO_TOTAL.md), seguindo as suas decisões:

- vagas de qualquer região do Brasil;
- CNPJ, se possível, consultado online, sem baixar a base;
- mesma marca nas 3 lojas, com troca automática por item parecido ou relacionado;
- todos os itens no mesmo trio de lojas;
- intervenção sua só em último caso;
- custo zero.

**Nada foi alterado no sistema (`sistema/`).** Tudo abaixo são protótipos em [`fase1/`](fase1/), testados com dados reais de hoje.

Legenda: 🟢 funciona · 🟡 funciona com ressalva · 🔵 proposta, ainda não testada · 🔴 não funciona.

---

## 1. Resumo

| Tema | Antes (Fase 1) | Agora | Status |
|---|---|---|---|
| Vagas do Brasil + CNPJ do empregador, sem intervenção | CNPJ manual | **6 de 7 cargos fecham 3 vagas com CNPJ confirmado** | 🟢 |
| CNPJ pelo nome, online e sem base | 6/8 (Brave, com bloqueio) | 12/15 certos; homônimos retidos; **1 erro que só a base da Receita evitaria** | 🟡 |
| Mesmo produto nas 3 lojas | comparação de nomes, quase nunca fechava | **código de barras (EAN) + estoque real no CEP** | 🟢 |
| Cesta limpeza (6 itens) | 2/6 com mesma marca | **5/6 no mesmo trio** | 🟢 |
| Cesta alimentação (14 itens) | 2/14 com mesma marca | **11/14 no mesmo trio** (4 com troca automática) | 🟡 |
| Cesta papelaria (9 itens) | 0/9 com mesma marca | **2/9**: faltam lojas com o mesmo catálogo | 🔴 |
| Carrinho do Tenda: quantidade | não ajustava | **resolvido** pela própria página | 🟢 |
| IA gratuita sem conta | — | nenhuma funciona hoje; só com chave sua ou modelo local | 🔵 |

---

## 2. Vagas do Brasil + CNPJ, ponta a ponta ([`e7_vagas_brasil_cnpj.py`](fase1/e7_vagas_brasil_cnpj.py))

### 2.1 Como funciona o fluxo automático

1. Busca nacional: InfoJobs, Catho, Vagas.com, BNE e LinkedIn público.
2. Filtros da vaga:
   - título exato (só variações das mesmas palavras);
   - empresa identificada, sem confidencial e sem agregador;
   - salário mensal informado.
3. Ordena as vagas pelo **menor salário** (regra da faixa mínima).
4. Para cada empresa, procura o CNPJ ([`cnpj_nome.py`](fase1/cnpj_nome.py)):
   - busca no Ecosia e no Yahoo (o Brave fica de reserva);
   - lê o CNPJ publicado no **site oficial** da empresa, quando existe;
   - confere cada número na API gratuita (nome, situação **ATIVA**).
5. Para quando tiver **3 empresas diferentes com CNPJ 🟢**. Se não fechar, abre as páginas seguintes das plataformas.

### 2.2 Resultado (rodada final, 26/09)

| Cargo | Vagas aptas no Brasil | Consultas de CNPJ | Resultado |
|---|---|---|---|
| Coordenador de Projetos | 5 | 5 | ✘ **0 com CNPJ seguro** |
| Assistente Social | 30 | 13 | ✔ 3 vagas |
| Psicólogo | 16 | 7 | ✔ 3 vagas |
| Auxiliar de Serviços Gerais | 51 | 7 | ✔ 3 vagas |
| Auxiliar Administrativo | 39 | 13 | ✔ 3 vagas |
| Orientador Socioeducativo | 3 | 3 | ✔ 3 vagas |
| Designer Gráfico | 14 | 6 | ✔ 3 vagas |

- **Tempo:** 1,5 a 8 minutos por cargo.
- **CNPJ:** de cada 3 empresas consultadas, cerca de 1 sai 🟢. As outras são homônimas, de outra UF, inativas ou não encontradas, e o motor passa para a próxima vaga. Há vagas de sobra, então isso não impede o fechamento.

### 2.3 Erros que os testes pegaram e as travas criadas

| Caso real | O que acontecia | Trava criada |
|---|---|---|
| "Yapp" (vaga em GO) | pegava o CNPJ da **matriz estrangeira** (município "EXTERIOR") | empresa estrangeira → 🔴 |
| "King Plast" (vaga em SP) | CNPJ de uma King Plast do **PR** | CNPJ em UF diferente da vaga → 🟡, passa para a próxima |
| "PORT" (vaga em MG) | CNPJ de uma empresa do **DF** | idem |
| "Clave de Sol" (2 empresas com o nome) | desempate pela UF escolhia uma **loja de roupas** | desempate só pela UF → 🟡 |
| "UNIRH", "Uni Udi", "Base e RH" | CNPJ **baixado, suspenso ou inapto** | situação ≠ ATIVA → 🔴 (regra R07) |

**Risco que continua (🟡):** na última rodada, "Clave de Sol" voltou a sair 🟢 como a loja de roupas, porque os buscadores só mostraram essa empresa. É o mesmo tipo de erro de "Confiança RH" no gabarito (item 3). Online, **não há como garantir que não exista outra empresa com o mesmo nome**. Só a base da Receita, que tem todos os nomes fantasia, resolve isso de vez (decisão D8).

### 2.4 Coordenador de Projetos: por que não fecha

Das vagas desse cargo no Brasil, 50 tinham título diferente ("…de TI", "…de Engenharia", "…Data Center"). Só 5 tinham o título exato com salário.

Buscar mais páginas não ajudou:
- a InfoJobs volta para a página 1 depois da 3ª;
- as páginas seguintes da Catho e do LinkedIn trazem só títulos diferentes.

**Possibilidade gratuita 🔵: banco de vagas.** O sistema busca todo dia e **guarda** cada vaga apta com a evidência (PDF e data), válida por 180 dias. Cargos raros acumulam vagas com o tempo, sem mudar a regra do título exato.

---

## 3. CNPJ pelo nome, online, sem baixar base

Gabarito: 15 empresas da grade do Parecer 8, com CNPJ conhecido.

| Fonte | Certos | Errados | Sem resposta |
|---|---|---|---|
| Ecosia | 12 | 0 | 3 |
| Yahoo | 11 | 1 | 3 |
| Brave | 7 de 10 | 0 | 3 bloqueios |
| Startpage | 3 | 0 | 12 |
| Qwant, DuckDuckGo Lite, AOL, ConsultaSócio, Linkana | 0 | 0 | 15 cada |
| **Módulo final (Ecosia + Yahoo + site oficial + API)** | **12** | **1** | 2 retidos como homônimos |

- **O erro que restou:** existem **duas empresas "Confiança RH" em Niterói/RJ**, ambas ativas. Os buscadores mostram só a errada. Nenhuma regra online separa as duas.
- **Bloqueio:** depois de centenas de consultas no mesmo dia, Yahoo e Ecosia começaram a recusar. O sistema precisa de **cache** (cada empresa é consultada uma vez só e o resultado fica guardado) e de um ritmo mais lento.
- **Base da Receita:** existe e é oficial e gratuita (~6,4 GB por mês). É a única forma de ver **todos** os homônimos. Proposta na decisão D8.

---

## 4. Cesta automática: mesmo produto, mesma marca, mesmo trio ([`e10_cesta_v5.py`](fase1/e10_cesta_v5.py))

### 4.1 Descobertas que mudaram o motor

| Descoberta | Efeito |
|---|---|
| **EAN (código de barras):** vem na API das lojas VTEX; Lepok publica no HTML; Kalunga e Carrefour, na página do produto | "mesmo produto" vira comparação **exata** do código, e não de nomes escritos de jeitos diferentes |
| **Ponte de EAN:** um código achado numa loja é procurado nas outras lojas VTEX pelo filtro exato | acha o mesmo produto mesmo quando a busca por texto não o mostra |
| **Estoque e preço reais no CEP:** a simulação de carrinho da loja para 03977-015 | a Atacadão mostrava "indisponível" no catálogo, mas **tinha estoque** (Ypê Neutro, R$ 2,19). Só isso levou a limpeza de 2/6 para 5/6 |
| **Americanas é marketplace:** é preciso escolher o vendedor que tem estoque | as ofertas disponíveis no CEP passaram de 55 para 63–65 |
| **Kalunga vende sobretudo marca própria (Spiral)** | raramente tem o mesmo produto que as outras papelarias |
| **Livrarias Curitiba** preenche a marca com o nome da loja ("LC") | o motor passou a ignorar esse campo |
| **Tenda e Gimba não publicam EAN** | identidade pela descrição (🟡); no Tenda, pelo **título completo** que abre a descrição (o nome da busca vem cortado) |

### 4.2 Regras de identidade (testadas: 17/17 + 10/10 + 11/11 casos-armadilha)

- **🟢 EAN igual** em todas as lojas, com a mesma quantidade na embalagem. Exemplo real: a Lepok vende "caneta com 4 unidades" com o EAN da caneta avulsa, e o motor recusa.
- **🟡 Pela descrição**, quando falta EAN em uma loja. Tudo abaixo precisa bater:
  - mesma marca;
  - mesmas unidades;
  - nenhuma medida, cor, formato (A4 × Ofício), variante (Colorido, Reforçado) ou linha (Linha Leve, Premium) diferente;
  - variante dita em só um dos nomes conta como diferente;
  - número de modelo igual (clips "NR 1/0" = "Nº0").
- **Nunca aceita:**
  - "Zero Álcool" como álcool; "sem sal" como "com sal";
  - produto que não começa pelo tipo (porta-objetos no lugar de clips);
  - outro item da mesma cesta (café solúvel no lugar de café em pó);
  - o **mesmo produto para dois itens** (suco de maçã para uva e para laranja).

### 4.3 Troca automática (item parecido ou relacionado), com "distância"

| Nível | O que pode mudar | Limites |
|---|---|---|
| 1 · parecido | tamanho ou variante | tamanho entre **metade e o dobro**; mesma forma (gel ≠ líquido); 26/6, furos e divisórias não mudam |
| 2 · relacionado | produto da mesma família | mesmos limites de tamanho; grampo 26/8 **não** substitui 26/6 (não serve no grampeador 26/6 da cesta) |

O motor escolhe a troca que perde menos atributos (sabor, cor, "integral") e fica mais perto do tamanho pedido. Cada troca vai com a justificativa ("perdeu: morango").

**Trocas absurdas das primeiras versões, hoje bloqueadas:**
- porta-objetos no lugar de clips;
- detergente de **5 L** no lugar de 500 mL;
- lápis **de cor** no lugar de lápis preto;
- o mesmo suco para dois itens.

### 4.4 Resultado final (rodada 7, regras estritas)

| Cesta | Melhor trio | Itens no trio | Como descrito | Trocas | Faltam |
|---|---|---|---|---|---|
| Limpeza (6) | Atacadão + Tenda + Carrefour | **5/6** | 4 | Sabão em pó Tixan 800 g no lugar de 1,6 kg | Álcool 1L |
| Alimentação (14) | Oba + Tenda + Carrefour | **11/14** | 7 | pão 500 g no lugar de 480 g e de 400 g; **geleia de pimenta no lugar de morango**; sardinha em óleo no lugar de com tomate | 2 sucos, banana chips |
| Papelaria (9) | Lepok + Gimba + Afonso Ruotolo | **2/9** | 2 | — | 7 itens |

Observações:
- **Alimentação:** o trio Atacadão + Tenda + Carrefour cobre 10/14 **sem nenhuma troca** e sai ~R$ 600 mais barato. A escolha entre "mais itens" e "menos trocas e menor preço" é decisão sua (D9).
- **"Geleia de pimenta no lugar de morango":** a regra permite ("relacionado"), mas uma pessoa acharia estranho. É exatamente o tipo de decisão em que uma IA ajudaria (item 6).
- **Papelaria:** Lepok e Gimba têm muitos produtos idênticos (clips Bacchi e ACC, caneta BIC Cristal caixa com 50), mas **falta uma 3ª loja com o mesmo catálogo e estoque no CEP**. Testei:
  - Kalunga: marca própria;
  - Americanas: pouco estoque no CEP;
  - Livrarias Curitiba: pouco estoque no CEP;
  - Afonso Ruotolo: nova, sem EAN;
  - Papelmais, MC Papéis, Art Nova, Costa Atacado, Martins: busca não lida;
  - Papelitech, TK Shopping: bloqueiam (403).
- **Tenda:** entra nos trios pela descrição (🟡), porque não publica EAN.

### 4.5 Precisão × cobertura (medido)

| Regra para lojas sem EAN | Limpeza | Alimentação | Papelaria | Risco |
|---|---|---|---|---|
| Mais solta (rodadas 3–5) | 5/6 | 12/14 | 1–2/9 | agrupa "Reforçado" com saco comum, "Colorido" com galvanizado |
| **Estrita + título completo (rodada 7)** | **5/6** | **11/14** | **2/9** | só agrupa quando tudo o que está escrito bate |

---

## 5. Carrinho do Tenda: quantidade resolvida 🟢 ([`e8_tenda_quantidade_sonda.py`](fase1/e8_tenda_quantidade_sonda.py))

A quantidade é um campo de texto no carrinho, e o "+" é um texto clicável, não um botão.

- Digitando 5 e saindo do campo, o site envia `quantity: 5` e a quantidade **permanece após recarregar**.
- Pelo "+", foi de 5 para 6 e 7.
- Conferência: 7 × R$ 2,39 = R$ 16,73, igual ao carrinho.

Tudo pela própria página, sem usar credenciais ou tokens do site.

---

## 6. IA gratuita para as decisões 🟡

| Opção | Custo | Precisa | Testado |
|---|---|---|---|
| Pollinations (anônima, sem conta) | 0 | nada | 🔴 erro no servidor nas 2 tentativas ("sem espaço em disco") |
| Google Gemini (camada gratuita) | 0 | **você** criar uma chave | 🔵 |
| Groq (camada gratuita) | 0 | chave sua | 🔵 |
| Cloudflare Workers AI / Mistral / OpenRouter | 0 | chave sua | 🔵 |
| Modelo local (Ollama, ~2–5 GB) | 0 | sua autorização para baixar | 🔵 |

**Onde a IA ajudaria, de forma medível:**
1. decidir se dois nomes sem EAN são o mesmo produto (os casos 🟡);
2. escolher trocas "relacionadas" com bom senso (morango → outra geleia de fruta, não de pimenta);
3. dizer se a empresa é plausível para o cargo ("loja de roupas contratando assistente social?").

Todas as opções gratuitas exigem **uma conta sua** (eu não crio contas nem chaves) ou **baixar um modelo**.

---

## 7. Travamentos, falhas e avisos (o que os testes mostraram)

| Situação real | O que aconteceu | Tratamento |
|---|---|---|
| Computador entrou em suspensão | uma busca "esperou" 31.000 s com a rede caída | nesta sessão, o PC ficou acordado pelo app do Claude; no sistema: impedir a suspensão durante a tarefa, limite de tempo por etapa e retomada de onde parou 🔵 |
| Rede instável ao acordar | 534 falhas numa rodada; lojas pareciam "sem produto" | **aviso "RESULTADO INCOMPLETO"** por loja quando ≥ 20% das buscas falham (🟢, no protótipo) |
| Buscadores recusando após muitas consultas | Yahoo e Ecosia "sem resposta" | cache de CNPJ por empresa + ritmo limitado 🔵 |
| Buscas repetidas | 3.400 simulações e 1.000 buscas por rodada | cache do dia: rodadas seguintes em 2 a 7 minutos, em vez de 30 (🟢) |

---

## 8. Decisões para você

| # | Decisão | Opções | Minha recomendação |
|---|---|---|---|
| D7 | Cargo que não fecha (ex.: Coordenador de Projetos) | **Banco de vagas diário** (guarda vagas válidas por 180 dias) / aviso para você buscar | **Banco de vagas**, com aviso na tela enquanto não houver 3 |
| D8 | Homônimos de CNPJ (erros como "Confiança RH" e "Clave de Sol") | (a) só online, como está; (b) **online + base da Receita** para checar homônimos, baixada e atualizada todo mês automaticamente (~6,4 GB) | **(b)**: é a única forma de ter certeza. Enquanto não houver, o sistema mostra o CNPJ e a atividade da empresa ao lado da vaga |
| D9 | Escolha do trio | mais itens (aceita trocas) / menos trocas e menor preço | **Mais itens**, com as trocas justificadas e a alternativa mostrada ao lado |
| D10 | Lojas sem EAN (Tenda, Gimba, Afonso) | aceitar identidade pela descrição (🟡) / só EAN | **Aceitar 🟡**, com as regras estritas; sem isso, nenhuma cesta fecha |
| D11 | Papelaria (2/9) | manter mesma marca (sua decisão) e continuar procurando lojas / abrir exceção de "mesma especificação" só na papelaria, como a SEJC aceitou no Parecer 8 / IA | Você pediu **mesma marca**; com ela, a papelaria fecha só 2/9 hoje. Se aceitar, uma **exceção só para a papelaria**, com aviso na tela, até achar uma 3ª loja com o mesmo catálogo. Se não, a papelaria fica parcial |
| D12 | IA gratuita | criar uma chave gratuita (ex.: Gemini) / autorizar modelo local / nenhuma | Uma **chave gratuita sua**, usada só nos casos 🟡, com as regras continuando a decidir o resto |

---

## 9. Arquivos desta etapa (`fase1/`)

| Arquivo | O que é |
|---|---|
| `cnpj_nome.py` | CNPJ pelo nome com as travas (site oficial, UF, estrangeira, homônimos) |
| `e7_vagas_brasil_cnpj.py` | vagas do Brasil + CNPJ, ponta a ponta |
| `e7_rodada2_completa.log`, `e7_rodada3_cargos2e5.log`, `e7_*.json` | resultados das vagas |
| `e10_cesta_v5.py` | cesta com EAN, estoque no CEP, identidade estrita, trocas com distância |
| `e10_rodada3…7.log` | resultados de cada rodada da cesta |
| `d10_diagnostico.py` | diagnóstico da cesta só com o cache, sem acessar as lojas |
| `t6_armadilhas.py` | 17 casos-armadilha de compatibilidade |
| `e8_tenda_quantidade_sonda.py` | quantidade no carrinho do Tenda |
| `e9_ean_paginas.py` | quais lojas publicam EAN |
| `e11_lojas_genericas.py` | teste de papelarias pequenas |
| `e5_cnpj_online.py` | comparação dos buscadores |
| `e17_gemini_instrucao.py`, `e17_gemini_instrucao.json` | instrução da IA "mesmo produto?": atual × revisada (seção 12) |

Os tokens do site do Tenda capturados na sonda foram **omitidos** do arquivo salvo.

---

## 10. Suas decisões (26/09) e os testes feitos em seguida

| # | Sua decisão | O que foi testado | Status |
|---|---|---|---|
| D7 | Banco de vagas diário | desenho pronto (item 10.4); implementação na v0.3 | 🔵 |
| D8 | Base da Receita, atualizada todo mês | base oficial de setembro **baixada e indexada**; acha o CNPJ direto e barra homônimos (itens 10.1, 10.5–10.7) | 🟢 |
| D9 | Trio com os mesmos itens + **teto por rubrica** | otimizador protótipo com os tetos do Parecer 8 (item 10.2) | 🟢 limpeza e alimentação · 🔴 papelaria |
| D10 | Aceitar identidade pela descrição, **priorizando EAN** | peso do EAN triplicado na escolha dos produtos | 🟢 |
| D11 | **Mesmo produto e mesma marca em todas as rubricas** | é a regra do motor (sem exceção para a papelaria) | 🟢 |
| D12 | Gemini gratuito | passo a passo em [`GEMINI_PASSO_A_PASSO.md`](GEMINI_PASSO_A_PASSO.md); teste pronto ([`e14_gemini.py`](fase1/e14_gemini.py)), aguardando a sua chave | 🔵 |

### 10.1 Base oficial da Receita (D8) — [`e13_base_receita.py`](fase1/e13_base_receita.py)

- **Fonte:** arquivos oficiais de setembro/2026 (Empresas + Estabelecimentos), 6,3 GB baixados em 58 min.
- **Onde fica:** `%LOCALAPPDATA%\OrcamentoOSC\receita`, **fora do OneDrive**, para não ocupar a sua cota nem sincronizar 6 GB com a nuvem.
- **Conteúdo lido:** 70 milhões de empresas e 73,4 milhões de estabelecimentos, dos quais **28,3 milhões ativos**. O índice local guarda só os ativos, com nome fantasia, razão social, UF, município e CNAE.
- **Busca:** milissegundos por nome.
- **Trava nova:** quando o CNPJ encontrado online sai 🟢, o sistema confere na base se existe **outra empresa ativa com o mesmo nome**. Se existir, vira 🟡 e o motor passa para a próxima vaga. A exceção é o CNPJ publicado no site oficial da empresa.
- **Atualização mensal automática 🔵:** o sistema baixa a pasta nova, monta um índice novo ao lado e só troca quando termina. O índice anterior continua funcionando enquanto isso.

### 10.2 Teto por rubrica (D9) — [`e12_teto_rubrica.py`](fase1/e12_teto_rubrica.py)

Como ficou a regra, a partir da sua decisão:

1. A soma da rubrica no plano fica **≤ teto** e o mais perto possível dele.
2. O valor de cada item é um preço orçado **≤ média** ou a própria média (valores defensáveis).
3. **Tira itens** só se nem com os menores valores couber.
4. **Acrescenta itens** da mesma rubrica (achados nas **mesmas 3 lojas**, mesmo produto, EAN primeiro) só se a sobra passar de **5% do teto** ("muito longe"; configurável).
5. O fechamento **exato em centavos** continua no total do projeto, pelo otimizador do sistema, que também ajusta as horas de RH.

Resultado com os tetos mensais do Parecer 8 e os preços de hoje:

| Rubrica | Teto | Plano | Sobra | O que o motor fez |
|---|---|---|---|---|
| Limpeza | R$ 299,55 | R$ 298,83 | 0,2% | manteve os 5 itens achados; desinfetante e sabão em pó no preço de uma loja (≤ média), o resto na média |
| Alimentação | R$ 1.839,71 | R$ 1.834,98 | 0,3% | manteve os 11 itens achados, todos na média |
| Papelaria | R$ 320,00 | R$ 74,93 | 77% | **incompleta**: só 2 itens pedidos acharam o mesmo produto nas 3 lojas, e nenhum extra seguro |

**Travas acrescentadas depois do primeiro teste:**
- Na 1ª versão o motor fechava o teto em centavos **tirando a água sanitária e pondo 10 limpadores multiuso**. Corrigido: o teto da rubrica passou a ser limite, não valor exato.
- A quantidade de um item extra não passa da maior quantidade já pedida na rubrica. Na 1ª versão apareceram "20 apontadores".
- Extra confirmado **só pela descrição**, com preço variando mais de **2,5×** entre as lojas, é recusado. O apontador custava de R$ 0,59 a R$ 2,89: provavelmente não era o mesmo produto.

**Ponto de atenção:** o saco de lixo (mesmo EAN em 2 lojas) custa R$ 14,90, R$ 25,90 e R$ 49,99, variação de 3,4×. A proposta é mostrar um aviso de dispersão, sem recusar, quando o EAN confirma o produto.

### 10.3 EAN primeiro (D10)

A cobertura dos itens pedidos continua em primeiro lugar, como você pediu. Entre opções com a mesma cobertura, cada loja **sem EAN** passou a pesar 3 vezes mais contra a escolha. Assim o motor prefere o produto confirmado por código de barras quando existe.

### 10.4 Banco de vagas (D7) — desenho para a v0.3

- **Todo dia**, pelo Agendador de Tarefas do Windows ou ao abrir o sistema, a busca roda para os cargos dos projetos ativos.
- **Cada vaga apta é guardada** com:
  - título, empresa, CNPJ (🟢/🟡), salário mínimo da faixa, cidade/UF, plataforma e link;
  - data da vaga e data da coleta;
  - **PDF da página** com o carimbo de data e o código de verificação (SHA-256).
- **Validade:** 180 dias a partir da coleta. O sistema avisa antes de vencer.
- Ao montar o orçamento, o sistema usa as **3 vagas válidas de menor salário, de empresas diferentes e com CNPJ 🟢**. Cargos raros, como Coordenador de Projetos, acumulam vagas com o tempo.
- Se um cargo ainda não tiver 3 vagas, aparece na tela quantas faltam e desde quando o sistema procura.

### 10.5 Base da Receita: resultado medido ([`e15_homonimos.py`](fase1/e15_homonimos.py))

**Montagem do índice:**
- tamanho: 7,3 GB;
- tempo: 97 minutos, uma vez por mês e em segundo plano. Dá para reduzir indexando só nomes distintos;
- busca: 20 a 140 ms por nome.

| Nome da empresa | Empresas ATIVAS com esse nome no Brasil |
|---|---|
| Clave de Sol | **25** (instrumentos musicais, eventos, chocolates, loja de roupas…) |
| Confiança RH | **3**, todas em Niterói/RJ (entre elas a certa e a que os buscadores mostravam) |
| Hospital Santa Mônica | 11 |
| CEJA Brasil | 81 |
| PORT | 876 |

**Todas as empresas que saíram 🟢 online, conferidas na base:**

| Grupo | Continua 🟢 (nome único) | Vira 🟡 (há outras empresas ativas com o nome) |
|---|---|---|
| Empresas das vagas (25) | 13 | 12 |
| Gabarito do Parecer 8 (15) | 9, **todos com o CNPJ certo** | 6, incluindo **"Confiança RH"**, o único erro que restava |

**Efeito:** com a base, **nenhum erro conhecido passa como 🟢**. Em compensação, menos empresas saem 🟢, e o motor consulta mais vagas por cargo até achar 3 com nome único.

### 10.6 A base também ACHA o CNPJ, sem buscadores

Como a base tem **todas** as empresas ativas, ela resolve o CNPJ sozinha quando não há dúvida:

1. **Única empresa ativa no Brasil com o nome** (nome igual, ou cadastro que **começa** pelo nome da vaga: "Bijunova" → "BIJUNOVA COMÉRCIO, IMPORTAÇÃO E EXPORTAÇÃO") → 🟢.
2. **Várias no Brasil, mas uma só no município da vaga** → 🟢. Exemplo: "Hospital Santa Mônica", 11 no país e 1 só em Itapecerica da Serra.
3. Senão, busca online + site oficial + trava de homônimos. Se continuar em dúvida → 🟡, e o motor passa para a próxima vaga.
4. **A trava de estado continua valendo.** O único "INPLAK" ativo do Brasil fica na Bahia, e a vaga era em SP → 🟡.

| Teste | Resultado |
|---|---|
| Gabarito do Parecer 8 (15 empresas) | **9 resolvidas pela base, 0 erros**; 6 vão para a busca online com a trava |
| Empresas das vagas (54) | 17 resolvidas pela base; em 15, o mesmo CNPJ da busca online, agora com nome único confirmado |
| "Base e RH" (vaga em MG) | buscadores: só uma empresa **inapta**; base: "BASE RH", Betim/MG, ativa → 🟢 |

**Vantagens:**
- menos consultas aos buscadores, portanto menos bloqueio;
- resposta em milissegundos;
- fonte oficial, que pode ser citada na evidência.

### 10.7 Vagas + CNPJ com a base (rodada final, 26/09) — [`e7_rodada5_base_primeiro.log`](fase1/e7_rodada5_base_primeiro.log)

| Cargo | Vagas aptas no Brasil | Resultado |
|---|---|---|
| Coordenador de Projetos | 5 | ✘ nenhuma empresa com CNPJ seguro |
| Assistente Social | 30 | ✔ 3 vagas (21 consultas) |
| Psicólogo | 16 | ✔ 3 vagas |
| Auxiliar de Serviços Gerais | 44 | ✔ 3 vagas |
| Auxiliar Administrativo | 36 | ✔ 3 vagas |
| Orientador Socioeducativo | 3 | ✘ 2 de 3 ("CEJA Brasil": 81 empresas com "CEJA" no nome) |
| Designer Gráfico | 19 | ✔ 3 vagas |

- **5 de 7 cargos** fecham na hora, e agora **todo 🟢 tem nome único confirmado na base oficial** (ou é único no município da vaga).
- A rodada sem base fechava 6 de 7, mas com 🟢 que depois se mostraram homônimos (ex.: "Clave de Sol", loja de roupas).
- **Os 2 cargos que não fecham têm título raro.** O banco de vagas (D7) resolve com o tempo, porque cada vaga boa encontrada fica guardada por 180 dias.
- O Gemini (D12) poderá ajudar em casos como "CEJA Brasil": a atividade da empresa encontrada (centro educacional jovem aprendiz) combina com a vaga (orientador socioeducativo).

### 10.8 Próximos passos

1. **Você:** criar a chave do Gemini ([`GEMINI_PASSO_A_PASSO.md`](GEMINI_PASSO_A_PASSO.md)) e me avisar. Eu rodo o teste de acerto da IA (13 casos-armadilha) antes de ligá-la no motor.
2. **Implementar a v0.3 no sistema**, quando você autorizar:
   - tarefas em segundo plano com **barra de progresso**, situação por fonte, aviso de travamento e de "resultado incompleto", botão cancelar e impedimento de suspensão;
   - **vagas do Brasil** com título exato + CNPJ pela base (e online só quando precisar) + **banco de vagas diário**;
   - **cesta** com EAN, estoque no CEP, identidade estrita, trocas justificadas e **teto por rubrica**;
   - **atualização mensal automática** da base da Receita;
   - carrinho do Tenda com quantidade; Gemini só nos casos 🟡, com registro no histórico.
3. **Papelaria:** continuar procurando uma 3ª loja com o mesmo catálogo de Lepok e Gimba (marcas Bacchi, ACC, BIC, Dello, Post-it) e estoque no CEP. Enquanto não houver, a papelaria sai **parcial e com aviso**, respeitando a sua regra de mesma marca.

---

## 11. Teste da regra nova: cada item orçado nas SUAS 3 lojas (27/09)

**Pedido:** esquecer a regra de "todos os itens nas mesmas 3 lojas". Cada item é procurado em todas as lojas; os que existirem, idênticos, em 3 lojas quaisquer entram no orçamento, cada um com os seus fornecedores, e depois vão para a rubrica correspondente.

### 11.1 A SEJC tem algum impedimento? Não encontrei nenhum.

Li os 8 pareceres (inclusive o texto do Parecer 8) e a Grade Comparativa aceita:

| Evidência | O que mostra |
|---|---|
| **Grade Comparativa de Preços** (modelo da própria SEJC) | cada **subitem** tem as suas 3 colunas de **fornecedor e CNPJ**; a grade é feita item a item |
| **Banana Chips no Parecer 8** | orçada em 3 lojas **próprias** (Mercado Janko, Nutrição e Saúde, Bonança), diferentes das lojas dos outros itens da rubrica (Carrefour, Tenda, Atacadão). A 8ª análise **não fez nenhuma objeção** |
| Pareceres 2 e 3 | "após a celebração do ajuste, a organização proponente terá autonomia para definir o fornecedor, desde que observadas as disposições da Lei nº 13.019/2014". As lojas do orçamento são **referência de preço**, não o lugar da compra |
| Pareceres 1, 2 e 4 | o que é exigido **por item**: 3 pesquisas com as **mesmas quantidades e especificações**, valor de **cada produto** discriminado, fornecedores identificados (nome e **CNPJ**) |

**O que continua valendo para cada item:**
- 3 empresas **diferentes**, ativas e identificadas pelo CNPJ;
- mesmo produto e mesma quantidade nas 3;
- evidência datada (válida por 180 dias);
- preço do plano ≤ média.

**Cuidados:**
- mais lojas significam mais comprovantes e mais CNPJs para conferir. O sistema faz isso automaticamente, mas o pacote enviado fica maior;
- o critério de escolha das 3 lojas precisa ser **neutro e registrado**, para não parecer escolha de lojas para mexer na média. No teste: EAN primeiro, depois carrinho automático, depois o menor preço.

### 11.2 Resultado medido: trio único × por item — logs [`e16_por_item_limpeza_papelaria.log`](fase1/e16_por_item_limpeza_papelaria.log) e [`e16_por_item_alimentacao.log`](fase1/e16_por_item_alimentacao.log)

Mesmas regras de identidade (mesmo produto e mesma marca, D11). Cada item procurado em 13 lojas (alimentação: nas 8 que vendem alimentos).

| Cesta | Trio único (melhor entre todas as lojas) | **Por item** |
|---|---|---|
| Limpeza (6 itens) | 6/6 · 1 troca · **0** itens com EAN nas 3 lojas · 3 lojas | **6/6 · 0 trocas · 4 com EAN nas 3** · 6 lojas |
| Alimentação (14) | 10/14 · 0 trocas · **0** com EAN nas 3 · 3 lojas | **13/14 · 1 troca · 9 com EAN nas 3** · 7 lojas |
| Papelaria (9) | 2/9 · 3 lojas | **4/9** · 2 trocas · 2 com EAN nas 3 · 8 lojas |
| **Total (29)** | **18 itens** · 0 com EAN nas 3 | **23 itens · 15 com EAN nas 3** |

**O que melhora com a regra por item:**
- **mais itens** no orçamento (23 × 18);
- **mais certeza de que é o mesmo produto:** 15 itens confirmados por código de barras nas 3 lojas, contra nenhum;
- **menos trocas estranhas:** a geleia volta a ser de **morango** (Queensberry), e não de pimenta; a sardinha volta a ser **com tomate**; o sabão em pó é o de **1,6 kg**, e não 800 g.

**O que piora ou exige cuidado:**
- **Preço mais alto:** limpeza R$ 501 × R$ 366; alimentação R$ 1.978 para 13 itens × R$ 1.245 para 10. O motor hoje escolhe primeiro o EAN e só depois o preço, e as lojas com EAN (Sam's, Oba) às vezes são mais caras. **Correção na implementação:** o otimizador do teto passa a escolher entre os produtos e trios válidos de cada item, e não só entre preços.
- **Mais lojas e mais comprovantes:** 13 lojas diferentes no projeto, contra 6. O sistema gera os comprovantes sozinho (carrinho automático em 7 lojas e PDF da página do produto nas demais), mas o pacote enviado à SEJC fica maior.
- **Papelaria continua limitada:** pasta sanfonada, grampeador, perfurador, clips e caneta **não existem idênticos em 3 lojas quaisquer** das 13, com estoque no CEP. Na grade que a SEJC aceitou, essas linhas tinham marcas diferentes.
- **Banana Chips:** nenhuma das 13 lojas grandes tem o mesmo produto em 3; a SEJC aceitou lojas pequenas (empórios de produtos naturais). Busca por lojas especializadas fica como próximo passo.

### 11.3 Vale a pena implementar? **Sim, como regra padrão**, com 4 ajustes

1. **Por item como padrão:** para cada item, o mesmo produto em 3 empresas diferentes. Se várias lojas tiverem, o critério é neutro e registrado: EAN, depois carrinho automático, depois o menor preço.
2. **Teto por rubrica escolhendo produto e trio:** entre as opções válidas de cada item, o otimizador pega as que fecham o teto com menos trocas. Isso resolve o preço mais alto.
3. **Agrupar as compras por loja:** um carrinho por loja com todos os itens que ela orça. Menos comprovantes, e a evidência continua sendo por item.
4. **Trio único como opção**, para quem preferir menos lojas e aceitar menos itens.

## 12. v0.3 implementada: testes de ponta a ponta na tela (27/09)

Teste com os dados do Parecer 8 (projeto de exemplo), rubrica **Limpeza** (6 itens), pelo sistema, do botão "Pesquisar produtos" até o Excel. Cada problema encontrado foi corrigido e testado de novo.

### 12.1 O que os testes pegaram e o que mudou

| Problema encontrado | Correção | Conferido em |
|---|---|---|
| **Atacadão:** o carrinho marcou o desinfetante "Indisponível", embora a simulação no CEP dissesse que havia estoque. Motivo: a loja não junta no mesmo carrinho produtos de centros de distribuição diferentes (`maxNumberOfSellersReached`). O sistema não percebia | o carrinho é dividido automaticamente: 2 carrinhos, os dois sem item indisponível | carrinhos reais: 1º com água sanitária (5) e sabão (3), subtotal R$ 106,20; 2º com desinfetante (2), R$ 42,60 |
| **Carrefour:** 3 de 5 páginas de produto saíram com a tela "Oops!" da loja (bloqueio 403 na 1ª visita sem cookies) | todo PDF é **conferido** (tela de erro, página vazia, produto indisponível, preço ausente) antes de valer; passa pela página inicial antes e recarrega na mesma sessão | 5/5 páginas boas no teste seguinte |
| **Carrefour pediu verificação humana (CAPTCHA)** depois de muitos acessos de teste. Numa busca, isso pareceria "produto não existe" | detecção de bloqueio: a loja sai da tarefa com aviso claro, **sem tentativa de resolver o CAPTCHA**, e os itens dela vão para **lojas reserva** (mesmo produto). Intervalo mínimo entre acessos à mesma loja | "Aplicar" com o Carrefour bloqueado: água sanitária e desinfetante foram para o Tenda automaticamente |
| **Tenda:** com o CEP informado, o sabão Tixan Maciez aparece como **"Produto indisponível"**. A busca sem CEP o aceitava | o estoque do Tenda é **por filial**: o sistema descobre a filial que atende o CEP (03977-015 → São Mateus) e só aceita produto com estoque nela | Tixan Maciez recusado; Tixan Primavera aceito |
| **Tenda sem carrinho automático** (só página do produto, com o aviso de CEP cobrindo o preço) | **carrinho real do Tenda**: CEP, produto adicionado pelo card da busca, quantidade digitada no carrinho. O preço vem do subtotal da linha ÷ quantidade, porque a partir de 2 unidades vale o preço de atacado | carrinho real: água sanitária 5 × R$ 15,49; sabão 3 × R$ 16,59 (atacado; R$ 18,59 riscado) |
| **IA:** o Gemini respondeu uma vez com uma lista `[{...}]`; o sistema não entendeu e **desligou a conferência de todos os itens** | lista de 1 item é aceita; uma falha não desliga os outros itens; erro passageiro (5xx) ou resposta cortada = nova pergunta | IA conferiu todos os itens 🟡 |
| **IA rígida demais:** recusou "PT 1 UN" (unidade de venda) e "Coperalcool + Bacfree" (fabricante + marca), e com isso tirou o Álcool 1L | instrução revisada e testada antes: **19/21** contra **16/21** da anterior, sem afrouxar nenhum caso "diferente". A anterior chegou a aceitar leite **Desnatado** junto de **Integral** ([`e17_gemini_instrucao.py`](fase1/e17_gemini_instrucao.py)) | Álcool Chá Branco confirmado; saco de lixo "Oceano" continua reprovado |
| Item retirado aparecia como "sem o mesmo produto em 3 lojas" quando, na verdade, a IA tinha reprovado as opções | a proposta mostra "reprovado pela IA", com os anúncios e o motivo | tela da proposta |
| Produto que **saiu do catálogo** do Tenda horas depois da pesquisa (o carrinho não conseguiu adicionar) | loja reserva; se não houver, a **próxima opção** do item, sem piorar o item (não troca 1,6 kg por 800 g), dentro do teto e com a IA nos casos 🟡. O anúncio fica marcado como indisponível no dia, e a próxima pesquisa não o escolhe | Álcool: Chá Branco → Zulu (Tenda, Kalunga, Gimba), comprovantes nas 3 |
| **Banco de vagas:** a coleta falhou na 1ª vaga porque a pasta do banco não existia | a pasta é criada; falha de disco numa vaga não derruba a coleta | coleta completa: 3 vagas 🟢 com PDF |
| **Vaga com salário ambíguo:** a Orsegups informa R$ 2.000,00 no anúncio, mas o texto diz "Salário: R$ 1.727,27 + gratificação" | vaga cujo texto diz um salário diferente do informado fica de fora (a pesquisa salarial tem de ser inequívoca). As vagas já guardadas são reavaliadas com as regras atuais | Orsegups saiu; entrou Souza Lima (São Paulo) |

### 12.2 Resultado do teste da rubrica Limpeza (com o Carrefour bloqueado por CAPTCHA)

| Item | Produto e lojas | Comprovantes |
|---|---|---|
| Água sanitária 5L | Ypê (EAN) · Sam's, Atacadão, **Tenda** (reserva no lugar do Carrefour) | 3 carrinhos reais |
| Desinfetante 5L | Ypê Bak Lavanda (EAN) · Sam's, Atacadão, **Tenda** (reserva) | 3 carrinhos reais |
| Sabão em pó 1,6 kg | Omo Lavagem Perfeita (IA confirma) · Americanas, Carrefour, Gimba | 2 automáticos; **Carrefour pendente** (CAPTCHA; a única alternativa era um pacote de 800 g) |
| Detergente 500 mL | Ypê Clear (próxima opção; o Limpol ficou sem comprovante no Carrefour) · Atacadão, Tenda, Gimba | 3 automáticos |
| Álcool 1L | Zulu com bicarbonato (próxima opção) · Tenda, Kalunga, Gimba | 3 automáticos |
| Sacos de lixo 50 L | a única opção em 3 lojas misturava a linha "Oceano" (IA reprovou) | pendência para a sua decisão |

O Excel sai com o fornecedor e o CNPJ de cada preço, subitem a subitem. Divergências entre o preço da pesquisa e o do carrinho ficam registradas; **vale o carrinho**.

### 12.3 "Pesquisar tudo" no projeto inteiro (1 clique, 2 h 35 min, sem travar)

| Etapa | Resultado |
|---|---|
| Vagas (7 cargos) | **5 cargos com 3 vagas** (título exato, CNPJ 🟢, PDF). Orientador socioeducativo: 2 de 3. Coordenador de projetos: 0 de 3. Esses dois continuam no banco de vagas (coleta diária); as pesquisas do plano não são trocadas enquanto não houver 3 |
| Papelaria (9 itens) | 5 itens com o mesmo produto em 3 lojas (2 por troca). Pasta sanfonada, grampeador, perfurador e caneta continuam sem o mesmo produto em 3 lojas |
| Alimentação (14) | 12 itens. Suco de uva: a IA reprovou as 2 opções. Banana chips: sem o mesmo produto em 3 lojas grandes |
| Limpeza (6) | 5 itens (sacos de lixo: IA reprovou a única opção) |

**Mais problemas encontrados e corrigidos:**

| Problema | Correção |
|---|---|
| A rubrica **"Sistema de gestão de dados"** (serviço) foi procurada nas lojas de produtos. Nada se perdeu (as 3 cotações originais ficaram), mas a justificativa foi trocada e apareceu um falso "resultado incompleto" | rubrica de **serviço** (sistema, software, licença, locação, consultoria, transporte…) fica fora da pesquisa de produtos; a tela explica que o orçamento é com 3 fornecedores do serviço |
| **Americanas:** um item com limite de quantidade por cliente (água de coco: 20 no plano) invalidou o carrinho inteiro (0/3 comprovantes) | item com quantidade diferente da pedida é separado, como os indisponíveis. Os outros itens ficam com carrinho próprio, e o item limitado vai para a loja reserva |
| A busca direcionada por marca montou a consulta "chips malu (malu chips)". A API das lojas VTEX recusa parênteses (HTTP 400), e isso aparecia como falha da loja | as consultas saem sem os símbolos que as lojas recusam |
| "Bloco de notas **4 Cores**" foi trocado por um bloco **Rosa**, e a justificativa só dizia "perdeu: notas" (palavra que está nos outros 2 anúncios do mesmo produto) | "4 cores" passa a ser atributo do item: perder isso aumenta a distância da troca e aparece na justificativa. Atributo presente em qualquer um dos 3 anúncios não conta como perdido |

## 13. v0.4 em uso: o que a OSC apontou em 01/10 e o que os testes de 02/10 mostraram

Tudo abaixo foi testado numa **cópia** dos dados do projeto antes de ir para o projeto real. Testes automáticos: 150.

### 13.1 Pedidos da OSC (01/10) e o que foi feito

| Pedido | Causa encontrada | O que mudou |
|---|---|---|
| Salário das vagas de psicólogo errado (2.001 no lugar de 2.300; 3.001 no lugar de 3.000) | A Catho informa nos dados da vaga só a **faixa cadastrada** (2.001 a 3.000); a página mostra o salário real | Vale o salário que a **página** mostra, que é o que o PDF comprova. As 11 pesquisas da Catho do projeto foram corrigidas na mesma vaga (versão 53) e o banco de vagas também (9 vagas) |
| O plano do sistema não deve ser o mais barato: deve seguir as ferramentas da F&D Solutions | A regra anterior pegava o plano pago mais barato de cada sistema | As 12 ferramentas da proposta da F&D viram a **referência**. A IA só compara (ferramenta de referência → recurso da página → planos que o incluem), em **duas leituras**; vale o que as duas dizem. A escolha é uma **regra fixa**: o plano com mais ferramentas de referência e, no empate, o mais barato. A comparação fica guardada, então o resultado não muda de um dia para o outro |
| Proposta da F&D em PDF, sem link | Não havia como anexar PDF a um preço nem deixar o link vazio | Tela da rubrica: empresa, CNPJ, data e produto de cada pesquisa são editáveis; PDF anexável por preço; link opcional. A proposta foi anexada ao item 13 (versão 49) |
| Link do suco de uva da Coop abre carrinho vazio | O endereço guardado era o do carrinho, que só existe na sessão em que foi montado | O endereço guardado é o da página do produto. 15 endereços do projeto real foram trocados sem refazer a pesquisa (versão 52) |
| PDFs de carrinho com vários itens (café, água de coco, pão Panco) | Eram carrinhos de 27/09, anteriores à regra "um item por PDF"; como tinham 3 comprovantes, o "Pesquisar tudo" os pulava | Carrinho antigo com vários itens e endereço de carrinho contam como **pendentes** e são refeitos |
| Links da Catho com erro 403 | Não reproduzido: a mesma vaga abre no navegador deste computador, inclusive logo depois de uma coleta. A Catho devolve 403 a programas que não são navegador | 3 s entre acessos à mesma plataforma; os links do sistema não informam de onde veio o clique |

### 13.2 Item 13 (sistema) no projeto real

| Fornecedor | Plano e preço | Por quê |
|---|---|---|
| F&D Solutions | proposta em PDF, R$ 270,92/mês, sem link | referência (12 ferramentas) |
| Ongsys | Profissional, R$ 499,00/mês | menor plano com "Dashboards" (= relatório com gráficos); o Iniciante (R$ 299) não tem nenhuma das 12 |
| OngFácil | Prata, R$ 320,00/mês | cadastro de beneficiários e controle de frequência já estão no Prata; o Ouro (R$ 490) não acrescenta ferramenta de referência |

Média R$ 363,31; o valor do plano voltou a R$ 270,92 (era o valor até a versão 42). Any3 e Economato ficaram de fora: são sistemas financeiros, com 0 a 2 das 12 ferramentas.

**Atenção:** a proposta da F&D traz o CNPJ 42.274.849/0001-**37**, com dígito verificador inválido; a pesquisa ficou com o 0001-**01**, que é o da base da Receita. A proposta é de 2025 e a data da pesquisa no plano é 26/03/2026, vencida pelos 180 dias: vale pedir uma proposta atualizada.

### 13.3 Teste de ponta a ponta na cópia (02/10): "Pesquisar tudo", 59 minutos

Resultado da 1ª rodada: 30 de 30 subitens com 3 comprovantes, um PDF por item, todos os links abrindo a página do produto. Vagas: 6 de 7 cargos com 3 vagas (Orientador socioeducativo: 2 no banco).

A conferência PDF por PDF, feita depois, achou comprovantes que **não provavam o preço** e que mesmo assim contavam como prontos:

| Problema encontrado | Correção |
|---|---|
| **Tenda:** em 5 itens o site não aceitou o CEP naquele momento; o sistema caiu para a página do produto, que sem CEP mostra o **preço borrado** | sem CEP aceito não há comprovante; o carrinho é tentado de novo depois de uma pausa |
| **Pão de Açúcar:** em 3 itens a página mostrava um preço e a grade outro (leite: R$ 6,79 na página, R$ 6,99 na grade) | vale o preço que a página mostra |
| Comprovante com problema conhecido (preço ausente, "produto indisponível") era guardado como se servisse | todo PDF novo é conferido: o preço registrado tem de aparecer no texto do PDF. Comprovante com problema fica marcado, aparece na tela e o subitem fica **pendente** (é refeito). Comprovantes antigos também são conferidos pelo PDF |
| **Kalunga** pediu CAPTCHA no meio da busca, mas anúncios já lidos dela entraram na proposta e o sistema voltou à loja para os comprovantes | os anúncios da loja que barrou saem das opções; os comprovantes não voltam a ela |
| **Afonso Ruotolo** limitou os acessos (erro 429) e foi descartada por 30 dias, como se fosse CAPTCHA | limite de acessos não é CAPTCHA: a loja descansa até o dia seguinte; o intervalo entre acessos a ela subiu para 2,5 s |
| A IA oscilava na escolha do plano do OngFácil (Ouro numa rodada, Prata na outra) | duas leituras + regra fixa + resposta guardada (13.1) |
| A cota gratuita do dia do modelo mais forte da IA acabou e todas as perguntas ficaram sem resposta | a pergunta segue no modelo seguinte |
| Cargo com menos de 3 vagas no banco (Orientador socioeducativo) ficava com o salário antigo da Catho | o salário é corrigido na própria pesquisa, pela página guardada |
| "Salário: a combinar" de uma vaga parecida, listada no fim da página, derrubava a vaga certa (Coordenador de Projetos) | só conta o "a combinar" que aparece antes do salário da vaga |
| O trio de produtos montado pela IA não tinha loja reserva (caneta sem comprovante na Kalunga) | a IA indica também anúncios reserva, de outras empresas |
| **Tenda:** quando o campo de quantidade do carrinho não aceitava a digitação (ficava em 1), o sistema entendia como limite de compra e **reduzia a quantidade do item** (desinfetante: de 2 para 1) | a quantidade é conferida e digitada de novo até 3 vezes; se continuar em 1, é falha do site, não limite: a quantidade do plano não muda e o item vai para a loja reserva |

Observação: em 02/10 o Pão de Açúcar respondeu que **não entrega** no CEP 03977-015 (em 01/10 entregava). O sistema o deixou de fora, com aviso.

### 13.4 Segunda rodada na cópia, já com as correções (22 minutos)

| Etapa | Resultado |
|---|---|
| Vagas | 7 de 7 cargos prontos, sem nova coleta: 3 salários corrigidos na própria pesquisa (Perseverança: R$ 2.001 → R$ 2.407) |
| Produtos | só os 9 subitens com comprovante que não provava o preço foram refeitos; os outros 21 ficaram como estavam |
| Conferência PDF por PDF | **28 de 30** subitens com os 3 comprovantes válidos (um item por PDF, link do produto, preço presente). Nenhum comprovante inválido contado como pronto |
| Pendentes, com aviso na tela | Leite 1L (o Sam's Club aceita no máximo 8 unidades; o plano pede 20) e Sacos de lixo 50L (o produto não entrou no carrinho do Tenda). Ficam para a próxima rodada ou para um PDF anexado à mão |

### 13.5 Estado do projeto real em 02/10 (versão 53)

- Mão de obra: 11 de 11 itens prontos, com os salários que as páginas mostram.
- Item 13 (sistema): pronto (13.2).
- Produtos: 5 de 30 subitens prontos. Os outros 25 têm carrinho antigo com vários itens, comprovante sem o preço registrado ou ainda não foram achados; o "Pesquisar tudo" os refaz (cerca de 1 hora).
- A Kalunga pediu CAPTCHA durante o teste e está descartada até 01/11/2026 (dá para reativar na configuração do projeto).

