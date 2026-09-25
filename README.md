# Orça.AI

*(O repositório se chama `Orca.AI`, sem "ç", porque o GitHub não aceita o caractere.)*

Montador de orçamentos para projetos sociais de OSCs (termos de fomento, colaboração, emendas parlamentares). Gratuito e de código aberto.

O Orça.AI pesquisa produtos e vagas, confere se os produtos são idênticos, valida CNPJs, monta as cotações e os três orçamentos comparativos, calcula as médias, fecha o orçamento final **exatamente no teto** do projeto e gera o pacote de evidências. A regra que orienta tudo: **todo valor precisa ser comprovável perante a secretaria**.

## Situação

Em construção — **Fase 1** pronta: cálculo, regras, banco local, seleção, otimização do teto, coleta por URL (evidências e CNPJ), captura assistida e PDF enviado para lojas que recusam programas, comprovantes da Receita, correspondência de produtos com catálogos e vocabulário editáveis por OSC, documentos (Excel, PDF e pacote ZIP), API local e interface. Ainda não há instalador. **Fase 2** pronta para os testes: o sistema pesquisa sozinho as lojas de cada lote ("Pesquisar nas lojas"), abre as buscas de vagas na janela para você escolher, avisa as pesquisas vencidas e pesquisa de novo, sugere melhorias no vocabulário a partir das suas decisões, fecha o lote (pesquisa tudo, pede para você confirmar um produto por item, com as fotos lado a lado, e sugere outra marca para o item que falta nas lojas), procura produto de outra marca quando um item passa da média e, se você quiser, usa opcionais gratuitos (buscador SerpApi, Google Vagas e IA Gemini ou local) — tudo desligado por padrão.

## Como usar (versão em desenvolvimento)

Depois de instalar (veja Desenvolvimento), rode `orca`. O sistema abre no navegador em `http://localhost:8765`:

1. crie o projeto com o teto e a duração;
2. cadastre os orçamentos (rubricas), os lotes, os itens (com marca e especificação) e os cargos;
3. em **Pesquisa e revisão**, cole os links das páginas das lojas e das vagas; o sistema guarda a prova, lê o preço e confere se é o mesmo produto. Se a loja recusar programas (como Carrefour e Extra), escolha **abrir numa janela** — você navega e clica em "Capturar agora" — ou envie o PDF da página salvo no seu navegador;
4. os CNPJs são consultados sozinhos; em **Documentos**, emita os comprovantes da Receita no seu navegador e envie os PDFs (o sistema confere cada um);
5. em **Regras**, ajuste o que o edital pede (ex.: regra A ou B em cada orçamento);
6. resolva o que estiver apontado, feche o teto e gere os documentos.

Em **Catálogos** ficam o vocabulário, as categorias, as lojas e os pares de exemplo da sua OSC. Toda mudança no vocabulário é conferida antes de salvar: se fizer produtos diferentes parecerem iguais, é recusada.

Os dados ficam na pasta `Documentos\Orca.AI` (ou na que você escolher com `orca --pasta`).

## Documentação

A especificação completa está em [`docs/`](docs/README.md): decisões, regras de negócio, modelo matemático, arquitetura, regras padrão, roadmap e levantamento de lojas.

## Desenvolvimento

Requisitos: Python 3.12+.

```bash
python -m venv ~/.venvs/orca-ai
~/.venvs/orca-ai/Scripts/python -m pip install -e "backend[dev]"
cd backend && ~/.venvs/orca-ai/Scripts/python -m pytest
```

(No Linux/macOS, troque `Scripts` por `bin`.) A interface fica em `frontend/`; para compilá-la: `cd frontend && npm install && npm run build` (precisa de Node.js).

## Licença

[GNU AGPL-3.0](LICENSE). Quem modificar o Orça.AI e oferecê-lo a outras pessoas precisa manter o código aberto.
