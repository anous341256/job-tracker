$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$state = Join-Path $root '.local\host-agent'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$token = Join-Path $state 'token'
if (-not (Test-Path $token)) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  [Convert]::ToBase64String($bytes) | Set-Content -NoNewline -Encoding ascii $token
}

# Ollama is kept entirely under the project directory. Start it before the
# agent so local AI tasks recover automatically after a Windows login or
# reboot. Outlook relay remains available even when Ollama cannot start.
$ollamaScript = Join-Path $PSScriptRoot 'start-ollama.ps1'
if (Test-Path -LiteralPath $ollamaScript) {
  try {
    & $ollamaScript
  } catch {
    Write-Warning "Ollama could not be started; Outlook relay will continue: $($_.Exception.Message)"
  }
}

& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'host_agent.py')
