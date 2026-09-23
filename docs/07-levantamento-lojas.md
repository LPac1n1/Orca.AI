# 07 — Levantamento das lojas

**Verificado em:** 23/09/2026, a partir do computador da OSC (conexão residencial).
**Como:** poucas requisições a páginas públicas (acesso simples por HTTP e, quando necessário, um navegador comum). Nenhum login, nenhum cookie aceito.
**Resultado técnico:** [`catalogos/lojas.yaml`](../catalogos/lojas.yaml).

## 1. Resumo por loja

| Loja | CNPJ visto no site | Plataforma | Como coletar | Código de barras (EAN) | CEP | Observações |
|---|---|---|---|---|---|---|
| **Atacadão** | vendedor "ATACADAO SA" (CNPJ não aparece na home) | VTEX | **C0 — API pública**: busca por texto e **por EAN**; o CEP devolve as lojas próximas | ✅ na API | ✅ CEP → lojas (Aricanduva, Tatuapé, Itaquera…) | Melhor caso. A evidência (PDF da página) é capturada pelo navegador |
| **Carrefour Mercado** | 45.543.915/0736-50 e /0846-95 (rodapé, filiais) | VTEX | **C1 — navegador** (a API recusa acesso simples) | ✅ JSON-LD | pede CEP | Preço "de R$ 29,89 por R$ 25,29"; o JSON-LD traz o preço atual (25,29) |
| **Extra Mercado** | 47.508.411/0001-56 (rodapé) | própria (Next.js) | **C1 — navegador** | ✅ nos dados da página | — | ⚠️ O JSON-LD traz o **preço Clube Extra** (R$ 24,99), que exige cadastro; o preço normal (R$ 32,99) está na página |
| **Tenda Atacado** | 01.157.555/0011-86 (rodapé) | própria (Next.js) | **C1 — acesso simples** (dados embutidos na página) | ❌ não encontrado | — | ⚠️ Dois preços: unitário (R$ 25,90) e **atacado a partir de 4 un.** (R$ 23,90) |
| **Kalunga** | 43.283.811/0001-50 (rodapé) | própria | **C1 — acesso simples** | ❌ (só código interno) | — | Título bem estruturado (marca, gramatura, tamanho, nº de folhas). Mostra "Produto indisponível" e ⚠️ um preço de **assinante** |
| **Gimba** | 54.651.716/0011-50 (rodapé) = **Supricorp Suprimentos** | própria | **C1 — navegador** para o preço normal | ❌ no JSON-LD | — | ⚠️ O preço em destaque e o do JSON-LD são o **preço Pix** (−3%). Também tem "leve mais, pague menos" (2+ un.) |
| **Lepok** | 19.576.717/0001-04 (rodapé) | própria | **C1 — navegador** (produtos carregam por JavaScript) | a verificar | — | Detalhar na Fase 2 |
| **Amazon** | por vendedor ("Enviado / Vendido por") | própria | **C1 — só navegador** (acesso simples bloqueado) | ❌ não visível | — | Vendedor terceiro: CNPJ na página do vendedor |
| **Mercado Livre** | 03.007.331/0001-41 (é da plataforma, não do vendedor) | própria | **C4 — captura assistida** | — | — | ❌ **Exige login até no navegador comum**; a API de busca também está bloqueada |
| **Shopee** | — | própria | **C4 — captura assistida** | — | — | ❌ **Não mostra resultados sem login**. Muitos vendedores sem CNPJ |
| **Ongsys** (sistema de gestão) | não aparece no site | site institucional | **C1 — página de preços** (`/precos`) | — | — | Planos publicados: "de R$ 399 por R$ 299/mês" e outros |
| **OngFácil** (sistema de gestão) | não aparece no site | site institucional (Wix) | **C1 — navegador com rolagem** (`/registre-se`): os preços ficam em quadros incorporados que só carregam ao rolar | — | — | Mensalidade: Gratuito R$ 0,00 · Prata R$ 320,00 · Ouro R$ 490,00. Implantação opcional, à parte: Prata R$ 1.700 (ou 6× R$ 315) · Ouro R$ 2.000 (ou 6× R$ 370) |

## 2. O que isso muda no projeto

1. **Quase tudo é coletável de graça.** 9 das 12 funcionam com acesso simples ou com o navegador do sistema (a Lepok ainda precisa de confirmação). Mercado Livre e Shopee só com captura assistida (o usuário logado na janela do sistema). Os dois fornecedores de sistema de gestão publicam preço.
2. **O código de barras funciona como previsto.** O mesmo café aparece como "Tradicional Almofada 500g" no Carrefour e "Tradicional Pacote 500g" no Extra, e os dois têm o **mesmo EAN (7896089012019)**. A comparação por EAN resolve isso sem ambiguidade.
3. **"O preço da página" não é um número só.** Em 5 lojas havia mais de um preço para o mesmo produto: Pix (Gimba), clube de fidelidade (Extra), assinante (Kalunga), atacado por quantidade (Tenda, Gimba), promoção "de/por" (Carrefour). Pior: o dado estruturado às vezes traz justamente o preço especial. Por isso cada loja do catálogo tem a regra de **qual preço ler**, seguindo as decisões D-60 a D-63 (§3).
4. **Uma das lojas da grade já está no catálogo com outro nome:** Gimba é a Supricorp Suprimentos (mesmo CNPJ).
5. **CNPJ no site × CNPJ da matriz:** o Carrefour mostra CNPJs de filiais no rodapé. Padrão proposto: usar o CNPJ exibido no site (o responsável pela venda, D-13). Se houver mais de um, o sistema pergunta.
6. **Conteúdo escondido:** na OngFácil, os preços só carregam quando a página é rolada. A primeira leitura não os encontrou. O coletor precisa rolar a página inteira antes de capturar, e o levantamento de cada loja é revisado por uma pessoa.
7. **Serviços com mais de um valor:** a OngFácil cobra mensalidade e, à parte, uma implantação opcional. A especificação do item precisa dizer o que está incluído (atributos `escopo` e `periodicidade`, [05 §3](05-regras-padrao.md)).
8. **Ressalva:** os testes com navegador usaram um navegador comum. O navegador automatizado do sistema pode ser detectado com mais facilidade por alguns sites. Isso será confirmado na Fase 2, loja por loja.

## 3. Perguntas geradas pelo levantamento (respondidas em 23/09/2026)

| # | Situação | Decisão |
|---|---|---|
| Q1 | Preço **Pix** em destaque (Gimba) | **D-60:** usar o preço normal (cartão/boleto à vista) |
| Q2 | Preço de **clube/fidelidade ou assinante** (Extra, Kalunga) | **D-61:** usar o preço para qualquer comprador, sem cadastro |
| Q3 | Preço **promocional aberto a todos** ("de R$ 29,89 por R$ 25,29") | **D-62:** usar o preço atual (R$ 25,29), registrado na evidência |
| Q4 | Preço de **atacado por quantidade** (Tenda 4+, Gimba 2+) | **D-63:** usar sempre o preço unitário, para que o preço não mude quando o otimizador ajusta quantidades |

## 4. Próximos passos do catálogo

- Adicionar mais lojas conforme a OSC usar (o catálogo aceita novas entradas sem mudar o código).
- Na Fase 2: confirmar cada loja com o navegador automatizado, detalhar a Lepok e escrever o conector de cada uma.
