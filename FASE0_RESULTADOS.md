# Fase 0 — Validações antes da implementação

> **Atualização:** depois deste relatório, os pareceres da Secretaria da Justiça e Cidadania (SEJC) foram analisados e o caso real foi testado. Veja [FASE0_SEJC.md](FASE0_SEJC.md). Ele prevalece sobre este documento onde houver diferença: faixa salarial, custo zero (sem IA paga), lojas para o CEP 03977-015 e formato de evidência (carrinho).

**Data:** 25/09/2026 · Continuação de [ANALISE_ARQUITETURA.md](ANALISE_ARQUITETURA.md)
**Scripts e dados:** [`fase0/poc/`](fase0/poc/) · **Pacote de evidências-modelo:** [`fase0/pacote_modelo/`](fase0/pacote_modelo/)

Legenda: 🟢 validado na prática · 🟡 parcial · 🔵 só documentação · 🔴 não validado / falhou

---

## 0. Resumo

| Validação planejada | Resultado | Status |
|---|---|---|
| 1. Matching com LLM (pares rotulados) | Conjunto de **800 pares reais** rotulados pelo EAN; comparador por regras v3 medido; **experimento com a API da Claude pronto, mas não executado** (sem chave de API nesta máquina) | 🟡 |
| 2. Mapa de lojas | **60 lojas** em 7 rubricas: 18 com API pública que devolve EAN, preço e estoque; 10 bloqueiam | 🟢 |
| 3. Deduplicação de vagas | 20/20 republicações detectadas no teste controlado; falsos duplicados por texto-padrão da empresa; regra simples proposta | 🟡 |
| 4. Descoberta de lojas pelo EAN | Buscadores automatizados bloqueiam; **busca web de IA funcionou** (9 de 15 páginas com EAN e preço confirmados) | 🟡 |
| 5. Pacote de evidências-modelo | **Gerado de ponta a ponta com dados reais**; revelou e corrigiu 1 falha de invariante | 🟢 (falta a aceitação da secretaria) |
| Decisão 1 (fechar no teto) | 7 estratégias testadas com preços reais → cascata recomendada | 🟢 |
| Decisão 2 (arredondamento) | Regra escolhida e testada; 2 armadilhas encontradas | 🟢 |
| Decisão 4 (horas pela jornada legal) | Tabela verificada nos textos oficiais; enquadramento automático testado em títulos reais | 🟢 |
| Decisão 5 (Recibo/MEI padrão; CLT/PJ) | Implementado e calculado com 3 vagas reais | 🟢 |

**Três achados que mudam o projeto:**

1. **O mesmo produto pode ter dois EANs, e o mesmo EAN pode vir com dados errados da loja.** "Chocolate Lacta ao Leite 80g" tem dois EANs; em outro caso, o mesmo EAN aparece como "Chocolate Musa" numa loja e "Biscoito Wafer Goldko" em outra. O EAN continua sendo a melhor chave, mas **não pode ser a única**: EAN igual + atributos compatíveis → verde; EAN igual com atributos em conflito → revisão; EAN diferente com descrição idêntica → revisão.
2. **Plataformas de vagas colocam dados que parecem da vaga, mas são da plataforma.** Todas as páginas da Catho exibem o CNPJ **da própria Catho** (03.753.088/0001-00). Usá-lo seria uma evidência falsa. *(Correção após ler os pareceres da SEJC: a faixa salarial da Catho **é aceita** pela Secretaria, desde que se use o **menor valor** da faixa e o nome/CNPJ da empresa contratante. Ver [FASE0_SEJC.md](FASE0_SEJC.md).)*
3. **A nova regra de horas reduz a mão de obra em ~18% para cargos de 44 h.** O seu exemplo passa de R$ 2.500,34 (divisor 180) para R$ 2.045,73 (divisor 220).

---

## 1. Decisões registradas

### D1 — Fechar exatamente no teto: possibilidades testadas

Cesta real: 8 itens com preços de Savegnago, Super Nosso e Mambo (as únicas 3 de 18 lojas com todos os itens). Base a preço médio: **R$ 5.348,70**.

| Estratégia | Teto **acima** da base (R$ 5.450,00) | Teto **abaixo** da base (R$ 5.270,00) | Mexe em preço? |
|---|---|---|---|
| **E1** Só quantidades (±10%), preço = média | ✔ exato; 4 itens alterados (máx. 10%) | ✔ exato; 5 itens alterados (máx. 5%) | Não |
| E1b Só quantidades (±25%) | ✔ exato | — | Não |
| E2 Quantidades fixas + 1 item de ajuste | ✘ **inviável**: um item só move o total em múltiplos do próprio preço | — | Não |
| E3a Quantidades fixas, preço ≤ média, **concentrado** | — | ✔ exato; 2 itens reduzidos, **até 10,06%** | Sim |
| **E3b** Quantidades fixas, preço ≤ média, **distribuído** | — | ✔ exato; 8 itens reduzidos, **no máx. 1,56%** | Sim |
| E4 Preço entre a menor cotação e a média | — | ✔ exato; até 6,93% | Sim |
| E5 Quantidades ±10% + preço ≤ média | ✔ exato, sem mexer em preço | ✔ exato, sem mexer em preço | Só se preciso |
| E6 Incluir novo item aprovado | ✘ inviável sozinho (mesmo motivo do E2) | — | Não |
| E7 Fechar abaixo do teto e devolver saldo | ✔ (neste caso fechou exato) | — | Não |
| E8 Remanejar centavos entre orçamentos do mesmo projeto | Não testado; depende do edital | | Não |

**Recomendação: cascata, parando na primeira que fecha**, com as estratégias permitidas configuradas por orçamento:

1. **E1** — quantidades dentro de uma faixa aprovada pelo usuário; nenhum preço alterado. É a preferida, porque todos os números vêm de cotações reais.
2. **E5** — igual à E1, mas com redução mínima de centavos no preço (≤ média), **distribuída**.
3. **E3b** — quantidades travadas, redução distribuída, com limite máximo configurável (sugestão: 2% por item).
4. Se nada fechar: o sistema **mostra a prova matemática** e oferece E7 (saldo), E6 (item novo, com aprovação) ou alteração do teto. Nunca decide sozinho.

Sempre que houver redução, o documento rotula o valor como **"valor proposto (≤ média)"** e mostra a diferença para a média.

### D2 — Arredondamento (escolha minha)

**Regra adotada:** arredondamento comercial (meio para cima) em centavos, **somente nos valores monetários publicados** (média unitária, total do item, valor da mão de obra). Cada etapa seguinte usa o valor publicado. Razões intermediárias, como o valor-hora, **não são arredondadas**.

**Por quê:** qualquer pessoa na secretaria reproduz a conta com calculadora a partir do documento. Isso também bate com o seu exemplo (R$ 5.000,67).

**Duas armadilhas encontradas e tratadas:**
- **Arredondar o valor-hora amplia o erro.** R$ 2.023,83 ÷ 220 = 9,1992 → arredondado para 9,20 × 90 h = R$ 828,00, contra R$ 827,93 correto. Por isso o valor final usa a sua fórmula direta: **média ÷ horas mensais × horas do projeto**, com um único arredondamento.
- **"Média dos totais" ≠ "soma das médias unitárias × quantidade".** No pacote-modelo: R$ 5.348,50 × R$ 5.348,70 (R$ 0,20 de diferença, por arredondamento item a item). O orçamento final usa as **médias unitárias**; a média dos totais aparece só como referência, com nota explicativa.

### D3 — CNPJ do vendedor

Implicações para o sistema:
- Em marketplaces (Amazon, Mercado Livre, Americanas marketplace), a oferta só é elegível se o **CNPJ do vendedor** for identificável; caso contrário, vai para revisão ou é descartada.
- A API VTEX informa o vendedor de cada oferta. 🟢 **Testado na Americanas:** o vendedor "1" é a loja própria (AMERICANAS SA); terceiros aparecem com nome e identificador próprios (ex.: DUFRIO, Electrolux, Pega Pega Móveis). 🔴 O **CNPJ do terceiro não vem nessa API**: precisa ser buscado na página do vendedor, e a oferta fica em revisão até lá.
- O CNPJ exibido no rodapé pode ser de uma **filial** (Savegnago: /0039; Super Nosso: /0011). O sistema registra o CNPJ exatamente como exibido e a consulta correspondente.

### D4 — Horas mensais pela jornada legal semanal

**Conversão:** horas mensais = **semanais ÷ 6 × 30** (CLT art. 64 + [Súmula 431 do TST](https://www.legistrab.com.br/520-sumula-431-tst-salario-hora-40-horas-semanais-calculo-aplicacao-do-divisor-200/)): 44 h → 220 · 40 h → 200 · 36 h → 180 · 30 h → 150 · 24 h → 120.

**Tabela inicial** (textos conferidos no planalto.gov.br, cópias em [`fase0/poc/leis/`](fase0/poc/leis/)):

| Cargo | Semanal | Mensal | Base legal |
|---|---|---|---|
| **Regra geral** (auxiliar de limpeza, cozinheira, educador social, oficineiro, coordenador…) | 44 h | 220 h | CF art. 7º, XIII |
| **Assistente Social** | 30 h | 150 h | Lei 8.662/1993, art. 5º-A |
| Fisioterapeuta / Terapeuta Ocupacional | 30 h | 150 h | Lei 8.856/1994, art. 1º |
| Técnico em Radiologia | 24 h | 120 h | Lei 7.394/1985, art. 14 |
| Telefonista / telemarketing | 36 h | 180 h | CLT art. 227 |
| Jornalista | 5 h/dia (30 h) | 150 h | CLT art. 303 |
| Músico | 5 h/dia (30 h) | 150 h | Lei 3.857/1960, art. 41 |
| Radialista (autoria/locução) | 5 h/dia (30 h) | 150 h | Lei 6.615/1978, art. 18, I |
| Advogado empregado | 40 h | 200 h | Lei 8.906/1994, art. 20 (red. Lei 14.365/2022) |

**Em tramitação (ainda não são lei; o sistema usa 44 h e emite alerta):**
- Psicólogo: [PL 1.214/2019 aprovado na Câmara, pendente no Senado](https://site.cfp.org.br/historico-camara-aprova-projeto-de-lei-das-30-horas/).
- Enfermagem: [PEC 19/2024 em análise](https://www12.senado.leg.br/radio/1/noticia/2025/10/30/comissao-vai-debater-o-piso-salarial-e-a-jornada-de-trabalho-dos-enfermeiros).
- Educador social: [PLS 328/2015](https://www25.senado.leg.br/web/atividade/materias/-/materia/121529), sem jornada especial.

**Teste com títulos reais:** as 5 variações de "Assistente Social" coletadas foram enquadradas em 30 h; "Educador Social" caiu na regra geral com o alerta do projeto de lei.

**Pontos de atenção:**
- Convenção coletiva ou edital podem fixar jornada menor; o sistema pergunta quando não há lei específica.
- Em Recibo/MEI, a jornada legal serve como **referência de cálculo** (não há vínculo CLT).
- **Impacto:** com a nova regra, cargos de 44 h ficam ~18% abaixo do padrão antigo (180 h); Assistente Social fica ~20% abaixo (150 h × 120 h).

### D5 — Regime: Recibo/MEI padrão, com CLT e PJ

Cálculo com **3 vagas reais** de auxiliar de limpeza (G4S, Top Service, Fundação Mudes; 90 h no projeto):

| Regime | Valor | Composição |
|---|---|---|
| **Recibo/MEI (padrão)** | **R$ 827,93** | 2.023,83 ÷ 220 × 90 |
| PJ | R$ 827,93 | sem encargos; retenções na fonte não mudam o custo |
| CLT | R$ 1.285,28 | + INSS 20%, RAT 2%, Terceiros 5,8%, FGTS 8%, 13º 8,33%, férias + 1/3 11,11% |
| CLT com imunidade (entidade CEBAS) | ≈ R$ 1.055,11 | sem cota patronal, RAT e Terceiros |

Os percentuais da CLT são um **modelo configurável**, a validar com a contabilidade da OSC.

⚠️ **Alerta a confirmar com o contador (não é orientação jurídica):** em pagamento por RPA a autônomo, a legislação previdenciária costuma prever contribuição patronal sobre o valor pago, salvo imunidade. Para MEI, há atividades específicas (ex.: hidráulica, eletricidade, pintura, alvenaria, carpintaria) em que o contratante também contribui. O sistema pode exibir esse aviso quando o regime for Recibo/MEI.

---

## 2. Resultados detalhados

### 2.1 Mapa de lojas (60 domínios, 7 rubricas) — `store_map.py`, `jsonld_map.py`

| Categoria | Lojas |
|---|---|
| 🟢 **API pública com EAN, preço e estoque (18)** | Livrarias Curitiba, Americanas, Atacadão, Sam's Club, Bistek, Giassi, Savegnago, Super Nosso, Zona Sul, Mambo, Telhanorte, Obramax, Drogaria São Paulo, Pague Menos, São João, Drogarias Pacheco, Ri Happy, PB Kids |
| 🟡 API sem EAN (2) | Hortifruti, Tok&Stok |
| 🟡 Página de produto com dados estruturados | Colombo (**com** EAN), KaBuM e Pão de Açúcar (preço **sem** EAN) |
| 🟡 Acessíveis, mas sem dados estruturados | Kalunga, Havan, Amazon, Mercado Livre (produto), Angeloni, Tenda |
| 🔴 **Bloqueiam (HTTP 403) (10)** | Magazine Luiza, Leroy Merlin, Drogasil, Droga Raia, Leitura, Le Biscuit, Pichau, Terabyte, Centauro, Casas Bahia (busca) |

**Conclusão:** supermercados, farmácias e redes regionais são a melhor fonte automatizável, e muitas usam a mesma plataforma (VTEX). Papelarias e grandes magazines exigem adaptador por loja, captura manual ou comparação por IA, porque raramente expõem o EAN.

### 2.2 Descoberta de lojas pelo EAN — `ean_discovery.py`, `verify_discovered.py`

| Método | Resultado | Status |
|---|---|---|
| Google (navegador automatizado) | Bloqueado 4/4 | 🔴 |
| DuckDuckGo | Desafio anti-robô ("selecione os patos"). **Não deve ser contornado** | 🔴 |
| Bing (navegador automatizado) | Nenhuma loja nos resultados | 🔴 |
| Cosmos/Bluesoft (base de EAN) | Bloqueado (Cloudflare) | 🔴 |
| Open Food Facts | Achou 1 de 2 (base de alimentos) | 🟡 útil para alimentação |
| **Busca web de IA com o EAN puro** | 9–10 resultados por EAN, muitas lojas pequenas e regionais | 🟢 |
| **Verificação das páginas encontradas** | 15 páginas → **9 com EAN confirmado + preço**; 3 fora do ar; 7 com preço em dados estruturados; 6 com CNPJ visível | 🟡 |

A busca de IA também trouxe ruído (Wikipédia) e uma armadilha: o **Chamequinho azul**, com outro EAN. Por isso, toda página descoberta passa por verificação do EAN antes de virar oferta.

**Arquitetura resultante:** *API das lojas conhecidas por EAN* → *busca web de IA para achar outras lojas* → *verificação automática (EAN na página + preço)* → *oferta*.

### 2.3 Matching com dados reais — `collect_offers.py`, `matcher_v3.py`, `build_eval_v3.py`

- **Coleta:** 4.812 ofertas reais com EAN; 3.530 produtos distintos; 764 em 2+ lojas; 215 em 3+ lojas.
- **Conjunto de teste:** 300 pares positivos (mesmo EAN, títulos diferentes) + 500 negativos difíceis (EAN diferente, títulos ≥ 85% parecidos). O comparador **não vê o EAN**, simulando lojas que não o exibem.

| Versão | Mesmo produto → verde | → amarelo | → vermelho (erro) | Diferente → **verde (erro perigoso)** |
|---|---|---|---|---|
| v2 | 27% | 53% | 20% | 1,6% (8) |
| **v3** | 28% | 69% | **4%** | **1,2% (6)** |

Nos 6 "erros perigosos" da v3, **todos parecem ser o mesmo produto com dois EANs** (ruído do rótulo), não erros do comparador. Os 11 falsos vermelhos são majoritariamente **erros de cadastro das lojas**.

**Limite do comparador por regras:** 42% dos pares ficam amarelos. É exatamente o que a camada de IA precisa resolver.

**Experimento com IA ([`llm_match_eval.py`](fase0/poc/llm_match_eval.py)) — pronto, não executado:**
- Envia só os pares amarelos (336).
- Exige resposta estruturada com o **trecho literal** que sustenta cada atributo.
- O código **rejeita citações que não existem no anúncio**; testado: aceita citação real, aceita "ausente", rejeita citação inventada.
- Política: a IA **nunca** transforma um vermelho das regras em verde.
- Custo estimado: **~US$ 0,74 com Haiku 4.5** para os 336 pares.

### 2.4 Vagas — `jobs_collect.py`, `jobs_dedup.py`

5 plataformas × 4 cargos (auxiliar de limpeza, assistente social, educador social, cozinheira):

| Plataforma | Vagas | Dados estruturados | Salário | Observação |
|---|---|---|---|---|
| **InfoJobs** | 24 | 24/24 | 14 (58%) | Melhor fonte. A cidade da busca precisa ser controlada: veio Rio de Janeiro em vez de São Paulo |
| Catho | 24 | 24/24 | ⚠️ faixa **do site** | **CNPJ exibido é da Catho**; salário real às vezes só no texto |
| Vagas.com | 24 | 16/24 | 4 | Muitas "a combinar" |
| BNE | 15 | 3/15 | 3 | O padrão de link capturou botões de compartilhar; precisa de adaptador próprio |
| Gupy | 0 | — | — | Página dinâmica; precisa de adaptador |

**Outras armadilhas encontradas:**
- A busca por "educador social" no InfoJobs devolveu açougueiro, vendedor e operador de caixa. O cargo precisa ser conferido.
- Uma vaga de cozinheiro com "R$ 100/mês" (erro de cadastro): o sistema aplica um teste de sanidade.
- Muitas vagas de "empresa confidencial" não têm empresa nem CNPJ.

**Deduplicação:**
- Teste controlado: **20/20 republicações detectadas**.
- Nos dados reais: 2 duplicatas verdadeiras (o mesmo anúncio coletado duas vezes) e 2 falsos duplicados (vagas diferentes com texto-padrão da empresa).
- **Regra recomendada:** as 3 vagas de cada cargo devem ser de **3 empresas distintas e identificáveis**. Isso elimina quase todo o risco de duplicidade, e o erro que sobra é o seguro (descartar demais, nunca usar duas vezes).

### 2.5 Pacote de evidências-modelo — `build_package.py`

Gerado de ponta a ponta com dados reais: [`fase0/pacote_modelo/ORCAMENTO_pacote_modelo.zip`](fase0/pacote_modelo/)

```
ORCAMENTO/
├── 01_ORCAMENTOS/        Orcamento_1.pdf, Orcamento_2.pdf, Orcamento_3.pdf, Orcamento_Final.pdf
├── 02_PRODUTOS/          Produto_001_<EAN>/ ... Produto_008_<EAN>/  (por loja: PDF + JPG + HTML compactado)
├── 03_VAGAS/             Auxiliar_de_Limpeza/ Vaga1..3 (PDF+JPG+HTML) + Calculo_Mao_de_Obra.pdf
├── 04_CNPJ/              PDF legível + resposta bruta da API (JSON) de cada loja
├── 05_MEMORIA_CALCULO/   Memoria_de_Calculo.xlsx  (com FÓRMULAS: médias, totais, "FECHA NO TETO")
└── 06_AUDITORIA/         log_de_eventos.json (71 eventos), dados_estruturados.json, SHA256SUMS.txt
```

| Verificação | Resultado |
|---|---|
| CNPJ das 3 lojas (rodapé + consulta) | 3/3 **ATIVA** (Savegnago filial /0039, Super Nosso filial /0011, Mambo matriz) |
| Fechamento | Base R$ 5.348,70 → teto **R$ 5.400,00** → final **R$ 5.400,00** via E1, sem alterar nenhum preço |
| Capturas | 24/24 (3 falhas de tempo esgotado recuperadas por nova tentativa) |
| EAN presente no HTML capturado | 24/24 |
| Preço da API visível na página | 24/24 na versão final (23/24 na anterior: carregamento lento → agora gera **alerta**) |
| Arquivos com hash no manifesto | 95 |
| Tamanho | 42,8 MB (**~1,8 MB por oferta**: o PDF é 1,4 MB) |

**Falhas encontradas durante a geração (e corrigidas):**
1. **Invariante faltando:** na primeira versão, 2 capturas falharam por tempo esgotado e o pacote foi gerado **sem essas evidências**. Agora: nova tentativa com espera crescente, no máximo 2 capturas simultâneas por loja, e **bloqueio** se faltar evidência.
2. **Tamanho:** a primeira versão ficou com ~4 MB por oferta. Após compactar o HTML, usar JPEG e limitar o PDF às 2 primeiras páginas, caiu para ~1,8 MB. Estimativa revisada: **30 itens × 3 lojas ≈ 160 MB por orçamento**. O armazenamento pesa mais no custo do que eu havia estimado.

---

## 3. Mudanças na arquitetura decorrentes da Fase 0

| Antes | Depois |
|---|---|
| EAN igual = verde; EAN diferente = vermelho | EAN + **conferência de atributos** nos dois sentidos |
| Descoberta de lojas por buscadores | **API por EAN nas lojas conhecidas + busca web de IA + verificação na página** |
| "Deduplicar vagas" como módulo complexo | Regra **3 empresas distintas identificáveis** + deduplicação como proteção extra |
| CNPJ do rodapé é confiável | **Lista de CNPJs de plataformas** (Catho etc.) que nunca podem ser atribuídos ao empregador |
| Salário estruturado é confiável | Distinguir **faixa do empregador** de **faixa de filtro da plataforma** |
| Evidência "quando possível" | **Evidência obrigatória** (bloqueio) + alerta quando o preço não está visível no PDF |
| 0,5–1 MB por oferta | ~1,8 MB por oferta → armazenamento de objetos barato no plano de custos |
| Horas 180/120 fixas | Tabela de jornadas legais versionada, com base legal citada no documento |

---

## 4. O que ainda falta validar

| # | Pendência | Como resolver | Quem |
|---|---|---|---|
| 1 | **Rodar o experimento de IA** | Criar uma chave de API em console.anthropic.com, definir `ANTHROPIC_API_KEY` e executar `python llm_match_eval.py --model claude-haiku-4-5` (~US$ 0,74) e depois `--model claude-sonnet-5` | Você cria a chave; eu rodo e analiso |
| 2 | **Aceitação do pacote pela secretaria** | Levar o ZIP e as perguntas abaixo | Você |
| 3 | Lojas reais da OSC + **cidade/CEP** de referência | Lista das lojas que vocês usam hoje | Você |
| 4 | Faixa salarial do empregador | Adotado provisoriamente: **ponto médio**. Confirmar (ou mínimo/máximo) | Você |
| 5 | Vagas de "empresa confidencial" | Recomendo **não aceitar** (sem empresa, não há como provar que não é duplicada) | Você |
| 6 | CNPJ do vendedor terceiro em marketplaces | Separação loja × terceiro já validada; falta extrair o CNPJ da página do vendedor | Eu, na implementação |
| 7 | Adaptadores de Kalunga, BNE, Gupy e Catho (salário no texto) | Na implementação | Eu |
| 8 | Escolha de stack e hospedagem | Depende de quem mantém o sistema | Decisão conjunta |

**Perguntas para levar à secretaria (com o pacote-modelo em mãos):**
1. PDF/print da página da loja, com data, URL e hash, é aceito como evidência de preço? Ou é preciso orçamento assinado pelo fornecedor?
2. Lojas online de outros municípios ou estados são aceitas?
3. A consulta de CNPJ por API (dados abertos da Receita) basta, ou exigem o comprovante emitido no site da Receita?
4. Qual a validade máxima da pesquisa de preços?
5. No orçamento final, é aceito "valor proposto ≤ média" ou deve ser exatamente a média?
6. Anúncios de vagas em plataformas de emprego valem como pesquisa salarial? Faixa salarial → qual valor?
7. Pagamento por Recibo/MEI sem encargos é aceito na rubrica de mão de obra?
8. Existe regra de arredondamento exigida?

---

## 5. Como reproduzir

```bash
cd fase0/poc
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m playwright install chromium
venv\Scripts\python build_package.py ..\pacote_modelo_novo
```

> Observação técnica: no Windows, o pacote `anthropic` falha ao instalar em caminhos muito longos (limite de 260 caracteres). Use uma pasta curta para o ambiente virtual ou habilite "caminhos longos" no Windows.

| Script | Validação |
|---|---|
| `store_map.py`, `jsonld_map.py` | Mapa de 60 lojas |
| `ean_discovery.py`, `verify_discovered.py` | Descoberta e verificação por EAN |
| `collect_offers.py`, `matcher_v3.py`, `build_eval_v3.py` | Coleta de 4.812 ofertas e avaliação do comparador |
| `llm_match_eval.py` | Experimento de IA (`--dry-run` funciona sem chave) |
| `jobs_collect.py`, `jobs_dedup.py` | Vagas e deduplicação |
| `closing_strategies.py` | Estratégias de fechamento no teto |
| `mao_de_obra.py` | Jornadas legais, horas e regimes |
| `build_package.py` | Pacote de evidências-modelo completo |
