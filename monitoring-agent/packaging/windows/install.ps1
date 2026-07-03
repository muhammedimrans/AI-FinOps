# COSTORAH Monitoring Agent — Windows installer.
#
# Installs costorah-agent into a per-user virtualenv under
# %ProgramData%\costorah-agent, writes a default config, and registers a
# Scheduled Task that runs the agent at startup (a lightweight
# always-available alternative to a native Windows Service, which would
# require a separate service wrapper such as NSSM — documented in
# docs/DEPLOYMENT.md as a supported alternative for production fleets
# that need service-manager integration, e.g. auto-restart-on-crash
# policies configured centrally).
#
# Usage (run as Administrator):
#   powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

$InstallDir = "$env:ProgramData\costorah-agent"
$ConfigDir  = "$InstallDir\config"
$RepoRoot   = Resolve-Path "$PSScriptRoot\..\.."

Write-Host "==> Checking for Python 3.12+"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python 3.12+ is required but was not found on PATH."
    exit 1
}

Write-Host "==> Installing to $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

python -m venv "$InstallDir\.venv"
& "$InstallDir\.venv\Scripts\pip.exe" install --quiet --upgrade pip
& "$InstallDir\.venv\Scripts\pip.exe" install --quiet "$RepoRoot"

if (-not (Test-Path "$ConfigDir\config.yaml")) {
    Copy-Item "$RepoRoot\config.example.yaml" "$ConfigDir\config.yaml"
    Write-Host "    Wrote default config to $ConfigDir\config.yaml — edit it and set organization.api_key"
}

Write-Host "==> Registering Scheduled Task 'CostorahAgent' (runs at startup)"
$action = New-ScheduledTaskAction -Execute "$InstallDir\.venv\Scripts\costorah-agent.exe" `
    -Argument "start --config `"$ConfigDir\config.yaml`"" `
    -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -Restart -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "CostorahAgent" -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host ""
Write-Host "Installed. Next steps:"
Write-Host "  1. Edit $ConfigDir\config.yaml and set organization.api_key"
Write-Host "  2. Start-ScheduledTask -TaskName CostorahAgent"
Write-Host "  3. Invoke-WebRequest http://127.0.0.1:9091/health"
