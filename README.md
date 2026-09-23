# Orça.AI

*(O repositório se chama `Orca.AI`, sem "ç", porque o GitHub não aceita o caractere.)*

Montador de orçamentos para projetos sociais de OSCs (termos de fomento, colaboração, emendas parlamentares). Gratuito e de código aberto.

O Orça.AI pesquisa produtos e vagas, confere se os produtos são idênticos, valida CNPJs, monta as cotações e os três orçamentos comparativos, calcula as médias, fecha o orçamento final **exatamente no teto** do projeto e gera o pacote de evidências. A regra que orienta tudo: **todo valor precisa ser comprovável perante a secretaria**.

## Situação

Em construção — **Fase 1**: cálculo, regras, banco local, seleção, otimização do teto, coleta por URL (evidências e CNPJ) e correspondência de produtos prontos. Ainda não há versão para uso.

## Documentação

A especificação completa está em [`docs/`](docs/README.md): decisões, regras de negócio, modelo matemático, arquitetura, regras padrão, roadmap e levantamento de lojas.

## Desenvolvimento

Requisitos: Python 3.12+.

```bash
python -m venv ~/.venvs/orca-ai
~/.venvs/orca-ai/Scripts/python -m pip install -e "backend[dev]"
cd backend && ~/.venvs/orca-ai/Scripts/python -m pytest
```

(No Linux/macOS, troque `Scripts` por `bin`.)

## Licença

[GNU AGPL-3.0](LICENSE). Quem modificar o Orça.AI e oferecê-lo a outras pessoas precisa manter o código aberto.
