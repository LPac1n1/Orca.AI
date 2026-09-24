# 02 — Especificação funcional

Este documento descreve **o que** o sistema faz. O **como** está em [03](03-modelo-matematico.md) (cálculos) e [04](04-arquitetura-e-dados.md) (tecnologia). As decisões citadas (D-xx) estão em [01](01-decisoes.md).

## 1. Fluxo geral

```
Projeto ─► Orçamentos (rubricas) ─► Regras ─► Itens e cargos
   ─► Pesquisa (produtos, vagas, CNPJ) ─► Correspondência de produtos
   ─► Cobertura e escolha das lojas ─► Conferência preço × média ─► Resolução de problemas
   ─► Cálculo das cotações e dos orçamentos comparativos
   ─► Otimização (teto exato) ─► Revisão humana ─► Aprovação ─► Documentos e exportação
```

Cada etapa só roda quando a anterior terminou. Qualquer mudança invalida apenas as etapas que dependem dela (ver [04 §3](04-arquitetura-e-dados.md)). Aprovações dadas a observações que não mudaram continuam valendo.

## 2. Projeto

Campos: nome, OSC, órgão/secretaria, instrumento (termo de fomento, colaboração, emenda…), número do processo, **teto** (R$), **duração** (meses), **CEP de referência** (D-15), data prevista de entrega (usada para conferir a validade das pesquisas), perfil de regras.

Ações: criar, editar, duplicar (com ou sem as pesquisas), arquivar, excluir (exclusão lógica; o histórico permanece).

## 3. Orçamentos (rubricas)

Um projeto tem quantos orçamentos precisar. Cada um tem:
- nome e descrição;
- **tipo**: `materiais`, `mao_de_obra` ou `servicos` (serviços são cotados por proposta ou página do fornecedor, como um item);
- **base do preço final**: Regra A ou Regra B (D-20);
- limites opcionais (mínimo, máximo, % do teto) (D-30);
- regras próprias, que sobrepõem as do projeto;
- um ou mais **lotes**.

Ações: criar, duplicar, renomear, arquivar, excluir, recalcular, pesquisar de novo, gerar documentos de novo — cada orçamento de forma independente.

## 4. Perfis de regras

- Herança em camadas: **padrão do sistema → OSC → secretaria/edital → projeto → orçamento**. Cada camada só declara o que muda.
- Todo perfil tem **versão**. Cada cálculo grava a versão exata usada (impressão digital SHA-256 do perfil completo e a lista das camadas).
- O sistema registra **de qual camada veio cada regra**, para responder "por que esta regra vale aqui?".
- Perfis podem ser exportados e importados (arquivo YAML), para OSCs compartilharem perfis de secretarias.
- O perfil padrão e todos os parâmetros estão em [05](05-regras-padrao.md).
- Com IA disponível, o sistema pode ler um edital (PDF) e **propor** um perfil, citando a página de cada regra. O usuário confirma.

## 5. Itens (materiais e serviços)

Cada item tem:
- **descrição genérica** (ex.: "Papel sulfite A4");
- **especificação exata**: marca, modelo, apresentação (ex.: 75 g/m², pacote com 500 folhas) e demais atributos críticos da categoria (D-17);
- código de barras (EAN) e CATMAT, quando conhecidos;
- **quantidade por período**, **meses ativos** (ex.: do 2º ao 11º mês) e margem de ajuste (padrão ±20%; pode ser travada) (D-32);
- lote a que pertence.

**Sugestão de quantidade** (quando o usuário não informa): fórmula com parâmetros visíveis (participantes × consumo por participante × encontros). A IA pode propor os parâmetros. A quantidade sugerida sempre fica 🟡 até ser aprovada.

## 6. Pesquisa de produtos

### 6.1 Escolha das lojas a pesquisar
- **Opção A:** o usuário escolhe as lojas.
- **Opção B:** o usuário informa quantas lojas pesquisar.
- **Opção C:** o sistema define a estratégia a partir do catálogo de lojas da categoria.

O sistema mantém um **catálogo de lojas** por categoria (papelaria, supermercado, limpeza…), com o método de coleta de cada uma. O catálogo é compartilhável entre OSCs.

### 6.2 Estratégia
- **O item mais difícil primeiro:** o item encontrado em menos lojas é pesquisado antes. Uma loja que não o tem é descartada sem gastar as outras buscas.
- **Busca pelo código de barras:** achado o EAN do produto em uma loja, as outras lojas são pesquisadas por ele.
- **Coleta em camadas** (detalhes em [04 §5](04-arquitetura-e-dados.md)): dados estruturados → busca do próprio site → navegador automático → agente de IA (opcional) → captura assistida pelo usuário.
- Todas as pesquisas usam o **CEP do projeto**, sem frete, com o preço de referência das decisões D-60 a D-63: o preço no Pix (sem Pix, no boleto; nunca o parcelado), para qualquer comprador (sem clube, assinatura ou cupom), promoção aberta a todos vale, e sempre o preço unitário.
- Cada loja do catálogo diz **qual dos preços da página** corresponde a essa regra. Os dados estruturados da própria loja às vezes trazem o preço especial (ex.: Pix ou clube), por isso não são aceitos sem essa indicação.
- Conteúdo que só carrega ao rolar a página (inclusive quadros incorporados) é carregado antes da captura.
- **Lojas que recusam acesso automático** (D-67): página do produto pelo link; link achado pelo código de barras num buscador; captura assistida numa janela em que o usuário navega (em fila); ou PDF salvo pelo usuário e enviado. Sem nada disso, a loja fica de fora e o dossiê registra o motivo. Antes de começar, o sistema avisa quantas capturas assistidas serão necessárias.

### 6.3 Resultado de cada tentativa
Cada tentativa gera uma **observação**, encontrada ou não: loja, CNPJ do vendedor, URL, título, marca, modelo, apresentação, EAN, preço (centavos), disponibilidade, data e hora, CEP, método de coleta e evidência. "Não encontrado" também fica registrado, porque prova que a loja foi pesquisada.

**Conferência da extração:** um preço só é aceito se o valor aparecer no HTML salvo da página. Senão, a observação fica 🔴 "Não foi possível validar automaticamente".

## 7. Correspondência de produtos

Objetivo: decidir se o produto encontrado é **exatamente** o item especificado (D-17).

Etapas:
1. **Mesmo EAN** → 🟢. Se a página contradisser o item mesmo assim (ex.: outro peso), 🟡. **EANs diferentes nunca dão 🟢**: o mesmo produto às vezes tem dois códigos (o levantamento achou anúncios iguais com códigos diferentes), então quem confirma é uma pessoa.
2. **Atributos críticos**, comparados pelo programa: marca, modelo e apresentação sempre, mais os atributos da categoria (catálogo `catalogos/atributos.yaml`, [05 §3](05-regras-padrao.md)). Medidas (peso, volume, gramatura, folhas, unidades, medidas, metragem, concentração, voltagem) são lidas e convertidas ("1 kg" = "1.000 g"; "LV 990g PG 900g" = 990 g). Atributos de texto (tipo, sabor, fragrância, cor, embalagem) usam um vocabulário de valores que se excluem (tradicional × extra forte; lavanda × eucalipto; branco × transparente).
   - Todos presentes e iguais → 🟢
   - Algum ausente, ou citado só de um lado → 🟡, com o motivo (ex.: "a página não informa: gramatura (75 g/m²)")
   - Algum diferente → 🔴
   - Palavras ou números que sobram de um lado só (ex.: "orgânico", "252°") → 🟡: uma diferença que o vocabulário ainda não conhece nunca vira 🟢.
   - Item sem marca ou sem categoria conhecida → no máximo 🟡.
3. **IA (opcional)** extrai atributos de textos desestruturados e julga casos 🟡. Ela pode manter 🟡 ou rebaixar para 🔴, **nunca promover para 🟢** (D-52). Só o usuário promove 🟡 para 🟢.

Diferenças só de texto ("Chamex Papel Sulfite A4 75g – 500 fls" × "Papel Sulfite A4 75g Chamex 500 folhas") não impedem 🟢.

Cada resultado é gravado (tabela `correspondencia`, imutável) com o status, a origem e os motivos. Uma decisão do usuário (confirmar ou recusar, com justificativa) é um registro novo; vale o mais recente. O perfil de regras diz se o 🟢 do programa já vale sozinho ou espera confirmação: padrão, **EAN automático** e **atributos com aprovação** (§4 de [05](05-regras-padrao.md)).

**Aprendizado (D-64 a D-66):** cada decisão do usuário vira um par rotulado; pares com o mesmo código de barras em lojas diferentes entram sozinhos. A partir deles, o sistema sugere inclusões no vocabulário e no catálogo de atributos (Fase 2); o usuário aprova depois de ver o efeito no teste de correspondência, e nenhuma mudança que crie um 🟢 errado é aceita. Pares, catálogo de lojas, atributos e vocabulário também podem ser editados diretamente na interface, com a mesma conferência.

## 8. Cobertura, lotes e escolha das lojas

1. **Matriz de cobertura:** lojas × itens do lote, com o status de correspondência.
2. **Lojas elegíveis:** têm **todos** os itens do lote com 🟢, evidência válida e CNPJ do vendedor ativo.
3. **Classificação:** lojas elegíveis ordenadas pelo total do lote (com as quantidades planejadas, P-05). Desempate: qualidade da evidência, depois ordem alfabética (determinístico).
4. **Trio:** as 3 primeiras da classificação. Orçamento 1 = menor total; 2 e 3 em seguida.
5. **Justificativa gerada**, ex.: *"Loja X escolhida: possui os 17 itens e teve o menor total entre as 6 lojas completas."* Todas as lojas pesquisadas e os motivos de descarte vão para o relatório.

**Item bloqueador** (existe em menos de 3 lojas elegíveis): o sistema informa qual item impede o trio, em quantas lojas ele existe e sugere:
- trocar o produto por um alternativo (com as características que o tornam equivalente), com aprovação;
- pesquisar mais lojas;
- se o perfil permitir, criar um lote separado para o item, com o seu próprio trio.

## 9. Conferência preço × média e resolução

### 9.1 Regra A
Preço final de cada item = média das 3 fontes, arredondada (D-21). Não há conferência adicional.

### 9.2 Regra B
Preço final de todos os itens do lote = preço da loja de menor total (D-22). Para cada item, o sistema confere: **preço na loja escolhida ≤ média da cotação** (média exata, P-02).

Se algum item passar da média, o sistema calcula as duas saídas (D-23) e apresenta os resultados para o usuário escolher:

**Saída 1 — Trocar o produto.**
- Buscar produtos alternativos para o item (mesma finalidade, atributos obrigatórios mantidos, outra marca ou modelo).
- Cotar cada alternativa **nas mesmas 3 lojas**, com correspondência 🟢 nas 3.
- Válida se: preço na loja escolhida ≤ nova média, e a loja escolhida continua a de menor total.
- Mostrar as alternativas válidas, da de menor impacto no total para a de maior.

**Saída 2 — Trocar a loja.**
- A loja escolhida sai do trio, com o motivo registrado (ex.: *"Café 500g: R$ 32,09, acima da média de R$ 29,02"*).
- Entra a **próxima loja elegível da classificação**. Se ela ainda não foi pesquisada em todos os itens, o sistema pesquisa.
- O sistema recalcula o trio, a nova loja de menor total e a conferência de todos os itens.
- Se houver novo problema, repete com a próxima loja, até resolver ou acabarem as lojas.
- Mostra a cadeia completa de tentativas e o efeito no total.

Se nenhuma saída resolver, o sistema informa o motivo e sugere pesquisar mais lojas ou aceitar outro produto.

Nunca se troca uma das outras duas lojas do trio para subir a média (D-27).

### 9.3 Conferência de uma grade pronta
Uma grade feita fora do sistema (ex.: planilha) pode ser conferida antes do envio. O sistema recalcula a média unitária, a média do total e os totais de cada linha, e aponta:
- valores informados que não batem com o cálculo (ex.: média unitária R$ 45,97 no lugar de R$ 9,19);
- preços do plano acima da média — a mesma conferência que a secretaria faz.

No caso real de 2026 (caso de teste T-03), essa conferência encontra exatamente os 14 itens da diligência e um erro de média que a secretaria não apontou.

## 10. Mão de obra

### 10.1 Cargos
Cada cargo tem: nome, CBO (quando identificado), número de postos, regime (MEI, Recibo ou CLT; D-45), horas por mês planejadas, meses ativos, margem (padrão ±20%) e **enquadramento de jornada** (tabela em [05](05-regras-padrao.md)).

O enquadramento é feito pela tabela de jornadas (mantida e revisada por humano, com a lei de cada linha). A IA pode sugerir o enquadramento de um cargo, que fica 🟡 até o usuário aprovar.

**Prioridade MEI:** o sistema consulta a lista oficial de ocupações permitidas ao MEI (Resolução CGSN nº 140/2018, Anexo XI, em tabela importável). Se a ocupação não for permitida, usa Recibo e avisa.

### 10.2 Pesquisa de vagas
- Plataformas, na ordem: Catho (mostra faixas salariais), Indeed, InfoJobs, Vagas.com e outras do catálogo; Google Jobs (plano grátis da SerpApi, opcional); LinkedIn só por captura assistida.
- Dados de cada vaga: cargo, empresa, CNPJ (quando encontrado), salário ou faixa, localização, descrição, URL, data de publicação, plataforma, identificador, data e hora da coleta, evidência.

### 10.3 Validação e escolha
1. Descartar: vaga sem salário; empresa não identificável ou confidencial (D-46).
2. Faixa salarial → menor valor (D-46).
3. **Duplicidade** (D-49): mesma empresa, cargo equivalente, salário e localização compatíveis, texto semelhante e datas próximas → mesma vaga, conta uma vez. Quando o Google Jobs lista a mesma vaga em várias plataformas, isso confirma a duplicidade. Casos incertos ficam 🟡.
4. Empresas diferentes na mesma cotação (P-04).
5. Escolha: as **3 de menor salário** entre as válidas (D-48).

### 10.4 Cálculo
Sequência D-43, detalhada em [03 §3](03-modelo-matematico.md). A memória de cálculo mostra a fórmula e todos os valores intermediários.

## 11. CNPJ

**Identificação:**
- Lojas: rodapé do site (o Decreto 7.962/2013 obriga a exibir o CNPJ); em marketplace, a página do vendedor.
- Vagas: busca pelo nome da empresa nos dados abertos da Receita, considerando nome fantasia e município. Mais de um candidato → 🟡 para o usuário. Nenhum → vaga descartada.
- Validação do dígito verificador, inclusive no formato alfanumérico (D-19).

**Situação cadastral:** consulta automática em API gratuita (OpenCNPJ, BrasilAPI ou outra configurada). CNPJ não ativo **bloqueia** o uso da fonte quando o perfil exigir.

**Comprovante oficial (D-13, D-14):** os comprovantes pendentes aparecem em Documentos. Para cada um, o sistema abre a página da Receita no navegador do usuário, com o CNPJ preenchido; o usuário resolve o captcha, clica em "Consultar", salva o comprovante em PDF (Ctrl+P) e o envia. O sistema confere se o PDF é o comprovante daquele CNPJ, lê a data de emissão, liga-o à empresa e o reaproveita por 30 dias. (A janela aberta pelo próprio sistema não serve: a Receita recusa a verificação feita nela.)

## 12. Evidências e validade

Por observação:
- **PDF** da página com cabeçalho: URL, data e hora (Brasília), CEP e impressão digital (SHA-256) da página salva;
- **imagem** da página inteira e **HTML** salvo;
- **SHA-256** de cada arquivo.

Por cotação: um PDF com os 3 prints e os comprovantes da Receita das 3 empresas.

**Validade** (D-12): cada observação vale 180 dias a partir da coleta, contando o dia da coleta (coleta em 23/09/2026 vale até 21/03/2027). O sistema avisa com antecedência (padrão 30 dias) e alerta se alguma evidência vence antes da data prevista de entrega do projeto. Uma pesquisa vencida pode ser refeita com um clique; a antiga fica no histórico.

## 13. Otimização do orçamento final

- Fecha o **teto do projeto exato ao centavo** (D-30).
- Muda só **quantidades** e **horas por mês**, dentro das margens (D-32).
- Mantém a loja escolhida como a de menor total com as quantidades finais (D-26).
- Respeita os limites por rubrica, quando houver.
- Se não houver solução, explica o motivo e sugere o que mudar (D-33).

Formulação completa em [03](03-modelo-matematico.md).

## 14. Revisão humana

Tela principal: **matriz item × fontes**. Para cada item: especificação; as 3 fontes com produto, preço, evidência (miniatura clicável) e CNPJ; média; preço final; quantidade; total; status.

Status por item: 🟢 aprovado · 🟡 revisão necessária · 🔴 problema.

Ações: aprovar, rejeitar, pedir nova pesquisa, trocar produto, trocar fonte, mudar quantidade ou horas, travar linha. Nenhuma ação exige reconstruir o orçamento.

Os **níveis de automação** (automático, automático com aprovação, manual) são definidos por tipo de ação no perfil de regras ([05 §4](05-regras-padrao.md)).

Outras telas:
- **Colar link**, com três jeitos de ler a página: o sistema lê sozinho; janela do navegador em que o usuário navega e clica em "Capturar agora"; ou PDF salvo pelo usuário (D-67). As capturas com janela aparecem no quadro de tarefas, com "Capturar agora" e "Cancelar".
- **Regras** do projeto: as regras que mais mudam de um edital para outro, com o valor em uso e de onde ele vem (padrão do sistema, projeto, orçamento); a regra A/B de cada orçamento; a lista completa para consulta. Cada gravação é uma versão nova.
- **Catálogos da OSC** (valem para todos os projetos da OSC): vocabulário, categorias, lojas e pares de exemplo. Mudanças no vocabulário e nas categorias passam por "Conferir e salvar", que mostra o teste de correspondência antes e depois (D-65, D-66).

## 15. Histórico, auditoria e rastreabilidade

- Todo evento é registrado: criação, alteração, substituição, quantidade, regra, fonte, aprovação, rejeição, nova pesquisa, com quem fez (usuário ou sistema/IA) e quando.
- Nada é apagado: versões anteriores ficam consultáveis.
- **Rastro do valor:** a partir de qualquer número, o usuário navega até a linha de cálculo, a regra (com versão), as 3 observações, as evidências, os CNPJs e comprovantes, e as decisões de correspondência e aprovação.

## 16. Alertas

- Menos de 3 fontes para um item ou cargo.
- Produto sem correspondência exata.
- Item acima da média (Regra B).
- CNPJ não ativo ou comprovante pendente ou vencido.
- Vaga duplicada ou empresa não identificada.
- Página indisponível ou evidência incompleta.
- Pesquisa perto de vencer ou vencida.
- Teto não fechado.
- Conflito de regras.
- Informação insuficiente.
- Aprovação humana pendente.

## 17. Painel

Teto; valor atual; diferença para o teto; nº de itens; aprovados, pendentes e com problema; fontes usadas; CNPJs validados e comprovantes pendentes; evidências que vencem em breve; documentos disponíveis; problemas encontrados.

## 18. Saídas

Não seguem o modelo de uma secretaria específica (D-07); contêm a informação completa.

| Saída | Formato | Conteúdo |
|---|---|---|
| Grade comparativa | Excel (com fórmulas) e PDF | Por orçamento: itens, quantidades, os 3 orçamentos com preço unitário, total e fornecedor com CNPJ, média unitária e média do total |
| Orçamentos 1, 2, 3 e final | PDF | Cada um com todos os itens de uma fonte; o final com preços, quantidades e totais. Os orçamentos 1, 2 e 3 dizem que foram montados pelo Orça.AI a partir das páginas das lojas (não são documentos emitidos pelas lojas) e mostram a página e a data de cada preço |
| Plano de aplicação | Excel | Linhas com valor unitário, quantidade, meses, total; totais por rubrica e do projeto |
| Recursos públicos | Excel | Valor total, concedente e contrapartida |
| Cronograma físico-financeiro | Excel | Valor de cada linha em cada mês, totais mensais e acumulados |
| Cronograma de desembolso | Excel | Parcelas por mês (P-06) |
| Memória de cálculo | PDF | Fórmulas, valores intermediários, arredondamentos e a solução da otimização |
| Relatório de conformidade | PDF | Conferência de cada regra: 3 fontes, preço ≤ média, validade, CNPJ ativo, duplicidades, teto exato |
| Relatório de pesquisa | PDF | Todas as lojas e vagas pesquisadas, inclusive as descartadas e o motivo |
| Auditoria | PDF + JSON | Histórico de eventos e decisões |
| Pacote completo | ZIP | Estrutura abaixo |

```
<PROJETO>_<AAAA-MM-DD>/
├── 00_RESUMO/            resumo.pdf, conformidade.pdf, pesquisa.pdf
├── 01_ORCAMENTOS/        <orçamento>/ Orcamento_1.pdf, Orcamento_2.pdf, Orcamento_3.pdf,
│                         Orcamento_Final.pdf, grade_comparativa.xlsx, grade_comparativa.pdf
├── 02_COTACOES/          <orçamento>/<nn>_<item>/ cotacao.pdf, fonte_1.(pdf|png|mhtml), ...
├── 03_VAGAS/             <cargo>/ cotacao.pdf, vaga_1.(pdf|png|mhtml), ...
├── 04_CNPJ/              <cnpj>_<razão social>.pdf
├── 05_PLANO/             plano_aplicacao.xlsx (recursos, aplicação, cronogramas)
├── 06_MEMORIA_CALCULO/   memoria_calculo.pdf, otimizacao.json
└── 07_AUDITORIA/         historico.pdf, historico.json, manifesto.json (SHA-256 de todos os arquivos)
```

Detalhes da etapa 8:
- `cotacao.pdf` junta a capa da cotação (fontes, preços, média, preço final, endereço, data e impressão digital de cada página), as páginas capturadas e os comprovantes da Receita das empresas.
- As planilhas têm **fórmulas vivas** (totais, médias arredondadas, preço final, conferência preço × média, subtotais, cronogramas). Um teste recalcula as fórmulas e confere que dão exatamente os valores do sistema.
- Nomes de pastas e arquivos sem acentos nem símbolos, para abrir em qualquer computador.
- O pacote é gravado em `exportacoes/<projeto>/<data_hora>.zip` e nunca sobrescreve um anterior. Ao montar, cada evidência é conferida pela impressão digital: um arquivo alterado impede o pacote.

## 19. Fora do escopo (por enquanto)

- Enviar documentos a sistemas do governo (SEI, Transferegov etc.).
- Fazer compras.
- Gestão da execução e prestação de contas.
- Contornar captchas ou raspar plataformas que proíbem (ex.: LinkedIn).
