# 01 — Registro de decisões

Cada decisão tem um código (D-xx) para ser citada no código e nos testes.
**Origem:** *Usuário* = definida pelo usuário; *Proposta aceita* = recomendada e aprovada pelo usuário.
Todas foram tomadas em 22/09/2026, salvo indicação. Decisões marcadas **(configurável)** viram parâmetros do perfil de regras ([05-regras-padrao.md](05-regras-padrao.md)).

## Produto e escopo

| Código | Decisão | Origem |
|---|---|---|
| D-01 | O sistema é construído pelo usuário com o Claude Code. | Usuário |
| D-02 | **Custo zero:** só componentes gratuitos. Serviços pagos podem ser plugados, nunca exigidos. | Usuário |
| D-03 | **Universal:** começa na CPIS 26 de Julho, mas deve servir qualquer OSC. Código aberto, licença **AGPL-3.0**. | Usuário / Proposta aceita |
| D-04 | **Genérico:** nenhum projeto ou secretaria é base central. Casos reais servem só como informação e casos de teste. | Usuário |
| D-05 | **Local primeiro:** roda no computador da OSC, com interface web em `localhost` e dados numa pasta (pode ficar no OneDrive/Google Drive para backup). Uma versão hospedada poderá vir depois, com o mesmo código. | Proposta aceita |
| D-06 | Âmbito inicial: município e Estado de São Paulo, secretarias diversas. Tudo o que varia entre elas é configurável. | Usuário |
| D-07 | Não é preciso reproduzir o modelo de documento de cada secretaria. Basta que as saídas contenham a informação (grade comparativa, plano de aplicação, cronogramas, memória de cálculo). | Usuário |

## Fontes e evidências

| Código | Decisão | Origem |
|---|---|---|
| D-10 | Padrão: **1 cotação com 3 fontes** por produto ou cargo. **(configurável)** | Usuário |
| D-11 | Lojas virtuais são aceitas. | Usuário |
| D-12 | Validade das pesquisas: **180 dias**. **(configurável)** | Usuário |
| D-13 | Evidência de cada fonte: **PDF com print da página, link, data e hora**, agrupado por cotação, mais o **comprovante oficial da Receita** de cada empresa, loja ou órgão. | Usuário |
| D-14 | O comprovante oficial tem captcha: é obtido por **captura assistida** (o usuário resolve o captcha e o sistema salva o PDF). Um comprovante é reaproveitado por **30 dias**. **(configurável)** | Proposta aceita |
| D-15 | Preço **sem frete**. O **CEP de referência** é definido no sistema, por projeto. | Usuário |
| D-16 | Marketplace é aceito. Vale o **CNPJ do vendedor**. Cada orçamento comparativo tem **um único vendedor (CNPJ)**. Anúncio sem CNPJ do vendedor identificável é descartado. | Usuário / Proposta aceita |
| D-17 | **Mesmo produto = mesma marca, mesmo modelo e mesma apresentação** (tamanho, peso, volume, quantidade na embalagem). | Usuário |
| D-18 | Fontes alternativas (atas de registro de preço, Painel de Preços, CAGED, convenções coletivas) podem ser habilitadas por perfil de regras. **(configurável)** | Usuário |
| D-19 | Aceita o CNPJ alfanumérico (atribuído desde julho/2026). | Proposta aceita |

## Materiais e preço final

| Código | Decisão | Origem |
|---|---|---|
| D-20 | A base do preço final é escolhida por orçamento: **Regra A** (média arredondada) ou **Regra B** (preço real da loja de menor total). **(configurável)** | Usuário |
| D-21 | **Arredondamento comercial:** pela terceira casa decimal, 5 ou mais sobe e menos de 5 desce (ex.: R$ 15,556 → R$ 15,56; R$ 15,554 → R$ 15,55). | Usuário |
| D-22 | **Regra B sem misturar lojas:** todos os itens do lote entram no orçamento final com o preço da loja de menor total. | Usuário |
| D-23 | Na Regra B, nenhum item pode ter preço acima da média da sua cotação. Se tiver, há duas saídas: **(1) trocar o produto** e cotá-lo nas mesmas 3 lojas; **(2) trocar a loja**: a loja de menor total sai do trio, entra a próxima da classificação e todos os itens são pesquisados nela. O sistema apresenta as opções encontradas e o usuário escolhe. | Usuário |
| D-24 | Cada orçamento (rubrica) tem o seu trio de lojas. Lotes dentro de uma mesma rubrica são permitidos. | Usuário |
| D-25 | Os orçamentos comparativos usam **as mesmas quantidades** do orçamento final. | Usuário |
| D-26 | O Orçamento 1 é o de menor total. A loja escolhida precisa continuar sendo a de menor total **com as quantidades finais** (restrição do otimizador). | Proposta aceita |
| D-27 | A escolha das lojas segue sempre o mesmo critério objetivo. O sistema nunca troca uma loja para subir a média. | Proposta aceita |

## Teto e otimização

| Código | Decisão | Origem |
|---|---|---|
| D-30 | O **teto é do projeto** (soma de todos os orçamentos) e deve ser atingido **exatamente, ao centavo**. Limites por rubrica (mínimo, máximo, %) são opcionais. **(configurável)** | Usuário / Proposta aceita |
| D-31 | **Preços unitários nunca são alterados.** Só mudam quantidades e horas. | Usuário |
| D-32 | O otimizador pode alterar **quantidades** e **horas por mês** numa margem de **±20%** (ajustável por linha ou travada), sem passar da jornada legal. Os **meses** de cada linha são definidos pelo usuário. **(configurável)** | Proposta aceita |
| D-33 | Se não houver solução, o sistema demonstra o motivo e sugere alterações possíveis. | Usuário |

## Mão de obra

| Código | Decisão | Origem |
|---|---|---|
| D-40 | Uma cotação por cargo com **3 vagas**. A mesma cotação vale para todos os postos do mesmo cargo. | Usuário |
| D-41 | O valor de referência é a **média das 3 vagas** (arredondada, D-21). | Usuário |
| D-42 | Divisor mensal = **jornada semanal máxima legal do cargo × 5** (44h → 220; 40h → 200; 36h → 180; 30h → 150). | Usuário / Proposta aceita |
| D-43 | Sequência de cálculo: média → valor-hora = média ÷ divisor → valor mensal = valor-hora × horas por mês → total = valor mensal × meses × postos. Arredondamento comercial a cada etapa. Horas podem ter decimais. | Usuário / Proposta aceita |
| D-44 | **Encargos não entram** no cálculo. | Usuário |
| D-45 | Regime definido por cargo. **Prioridade: MEI**, se a ocupação for permitida ao MEI; senão **Recibo (RPA)**. CLT disponível. Cada regime pode ter cálculo próprio (padrão: igual). **(configurável)** | Usuário |
| D-46 | Vaga com faixa salarial usa **o menor valor**. Vaga **sem salário** é descartada. Vaga cuja **empresa não pode ser identificada** com segurança é descartada. | Usuário / Proposta aceita |
| D-47 | Não há exigência de mesmo município nem idade máxima da vaga (a validade da pesquisa continua valendo). | Usuário |
| D-48 | Entre as vagas válidas, usam-se as **3 de menor salário**. | Proposta aceita |
| D-49 | A mesma vaga da mesma empresa encontrada em plataformas diferentes conta **uma vez só**. | Usuário |

## Inteligência artificial

| Código | Decisão | Origem |
|---|---|---|
| D-50 | IA **opcional e plugável**: o sistema funciona sem IA (com mais itens para revisão manual). Padrão gratuito: plano grátis do Gemini ou modelo local. Qualquer outra chave pode ser usada. | Proposta aceita |
| D-51 | Só dados públicos são enviados à IA (títulos e descrições de produtos e vagas). Nunca dados da OSC ou de pessoas. | Proposta aceita |
| D-52 | A IA nunca é origem de número; só propõe. Pode rebaixar a confiança de uma correspondência, nunca aumentar. | Proposta aceita |

## Preço de referência (decididas em 23/09/2026, a partir do [levantamento das lojas](07-levantamento-lojas.md))

| Código | Decisão | Origem |
|---|---|---|
| D-60 | **Pix:** usa-se o preço normal (cartão ou boleto à vista), nunca o preço com desconto Pix. **(configurável)** | Proposta aceita |
| D-61 | **Clube, fidelidade, assinatura ou cadastro:** usa-se o preço para qualquer comprador, sem cadastro, login ou cupom. **(configurável)** | Proposta aceita |
| D-62 | **Promoção aberta a todos** ("de R$ X por R$ Y"): vale o preço atual (Y), que fica registrado na evidência. **(configurável)** | Proposta aceita |
| D-63 | **Preço por quantidade** (atacado, "leve mais, pague menos"): usa-se sempre o **preço unitário**. Assim o preço não muda quando o otimizador ajusta quantidades. **(configurável)** | Proposta aceita |

## Premissas assumidas (não discutidas; revisar se necessário)

| Código | Premissa |
|---|---|
| P-01 | *Confirmada e substituída pelas decisões D-60 a D-63.* |
| P-02 | Na Regra B, o preço da loja escolhida é comparado com a **média exata** (sem arredondar), que é mais rigorosa que a média exibida na grade. **(configurável)** |
| P-03 | As 3 fontes de uma cotação precisam ter **CNPJs diferentes** (duas filiais da mesma empresa contam como uma). |
| P-04 | Na mão de obra, as 3 vagas de uma cotação precisam ser de **empresas diferentes**. **(configurável)** |
| P-05 | A classificação das lojas é feita com as **quantidades planejadas**. Depois da otimização, o sistema confere se a classificação continua valendo (ver [03](03-modelo-matematico.md)). |
| P-06 | Desembolso padrão: parcela única no 1º mês. **(configurável)** |
