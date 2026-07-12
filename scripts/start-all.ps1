$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Virtual environment not found: $python" }

$mysqlScript = Join-Path $PSScriptRoot 'start-mysql.ps1'
if (Test-Path -LiteralPath $mysqlScript) { & powershell -ExecutionPolicy Bypass -File $mysqlScript }

Start-Process -FilePath $python -ArgumentList @('manage.py', 'runserver') -WorkingDirectory $projectRoot -WindowStyle Hidden
$redis = Get-Command redis-cli -ErrorAction SilentlyContinue
if ($redis -and (& $redis.Source ping 2>$null) -eq 'PONG') {
    $celery = Join-Path $projectRoot '.venv\Scripts\celery.exe'
    Start-Process -FilePath $celery -ArgumentList @('-A', 'config', 'worker', '--pool=solo', '--loglevel=info') -WorkingDirectory $projectRoot -WindowStyle Hidden
    Start-Process -FilePath $celery -ArgumentList @('-A', 'config', 'beat', '--loglevel=info', '--scheduler', 'django_celery_beat.schedulers:DatabaseScheduler') -WorkingDirectory $projectRoot -WindowStyle Hidden
    Write-Host 'Web, MySQL, Celery worker, and beat started.'
} else { Write-Host 'Web and MySQL started. Redis was not detected, so scheduled reminders were not started.' }
Write-Host 'Open http://127.0.0.1:8000/'
