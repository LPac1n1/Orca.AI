# Fase 1 — Pesquisa e testes da automação total (vagas, materiais, produtos)

> **Continuação (26/09/2026):** resultados dos novos testes (vagas do Brasil + CNPJ automático, cesta por código de barras, carrinho do Tenda, IA gratuita) e decisões D7–D12 em [`FASE1B_RESULTADOS.md`](FASE1B_RESULTADOS.md).

**Data:** 25/09/2026 · **Base:** [PROMPT.md](PROMPT.md) §6–§9, §17–§20, §42 · **Scripts e dados:** [`fase1/`](fase1/)
**Nada foi alterado no sistema.** Este relatório traz os resultados medidos e as possibilidades para você decidir.

Legenda: 🟢 validado na prática · 🟡 parcial · 🔵 só documentação · 🔴 não funcionou

---

## 1. Resumo

| Pergunta | Resposta medida |
|---|---|
| A busca de vagas pode ser 100% automática com **título exato**? | **Sim, para 6 de 7 cargos em São Paulo** (3 a 32 empresas distintas por cargo). O 7º teve falha de fonte; no Brasil inteiro deu 32 empresas. Falta automatizar o **CNPJ do empregador** |
| O CNPJ do empregador pode ser achado sozinho, pelo nome? | Sem baixar nada: só a busca Brave acertou (6 de 8), mas bloqueia depois de algumas consultas 🟡. **Com a base oficial da Receita baixada** (gratuita, ~6,4 GB), a busca por nome fica offline e sem limite 🔵 (não baixei: precisa da sua autorização) |
| A cesta de materiais pode ser 100% automática a partir só da descrição? | **Parcialmente.** Limpeza e alimentação chegam perto; papelaria ainda não. Nenhum trio completo de lojas foi formado sem ajuste. Os motivos e as soluções estão abaixo |
| O que mais pesa? | **Regra de identidade:** exigir "mesmo produto" (marca igual) derruba a cobertura. **A SEJC aceitou marcas diferentes na papelaria** (mesma especificação). Isso é decisão sua (§4 do prompt: "necessidade de mesma marca") |
| Os processos travam? | **Sim, sem limite de tempo:** uma rodada levou **85 minutos** por páginas travadas; com limite de 75 s por busca + 1 nova tentativa, a mesma rodada levou **152 s, sem falhas**. Também houve bloqueios intermitentes (conexão recusada) resolvidos com nova tentativa |

---

## 2. Vagas

### 2.1 Regra de título exato — 🟢 33/33 casos ([`titulo_exato.py`](fase1/titulo_exato.py))

Aceita só variações das mesmas palavras: gênero ("Coordenador(a)", "Coordenadora"), singular/plural ("Projeto/Projetos"), acentos, maiúsculas, "/a". Rejeita qualquer palavra a mais ou a menos.

| Aceita | Rejeita |
|---|---|
| Coordenador(a) de Projetos · Coordenadora de Projeto · Coordenadores de Projetos | Coordenador de Projetos **de TI** · **de Logística** · **Sociais** · **- São Paulo** · **Sr** |
| Psicóloga · Psicólogo(a) | Psicólogo **Clínico** |
| Auxiliar de Serviço Geral | Auxiliar de Serviços Gerais **- Noturno** |
| Orientadora Socioeducativa | Orientador Socioeducativo **(Música)** |

### 2.2 Fontes de vagas testadas ([`sondar_plataformas.py`](fase1/sondar_plataformas.py))

| Fonte | Resultado | Status |
|---|---|---|
| InfoJobs (várias páginas) | Empresa, faixa, data, cidade estruturadas | 🟢 |
| Catho | Idem; faixa aceita pela SEJC (menor valor) | 🟢 |
| LinkedIn (listagem pública, sem login) | Empresa estruturada; salário raro | 🟢 |
| BNE | Parte das vagas com dados estruturados | 🟡 |
| Vagas.com | Muitas vagas sem dados estruturados | 🟡 |
| Indeed | Bloqueado (Cloudflare) | 🔴 |
| Trabalha Brasil, Empregos.com.br, Glassdoor, Solides | Links não identificados no 1º teste | 🔴 (não investigado a fundo) |
| Gupy | API pública mudou | 🔴 |

### 2.3 Rendimento real, título exato, 7 cargos do projeto ([`e1_rendimento_vagas.py`](fase1/e1_rendimento_vagas.py))

Vaga apta = título exato + empresa identificada (não confidencial, não agregador) + salário mensal ≥ R$ 1.000.

| Cargo | Vagas lidas (SP) | Aptas | Empresas distintas | Principal motivo de descarte |
|---|---|---|---|---|
| Coordenador de Projetos | 42 | 3 | **3** (no limite) | título diferente (28) |
| Assistente Social | 50 | 12 | 9 | título diferente, sem salário |
| Psicólogo | 83 | 6 | 5 | título diferente (59) |
| Auxiliar de Serviços Gerais | 20 | 2 | 2 → **Brasil: 32** | **Catho e Vagas.com falharam nessa rodada** |
| Auxiliar Administrativo | 82 | 33 | 32 | título diferente, confidencial |
| Orientador Socioeducativo | 10 | 3 | **3** (no limite) | título diferente |
| Designer Gráfico | 81 | 14 | 14 | título diferente (48) |

Tempo: 40 s a 7 min por cargo (média ~2,5 min). **Todo o projeto, cerca de 15 a 20 minutos.** Por isso a busca precisa rodar em segundo plano, com barra de progresso.

### 2.4 CNPJ do empregador pelo nome ([`e2_cnpj_por_nome.py`](fase1/e2_cnpj_por_nome.py))

Gabarito: 8 empresas da grade do Parecer 8, com CNPJ conhecido.

| Fonte | Acertos (1º resultado) | Observação | Status |
|---|---|---|---|
| **Busca Brave** | **6/8** | Bloqueou após algumas consultas | 🟡 |
| Bing, cnpj.biz, Empresaqui | 0/8 | Nada encontrado | 🔴 |
| Mojeek | 0/8 | Bloqueou e ficou muito lento (435 s) | 🔴 |
| Econodata | 0/8 | **CNPJ errado** nos 8 (perigoso) | 🔴 |
| Casa dos Dados (API) | — | Acesso recusado (403) | 🔴 |
| **Base oficial da Receita (Dados Abertos), baixada** | não testada | Gratuita e mensal: Empresas ~1,3 GB + Estabelecimentos ~5,1 GB compactados; busca por nome offline, sem limite. **Exige autorização para baixar** | 🔵 |

---

## 3. Materiais: cesta 100% automática a partir da descrição

Entrada: só as descrições genéricas do plano (29 itens reais do Parecer 8). Saída esperada: o mesmo produto (ou especificação) em **3 lojas que tenham todos os itens** (§6–§9).

### 3.1 Lojas para o CEP 03977-015 ([`e3a`](fase1/e3a_dados_lojas.py), [`e3b`](fase1/e3b_api_no_navegador.py), [`e3e`](fase1/e3e_mais_lojas.py))

| Loja | Como ler os produtos | EAN | Entrega no CEP | Carrinho automático |
|---|---|---|---|---|
| Atacadão | API aberta | ✔ | ✔ (varia por item) | 🟢 API + captura (Fase 0) |
| Sam's Club | API aberta | ✔ | ✔ | 🔵 mesmo método do Atacadão |
| **Oba Hortifruti** (nova) | API aberta | ✔ | ✔ | 🔵 mesmo método |
| **Drogaria São Paulo / Pacheco** (novas, limpeza) | API aberta | ✔ | ✔ | 🔵 mesmo método |
| Tenda | Bloco de dados da página | ✘ | ✔ | 🟢 3 itens no carrinho + captura; ajuste de quantidade 🟡 |
| Carrefour Mercado | Página de busca renderizada | ✘ | — | 🔴 API bloqueada (403) e página quebra com automação → **PDF impresso por você** (leitor validado 45/45) |
| Americanas | API aberta | ✔ | ✘ para este CEP | — |
| Kalunga | Página de busca | ✘ | — | 🔵 |
| Lepok | Página de busca (`/busca/<termo>`) | ✔ na página do produto | — | 🔵 |
| **Gimba = Supricorp** | Busca direto no HTML (`/?q=<termo>`), sem navegador | ✘ | — | 🔵 |
| Livrarias Curitiba | API aberta | ✔ | ✔ | 🔵 |
| Pão de Açúcar, Nagumo, Dia, Marché, Roldão | Sem API aberta / sem preço sem CEP | — | — | não testado |

### 3.2 Três versões do motor, medidas ([`e3c`](fase1/e3c_cesta_automatica.py), [`e3d`](fase1/e3d_cesta_v2.py), [`e3f`](fase1/e3f_cesta_v3.py))

| Versão | Limpeza (6) | Papelaria (9) | Alimentação (14) | Problema encontrado |
|---|---|---|---|---|
| v1: busca genérica + 1º resultado | nenhum trio | nenhum trio | nenhum trio | Aceitou "pão **tradicional**" por "integral", "**iogurte** de banana" por "banana chips", perfurador de **2** furos por 4 |
| v2: filtro estrito + marca + busca direcionada | 6/6 itens em ≥3 lojas; nenhum trio | 0/9 | 7/14 | **Agrupou produtos diferentes:** manteiga **com sal** × **sem sal**; Tixan **Power Act** × **Primavera**; saco **super econômico** × **reforçado** |
| v3: identidade estrita (🟢/🟡/🔴) | 3/6 itens em ≥3 lojas; melhor trio cobre 2/6 | 0/9 | 4–5/14; melhor trio 2/14 | Grupos corretos, mas cobertura baixa **exigindo a mesma marca** |
| **v3, Nível 2 (mesma especificação, marca livre)** | **melhor trio cobre 5/6** | 4/9 | **melhor trio cobre 10/14** | Faltam itens que as lojas de fato não têm ou que o filtro ainda rejeita por rigidez |

### 3.3 O que impede o trio completo

| Causa | Exemplo real | Tipo |
|---|---|---|
| Produto esgotado ou ausente naquele CEP | Água Sanitária Ypê 5L esgotada na Atacadão; Banana Chips só em 1 loja | real |
| Tamanho específico raro | Pão de forma **480 g** só em 2 lojas; sardinha **125 g** (a Atacadão só tem 75 g) | real, pede substituição (§9, §11) |
| Rigidez do filtro por regras fixas | Caneta "caixa com 50" rejeitada como fardo; grampo "Caixa C/5000"; grampeador que não escreve "26/6" | corrigível, mas cada categoria exige ajuste |
| Falha de leitura | URL de busca errada da Lepok (corrigida); "24/6 e 26/6" (corrigida) | corrigida |

### 3.4 Evidência da Secretaria que muda a regra

Nos carrinhos de papelaria **aceitos pela SEJC**, a mesma linha tem **marcas diferentes**:

| Item | Lepok | Kalunga | Gimba |
|---|---|---|---|
| Pasta sanfonada 12 divisórias | Polibras | Spiral | Plascony |
| Grampeador de mesa | Cis | Spiral | Goller |

Ou seja, **na papelaria a SEJC aceitou "mesma especificação"**. Na limpeza, a organização usou a mesma marca. O seu prompt prevê isso como regra configurável ("necessidade de mesma marca / mesmo modelo / mesmo produto").

---

## 4. Travamentos, falhas e progresso (seu pedido)

| Situação medida | O que aconteceu | Correção testada |
|---|---|---|
| Página travando sem limite | Cesta de papelaria levou **5.090 s** com 38 falhas | Limite de 75 s por busca + 1 nova tentativa → **152 s, 0 falhas** 🟢 |
| Fonte falha e a busca continua calada | Auxiliar de Serviços Gerais: Catho e Vagas.com falharam, resultado com só 2 vagas | Registrar falha por fonte, repetir e **avisar na tela** 🔵 |
| Conexão recusada intermitente | Tenda recusou a conexão; segundos depois respondia | Até 3 tentativas com espera crescente → os 3 itens entraram no carrinho 🟢 |
| Excesso de buscas seguidas | Centenas de buscas nesta sessão; bloqueios pontuais (Brave, Mojeek, Tenda) | Limitar o ritmo por loja e guardar resultados em cache 🔵 |

**Proposta de progresso (não aplicada):** cada busca vira uma "tarefa" em segundo plano, com:

- **barra de porcentagem** e etapa atual (ex.: "Catho, página 2 de 3");
- **situação de cada fonte** (✔ concluída / ⚠ repetindo / ✘ falhou) e tempo decorrido;
- **aviso de travamento** se nada avançar em 60 s, com botão "tentar de novo só esta fonte";
- botão **cancelar**;
- no fim, um resumo claro (ex.: "Catho falhou 2 vezes: os resultados não incluem a Catho").

---

## 5. Possibilidades para chegar à automação total

### Vagas (perto de pronto)
1. Título exato (validado) + InfoJobs, Catho, LinkedIn público e BNE, com 2–3 páginas cada.
2. Se um cargo tiver menos de 3 empresas em São Paulo: **ampliar para o Brasil** (a grade aceita tinha vaga de Brasília).
3. CNPJ do empregador:
   - **(a) Base oficial da Receita baixada:** gratuita, offline e confiável. 🔵 Precisa da sua autorização (~6,4 GB, atualização mensal).
   - (b) Busca Brave: 🟡 funciona, mas bloqueia.
   - (c) Link de busca para você: manual, é o que existe hoje.
4. Captura da página em PDF + consulta da situação cadastral (já validadas).

### Materiais
1. **Regra de identidade por rubrica** (decisão sua):
   - Nível 1, mesmo produto (marca, medida e variante), para quando a secretaria exigir;
   - Nível 2, mesma especificação, como a SEJC aceitou na papelaria.
2. **Motor em duas fases** (descoberta + confirmação direcionada) e **escolha automática do trio** (validado no protótipo).
3. **Quando faltar um item** (§9, §11): o sistema mostra o item gargalo, quantas lojas o têm e sugere alternativas (outro tamanho, outra marca) **para sua aprovação**. Nunca troca sozinho.
4. **Item avulso com 3 fontes próprias**, só para itens raros (a SEJC aceitou para a Banana Chips).
5. **Mais lojas:**
   - alimentação e limpeza: Atacadão, Sam's Club, Oba, Tenda, Drogaria São Paulo e Pacheco, e Carrefour via PDF impresso;
   - papelaria: Kalunga, Lepok, Gimba e Livrarias Curitiba.
6. **Carrinho automático:**
   - por API: Atacadão, Sam's, Oba e drogarias;
   - pelo navegador: Tenda (quantidade ainda a ajustar);
   - via PDF impresso por você: Carrefour;
   - papelarias: ainda a testar.
7. **IA local gratuita (opcional):** resolveria os casos 🟡 e sinônimos de papelaria sem regra por categoria. Precisa baixar um modelo de 2 a 5 GB.

---

## 6. Decisões necessárias antes de implementar

| # | Decisão | Opções | Minha recomendação |
|---|---|---|---|
| D1 | Regra de identidade dos produtos | Mesma marca sempre / **por rubrica** / mesma especificação sempre | **Por rubrica:** limpeza e alimentação tentam mesma marca e caem para mesma especificação com aviso; papelaria usa mesma especificação (como a SEJC aceitou) |
| D2 | Baixar a base oficial da Receita (~6,4 GB, grátis, mensal) para achar CNPJ pelo nome | Sim / Não (continua manual ou Brave) | **Sim**: é a única opção confiável e sem limite |
| D3 | Vagas: se faltar em SP, buscar no Brasil inteiro? | Sim / Não | **Sim**, com aviso na tela |
| D4 | Item raro com 3 fontes próprias (fora do trio) | Permitir com aprovação / Nunca | **Permitir com aprovação** |
| D5 | IA local gratuita (download de 2–5 GB) | Agora / Depois / Nunca | **Depois**: primeiro a versão por regras, medindo o que sobra para revisão |
| D6 | Detalhe das descrições dos itens | Você descreve a especificação / o sistema sugere a especificação a partir do mercado | **O sistema sugere, você aprova** (§10) |

## 7. O que foi testado na prática (esta fase)

| Tecnologia | O que foi testado | Resultado | Status |
|---|---|---|---|
| Regra de título exato | 33 casos, incluindo os seus exemplos | 33/33 | 🟢 |
| InfoJobs, Catho, LinkedIn público | 7 cargos reais, várias páginas | 3 a 32 empresas por cargo | 🟢 |
| BNE, Vagas.com | Idem | Parcial | 🟡 |
| Indeed, Gupy, Glassdoor… | Acesso | Bloqueado ou sem leitura | 🔴 |
| CNPJ por nome (Brave) | 8 empresas com gabarito | 6/8, com bloqueio | 🟡 |
| CNPJ por nome (outras 6 fontes) | Idem | 0/8 (Econodata: 8 errados) | 🔴 |
| Base da Receita | Disponibilidade e tamanho | Existe; não baixada | 🔵 |
| API VTEX (Atacadão, Sam's, Oba, drogarias, Livrarias Curitiba) | Busca + entrega no CEP | Funciona | 🟢 |
| Tenda (dados da página + carrinho) | Busca e carrinho com 3 itens | Funciona; quantidade 🟡 | 🟢/🟡 |
| Carrefour (automação) | API e carrinho | Bloqueado / página quebra | 🔴 → PDF impresso |
| Kalunga, Lepok, Gimba | Busca e extração | Funciona após correções | 🟢 leitura / 🔵 carrinho |
| Cesta automática (29 itens reais) | 3 versões do motor | Nível 2 chega a 5/6 e 10/14 itens por trio; nenhum trio completo sem substituição | 🟡 |
| Identidade de produto v3 | Inspeção dos grupos | Sem os erros da v2 (com/sem sal etc.) | 🟢 |
| Limite de tempo + nova tentativa | Rodada que travava | 5.090 s → 152 s | 🟢 |
| Barra de progresso | — | Proposta, não implementada | 🔵 |
