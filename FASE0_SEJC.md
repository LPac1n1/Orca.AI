# Fase 0 — Regras da SEJC e validação com o caso real

**Data:** 25/09/2026 · Complementa [FASE0_RESULTADOS.md](FASE0_RESULTADOS.md) e [ANALISE_ARQUITETURA.md](ANALISE_ARQUITETURA.md)
**Base:** `docs-base/` (Pareceres Técnicos 1 a 8 da Secretaria da Justiça e Cidadania de SP, grade comparativa, orçamentos e Plano de Trabalho do Parecer 8)
**Scripts e dados:** [`fase0/sejc/`](fase0/sejc/)

Decisões do usuário aplicadas: **custo zero**; faixa salarial pelo **valor mínimo**; vagas de empresa confidencial **excluídas**; CEP **03977-015**; lista de lojas escolhida por mim.

---

## 1. Resumo

| Validação | Resultado |
|---|---|
| Regras extraídas dos 8 pareceres | **17 regras**, cada uma com o parecer de origem |
| Verificador aplicado ao Plano do Parecer 8 | Encontrou **os mesmos 14 itens acima da média que a SEJC apontou**, com as mesmas diferenças ao centavo; nenhum a mais, nenhum a menos |
| Cálculo de mão de obra da organização | Reproduzido ao centavo nos **11 cargos** |
| Validade das pesquisas | Detectou que as pesquisas de 23/03/2026 **venceram em 19/09/2026** |
| CNPJs da grade (32, consultados em API gratuita) | **2 BAIXADOS**, que a SEJC ainda não apontou: ORSEGUPS (baixada em 31/12/2025, incorporação) e Mercado Janko (baixada em 23/09/2025). Ambos já estavam baixados quando a pesquisa foi feita |
| Plano corrigido fechando em R$ 150.000,00 | **Solução exata** em 4 cenários; em um deles, impossibilidade comprovada |
| Carrinho automático no formato aceito, com o CEP | 🟢 **Atacadão** (API) e 🟢 **Tenda** (navegador); Carrefour acessível, falta testar o carrinho |

---

## 2. Regras da SEJC (implementadas em [`sejc_regras.py`](fase0/sejc/sejc_regras.py))

| # | Regra | Parecer |
|---|---|---|
| R01 | Média = soma dos 3 orçamentos ÷ 3, calculada com exatidão (na prática: arredondamento comercial ao centavo) | PT1 |
| R02 | Valor unitário/mensal do plano **não pode ultrapassar a média** da grade | PT1, PT6, PT7, PT8 |
| R03 | Valor **abaixo do menor orçamento** exige justificativa por ofício | PT1, PT4 |
| R04 | Total = valor unitário × período, **sem divergência de centavos** | PT4, PT5 |
| R05 | A soma do plano não pode ultrapassar o recurso (teto) | PT4 |
| R06 | Pesquisas em sites e plataformas valem **180 dias** | PT5, PT8 |
| R07 | CNPJ válido e **ATIVO** (INAPTA e inválido foram rejeitados) | PT2, PT4 |
| R08 | A grade identifica a **empresa ofertante** (nome + CNPJ), nunca a plataforma (Catho, Indeed…) | PT1, PT2, PT3 |
| R09 | Não usar duas pesquisas da **mesma empresa** para o mesmo serviço | PT2 |
| R10 | As 3 simulações de compra com as **mesmas quantidades e especificações** | PT1, PT2 |
| R11 | Faixa salarial ("R$ 2 mil – R$ 4 mil") → usar o **menor valor** | PT1 |
| R12 | Pesquisa com várias opções (planos): adotar o **menor**, salvo justificativa | PT4, PT5 |
| R13 | Materiais **discriminados por subitem**, com valor de cada produto | PT1, PT4 |
| R14 | **Frete** não pode constar no plano | PT1 |
| R15 | Vaga publicada por **site agregador** (e não pela empresa recrutadora) não vale | PT2 |
| R16 | Descrição da rubrica **igual** à descrição das pesquisas | PT1 |
| R17 | Horas mensais **inteiras** (horas fracionadas, como 78,81003 h, geraram divergência de centavos) | PT5 |

Outras orientações encontradas: comprovante de simulação **precisa mostrar o valor total** (PT1); a empresa executora não precisa ser definida na formalização (PT2); Prestação de Contas não entra como etapa do plano (PT2, PT4, PT5); contratação por Recibo/MEI foi aceita após justificativa por ofício (PT4).

---

## 3. Como a organização calcula e o que a SEJC já aceitou

A partir do Plano de Trabalho do Parecer 8 (R$ 150.000,00), descobri a fórmula usada, que **bate ao centavo nos 11 cargos**:

> **valor mensal = arredondar(média ÷ 180; 2) × horas mensais** (Assistente Social: ÷ 120)
> Ex.: Coordenador: 5.000,67 ÷ 180 = 27,78 × 91 h = **R$ 2.527,98**

A SEJC analisou esse cálculo em 8 rodadas **sem objeção ao divisor**. As pendências foram outras: centavos, média, CNPJ, validade e empresa × plataforma.

**O teto é do projeto inteiro**, não de cada orçamento. A organização fechava os R$ 150.000,00 escolhendo horas "quebradas" (91 h) e, antes, horas fracionadas (78,81003 h), que a SEJC recusou.

**Materiais:** o plano usava os preços de **uma só loja** (orçamento 1) como valor de cada subitem. Quando essa loja era mais cara que a média, o item estourava a média. Foi exatamente o que gerou os 14 apontamentos do Parecer 8.

---

## 4. Plano corrigido: fechando em exatamente R$ 150.000,00 ([`otimizar_pt8.py`](fase0/sejc/otimizar_pt8.py))

Variáveis: horas mensais **inteiras** de cada cargo e valor de cada subitem **entre o menor orçamento e a média** (R02 + R03). Quantidades e meses como no plano. Toda solução foi **reverificada** contra as regras.

| Cenário | Resultado | O que muda |
|---|---|---|
| **A** — divisor 180/120 (aceito), horas mantidas | ✔ R$ 150.000,00 | Os 14 itens descem para a média; o Sistema de Gestão sobe de R$ 270,92 para R$ 346,12 para compensar |
| **A** — divisor 180/120, horas ajustáveis | ✔ R$ 150.000,00 | Coordenador 91 → 93 h; 1 Assistente Social 40 → 41 h; centavos em 2 itens |
| **B** — jornada legal (220/150), horas mantidas | ✘ **Impossível** | Mão de obra cai para R$ 99.454,96; mesmo com todos os materiais na média, **faltam R$ 21.067,02** |
| **B** — jornada legal, horas ajustáveis | ✔ R$ 150.000,00 | Todas as horas sobem ~22% (Coordenador 114 h, Assistente Social 50 h, Orientador 73 h…) para manter o mesmo pagamento mensal |

**Modo "valores defensáveis"** (`--discreto`): cada valor de subitem precisa ser **o preço de uma das 3 lojas ou a própria média**, nunca um número inventado para fechar a conta. Resultado no cenário A com horas ajustáveis:

- **3 mudanças de horas** (Coordenador 92 h, Assistente Social 42 h, Auxiliar Administrativo 91 h);
- todos os valores de materiais são preços reais ou a média.

**É a solução que eu recomendo.**

---

## 5. Evidências: o formato que a SEJC aceita e o que já é automatizável

| Evidência aceita | Formato visto em `docs-base` | Automação testada |
|---|---|---|
| **Materiais** | Página "Meu Carrinho" da loja: itens, quantidades, subtotal, CNPJ no rodapé | 🟢 **Atacadão**: carrinho montado pela API pública + página capturada. 🟢 **Tenda**: CEP + adicionar + página do carrinho, pelo navegador. 🟡 **Carrefour Mercado**: abre sem bloqueio e mostra preço; carrinho ainda não testado |
| **Vagas** | Página da vaga impressa (faixa, empresa, data, URL) | 🟢 Fase 0 (InfoJobs, Catho, Vagas.com); agora usando o **mínimo da faixa** e o **CNPJ do empregador** |
| **CNPJ** | **Comprovante oficial** de Inscrição e Situação Cadastral da Receita | 🔴 Não automatizável: o site da Receita tem CAPTCHA e **não deve ser contornado**. O sistema consulta a situação em API gratuita (triagem) e gera a lista de links para a pessoa emitir os comprovantes. **Nunca gera documento imitando o oficial** |

**Achados do teste de carrinho com o CEP 03977-015:**
- Das 14 lojas com API aberta, **só 3 entregam nesse CEP** (Atacadão, Sam's Club, Telhanorte). A maioria é rede regional de outros estados.
- **Filtrar por palavras-chave deixou passar produtos errados**: "Limpol **Pack 6**", "**Kit** Saco de Lixo", "Tixan **Maciez**", "Desinfetante **Candura**" no lugar de "Bak Ypê". O método correto é: **você escolhe o produto de referência (EAN) uma vez**, e o sistema procura **exatamente esse EAN** em cada loja.
- Produtos que vocês usavam em março estão **esgotados** hoje em algumas lojas nesse CEP (ex.: Água Sanitária Ypê 5L e Bak Ypê 5L na Atacadão). O sistema precisa mostrar isso e sugerir a troca, sem trocar sozinho.
- O preço no carrinho pode diferir do preço da busca (Tenda: R$ 15,49 × R$ 15,59). **Vale o do carrinho.**
- O frete aparece no total do carrinho, mas **não entra no plano** (R14): usa-se o subtotal dos itens.

### Leitura automática do PDF de carrinho impresso por você ([`ler_carrinho_pdf.py`](fase0/sejc/ler_carrinho_pdf.py))

Para lojas que bloqueiam robôs (ex.: o Carrefour quebrou ao receber o CEP pela automação), o caminho gratuito e universal é: **você imprime o carrinho em PDF, e o sistema lê e confere**. Validado nos **6 carrinhos reais aceitos pela SEJC** (limpeza e papelaria: Carrefour, Tenda, Atacadão, Lepok, Kalunga, Gimba):

| Resultado | |
|---|---|
| Preços lidos automaticamente | **45/45** |
| Preços corretos (conferem com a grade) | **45/45, zero erros** |
| Soma lida = total impresso no carrinho = total da grade | **6/6** |

O leitor só aceita um preço com **conferência**: unitário × quantidade = subtotal, o mesmo valor impresso como unitário e como subtotal, ou um valor rotulado "Subtotal". Ignora preços promocionais do tipo "Leve 5 ou + R$ 33,30 cada". Sem conferência, o item vai para revisão humana, nunca para um preço presumido.

**Descobertas: a Gimba é a Supricorp** (CNPJ 54.651.716/0011-50 no carrinho). E o PDF de alimentação do Tenda é **imagem sem texto**: exigiria OCR ou conferência humana.

### Conferência de especificação ([`conferir_especificacao.py`](fase0/sejc/conferir_especificacao.py))

Nos carrinhos de **alimentação aceitos pela SEJC**, a conferência automática "descrição da grade × produto no carrinho" encontrou divergências que **passaram despercebidas**:

| Item da grade | Produto no carrinho | Loja |
|---|---|---|
| **Manteiga** com sal 1 kg | **Margarina** Qualy com sal 1 kg | Atacadão e Carrefour |
| Sardinha com tomate **125 g** | Sardinha Gomes da Costa Tomate **75 g** (mais barata por ser menor) | Atacadão |
| Café 500 g (10 unidades) | **Dois produtos**: 5 Pilão Vácuo + 5 Pilão Almofada | Atacadão e Carrefour |

Isso confirma que a regra "mesmo produto / mesma especificação" (R10, R16) precisa ser checada **por máquina**. A SEJC confere médias e CNPJs, mas não conferiu esses produtos, e isso pode aparecer na prestação de contas.

### Lista de lojas escolhida (CEP 03977-015)

| Rubrica | Trio principal | Reservas | Situação |
|---|---|---|---|
| Alimentação / Limpeza | **Atacadão, Tenda, Carrefour Mercado** (o mesmo trio que a SEJC já aceitou) | Sam's Club (API, entrega no CEP; preço de clube, a confirmar), Pão de Açúcar | Atacadão 🟢 automático; Tenda 🟢 automático; Carrefour 🟢 **via PDF impresso por você** (a automação quebra a página) |
| Material pedagógico / escritório | **Kalunga, Lepok, Gimba (Supricorp)** (trio já aceito) | Livrarias Curitiba (API) | Kalunga e Lepok abrem sem bloqueio; as 3 validadas via PDF impresso (45/45) |
| Sistema de gestão | F&D Solutions, Ongsys, Instituto Ekloos (páginas de preço) | — | Captura de página (🟢 Fase 0) |
| Vagas | Catho (mínimo da faixa + empregador), InfoJobs, Vagas.com | Glassdoor, Indeed, LinkedIn (manual) | 🟢 |

---

## 6. Custo zero: o que muda na arquitetura

| Componente | Antes | Agora (custo zero) |
|---|---|---|
| IA para comparar produtos | API paga (~US$ 0,74 por lote) | **Removida do caminho obrigatório.** Comparação = EAN escolhido por você + regras (Fase 0: 1,2% de "erro" e todos eram o mesmo produto com dois EANs) + sua revisão dos casos amarelos |
| IA opcional | — | **Modelo local gratuito** (este computador tem 16 GB de RAM; roda um modelo pequeno, devagar). Exige baixar ~2–5 GB; **só com sua autorização** |
| CNPJ | APIs gratuitas | Mantidas (BrasilAPI → MinhaReceita), com cache |
| Preços | API VTEX + navegador | Mantidos: gratuitos |
| Otimização | OR-Tools | Mantido: gratuito |
| Hospedagem / banco | Nuvem com plano gratuito | **Local**: roda neste computador, banco SQLite, evidências numa pasta sincronizada no OneDrive |
| Comprovante oficial de CNPJ | — | Passo humano (CAPTCHA), com lista de links gerada pelo sistema |

---

## 7. Decisões pendentes

1. **Divisor de horas.** A regra que você definiu (jornada legal: 220/150) é juridicamente mais sólida. Mas a SEJC **já aceitou 180/120 em 8 análises** sem objeção, e com a regra legal o plano atual **não fecha** sem aumentar as horas em ~22% (ou reduzir o pagamento dos profissionais). Manter a jornada legal ou voltar ao 180/120 já aceito?
2. **Modo "valores defensáveis"** (todo valor = preço de uma loja ou a média): recomendo como padrão. Confirma?
3. **Produtos de referência:** para cada item, o sistema propõe o EAN e você confirma (ex.: "Tixan **Primavera** 1,6 kg", não "Power Act").
4. **Modelo de IA local (opcional, gratuito):** autoriza baixar e testar? Se não, o sistema funciona sem IA.
5. **Sam's Club** como reserva (preço de clube de assinatura): aceitável?

## 8. Próximo passo sugerido

Construir o **MVP local e gratuito** com o que já está validado:
- motor de regras SEJC (R01–R17);
- verificador (que já reproduz o Parecer 8);
- otimizador do Plano de Aplicação;
- carrinho automático em Atacadão e Tenda (depois Carrefour e papelarias);
- captura de vagas;
- lista de CNPJs para emissão dos comprovantes;
- exportação da **Grade Comparativa** e do **Plano de Aplicação** no formato da SEJC.
