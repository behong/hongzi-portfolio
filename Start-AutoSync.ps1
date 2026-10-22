[CmdletBinding()]
param([switch]$Install, [switch]$Stop, [switch]$Status)

$ErrorActionPreference = 'Stop'
$taskName = 'Hongzi-Portfolio-AutoSync'
$scriptPath = Join-Path $PSScriptRoot 'AutoSync.py'
$runtimePath = Join-Path $PSScriptRoot '.tools\autosync'
$processFile = Join-Path $runtimePath 'process.json'
$watcherProcess = $null
if (Test-Path -LiteralPath $processFile) {
    $record = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$record.pid)" -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.CommandLine -and $candidate.CommandLine.Contains($scriptPath)) {
        $watcherProcess = $candidate
    }
}

if ($Status) {
    if ($watcherProcess) { Write-Host "Auto sync running. PID: $($watcherProcess.ProcessId)" }
    else { Write-Host 'Auto sync is stopped.' }
    if (Test-Path -LiteralPath (Join-Path $runtimePath 'state.json')) {
        $state = Get-Content -LiteralPath (Join-Path $runtimePath 'state.json') -Raw | ConvertFrom-Json
        Write-Host "Last synced commit: $($state.commit)"
    }
    Write-Host "Log: $runtimePath\watcher.log"
    return
}
if ($Stop) {
    if ($watcherProcess) { Stop-Process -Id $watcherProcess.ProcessId }
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    Write-Host 'Auto sync stopped; logon task removed if present.'
    return
}

$pythonPath = (& python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Python 3.9 or newer is required.' }
$pythonWindowless = Join-Path (Split-Path $pythonPath) 'pythonw.exe'
if (Test-Path -LiteralPath $pythonWindowless) { $pythonPath = $pythonWindowless }
$arguments = '"' + $scriptPath + '" --interval 60'
if ($Install) {
    $userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userName
    $principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    try {
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Sync hongzi portfolio from GitHub every 60 seconds.' -Force | Out-Null
        Write-Host 'Logon auto-start installed.'
    } catch {
        Write-Warning "Could not install logon task: $($_.Exception.Message). Run this script with -Install from your normal PowerShell."
    }
}
if (-not $watcherProcess) {
    $process = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
    Write-Host "Auto sync launched. PID: $($process.Id)"
} else {
    Write-Host "Auto sync already running. PID: $($watcherProcess.ProcessId)"
}
Write-Host "Log: $runtimePath\watcher.log"
