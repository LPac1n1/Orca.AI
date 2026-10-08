# Orça.AI — reformulação da interface (02/10/2026)

Diagnóstico, nova arquitetura, design system, o que mudou em cada tela e a conferência final. O mostruário visual dos componentes está no próprio sistema, em **Ajuda → Guia de interface** (`/guia-de-interface`).

**Contexto usado** (os campos do pedido vieram em branco; foram preenchidos com o que o sistema é):

| Campo | Valor |
|---|---|
| Nome | Orça.AI (antes "Orçamentos OSC") |
| O que faz | Monta e confere a Grade Comparativa e o Plano de Aplicação de projetos para a SEJC-SP: pesquisa vagas e preços, valida CNPJs, guarda comprovantes em PDF, fecha o plano no teto e exporta o Excel |
| Quem usa | Equipe administrativa da OSC, sem formação técnica, no computador do escritório (Windows) |
| Tarefas principais | Criar o projeto, cadastrar cargos e itens, rodar a pesquisa automática, conferir pendências, fechar no teto, exportar |
| Tecnologia | FastAPI + Jinja2 (páginas montadas no servidor), CSS e JavaScript próprios, sem bibliotecas |
| Restrições | Mesmo backend, mesmas rotas e nomes de campo; custo zero; funcionar sem internet (nada de fontes ou scripts externos); usável a partir de 360 px |

---

## 1. Diagnóstico da interface anterior

| # | Problema | Gravidade |
|---|---|---|
| 1 | **Valor digitado errado sem aviso:** os campos de dinheiro mostravam `150000.00` e aceitavam qualquer texto. Quem digitasse `150.000` gravava R$ 150,00 | Alta |
| 2 | **A página do projeto não dizia o que fazer.** Indicadores, 5 botões com o mesmo peso, configuração, duas tabelas e a verificação, tudo empilhado | Alta |
| 3 | **Campos sem rótulo.** "Novo projeto" e as grades de edição usavam só o texto de exemplo dentro do campo, que some ao digitar | Alta |
| 4 | **Tela da rubrica:** tabela de 10 colunas cheia de campos, com uma segunda tabela escondida ("Fornecedor, link e PDF"). Rolagem lateral; difícil ver qual loja e qual comprovante pertencem a cada preço | Alta |
| 5 | **Erro sem explicação:** um campo numérico vazio derrubava a gravação com "Internal Server Error". Nenhuma conferência antes de enviar | Alta |
| 6 | **Confirmações pelo "OK / Cancelar" do navegador**, com texto longo; ações que apagam ficavam ao lado das comuns | Alta |
| 7 | **Situação só por cor ou símbolo** (🟢 🟡, texto vermelho), ilegível para quem não distingue cores e para leitor de tela | Alta |
| 8 | Navegação só por links "← voltar": sem menu, sem indicação de onde se está; Tarefas e Base da Receita em links pequenos | Média |
| 9 | Jargão sem explicação: "fontes", "evidência", "EAN", "trio", códigos R02/R11 | Média |
| 10 | Sem estado vazio: projeto novo mostrava tabelas em branco | Média |
| 11 | Sem retorno ao enviar (dava para clicar duas vezes) e sem aviso de alterações não salvas: anexar um PDF descartava o que tinha sido digitado na tela | Média |
| 12 | Tela da tarefa com texto cru ("estado: rodando · 754 s") e montada com `innerHTML` a partir de textos vindos de sites | Média |
| 13 | Alvos de clique pequenos (botões "1 2 3" com 25 px, links "editar") | Média |
| 14 | Tabelas sem adaptação para telas estreitas | Média |
| 15 | Datas em formato técnico (`2026-10-02T15:28`), durações em segundos | Baixa |
| 16 | Na grade do projeto, o cabeçalho da coluna trazia o nome de uma loja que não era a do item | Baixa |
| 17 | Todas as páginas com o mesmo título na aba do navegador | Baixa |

**O que já funcionava bem e foi mantido:** histórico de versões sem perda, barra de progresso das tarefas, mensagens de aviso das pesquisas em linguagem direta, exportação em um clique.

---

## 2. Nova arquitetura da informação

```
Menu principal (em todas as telas):  Projetos · Tarefas (com contador) · Base da Receita · Ajuda

Projetos
└─ Projeto
   ├─ Visão geral        ← "O que fazer agora": os 6 passos, com a situação de cada um e o botão do passo
   ├─ Mão de obra        ← lista dos cargos → Cargo (3 pesquisas de salário)
   ├─ Materiais e serviços ← rubricas e itens → Rubrica (itens e 3 pesquisas de preço) → Proposta da pesquisa
   ├─ Verificação        ← pendências e pontos para revisar, cada um com o botão "Corrigir"
   ├─ Configuração       ← dados do projeto, regras, lojas, remover projeto
   ├─ CNPJs e comprovantes
   └─ Histórico
Tarefas → Acompanhar tarefa
Ajuda → Guia de interface
```

**Fluxo principal em 6 passos**, visível na visão geral do projeto: montar o plano → pesquisar → conferir CNPJs → resolver pendências → fechar no teto → exportar. O passo seguinte fica em destaque e é o único com botão principal.

Reduções de passos:

- "Pesquisar tudo", "Fechar no teto" e "Exportar" ficam no passo correspondente, com a situação ao lado, em vez de uma fileira de botões.
- Cada pendência tem o botão **Corrigir**, que abre a tela do item (antes era preciso achar o item na página).
- "Desfazer a última alteração" na visão geral (antes: abrir o histórico e achar a versão).
- Na rubrica, empresa, CNPJ, data, produto, link e PDF de cada pesquisa ficam no mesmo quadro do preço.
- O caminho (Projetos › Projeto › Item) aparece no topo de toda tela interna.

---

## 3. Design system

Arquivo único: `templates/_estilo.css` (tokens + componentes). Macros dos componentes: `templates/_ui.html`. Comportamento: `templates/_app.js`.

### 3.1 Tokens

**Cores** (contraste medido; mínimo AA = 4,5:1 para texto e 3:1 para bordas de componentes):

| Variável | Valor | Uso | Contraste |
|---|---|---|---|
| `--cor-primaria` | `#1a56a0` | botão principal, links, foco | branco sobre ela 7,3:1; ela sobre branco 7,3:1 |
| `--cor-primaria-forte` | `#143f77` | botão sob o cursor | branco 10,5:1 |
| `--cor-primaria-suave` | `#e8f0fa` | fundo de destaque | primária sobre ela 6,3:1 |
| `--cor-texto` | `#1b2430` | texto | 15,7:1 sobre branco |
| `--cor-texto-suave` | `#55606e` | texto de apoio | 6,4:1 sobre branco; 5,9:1 sobre o fundo |
| `--cor-fundo` / `--cor-superficie` / `--cor-superficie-2` | `#f4f6f9` / `#fff` / `#eef2f6` | página / cartões / cabeçalho de tabela | — |
| `--cor-borda` / `--cor-borda-campo` | `#d5dbe3` / `#7d8898` | linhas / borda de campo | campo 3,6:1 sobre branco |
| `--cor-ok` + `-fundo` | `#17603a` / `#e3f4ea` | sucesso | 6,6:1 |
| `--cor-alerta` + `-fundo` | `#7a4d00` / `#fff3d1` | atenção | 6,6:1 |
| `--cor-erro` + `-fundo` / `--cor-erro-solida` | `#a3231c` / `#fde9e7` / `#b3261e` | erro | 6,4:1; branco sobre a sólida 6,5:1 |
| `--cor-info` + `-fundo` | `#1a56a0` / `#e8f0fa` | informação | 6,3:1 |

**Modo escuro.** O botão "Modo escuro / Modo claro" fica no menu. Sem escolha feita, o sistema acompanha a preferência do computador; a escolha fica guardada no navegador. O tema é aplicado antes de a página ser desenhada (não pisca). Todas as cores dos componentes vêm de tokens; o tema escuro só troca os valores (`:root[data-tema="escuro"]`), sem regra própria por componente. Um teste automático impede cor fixa em componente e exige que toda cor do tema claro tenha valor no escuro.

| Variável (tema escuro) | Valor | Contraste |
|---|---|---|
| `--cor-fundo` / `--cor-superficie` / `--cor-superficie-2` | `#11161c` / `#1a2029` / `#242c37` | — |
| `--cor-texto` | `#e7ebf0` | 13,7:1 sobre a superfície |
| `--cor-texto-suave` | `#a9b3c0` | 7,7:1 |
| `--cor-primaria` (links e botão principal) | `#8ab8f5` | 8,0:1 sobre a superfície; texto do botão (`--cor-sobre-primaria` `#0e1a2b`) 8,5:1 |
| `--cor-borda-campo` | `#8b97a8` | 5,5:1 |
| `--cor-ok` / `--cor-alerta` / `--cor-erro` (sobre os seus fundos) | `#7ed9a5` / `#f1c76e` / `#f7a59f` | 8,4:1 / 8,4:1 / 8,1:1 |
| `--cor-erro-solida` (botão de confirmação perigosa) | `#c7372f` | branco sobre ela 5,2:1 |
| `--cor-inverso-fundo` (aviso rápido, balão de ajuda) | `#39444f` | texto 9,2:1 |

**Tipografia:** fonte do sistema (`system-ui`, Segoe UI no Windows). Escala: 12 (legenda), 13 (apoio), 15 (corpo), 17 (subtítulo), 20 (seção), 26 (página). Pesos 400 / 600 / 700. Altura de linha 1,5 no texto e 1,25 nos títulos. Números em tabelas com largura fixa. No celular, campos e botões usam 16 px (o navegador não dá zoom ao focar).

**Espaçamento:** escala de 4 px (`--esp-1` = 4 … `--esp-12` = 48). **Raios:** 6 / 10 / 14 px e pílula. **Sombras:** `--sombra-1` (cartão) e `--sombra-2` (janela, aviso rápido). **Foco:** contorno de 2 px + halo (`--foco`). **Alvo mínimo:** `--alvo` = 44 px.

### 3.2 Componentes

| Componente | Classe / macro | Regras |
|---|---|---|
| Botão | `.btn` + `--primario`, `--secundario`, `--perigo`, `--perigo-cheio`, `--texto` | Um principal por área. Rótulo com verbo ("Salvar alterações"). 44 px. Ao enviar: desabilita e mostra "Aguarde…" (`.is-carregando`) |
| Campo | macro `campo(...)`, `.campo` | Rótulo sempre visível; `*` em obrigatório, "(opcional)" quando ajuda; dica e exemplo embaixo; erro em texto embaixo (`.campo__erro`, ligado por `aria-describedby`); prefixo `R$` e sufixos (`%`, `meses`) |
| Seleção | `.escolha` | Caixa ou opção com título e uma linha de explicação; a linha inteira é clicável |
| Ajuda | macro `ajuda(...)`, `.dica` | Botão `?` que abre uma explicação curta; fecha com Esc ou clique fora; nunca sai da tela |
| Selo | macro `selo(tipo, texto)` | Sempre ícone + texto: `ok`, `alerta`, `erro`, `info`, `neutro` |
| Contador | `.contador` | Quantidades no menu, nas abas e nos títulos |
| Aviso | `.aviso--ok/info/alerta/erro` | Ícone + texto; `role="status"` ou `alert`; pode ter botão de fechar |
| Aviso rápido | `OSC.toast(msg, tipo)` | Some sozinho; usado para retorno de ações na própria tela |
| Janela de confirmação | `<dialog class="modal">` + `data-confirmar` no formulário | Título com a pergunta, texto com a consequência, botão com o nome da ação. Em ação perigosa o foco começa em "Cancelar" |
| Cartão | `.cartao`, `.cartao--perigo` | Agrupa um assunto; o de perigo isola ações que removem |
| Indicador | `.indicador` | Número grande + rótulo + nota |
| Passos | `.passos` / `.passo--feito` / `--atual` | Guia do projeto e instruções numeradas |
| Tabela | `.tabela`, `.tabela--cartoes` | Cabeçalhos com `scope`; no celular cada linha vira um cartão e cada célula mostra o nome da coluna |
| Navegação | `.menu`, `.subnav`, macro `migalhas(...)` | Item atual marcado com `aria-current` |
| Abre-e-fecha | `.detalhe` | Conteúdo secundário (opções avançadas, justificativas) |
| Lista de itens recolhíveis | `.itens` + `<details class="item-recolhivel" data-recolhivel>` com `<summary class="item-resumo">`; macros `itens_barra`, `itens_cabecalho`, `item_resumo` (`_rubrica.html`) | Cada item é uma linha com o que se confere de relance; o conteúdo completo abre ao clicar. As colunas da linha e do cabeçalho vêm da mesma variável (`--colunas`), então a lista é lida como tabela; abaixo de 1080 px a linha vira título + dados. Na linha não entra campo nem botão (só links). O `_app.js` abre o item da âncora (`#sub3`, `#pesquisa1`, `#t-banco`), abre o item que tem campo com erro, lembra os itens abertos na sessão do navegador e atende `data-recolher="abrir|fechar"` |
| Progresso / carregando | `.progresso`, `.esqueleto` | Barra com `role="progressbar"`; faixa cinza enquanto os dados chegam |
| Estado vazio | `.vazio` | Diz o que vai aparecer ali e qual é o primeiro passo |
| Barra de salvar | `.barra-salvar` | Fixa no pé do formulário; avisa quando há alterações não salvas |

### 3.3 Campos inteligentes (`_app.js`)

| Tipo | Comportamento |
|---|---|
| Dinheiro (`data-mascara="moeda"`) | Pontos de milhar enquanto digita; vírgula para centavos; completa `,00` ao sair; aceita colar `R$ 1.234,56` e `1234.56` |
| CNPJ | `00.000.000/0000-00` enquanto digita; confere os dígitos ao sair; **preenche o nome da empresa e mostra a situação** pela base da Receita guardada no computador |
| CEP | `00000-000` |
| Número inteiro | Só dígitos, com mínimo e máximo (horas, meses, quantidade) |
| Porcentagem | Uma casa decimal, com `%` |
| Data | Calendário do navegador (dd/mm/aaaa); a data da pesquisa não pode ser futura |
| Link | Confere se começa com `http`; botão para abrir em outra aba |
| Arquivo | Só PDF; avisa antes de enviar |
| Texto | Tira espaços sobrando ao sair do campo |

Validação: ao sair do campo e de novo ao enviar. A mensagem diz o que está errado e como corrigir ("CNPJ incompleto: são 14 números (faltam 2)"). Ao enviar com erro, o foco vai para o primeiro campo errado. Teclado numérico no celular (`inputmode`).

---

## 4. Arquivos

| Arquivo | Conteúdo |
|---|---|
| `templates/_estilo.css` | Design system |
| `templates/_app.js` | Máscaras, validação, confirmação, alterações não salvas, navegação por partes, ajuda, avisos |
| `templates/_ui.html` | Macros: `icone`, `selo`, `ajuda`, `campo`, `migalhas`, `aviso`, `estado_tarefa`, `tarefas_em_andamento` |
| `templates/base.html` | Menu, caminho, aviso de projeto removido, janela de confirmação, área de avisos, rodapé |
| `templates/*.html` | As 12 telas reescritas + `ajuda.html`, `guia.html`, `erro.html` |
| `app.py` | Filtros `moeda`, `data_br`, `duracao`; ícones; `guia_do_projeto`; `/ajuda`, `/guia-de-interface`, `/api/cnpj/{n}`; página de erro |
| `tests/test_interface.py` | 10 testes da interface |

**Mudanças no backend, e por quê** (a lógica do orçamento não mudou):

| Mudança | Motivo |
|---|---|
| `cent('150.000')` = R$ 150.000,00 | Era lido como R$ 150,00 (problema 1) |
| Campo numérico vazio mantém o valor anterior | Antes derrubava a gravação (problema 5) |
| Página de erro própria | Explica o que fazer em vez de "Internal Server Error" |
| Link digitado num item que usa os fornecedores da rubrica passa a ser gravado | Antes era ignorado em silêncio |
| `/api/cnpj/{n}` (só leitura, base local) | Preenchimento do nome da empresa pelo CNPJ |
| `guia_do_projeto` | Situação dos 6 passos na visão geral |

CSS e JavaScript vão embutidos em cada página (inclusão no `base.html`). Motivo: nenhum arquivo externo para o navegador guardar desatualizado depois de uma atualização, e nenhuma dependência de internet.

---

## 5. O que mudou em cada tela

| Tela | Mudanças | Por quê |
|---|---|---|
| **Projetos** | Lista com botão "Abrir projeto"; formulário "Novo projeto" com rótulos, máscara de valor e de CEP; guia de primeiro acesso dispensável; estado vazio; situação do sistema em indicadores; projetos removidos com "Restaurar" e "Apagar de vez" (nome digitado + janela de confirmação) | Problemas 1, 3, 10 |
| **Projeto** | Resumo em 5 indicadores com nota; 5 partes (visão geral, mão de obra, materiais, verificação, configuração) + CNPJs e histórico; guia de 6 passos; botão "Corrigir" em cada pendência; "Desfazer a última alteração"; configuração agrupada por assunto, cada opção com explicação; "Remover projeto" isolado | Problemas 2, 6, 8, 9, 16 |
| **Cargo** | 3 seções numeradas; as 3 pesquisas em quadros lado a lado, com situação (completa, incompleta, em branco); CNPJ com máscara e preenchimento do nome; banco de vagas com botões nomeados; barra de salvar fixa | Problemas 3, 4, 13 |
| **Rubrica** | Cada item é um cartão: descrição, quantidade, média, valor no plano e as 3 pesquisas em quadros (preço, loja, produto, comprovante, "o que falta"); "Detalhes e comprovante" junta empresa, CNPJ, data, produto, link e PDF; opções técnicas em "Opções avançadas"; "Adicionar um item" separado | Problema 4 |
| **Proposta** | Texto do que acontece ao aplicar; situação de cada item em selo com texto; links avisam que abrem em outra aba | Problemas 7, 9 |
| **Tarefa** | Situação em selo, tempo em minutos, avisos em lista própria, tabela montada sem `innerHTML`, aviso quando o sistema para de responder, cancelamento com janela de confirmação | Problemas 12, 15 |
| **Tarefas** | Nome do projeto, situação em selo, datas e durações legíveis, estado vazio | Problemas 10, 15 |
| **CNPJs** | "Como emitir e importar" em 4 passos; contador de comprovantes; estado vazio | Problema 9 |
| **Histórico** | "Restaurar" com janela que explica a consequência; nomes dos eventos em português | Problemas 6, 9 |
| **Fechar no teto** | Explica a simulação; quando não há solução, lista o que fazer | Problema 9 |
| **Base da Receita** | Situação em lista; atualização com janela que avisa o tamanho do download | Problema 6 |
| **Ajuda** (nova) | Caminho completo, glossário, dúvidas comuns, tabela das regras | Problema 9 |
| **Guia de interface** (nova) | Mostruário do design system | Manter as telas consistentes |
| **Erro** (nova) | O que aconteceu, o que fazer, mensagem técnica recolhida | Problema 5 |

---

## 6. Conferência final

Feita numa cópia dos dados reais (projeto com 11 cargos, 4 rubricas e 30 itens), nas larguras de 1280 px e 360 px.

| Item | Como foi conferido | Resultado |
|---|---|---|
| Funcionalidades preservadas | 163 testes automáticos; gravar cargo, rubrica de mercado, rubrica de sistema e configuração pelas telas novas, sem alterar nada, e comparar as versões campo a campo | Sem diferença nos dados |
| Todas as telas abrem | 14 endereços, incluindo tarefa e projeto inexistentes | 200, ou 404 com página explicativa |
| Máscaras | Digitação real no navegador: `150000` → `150.000` → `150.000,00`; CNPJ formatado; CNPJ com dígito errado | Funcionando |
| Validação | Envio com campo obrigatório vazio, CNPJ inválido e número acima do máximo | Mensagem embaixo do campo, foco no primeiro erro, aviso com a contagem |
| Preenchimento pelo CNPJ | CNPJ real na base local | Nome e situação preenchidos |
| Confirmações | Remover projeto, exemplo do guia | Janela com foco em "Cancelar"; Esc fecha |
| Alterações não salvas | Editar e desfazer a edição na configuração | Barra muda de estado e volta |
| Navegação do projeto | Endereços `#item14`, `#alertas`, cliques nas partes e no botão "Ver a verificação" | Parte certa aberta e marcada |
| Rótulos | Varredura de todos os campos visíveis em todas as telas (teste automático e no navegador) | Nenhum campo sem rótulo |
| Alvos de 44 px | Medição de botões, campos, links de navegação e abre-e-fecha em 12 telas | Nenhum abaixo de 44 px |
| Estrutura | Um `h1` por tela, sem salto de nível, sem `id` repetido, botões e links com nome | Sem ocorrências |
| Contraste | Cálculo dos 22 pares de cor do tema claro e dos 27 do escuro; no navegador, medição de cada texto contra o fundo em 6 telas no modo escuro (2.497 textos) e no guia nos dois modos | Todos acima do mínimo AA |
| Responsividade | Largura de 360 px em 9 telas | Sem rolagem lateral da página; tabelas viram cartões; explicações (?) dentro da tela |
| Erros de script | Console do navegador em todas as telas | Nenhum |
| Textos | Revisão tela a tela: verbos nos botões, sem jargão sem explicação, datas e valores no formato brasileiro | Feito |

**Não conferido:** leitor de tela real (NVDA) e navegadores além do Chromium. A estrutura segue as práticas (rótulos, papéis, `aria-live`, ordem de tabulação natural), mas o teste com leitor de tela vale ser feito por uma pessoa.

---

## 7. Decisões registradas

| Assunto | Decisão |
|---|---|
| Endereço pelo CEP | Não se aplica: o sistema guarda só o CEP. O preenchimento automático foi feito onde há dado local: nome da empresa pelo CNPJ |
| Máscara de dinheiro | Milhar automático e vírgula para centavos, em vez de "empurrar os centavos" como em aplicativo de banco: no computador, quem digita `150000` espera R$ 150.000 |
| Datas | Campo de data do navegador (já mostra dd/mm/aaaa e traz calendário), em vez de máscara própria |
| Primeiro acesso | Quadro "Primeira vez aqui?" na página inicial, dispensável e reabrível, em vez de um tour que cobre a tela |
| Partes do projeto | Uma página com partes que se alternam (os endereços `#item12` e `#alertas` que o sistema já usava continuam funcionando) |
| CNPJ alfanumérico | O sistema só trata CNPJ numérico; a máscara segue essa regra. Se a OSC passar a cotar com empresas de CNPJ alfanumérico, o backend precisa ser ajustado antes |
| Tema escuro | Incluído a pedido (02/10): botão no menu, acompanha o computador quando não há escolha |
| Sistema para qualquer OSC | Nada de dados de uma OSC nas telas (02/10): saiu o "exemplo real", o CEP não vem preenchido e passou a ser obrigatório (sem CEP padrão no cálculo), e os textos deixaram de citar decisões e pareceres de uma OSC específica. As telas e o Excel não citam os pareceres técnicos (dirigidos a uma OSC): cada regra aparece como "regra da SEJC" ou "regra do sistema". O caso real usado como regressão continua só nos testes automáticos |
| Registro de tarefas | Ao apagar um projeto de vez, saem as tarefas dele e os registros terminados da coleta diária de vagas. A tela Tarefas identifica as rotinas do sistema e tem "Limpar tarefas terminadas" |
| Situações guardadas com símbolo (🟢 🟡) | Continuam assim no banco de dados; na tela viram selos com texto |

## 8. Ajustes depois do primeiro uso (02/10/2026, noite)

Lista de 17 pedidos; o detalhe de cada um está no [LEIAME](LEIAME.md#novo-na-05-lista-de-17-pedidos-de-02102026). O que mudou na interface:

| Tela | Mudança |
|---|---|
| Todas | Aba do navegador: "Orça.AI · tela"; marca Orça.AI no topo e no rodapé. Nenhum campo traz texto escrito dentro (o macro `campo` só usa o exemplo na dica) |
| Projeto | Quadros "Adicionar cargo" (nome, quantidade, horas, duração) e "Adicionar rubrica" (nome, como cotar, duração), abertos pelo guia com o cursor no 1º campo. Quantidade de profissionais na tabela; aviso "Juntar cargos repetidos". Verificação com "Conferir", "Marcar como revisado" e o grupo "Revisados". Mensagens que ficariam fora da tela viram aviso flutuante |
| Cargo | Quantidade de profissionais; títulos similares (caixas de marcar + outros títulos); "Salvar e buscar vagas" salva antes de buscar; banco de vagas com o PDF guardado no nome da empresa, o número da posição em uso preenchido (`aria-pressed`), "Confirmar a empresa" para vaga em dúvida e "Descartar"; barra com "Salvar e continuar aqui" / "Salvar e voltar para Mão de obra" |
| Rubrica de produtos | Especificação em cada item; "Pesquisar de novo só este item" (todas as lojas ou só outras); quadro "Adicionar itens" com várias linhas e colagem de lista; "Salvar e pesquisar os preços" salva antes de pesquisar; Enter num campo só salva (botão invisível no início do formulário), nunca dispara pesquisa |
| Rubrica de sistema | Tela própria (`sistema.html`): ferramentas de referência, 3 cotações com preço mensal, cotação automática e a lista de fornecedores conhecidos |
| Rubrica de serviço | Tela própria (`servico.html`): serviços com especificação e 3 propostas em PDF cada; sem pesquisa automática |
| Tarefa | Avisos com margem; "Cancelar a tarefa" vale uma vez ("Cancelando…") |

Peças comuns das telas de rubrica ficam em `templates/_rubrica.html` (cartão de pesquisa, linhas novas, barra de salvar, dados da rubrica, excluir).

## 9. Ajustes de 03/10/2026

| Tela | Mudança |
|---|---|
| Todas as telas de edição | Quadro/lista "O que a verificação aponta" com a mesma situação da lista do projeto e "Marcar como revisado" no próprio lugar (macro `pontos_lista`; os botões usam o formulário `#f-revisar` do `base.html`) |
| Projeto → Verificação | Caixas de marcar, "Selecionar todos" e "Marcar os selecionados como revisados"; saiu da configuração a opção "produto igual de outra marca" |
| Rubrica de produtos | Campo "Marca"; aviso quando as 3 pesquisas não são do mesmo produto; bloco "Refazer só esta pesquisa" em cada pesquisa ("Buscar outra loja (mesmo produto)" e "Guardar a página de novo"); linhas novas com marca |
| Cargo | Faixa salarial explicada ("o cálculo usa sempre o menor"); bloco "Refazer só esta pesquisa" em cada pesquisa ("Buscar outra vaga" e "Guardar a página de novo") |
| Sistema | bloco "Refazer só esta cotação" em cada cotação ("Cotar de novo com outro sistema" e "Guardar a página de novo"); texto "o que você deixou fica onde está" |
| Campos de link | Endereço com espaço é aceito (vira %20) |
| Rubrica de produtos e de serviço | Itens em lista recolhível (uma linha por item: quantidade, 3 preços com a loja, média, valor no plano, situação). Dentro do item: campos numa linha só (as dicas longas foram para o `?`), as 3 pesquisas com os botões "Buscar outra loja" e "Guardar a página de novo" lado a lado, e no rodapé "Pesquisar de novo só este item", "Trocar por outra opção", "Por que este produto", "Opções avançadas" e "Excluir este item ao salvar". A explicação longa da pesquisa automática ficou em "Como a pesquisa funciona" |
| Cargo | As 3 pesquisas em lista recolhível (empresa e vaga, salário, site, data, PDF, situação); dentro, os campos em colunas. "Títulos similares aceitos" e o banco de vagas são abre-e-fecha (o banco abre sozinho quando faltam pesquisas ou quando se chega por `#t-banco`); tabela do banco mais densa (`.tabela--densa`), com o local junto da vaga, o motivo do CNPJ em "por quê" e o descarte na lixeira |
| Sistema e serviço | "Detalhes e comprovante" de uma cotação já comprovada vem recolhido |
| Todas as telas do projeto (05/10/2026) | Topo comum `_projeto_topo.html` (macro `projeto_topo(atual)`): nome, proponente, indicadores, botões "Baixar tudo para a Secretaria (.zip)" e "Só as planilhas (.xlsx)" e a barra de navegação (Visão geral · Mão de obra · Materiais e serviços · Verificação · CNPJs e comprovantes · Configuração · Histórico). Na tela do projeto as partes são âncoras (`data-secoes`); em CNPJs e Histórico os mesmos botões voltam para a parte certa do projeto e a tela atual fica marcada |
| CNPJs e comprovantes | Indicadores "Já baixados, falta importar" e "Falta emitir"; cada linha diz se o PDF já está na pasta "Orça.AI" (Documentos), com o caminho e o botão "Abrir a pasta Orça.AI"; a tela consulta `/cnpjs/baixados` a cada 4 s |
| Página inicial | "Novo projeto" na largura toda (`.formulario.formulario--projeto`, 3 colunas) |
| Cargo (05/10/2026) | Campo "Faixa salarial pretendida" (opcional) em "Adicionar cargo" e em "1. Dados do cargo"; em "3. Valor no plano", a linha "Faixa pretendida: R$ X → N h = R$ Y"; o botão do banco vira "Usar as 3 vagas de menor salário que chegam na faixa"; na lista de cargos do projeto, a faixa aparece junto da carga horária |
| Proposta da pesquisa | Linha "O sistema entendeu: …" quando o pedido foi reescrito, ganhou outros nomes ou outras buscas |

## 10. Órgãos (05/10/2026)

| Tela | O que tem |
|---|---|
| Menu | Entrada "Órgãos" entre "Tarefas" e "Base da Receita" (`base.html`) |
| Órgãos (`orgaos.html`, `/orgaos`) | Tabela-cartão com esfera, regras do sistema desligadas, regras próprias e projetos de cada órgão; selo "Padrão do sistema"; formulário "Adicionar órgão" com "Começar com as regras de" (em branco ou cópia de outro); abre-e-fecha "Órgãos removidos", com "Restaurar" |
| Órgão (`orgao.html`, `/orgaos/{id}`) | Um formulário só para as partes 1 a 3, com barra de salvar fixa: **1. Dados** (nome, sigla, esfera, estado, nome na coluna do concedente, observações); **2. Como o orçamento é feito** (validade, valor do plano, valor da hora, planilhas do pacote, repasse); **3. Regras do sistema** (caixa "Vale?" e seletor de peso em cada regra; as cinco fixas mostram "Sempre"). **4. Regras próprias**: lista recolhível (código, título, o que confere em uma linha, peso, ligada/desligada); dentro, os campos do tipo; "Adicionar regra" é um abre-e-fecha por tipo, com a explicação de cada um. **5. Deixar a IA propor as regras**: caixa de texto e, depois da resposta, a proposta com caixas de marcar e a frase do texto de onde cada regra saiu. No fim, o quadro "Remover este órgão" (com confirmação; não aparece no órgão padrão) |
| Página inicial | "Novo projeto" ganhou o seletor "Órgão que analisa o projeto" |
| Projeto | O órgão aparece na linha de dados do topo; em Configuração, seletor de órgão com o link "Ver as regras de …"; a Verificação diz com as regras de quem o orçamento é conferido (link "Ver ou mudar as regras do órgão") e, quando há regra em texto para a IA, mostra o botão "Conferir regras com a IA (n)"; o texto de cada ponto usa o nome que o órgão deu à regra própria ("regra própria de …") |
| Cargo e rubrica | Campo opcional "Começa no mês", ao lado da duração, com a dica dizendo onde a rubrica fica hoje nos cronogramas |
| Rubrica de produtos | Abre-e-fecha "Não sabe por onde começar? Peça à IA uma lista de itens e quantidades" (caixa de texto e botão; desligado sem a chave da IA). Depois da resposta, o cartão "O que a IA sugere para esta rubrica": tabela com caixa de marcar, item, quantidade por mês editável e o porquê; botões "Acrescentar os marcados à rubrica" e "Descartar a sugestão" |
| Topo do projeto | Terceiro botão de baixar: "Planilhas em PDF" (as mesmas abas da planilha, prontas para imprimir) |
| Ajuda | Glossário com "Órgão", "Regra própria" e "Começa no mês"; dúvida "Meu projeto é de outra secretaria. Funciona?"; a dúvida sobre os dados na internet diz o que a IA recebe |

## 11. Apagar as pesquisas e refazer do zero (06/10/2026)

| Tela | O que tem |
|---|---|
| Projeto → Visão geral | No passo "Pesquise vagas e preços", ao lado de "Pesquisar tudo automaticamente", o botão de texto "Apagar as pesquisas e refazer do zero" |
| Projeto → Configuração | Cartão "Refazer as pesquisas do zero", antes de "Remover projeto" |
| Apagar as pesquisas (`zerar.html`, `/p/{id}/zerar-pesquisas`) | Topo do projeto; 4 indicadores (pesquisas automáticas, itens que voltam ao pedido, marcas apagadas, feitas à mão); cartão "O que sai", com abre-e-fecha de cargos, itens, itens que voltam ao que foi pedido ("de → para") e quantidades; cartão "O que fica"; cartão "Confirmar" com as opções (marcas que a pesquisa preencheu e vagas confirmadas: marcadas; feito à mão: desmarcada) e os botões "Apagar e pesquisar tudo de novo", "Só apagar" e "Cancelar". O envio pede confirmação na janela de perigo. Com tarefa em andamento, aviso e botões desligados |
| Ajuda | Dúvida "Quero refazer todas as pesquisas do zero. Como faço?" |

## 13. Títulos com vagas, empresas para confirmar e limite de horas (08/10/2026)

| Tela | O que tem |
|---|---|
| Cargo → "2. As 3 pesquisas de salário" | Quadro **"Títulos com vagas"** (`id="t-titulos"`), acima da lista das pesquisas, quando há vagas de outro título, título similar em uso ou títulos misturados: o título em uso, um item por título (selos "título do cargo" / "título similar" / "em uso", "N de 3 vagas", média, as empresas com o salário), botão "Usar as 3 vagas deste título" nos grupos completos e "Voltar ao título do cargo"; embaixo, "Ainda sem 3 vagas (não podem ser usados): …". Com títulos misturados, aviso de erro no alto do quadro |
| Cargo → banco de vagas | Vaga de outro título: "De outro título (X): para usar, escolha esse título em Títulos com vagas", no lugar dos botões 1-2-3 |
| Cargo → banco de vagas → "Confirmar a empresa" | Lista "Empresas ativas com esse nome na base da Receita": razão social, nome fantasia, CNPJ, cidade/UF, selo "mesma cidade da vaga" ou "mesmo estado da vaga" e botão "É esta"; o campo de CNPJ continua para digitar |
| Projeto → configuração → "Mão de obra" | Campo "Máximo de horas por mês de um cargo" (padrão 90) |
| Apagar as pesquisas | O texto diz que saem todas as vagas guardadas dos cargos, inclusive as descartadas |

## 12. Quadro de decisão do item (06/10/2026)

| Tela | O que tem |
|---|---|
| Rubrica de produtos → item | Quando a última pesquisa não achou o item pedido igual em 3 lojas: cartão "O sistema não achou … igual em 3 lojas" (`id="decidir{i}"`), com "Nada foi substituído", a lista "1. Substituir por uma destas opções" (selo do tipo de opção, as 3 lojas com link e preço, o que a IA achou, botão "Substituir por esta opção"), o abre-e-fecha "Ver também produtos de outro tipo, da categoria da rubrica (N)" e "2. Não substituir", com o botão "Salvar o que mudei e pesquisar este item de novo". Enquanto o quadro aparece, "Trocar por outra opção já pesquisada" fica oculto (as opções são as mesmas) |
| Rubrica de produtos → item sem nenhuma opção | O mesmo cartão (`id="decidir{i}"`), sem a lista de opções: "Nada foi substituído, e a pesquisa também não tem opção de substituição para mostrar", o parágrafo "O mais perto do pedido — o mesmo produto, mas em só 2 lojas: … Falta a 3ª loja" (quando há) e o botão "Salvar o que mudei e pesquisar este item de novo" |
| Quadro de decisão → tipos de opção | Selos: "Mesma marca e descrição; códigos de barras diferentes", "O mesmo produto em 2 lojas; a 3ª não cita um detalhe", "Como pedido, mas sem: …", "Parecido: outro tamanho ou variante", "Relacionado: mesmo tipo de produto". Nas duas primeiras, a linha "IA acha que é / NÃO é o mesmo produto" ou "A IA não conferiu esta opção" |
| Rubrica de produtos → item substituído | Aviso "Este item está substituído: você pediu X; o que está orçado é Y" e botão "Desfazer a substituição" |
| Rubrica de produtos (alto da lista) | Aviso "N item(ns) desta rubrica estão substituídos" e botão "Desfazer as N substituições" |
| Proposta da pesquisa | Linha com o selo "Aguarda a sua decisão" (há opções) ou "Não achado em 3 lojas" (não há); o motivo diz "o mais perto do pedido" quando o produto existe em 2 lojas; o texto do fim diz que o sistema nunca substitui sozinho |
| Tarefa "Pesquisar tudo" | No resumo de cada rubrica, "N não achado(s) como pedido(s): aguardam a sua decisão (nada foi substituído)"; um aviso lista os itens |
| Tarefa "Nova pesquisa" de um item | Aviso "NADA foi substituído. Há N opção(ões) de substituição na tela do item" e volta direto ao quadro (`#decidir{i}`) |
