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
| D-14 | O comprovante oficial tem captcha. A Receita recusa a verificação feita na janela aberta pelo sistema, mesmo resolvida pela pessoa ("Erro ao validar captcha", piloto, 24/09/2026), e o sistema não se disfarça (D-67). Por isso o comprovante é emitido **no navegador da própria pessoa** (o sistema abre a página com o CNPJ preenchido), salvo em PDF e **enviado ao sistema**, que confere se é o comprovante daquele CNPJ e lê a data de emissão. Um comprovante é reaproveitado por **30 dias**. **(configurável)** | Proposta aceita; revista no piloto |
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
| D-60 | **Forma de pagamento (revista no piloto, 24/09/2026):** usa-se o preço **no Pix**; se a página não tiver preço no Pix, o preço **no boleto**; **nunca o preço parcelado**. Sem forma de pagamento escrita junto do preço, vale o preço mostrado. O valor escolhido é sempre um dos escritos na página, perto do preço do produto, e a prova registra qual foi. *Antes: preço normal, sem o desconto Pix.* **(configurável: `preco_referencia.desconto_pix`)** | Usuário |
| D-61 | **Clube, fidelidade, assinatura ou cadastro:** usa-se o preço para qualquer comprador, sem cadastro, login ou cupom. **(configurável)** | Proposta aceita |
| D-62 | **Promoção aberta a todos** ("de R$ X por R$ Y"): vale o preço atual (Y), que fica registrado na evidência. **(configurável)** | Proposta aceita |
| D-63 | **Preço por quantidade** (atacado, "leve mais, pague menos"): usa-se sempre o **preço unitário**. Assim o preço não muda quando o otimizador ajusta quantidades. **(configurável)** | Proposta aceita |

## Aprendizado e acesso às lojas (decididas em 23/09/2026)

| Código | Decisão | Origem |
|---|---|---|
| D-64 | **Pares rotulados alimentados pelo uso:** cada confirmação ou recusa de correspondência feita pelo usuário vira um par rotulado do conjunto de referência; pares com o mesmo código de barras em lojas diferentes entram como "mesmo produto" sem precisar de rótulo. Só dados públicos do produto (título, marca, código de barras, loja). | Proposta aceita |
| D-65 | **Catálogo de atributos e vocabulário evoluem por sugestão:** o sistema sugere inclusões a partir das decisões (ex.: um sabor novo, um sinônimo); o usuário aprova. Antes da aprovação, o teste de correspondência (T-11) roda com todos os pares e mostra o efeito; mudança que crie qualquer 🟢 errado é barrada. As mudanças ficam numa camada da OSC, com versão, por cima do catálogo do sistema, e podem ser compartilhadas. | Proposta aceita |
| D-66 | **Edição fácil pelo usuário:** pares, catálogo de lojas, atributos e vocabulário podem ser vistos, editados e ampliados pela interface, sem mexer em arquivos. Toda edição passa pela mesma conferência (T-11) e fica no histórico. | Usuário |
| D-67 | **Lojas que recusam acesso automático** (ex.: a busca do Carrefour e do Extra recusa o navegador sem janela, 23/09/2026): o sistema não se disfarça, não resolve captcha e não entra em contas por conta própria. Camadas, em ordem: página do produto pelo link (C1); link achado pelo código de barras num buscador (C2, opcional); **captura assistida** numa janela visível em que **quem navega é o usuário** (C4), com fila para fazer todas de uma vez; PDF salvo pelo usuário no próprio navegador e enviado ao sistema, com conferência do endereço e do preço. Se nada funcionar, a loja fica de fora e o dossiê registra "não pesquisada: acesso bloqueado". Lojas de acesso aberto têm prioridade, e o sistema avisa antes quantas capturas assistidas o orçamento vai exigir. **Robots.txt (25/09/2026):** antes de ligar a busca automática de uma loja, o sistema confere o robots.txt dela; se ele proíbe a busca para programas, a loja fica com janela (Gimba e Tenda, levantamento em docs/07 §5). | Proposta aceita |
| D-68 | **Busca automática por lote (Fase 2, etapa 10):** o usuário escolhe as lojas; o sistema pré-marca as do catálogo que vendem todas as categorias do lote. Em cada loja, os itens são pesquisados do mais difícil ao mais fácil (o que está em menos lojas; sem código de barras antes). A busca só aponta o caminho: o melhor candidato (🟢 primeiro, depois o 🟡 mais parecido; nunca 🔴) tem a **página do produto capturada como prova**, exatamente como ao colar o link; se a página mostrar outro produto, tenta o seguinte (no máximo 2 por item e loja). Se a primeira busca não trouxer um candidato bom, tenta uma segunda, sem as medidas. Achado o código de barras numa loja, as que aceitam busca por código (API VTEX) são pesquisadas por ele, por último. Se a loja não tem um item, fica registrado "não encontrado" com a página da busca como prova e **a busca continua nos outros itens** (revista em 25/09/2026, a pedido do usuário: com todos os preços na tela, o item que falta pode ser trocado — D-72). Página recusada pela pessoa (🔴) não volta. Pelo menos 3 s entre dois pedidos à mesma loja; o sistema se identifica como Orça.AI. Lojas que recusam programas (Carrefour, Extra) entram como capturas com janela, uma por item, abertas na busca da loja; o sistema avisa antes quantas serão. | Usuário (confirmada em 25/09/2026) |
| D-69 | **Vagas: a busca é feita pela pessoa, na janela (Fase 2, etapa 11).** Conferido em 24/09/2026: os termos de uso do Indeed proíbem "usar qualquer sistema automatizado (bots, scrapers, spiders, IA ou IA agêntica) para acessar, extrair dados […] sem a permissão expressa por escrito"; o robots.txt da Catho proíbe programas na busca (`/buscar/vagas/`, `?q=`) e o da Vagas.com nas pesquisas (`/vagas/pesquisas`); o LinkedIn exige login; os termos da InfoJobs não foram conferidos (por prudência, janela). Por isso o sistema não pesquisa vagas sozinho: para cada plataforma escolhida, abre a janela na busca já preenchida com o cargo e a cidade; a pessoa escolhe a vaga e clica em "Capturar agora"; o sistema guarda a prova e lê salário e empresa. Link de vaga colado: Catho, InfoJobs e Vagas.com podem ser abertos pelo sistema (o robots.txt permite as páginas de vaga); Indeed e LinkedIn só na janela. Catálogo em `catalogos/vagas.yaml`. Busca automática de salários só por fontes que permitam (ex.: dados públicos do CAGED ou API oficial), em etapa futura. **Revista em 25/09/2026 (escolha do usuário):** com a chave da SerpApi (D-70), o sistema procura as vagas no **Google Vagas** (uma busca por cargo e cidade; o Google junta as vagas de várias plataformas). As vagas das plataformas que permitem programas (Catho, InfoJobs, Vagas.com) são capturadas sozinhas, até 6, preferindo as que mostram salário; as do Indeed, do LinkedIn e de outros sites ficam listadas para abrir na janela. O salário que o Google mostra não é prova: vale o da página da vaga. Outras APIs avaliadas e recusadas: Adzuna (uso grátis só pessoal ou para publicar os anúncios deles), Jooble (500 pedidos por chave, no total), SINE/Emprega Brasil (sem API pública de busca). | Usuário |
| D-70 | **Opcionais (Fase 2, etapa 15):** tudo desligado por padrão; o sistema funciona sem eles (D-50). **Buscador (SerpApi, C2):** uma busca do Google por item, só para achar páginas em lojas fora do catálogo; os resultados passam pela correspondência (🔴 saem) e **a pessoa escolhe** quais páginas o sistema lê — cada uma é conferida como link colado. **IA:** a primeira tarefa é conferir os 🟡 (docs/04 §6): responde "sim", "não" ou "incerto"; "não" rebaixa para 🔴 com o motivo, "sim" e "incerto" mantêm 🟡 (quem aprova é a pessoa, D-52); cada resposta fica na correspondência, com autor `ia:<provedor>`, e a pessoa pode desfazer. Provedores: Gemini (plano grátis; a chave vai no cabeçalho) ou modelo local (Ollama). **Chaves** no Gerenciador de Credenciais do Windows (biblioteca keyring); a escolha do provedor, no config.json do computador; nunca na pasta de dados, no banco ou nos documentos. | Usuário (confirmada em 25/09/2026) |
| D-71 | **Produto de referência (25/09/2026):** a primeira página que uma pessoa confirma como o mesmo produto de um item vira a referência dele (dá para trocar, com justificativa). As outras lojas passam a ser comparadas também com ela: mesmo código de barras da referência = 🟢 (D-24, automação `correspondencia_ean`); atributo diferente do da referência (ex.: 90 g × 75 g) = 🔴; marca e atributos iguais aos da referência = 🟢 por atributos (com a aprovação que o perfil pede). Quando a referência muda, as páginas do item que não foram decididas por uma pessoa são comparadas de novo. O código de barras da referência também é usado na busca. | Usuário |
| D-72 | **Fechar o lote (25/09/2026):** o botão "Fechar o lote" pesquisa todos os itens nas lojas escolhidas (D-68), mostra o que falta — produtos a confirmar (um por item, com as fotos lado a lado, D-73) e itens que faltam nas 3 lojas mais completas — e, para cada item que falta, procura produtos de outra marca que existam nessas 3 lojas e **sugere** a troca, do menor preço somado para o maior. Nada é trocado sem a pessoa (princípio 8); a troca é a Saída 1 de sempre (item novo; o antigo no histórico) e as páginas da escolhida entram na fila como prova. | Usuário |
| D-73 | **Fotos lado a lado (25/09/2026):** ao conferir um produto, a tela mostra a foto de cada loja (lida da página: dados do produto ou `og:image`) e a do produto de referência, lado a lado. A foto só ajuda a pessoa a decidir: não decide sozinha (a mesma foto serve para 395 g e 1 kg). | Usuário |
| D-74 | **O que cada loja vende (25/09/2026, pedido do usuário):** o sistema separa as lojas pelo que vendem (papelaria e escritório, alimentos, bebidas, limpeza e higiene, descartáveis, utensílios, informática) e, em cada lote, mostra primeiro as **indicadas** (vendem tudo o que o lote tem, já marcadas as de busca automática), depois as que vendem só parte, as ainda sem tipo e, escondidas, as outras. Loja nova com busca automática: o sistema **descobre sozinho** o que ela vende, testando a busca com produtos típicos de cada tipo (caneta, grampeador, papel sulfite; arroz, café; refrigerante, suco; detergente, água sanitária; copo descartável, guardanapo; panela, talheres; mouse, cartucho) — vende o tipo quando a busca traz pelo menos 2 produtos dele; uma vez por loja, no ritmo das buscas. Todas as lojas (também as só com janela) **aprendem** com as páginas confirmadas (🟢) nas pesquisas. A pessoa pode corrigir no formulário da loja; a escolha dela vale mais que a descoberta. | Usuário |

## Premissas assumidas (não discutidas; revisar se necessário)

| Código | Premissa |
|---|---|
| P-01 | *Confirmada e substituída pelas decisões D-60 a D-63.* |
| P-02 | Na Regra B, o preço da loja escolhida é comparado com a **média exata** (sem arredondar), que é mais rigorosa que a média exibida na grade. **(configurável)** |
| P-03 | As 3 fontes de uma cotação precisam ter **CNPJs diferentes** (duas filiais da mesma empresa contam como uma). |
| P-04 | Na mão de obra, as 3 vagas de uma cotação precisam ser de **empresas diferentes**. **(configurável)** |
| P-05 | A classificação das lojas é feita com as **quantidades planejadas**. Depois da otimização, o sistema confere se a classificação continua valendo (ver [03](03-modelo-matematico.md)). |
| P-06 | Desembolso padrão: parcela única no 1º mês. **(configurável)** |
