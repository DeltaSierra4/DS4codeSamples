 # schedule_task.ps1
# Registers the daily 9 AM digest task — or unpauses it if it already exists
# but is currently disabled (i.e. pause_task.ps1 was run previously).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File schedule_task.ps1

$ErrorActionPreference = "Stop"

$TaskName   = "DigestWatcher-DailyDigest"
$TaskPath   = "\"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe  = (Get-Command python -ErrorAction Stop).Source
$ScriptFile = Join-Path $ScriptDir "digest_watcher.py"

if (-not (Test-Path $ScriptFile)) {
    Write-Error "digest_watcher.py not found at $ScriptFile"; exit 1
}

# Check if the task already exists
$existing = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue

if ($existing) {
    if ($existing.Settings.Enabled -eq $false) {
        # Task exists but was paused — just re-enable it
        Enable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null
        Write-Host ""
        Write-Host "Task unpaused: $TaskPath$TaskName  (will run again at 9:00 AM)"
    } else {
        Write-Host ""
        Write-Host "Task is already registered and running: $TaskPath$TaskName"
    }
} else {
    # Task does not exist — create it
    $action   = New-ScheduledTaskAction `
                    -Execute $PythonExe `
                    -Argument "`"$ScriptFile`"" `
                    -WorkingDirectory $ScriptDir

    $trigger  = New-ScheduledTaskTrigger -Daily -At "9:00AM"

    $settings = New-ScheduledTaskSettingsSet `
                    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
                    -StartWhenAvailable `
                    -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName   $TaskName `
        -TaskPath   $TaskPath `
        -Action     $action `
        -Trigger    $trigger `
        -Settings   $settings `
        -Force | Out-Null

    Write-Host ""
    Write-Host "Task registered: $TaskPath$TaskName  (runs daily at 9:00 AM)"
}

Write-Host ""
Write-Host "To pause:        powershell -ExecutionPolicy Bypass -File pause_task.ps1"
Write-Host "To test now:     python `"$ScriptFile`""
Write-Host "To view in UI:   taskschd.msc  ->  Task Scheduler Library (root)"
Write-Host "To test immediately, run:"
Write-Host "  python `"$ScriptFile`""
Write-Host ""
Write-Host "To view/edit the task:"
Write-Host "  taskschd.msc  ->  Task Scheduler Library (root)"