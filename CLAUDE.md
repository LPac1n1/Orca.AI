# CLAUDE.md — Orça.AI

O nome do sistema é **Orça.AI** (com "ç") em tudo que as pessoas leem. Sem "ç" só onde é obrigatório: repositório `Orca.AI`, pacote Python `orca`, distribuição `orca-ai`.

Montador de orçamentos para OSCs. O usuário (Leonardo, OSC CPIS 26 de Julho, São Paulo) constrói o sistema com o Claude Code e não é programador: responda em **português do Brasil**, em linguagem simples.

## Fonte da verdade

A especificação em [`docs/`](docs/README.md) manda. Antes de propor ou implementar algo, leia o trecho relevante. Decisões têm códigos (`D-xx`, premissas `P-xx`) em [`docs/01-decisoes.md`](docs/01-decisoes.md). Se algo não estiver decidido, **pergunte** em vez de assumir. Se uma decisão mudar, atualize os docs no mesmo commit.

## Princípios invioláveis (docs/README.md)

1. Nada é inventado: nenhum preço, produto, vaga, CNPJ, URL ou evidência. Sem evidência: *"Não foi possível validar automaticamente."*
2. Todo número é rastreável até evidência, regra (com versão) e decisão humana.
3. A IA propõe, o algoritmo confere e calcula, o humano aprova. A IA nunca é origem de número.
4. A IA pode rebaixar confiança, nunca aumentar.
5. Preços encontrados nunca são alterados.
6. Nada é apagado (registros imutáveis, eventos só de acréscimo).
7. Fontes escolhidas por critério objetivo; nunca para subir média.
8. Nenhuma substituição silenciosa.
9. Custo zero: nada essencial depende de serviço pago.

## Convenções de código

- Python 3.12, pacote `orca` em `backend/orca/`; testes em `backend/testes/` (pytest + hypothesis).
- **Dinheiro sempre em centavos (`int`)**. Valores exatos intermediários em `fractions.Fraction`. **Nunca `float`** em dinheiro, horas ou médias.
- Horas em **centésimos de hora** (`int`): 91,5 h = 9150.
- Arredondamento só pela função oficial (`orca.calculo.arredondamento`), nos pontos que a regra define (D-21, D-43).
- Módulos do núcleo (`dominio`, `calculo`, `selecao`, `correspondencia`, `otimizacao`) **não acessam rede nem disco**.
- Nomes do domínio em português (como nos docs). Cite a decisão no código quando ela justificar uma regra: `# D-23`.
- Toda regra de negócio nova vem com teste. Casos de teste da especificação: `docs/06-roadmap-e-testes.md` §3.

## Banco de dados (`orca.banco`)

- Toda gravação passa por `sessao_como(fabrica, autor)`; o autor é `usuario:<nome>`, `sistema[:<módulo>]` ou `ia:<provedor>`. A auditoria (`orca.auditoria`) registra cada criação/alteração em `evento` e recusa gravação sem autor.
- **Nunca** `sessao.delete(...)`: use `excluido_em`/`arquivado_em`. Tabelas com `__imutavel__` não se alteram — correção é registro novo. Gatilhos no banco repetem essas proteções.
- Mudou uma tabela? Gere a migração (`cd backend && python -m alembic revision --autogenerate -m "..."`), troque tipos próprios (`DataHora`, `Data`) por `sa.String` na migração e, depois de operações batch, recrie os gatilhos com `criar_gatilhos`. Os testes de `testes/banco/test_migracao.py` acusam divergências.
- Datas/horas sempre com fuso (`orca.banco.agora()`).

## Comandos

O ambiente virtual fica **fora do OneDrive** (para não sincronizar milhares de arquivos):

```bash
# instalar (uma vez)
python -m venv /c/Users/leopa/.venvs/orca-ai
/c/Users/leopa/.venvs/orca-ai/Scripts/python -m pip install -e "backend[dev]"
# testes
cd backend && /c/Users/leopa/.venvs/orca-ai/Scripts/python -m pytest
# testes que consultam APIs reais (marcados "rede"; normalmente pulados)
cd backend && ORCA_TESTES_REDE=1 /c/Users/leopa/.venvs/orca-ai/Scripts/python -m pytest -m rede
```

Para abrir o sistema:

```bash
/c/Users/leopa/.venvs/orca-ai/Scripts/orca
```

A interface (React + TypeScript + Vite) fica em `frontend/`. Depois de mudar as telas, compile — o resultado vai para `backend/orca/api/estatico/` e entra no commit:

```bash
cd frontend && npm install && npm run build
```

Para desenvolver com recarga automática: `orca` rodando e `cd frontend && npm run dev` (abre em http://localhost:5173).

A API tem documentação em `http://localhost:8765/api/docs`. Pedidos que mudam dados precisam do cabeçalho `X-Orca: 1`.

A captura de páginas usa o **Microsoft Edge** do Windows (Playwright, canal `msedge`); não baixe outro navegador. Testes marcados `navegador` usam uma loja sintética servida no próprio computador.

- **Janela visível (D-67):** captura assistida e comprovante da Receita rodam na pista `assistida` da fila (`orca.tarefas.fila`). Nessa janela **quem navega é o usuário**: o sistema só abre a página, espera o sinal ("Capturar agora" ou o comprovante na tela) e captura. Nunca automatize cliques, login ou captcha nela.
- **Catálogos da OSC (D-64 a D-66):** as edições ficam em `catalogo_camada` (só a diferença para `catalogos/*.yaml`) e os pares em `par_referencia` (`orca.fluxo.catalogos`). Mudança no vocabulário ou nas categorias só é salva se o teste de correspondência (`orca.correspondencia.avaliar`, pares do sistema + da OSC) não criar nenhum 🟢 errado novo.

## Cuidados

- O repositório é **público**. A pasta `Modelo de Orçamento/` (documentos reais de processos, com nomes de pessoas) está no `.gitignore` e **nunca** deve ser publicada. Dados de teste derivados de casos reais: só preços, produtos e CNPJs de empresas.
- Não fazer commit nem push sem o usuário pedir. Trabalho novo em branch própria; junção ao `main` com aprovação do usuário.
- Ao consultar sites de lojas: poucas requisições, sem login, sem aceitar cookies, sem contornar captcha.
- Catálogo de atributos e vocabulário (`catalogos/atributos.yaml`): toda mudança passa pelo caso T-11 (`testes/correspondencia/test_referencia.py`), que exige **nenhum falso 🟢**. Na dúvida, a correspondência fica 🟡.
- Dados de CNPJ: guardar só o necessário (razão social, situação, município…). Nunca sócios, e-mails ou telefones (LGPD).
