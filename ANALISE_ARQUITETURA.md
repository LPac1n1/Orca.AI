# Motor de Orçamentação para Projetos Sociais — Análise Estratégica e Tecnológica

> **Atualização (25/09/2026):** a Fase 0 foi concluída. Veja [FASE0_RESULTADOS.md](FASE0_RESULTADOS.md). Ela atualiza este documento em: regra de horas (jornada legal ÷ 6 × 30, no lugar de 180/120 h), matching (EAN + conferência de atributos), descoberta de lojas (busca web de IA + verificação), vagas (armadilhas de CNPJ e de faixa salarial da plataforma) e armazenamento (~1,8 MB por oferta).

**Data:** 25/09/2026 · **Fase:** análise e validação prática. Nada do sistema foi construído ainda.
**Provas de conceito executadas:** 9 (scripts em [`poc/`](poc/), evidências em [`poc/evidencias/`](poc/evidencias/))

Legenda usada em todo o documento:

| Selo | Significado |
|---|---|
| 🟢 **Validado** | Testado nesta análise, com dados reais, e funcionou |
| 🟡 **Parcial** | Testado, mas com limitações ou cobertura incompleta |
| 🔵 **Documentação** | A ferramenta declara a capacidade; **não foi testada** aqui |
| 🔴 **Não validado / falhou** | Testado e falhou, ou impossível confirmar |

---

## 0. Resumo executivo

**Recomendação:** um núcleo **determinístico em código próprio (Python)** para regras, cálculos, otimização, evidência e auditoria, com a **IA atuando como ferramenta controlada** (pesquisar, extrair, comparar e explicar), nunca como a fonte de um número. Os dados ficam em **PostgreSQL** (Supabase ou equivalente), a captura de páginas em **Playwright**, a otimização em **OR-Tools CP-SAT** e o CNPJ em **APIs públicas com fallback**. Ferramentas no-code servem só para cola e agendamento, nunca para o núcleo.

**Por que essa arquitetura (com base nos testes, não na teoria):**

1. **O identificador EAN/GTIN resolve a regra "mesmo produto" de forma determinística.** O mesmo EAN `7891173023001` (Chamex A4 75g 500 fls) foi encontrado em 7 lojas com **7 títulos diferentes**. Sem o EAN, o matching só por regras teve **1 falso positivo perigoso em 25 casos**.
2. **O fechamento exato no teto funciona e é instantâneo** (200 itens em 0,3 s). Porém, com preço unitário = média e poucos itens, **muitas vezes o fechamento é matematicamente impossível**. No teste, com teto de R$ 9.000,00, os valores alcançáveis mais próximos foram R$ 8.999,98 e R$ 9.000,01. Isso é uma **decisão administrativa** (ver §13), não um problema de software.
3. **O teste integrado encontrou um bug que nenhum teste isolado encontraria:** com só 2 lojas disponíveis, a média foi dividida por 3 (R$ 29,63 em vez de R$ 44,45). Um sistema que precisa ser comprovado perante uma secretaria exige **invariantes verificadas por código**, e isso descarta arquiteturas em que um agente de IA ou um fluxo no-code "decide" os números.
4. **O acesso às lojas é heterogêneo.** Das 12 lojas testadas em modo headless, 4 entregaram preços; 3 bloquearam (HTTP 403); 1 exigiu login; 1 deu falso "sem resultados". Portanto, a pesquisa precisa de **fontes em camadas com fallback**, incluindo a captura manual assistida.
5. **A consulta de CNPJ é o módulo mais maduro:** 5 APIs gratuitas responderam em cerca de 1 s. Um CNPJ **BAIXADO** foi detectado corretamente. Os limites reais de taxa foram medidos (3 consultas/min em duas delas).

**O que ainda NÃO foi validado e precisa ser antes de implementar:** matching por LLM via API (não havia chave no ambiente), deduplicação de vagas, busca de lojas por EAN em motores de busca, ferramentas no-code/low-code (n8n, Bubble, Supabase etc.) e aceitação do pacote de evidências por uma secretaria real.

---

## 1. O problema reformulado em termos de arquitetura

O sistema é um **pipeline de decisão auditável** com seis naturezas de trabalho diferentes:

| Natureza | Exemplo no sistema | Característica técnica |
|---|---|---|
| **Coleta não confiável** | buscar produtos, preços e vagas na web | fontes instáveis, bloqueios, páginas que mudam → precisa de retry, fallback e evidência |
| **Julgamento semântico** | "estes dois anúncios são o mesmo produto?" | ambíguo por natureza → IA + regras + humano no caso incerto |
| **Regras configuráveis** | "3 fontes, mesma marca, CNPJ ativo, validade de 90 dias" | dados, não código → motor de regras declarativo e versionado |
| **Cálculo exato** | médias, horas proporcionais, totais | determinístico, em centavos inteiros, reprodutível |
| **Otimização combinatória** | fechar exatamente no teto | problema de programação inteira → solver com prova de inviabilidade |
| **Prova documental** | PDF, captura, HTML, hash, trilha de auditoria | armazenamento imutável + cadeia de proveniência |

**Princípio arquitetural derivado dos testes:** *nenhum número que chega ao orçamento final pode ter sido escrito por um LLM.* Todo preço é extraído por código a partir de uma resposta de API ou página salva (com hash). O LLM só pode **apontar** para ofertas existentes (por ID) e **classificar** correspondências. O código valida cada saída do LLM contra os dados reais.

Isso transforma o requisito "a IA nunca deverá inventar preços" de uma **instrução ao modelo** (frágil) em uma **propriedade estrutural do sistema** (verificável).

---

## 2. Módulos do sistema e dificuldade

| # | Módulo | Dificuldade | Quem executa | Observação baseada em teste |
|---|---|---|---|---|
| M1 | Projetos / Orçamentos / Itens (CRUD, duplicar, arquivar) | 🟩 Baixa | Código | Padrão de mercado |
| M2 | **Motor de regras** (por orçamento, com templates por secretaria/edital) | 🟨 Média | Código + IA sugere | IA pode ler o edital e *propor* regras; o humano aprova |
| M3 | Planejamento de itens e quantidades | 🟨 Média | IA sugere → humano aprova | Não testado 🔵 |
| M4 | **Descoberta de fontes** (quais lojas têm o produto) | 🟥 Alta | API + scraping + busca | VTEX por EAN 🟢; busca aberta por EAN 🔴 não testada |
| M5 | **Coleta de ofertas** (preço, disponibilidade, atributos) | 🟥 Alta | API > scraping > LLM > humano | 4/12 lojas via headless; 7 via API VTEX |
| M6 | **Matching de produtos** 🟢🟡🔴 | 🟥 Alta | EAN → regras → LLM → humano | Regras: 21/25; EAN: determinístico |
| M7 | Seleção das 3 lojas | 🟩 Baixa | Algoritmo | Testado no fluxo integrado |
| M8 | Diagnóstico de lacunas (item gargalo, sugestão de substituto) | 🟨 Média | Algoritmo + IA sugere substituto | Gargalo identificado 🟢; sugestão de substituto 🔵 |
| M9 | Cálculo de médias e totais | 🟩 Baixa | Algoritmo | **Bug de integração encontrado** → invariantes |
| M10 | **Otimização (4º orçamento = teto exato)** | 🟨 Média técnica / 🟥 Alta administrativa | Solver CP-SAT | 🟢 validado em 10 casos |
| M11 | Pesquisa de vagas | 🟥 Alta | Scraping + LLM | 4 de 8 plataformas acessíveis |
| M12 | Deduplicação de vagas | 🟨 Média | Algoritmo + LLM | 🔴 não testada |
| M13 | Cálculo de mão de obra (horas proporcionais) | 🟩 Baixa | Algoritmo | Regra de horas precisa de decisão (§13) |
| M14 | CNPJ (identificação + situação) | 🟩 Baixa | API | 🟢 5 provedores; rodapé 6/7 |
| M15 | **Evidências** (PDF, PNG, HTML, JSON, hash, data/hora) | 🟨 Média | Playwright | 🟢 PDF com carimbo de URL e data/hora |
| M16 | **Rastreabilidade e histórico** (log de eventos imutável) | 🟨 Média | Código/BD | SQLite 🟢 no PoC; desenho em §8 |
| M17 | Revisão humana item a item (UI) | 🟨 Média | Front-end | Não testado |
| M18 | Dashboard e alertas | 🟩 Baixa | Front-end | — |
| M19 | Exportação (PDF, Excel, Word, ZIP) | 🟩 Baixa | Bibliotecas | 🔵 bibliotecas maduras, não testadas aqui |
| M20 | Validade das pesquisas / re-execução | 🟩 Baixa | Agendador | — |

**Os três módulos que decidem se o projeto dá certo:** M5 (coleta), M6 (matching) e M15/M16 (evidência e rastreabilidade). A otimização (M10) é tecnicamente resolvida; o desafio dela é de **regra de negócio**.

---

## 3. O que foi testado na prática

### 3.1 Tabela-resumo de validação

| Tecnologia | O que foi testado | Resultado | Limitações | Status |
|---|---|---|---|---|
| **BrasilAPI** (CNPJ) | 6 CNPJs (4 ativos, 1 baixado, 1 inválido) | 100% de respostas, ~0,5–0,9 s, situação correta incluindo **BAIXADA** | Sem limite atingido no teste; é espelho dos dados abertos, não comprovante oficial | 🟢 |
| **MinhaReceita** (CNPJ) | mesmos casos | 100%, ~0,6–1,2 s | idem | 🟢 |
| **CNPJá Open** (CNPJ) | mesmos casos | OK até 429 na 5ª chamada rápida | limite de taxa baixo | 🟡 |
| **CNPJ.ws pública** | mesmos casos | 2 OK, depois 429 ("máximo de 3 consultas por minuto") | 3/min | 🟡 |
| **ReceitaWS** | mesmos casos + rajada de 5 | 2 OK, depois 429 persistente | 3/min | 🟡 |
| Validação local de DV do CNPJ | CNPJ com dígito inválido | Rejeitado sem chamada de rede | — | 🟢 |
| **Playwright headless** (lojas) | 12 lojas, busca "papel sulfite chamex a4 75g 500 folhas" | Preços extraídos em **4/12** (Kalunga, Amazon, Americanas, Atacadão) | 403 em Magalu, Casas Bahia e Leroy; login no Mercado Livre; certificado inválido em 1; 404 em 1 (URL); Carrefour e Shopee sem preço | 🟡 |
| **API pública VTEX** (catálogo) | 30 domínios de varejo BR | 11 respondem; retorna **EAN, preço, estoque e URL** em ~1 s | Nem toda loja é VTEX; Carrefour e Assaí bloqueiam a API (403) | 🟢 |
| Busca VTEX **por EAN** (`fq=alternateIds_Ean`) | 4 EANs × 10 lojas | Funcionou; ofertas exatas por EAN | Um EAN informado por mim estava errado → 0 resultados (ver §4.4) | 🟢 |
| **Matching determinístico** (regex + atributos + rapidfuzz) | 25 pares difíceis (marca, gramatura, folhas, caixa, cor, ponta, volume, formato, cm) | **21/25 corretos; 1 falso positivo perigoso** (tesoura 13 cm × 21 cm → verde) | Depende de dicionário de atributos por categoria | 🟡 |
| **Matching por EAN** | 7 ofertas do mesmo EAN com títulos diferentes | 100% agrupadas corretamente | Só quando a fonte expõe EAN | 🟢 |
| **Matching por LLM** | — | **Não testado via API** (sem chave no ambiente) | — | 🔴 |
| **OR-Tools CP-SAT** | 10 casos (ver §3.5) | Fechamento exato em centavos; provas de inviabilidade; 200 itens em 0,3 s | Objetivo precisa ser bem definido (ver C4) | 🟢 |
| **Playwright PDF/PNG/HTML** | Evidência de página de produto | PDF de 2 páginas com cabeçalho "EVIDÊNCIA data/hora + URL"; preço R$ 41,90 presente no texto do PDF; SHA-256 registrado | Imagem do produto não carregou (lazy load); banner de cookies cobre parte da página | 🟢 |
| Conferência **preço da API × preço na página** | 2 lojas | Iguais (R$ 41,90 e R$ 46,99) | Amostra pequena | 🟡 |
| **CNPJ pelo rodapé da loja** | 7 lojas | **6/7** encontrados após rolar a página | 1 loja sem CNPJ no rodapé; marketplace ≠ vendedor | 🟡 |
| **Vagas** (Playwright) | 8 plataformas, "auxiliar de limpeza" em São Paulo | Salários extraídos: **InfoJobs, Catho, BNE, Vagas.com** | Indeed bloqueado (Cloudflare 403); LinkedIn exige login; Glassdoor e Gupy sem salário | 🟡 |
| Deduplicação de vagas | — | Não testado | — | 🔴 |
| **Fluxo integrado** (API → EAN → filtro → seleção → médias → evidência → CNPJ → BD) | 10 lojas × 4 produtos | Rodou em 51,7 s; 27 ofertas gravadas; gargalo identificado; **bug de média encontrado** | Nenhuma loja tinha os 4 itens → caminho de falha exercitado (útil) | 🟡 |
| SQLite (armazenamento de ofertas com hash) | Fluxo integrado | OK | PoC apenas | 🟢 |
| n8n, Make, Zapier, Power Automate | — | Não testado | — | 🔵 |
| Supabase, Airtable, Google Sheets | — | Não testado | — | 🔵 |
| Bubble, Retool, AppSheet, Softr | — | Não testado | — | 🔵 |
| Apify, Firecrawl, serviços anti-bot | — | Não testado | — | 🔵 |
| Busca web (Claude web search, SerpAPI, Google Shopping) | — | Não testado | — | 🔵 |
| Exportação Excel/Word/ZIP | — | Não testado (bibliotecas maduras) | — | 🔵 |

### 3.2 Registro detalhado — CNPJ (`poc/cnpj_poc.py`, `poc/cnpj_footer.py`)

| Campo | Registro |
|---|---|
| Cenário | Consultar razão social, situação cadastral, data e CNAE em 5 provedores |
| Entrada | Petrobras, Kalunga, Magazine Luiza, Mercado Livre, 1 CNPJ com DV inválido, 1 CNPJ com DV válido escolhido ao acaso |
| Esperado | Dados consistentes entre provedores; erro para DV inválido |
| Obtido | Dados idênticos entre provedores. O CNPJ "aleatório" existia e estava **BAIXADO**, o que valida a detecção de irregularidade. O DV inválido foi barrado localmente |
| Taxa de sucesso | BrasilAPI e MinhaReceita: 5/5. As demais caíram em 429 após 2–4 chamadas |
| Tempo | 0,5–1,2 s por consulta |
| Custo | R$ 0 |
| Intervenção humana | Nenhuma para a consulta. **Necessária** se a secretaria exigir o *Comprovante de Inscrição* emitido no site da Receita, que tem CAPTCHA e não deve ser automatizado |
| Conclusão | Pronto para produção com cadeia de fallback (BrasilAPI → MinhaReceita → CNPJá → cache local), fila com limite de taxa e cache |
| Confiança | Alta |

### 3.3 Registro detalhado — Acesso a lojas (`poc/stores_poc.py`, `poc/vtex_poc.py`)

| Loja | Headless (HTML) | API VTEX | Observação |
|---|---|---|---|
| Kalunga | 🟢 9 preços | ✖ | Busca por "75g" retornou também **Chamex 90g** e **caixa com 10 resmas**: armadilhas reais |
| Amazon | 🟢 232 preços | ✖ | Marketplace: vendedor ≠ Amazon (impacta o CNPJ) |
| Americanas | 🟢 42 preços | 🟢 com EAN | — |
| Atacadão | 🟢 4 preços | 🟢 com EAN | Preço regional (CEP) |
| Magazine Luiza | 🔴 403 | ✖ | Bloqueio anti-bot |
| Casas Bahia | 🔴 403 | ✖ | Bloqueio anti-bot |
| Leroy Merlin | 🔴 403 | ✖ | Bloqueio anti-bot |
| Mercado Livre | 🔴 exige login | — | Tela "Para continuar, acesse sua conta" |
| Carrefour | 🟡 "sem resultados" | 🔴 403 | **Falso negativo** causado pelo formato da URL |
| Shopee | 🟡 sem preços renderizados | — | — |
| Giassi, Savegnago, Super Nosso, São João, Telhanorte | não testado | 🟢 com EAN | — |

**Achado crítico sobre esgotados:** na API VTEX, produtos esgotados vêm com `Price: 0.0` e `AvailableQuantity: 0`. Sem tratamento explícito, o sistema calcularia médias com R$ 0,00. A regra "preço > 0 **e** em estoque" precisa ser uma invariante.

### 3.4 Registro detalhado — Matching (`poc/match_poc.py`)

25 pares com as armadilhas pedidas no briefing. Resultados:

| Tipo de caso | Resultado |
|---|---|
| Mesmo produto, ordem de palavras diferente, abreviação ("fls", "g/m²") | ✔ verde |
| Marca diferente (Chamex × Report; Tenaz × Pritt; Ypê × Limpol) | ✔ vermelho |
| Gramatura (75 × 90 g), folhas (500 × 300), formato (A4 × Ofício) | ✔ vermelho |
| Embalagem (1 pacote × caixa com 10 resmas) | ✔ vermelho |
| Variante (reciclado, cor da caneta, fragrância do detergente) | ✔ vermelho |
| Volume (500 ml × 5 L), ponta (1,0 × 0,8 mm), número de cores (24 × 12) | ✔ vermelho |
| Gramatura ausente em uma das descrições | ✔ amarelo (revisão) |
| **Tesoura 13 cm × 21 cm** | ✘✘ **verde (falso positivo perigoso)**: o dicionário não tinha "cm" |
| Lápis 24 cores × 24 cores **aquarelável** | ✘ verde (deveria ser amarelo) |
| Caneta avulsa × caixa com 50 | ~ amarelo (deveria ser vermelho; seguro, mas gera trabalho) |

**Conclusão:** regras sozinhas nunca cobrem todas as dimensões de todos os produtos. A arquitetura correta é em camadas:

```
1. EAN/GTIN igual nas duas ofertas?  → VERDE (determinístico)
   EAN diferente?                     → VERMELHO (determinístico)
2. Sem EAN: extração de atributos (regras + LLM com saída estruturada)
   Algum atributo crítico diverge?    → VERMELHO (com o motivo)
3. LLM compara as duas descrições completas e cita o trecho que sustenta cada atributo
4. VERDE somente se regras E LLM concordarem; qualquer divergência → AMARELO → humano
```

A regra 4 é o que protege contra o falso positivo encontrado: um LLM identifica trivialmente 13 cm ≠ 21 cm, e as regras identificam o que o LLM eventualmente deixe passar. **Essa hipótese ainda precisa ser validada** com uma PoC de LLM via API sobre cerca de 200 pares rotulados (Fase 0).

### 3.5 Registro detalhado — Otimização (`poc/opt_poc.py`, `poc/near.py`)

Modelagem: **tudo em centavos inteiros** (elimina erro de ponto flutuante do tipo R$ 19.999,99), com variáveis inteiras de quantidade e, opcionalmente, de preço unitário. Solver: Google OR-Tools CP-SAT.

| Caso | Regra | Resultado | Tempo |
|---|---|---|---|
| C1 | 5 itens, quantidade em faixa, **preço = média** | **INVIÁVEL**: nenhuma combinação dá R$ 9.000,00; as mais próximas são **R$ 8.999,98** e **R$ 9.000,01** | 0,00 s |
| C1b | igual ao C1 + 1 item barato "de ajuste" (R$ 1,05) | ✔ **R$ 9.000,00 exatos** | 0,03 s |
| C2 | quantidade em faixa, **preço ≤ média**, teto quebrado R$ 9.000,01 | ✔ exato; preços reduzidos em poucos centavos | 0,04 s |
| C3 | **quantidade travada**, preço = média | INVIÁVEL, com prova: "total é determinado: R$ 8.295,40 ≠ teto" | 0,00 s |
| C4 | quantidade travada, preço entre a **menor cotação e a média** | ✔ R$ 8.000,00 exatos, **mas o solver concentrou a redução num único item** (papel: R$ 36,93 → R$ 34,48) | 0,02 s |
| C5 | teto alto demais | INVIÁVEL, com prova: "mesmo no máximo faltam R$ 79.990,80" | 0,00 s |
| C6 | teto baixo demais | INVIÁVEL, com prova: "no mínimo o total já é R$ 7.023,00" | 0,01 s |
| C7 | preços múltiplos de R$ 5, teto R$ 200,03 | INVIÁVEL, com **prova por MDC** | 0,00 s |
| C8 | **200 itens**, teto com centavos quebrados | ✔ exato | 0,28 s |

**Conclusões:**

- 🟢 O solver fecha exatamente no teto quando existe solução e **prova** quando não existe, com explicação legível e os valores alcançáveis mais próximos.
- ⚠️ **Com poucos itens e preço fixo na média, o fechamento exato é frequentemente impossível.** Não é defeito de ferramenta: é aritmética. A OSC precisa definir qual "grau de liberdade" é aceito (§13, decisão D1).
- ⚠️ O caso C4 mostra que **"como distribuir o ajuste"** também é regra de negócio: concentrar em um item ou distribuir proporcionalmente entre todos. O objetivo do solver deve ser configurável.
- ⚠️ Existe tensão entre "atingir exatamente o teto" e "nunca alterar artificialmente um preço". Minha recomendação: o preço do 4º orçamento é rotulado como **"valor proposto (≤ média)"**, nunca como "preço encontrado", e o relatório mostra a diferença para a média em cada item.

### 3.6 Registro detalhado — Vagas (`poc/jobs_poc.py`)

| Plataforma | Acesso | Salários visíveis | Observação |
|---|---|---|---|
| InfoJobs | 🟢 | 🟢 ex.: R$ 1.760,00, R$ 2.180,00 | 32 menções a salário |
| Catho | 🟢 | 🟢 **faixas** (ex.: "R$ 1.830 a R$ 2.100") | Faixa exige regra (§13, D6) |
| BNE | 🟢 | 🟡 poucos | — |
| Vagas.com | 🟢 | 🔴 quase nenhum | — |
| Gupy | 🟢 | 🔴 não exibido | — |
| Glassdoor | 🟡 | 🔴 | — |
| LinkedIn | 🟡 lista pública visível, pede login | 🔴 raramente informa salário | Termos de uso restritivos |
| Indeed | 🔴 403 Cloudflare | — | Exigiria serviço anti-bot ou captura manual |

**Deduplicação de vagas:** não testada. Proposta a validar: chave de similaridade (empresa normalizada ou CNPJ + cargo normalizado + cidade + salário + janela de datas) + similaridade do texto da descrição + LLM para os casos limítrofes.

### 3.7 Registro detalhado — Fluxo integrado (`poc/pipeline_poc.py`)

`API VTEX por EAN → filtro (preço > 0 e em estoque) → lojas com todos os itens → diagnóstico de gargalo → seleção → médias → PDF de evidência + hash → CNPJ → banco`

| Campo | Registro |
|---|---|
| Entrada | 4 produtos por EAN × 10 lojas |
| Resultado | Nenhuma loja com os 4 itens. O sistema **identificou o item gargalo** (esponja: 0 lojas), removeu-o no modo diagnóstico e encontrou só 2 lojas completas |
| **Bug encontrado** | A média foi calculada dividindo por 3 mesmo com 2 lojas: R$ 29,63 em vez de R$ 44,45 |
| Causa do "gargalo" | O EAN da esponja **foi informado por mim sem verificação** e provavelmente está errado. Lição: "não encontrado" ≠ "não existe" |
| Evidência | PDFs gerados; preço da API conferido com o preço impresso na página |
| CNPJ | Não encontrado no HTML da página de produto; encontrado depois no rodapé (6/7 lojas) |
| Tempo | 51,7 s no total (~1 s por consulta de API; ~10–15 s por página renderizada) |
| Conclusão | O fluxo é viável, mas precisa de **invariantes**: nº de fontes = regra; preço > 0; fonte com evidência; EAN verificado; média só com o conjunto completo |

---

## 4. Achados que mudam a arquitetura

1. **EAN/GTIN é a espinha dorsal do matching.** Resolve de forma determinística e auditável ("mesmo código de barras") a regra mais importante do sistema. A estratégia de coleta deve **priorizar fontes que expõem EAN** (APIs VTEX, JSON-LD `schema.org/Product` com `gtin13`, páginas de produto) e, na criação do item, **fixar o EAN de referência** (verificado).
2. **Busca textual produz armadilhas no primeiro resultado.** A Kalunga devolveu 90g e caixa com 10 resmas numa busca por "75g 500 folhas". Nunca se pode usar "o primeiro resultado".
3. **Preço zero significa esgotado**, não gratuito.
4. **"Não encontrado" ≠ "não existe".** Aconteceu duas vezes: URL malformada no Carrefour e EAN errado na esponja. O sistema deve distinguir *fonte falhou*, *busca inconclusiva* e *produto ausente confirmado*, e só descartar uma loja no terceiro caso.
5. **O fechamento exato depende de uma regra administrativa**, não de tecnologia (§3.5).
6. **Bugs aparecem nas junções.** A camada de cálculo precisa de testes automatizados e invariantes com bloqueio, não apenas de "revisão".
7. **Marketplaces (Amazon, Mercado Livre, Shopee, Americanas marketplace)** vendem por terceiros: o CNPJ do rodapé é o da plataforma, não o do vendedor. É preciso uma regra (§13, D3).
8. **Preço depende de CEP/região** em atacarejos e supermercados. A pesquisa precisa de um CEP de referência registrado.
9. **Bloqueios anti-bot são estruturais** em grandes varejistas. Contorná-los exige serviços pagos de proxy/navegador, e **resolver CAPTCHA não deve ser feito**. Logo, a captura manual assistida precisa existir como caminho de primeira classe, não como exceção.

---

## 5. Divisão do trabalho: IA, algoritmos, APIs, scraping e humano

| Parte | Automação comum | IA | API | Scraping / navegador | Código próprio | No-code serve? | Humano |
|---|---|---|---|---|---|---|---|
| Cadastro, CRUD, duplicação | ✔ | — | — | — | ✔ | ✔ | usa |
| Motor de regras | ✔ | propõe a partir do edital | — | — | ✔ | ✖ (lógica complexa) | **aprova** |
| Itens e quantidades | — | sugere | — | — | — | — | **aprova** |
| Descoberta de lojas | — | gera termos de busca e escolhe lojas | busca web, VTEX | ✔ | ✔ | parcial (Apify) | escolhe lojas (opção A) |
| Coleta de preço | ✔ | extrai quando não há dado estruturado | VTEX, JSON-LD | ✔ Playwright | ✔ adaptadores | parcial | captura manual quando bloqueia |
| Matching | regras/EAN | ✔ julgamento | — | — | ✔ | ✖ | casos 🟡 |
| Seleção de 3 lojas | ✔ | explica | — | — | ✔ | ✖ | revisa |
| Substituição | — | sugere e justifica | — | — | — | — | **aprova sempre** |
| Médias e totais | ✔ | **nunca** | — | — | ✔ | ✖ (risco) | confere |
| Otimização | solver | explica o resultado | — | — | ✔ | ✖ | escolhe o grau de liberdade |
| Vagas | ✔ | extrai e detecta duplicidade | — | ✔ | ✔ | parcial | valida o enquadramento do cargo |
| Horas por cargo | regra | sugere o enquadramento | — | — | ✔ | — | **confirma** |
| CNPJ | ✔ | — | ✔ | rodapé | ✔ | ✔ | comprovante oficial (CAPTCHA) |
| Evidência | ✔ | — | — | ✔ | ✔ | ✖ | — |
| Auditoria e histórico | ✔ | — | — | — | ✔ | ✖ | consulta |
| Exportação | ✔ | redige textos de justificativa | — | — | ✔ | parcial | assina |

**Onde o no-code não serve:** cálculo com invariantes, otimização inteira, matching em camadas e trilha de auditoria imutável. Nesses pontos, a lógica em blocos visuais fica difícil de testar, versionar e provar.

---

## 6. Panorama de ferramentas

### 6.1 IA / LLM

| Opção | Papel | Status | Nota |
|---|---|---|---|
| Claude Haiku 4.5 (US$ 1 / 5 por milhão de tokens entrada/saída) | extração e matching em volume | 🔵 | Barato; saída estruturada |
| Claude Sonnet 5 (US$ 2 / 10) | casos 🟡, explicações, leitura de edital | 🔵 | Custo-benefício |
| Claude Opus 5 (US$ 5 / 25) | leitura de edital complexo, auditoria | 🔵 | Uso pontual |
| Batch API | reprocessamento em massa | 🔵 | 50% de desconto, assíncrono |
| Ferramenta de busca web do modelo | descoberta de lojas | 🔵 | Preço por busca a verificar |
| GPT / Gemini | alternativas equivalentes | 🔵 | Não avaliados |
| Agentes autônomos com navegador (browser-use, computer use) | navegar como humano | 🔵 | Lentos, caros e pouco reprodutíveis → não servem como núcleo (ver Arquitetura E) |

### 6.2 Coleta, scraping e pesquisa

| Opção | Status | Custo | Nota |
|---|---|---|---|
| **Playwright** (Python) | 🟢 | grátis | Renderiza JS, gera PDF/PNG/HTML |
| **API de catálogo VTEX** | 🟢 | grátis | EAN, preço e estoque; 11 dos 30 domínios testados |
| JSON-LD `schema.org/Product` em páginas de produto | 🟡 (1 página de busca com JSON-LD) | grátis | Padrão para SEO; tende a expor `gtin` e `price` |
| Apify (atores prontos) | 🔵 | plano grátis com créditos mensais; pago por uso | Atores de Amazon/ML/Indeed prontos; qualidade variável |
| Firecrawl, Crawl4AI | 🔵 | grátis / pago | Extração orientada a LLM |
| Proxies anti-bot (Bright Data, ZenRows, ScraperAPI) | 🔵 | ~US$ 50+/mês | Para Magalu/Casas Bahia/Indeed; avaliar termos de uso |
| API Mercado Livre | 🔴 não testada | grátis com app OAuth | Busca pública passou a exigir login no navegador |
| Amazon PA-API | 🔵 | exige conta de afiliado com vendas | Pouco viável para OSC |
| SerpAPI / Google Shopping | 🔵 | pago por busca | Descoberta de lojas por EAN |
| Comparadores (Buscapé, Zoom) | 🔵 | — | Descoberta |

### 6.3 Automação e orquestração

| Opção | Status | Serve para | Não serve para |
|---|---|---|---|
| **n8n** (auto-hospedado grátis) | 🔵 | agendamentos, notificações, integrações (e-mail, Drive) | núcleo de cálculo e matching |
| Make / Zapier | 🔵 | cola simples | volume (custo por operação) e lógica complexa |
| Power Automate | 🔵 | ambiente Microsoft 365 | web scraping robusto |
| Fila de jobs em código (Celery, RQ, Dramatiq) | 🔵 | pipeline confiável com retry | — |

### 6.4 Banco de dados

| Opção | Status | Nota |
|---|---|---|
| **PostgreSQL** (Supabase, Neon ou VPS) | 🔵 | Relacional, transações, JSONB para regras, triggers para auditoria |
| Supabase (plano grátis) | 🔵 | Postgres + Auth + Storage + API; pausa por inatividade no plano grátis |
| SQLite | 🟢 no PoC | Ótimo para versão local monousuário |
| Airtable | 🔵 | Fácil, mas limites de registros e sem transações fortes |
| Google Sheets | 🔵 | Bom para o usuário ver; ruim como fonte de verdade auditável |

### 6.5 Interface

| Opção | Status | Nota |
|---|---|---|
| React/Next.js próprio | 🔵 | Máxima flexibilidade para a revisão item a item |
| Streamlit / NiceGUI (Python) | 🔵 | Rápido para MVP interno; limitado para UX refinada |
| Django + admin + HTMX | 🔵 | Uma linguagem só; admin pronto para cadastros; histórico com `django-simple-history` |
| Retool / Appsmith | 🔵 | Painéis internos rápidos sobre Postgres |
| Bubble | 🔵 | UI completa sem código; lógica pesada vira dívida; lock-in |
| Softr / AppSheet | 🔵 | Front simples sobre Airtable/Sheets; limitados para revisão complexa |

### 6.6 Documentos e evidência

| Opção | Status | Nota |
|---|---|---|
| Playwright `page.pdf()` + screenshot + HTML | 🟢 | PDF com cabeçalho de data/hora/URL validado |
| SHA-256 de cada arquivo | 🟢 | Integridade |
| WARC / SingleFile / MHTML | 🔵 | Arquivo fiel da página |
| Wayback Machine "Save Page Now" | 🔵 | Terceiro independente atestando a página |
| Carimbo de tempo RFC 3161 (TSA) | 🔵 | Prova de data independente |
| openpyxl / python-docx / WeasyPrint | 🔵 | Excel, Word e PDF de relatórios |

### 6.7 CNPJ

BrasilAPI 🟢 · MinhaReceita 🟢 · CNPJá 🟡 · CNPJ.ws 🟡 · ReceitaWS 🟡 · Dados abertos da Receita (download mensal, base própria) 🔵 · Portal da Transparência (CEIS/CNEP, sanções, exige chave gratuita) 🔵.

### 6.8 Otimização

OR-Tools CP-SAT 🟢 · PuLP/CBC 🔵 (instalado, não testado) · HiGHS 🔵 · Z3 / MiniZinc 🔵 · Solver do Excel 🔵 (não recomendado: não garante exatidão inteira em centavos nem prova inviabilidade de forma auditável).

---

## 7. Arquiteturas possíveis e comparação

### A. No-code puro
Bubble ou Softr + Airtable + Make/Zapier + LLM via HTTP + Apify.

### B. Low-code orquestrado
n8n (fluxos) + Supabase + Apify + LLM + Retool/Appsmith, com nós "Code" para os cálculos.

### C. Código próprio monolítico
Python (FastAPI ou Django) + PostgreSQL + Playwright + OR-Tools + LLM + front web.

### D. Híbrida com núcleo determinístico (**recomendada**)
Núcleo em código (Python) com máquina de estados, invariantes e solver. A IA é chamada como **ferramenta com contrato** (entrada e saída estruturadas, validadas). Coleta em camadas com fallback para captura manual. Postgres com log de eventos imutável. n8n opcional só para agendamento e notificações.

### E. Agente autônomo
Um agente LLM com navegador faz a pesquisa inteira ("pesquise estes 20 itens em 10 lojas"), e o código só formata.

### F. Planilha + scripts (menor custo)
Google Sheets como interface + scripts Python locais (os PoCs deste documento, evoluídos) + Playwright local + APIs gratuitas.

### 7.1 Comparação

| Critério | A. No-code | B. Low-code | C. Código | **D. Híbrida** | E. Agente | F. Planilha |
|---|---|---|---|---|---|---|
| Complexidade de construção | Baixa no início, alta no fim | Média | Alta | Alta | Baixa no início | Baixa |
| Automação | Média | Alta | Alta | **Alta** | Aparente alta, real baixa | Média |
| IA | Chamadas soltas | Nós de IA | Integrada | **Integrada com contratos** | Central | Scripts |
| Pesquisa web | Apify | Apify/HTTP | Playwright | **Camadas + fallback** | Navegador do agente | Playwright local |
| Scraping com JS | Apify | Apify | 🟢 | 🟢 | Sim, lento | 🟢 |
| CNPJ | HTTP simples | 🟢 fácil | 🟢 | 🟢 | Pode inventar | 🟢 |
| Matching | Frágil | Médio | Bom | **EAN + regras + LLM + humano** | Opaco | Bom |
| Otimização exata | ✖ | Nó Code (difícil de manter) | 🟢 | 🟢 | ✖ não confiável | 🟢 |
| PDFs e evidências | Via serviço externo | Via serviço externo | 🟢 | 🟢 | Difícil padronizar | 🟢 |
| Auditoria | Fraca | Média | Forte | **Forte (event log)** | Fraca (não reprodutível) | Média |
| Escalabilidade | Limitada por custo por operação | Boa | Boa | Boa | Cara | Um usuário |
| Manutenção | Difícil quando cresce | Média; fluxos visuais longos | Exige dev | Exige dev; módulos isolados | Imprevisível | Exige quem rode scripts |
| Dependência de programação | Nenhuma no início | Moderada | Alta | Alta (mitigável com Claude Code) | Baixa | Moderada |
| Principal limitação | Não prova invariantes; lock-in | A lógica espalha-se entre nós | Tempo de construção | Tempo de construção | **Viola o princípio de não inventar** | Sem multiusuário, UX pobre |

**O que cada uma resolve e o que deixa a desejar:**

- **A (No-code)** resolve rápido o cadastro e a UI. Deixa a desejar exatamente no que o briefing chama de fundamental: otimização exata, invariantes, matching confiável e auditoria. O bug de média do teste integrado passaria despercebido.
- **B (Low-code)** é bom para orquestração e integração. Ao colocar matching, otimização e cálculo em nós de código dentro do n8n, perde-se testabilidade e versionamento, e o resultado vira uma "arquitetura C mal organizada".
- **C (Código)** resolve tudo tecnicamente, mas não impõe por si só a separação IA × números nem a coleta em camadas. É a base da D.
- **D (Híbrida)** é a C com as disciplinas que os testes mostraram ser necessárias: contratos da IA, invariantes, coleta em camadas, captura manual de primeira classe e log de eventos.
- **E (Agente)** parece a mais automática, mas é a menos adequada: não é reprodutível, é cara por orçamento e mistura "pesquisar" com "afirmar", justamente o que o §39 proíbe. Serve apenas como **ferramenta auxiliar** de descoberta dentro da D.
- **F (Planilha)** é a porta de entrada de menor custo e reaproveita os PoCs. Não atende multiusuário, revisão visual nem escala.

---

## 8. Arquitetura recomendada (D) em detalhe

```
┌──────────────────────────── INTERFACE WEB ─────────────────────────────┐
│ Projetos → Orçamentos → Regras → Itens → Revisão item a item → Export   │
│ Dashboard · Alertas · Cadeia de rastreabilidade clicável                │
└───────────────┬────────────────────────────────────────────────────────┘
                │ API
┌───────────────▼────────────── NÚCLEO (Python) ─────────────────────────┐
│ Máquina de estados do orçamento:                                        │
│  RASCUNHO → REGRAS_OK → ITENS_OK → PESQUISANDO → MATCHING → SELEÇÃO     │
│  → CÁLCULO → OTIMIZAÇÃO → REVISÃO → APROVADO → DOCUMENTADO             │
│                                                                         │
│ Motor de regras (JSON versionado + templates por secretaria/edital)     │
│ Invariantes (bloqueiam a transição de estado se violadas):              │
│   nº fontes == regra · preço > 0 · em estoque · evidência com hash ·    │
│   CNPJ ativo (se exigido) · pesquisa dentro da validade · mesmo EAN     │
│ Cálculo em centavos inteiros · Solver CP-SAT · Explicações              │
└──┬──────────┬──────────────┬───────────────┬──────────────┬────────────┘
   │          │              │               │              │
┌──▼───┐ ┌────▼──────┐ ┌─────▼───────┐ ┌─────▼──────┐ ┌─────▼──────────┐
│Coleta│ │ IA (LLM)  │ │ CNPJ        │ │ Evidência  │ │ Fila de jobs   │
│camada│ │ contratos:│ │ BrasilAPI → │ │ Playwright │ │ retry, limite  │
│1 API │ │ extrair   │ │ MinhaReceita│ │ PDF+PNG+   │ │ de taxa,       │
│ VTEX/│ │ comparar  │ │ → CNPJá →   │ │ HTML+JSON  │ │ agendamento    │
│ EAN  │ │ sugerir   │ │ cache       │ │ + SHA-256  │ │ (validade)     │
│2 JSON│ │ explicar  │ └─────────────┘ │ + data/hora│ └────────────────┘
│  -LD │ │ NUNCA     │                 └────────────┘
│3 HTML│ │ escreve   │
│ adapt│ │ número    │
│4 LLM │ └───────────┘
│5 Manual (upload de print/URL pelo usuário, com o mesmo fluxo de hash)  │
└──────┘
┌──────────────────────── PostgreSQL + Storage ──────────────────────────┐
│ entidades versionadas · tabela `eventos` append-only (quem, quando,     │
│ o quê, antes/depois, IA ou humano, justificativa) · arquivos imutáveis  │
└────────────────────────────────────────────────────────────────────────┘
```

**Modelo de proveniência (a cadeia do §24):**
`ValorUsado → Regra aplicada → Oferta (preço extraído, JSON bruto) → Evidência (PDF/PNG/HTML, SHA-256, data/hora, URL) → Loja → CNPJ (resposta da API + data) → Pesquisa (execução, parâmetros, CEP)`.
Cada seta é uma chave estrangeira, e a UI permite navegar por ela.

**Contratos da IA (exemplos):**

| Ferramenta de IA | Entrada | Saída estruturada | Validação por código |
|---|---|---|---|
| `extrair_atributos` | texto/HTML da página | marca, modelo, EAN, gramatura… + **trecho citado** para cada campo | o trecho citado precisa existir literalmente na página salva |
| `comparar_ofertas` | 2 ofertas (IDs) | verde/amarelo/vermelho + atributo divergente + trechos | só IDs existentes; verde exige concordância com as regras |
| `sugerir_substituto` | item gargalo + ofertas coletadas | lista de IDs de ofertas + justificativa | IDs existentes; o humano aprova |
| `propor_regras` | texto do edital | JSON de regras + citação da cláusula | schema válido; o humano aprova |
| `explicar` | decisão + dados | texto curto | não contém números que não estejam nos dados |

**Níveis de automação (§28)** ficam no próprio motor de regras, por tipo de ação. Exemplo: `matching.verde: automatico`, `matching.amarelo: aprovacao`, `substituicao: aprovacao`, `quantidade_sugerida: aprovacao`, `selecao_lojas: automatico_com_explicacao`.

---

## 9. Arquitetura de menor custo possível

**Versão praticamente gratuita (variante F → D-lite):**

| Componente | Ferramenta | Custo | Limite |
|---|---|---|---|
| Execução | Computador da OSC (Python + Playwright) | R$ 0 | Só roda com a máquina ligada |
| Banco | SQLite (arquivo) | R$ 0 | Um usuário por vez |
| Interface | Streamlit local ou planilha | R$ 0 | UX simples |
| CNPJ | BrasilAPI + MinhaReceita | R$ 0 | Sem limite observado; usar cache |
| Preços | API VTEX + Playwright | R$ 0 | Lojas bloqueadas exigem captura manual |
| Otimização | OR-Tools | R$ 0 | — |
| Evidência | Playwright PDF/PNG + pasta sincronizada no OneDrive/Drive | R$ 0 | Espaço da conta |
| IA | Haiku 4.5 via API | **~US$ 1–5 por orçamento de materiais** (estimativa) | Custo real; não é gratuito |

**Custos ocultos:** tempo de alguém técnico para manter os adaptadores de lojas (sites mudam), o arquivamento de evidências e o horário da máquina. Sem IA, o matching fica só em EAN + regras, com mais itens em amarelo para revisão humana.

**Armazenamento (medido):** os PDFs gerados tiveram de 16 KB a 4,1 MB (mediana ~250 KB). Estimando ~0,5–1 MB por oferta (PDF + PNG + HTML), um orçamento com 30 itens × 3 lojas ≈ **45–90 MB**, ou 1 GB para ~10–20 orçamentos.

---

## 10. Estimativa de custos (arquitetura D)

| Item | Estimativa mensal | Status |
|---|---|---|
| Hospedagem (VPS para worker Playwright + API) | US$ 6–25 | 🔵 |
| Postgres + Storage gerenciado (ex.: Supabase Pro) | US$ 0 (grátis) a ~US$ 25 | 🔵 verificar preços atuais |
| LLM: ~30 itens × 10 lojas, com EAN resolvendo parte do matching | **~US$ 2–5 por orçamento** | Estimativa com os preços oficiais; volume de tokens não medido |
| Busca web para descoberta de lojas | a verificar | 🔵 |
| Proxy anti-bot (opcional, lojas bloqueadas) | US$ 50+ | 🔵 |
| CNPJ | R$ 0 | 🟢 |

Premissas da estimativa de LLM: ~300 ofertas; extração com Haiku (~4 mil tokens de entrada por página); ~30% dos pares indo para comparação por LLM; ~50 casos amarelos revisados com Sonnet 5. **Precisa ser medida na PoC da Fase 0.**

---

## 11. Principais riscos

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Lojas bloqueiam ou mudam o layout | **Alta** (3/12 já bloqueiam) | Alto | Camadas: API > JSON-LD > adaptador > LLM > manual; monitor de adaptadores quebrados |
| Poucas lojas com todos os itens | **Alta** (visto no fluxo integrado) | Alto | Diagnóstico de gargalo, sugestão de substituto, mais lojas na busca |
| Falso positivo no matching | Média | **Crítico** | Verde só com EAN ou concordância regras + LLM; auditoria amostral |
| Teto impossível de fechar | **Alta** com poucos itens | Alto | Decisão D1; prova matemática e alternativas mostradas ao usuário |
| Secretaria não aceita a evidência digital | Desconhecida | **Crítico** | Validar o pacote-modelo com uma secretaria real **antes** de construir |
| Termos de uso de sites (scraping) | Média | Médio | Preferir APIs públicas; baixo volume; respeitar robots; captura manual para sites restritivos |
| Limites de taxa das APIs de CNPJ | Média | Baixo | Fallback + cache (testado) |
| Alucinação do LLM | Média | Alto | IA nunca escreve números; citações verificadas por código |
| Dependência de uma pessoa técnica | Alta | Alto | Código simples, testes automatizados, documentação; uso de Claude Code para manutenção |
| LGPD (dados de sócios nas respostas de CNPJ) | Baixa | Médio | Armazenar só os campos necessários |

---

## 12. Caminho evolutivo

### Fase 0 — Validações que faltam (antes de construir)
1. **PoC de matching com LLM**: 200 pares rotulados de produtos reais da OSC; medir falsos positivos, taxa de amarelos e custo.
2. **Mapear as 20–30 lojas** que a OSC realmente usa: quais têm API, EAN e JSON-LD, quais bloqueiam.
3. **PoC de deduplicação de vagas** com 30–50 vagas reais.
4. **PoC de descoberta por EAN** (busca web → lojas que vendem aquele EAN).
5. **Mostrar um pacote de evidências-modelo** (gerado pelos PoCs) a uma secretaria ou a quem presta contas e confirmar a aceitação.
6. Responder às decisões do §13.

### MVP — "Orçamento de materiais auditável"
- Projetos, orçamentos e itens (com EAN de referência).
- Regras em JSON com 1–2 templates.
- Coleta: VTEX + JSON-LD + 3–5 adaptadores + **captura manual assistida**.
- Matching: EAN + regras + LLM, com fila de revisão amarela.
- Seleção de 3 lojas com explicação; médias com invariantes; CP-SAT com prova de inviabilidade.
- CNPJ com fallback; evidência PDF/PNG/HTML + hash; log de eventos.
- Exportação Excel + PDF + ZIP na estrutura do §32.
- Mão de obra **semiautomática**: o usuário cola 3+ URLs de vagas, e o sistema extrai, verifica duplicidade e calcula.

### Versão intermediária
- Descoberta automática de lojas por EAN.
- Pesquisa automática de vagas (InfoJobs, Catho, BNE) com deduplicação.
- Tela de revisão item a item completa, dashboard, alertas e validade com re-pesquisa.
- IA sugerindo quantidades e lendo o edital para propor regras.
- Templates por secretaria.

### Sistema completo
- Multiusuário/multi-OSC, permissões.
- Serviço anti-bot opcional para lojas bloqueadas.
- Carimbo de tempo RFC 3161 e/ou Wayback nas evidências.
- Histórico de preços reutilizável entre orçamentos.
- Word, relatórios de auditoria, monitoramento de adaptadores.

### O que construir primeiro
**O núcleo determinístico e o modelo de dados de proveniência**: regras, cálculo em centavos, invariantes, solver, log de eventos e armazenamento de evidência. É o que torna o orçamento defensável, é 100% testável offline e não muda quando uma loja muda o site. Os adaptadores de coleta são peças substituíveis encaixadas depois.

---

## 13. Decisões que precisam ser tomadas antes da implementação

| # | Decisão | Por que importa (evidência) |
|---|---|---|
| **D1** | **Como fechar exatamente no teto?** (a) só variando quantidades; (b) preço proposto ≤ média; (c) preço entre a menor cotação e a média; (d) item de ajuste permitido; (e) combinação | C1 mostrou que (a) sozinha frequentemente é impossível; C2/C4/C1b mostram que (b), (c) e (d) funcionam |
| D2 | Se houver ajuste de preço: **concentrar** em poucos itens ou **distribuir** proporcionalmente? | C4 concentrou toda a redução no papel |
| D3 | **Arredondamento da média**: comercial (seu exemplo R$ 5.000,67 é arredondamento) ou truncamento? Por item ou só no total? | O PoC usou truncamento; a média de 4.001 / 5.000 / 6.001 dá R$ 5.000,67 ou R$ 5.000,66 conforme a regra |
| D4 | **Marketplaces** são aceitos? Se sim, vale o CNPJ do **vendedor** ou da plataforma? | Amazon, ML e Shopee vendem por terceiros |
| D5 | Lojas **físicas/regionais** ou só online? Qual **CEP de referência**? Frete entra no preço? | Preço varia por CEP (Atacadão) |
| D6 | Vagas com **faixa salarial** ("R$ 1.830 a R$ 2.100"): usar mínimo, máximo ou ponto médio? Vagas "a combinar" são descartadas? | Catho mostra faixas |
| D7 | **Horas mensais**: o seu padrão 180 h (geral) / 120 h (Assistente Social) vem do edital? | 180 = 40 h × 4,5 semanas; 120 = 30 h × 4 semanas: multiplicadores diferentes. A convenção trabalhista usual é 220 h (44 h/sem), 200 h (40 h) e 150 h (30 h). A jornada de 30 h do Assistente Social está na Lei 8.662/1993, art. 5º-A. Deve ser **regra configurável do edital**, com a IA só sugerindo o enquadramento |
| D8 | Mão de obra inclui **encargos** (INSS patronal, FGTS, 13º, férias) ou só salário? | Muda o valor total significativamente |
| D9 | **Preço promocional** ("De R$ 345 por R$ 310"), à vista, Pix ou parcelado: qual usar? | Kalunga exibe ambos |
| D10 | Qual evidência a secretaria **aceita**? Print/PDF basta, ou exige orçamento assinado pelo fornecedor ou comprovante oficial do CNPJ (CAPTCHA → passo humano)? | Define o escopo do módulo de evidência |
| D11 | **Validade** padrão das pesquisas (30, 60, 90 dias?) | Motor de regras |
| D12 | Uso **interno de uma OSC** ou **plataforma para várias OSCs**? | Muda autenticação, custo e LGPD |
| D13 | **Quem mantém** o sistema? (define linguagem, hospedagem e grau de no-code aceitável) | Arquitetura D exige alguém técnico, ou uso contínuo de um assistente de código |
| D14 | Orçamento mensal aceitável para IA, hospedagem e, opcionalmente, anti-bot | §10 |

---

## 14. Reprodução dos testes

```bash
python -m venv venv && venv\Scripts\pip install -r poc\requirements.txt && venv\Scripts\python -m playwright install chromium
```

| Script | O que testa |
|---|---|
| `poc/cnpj_poc.py` | 5 APIs de CNPJ, CNPJ baixado, DV inválido, limites de taxa |
| `poc/cnpj_footer.py` | Identificação de CNPJ no rodapé das lojas |
| `poc/stores_poc.py` | 12 lojas em headless, com PDF/PNG/HTML/hash |
| `poc/vtex_poc.py` | API VTEX em 30 domínios (EAN, preço, estoque) |
| `poc/match_poc.py` | 25 pares de matching |
| `poc/opt_poc.py`, `poc/near.py` | 10 casos de otimização + valores alcançáveis mais próximos |
| `poc/jobs_poc.py` | 8 plataformas de vagas |
| `poc/pipeline_poc.py` | Fluxo integrado (contém o bug de média, **mantido de propósito** como registro do achado) |

> **Princípio seguido:** "Se funciona na teoria, investigue. Se funciona na prática, valide. Se funciona de forma confiável em um fluxo integrado, considere para produção." Pelos critérios deste documento, apenas **CNPJ** e **otimização** estão prontos para produção. **Coleta e matching** estão validados parcialmente. **Vagas, LLM e ferramentas no-code/low-code** ainda precisam de PoC.
