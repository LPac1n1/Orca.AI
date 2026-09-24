# 04 — Arquitetura e dados

## 1. Visão geral

Aplicação **local** (D-05): um único programa instalado no computador da OSC. A interface abre no navegador (`http://localhost:8765`) e os dados ficam numa pasta escolhida pelo usuário.

```
┌───────────── Navegador do usuário ─────────────┐
│  Interface web (React)                          │
└──────────────────────┬─────────────────────────┘
                       │ HTTP local
┌──────────────────────▼─────────────────────────┐
│  Backend (Python + FastAPI)                     │
│  ├─ núcleo: regras, cálculo, seleção,           │
│  │          correspondência, otimização          │
│  ├─ fila de tarefas (coleta, captura, export)   │
│  └─ auditoria (eventos só de acréscimo)         │
└───┬──────────────┬───────────────┬─────────────┘
    │              │               │
┌───▼──────┐ ┌─────▼──────┐ ┌──────▼─────────────┐
│ Playwright│ │ APIs grátis│ │ IA (opcional)      │
│ (Chromium)│ │ CNPJ, VTEX │ │ Gemini grátis,     │
│ coleta e  │ │ SerpApi*   │ │ modelo local ou    │
│ evidência │ │            │ │ outra chave        │
└───┬──────┘ └────────────┘ └────────────────────┘
┌───▼─────────────────────────────────────────────┐
│ Pasta de dados: SQLite + evidências + exportações│
└─────────────────────────────────────────────────┘
* opcional, plano grátis
```

## 2. Tecnologias

| Parte | Escolha | Motivo |
|---|---|---|
| Linguagem do núcleo | Python 3.12 (já instalado) | Melhores bibliotecas para navegador, otimização, planilhas e IA |
| API local | FastAPI + Uvicorn | Simples, tipada |
| Banco | SQLite (modo WAL) via SQLAlchemy 2 + Alembic | Um arquivo, sem instalação; o mesmo código roda em PostgreSQL numa futura versão hospedada |
| Validação de dados e regras | Pydantic + YAML | Perfis de regras legíveis e validados |
| Navegador | Playwright (Chromium) | Coleta, captura de PDF/PNG/HTML, janela visível para captura assistida |
| HTTP | httpx | APIs de CNPJ, VTEX, SerpApi |
| HTML e dados estruturados | lxml/selectolax + extruct | Ler JSON-LD (schema.org) e microdados |
| Similaridade de texto | rapidfuzz | Correspondência e vagas duplicadas |
| Otimização | Google OR-Tools (CP-SAT) | Inteiros exatos, igualdade ao centavo, diagnóstico de inviabilidade |
| Excel | openpyxl | Planilhas com fórmulas vivas |
| PDF | Jinja2 (HTML) → Playwright (PDF); pypdf para juntar | Um só motor de renderização |
| Chaves de API opcionais | keyring (Gerenciador de Credenciais do Windows) | Nada de chave em arquivo de texto |
| Interface | React + TypeScript + Vite; TanStack Table | A matriz de revisão precisa de uma tela rica |
| Testes | pytest + hypothesis | Testes de propriedade para arredondamento e cálculo |

Node.js (já instalado) é usado só no desenvolvimento, para compilar a interface. O usuário final não precisa dele: a interface compilada fica em `backend/orca/api/estatico/` (vai junto com o pacote Python) e é servida pelo comando `orca`. As telas usam endereços com `#` (`/#/projetos/…`), para funcionar sem configuração no servidor. A matriz de revisão é uma tabela própria; a TanStack Table fica para quando for necessária.

## 3. Organização do código

```
Orca.AI/                       ← repositório (sem "ç": limite do GitHub)
├── docs/                      ← esta especificação
├── backend/
│   ├── pyproject.toml
│   ├── ferramentas/           scripts de apoio (ex.: montar o conjunto de referência)
│   ├── testes/                unitários, propriedades, casos de teste completos
│   └── orca/
│       ├── dominio/           tipos, identificadores (CNPJ, EAN) e regras puras (sem I/O)
│       ├── regras/            perfis, herança, versões, validação
│       ├── calculo/           dinheiro em centavos, arredondamento, cotações, mão de obra
│       ├── selecao/           cobertura, classificação, conferência preço × média, resolução
│       ├── correspondencia/   normalização, medidas, vocabulário, EAN, cascata 🟢🟡🔴
│       ├── otimizacao/        modelo CP-SAT, diagnóstico, verificação independente
│       ├── coleta/            captura (Edge), leitura de preço/vaga/CNPJ, situação cadastral, comprovante, pendências
│       ├── busca/             Fase 2: lojas pesquisáveis, conectores (API VTEX, página de busca), escolha dos candidatos, alternativas da Saída 1
│       ├── evidencias/        armazém por impressão digital (SHA-256), validade, manifesto
│       ├── ia/                provedores plugáveis e tarefas de IA
│       ├── fluxo/             liga as etapas a partir do banco: estado, seleção, vagas, teto, painel, dossiê
│       ├── documentos/        Excel, PDF, ZIP
│       ├── banco/             tabelas, migrações, gatilhos, sessões com autor, regras gravadas
│       ├── auditoria/         histórico automático de eventos, rastro do valor
│       ├── tarefas/           fila, orquestração, grafo incremental
│       └── api/               endpoints
├── frontend/                  React
└── catalogos/                 lojas, jornadas, atributos e vocabulário, ocupações MEI (versionados)
```

Regra de dependência: `dominio`, `calculo`, `selecao`, `correspondencia` e `otimizacao` **não acessam rede nem disco**. Toda I/O fica em `coleta`, `evidencias`, `documentos` e `api`. Isso deixa o núcleo 100% testável.

**Grafo incremental:** cada etapa grava o hash das suas entradas. Se as entradas não mudaram, o resultado anterior é reaproveitado. Mudar um item refaz só o que depende dele.

**Fila de tarefas:** uma tabela no SQLite (`tarefa`) e dois trabalhadores em segundo plano, cada um com a sua pista e executando uma tarefa de cada vez (o Playwright síncrono precisa ficar sempre na mesma thread; o navegador fica aberto entre as tarefas). Pista principal, sem janela: coletar página de item ou de vaga, consultar CNPJs, fechar o teto, exportar. Pista assistida, com **janela visível** (D-67): captura assistida — a tarefa fica **esperando o usuário**, que navega na janela e clica em “Capturar agora”; “Cancelar” fecha a espera. (A tarefa de comprovante da Receita pela janela continua existindo, mas a Receita recusa a verificação feita nela: o comprovante vem em PDF, D-14.) Enquanto uma captura assistida espera, a pista principal continua. Uma tarefa que falha não para a fila; as que estavam rodando quando o programa fechou voltam para a fila, menos as assistidas, que são canceladas (a janela fechou). O andamento das tarefas não gera eventos de auditoria (é registro de operação), mas a tarefa guarda quem pediu, quando e o resultado.

**API local e segurança:** o comando `orca` abre `http://localhost:8765` no navegador. O servidor escuta só no próprio computador (127.0.0.1), recusa pedidos com outro nome de endereço (proteção contra *DNS rebinding*) e exige o cabeçalho `X-Orca: 1` em todo pedido que muda dados (proteção contra *CSRF*: outros sites abertos no navegador não conseguem enviá-lo). Os arquivos baixáveis ficam restritos à pasta `exportacoes/`; as evidências são conferidas pela impressão digital a cada leitura.

**Configuração:** `%APPDATA%\Orca.AI\config.json` guarda a pasta de dados, o nome de quem usa (vira `usuario:<nome>` no histórico) e a porta. `orca --pasta … --usuario … --porta …` muda esses valores.

## 4. Pasta de dados

```
<pasta de dados>/
├── orcamentos.sqlite
├── evidencias/ab/cd/<sha256>.<ext>    arquivos endereçados pelo conteúdo (nunca sobrescritos)
├── exportacoes/<projeto>/<data>.zip
├── perfis/                            perfis de regras exportados/importados
└── logs/
```

Pode ficar dentro do OneDrive ou do Google Drive para backup automático. O sistema também faz cópia do banco antes de cada migração.

## 5. Coleta

### 5.1 Camadas (tentadas nesta ordem)

| Camada | Método | Uso |
|---|---|---|
| C0 | Dados estruturados: API pública VTEX (inclusive busca por EAN), JSON-LD schema.org na página | Rápido, exato, grátis |
| C1 | Busca do próprio site da loja (via Playwright) | Lojas sem dados estruturados de busca |
| C2 | Descoberta: SerpApi (plano grátis, opcional) | Achar lojas e URLs; **não é evidência** |
| C3 | Agente de IA com navegador (opcional) | Sites difíceis; toda ação gravada |
| C4 | **Captura assistida:** o usuário navega na janela do sistema e clica "capturar para o item X"; ou envia o PDF da página salvo no próprio navegador (D-67) | Login, CEP, captcha, bloqueio, LinkedIn |

A evidência é sempre a página da loja, capturada pelo navegador do sistema (C1, C3, C4) ou aberta por ele depois de uma descoberta (C0, C2). Na janela visível da C4 quem navega é o usuário: o sistema não usa a janela para escapar de bloqueios nem se disfarça (D-67).

### 5.1.1 Busca automática (Fase 2, etapa 10; D-68)

Módulo `orca.busca` (conectores e escolha dos candidatos) e tarefa `buscar_lote` (`orca.tarefas.busca`), na pista principal da fila.

- **Configuração:** cada loja do catálogo pode ter `busca: {modo, url, produto}`. `api_vtex` = API pública de catálogo (texto e código de barras); `pagina` = página de busca do site, aberta pelo navegador sem janela, de onde se leem os links de produto (`produto` é o pedaço do endereço que os identifica) e o texto do cartão de cada um; `assistida` = a janela abre na busca e a pessoa escolhe. Levantamento: Atacadão (API), Kalunga, Gimba, Lepok e Tenda (página), Carrefour e Extra (janela), 24/09/2026.
- **Escolha:** cada candidato passa pela mesma correspondência dos produtos (sem código de barras, pelo título); 🔴 nunca é capturado; entre os 🟡, ganha o mais parecido — palavras em comum sobre todas as palavras do item e do título, para que variações ("reciclado", "eco") percam para o produto comum. Se o primeiro não for 🟢 nem bem parecido, faz uma segunda busca sem as medidas.
- **Prova:** a página do produto escolhido é capturada e registrada como ao colar o link (preço à vista, CNPJ consultado, correspondência pela página). "Não encontrado" é registrado com a página da busca.
- **Ritmo:** pelo menos 3 s entre pedidos à mesma loja (`Contexto.intervalo_busca_s`); identificação "Orca.AI/0.1" no pedido à API.
- **Lojas que precisam de CEP** (ex.: Atacadão sem CEP mostra preço zero): o produto é achado, mas fica "sem preço na página" — a captura com janela resolve.

### 5.1.1b Produto alternativo para a Saída 1 (Fase 2, etapa 14; D-23)

Tarefa `buscar_alternativas` (`orca.tarefas.alternativas`), na pista principal, pedida pela rota `/api/itens/{id}/alternativas` quando um item passa da média na Regra B.

- **Onde procurar:** nas 3 lojas do trio, pela busca configurada da loja de cada uma (pelo domínio da página usada no item). A loja escolhida precisa ter busca automática; as outras sem busca aparecem como "confira você mesmo".
- **O que procurar:** o item **sem a marca** (`orca.busca.alternativas.especificacao_sem_marca`: sai marca, modelo, código de barras e as palavras da marca na descrição; ficam os atributos, a mesma finalidade). Os candidatos da loja escolhida da mesma marca de antes são deixados de lado; os 🔴 também.
- **Mesmo produto nas outras lojas:** pelo título. As palavras que distinguem o produto (as que ele tem a mais que a descrição genérica, em geral a marca) têm que estar no título da outra loja; sem contradição de atributos (nunca 🔴) e com pelo menos metade das palavras em comum. Sem palavra que distinga, o produto não é juntado.
- **A conta:** a de sempre (`orca.selecao.trocar_produto`: preço na escolhida ≤ nova média e a escolhida continua a de menor total), com os preços da **prévia** da busca (preço no Pix/boleto quando o cartão mostra, D-60). Nada é gravado: o resultado fica na tarefa.
- **A escolha:** a pessoa escolhe uma alternativa, confere descrição e marca e justifica; a rota `/api/itens/{id}/usar-alternativa` troca o produto (`substituir_item`: item novo, o antigo no histórico, decisão `trocar_produto`) e põe as páginas dela nas 3 lojas na fila de coleta. As provas, o preço e a correspondência que valem são os dessas páginas; 🟢 por atributos espera a confirmação, como qualquer produto.
- **Saída 2:** a simulação da troca de loja já existia (etapa 9); na tela, o aviso do item acima da média ganhou o atalho "Pesquisar outras lojas" (a busca do lote, etapa 10), para quando a próxima loja da classificação ainda não tem todos os itens.

### 5.1.2 Vagas (Fase 2, etapa 11; D-69)

`catalogos/vagas.yaml` lista as plataformas com o endereço da busca (marcadores `{cargo_slug}`, `{cidade_slug}`, `{uf}`, `{cargo_q}`, `{cidade_q}`), o motivo de a busca ser com janela e se a página de uma vaga pode ser aberta pelo sistema (`abrir_vaga: sistema | janela`). `orca.busca.vagas` monta os endereços; a rota `/api/cargos/{id}/busca-de-vagas` cria uma captura assistida por plataforma. As capturas assistidas passam pela mesma leitura de vaga (JSON-LD `JobPosting`) de quando se cola o link.

### 5.2 Contrato de um conector

```python
class Conector(Protocol):
    id: str                      # ex.: "vtex", "jsonld", "catho"
    def buscar(self, consulta: Consulta) -> list[Candidato]: ...
    def coletar(self, url: str, contexto: Contexto) -> ObservacaoColetada: ...
    # contexto: CEP, regra de preço (D-60 a D-63), tempo limite
    # ObservacaoColetada: dados extraídos + evidência (PDF, PNG, HTML) + método
```

O **catálogo de lojas** (`catalogos/lojas.yaml`) diz qual conector usar em cada loja, as categorias que ela atende e observações (ex.: exige CEP). O catálogo é compartilhável.

### 5.3 Conferências obrigatórias na coleta

- A página é rolada até o fim antes da captura, para carregar conteúdo tardio. O HTML salvo inclui o conteúdo dos quadros incorporados (iframes), e o PDF mostra o que está neles.
- O preço extraído precisa aparecer no texto visível da página (inclusive dos quadros). Senão: 🔴 "Não foi possível validar automaticamente". Na captura assistida, o preço informado pelo usuário passa pela mesma conferência.
- **Forma de pagamento (D-60):** em volta do preço dos dados da página, o sistema lê a forma escrita junto de cada valor ("no Pix", "no boleto", "em 1x", "10x de") e usa o preço no Pix; sem Pix, o do boleto; nunca o parcelado. O preço cheio fica registrado e o aviso mostra os dois.
- Outros valores logo antes ou depois do preço (clube, "leve 5", "de/por") geram aviso para conferir D-60 a D-63. Valores distantes (produtos recomendados, rodapé) não.
- Se a leitura errar, a pessoa escolhe outro valor **escrito na mesma página salva** ("O preço está errado?"): nasce uma observação nova com a mesma prova e o motivo; a anterior fica no histórico. Um valor que não aparece na página é recusado.
- O CNPJ encontrado é consultado nas APIs gratuitas logo depois da leitura (sem a consulta a loja não entra no trio).
- O PDF da prova é gerado em escala de 70%, para a página caber na folha no formato de computador.
- EAN com dígito verificador válido; CNPJ com DV válido (numérico e alfanumérico).
- Página de marketplace: o CNPJ do **vendedor** precisa ser identificado (D-16). O CNPJ do rodapé é da plataforma e nunca é usado como o do vendedor; sem ele, o anúncio é descartado (T-12). Em loja comum, um único CNPJ na página é o da loja; com vários, o usuário indica qual.
- A página está disponível, e o produto está em estoque para o CEP do projeto.
- O CEP só aparece no PDF quando foi de fato aplicado na página. Lojas com preço por região (catálogo) avisam quando a captura foi feita sem CEP.
- Sinais de bloqueio (códigos 401, 403, 429, 503; captcha; página de verificação) geram aviso para usar a captura assistida. O sistema nunca contorna captcha.

### 5.4 CNPJ

- Situação cadastral: provedores plugáveis (OpenCNPJ, BrasilAPI; outros configuráveis). Resultados guardados com data e fonte.
- Comprovante oficial: captura assistida na página da Receita, com uma **fila de comprovantes pendentes** para resolver de uma vez (D-14). O sistema abre a página com o CNPJ já preenchido; o usuário resolve o captcha e clica em "Consultar"; o sistema reconhece o comprovante (e não a página de solicitação, que tem o mesmo título) e o captura sozinho. Um comprovante emitido há menos de 30 dias é reaproveitado; a fila tem os CNPJs sem comprovante reaproveitável.

### 5.5 Evidência capturada (etapa 6)

- Navegador: o **Microsoft Edge** que já vem no Windows (Playwright, canal `msedge`), sem baixar outro navegador. Sem janela na coleta automática (C1); com janela na captura assistida (C4).
- Antes de capturar, a página é rolada tela a tela até o fim, esperando o conteúdo tardio.
- **PDF** A4 com cabeçalho em todas as páginas: "Orça.AI — capturado em dd/mm/aaaa hh:mm:ss (horário de Brasília) · CEP", a URL e o SHA-256 da página salva (MHTML); rodapé com "página x de y".
- **Imagem** (PNG) da página inteira e **página salva** (MHTML, com os quadros).
- Arquivos gravados em `evidencias/ab/cd/<sha256>.<ext>`: o nome é a impressão digital do conteúdo, o arquivo fica somente leitura e é conferido a cada leitura.
- Captura assistida: a janela fica aberta até a página ficar pronta — um sinal da própria página (ex.: o comprovante apareceu) ou o botão "Capturar agora" da interface (etapa 9).

## 6. Inteligência artificial (opcional)

**Provedores plugáveis:** `nenhum` (padrão seguro) · `gemini` (plano grátis) · `local` (Ollama ou similar) · outros com chave do usuário.

| Tarefa | Entrada | Saída (JSON validado) | Limite |
|---|---|---|---|
| Extrair produto de página sem estrutura | HTML reduzido | título, marca, modelo, apresentação, preço exibido | O preço só vale se aparecer no HTML (§5.3) |
| Extrair atributos | título + descrição | atributos da categoria | Comparação feita pelo programa |
| Julgar correspondência 🟡 | item + observação | manter 🟡 ou rebaixar para 🔴, com motivo | Nunca promove para 🟢 |
| Sugerir produtos alternativos | item + motivo | lista de candidatos | Candidatos são pesquisados e conferidos como qualquer produto |
| Enquadrar cargo na tabela de jornadas | nome e descrição do cargo | linha da tabela | Fica 🟡 até aprovação |
| Sugerir parâmetros de quantidade | atividades do projeto | participantes, consumo, encontros | Fica 🟡 até aprovação |
| Propor perfil de regras a partir do edital | PDF do edital | parâmetros com citação da página | Usuário confirma cada regra |
| Redigir explicações | fatos estruturados | texto | Números inseridos pelo programa, nunca pela IA |

Só dados públicos são enviados (D-51). Toda chamada é registrada (tarefa, provedor, modelo, entrada resumida, saída).

## 7. Modelo de dados

Implementado em `backend/orca/banco/tabelas.py` (etapa 3). Convenções:
- **Identificadores** gerados pelo programa (UUID em texto), conhecidos antes de gravar.
- **Dinheiro** em centavos e **horas** em centésimos: sempre inteiros. Um teste recusa qualquer coluna decimal.
- **Data e hora** sempre com fuso, gravadas em UTC (texto ISO 8601).
- **Nada é apagado:** todas as tabelas têm gatilho que recusa `DELETE`; as vivas usam exclusão lógica (`excluido_em`) e arquivamento (`arquivado_em`).
- Tabelas **(imutável)** também recusam `UPDATE`: correção = registro novo.
- **Histórico automático:** toda criação ou alteração feita pelo programa gera um `evento` (antes, depois, autor, hora). Gravar exige declarar o autor (`usuario:<nome>`, `sistema[:<módulo>]` ou `ia:<provedor>`).
- **Restrições no próprio banco** (CHECK), além das validações do programa: teto > 0, meses coerentes, margens nos limites, alvo coerente (item *ou* cargo), faixa salarial, e a IA nunca grava uma correspondência 🟢.
- O projeto pertence a uma organização; tudo abaixo dele herda. Fontes, consultas de CNPJ e arquivos são compartilhados (revisar se houver versão hospedada com várias OSCs).

### Estrutura do projeto
| Tabela | Campos principais |
|---|---|
| `organizacao` | id, nome, cnpj |
| `perfil_regras` **(imutável)** | id, organizacao_id (vazio só na camada do sistema), nome, nivel, versao, impressao (SHA-256), conteudo_yaml — nome + versão com outro conteúdo é recusado |
| `projeto` | id, organizacao_id, nome, orgao, instrumento, processo, teto_centavos, duracao_meses, cep, data_entrega, camadas_regras (ids das versões usadas, na ordem), arquivado_em, excluido_em |
| `orcamento` | id, projeto_id, nome, descricao, tipo (materiais, mao_de_obra, servicos), camada_regras_id (camada própria, opcional), arquivado_em, excluido_em — a regra A/B e os limites vêm das regras |
| `lote` | id, orcamento_id, nome, excluido_em |
| `item` | id, lote_id, descricao, categoria, marca, modelo, apresentacao, atributos, ean, catmat, unidade, qtd_planejada, mes_inicio, mes_fim, margem_min/max_percentual, travado, substitui_item_id, excluido_em |
| `cargo` | id, orcamento_id, nome, cbo, postos, regime, jornada_id, horas_planejadas_centesimos, mes_inicio, mes_fim, margem_min/max_percentual, travado, excluido_em |

### Pesquisa e evidências
| Tabela | Campos principais |
|---|---|
| `fonte` | id, tipo (loja, empresa, fornecedor, publica), nome, dominio, catalogo_id, conector |
| `consulta_cnpj` **(imutável)** | id, cnpj, razao_social, nome_fantasia, situacao, data_situacao, municipio, uf, provedor, consultado_em, dados_brutos — cada consulta fica guardada como estava naquele dia |
| `comprovante` **(imutável)** | id, cnpj, arquivo_sha256, emitido_em |
| `arquivo` **(imutável)** | sha256, caminho, tipo_mime, tamanho |
| `evidencia` **(imutável)** | id, url, capturado_em, metodo, cep, pdf_sha256 (obrigatório), png_sha256, html_sha256 |
| `observacao` **(imutável)** | id, alvo_tipo, item_id ou cargo_id, fonte_id, cnpj_vendedor, url, titulo, marca, modelo, apresentacao, ean, preco_centavos, salario_min/max_centavos, encontrado, disponivel, coletado_em, cep, metodo, evidencia_id, preco_no_html, dados_brutos, autor |
| `correspondencia` **(imutável)** | id, item_id, observacao_id, status (verde, amarelo, vermelho), motivos, origem (ean, atributos, ia, humano), autor |

### Cálculo, decisões e histórico
| Tabela | Campos principais |
|---|---|
| `cotacao` **(imutável)** | id, alvo_tipo, item_id ou cargo_id, n, soma_centavos, media_exibida_centavos, impressao_regras, autor |
| `cotacao_observacao` **(imutável)** | cotacao_id, ordem, observacao_id |
| `decisao` **(imutável)** | id, tipo, alvo_tipo, alvo_id, valor, justificativa, autor |
| `alerta` | id, projeto_id, tipo, severidade (info, atencao, problema), alvo, mensagem, resolvido_em |
| `evento` **(imutável)** | id (sequencial), projeto_id, entidade, entidade_id, acao (criar, alterar, excluir, arquivar), antes, depois, autor, criado_em |
| `execucao_otimizacao` **(imutável)** | id, projeto_id, impressao_regras, status (otima, viavel, sem_solucao), teto_centavos, total_centavos, verificacao_ok, versao_otimizador, entradas, resultado, autor |
| `linha_final` **(imutável)** | id, execucao_id, linha_id, alvo_tipo, preco_unitario_centavos e quantidade (material) ou valor_hora, horas, valor_mensal e postos (cargo), meses, total_centavos |

### Previstas para as próximas etapas
| Tabela | Etapa |
|---|---|
| `selecao_lojas`, `resolucao` | 4 — seleção de lojas e resolução do item acima da média |

### Catálogos e pares da OSC (D-64 a D-66)
| Tabela | Campos principais |
|---|---|
| `catalogo_camada` **(imutável)** | id, organizacao_id, tipo (atributos, lojas), versao, conteudo (só o que a OSC mudou em relação ao catálogo do sistema; `null` retira), impressao (SHA-256), resumo, autor — a versão mais recente vale |
| `par_referencia` | id, organizacao_id, categoria, titulo_a, marca_a, ean_a, titulo_b, marca_b, ean_b, rotulo (mesmo, diferente), motivo, origem (decisao, ean, usuario), chave (evita repetir um par automático; um par retirado não volta), excluido_em |

### Operação
| Tabela | Campos principais |
|---|---|
| `tarefa` | id, projeto_id, tipo, estado (pendente, rodando, esperando_usuario, concluida, falhou, cancelada), progresso, mensagem, parametros, resultado, autor, iniciada_em, concluida_em — não gera eventos de auditoria |

A duplicidade de vagas (D-49) não tem tabela própria: é calculada a cada seleção (`orca.selecao.agrupar_duplicadas`), e a decisão do usuário nos casos incertos é gravada em `decisao`.

### Catálogos (arquivos versionados no repositório)
| Arquivo | Conteúdo |
|---|---|
| `catalogos/lojas.yaml` | lojas, domínios, categorias, conector, qual preço usar |
| `catalogos/jornadas.yaml` | jornada semanal, divisor, fonte legal, revisão |
| `catalogos/atributos.yaml` | atributos críticos por categoria e vocabulário de valores que se excluem |
| `backend/orca/correspondencia/referencia/pares_referencia.csv` | conjunto de referência da correspondência (T-11), distribuído com o programa |
| `catalogos/ocupacoes_mei.csv` | lista oficial de ocupações permitidas ao MEI (a importar) |

As edições da OSC nos catálogos de atributos e de lojas não mudam esses arquivos: ficam em `catalogo_camada`, por cima deles.

### Migrações
Alembic, em `backend/orca/banco/migracoes/`. Ao abrir o banco, o programa aplica as migrações pendentes e **faz cópia de segurança antes** (API de backup do SQLite). Operações "batch" recriam tabelas e perdem os gatilhos: depois delas, recriá-los com `orca.banco.gatilhos.criar_gatilhos`. Um teste confere que todas as tabelas continuam protegidas e que as migrações correspondem às tabelas do código.

## 8. Segurança e privacidade

- Todos os dados ficam no computador da OSC. Nada é enviado a servidores do projeto.
- Nenhuma senha é pedida nem guardada. Chaves opcionais (Gemini, SerpApi) ficam no Gerenciador de Credenciais do Windows.
- Dados pessoais mínimos: vagas são de empresas; o histórico guarda só o nome de quem usou o sistema.
- O sistema não contorna captcha nem raspa plataformas que proíbem.

## 9. Distribuição

- Código no GitHub, licença AGPL-3.0 (D-03).
- Primeiras versões: instalação por script. Depois: instalador para Windows.
- Perfis de regras e catálogo de lojas podem ser compartilhados como arquivos, e futuramente por um repositório comunitário.
- Catálogo de atributos e vocabulário em camadas, como as regras: sistema (arquivo versionado no repositório) → OSC (edições e sugestões aprovadas, gravadas no banco com versão). Os pares rotulados das decisões ficam no banco e se somam ao conjunto de referência do repositório no teste de correspondência (D-64 a D-66).
