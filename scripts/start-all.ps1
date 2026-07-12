$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$celery = Join-Path $projectRoot '.venv\Scripts\celery.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Virtual environment not found: $python" }

& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-mysql.ps1')
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-ollama.ps1')
Start-Process -FilePath $celery -ArgumentList @('-A', 'config', 'worker', '--pool=solo', '--loglevel=info') -WorkingDirectory $projectRoot -WindowStyle Hidden
Start-Process -FilePath $celery -ArgumentList @('-A', 'config', 'beat', '--loglevel=info', '--scheduler', 'django_celery_beat.schedulers:DatabaseScheduler') -WorkingDirectory $projectRoot -WindowStyle Hidden
Start-Process -FilePath $python -ArgumentList @('manage.py', 'runserver') -WorkingDirectory $projectRoot -WindowStyle Hidden
Write-Host 'MySQL, portable Ollama, Celery worker, beat, and Django started.'
Write-Host 'Open http://127.0.0.1:8000/'
