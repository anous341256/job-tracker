$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$client = Join-Path $projectRoot ".local\mysql-8.4.10-winx64\bin\mysqladmin.exe"
$passwordFile = Join-Path $projectRoot ".local\mysql-client.ini"

& $client "--defaults-extra-file=$passwordFile" shutdown
Write-Host "MySQL stopped."

