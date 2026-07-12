$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
& (Join-Path $projectRoot '.venv\Scripts\celery.exe') -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
