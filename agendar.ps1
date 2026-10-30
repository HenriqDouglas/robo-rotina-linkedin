# Cria (ou recria) as tarefas do robô no Agendador do Windows. Rode: powershell -ExecutionPolicy Bypass -File agendar.ps1
# Para remover tudo: powershell -ExecutionPolicy Bypass -File agendar.ps1 -Remover
param([switch]$Remover)
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# pythonw roda sem janela; o próprio robô grava o log em logs\
$arqPy = Join-Path $dir "python.txt"
if (Test-Path $arqPy) { $py = (Get-Content $arqPy -TotalCount 1 -Encoding UTF8).Trim() }
else { $py = (Get-Command python).Source }
$pyw = Join-Path (Split-Path -Parent $py) "pythonw.exe"

# horários combinados: config.json (padrões) + dados\config-local.json (ajustes da pessoa)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$cfg = (& $py "$dir\robo.py" config) -join "" | ConvertFrom-Json
$h = $cfg.horarios

$tarefas = @(
  @{ nome = "curtir_comentar"; dias = "MON,TUE,WED,THU,FRI"; hora = $h.curtir_comentar },
  @{ nome = "conectar";        dias = "MON,TUE,WED,THU,FRI"; hora = $h.conectar },
  @{ nome = "responder";       dias = "MON,TUE,WED,THU,FRI"; hora = $h.responder },
  @{ nome = "publicar";        dias = $h.publicar_dias;      hora = $h.publicar },
  @{ nome = "resumo";          dias = $h.resumo_dia;         hora = $h.resumo }
)
$conf = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2)
foreach ($t in $tarefas) {
  $tn = "RoboLinkedIn\$($t.nome)"
  schtasks /Delete /TN $tn /F 2>$null | Out-Null
  if (-not $Remover) {
    $cmd = "`"$pyw`" `"$dir\robo.py`" $($t.nome)"
    schtasks /Create /TN $tn /TR $cmd /SC WEEKLY /D $t.dias /ST $t.hora /F | Out-Null
    # PC desligado ou dormindo no horário: roda assim que ligar. Também roda na bateria (notebook).
    Set-ScheduledTask -TaskPath "\RoboLinkedIn\" -TaskName $t.nome -Settings $conf | Out-Null
    Write-Output "agendado: $tn  $($t.dias) $($t.hora)"
  } else { Write-Output "removido: $tn" }
}

# Ouvinte: confirma os botões e lê os comandos do Telegram na hora. A tarefa tenta ligá-lo a cada 10 minutos;
# se já estiver ligado, a cópia nova fecha sozinha.
$tn = "RoboLinkedIn\ouvinte"
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -like "*$dir*robo.py*escutar*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
schtasks /Delete /TN $tn /F 2>$null | Out-Null
if (-not $Remover) {
  $cmd = "`"$pyw`" `"$dir\robo.py`" escutar"
  schtasks /Create /TN $tn /TR $cmd /SC MINUTE /MO 10 /F | Out-Null
  # o ouvinte roda sem limite de tempo e também na bateria
  Set-ScheduledTask -TaskPath "\RoboLinkedIn\" -TaskName "ouvinte" -Settings (New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)) | Out-Null
  schtasks /Run /TN $tn | Out-Null
  Write-Output "agendado: $tn  a cada 10 min (liga o ouvinte se estiver desligado)"
} else {
  Write-Output "removido: $tn (ouvinte desligado)"
}
