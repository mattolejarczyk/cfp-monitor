<#
.SYNOPSIS
  OPERATOR-RUN. Registers the ONE-TIME Windows scheduled task 'CFP Saturday Patch Apply (one-time)': it applies the ACT-64 and ACT-63 patches by itself on Friday and e-mails you.

.DESCRIPTION
  From Friday 2026-10-16 10:00 it runs every 30 minutes until Saturday 2026-10-17 01:00 (the Saturday research job starts at 02:00):

      C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe C:\Users\matts\cfp-monitor\experiments\saturday_apply\auto_apply_saturday_patches.py

  Each run does ONE thing: if a CFP task is still running (Friday's awards research) it waits (and e-mails a reminder every 2 hours);
  the first time nothing is running it applies both patches (backups, parse check, byte-for-byte read-back, automatic restore) and e-mails you the result;
  after that it is silent. If the window closes unapplied it sends one final note. E-mail goes to CFP_RECAP_TO only (the operator).
  The task deletes itself a day after the window ends.

  Safe to try first:   .\register_saturday_patch_task.ps1 -WhatIf
  To register:         .\register_saturday_patch_task.ps1
  It REFUSES a second registration. To cancel: Unregister-ScheduledTask -TaskName 'CFP Saturday Patch Apply (one-time)' -Confirm:$false
  Settings are the other CFP tasks': the signed-in user, interactive, limited rights, StartWhenAvailable, WakeToRun OFF (the PC must be on and signed in), one instance at a time.
  Windows PowerShell 5.1. No administrator rights.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'CFP Saturday Patch Apply (one-time)',
    [string]$Repo     = 'C:\Users\matts\cfp-monitor',
    [datetime]$Start  = '2026-10-16 10:00',
    [datetime]$End    = '2026-10-17 01:05'
)

$ErrorActionPreference = 'Stop'
$py     = Join-Path $Repo '.venv\Scripts\python.exe'
$script = Join-Path $Repo 'experiments\saturday_apply\auto_apply_saturday_patches.py'

if (-not (Test-Path $py))     { Write-Host "REFUSED: the interpreter was not found: $py" -ForegroundColor Red; exit 2 }
if (-not (Test-Path $script)) { Write-Host "REFUSED: the script was not found: $script" -ForegroundColor Red; exit 2 }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "REFUSED: a task named '$TaskName' is already registered (state: $($existing.State)). Nothing was changed." -ForegroundColor Yellow
    Write-Host "  To replace it, delete it yourself first: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Yellow
    exit 1
}
if ($End -le (Get-Date)) { Write-Host "REFUSED: the window already ended ($End)." -ForegroundColor Red; exit 2 }

$argument = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$py' '$script'`""
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $Repo
$minutes  = [int](($End - $Start).TotalMinutes)
$trigger  = New-ScheduledTaskTrigger -Once -At $Start -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Minutes $minutes)
$trigger.EndBoundary = $End.ToString('s')
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -DeleteExpiredTaskAfter (New-TimeSpan -Days 1)
$settings.WakeToRun = $false
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Write-Host ""
Write-Host "Task      : $TaskName"
Write-Host "When      : every 30 minutes from $Start until $End (about $([int]($minutes / 30)) tries), then deletes itself a day later"
Write-Host "Runs      : powershell.exe $argument"
Write-Host "Start in  : $Repo"
Write-Host "Settings  : StartWhenAvailable, WakeToRun OFF (PC must be on and signed in), one instance, 20 minute limit, runs on battery"
Write-Host "Effect    : applies the ACT-64 and ACT-63 patches to Markets\run_overnight.ps1 and Markets\run_monthly.ps1 ONLY when no CFP task is running; backups first; e-mails the operator (CFP_RECAP_TO)"
Write-Host ""

if ($PSCmdlet.ShouldProcess($TaskName, "Register the one-time Saturday patch apply task")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'One-time: applies the ACT-64 and ACT-63 patches on Friday evening when no CFP task is running, with backups and a parse check, and e-mails the operator. Reminders while waiting. Deletes itself.' | Out-Null
    $t = Get-ScheduledTask -TaskName $TaskName
    Write-Host "REGISTERED '$TaskName' (state: $($t.State)). Next run: $((Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)" -ForegroundColor Green
    Write-Host "Check it any time with:  Get-ScheduledTaskInfo -TaskName '$TaskName'"
} else {
    Write-Host "(-WhatIf: nothing was registered.)"
}
