# Instalador do robô da rotina LinkedIn. Abra com duplo clique em INSTALAR.cmd.
# Pode rodar quantas vezes quiser: cada passo confere antes e pula o que já está pronto.
$ErrorActionPreference = "Continue"  # erros de programas externos são tratados pelo código de saída
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"  # mostra as instruções do robô na hora

function Titulo($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ok($t) { Write-Host "  OK: $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "  $t" -ForegroundColor Yellow }
function Pausa($t) { Write-Host ""; Read-Host "  $t (aperte Enter)" | Out-Null }
function AtualizarPath {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User") + ";$HOME\.local\bin"
}
function AcharPython {
  $teste = "import sys; assert sys.version_info >= (3, 10); print(sys.executable)"
  $exe = $null
  if (Get-Command py -ErrorAction SilentlyContinue) { $exe = & py -3 -c $teste 2>$null }
  if (-not $exe -and (Get-Command python -ErrorAction SilentlyContinue)) { $exe = & python -c $teste 2>$null }
  if ($exe -and (Test-Path "$exe".Trim())) { return "$exe".Trim() }
  return $null
}
function Robo { & $script:py "$dir\robo.py" @args | Out-Host; return $LASTEXITCODE }
function TemChave($k) { (Test-Path "$dir\.env") -and (Select-String -Path "$dir\.env" -Pattern "^$k=." -Quiet) }

Write-Host "Robô da rotina LinkedIn: instalação" -ForegroundColor Cyan
Write-Host "O robô só manda sugestões no Telegram. Curtir, comentar, conectar e publicar continuam com você."

# 1. Python
Titulo "1/7 Python"
$py = AcharPython
if (-not $py) {
  Aviso "Instalando o Python 3.12 (leva alguns minutos)..."
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements `
    --override "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1"
  AtualizarPath
  $py = AcharPython
  if (-not $py) { throw "Não consegui instalar o Python. Instale pelo site python.org (marque 'Add to PATH') e rode de novo." }
}
[IO.File]::WriteAllText("$dir\python.txt", $py)  # UTF-8 sem BOM: aceita nome de usuário com acento
& $py -m pip install --user --quiet --disable-pip-version-check -r "$dir\requirements.txt"
Ok "Python em $py"

# Segundo robô no mesmo PC: nome próprio para as tarefas, porta própria e um Chrome só dele
$outros = Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object { $_.TaskPath -like "\RoboLinkedIn*" -and $_.TaskName -eq "ouvinte" -and "$($_.Actions.Arguments)" -notlike "*$dir*" }
$local = "$dir\dados\config-local.json"
if ($outros -and -not ((Test-Path $local) -and (Select-String -Path $local -Pattern '"instancia"' -Quiet))) {
  Aviso "Já existe outro robô do LinkedIn neste computador. Este vai ter tarefas, ouvinte e Chrome separados."
  $nome = (Read-Host "  Um nome curto para este robô (ex.: maria)").Trim()
  if ((Robo instancia $nome) -ne 0) { throw "Não consegui separar este robô do outro." }
}
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$cfgAtual = (& $py "$dir\robo.py" config) -join "" | ConvertFrom-Json
$proprio = $cfgAtual.navegador -eq "proprio"
if ($proprio) { & $py -m pip install --user --quiet --disable-pip-version-check playwright }

# 2. Claude Code
Titulo "2/7 Claude Code"
AtualizarPath
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Aviso "Instalando o Claude Code..."
  Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
  AtualizarPath
}
if ((Robo checar claude) -ne 0) {
  Aviso "Falta entrar na sua conta Claude (precisa do plano Pro ou Max)."
  Aviso "Vai abrir uma janela do Claude Code: siga o login no navegador e, quando terminar, digite /exit nela."
  Start-Process -Wait powershell -ArgumentList "-Command", "claude"
  if ((Robo checar claude) -ne 0) { throw "O Claude Code ainda não respondeu. Veja o passo 2 do GUIA.md e rode de novo." }
}
Ok "Claude Code respondendo"

# 3. Chrome
if ($proprio) {
  Titulo "3/7 Chrome do robô (separado do seu)"
  if ((Robo checar chrome) -ne 0) {
    Aviso "Vai abrir um Chrome só deste robô. A pessoa dona da conta entra no LinkedIn dela nele (senha e código)."
    Aviso "Quando aparecer o feed do LinkedIn, a janela fecha sozinha."
    if ((Robo entrar) -ne 0) { throw "O login não terminou. Rode de novo." }
  }
  Ok "LinkedIn logado no Chrome do robô"
} else {
Titulo "3/7 Chrome com a extensão Claude"
if ((Robo checar chrome) -ne 0) {
  Aviso "1) No Chrome, instale a extensão 'Claude' (da Anthropic) e entre com a mesma conta Claude."
  Aviso "2) No mesmo Chrome, deixe o LinkedIn logado na sua conta."
  Start-Process "https://chromewebstore.google.com/search/claude%20anthropic"
  Pausa "Quando terminar"
  if ((Robo checar chrome) -ne 0) { throw "O Chrome ainda não respondeu. Veja o passo 3 do GUIA.md e rode de novo." }
}
Ok "Chrome conectado"
}

# 4. Telegram
Titulo "4/7 Telegram"
if (-not (TemChave "TELEGRAM_BOT_TOKEN")) {
  Aviso "Crie o seu bot no @BotFather (passo 4 do GUIA.md) e cole aqui o token que ele mandar."
  $tok = (Read-Host "  Token do bot").Trim()
  $tok | & $py "$dir\robo.py" definir TELEGRAM_BOT_TOKEN
}
if (-not (TemChave "TELEGRAM_CHAT_ID")) {
  if ((Robo vincular) -ne 0) { throw "Não recebi a mensagem no bot. Rode de novo e mande 'oi' para o bot." }
}
Ok "Telegram conectado"

# 5. Apify
Titulo "5/7 Apify (busca de posts)"
if (-not (TemChave "APIFY_TOKEN")) {
  Aviso "Crie a conta grátis no Apify (passo 5 do GUIA.md) e cole aqui o seu API token."
  $tok = (Read-Host "  Token do Apify").Trim()
  $tok | & $py "$dir\robo.py" definir APIFY_TOKEN
}
if ((Robo checar apify) -ne 0) { throw "O Apify recusou o token. Confira o token no site e rode de novo." }
Ok "Apify respondendo"

# 6. Personalização
Titulo "6/7 Seu perfil"
if (-not (Test-Path "$dir\dados\perfil.json")) {
  Aviso "Agora a conversa continua no Telegram: mande o link do seu perfil quando o bot pedir."
  Aviso "Deixe esta janela aberta até o bot dizer que a configuração foi salva."
  if ((Robo configurar) -ne 0) { throw "A configuração parou no meio. Rode o instalador de novo para recomeçar." }
}
Ok "Perfil configurado"

# 7. Agendamento
Titulo "7/7 Horários"
& powershell -ExecutionPolicy Bypass -File "$dir\agendar.ps1"
Robo pronto | Out-Null
Write-Host ""
Write-Host "Instalação concluída. Pode fechar esta janela." -ForegroundColor Green
