# Guia de instalação: Robô da Rotina LinkedIn

O robô roda no seu computador e, nos horários da rotina, manda no seu Telegram **o que fazer** no LinkedIn: quais posts curtir, comentários prontos para copiar, pessoas para conectar, mensagens para responder e o post da semana.

**Ele nunca mexe no seu LinkedIn sozinho.** Curtir, comentar, convidar e publicar continuam sendo feitos por você, à mão. O robô só lê.

Tempo total: cerca de 40 minutos, uma vez só.

---

## O que você precisa

| Item | Para quê | Custo |
|---|---|---|
| Computador com Windows 10 ou 11 | Onde o robô roda | — |
| Google Chrome com o LinkedIn logado | O robô lê o seu perfil e a busca de pessoas | Grátis |
| Conta Claude (plano **Pro** ou **Max**) | A IA que escolhe os posts e escreve os textos | Assinatura do plano |
| Telegram no celular | Onde chegam as tarefas | Grátis |
| Conta Apify | Busca posts recentes no LinkedIn | Grátis (US$ 5/mês de crédito; o robô gasta ~US$ 4) |

---

## Passo a passo

### 1. Baixe e descompacte
Baixe a versão mais nova em https://github.com/HenriqDouglas/robo-rotina-linkedin/releases/latest/download/robo-linkedin.zip e descompacte numa pasta fixa, por exemplo `Documentos\robo-linkedin`. **Não apague nem mova a pasta depois**: o robô roda a partir dela.

### 2. Rode o instalador
Dê **duplo clique em `INSTALAR.cmd`**. Uma janela preta vai guiar você. Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.

O instalador faz tudo em 7 etapas e para quando precisar de você. Se algo falhar, ele diz o que fazer. Depois de resolver, é só rodar `INSTALAR.cmd` de novo: o que já está pronto ele pula.

Abaixo, o que você vai fazer em cada parada.

### Etapa 2 · Entrar na conta Claude
Abre uma janela do Claude Code. Siga o login que aparece (ele abre o navegador). Se ele perguntar se confia na pasta, responda que sim. Quando terminar, digite `/exit` e aperte Enter.

### Etapa 3 · Extensão Claude no Chrome
1. O instalador abre a loja do Chrome. Instale a extensão **Claude** (de Anthropic).
2. Clique no ícone da extensão e entre com a **mesma conta Claude** do passo anterior.
3. No mesmo Chrome, abra o LinkedIn e confirme que está logado na sua conta.
4. Volte à janela preta e aperte Enter.

### Etapa 4 · Criar o seu bot no Telegram
1. No Telegram, procure **@BotFather** (tem o selo azul) e toque em **Iniciar**.
2. Mande `/newbot`.
3. Escolha um nome (ex.: `Minha Rotina LinkedIn`) e depois um usuário terminado em `bot` (ex.: `rotina_linkedin_maria_bot`).
4. O BotFather responde com um **token** parecido com `1234567890:AAH...`. Copie e cole na janela preta.
5. Toque no link do seu bot (aparece na mensagem do BotFather), toque em **Iniciar** e mande `oi`. O instalador reconhece você sozinho.

> Guarde o token só para você. Quem tiver o token controla o bot.

### Etapa 5 · Conta no Apify
1. Crie a conta grátis em https://apify.com (pode entrar com o Google).
2. Vá em **Settings → API & Integrations** e copie o **Personal API token**.
3. Cole na janela preta.

### Etapa 6 · Personalização (no Telegram)
O bot pede o **link do seu perfil do LinkedIn**. Mande, por exemplo, `https://www.linkedin.com/in/seu-nome/`.

O robô lê o seu perfil no Chrome (só lê) e faz cerca de 10 perguntas:
- quais cargos você quer;
- em quais países e se aceita remoto;
- em que idioma quer comentar e publicar;
- seus resultados com números;
- como você quer (e não quer) soar;
- e o que faltar no seu perfil.

Responda com calma, do jeito que falaria.

No fim, ele mostra **as suas histórias** e um **resumo**. Responda `OK` para salvar, ou escreva o que quer mudar (ex.: "tire a história da empresa X", "quero focar em fintechs").

> O robô só usa números que estão nas suas histórias. Se algum estiver errado, corrija antes de responder OK.

### Etapa 7 · Horários
O instalador agenda tudo e o bot manda "Tudo pronto" com os horários. Pronto!

---

## O dia a dia

| Quando | O que chega no Telegram |
|---|---|
| Seg a sex 08:30 | 👍 10 posts para curtir + 💬 5 posts com 2 opções de comentário cada |
| Seg a sex 12:30 | 🤝 10 recrutadores + 10 pessoas da sua área para conectar |
| Seg a sex 18:00 | 📨 Lembrete de responder mensagens e convites, com modelos prontos |
| Ter e qui 07:45 | 📝 Post pronto: texto, primeiro comentário, ideia de imagem e horário |
| Sex 18:30 | 📊 Resumo da semana |

- Toque no texto do comentário para copiar e cole no LinkedIn.
- Em cada tarefa, toque em **✅ Feito** ou **⏭ Pular**. É assim que o resumo da semana é contado.
- O computador precisa estar **ligado, com a sua sessão do Windows aberta** nesses horários. Para a etapa de conectar, deixe o **Chrome aberto**.

### Comandos no Telegram
- `/pausar`: o robô para de mandar tarefas (por exemplo, nas férias).
- `/religar`: volta ao normal.
- `/configurar`: refaz a personalização (mudou de objetivo, idioma ou tem resultados novos).
- `/atualizar`: instala a versão mais nova do robô, se houver. `/versao`: mostra a versão instalada. `/ajuda`: lista os comandos.

### Mudar horários ou metas
Abra `dados\config-local.json` no Bloco de Notas e acrescente o que quer mudar, por exemplo:
`"horarios": {"curtir_comentar": "09:00"}` ou `"metas": {"comentar_por_dia": 3}` (o arquivo é JSON: mantenha as chaves `{ }` e as vírgulas).
Salve e rode no PowerShell, dentro da pasta: `powershell -ExecutionPolicy Bypass -File agendar.ps1`.
Não mexa no `config.json`: ele traz os padrões e é trocado nas atualizações.

### Atualizações
- Quando sair uma versão nova, o bot avisa uma vez com **🆕 Versão X disponível**, o que mudou e o botão **⬆️ Atualizar**. Toque e pronto: em cerca de 1 minuto chega **✅ Versão X ativa**.
- Quer conferir na hora? Mande `/atualizar`. Para ver a versão instalada, `/versao`.
- Sem Telegram? Dê duplo clique em `ATUALIZAR.cmd`.
- A atualização troca só o programa. Seus tokens, perfil, histórias, ajustes e histórico ficam como estão. Uma cópia da versão anterior fica na pasta `backup\`.

---

## Segurança
- O robô **nunca** clica, curte, comenta, convida, envia mensagem ou publica. Ele só lê páginas e manda sugestões para você.
- Se o LinkedIn mostrar captcha ou aviso de limite, o robô **se pausa sozinho** e avisa no Telegram. Confira o LinkedIn no navegador e mande `/religar` depois.
- Seus tokens ficam só no arquivo `.env` desta pasta. Não envie esse arquivo para ninguém.
- O bot só obedece ao seu chat do Telegram.

## Desinstalar
No PowerShell, dentro da pasta: `powershell -ExecutionPolicy Bypass -File agendar.ps1 -Remover`. Depois apague a pasta.

## Algo deu errado?
- Os registros ficam na pasta `logs\` (arquivo `robo-AAAA-MM.log`).
- Erros também chegam no Telegram, com ❌.
- Rodar `INSTALAR.cmd` de novo corrige a maioria dos problemas.

---
Créditos: modelos de comentário, fórmulas de gancho e regras de voz em `prompts\ref\` vêm de github.com/sergebulaev/linkedin-skills (licença MIT, ver `prompts\ref\LICENSE-linkedin-skills.txt`).
