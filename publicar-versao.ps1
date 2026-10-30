# Lança uma versão nova: confere privacidade, atualiza versao.txt e CHANGELOG, faz push e cria o Release com o zip.
# Rode: powershell -ExecutionPolicy Bypass -File publicar-versao.ps1 -Versao 1.1.0 -Notas "O que mudou; outra mudança"
# As instalações recebem o aviso no Telegram no dia seguinte (ou na hora, com /atualizar).
param(
  [Parameter(Mandatory = $true)][string]$Versao,
  [Parameter(Mandatory = $true)][string]$Notas
)
$ErrorActionPreference = "Continue"  # git escreve avisos no stderr; o código de saída é que decide
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir
function Checar($passo) { if ($LASTEXITCODE -ne 0) { throw "falhou: $passo" } }

if ($Versao -notmatch '^\d+\.\d+\.\d+$') { throw "use o formato 1.2.3" }
$atual = (Get-Content "$dir\versao.txt" -TotalCount 1).Trim()
if ([version]$Versao -le [version]$atual) { throw "a versão $Versao não é maior que a atual ($atual)" }

# 1. Privacidade: termos pessoais ficam num arquivo local, fora do repositório (.verificar-privado.txt, um por linha)
$lista = Join-Path $dir ".verificar-privado.txt"
if (Test-Path $lista) {
  $padroes = Get-Content $lista -Encoding UTF8 | Where-Object { $_.Trim() }
  $achados = git ls-files --cached --others --exclude-standard | ForEach-Object {
    Select-String -Path $_ -Pattern $padroes -SimpleMatch -Encoding UTF8
  }
  if ($achados) { $achados | Out-Host; throw "dados pessoais encontrados nos arquivos acima; nada foi publicado" }
  Write-Output "privacidade: ok"
} else { Write-Warning "sem .verificar-privado.txt: pulei a conferência de dados pessoais" }

# 2. Versão e histórico
[IO.File]::WriteAllText("$dir\versao.txt", "$Versao`n")
$itens = ($Notas -split ";" | ForEach-Object { "- " + $_.Trim() }) -join "`n"
$hist = [IO.File]::ReadAllText("$dir\CHANGELOG.md")
$hist = $hist -replace "^(# .+?\r?\n)", "`$1`n## $Versao · $(Get-Date -Format yyyy-MM-dd)`n$itens`n"
[IO.File]::WriteAllText("$dir\CHANGELOG.md", $hist)

# 3. Commit e push
git add -A; Checar "git add"
git commit -m "Versão $Versao"; Checar "git commit"
git push; Checar "git push"

# 4. Pacote e Release
& powershell -NoProfile -ExecutionPolicy Bypass -File "$dir\empacotar.ps1"; Checar "empacotar"
$zip = Join-Path (Split-Path -Parent $dir) "robo-linkedin.zip"
gh release create "v$Versao" $zip --title "Versão $Versao" --notes ($Notas -split ";" | ForEach-Object { "- " + $_.Trim() } | Out-String)
Checar "gh release create"
Write-Output "publicada: v$Versao"
