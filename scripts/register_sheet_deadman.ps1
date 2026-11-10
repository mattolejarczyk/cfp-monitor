<#
.SYNOPSIS
  OPERATOR-RUN. Registers the Windows scheduled task 'CFP Sheet Load Check' (the dead-man check for the customer sheets, 2026-11-09).

.DESCRIPTION
  Every Friday and Saturday at 03:00 it runs the dev repo's sheet check:

      C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe C:\Users\matts\cfp-monitor\scripts\customer_sheet_load.py --deadman auto

  It FETCHES NOTHING. It asks whether today's copies of the customer sheets exist (Friday: the two awards sheets; Saturday: all four),
  and if not, which of three cases it is (Matt, 2026-11-10), each with its own one-line cause and fix steps:
    - the research task did not start (no run log today and Task Scheduler's last run is not today): the CRITICAL email, with how to
      start the job by hand (Start-ScheduledTask). It first gives a task that missed 02:00 five minutes to start by itself.
    - the task is running but the sheets have not loaded yet: NO email. The run sends its own alert and waits up to 2 hours for the sheets.
    - the task ran and today's copies are missing: the CRITICAL email, with the cause read from today's run log.
  The CRITICAL email ("CFP customer sheets failed to load - CRITICAL ERROR") goes at most once a day, so no second email when the run
  already alerted.

  WHY ITS OWN TASK: when the 02:00 job never runs, nothing inside it can alert. Settings differ from the other CFP tasks in ONE way, on
  purpose: WakeToRun is ON, so a sleeping PC wakes for it (the research tasks then catch up, as they start when available). It cannot help
  when the PC is switched OFF: wake-to-run wakes from sleep only.

  Safe to try first:   .\register_sheet_deadman.ps1 -DryRun     (prints what it would register, changes nothing; -WhatIf does the same)
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
    [string]$At       = '03:00',
    [switch]$DryRun
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
if ($existing -and -not $DryRun) {
    Write-Host "REFUSED: a task named '$TaskName' is already registered (state: $($existing.State)). Nothing was changed." -ForegroundColor Yellow
    Write-Host "  To replace it, delete it yourself first: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    exit 1
}

$argument = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$py' '$script' --deadman auto; exit `$LASTEXITCODE`""
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $Repo
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday, Saturday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$settings.WakeToRun = $true
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Write-Host ""
Write-Host "Task      : $TaskName"
Write-Host "When      : every Friday and Saturday at $At"
Write-Host "Runs      : powershell.exe $argument"
Write-Host "Start in  : $Repo"
Write-Host "Settings  : WakeToRun ON (wakes a sleeping PC), StartWhenAvailable, one instance, 10 minute limit, runs on battery"
Write-Host "Effect    : reads the copies folder, today's run log and the research task's state (read only); emails Matt once (CFP_RECAP_TO)"
Write-Host "            only if today's copies are missing AND the research task is not running (did not start, or ran without them)"
Write-Host "Exit code : 0 HEALTHY or RUNNING (no email), 1 FAILED (alert sent or already sent), 2 DEGRADED (the check itself failed)"
if ($existing) { Write-Host "Note      : a task named '$TaskName' is ALREADY registered (state: $($existing.State)); a real run would refuse." -ForegroundColor Yellow }
Write-Host ""

if ($DryRun) {
    Write-Host "(-DryRun: nothing was registered.)"
} elseif ($PSCmdlet.ShouldProcess($TaskName, "Register the Friday and Saturday $At customer sheet dead-man check")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'CFP customer sheet dead-man check (2026-11-09): are today''s copies of the customer sheets there? If not, the CRITICAL email to Matt. Fetches nothing.' | Out-Null
    $t = Get-ScheduledTask -TaskName $TaskName
    Write-Host "REGISTERED '$TaskName' (state: $($t.State)). Next run: $((Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)" -ForegroundColor Green
    Write-Host "Check it any time with:  Get-ScheduledTaskInfo -TaskName '$TaskName'"
} else {
    Write-Host "(-WhatIf: nothing was registered.)"
}
