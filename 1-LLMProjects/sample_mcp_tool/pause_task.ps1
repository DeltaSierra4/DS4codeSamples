# pause_task.ps1
# Disables the daily 9 AM digest task so it stops firing.
# The task definition is kept intact — run schedule_task.ps1 to re-enable it.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File pause_task.ps1

$ErrorActionPreference = "Stop"

$TaskName = "DigestWatcher-DailyDigest"
$TaskPath = "\"

$task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue

if (-not $task) {
    Write-Host "Task '$TaskName' not found — nothing to pause."
    exit 0
}

if ($task.Settings.Enabled -eq $false) {
    Write-Host "Task is already paused."
    exit 0
}

Disable-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Out-Null

Write-Host ""
Write-Host "Task paused: $TaskPath$TaskName  (will not fire at 9:00 AM until re-enabled)"
Write-Host "To resume:   powershell -ExecutionPolicy Bypass -File schedule_task.ps1"
Write-Host ""