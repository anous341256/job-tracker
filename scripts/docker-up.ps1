$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".env.docker")) {
    Copy-Item ".env.docker.example" ".env.docker"
    Write-Host "Created .env.docker from .env.docker.example. You can edit it before the next run."
}

docker compose up --build
