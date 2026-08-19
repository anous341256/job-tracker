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

function Test-OllamaHealth {
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-OllamaHealth)) {
    Start-Process -FilePath $exe -ArgumentList 'serve' -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-OllamaHealth) {
            $ready = $true
            break
        }
    }
    if (-not $ready) { throw 'Ollama did not become ready on port 11434.' }
}

$modelNames = (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5).models.name
if ($modelNames -notcontains 'qwen3:8b') {
    Write-Warning 'Ollama is running, but qwen3:8b is not available.'
} else {
    Write-Host 'Ollama and qwen3:8b are ready at http://127.0.0.1:11434.'
}
Write-Host 'All Ollama data remains under the project .local directory.'
