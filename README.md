# Orça.AI

**Orçamentos de projetos sociais prontos para o órgão que vai analisar: pesquisa de vagas e de preços, comprovantes em PDF e planilhas — no seu computador, sem custo e com tudo conferível.**

O Orça.AI é um sistema local (abre no navegador, em `http://127.0.0.1:8000`) para organizações da sociedade civil (OSCs) montarem o **Plano de Aplicação** e o **Comparativo de Preço** de projetos financiados por secretarias, fundos e emendas. Ele procura sozinho as 3 pesquisas de cada item, guarda o comprovante de cada uma, confere as regras do órgão e entrega um pacote pronto para enviar.

Já vem com as regras da Secretaria da Justiça e Cidadania do Estado de São Paulo (SEJC). As de qualquer outro órgão são cadastradas pela tela, sem programar.

> Versão 0.6 · em uso e em evolução · feito e testado no Windows 11 com Python 3.12

---

## O que ele faz

| | |
|---|---|
| **Mão de obra** | Procura vagas do cargo em sites de emprego, lê o salário que a página mostra, descobre e confere o CNPJ de quem contrata e guarda a página da vaga em PDF. Aceita uma **faixa salarial pretendida** por cargo e ajusta as horas para o valor chegar nela. |
| **Produtos** | Acha o **mesmo produto** (marca, cor, tipo e embalagem) em 3 lojas de empresas diferentes, confere estoque e preço no CEP do projeto e guarda um PDF por pesquisa, só com aquele item. Quando o produto não existe em 3 lojas, propõe uma troca e explica o motivo. |
| **Sistemas e serviços** | Sistemas: compara 3 fornecedores pelas ferramentas de referência (não pelo nome nem pelo menor preço). Serviços: recebe as 3 propostas em PDF e confere valor e CNPJ. |
| **CNPJ** | Confere a situação de cada empresa na base pública da Receita Federal e importa o Comprovante de Inscrição e de Situação Cadastral que você emite. |
| **Verificação** | Aponta, item por item, o que bloqueia o envio e o que merece revisão, com o código da regra. |
| **Órgãos e regras** | Cada órgão (secretaria, ministério, fundo, emenda) é um cadastro: quais regras valem e com que peso, as regras próprias dele ("só empresas do estado", "material permanente não pode", "mão de obra até 60% do total"), como o valor do plano é escolhido e quais planilhas vão no pacote. O projeto segue as regras do órgão dele. |
| **Fechar no teto** | Encontra a combinação de horas e valores que fecha o plano exatamente no teto do projeto, sem sair das regras. |
| **Histórico** | Cada alteração vira uma versão nova; nada é apagado e qualquer versão pode ser restaurada. |
| **Pacote para envio** | Um `.zip` com a planilha formatada e com fórmulas (Plano de Aplicação, Cronograma físico-financeiro, Etapas e Fases, Cronograma de desembolso e Comparativo de Preço), as mesmas planilhas em PDF e o PDF de cada pesquisa, separado por rubrica e item, na ordem do plano, cada um já com o comprovante de CNPJ da empresa. |

## Como é o uso

1. **Crie o projeto**: nome, teto (o valor que o orçamento precisa fechar), CEP de entrega e o órgão que vai analisar. Órgão novo? Cadastre em **Órgãos** e ajuste as regras dele.
2. **Cadastre o plano**: os cargos (com horas ou faixa salarial pretendida) e as rubricas de materiais, sistemas e serviços, com os itens de cada uma. Dá para colar uma lista inteira do Excel — ou descrever a atividade ("lanche para 30 adolescentes, 2 encontros por semana") e deixar a IA sugerir os itens e as quantidades, que você confere antes de aceitar.
3. **Clique em "Pesquisar tudo automaticamente"**: o sistema busca vagas e preços, confere os CNPJs e guarda os comprovantes. Uma barra mostra o andamento; o que já está pesquisado não é refeito.
4. **Confira**: cada item é uma linha com os 3 preços, a média, o valor no plano e a situação. Dá para refazer uma pesquisa só, trocar de loja ou de vaga e marcar pontos como revisados.
5. **Emita os comprovantes de CNPJ** na Receita (o site pede uma verificação humana) e salve na pasta `Orça.AI`, em Documentos: o sistema mostra o que já foi baixado e importa.
6. **Feche no teto e baixe o pacote** para enviar ao órgão.

## O que o sistema nunca faz

- **Não inventa** preço, produto, vaga, CNPJ nem endereço: tudo o que entra no orçamento veio de uma página ou de um documento, e o PDF fica guardado com código de verificação (SHA-256).
- **Não resolve nem contorna CAPTCHA** e não disfarça a automação. Loja que pede verificação humana sai da pesquisa.
- **Não guarda senhas nem chaves**. O login em sites, quando necessário, é feito por você numa janela do próprio site.
- **Não manda seus dados para fora**: projetos, vagas e comprovantes ficam só no seu computador. A exceção é a IA gratuita, opcional: ela recebe nomes de produtos anunciados e de cargos e, só quando você pede, os itens do plano (para conferir uma regra escrita em texto; sem o nome da organização nem o do projeto), o trecho do edital que você colou (para propor regras) ou a descrição da atividade que você escreveu (para sugerir itens).
- **Não custa nada**: usa só ferramentas e fontes gratuitas.

O sistema monta e confere; revisar o resultado e enviar continua sendo responsabilidade da organização.

## Instalação (Windows)

**Você precisa de:** Windows 10 ou 11, [Python 3.12](https://www.python.org/downloads/) (marque *Add python.exe to PATH* ao instalar), internet e espaço em disco — cerca de 150 MB para o navegador de captura e cerca de 14 GB para a base pública de CNPJ da Receita, que o sistema baixa sozinho.

1. Baixe o repositório (botão **Code → Download ZIP**, ou `git clone`).
2. Na pasta `sistema`, clique duas vezes em **`instalar.bat`** (uma vez só). Ele cria o ambiente Python em `%LOCALAPPDATA%\OrcamentoOSC\venv`, instala as dependências e baixa o navegador Chromium usado para capturar as páginas.
3. Clique duas vezes em **`iniciar.bat`** sempre que for usar. O navegador abre em `http://127.0.0.1:8000`; feche a janela preta para desligar.

Na primeira abertura, a base pública de CNPJ da Receita é baixada em segundo plano (leva algumas horas; o resto do sistema já funciona enquanto isso) e depois é atualizada todo mês.

### IA gratuita (opcional)

Com uma chave gratuita do Google Gemini, o sistema usa a IA como **apoio**: para confirmar que dois anúncios são o mesmo produto, entender pedidos escritos de outro jeito ("Caixa Caneta Esferográfica Azul", "Sardinha Enlatada"), escolher o plano de um sistema pelas ferramentas, sugerir títulos de cargo com a mesma função, **sugerir os itens e as quantidades de uma rubrica** a partir da descrição da atividade (nunca o preço: preço só vem de pesquisa), **propor as regras de um órgão a partir do texto do edital** (nada é gravado antes de você aceitar) e conferir o plano contra uma regra escrita em texto livre (o resultado entra sempre como ponto para revisar). As regras é que decidem; a resposta da IA é sempre conferida e fica registrada. Sem a chave, tudo funciona, com mais itens deixados para a sua conferência.

O passo a passo está em [GEMINI_PASSO_A_PASSO.md](GEMINI_PASSO_A_PASSO.md). A chave fica só na variável de ambiente `GEMINI_API_KEY` do seu Windows: nunca é escrita em arquivo nem mostrada na tela.

## Onde ficam os dados

| O quê | Onde | Vai para o repositório? |
|---|---|---|
| Projetos, versões, banco de vagas e comprovantes em PDF | `sistema/dados/` | **Não** |
| Base da Receita, cache das buscas, navegador e ambiente Python | `%LOCALAPPDATA%\OrcamentoOSC\` | Não |
| Comprovantes de CNPJ que você emite na Receita | `Documentos\Orça.AI\` | Não |

O `.gitignore` deixa de fora os dados dos projetos e qualquer documento da organização.

## De onde vêm as pesquisas

- **Vagas:** InfoJobs, Catho, Vagas.com, BNE e LinkedIn (páginas públicas).
- **Produtos (24 lojas):** Atacadão, Sam's Club, Tenda Atacado, Giga Atacado, Carrefour, Pão de Açúcar, Extra Mercado, Mambo, Coop, Oba Hortifruti, Americanas, Casa & Video, Telhanorte, Drogaria São Paulo, Drogarias Pacheco, Drogal, Farmácias Pague Menos, Kalunga, Gimba, Lepok, Papelex, Livrarias Curitiba, Bazar Horizonte e Afonso Ruotolo.
- **Sistemas:** páginas de preços de fornecedores de sistemas de gestão para o terceiro setor.
- **CNPJ:** dados abertos da Receita Federal e o comprovante oficial emitido por você.

Uma loja só entra na lista quando passa em quatro conferências feitas de verdade: a busca do site é aberta, ela entrega em São Paulo, publica o CNPJ no próprio site (conferido como ativo na base da Receita) e a página do produto abre sem verificação humana. Em sites com marketplace, só vale o que a **própria loja** vende — a oferta de outro vendedor é de outra empresa, com outro CNPJ.

Lojas e sites mudam com frequência: quando uma fonte deixa de responder ou passa a pedir verificação humana, ela sai da pesquisa e as outras cobrem.

## Regras conferidas

O sistema traz um catálogo de 28 regras: as estabelecidas pela SEJC (3 pesquisas por item, empresas diferentes e ativas, comprovante de cada pesquisa, valor do plano até a média, menor valor da faixa salarial, horas inteiras, entre outras) e as do próprio sistema (mesmo produto nas 3 lojas, comprovante que prova o preço registrado, dois itens que não podem ser o mesmo produto, valor no plano igual ao menor preço ou à média, caixa pedida que não pode ser atendida com a unidade avulsa). A lista completa, com o código de cada uma, aparece na tela **Ajuda** e em [`sistema/orcamento/regras.py`](sistema/orcamento/regras.py).

### Regras de cada órgão

Na tela **Órgãos**, cada órgão diz o que vale para ele — tudo pela tela, e a verificação dos projetos muda na hora:

- **Regras do catálogo**: ligada ou desligada, e o peso (pendência que bloqueia o envio, ponto para revisar ou só informação). Cinco não podem ser desligadas, porque garantem que o orçamento está inteiro e é verdadeiro.
- **Regras próprias** (códigos P01, P02…), criadas a partir de tipos que o sistema sabe conferir sozinho:

| Tipo | Exemplo |
|---|---|
| Empresas só de determinados estados | "As cotações devem ser de fornecedores de SP" (o estado vem do cadastro oficial do CNPJ) |
| Itens que não podem constar | "Material permanente não pode" (lista de palavras; plural e acento não fazem diferença) |
| Um grupo até uma parte do total | "Mão de obra até 60% do total" |
| Valor máximo | "Cada item até R$ 2.000,00" · "Cada cargo até R$ 5.000,00 por mês" |
| Duração máxima | "Nenhuma despesa por mais de 12 meses" |
| Texto conferido por uma pessoa | Um lembrete que aparece em todo projeto do órgão até alguém marcar como revisado |
| Texto conferido pela IA | A IA lê a regra e os itens do plano e aponta o que parece descumprir (sempre como ponto para revisar) |

- **Como o orçamento é feito**: validade das pesquisas, como o valor do plano é escolhido, como a hora de trabalho é calculada, quais planilhas vão no pacote, como é o repasse e o nome que aparece na coluna "Concedente".
- **IA propõe as regras**: cole o trecho do edital ou do manual do órgão e a IA sugere as regras próprias e o que desligar, mostrando de que frase tirou cada uma. Você escolhe o que aceitar.

Remover um órgão só o tira da lista: os projetos ligados a ele continuam com as mesmas regras, e dá para restaurar.

## Estrutura do repositório

```
├── README.md                    este arquivo
├── sistema/
│   ├── app.py                   as telas e rotas (FastAPI)
│   ├── orcamento/               o motor
│   │   ├── modelo.py, db.py     dados do projeto e versões (SQLite, só acrescenta)
│   │   ├── regras.py, calculo.py  regras, médias, verificação
│   │   ├── orgaos.py, regras_dinamicas.py  cadastro de órgãos e as regras próprias de cada um
│   │   ├── otimizador.py        "Fechar no teto" (OR-Tools)
│   │   ├── vagas.py             busca e leitura de vagas, títulos, banco de vagas
│   │   ├── produtos/            lojas, identidade de produto, cesta, comprovantes, texto dos itens
│   │   ├── sistemas.py          cotação de sistemas pelas ferramentas de referência
│   │   ├── cnpj*.py, comprovante_receita.py   CNPJ e comprovante oficial
│   │   ├── ia.py                apoio da IA gratuita (opcional)
│   │   ├── exportar.py, pacote.py  Excel de conferência e pacote para a Secretaria
│   │   ├── pacote_pdf.py        as planilhas do pacote em PDF (cada aba convertida célula a célula)
│   │   └── servico.py, tarefas.py  o que cada botão faz; tarefas com progresso
│   ├── templates/               telas (Jinja2), estilo e JavaScript, sem bibliotecas externas
│   ├── tests/                   testes automáticos
│   ├── LEIAME.md                manual e histórico detalhado de cada mudança
│   ├── INTERFACE.md             guia das telas e dos componentes
│   ├── instalar.bat, iniciar.bat
│   └── requirements.txt
├── fase0/sejc/pt8_dados.json    plano real já aceito, usado como teste de regressão
└── *.md                         relatórios das fases de pesquisa (regras, fontes, testes de viabilidade)
```

## Para desenvolver

```bat
:: ambiente (o instalar.bat faz o mesmo)
py -3.12 -m venv "%LOCALAPPDATA%\OrcamentoOSC\venv"
"%LOCALAPPDATA%\OrcamentoOSC\venv\Scripts\python" -m pip install -r sistema\requirements.txt
"%LOCALAPPDATA%\OrcamentoOSC\venv\Scripts\python" -m playwright install chromium

:: rodar
cd sistema
"%LOCALAPPDATA%\OrcamentoOSC\venv\Scripts\python" -m uvicorn app:app --host 127.0.0.1 --port 8000

:: testes
"%LOCALAPPDATA%\OrcamentoOSC\venv\Scripts\python" -m pytest -q
```

O ambiente Python fica fora da pasta do projeto de propósito, para não ser sincronizado por serviços de nuvem.

**Testes:** 234 ao todo. Num clone limpo, 232 passam e 2 são pulados (leem documentos que não fazem parte do repositório). Cada teste usa uma pasta temporária: nenhum mexe nos dados reais.

**Variáveis de ambiente**

| Variável | Para quê |
|---|---|
| `GEMINI_API_KEY` | Chave da IA gratuita (opcional) |
| `ORCAMENTO_DADOS` | Outra pasta para os dados dos projetos (padrão: `sistema/dados`) |
| `ORCAMENTO_LOCAL` | Outra pasta para base da Receita, cache e navegador (padrão: `%LOCALAPPDATA%\OrcamentoOSC`) |
| `ORCAMENTO_COMPROVANTES` | Outra pasta para os comprovantes de CNPJ emitidos (padrão: `Documentos\Orça.AI`) |
| `ORCAMENTO_SEM_ROTINAS` | `1` desliga as rotinas automáticas ao abrir (usado nos testes) |

**Tecnologias:** Python 3.12, FastAPI, Jinja2, SQLite, Playwright (Chromium), OR-Tools, PyMuPDF e openpyxl.

## Limites conhecidos

- O comprovante oficial de CNPJ depende de você: o site da Receita pede uma verificação humana para cada empresa.
- Item que não existe igual em 3 lojas, nem como troca aceitável, fica com pendência para a sua decisão.
- Cargo de título raro pode levar dias até o banco de vagas juntar 3 vagas válidas; o sistema avisa e continua procurando.
- Sistemas vendidos só sob consulta precisam da proposta do fornecedor, anexada em PDF.
- Na Catho, a página só mostra as informações da empresa com login; o sistema abre a janela e você entra com a sua conta.
- As pesquisas levam minutos (o sistema espera entre os acessos para não sobrecarregar os sites).
- Regras de órgão: o sistema confere sozinho os tipos listados acima; o que não cabe neles entra como texto, conferido por uma pessoa ou, como apoio, pela IA.
- As planilhas seguem um modelo só (o de pré-cálculos); ainda não dá para enviar o modelo de planilha de outro órgão.
- No cronograma de desembolso, o repasse é em parcela única no 1º mês ou mês a mês; outras divisões são ajustadas na planilha.
- Só foi testado no Windows.

## Documentação

- [sistema/LEIAME.md](sistema/LEIAME.md) — manual de uso e o histórico detalhado de cada mudança, com o porquê.
- [sistema/INTERFACE.md](sistema/INTERFACE.md) — arquitetura das telas e guia dos componentes.
- [FASE0_SEJC.md](FASE0_SEJC.md) — levantamento das regras da Secretaria.
- [FASE0_RESULTADOS.md](FASE0_RESULTADOS.md), [FASE1_AUTOMACAO_TOTAL.md](FASE1_AUTOMACAO_TOTAL.md), [FASE1B_RESULTADOS.md](FASE1B_RESULTADOS.md) — testes de viabilidade das fontes e da automação.
- [ANALISE_ARQUITETURA.md](ANALISE_ARQUITETURA.md) — análise que deu origem ao sistema.
- [PROMPT.md](PROMPT.md) — o pedido original.

## Últimas mudanças

O histórico completo, com o motivo de cada decisão, está em [sistema/LEIAME.md](sistema/LEIAME.md).

- **05/10/2026 — versão 0.6**
  - **Órgãos com regras próprias**: o sistema deixa de ser só da SEJC. Cada órgão é um cadastro com as regras que valem, as regras próprias (7 tipos), a forma de fazer o orçamento e as planilhas do pacote; a IA propõe as regras a partir do edital.
  - **Planilha completa**: além do Plano de Aplicação e do Comparativo de Preço, saem o Cronograma físico-financeiro, as Etapas e Fases e o Cronograma de desembolso, puxando os valores do Plano por fórmula. Cada cargo e rubrica pode dizer em que mês começa.
  - Linhas da planilha com a altura certa para o texto (nomes compridos de empresa não saem mais cortados na impressão).
  - "Evolution" é uma linha da Bic, não uma marca: a marca do item passa a ser a do fabricante.
  - **IA sugere itens e quantidades**: na rubrica de produtos, descreva a atividade e a IA propõe os itens e a quantidade por mês, com a conta de cada um. Você marca o que aceita; os preços continuam vindo só da pesquisa.
  - **Planilhas em PDF**: o Plano, os cronogramas e o Comparativo saem também em PDF (botão "Planilhas em PDF" e dentro do pacote), gerados a partir da própria planilha — o PDF nunca diz outra coisa — e sem precisar do Excel.
  - **Teste real de ponta a ponta** (projeto de teste, numa cópia dos dados): vagas com faixa pretendida e produtos nas lojas novas. Dele saiu a regra **S10**: quando o pedido é de uma caixa e a pesquisa só acha a unidade avulsa, o item vai para revisão em vez de ficar "em ordem".
  - **6 lojas novas** (Mambo, Giga Atacado, Casa & Video, Telhanorte, Drogal e Farmácias Pague Menos), escolhidas entre 89 sites sondados. Em sites com marketplace, só entra o que a própria loja vende.
- **05/10/2026**
  - Faixa salarial pretendida por cargo: vagas de menor salário que alcançam a faixa e horas ajustadas a ela; o "Fechar no teto" reparte a diferença por igual entre os cargos.
  - Pacote para a Secretaria (`.zip`) com as planilhas e os PDFs por rubrica, cada um com o comprovante de CNPJ; as planilhas já saem com os valores calculados.
  - Descrição dos itens simples e sem marca; unidades de medida com as letras certas (1L, 500mL, 1kg).
  - Busca que entende o pedido (embalagem na frente, abreviações, outros nomes do produto, títulos de vaga abreviados ou com a cidade).
  - Valor no plano: só o menor dos 3 preços ou a média.
  - Comprovantes de CNPJ na pasta `Documentos\Orça.AI`, com a situação de cada um antes de importar.
  - Topo do projeto em todas as telas; telas de edição em lista recolhível.
- **03/10/2026** — mesmo produto exato nas 3 lojas, campo de marca, nova pesquisa de uma pesquisa só, revisão em lote.
- **02/10/2026** — interface nova, quantidade de profissionais por cargo, títulos similares de vaga, telas próprias para sistema e serviço.

## Licença

Ainda não definida.
