param(
    [switch]$Backup,
    [string]$HostName = 'root@5.231.230.25',
    [string]$BackupDir = "$PWD\backups",
    [switch]$SkipHealth
)

$ErrorActionPreference = 'Stop'
if ($HostName -notmatch '^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$') {
    throw 'Неверный SSH-адрес'
}
function Remote([string]$Script) {
    # HostName допускает только буквы, цифры и знаки из проверки выше, поэтому
    # строка аргументов безопасна и работает в Windows PowerShell 5.1 (.NET Framework).
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = 'ssh'
    $start.Arguments = "-o BatchMode=yes -o ConnectTimeout=10 $HostName bash -se"
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::Start($start)
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.Write($Script.Replace("`r`n", "`n").TrimEnd("`r", "`n") + "`n")
    $process.StandardInput.Close()
    $process.WaitForExit()
    if ($stderr.Result) { [Console]::Error.Write($stderr.Result) }
    if ($process.ExitCode -ne 0) {
        throw "Команда на сервере завершилась с кодом $($process.ExitCode)"
    }
    $stdout.Result.TrimEnd("`r", "`n")
}
if ($Backup) {
    $name = (Remote 'cd /opt/swarmlab/deploy; docker compose exec -T swarmlab python /app/tools/backup.py create /data /backups' | Select-Object -Last 1).Trim()
    if ($name -notmatch '^/backups/swarmlab-[0-9-]+\.tar\.gz$') { throw "Неожиданное имя бэкапа: $name" }
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $target = Join-Path $BackupDir ([System.IO.Path]::GetFileName($name))
    scp -o BatchMode=yes "${HostName}:/opt/swarmlab/backups/$([System.IO.Path]::GetFileName($name))" $target
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось скачать бэкап' }
    Write-Host "Бэкап скачан: $target"
    exit 0
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if ((git -C $repo branch --show-current) -ne 'master') { throw 'Локально нужна ветка master' }
if (git -C $repo status --porcelain) { throw 'Локально есть незакоммиченные изменения' }
$localSha = (git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $localSha -notmatch '^[0-9a-f]{40}$') { throw 'Не удалось определить локальный commit' }
Write-Host "Выкладка master $localSha на $HostName"
$script = @'
set -euo pipefail
if [ ! -d /opt/swarmlab/.git ]; then
  mkdir -p /opt/swarmlab
  git clone --branch master https://github.com/quatobyte/swarmlab.git /opt/swarmlab
fi
cd /opt/swarmlab
git fetch origin master
git checkout master
git pull --ff-only origin master
if [ "$(git rev-parse HEAD)" != '__EXPECTED_SHA__' ]; then
  echo 'origin/master не совпадает с локальным commit; отправьте master перед выкладкой' >&2
  exit 1
fi
install -d -m 700 -o 1000 -g 1000 data backups
if [ ! -f deploy/.env ]; then
  install -m 600 /dev/null deploy/.env
fi
chmod 600 deploy/.env
proxy_ip=$(docker inspect -f '{{(index .NetworkSettings.Networks "vaultwarden_default").IPAddress}}' caddy)
if [ -z "$proxy_ip" ]; then echo 'Caddy отсутствует в сети vaultwarden_default' >&2; exit 1; fi
printf 'proxy:\n  trusted: ["%s"]\ncookie:\n  secure: always\n' "$proxy_ip" > data/public.yaml
chown 1000:1000 data/public.yaml
cd deploy
docker compose up -d --build
docker compose ps
'@
$script = $script.Replace('__EXPECTED_SHA__', $localSha)
Remote $script
$deployedSha = (Remote 'git -C /opt/swarmlab rev-parse HEAD' | Select-Object -Last 1).Trim()
if ($deployedSha -ne $localSha) { throw "На сервере $deployedSha, локально $localSha. Сначала отправьте master в origin." }
if (-not $SkipHealth) {
    $health = (Remote 'curl --fail --silent --show-error --max-time 20 -o /dev/null -w "%{http_code}" https://swarmlab.kmashinist.ru/' | Select-Object -Last 1).Trim()
    if ($health -ne '200') { throw "HTTPS проверка вернула $health" }
}
Write-Host 'Выкладка завершена.'
