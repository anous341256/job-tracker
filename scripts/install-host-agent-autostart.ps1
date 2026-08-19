$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'start-host-agent.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName 'JobTrackerHostAgent' -Action $action -Trigger $trigger -Description 'Job Tracker local Outlook and Ollama companion' -Force | Out-Null
Write-Host 'Job Tracker Host Agent autostart has been configured for the current user.'
