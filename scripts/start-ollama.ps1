$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$localRoot = Join-Path $projectRoot '.local'
$exe = Join-Path $localRoot 'ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw "Portable Ollama not found: $exe" }
$ollamaHome = Join-Path $localRoot 'ollama-home'
$models = Join-Path $localRoot 'ollama-models'
New-Item -ItemType Directory -Force -Path $ollamaHome,$models | Out-Null
$env:OLLAMA_MODELS = $models
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:HOME = $ollamaHome
$env:USERPROFILE = $ollamaHome
if (-not (Get-Process -Name ollama -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $exe -ArgumentList 'serve' -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden
}
Write-Host 'Ollama started with all persistent data under the project .local directory.'
