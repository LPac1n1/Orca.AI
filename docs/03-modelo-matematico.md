# 03 — Modelo matemático

Cálculos de cotação, mão de obra e a otimização que fecha o teto exato. Decisões citadas estão em [01](01-decisoes.md).

## 1. Unidades e exatidão

- **Dinheiro:** sempre em **centavos inteiros**. Nunca ponto flutuante.
- **Médias:** guardadas como **frações exatas** (ex.: 1.500.200/3 centavos). O arredondamento só acontece onde a regra manda.
- **Horas:** em **centésimos de hora** inteiros (91,50 h = 9.150).
- **Arredondamento comercial** (D-21), para valores positivos, com 2 casas:
  `R(x) = ⌊x · 100 + 0,5⌋ / 100`
  Pela terceira casa: 5 ou mais sobe; menos de 5 desce. R$ 15,556 → R$ 15,56; R$ 15,554 → R$ 15,55; R$ 2.079,795 → R$ 2.079,80.
- A média de 3 valores em centavos termina sempre em 0, 1/3 ou 2/3 de centavo. Por isso o caso "exatamente 5" nunca aparece nas médias de cotação, só em outras contas (ex.: mão de obra).

## 2. Cotação e preço final (materiais e serviços)

Para o item *i*, com preços `p_i1, p_i2, p_i3` (centavos) nas 3 fontes:

- Soma: `S_i = p_i1 + p_i2 + p_i3`
- Média exata: `M_i = S_i / 3` (fração)
- Média exibida na grade: `R(M_i)`

**Regra A:** preço final `u_i = R(M_i)`.

**Regra B:** preço final `u_i = p_i,E`, o preço na loja escolhida *E* (a de menor total do lote).
Conferência (P-02, média exata), feita só com inteiros, sem arredondar nada:

```
p_i,E ≤ M_i   ⇔   3 · p_i,E ≤ S_i
```

Se o perfil usar a média exibida (`comparar_com: media_exibida`): `p_i,E ≤ R(M_i)`.

**Atenção à média dos totais.** A grade mostra a média do preço unitário e a média do total de cada linha. Elas podem diferir em centavos do produto quantidade × média unitária. Exemplo com preços 7,95 / 8,60 / 6,90 e quantidade 2: média unitária 7,8166… → **7,82**; 2 × 7,82 = **15,64**; mas média dos totais = 46,90 ÷ 3 = 15,6333… → **15,63**. O plano de aplicação usa sempre `quantidade × preço final`, e a memória de cálculo explica a diferença.

## 3. Mão de obra

Para o cargo *r*, com salários `s_r1, s_r2, s_r3` (já com o menor valor da faixa, D-46):

| Etapa | Fórmula |
|---|---|
| Média | `m_r = R((s_r1 + s_r2 + s_r3) / 3)` |
| Divisor | `D_r = 5 × jornada semanal máxima legal` ([05 §2](05-regras-padrao.md)) |
| Valor-hora | `v_r = R(m_r / D_r)` |
| Valor mensal | `V_r = R(v_r × h_r)` — `h_r` = horas por mês, até 2 decimais |
| Total da linha | `T_r = V_r × meses_r × postos_r` |

**Exemplo** (regra geral, 44 h → divisor 220; 91,5 h/mês; 12 meses; 1 posto):

```
Salários:     R$ 4.001,00 · R$ 5.000,00 · R$ 6.001,00
Média:        R(15.002,00 / 3 = 5.000,6666…)   = R$ 5.000,67
Valor-hora:   R(5.000,67 / 220 = 22,730318…)  = R$ 22,73
Mensal:       R(22,73 × 91,5 = 2.079,795)      = R$ 2.079,80
Total:        2.079,80 × 12                     = R$ 24.957,60
```

O regime (MEI, Recibo, CLT) pode ter fórmula própria no perfil de regras (D-45). O padrão é a mesma fórmula para todos.

## 4. Otimização: fechar o teto exato

### 4.1 Dados

- `T`: teto do projeto em centavos.
- `F`: soma das linhas travadas (não otimizáveis).
- **Linhas de material/serviço** *i*: preço final `u_i`, meses `n_i`, quantidade planejada `q⁰_i`, limites `[qmin_i, qmax_i]` = `[⌈0,8·q⁰_i⌉, ⌊1,2·q⁰_i⌋]` (D-32) ou `q_i = q⁰_i` se travada.
- **Linhas de mão de obra** *r*: valor-hora `v_r` (centavos), meses `n_r`, postos `k_r`, horas planejadas `H⁰_r` (centésimos), limites `[⌈0,8·H⁰_r⌉, min(⌊1,2·H⁰_r⌋, 100·D_r)]`. O teto de `100·D_r` impede passar da jornada mensal legal.

Observação: com quantidade planejada 1, a margem de ±20% não deixa folga (o único inteiro possível é 1). O sistema avisa quando há poucas linhas com folga.

### 4.2 Variáveis

- `q_i` inteiro: quantidade por período.
- `H_r` inteiro: horas por mês, em centésimos.
- `V_r` inteiro: valor mensal do cargo, em centavos.

### 4.3 Restrições

**(C1) Arredondamento do valor mensal.** `V_r = ⌊(v_r · H_r + 50) / 100⌋`, escrito de forma linear:

```
100·V_r ≤ v_r·H_r + 50 ≤ 100·V_r + 99
```

**(C2) Teto exato.**

```
Σ_i u_i · q_i · n_i  +  Σ_r V_r · n_r · k_r  +  F  =  T
```

**(C3) Loja escolhida continua a de menor total (D-26).** Para cada lote com Regra B e trio {E, a, b}:

```
Σ_{i∈lote} q_i·n_i·p_i,E  ≤  Σ_{i∈lote} q_i·n_i·p_i,a
Σ_{i∈lote} q_i·n_i·p_i,E  ≤  Σ_{i∈lote} q_i·n_i·p_i,b
```

**(C4) Classificação continua valendo (P-05; padrão ligada, pode ser relaxada).** Para cada loja elegível *j* fora do trio, com todos os preços do lote conhecidos:

```
Σ q_i·n_i·p_i,j  ≥  Σ q_i·n_i·p_i,a     e     Σ q_i·n_i·p_i,j  ≥  Σ q_i·n_i·p_i,b
```

**(C5) Limites por rubrica (opcionais).** `Lmin_o ≤ Σ(linhas do orçamento o) ≤ Lmax_o`.

**(C6) Limites de cada variável** (§4.1).

Os preços `u_i`, `p_i,k` e `v_r` são **constantes**. O otimizador nunca os altera (D-31).

### 4.4 Objetivo (em ordem de prioridade)

1. Alterar **o menor número possível de linhas** (variável binária `z` por linha, ligada a `q_i ≠ q⁰_i` ou `H_r ≠ H⁰_r`).
2. Entre as soluções empatadas, o **menor desvio relativo total** em relação ao planejado.
3. **Prioridade do usuário:** o usuário pode indicar quais linhas preferir ajustar primeiro (pesos).

**Determinismo:** o otimizador roda com semente fixa e de forma reproduzível. A mesma entrada gera sempre a mesma saída.

### 4.5 Quando não há solução

O sistema nunca altera preços para fechar a conta. Ele identifica o motivo:

| Motivo | Como é detectado | Exemplo de mensagem |
|---|---|---|
| **Limites** | máximo possível < T, ou mínimo possível > T | "Mesmo com todas as quantidades e horas no máximo, o total é R$ 148.230,15, R$ 1.769,85 abaixo do teto." |
| **Divisibilidade** | o máximo divisor comum dos "passos" das linhas livres não divide o que falta | "Os itens livres custam múltiplos de R$ 2,50; não há como chegar a R$ 1.001,00." |
| **Conflito de regras** | cada grupo de restrições tem um marcador; o otimizador devolve o conjunto de grupos que não podem valer juntos | "A exigência de a Loja X continuar a mais barata (C3) conflita com a margem do item 7." |

Exemplo de divisibilidade: itens a R$ 12,50, R$ 7,50 e R$ 25,00, todos múltiplos de R$ 2,50. Teto de R$ 1.000,00 fecha (20 × 12,50 + 50 × 7,50 + 15 × 25,00). Teto de R$ 1.001,00 é impossível. Linhas de mão de obra com horas decimais costumam quebrar esse bloqueio, porque dão passos pequenos (valor-hora × 0,01 h).

**Sugestões:** o otimizador roda de novo relaxando um grupo de cada vez (ex.: margem do item 7 para ±30%, destravar uma linha, desligar C4, mudar o limite de uma rubrica) e informa a **menor mudança** que resolve. Também pode sugerir troca de produto ou de loja (D-23).

### 4.5.1 O que os testes mostraram
- **Com poucas linhas ajustáveis, o teto exato costuma ser impossível.** Preços com um divisor comum (ex.: todos múltiplos de R$ 2,50) só alcançam alguns totais. Mesmo a mão de obra, cujo valor mensal anda em passos de ~R$ 0,23, pode não acertar um centavo específico quando há só uma ou duas linhas livres. O otimizador demonstra isso e a força bruta confirma.
- **Com um projeto real, fecha rápido.** No plano real de 2026 (30 linhas de material em 5 lotes, 7 cargos, teto de R$ 150.000,00), o otimizador fecha o centavo em menos de 1 segundo — tanto com os divisores antigos (nenhuma alteração) quanto com o divisor legal (sobe horas e quantidades dentro dos ±20%).
- **Prioridade do usuário** (item 3 do §4.4): cada linha tem um `custo_alteracao` (padrão 1). Um custo maior faz o otimizador evitar mexer naquela linha.

### 4.6 Verificação independente

Depois de resolver, uma rotina separada e simples **recalcula tudo do zero**: médias, arredondamentos, valores mensais, totais, teto, C3, C4 e a conferência preço × média. O resultado precisa bater exatamente; se não bater, é erro e nada é exportado.

Ficam gravados (tabelas `execucao_otimizacao` e `linha_final`): entradas, impressão das regras, versão do otimizador, solução ou diagnóstico e resultado da verificação. As linhas finais só são gravadas se a verificação passou.

## 5. Algoritmo de escolha de lojas e resolução (Regra B)

```
para cada lote com Regra B:
    elegiveis ← lojas com todos os itens em 🟢, evidência válida e CNPJ ativo
    ordenar elegiveis por total (quantidades planejadas), desempate determinístico
    trio ← 3 primeiras;  E ← menor total do trio
    violacoes ← itens com 3·p(i,E) > S_i

    se violacoes vazio: seguir para a otimização

    opcoes ← []
    # Saída 1: trocar o produto (nas mesmas 3 lojas)
    para cada item v em violacoes:
        para cada alternativa a de v (mesma finalidade, atributos obrigatórios mantidos):
            cotar a nas 3 lojas do trio (correspondência 🟢 nas 3)
            se 3·p(a,E) ≤ S_a e E continua menor total: registrar opção
    # Saída 2: trocar a loja
    removidas ← [E] com motivo;  candidatas ← elegiveis sem removidas
    repetir:
        trio ← 3 primeiras de candidatas (pesquisar todos os itens na loja nova, se preciso)
        E ← menor total do trio;  violacoes ← itens com 3·p(i,E) > S_i
        se vazio: registrar opção (com a cadeia de tentativas); parar
        senão: removidas += E;  candidatas -= E
    até faltarem lojas

    apresentar opcoes ao usuário (efeito no total, lojas envolvidas, tentativas)
    aplicar a escolhida, registrar decisão, recalcular
```

Notas:
- As médias `S_i` mudam quando o trio muda; a conferência é sempre refeita com o trio atual.
- Na Saída 2, só sai do trio a loja escolhida em que houve violação. As outras nunca são trocadas para subir a média (D-27).
