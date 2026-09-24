# 05 — Regras padrão

## 1. Perfil de regras padrão do sistema

Camadas seguintes (OSC → secretaria/edital → projeto → orçamento) declaram **só o que muda**. Cada parâmetro cita a decisão de origem ([01](01-decisoes.md)).

Arquivo usado pelo sistema: [`backend/orca/regras/padrao-sistema.yaml`](../backend/orca/regras/padrao-sistema.yaml). Um teste garante que este bloco e o arquivo são iguais.

```yaml
perfil: padrao-sistema
camada: sistema
versao: 2
descricao: Perfil padrão do Orça.AI. As camadas seguintes declaram só o que muda.

fontes:
  fontes_por_cotacao: 3                    # D-10
  lojas_virtuais: permitidas               # D-11
  validade_dias: 180                       # D-12
  aviso_vencimento_dias: 30
  cnpjs_distintos_na_cotacao: true         # P-03
  marketplace:                             # D-16
    permitido: true
    cnpj_considerado: vendedor
    um_vendedor_por_orcamento_comparativo: true
    descartar_sem_cnpj_vendedor: true
  fontes_alternativas:                     # D-18
    atas_registro_preco: false
    painel_de_precos: false
    caged: false
    convencao_coletiva: false

preco_referencia:                          # D-15, D-60 a D-63
  frete: excluir
  desconto_pix: usar                       # D-60 (revista em 24/09/2026): Pix; sem Pix, boleto; nunca parcelado
  cupom: ignorar                           # D-61
  clube_assinatura_ou_login: ignorar       # D-61
  promocao_aberta_a_todos: usar            # D-62 — vale o preço atual ("por")
  preco_por_quantidade: ignorar            # D-63 — sempre o preço unitário
  cep: do_projeto                          # ou um CEP fixo, ex.: "03977-015"

produto:
  equivalencia: mesma_marca_modelo_apresentacao   # D-17 | mesmo_ean
  exige_ean_igual: false                           # true = só 🟢 com EAN igual
  atributos_criticos: catalogos/atributos.yaml     # ver §3

evidencia:
  por_fonte: [pdf, png, html]              # o PDF é obrigatório (D-13)
  cabecalho_pdf: [url, data_hora, cep, sha256]
  pdf_por_cotacao: true
  comprovante_receita: obrigatorio         # D-13
  reaproveitar_comprovante_dias: 30        # D-14
  cnpj_ativo_obrigatorio: true

cnpj:
  provedores: [opencnpj, brasilapi]
  aceita_alfanumerico: true                # D-19

calculo:
  base_preco_final: B                      # D-20 — A: média arredondada | B: loja de menor total
  arredondamento: comercial                # D-21
  casas_decimais: 2
  comparar_com: media_exata                # P-02 — media_exata | media_exibida
  misturar_lojas_no_final: false           # D-22
  resolucao_item_acima_da_media: [trocar_produto, trocar_loja]   # D-23 — o usuário escolhe
  lotes_dentro_do_orcamento: permitido     # D-24
  comparativos_usam_quantidades_finais: true   # D-25
  orcamento_1: menor_total                 # D-26

teto:
  nivel: projeto                           # D-30
  exato: true
  limites_por_orcamento: {}                # ex.: {"Mão de obra": {max_percentual: 70}}

otimizacao:                                # D-32 — margens em percentual inteiro
  margem_quantidade: {min_percentual: -20, max_percentual: 20}
  margem_horas: {min_percentual: -20, max_percentual: 20}
  meses: definidos_pelo_usuario
  manter_loja_escolhida_menor_total: true  # C3
  manter_classificacao: true               # C4
  objetivo: [menos_linhas_alteradas, menor_desvio_relativo]

mao_de_obra:
  fontes_por_cotacao: 3                    # D-40
  valor_referencia: media                  # D-41
  divisor: jornada_semanal_x5              # D-42
  tabela_jornadas: catalogos/jornadas.yaml # ver §2
  sequencia_arredondamento: [media, valor_hora, valor_mensal]   # D-43
  horas_casas_decimais: 2
  encargos: false                          # D-44
  regime_padrao: [mei_se_permitido, recibo]   # D-45
  formula_por_regime: {mei: padrao, recibo: padrao, clt: padrao}
  faixa_salarial: menor_valor              # D-46
  vaga_sem_salario: descartar
  empresa_nao_identificada: descartar
  empresas_distintas_na_cotacao: true      # P-04
  mesmo_municipio: false                   # D-47
  idade_maxima_vaga_dias: null
  escolha: tres_menores_salarios           # D-48
  plataformas: [catho, indeed, infojobs, vagas_com, google_jobs, linkedin_assistido]

desembolso:
  padrao: parcela_unica_mes_1              # P-06 | conforme_cronograma

automacao:                                 # §4 — automatico | com_aprovacao | manual
  correspondencia_ean: automatico
  correspondencia_atributos: com_aprovacao
  ia_rebaixa_correspondencia: automatico
  promover_amarelo_para_verde: manual      # sempre manual (princípio 4)
  escolher_lojas: automatico
  resolver_item_acima_da_media: com_aprovacao   # nunca automático (D-23)
  bloquear_cnpj_inativo: automatico
  descartar_vaga_duplicada_clara: automatico
  descartar_vaga_duplicada_incerta: com_aprovacao
  sugerir_quantidade_horas_cargo: com_aprovacao
  refazer_pesquisa_vencida: com_aprovacao
  otimizar_teto: com_aprovacao
  perfil_do_edital: manual                 # sempre manual
  aprovacao_final: manual                  # sempre manual
```

**Como as camadas se somam** (ordem: sistema → OSC → secretaria/edital → projeto → orçamento, cada nível no máximo uma vez):
- grupos de chaves são somados; listas e valores simples **substituem** o anterior; um grupo vazio (`{}`) limpa o grupo;
- o sistema registra **de qual camada veio cada regra** e grava a impressão digital (SHA-256) do perfil completo em cada cálculo;
- **números decimais não são aceitos** nas regras (evita arredondamentos escondidos): percentuais são inteiros (`-20`, não `-0.20`);
- chaves desconhecidas e valores fora das opções geram erro em português, com o nome da camada responsável.

**Opções ainda fixas:** algumas chaves aceitam hoje só o valor padrão, porque a alternativa ainda não foi implementada (ex.: `teto.exato`, `calculo.misturar_lojas_no_final`, `mao_de_obra.encargos`, `mao_de_obra.faixa_salarial`, `preco_referencia.preco_por_quantidade`). Mudar isso exige decisão registrada em [01](01-decisoes.md) e implementação.

**Travas dos princípios** (nenhuma camada muda): `automacao.promover_amarelo_para_verde`, `automacao.perfil_do_edital` e `automacao.aprovacao_final` são sempre `manual`; `automacao.resolver_item_acima_da_media` nunca é `automatico`; o PDF da página e, no cabeçalho, URL e data/hora são obrigatórios na evidência.

## 2. Tabela de jornadas (divisor mensal = jornada semanal × 5)

**Revisada e aprovada pelo usuário em 23/09/2026.** Versão em dados: [`catalogos/jornadas.yaml`](../catalogos/jornadas.yaml). Cada nova linha ou alteração precisa de nova revisão (o sistema registra quem revisou e quando). Profissões fora da tabela usam a regra geral e geram alerta 🟡.

| Enquadramento | Exemplos | Jornada semanal máxima | Divisor | Fonte legal |
|---|---|---|---|---|
| Regra geral | coordenador(a), orientador(a) ou educador(a) social, oficineiro(a), auxiliar administrativo, auxiliar de serviços gerais, cozinheiro(a), designer, pedagogo(a), nutricionista, psicólogo(a)¹, enfermeiro(a)¹ | 44 h | 220 | Constituição, art. 7º, XIII; CLT, art. 58 |
| Assistente social | — | 30 h | 150 | Lei 8.662/1993, art. 5º-A (incluído pela Lei 12.317/2010) |
| Fisioterapeuta; terapeuta ocupacional | — | 30 h | 150 | Lei 8.856/1994 |
| Técnico(a) em radiologia | — | 24 h | 120 | Lei 7.394/1985, art. 14 |
| Jornalista | — | 5 h/dia (30 h) | 150 | CLT, art. 303 |
| Telefonista; operador(a) de telemarketing | — | 6 h/dia (36 h) | 180 | CLT, art. 227; NR-17, Anexo II |

¹ Sem lei federal que fixe jornada menor (há projetos de lei em tramitação). Revisar se a situação mudar.

Profissões com regra controversa (ex.: médico, advogado empregado) ficam **fora** da tabela inicial até revisão.

## 3. Atributos críticos por categoria

Além de **marca, modelo e apresentação** (sempre obrigatórios, D-17):

```yaml
papel:        [formato, gramatura, folhas_por_pacote, cor]
caneta:       [cor, espessura_ponta, unidades_por_embalagem, tipo]
papelaria:    [dimensoes, unidades_por_embalagem, cor]
alimento:     [peso_ou_volume_liquido, tipo, sabor]
bebida:       [volume, tipo, sabor]
limpeza:      [peso_ou_volume_liquido, tipo, concentracao, fragrancia]
higiene:      [comprimento, unidades_por_embalagem, dimensoes, tipo, fragrancia]
descartavel:  [capacidade, unidades_por_embalagem, dimensoes, cor, tipo]
eletronico:   [modelo_exato, voltagem]
servico:      [escopo, periodicidade, unidade_de_cobranca]
```

Ajustes da etapa 7, a partir de 921 produtos reais do Atacadão: limpeza usa peso **ou** volume (sabão em pó vem em kg) e ganhou o tipo (líquido, pó, gel…); papel ganhou a cor; descartável ganhou medidas (guardanapo) e cor (copo branco × transparente); nova categoria higiene (papel higiênico: metragem, rolos, folha simples/dupla/tripla).

Os atributos de texto têm um **vocabulário** no mesmo arquivo: grupos de valores que se excluem, cada um com os seus sinônimos (ex.: torra do café: tradicional, extra forte, suave…; fragrâncias; cores; formatos de massa). Características independentes (orgânico, zero lactose, sem açúcar…) ficam cada uma no seu grupo. Atributos sem leitor nem vocabulário (escopo e periodicidade de serviços, modelo exato de eletrônico) são conferidos por uma pessoa, a menos que o item traga o valor e ele apareça na página.

O catálogo pode ser ampliado pelo usuário e compartilhado. Toda mudança nele é conferida pelo caso T-11 ([06](06-roadmap-e-testes.md)).

## 4. Níveis de automação padrão

No perfil de regras: grupo `automacao` (valores `automatico`, `com_aprovacao`, `manual`).

| Ação | Nível padrão |
|---|---|
| Correspondência por EAN igual | Automático |
| Correspondência por atributos (todos presentes e iguais) | Automático com aprovação |
| IA rebaixa uma correspondência | Automático |
| Promover 🟡 para 🟢 | Manual |
| Classificar lojas e escolher trio e loja do Orçamento 1 | Automático (com justificativa) |
| Resolver item acima da média (troca de produto ou de loja) | Automático com aprovação: o sistema calcula as opções, o usuário escolhe |
| Bloquear fonte com CNPJ não ativo | Automático |
| Descartar vaga duplicada (casos claros) | Automático |
| Descartar vaga duplicada (casos incertos) | Automático com aprovação |
| Sugerir quantidade, horas ou enquadramento de cargo | Automático com aprovação |
| Refazer pesquisa vencida | Automático com aprovação |
| Otimizar para fechar o teto | Automático com aprovação |
| Perfil de regras sugerido a partir do edital | Manual (confirmação regra a regra) |
| Aprovação final do orçamento | Manual |

## 5. MEI

- Regime padrão do cargo: **MEI, se a ocupação for permitida**; senão **Recibo (RPA)** (D-45).
- A lista de ocupações permitidas vem da Resolução CGSN nº 140/2018, Anexo XI, importada como tabela (`catalogos/ocupacoes_mei.csv`) e atualizável.
- Profissões regulamentadas de natureza intelectual (ex.: assistente social, psicólogo) não são permitidas ao MEI. O sistema usa Recibo e avisa.
- Aviso fixo na memória de cálculo: contratar por Recibo ou MEI uma função contínua, com horário fixo, pode caracterizar vínculo de emprego. Recomenda-se confirmar com a contabilidade da OSC.
