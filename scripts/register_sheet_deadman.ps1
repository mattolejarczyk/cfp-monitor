<#
.SYNOPSIS
  OPERATOR-RUN. Registers the Windows scheduled task 'CFP Sheet Load Check' (the dead-man check for the customer sheets, 2026-11-09).

.DESCRIPTION
  Every Friday and Saturday at 03:00 it runs the dev repo's sheet check:

      C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe C:\Users\matts\cfp-monitor\scripts\customer_sheet_load.py --deadman auto

  It FETCHES NOTHING. It asks whether today's copies of the customer sheets exist (Friday: the two awards sheets; Saturday: all four).
  If they do not - the PC was asleep at 02:00, the research task did not start, or it stopped before the sheets - it sends Matt the same
  CRITICAL email as a failed load ("CFP customer sheets failed to load - CRITICAL ERROR"), at most once a day, so no second email when the
  run already alerted. If a research run is still going (its log changed in the last 15 minutes) it waits up to 25 minutes first.

  WHY ITS OWN TASK: when the 02:00 job never runs, nothing inside it can alert. Settings differ from the other CFP tasks in ONE way, on
  purpose: WakeToRun is ON, so a sleeping PC wakes for it (the research tasks then catch up, as they start when available). It cannot help
  when the PC is switched OFF: wake-to-run wakes from sleep only.

  Safe to try first:   .\register_sheet_deadman.ps1 -WhatIf     (prints what it would register, changes nothing)
  To register:         .\register_sheet_deadman.ps1
  It REFUSES a second registration: if the task already exists it stops and changes nothing. To replace it, delete the task yourself
  first (Unregister-ScheduledTask -TaskName 'CFP Sheet Load Check').

  Windows PowerShell 5.1. It needs no administrator rights. Its manifest entry (agentos tools\scheduled-tasks.manifest.json) is added in
  the same change.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'CFP Sheet Load Check',
    [string]$Repo     = 'C:\Users\matts\cfp-monitor',
    [string]$At       = '03:00'
)

$ErrorActionPreference = 'Stop'
$py     = Join-Path $Repo '.venv\Scripts\python.exe'
$script = Join-Path $Repo 'scripts\customer_sheet_load.py'

if (-not (Test-Path $py))     { Write-Host "REFUSED: the interpreter was not found: $py" -ForegroundColor Red; exit 2 }
if (-not (Test-Path $script)) { Write-Host "REFUSED: the script was not found: $script" -ForegroundColor Red; exit 2 }
if (-not (Select-String -Path $script -SimpleMatch '"auto"' -Quiet)) {
    Write-Host "REFUSED: $script has no --deadman auto mode yet. Pull the latest cfp-monitor main first." -ForegroundColor Red
    exit 2
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "REFUSED: a task named '$TaskName' is already registered (state: $($existing.State)). Nothing was changed." -ForegroundColor Yellow
    Write-Host "  To replace it, delete it yourself first: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    exit 1
}

$argument = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$py' '$script' --deadman auto; exit `$LASTEXITCODE`""
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $Repo
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday, Saturday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$settings.WakeToRun = $true
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Write-Host ""
Write-Host "Task      : $TaskName"
Write-Host "When      : every Friday and Saturday at $At"
Write-Host "Runs      : powershell.exe $argument"
Write-Host "Start in  : $Repo"
Write-Host "Settings  : WakeToRun ON (wakes a sleeping PC), StartWhenAvailable, one instance, 45 minute limit, runs on battery"
Write-Host "Effect    : reads the copies folder and today's run log; emails Matt once (CFP_RECAP_TO) only if today's copies are missing"
Write-Host "Exit code : 0 HEALTHY, 1 FAILED (alert sent or already sent), 2 DEGRADED (the check itself failed)"
Write-Host ""

if ($PSCmdlet.ShouldProcess($TaskName, "Register the Friday and Saturday $At customer sheet dead-man check")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'CFP customer sheet dead-man check (2026-11-09): are today''s copies of the customer sheets there? If not, the CRITICAL email to Matt. Fetches nothing.' | Out-Null
    $t = Get-ScheduledTask -TaskName $TaskName
    Write-Host "REGISTERED '$TaskName' (state: $($t.State)). Next run: $((Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)" -ForegroundColor Green
    Write-Host "Check it any time with:  Get-ScheduledTaskInfo -TaskName '$TaskName'"
} else {
    Write-Host "(-WhatIf: nothing was registered.)"
}
