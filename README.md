# Orça.AI

*(O repositório se chama `Orca.AI`, sem "ç", porque o GitHub não aceita o caractere.)*

Montador de orçamentos para projetos sociais de OSCs (termos de fomento, colaboração, emendas parlamentares). Gratuito e de código aberto.

O Orça.AI pesquisa produtos e vagas, confere se os produtos são idênticos, valida CNPJs, monta as cotações e os três orçamentos comparativos, calcula as médias, fecha o orçamento final **exatamente no teto** do projeto e gera o pacote de evidências. A regra que orienta tudo: **todo valor precisa ser comprovável perante a secretaria**.

## Situação

Em construção — **Fase 1**: cálculo, regras, banco local, seleção, otimização do teto, coleta por URL (evidências e CNPJ), correspondência de produtos, documentos (Excel, PDF e pacote ZIP), API local e telas principais prontos. Faltam as telas de captura assistida, catálogos e regras; ainda não há instalador.

## Como usar (versão em desenvolvimento)

Depois de instalar (veja Desenvolvimento), rode `orca`. O sistema abre no navegador em `http://localhost:8765`:

1. crie o projeto com o teto e a duração;
2. cadastre os orçamentos (rubricas), os lotes, os itens (com marca e especificação) e os cargos;
3. em **Pesquisa e revisão**, cole os links das páginas das lojas e das vagas; o sistema guarda a prova, lê o preço e confere se é o mesmo produto;
4. consulte os CNPJs, resolva o que estiver apontado, feche o teto e gere os documentos.

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
