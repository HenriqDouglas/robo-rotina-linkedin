# Robô da rotina LinkedIn → Telegram

Para instalar: veja **GUIA.md** e dê duplo clique em **INSTALAR.cmd**.

O robô varre posts (Apify) e pessoas (seu Chrome, só leitura) e manda no Telegram o que fazer. **Ele nunca curte, comenta, convida nem publica**: tudo isso é com você.

## Arquivos
- `robo.py`: o robô (`python robo.py <momento> [--dry-run]`).
- `config.json`: padrões (metas, horários, repositório de atualização). Vem nas atualizações; não edite.
- `dados/config-local.json`: ajustes da pessoa (temas da coleta, grupos de pessoas e o que quiser sobrescrever do `config.json`).
- `navegador.py` + `ENTRAR-LINKEDIN.cmd`: Chrome próprio do robô (`"navegador": "proprio"`), usado quando há mais de um robô no mesmo PC. A pasta `navegador/` guarda o login e nunca vai para o git.
- `atualizar.py` + `versao.txt`: atualização pelo GitHub Releases (`/atualizar` no Telegram ou `ATUALIZAR.cmd`).
- `dados/`: gerado na personalização. Contém `perfil.json`, `voice-profile.md` (sua voz), `story-bank.md` (suas histórias e números; o robô só usa números daqui) e `mensagens.json` (modelos pós-aceite). Pode editar à mão.
- `prompts/`: instruções da IA. `prompts/ref/` vem do linkedin-skills (MIT).
- `.env`: seus tokens (Telegram e Apify). Não compartilhe.
- `logs/`: registros.

## Comandos úteis (PowerShell, dentro da pasta)
- Testar um momento sem enviar: `python robo.py curtir_comentar --dry-run`
- Ver estado: `python robo.py status`
- Testes da instalação: `python robo.py checar claude|chrome|apify|telegram`
- Refazer a personalização: mande `/configurar` no Telegram
- Pausar: `/pausar` no Telegram (ou crie um arquivo vazio `PAUSADO` na pasta). Religar: `/religar`.
- Reagendar após mudar horários: `powershell -ExecutionPolicy Bypass -File agendar.ps1` · remover tudo: `... agendar.ps1 -Remover`

## Para quem mantém o código
- Repositório: https://github.com/HenriqDouglas/robo-rotina-linkedin
- Lançar versão: `powershell -ExecutionPolicy Bypass -File publicar-versao.ps1 -Versao 1.1.0 -Notas "mudança 1; mudança 2"`.
  Ele confere dados pessoais (lista local `.verificar-privado.txt`, fora do git), atualiza `versao.txt` e `CHANGELOG.md`, faz push e cria o Release com `robo-linkedin.zip`.
- Cada instalação recebe o aviso no dia seguinte, a partir das 9h, ou na hora com `/atualizar`.
- Nunca entram no repositório: `.env`, `dados/`, `estado.sqlite`, `logs/` (ver `.gitignore`).
