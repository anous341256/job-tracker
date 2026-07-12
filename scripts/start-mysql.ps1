$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$mysqlHome = Join-Path $projectRoot ".local\mysql-8.4.10-winx64"
$configFile = Join-Path $projectRoot ".local\mysql.ini"
$server = Join-Path $mysqlHome "bin\mysqld.exe"
$pidFile = Join-Path $projectRoot ".local\mysql-data\mysql.pid"

if (Test-Path $pidFile) {
    $processId = Get-Content $pidFile -ErrorAction SilentlyContinue
    if ($processId -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
        Write-Host "MySQL is already running (PID $processId)."
        exit 0
    }
}

Start-Process -FilePath $server -ArgumentList "--defaults-file=`"$configFile`"" -WindowStyle Hidden
Write-Host "MySQL is starting on 127.0.0.1:3307."
