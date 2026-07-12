$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
& (Join-Path $projectRoot '.venv\Scripts\celery.exe') -A config worker --pool=solo --loglevel=info
