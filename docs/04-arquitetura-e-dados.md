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

Node.js (já instalado) é usado só no desenvolvimento, para compilar a interface. O usuário final não precisa dele.

## 3. Organização do código

```
Orca.AI/                       ← repositório (sem "ç": limite do GitHub)
├── docs/                      ← esta especificação
├── backend/
│   ├── pyproject.toml
│   ├── testes/                unitários, propriedades, casos de teste completos
│   └── orca/
│       ├── dominio/           tipos, identificadores (CNPJ, EAN) e regras puras (sem I/O)
│       ├── regras/            perfis, herança, versões, validação
│       ├── calculo/           dinheiro em centavos, arredondamento, cotações, mão de obra
│       ├── selecao/           cobertura, classificação, conferência preço × média, resolução
│       ├── correspondencia/   normalização, atributos, EAN, cascata 🟢🟡🔴
│       ├── otimizacao/        modelo CP-SAT, diagnóstico, verificação independente
│       ├── coleta/            conectores de lojas, vagas e CNPJ; captura assistida
│       ├── evidencias/        captura, hash, armazenamento, manifesto, validade
│       ├── ia/                provedores plugáveis e tarefas de IA
│       ├── documentos/        Excel, PDF, ZIP
│       ├── banco/             tabelas, migrações, gatilhos, sessões com autor, regras gravadas
│       ├── auditoria/         histórico automático de eventos, rastro do valor
│       ├── tarefas/           fila, orquestração, grafo incremental
│       └── api/               endpoints
├── frontend/                  React
└── catalogos/                 lojas, jornadas, ocupações MEI (versionados no repositório)
```

Regra de dependência: `dominio`, `calculo`, `selecao`, `correspondencia` e `otimizacao` **não acessam rede nem disco**. Toda I/O fica em `coleta`, `evidencias`, `documentos` e `api`. Isso deixa o núcleo 100% testável.

**Grafo incremental:** cada etapa grava o hash das suas entradas. Se as entradas não mudaram, o resultado anterior é reaproveitado. Mudar um item refaz só o que depende dele.

**Fila de tarefas:** uma tabela no SQLite e um processo trabalhador. Tarefas longas (coleta, captura, exportação) mostram progresso e podem **pausar esperando o usuário** (captcha, aprovação).

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
| C4 | **Captura assistida:** o usuário navega na janela do sistema e clica "capturar para o item X" | Login, CEP, captcha, bloqueio, LinkedIn |

A evidência é sempre a página da loja, capturada pelo navegador do sistema (C1, C3, C4) ou aberta por ele depois de uma descoberta (C0, C2).

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
- O preço extraído precisa aparecer no HTML salvo. Senão: 🔴 "Não foi possível validar automaticamente".
- EAN com dígito verificador válido; CNPJ com DV válido (numérico e alfanumérico).
- Página de marketplace: o CNPJ do **vendedor** precisa ser identificado (D-16).
- A página está disponível, e o produto está em estoque para o CEP do projeto.

### 5.4 CNPJ

- Situação cadastral: provedores plugáveis (OpenCNPJ, BrasilAPI; outros configuráveis). Resultados guardados com data e fonte.
- Comprovante oficial: captura assistida na página da Receita, com uma **fila de comprovantes pendentes** para resolver de uma vez (D-14).

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

### Previstas para as próximas etapas
| Tabela | Etapa |
|---|---|
| `selecao_lojas`, `resolucao` | 4 — seleção de lojas e resolução do item acima da média |
| `execucao_otimizacao`, `linha_final` | 5 — otimização |
| `grupo_vaga` | 6 — coleta de vagas |
| `tarefa` | fila de tarefas (coleta, captura, exportação) |

### Catálogos (arquivos versionados no repositório)
| Arquivo | Conteúdo |
|---|---|
| `catalogos/lojas.yaml` | lojas, domínios, categorias, conector, qual preço usar |
| `catalogos/jornadas.yaml` | jornada semanal, divisor, fonte legal, revisão |
| `catalogos/atributos.yaml` | atributos críticos por categoria |
| `catalogos/ocupacoes_mei.csv` | lista oficial de ocupações permitidas ao MEI (a importar) |

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
