# Gera robo-linkedin.zip (ao lado desta pasta) só com o que vai para outra pessoa: sem tokens, estado, logs nem dados pessoais.
# Rode: powershell -ExecutionPolicy Bypass -File empacotar.ps1  (o publicar-versao.ps1 já chama este script)
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$itens = @("robo.py", "telegram.py", "apify.py", "atualizar.py", "navegador.py", "ENTRAR-LINKEDIN.cmd", "config.json", "versao.txt", "requirements.txt",
           "agendar.ps1", "instalar.ps1", "INSTALAR.cmd", "ATUALIZAR.cmd", "GUIA.md", "ROTINA.md", "LEIA-ME.md",
           "CHANGELOG.md", "prompts")
$tmp = Join-Path $env:TEMP "robo-linkedin-pacote"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
$raiz = Join-Path $tmp "robo-linkedin"
New-Item -ItemType Directory -Force $raiz | Out-Null
foreach ($i in $itens) { Copy-Item (Join-Path $dir $i) $raiz -Recurse }
Get-ChildItem $raiz -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
New-Item -ItemType Directory -Force (Join-Path $raiz "dados"), (Join-Path $raiz "logs") | Out-Null
"" | Out-File (Join-Path $raiz "dados\.gitkeep"); "" | Out-File (Join-Path $raiz "logs\.gitkeep")
$zip = Join-Path (Split-Path -Parent $dir) "robo-linkedin.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $raiz -DestinationPath $zip
Remove-Item $tmp -Recurse -Force
Write-Output "pacote: $zip"
