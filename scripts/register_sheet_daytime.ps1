<#
.SYNOPSIS
  OPERATOR-RUN. Registers the Windows scheduled task 'CFP Sheet Daytime Load' (the daytime load of the customer sheets, 2026-11-13, Matt: D67 = A).

.DESCRIPTION
  On Thursday and Friday, at 07:30 and again at 18:15, it runs the dev repo's daytime check:

      C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe C:\Users\matts\cfp-monitor\scripts\sheet_daytime_check.py --kind auto

  --kind auto picks the research it protects by weekday: Thursday protects Friday 02:00 (the awards research), Friday protects Saturday 02:00 (the
  conference research). Each run does three things:
    1. a REAL load of all four customer sheets, with the usual retries; the copies are saved in Markets\customer_snapshots, as the 02:00 load does.
       Nothing is loaded into the database and no research is touched.
    2. the REAL step 0a4 block of run_monthly.ps1 (the customer context) is run on scratch copies: a usage error, no verdict line, FAILED, UNKNOWN or zero
       rows is RED. This would have caught the 2026-11-13 crash on Thursday.
    3. a verdict with the hours left before 02:00: GREEN (no email), YELLOW (email: tonight would still proceed, on a copy within the 24 hour limit) or
       RED (email at once: the 02:00 research would be HELD, or run without context, unless it is fixed).
  Exit code (the AgentOS convention): 0 GREEN, 2 YELLOW, 1 RED or the check itself failed.

  WHY ITS OWN TASK (and not folded into the Thursday 18:00 pre-flight): the pre-flight reads files and the switches and emails one verdict; this one
  fetches from Google and runs a PowerShell block, which fail in different ways and may take up to about 20 minutes. It starts at 18:15 so the two never
  start together.

  IF THE PC IS ASLEEP at 07:30: WakeToRun is ON, so it wakes (on mains power); StartWhenAvailable is ON, so a missed start runs when the PC next wakes.
  IF THE PC IS OFF, or you are signed out, nothing runs: the 18:15 run is the backup, and the 02:00 load still happens by itself. It needs you signed in,
  like every other CFP task.

  Safe to try first:   .\register_sheet_daytime.ps1 -DryRun     (prints what it would register, changes nothing; -WhatIf does the same)
  To register:         .\register_sheet_daytime.ps1
  It REFUSES a second registration: if the task already exists it stops and changes nothing. To replace it, delete the task yourself first
  (Unregister-ScheduledTask -TaskName 'CFP Sheet Daytime Load').

  Windows PowerShell 5.1. It needs no administrator rights. Its manifest entry (agentos tools\scheduled-tasks.manifest.json) is added in the same change.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'CFP Sheet Daytime Load',
    [string]$Repo     = 'C:\Users\matts\cfp-monitor',
    [string]$Morning  = '07:30',
    [string]$Evening  = '18:15',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$py     = Join-Path $Repo '.venv\Scripts\python.exe'
$script = Join-Path $Repo 'scripts\sheet_daytime_check.py'

if (-not (Test-Path $py))     { Write-Host "REFUSED: the interpreter was not found: $py" -ForegroundColor Red; exit 2 }
if (-not (Test-Path $script)) { Write-Host "REFUSED: the script was not found: $script" -ForegroundColor Red; exit 2 }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing -and -not $DryRun) {
    Write-Host "REFUSED: a task named '$TaskName' is already registered (state: $($existing.State)). Nothing was changed." -ForegroundColor Yellow
    Write-Host "  To replace it, delete it yourself first: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    exit 1
}

$argument = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$py' '$script' --kind auto; exit `$LASTEXITCODE`""
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $Repo
$triggerA = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday, Friday -At $Morning
$triggerB = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday, Friday -At $Evening
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$settings.WakeToRun = $true
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Write-Host ""
Write-Host "Task      : $TaskName"
Write-Host "When      : every Thursday and Friday at $Morning and at $Evening"
Write-Host "Runs      : powershell.exe $argument"
Write-Host "Start in  : $Repo"
Write-Host "Settings  : WakeToRun ON (wakes a sleeping PC), StartWhenAvailable, one instance, 45 minute limit, runs on battery"
Write-Host "Effect    : loads the four customer sheets (saves copies), runs the step 0a4 block on scratch copies, emails Matt (CFP_RECAP_TO) only if the"
Write-Host "            result is YELLOW or RED, with the hours left before 02:00. Loads nothing into the database; starts no research."
Write-Host "Exit code : 0 GREEN, 2 YELLOW, 1 RED or the check itself failed"
Write-Host "Protects  : Thursday -> Friday 02:00 (awards research); Friday -> Saturday 02:00 (conference research)"
if ($existing) { Write-Host "Note      : a task named '$TaskName' is ALREADY registered (state: $($existing.State)); a real run would refuse." -ForegroundColor Yellow }
Write-Host ""

if ($DryRun) {
    Write-Host "(-DryRun: nothing was registered.)"
} elseif ($PSCmdlet.ShouldProcess($TaskName, "Register the Thursday and Friday $Morning and $Evening customer sheet daytime load")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($triggerA, $triggerB) -Settings $settings -Principal $principal `
        -Description 'CFP customer sheet daytime load (2026-11-13, D67): loads the four sheets, rehearses the customer context step on copies, alerts Matt when YELLOW or RED before 02:00.' | Out-Null
    $t = Get-ScheduledTask -TaskName $TaskName
    Write-Host "REGISTERED '$TaskName' (state: $($t.State)). Next run: $((Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)" -ForegroundColor Green
    Write-Host "Check it any time with:  Get-ScheduledTaskInfo -TaskName '$TaskName'"
} else {
    Write-Host "(-WhatIf: nothing was registered.)"
}
