param(
  [Parameter(Mandatory = $true)]
  [string]$ServerUrl,
  [ValidateRange(2, 60)]
  [int]$PollSeconds = 3
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$state = Join-Path $root '.local\host-agent'
New-Item -ItemType Directory -Force -Path $state | Out-Null

$uri = [System.Uri]$ServerUrl
$isLocal = $uri.Host -in @('127.0.0.1', 'localhost', '::1')
if ($uri.Scheme -ne 'https' -and -not $isLocal) {
  throw 'Remote Job Tracker servers must use an https:// address.'
}

$token = Join-Path $state 'token'
if (-not (Test-Path $token)) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  [Convert]::ToBase64String($bytes) | Set-Content -NoNewline -Encoding ascii $token
}

@(
  "JOB_TRACKER_URL=$($ServerUrl.TrimEnd('/'))"
  "HOST_AGENT_POLL_SECONDS=$PollSeconds"
) | Set-Content -Encoding utf8 (Join-Path $state 'agent.env')

Write-Host 'Host Agent configuration saved under the project .local directory.'
Write-Host "Server: $($ServerUrl.TrimEnd('/'))"
Write-Host "Token file: $token"
Write-Host 'The server must use the same token as HOST_AGENT_TOKEN. Transfer it through a secure channel; do not commit it to Git.'
