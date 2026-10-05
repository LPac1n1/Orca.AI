# Como criar a chave gratuita do Google Gemini (≈ 5 minutos)

A chave é uma "senha" que permite ao sistema de orçamentos consultar a IA do Google. **É gratuita**: a camada sem custo não pede cartão de crédito.

## Parte 1 — Criar a chave

1. No navegador, abra **https://aistudio.google.com/apikey** e entre com uma conta Google. Pode ser a da OSC.
2. Se for o primeiro acesso, leia e aceite os termos de uso do Google AI Studio.
3. Clique em **"Criar chave de API"** (em inglês, *"Create API key"*).
   - Se o site pedir um projeto, escolha o projeto sugerido ou **"Criar projeto"**. Não é preciso ativar faturamento.
4. A chave aparece na tela. Clique em **copiar**.

## Parte 2 — Guardar a chave no computador (sem mostrar para ninguém)

5. No Windows, aperte a tecla **Windows** e digite **"variáveis de ambiente"**.
6. Abra **"Editar as variáveis de ambiente para sua conta"**.
7. Na parte de cima, **"Variáveis de usuário"**, clique em **"Novo..."**.
8. Preencha:
   - **Nome da variável:** `GEMINI_API_KEY`
   - **Valor da variável:** cole a chave (Ctrl+V)
9. Clique em **OK** e em **OK** de novo.
10. Me avise: **"criei a chave"**. **Não cole a chave no chat.** O sistema lê a chave direto do Windows, sem exibi-la.

## Cuidados

- **Não coloque a chave** em e-mail, WhatsApp, chat ou em arquivos da pasta do OneDrive.
- Se a chave vazar, volte em https://aistudio.google.com/apikey, **apague** a chave e crie outra (repita a Parte 2 com a nova).
- **Camada gratuita:** o Google pode usar o conteúdo das consultas para melhorar os produtos dele. O sistema envia **só dados públicos**: nomes de produtos anunciados em lojas e nomes de empresas de vagas. Nunca envia dados da OSC, de pessoas ou valores do projeto.
- **Limites diários:** a camada gratuita tem limite de consultas por minuto e por dia. O sistema consulta a IA **só nos casos de dúvida (🟡)** e espera quando o limite é atingido.

## O que a IA vai fazer no sistema

| Situação | Pergunta feita à IA | Quem decide |
|---|---|---|
| Mesmo produto sem código de barras em uma das lojas | "Estes dois anúncios são exatamente o mesmo produto?" | as regras primeiro; a IA só nos casos 🟡 |
| Troca por item "relacionado" | "Qual destes é o substituto mais razoável?" (ex.: geleia de outra fruta, e não de pimenta) | IA sugere; fica registrado e visível |
| CNPJ do empregador | "É plausível que esta empresa seja a empregadora desta vaga?" (ex.: loja de roupas × assistente social) | IA alerta; na dúvida, o sistema passa para a próxima vaga |

Cada resposta da IA fica registrada no histórico do orçamento, com a pergunta e o motivo.
