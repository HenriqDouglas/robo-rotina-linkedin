# Robô da Rotina LinkedIn

Assistente que roda no seu Windows e, nos horários da rotina, manda no Telegram o que fazer no LinkedIn para quem está buscando emprego:
- posts para curtir;
- comentários prontos, em tom de conversa;
- recrutadores e pessoas da área para conectar;
- mensagens para responder;
- o post da semana.

**Ele nunca age no LinkedIn sozinho**: só lê e sugere. Curtir, comentar, convidar e publicar é sempre com você.

## Instalar
1. Baixe **[robo-linkedin.zip](https://github.com/HenriqDouglas/robo-rotina-linkedin/releases/latest/download/robo-linkedin.zip)** e descompacte numa pasta fixa.
2. Dê duplo clique em `INSTALAR.cmd` e siga o [GUIA.md](GUIA.md).

Você vai precisar de:
- Windows 10 ou 11;
- Google Chrome;
- conta Claude Pro ou Max;
- Telegram;
- conta grátis no Apify.

## Atualizar
O bot avisa no Telegram quando sai versão nova, com o botão **⬆️ Atualizar**. Você também pode mandar `/atualizar` a qualquer momento. Seus dados e configurações são mantidos.

Histórico de versões: [CHANGELOG.md](CHANGELOG.md).

## Créditos
Os modelos de comentário, as fórmulas de gancho e as regras de voz em `prompts/ref/` vêm de [sergebulaev/linkedin-skills](https://github.com/sergebulaev/linkedin-skills) (licença MIT).
