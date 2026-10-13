<#
.SYNOPSIS
  OPERATOR-RUN. Registers the Windows scheduled task 'CFP Thursday Pre-flight' (ACT-70, QA-REGISTER A65).

.DESCRIPTION
  Every Thursday at 18:00 it runs the dev repo's release gate in Thursday mode:

      C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe C:\Users\matts\cfp-monitor\scripts\release_gate.py --thursday

  exactly as 'CFP Weekly Customer Pages' runs the dev repo's weekly_deliverable.py and as the Sunday recap runs the dev
  repo's weekend_recap.py: the dev repo's interpreter, the dev repo's script, working directory the dev repo. It READS files
  and sends ONE email to the operator (CFP_RECAP_TO); it changes nothing and spends no API quota.

  Settings are the other CFP tasks': the signed-in user, interactive, limited rights; StartWhenAvailable (a missed 18:00 runs
  when the computer is next on); WakeToRun OFF (as every other CFP task); one instance at a time; a one-hour limit; runs on
  battery (it is a few seconds of reading).

  Safe to try first:   .\register_thursday_preflight.ps1 -WhatIf     (prints what it would register, changes nothing)
  To register:         .\register_thursday_preflight.ps1
  It REFUSES a second registration: if the task already exists it stops and changes nothing. To replace it, delete the
  task yourself first (Unregister-ScheduledTask -TaskName 'CFP Thursday Pre-flight').

  Windows PowerShell 5.1. Run it from the folder it sits in, or give its full path. It needs no administrator rights.
  Run it only AFTER the branch that adds `release_gate.py --thursday` is merged into C:\Users\matts\cfp-monitor: it checks
  that and refuses otherwise.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'CFP Thursday Pre-flight',
    [string]$Repo     = 'C:\Users\matts\cfp-monitor',
    [string]$At       = '18:00'
)

$ErrorActionPreference = 'Stop'
$py     = Join-Path $Repo '.venv\Scripts\python.exe'
$script = Join-Path $Repo 'scripts\release_gate.py'

if (-not (Test-Path $py))     { Write-Host "REFUSED: the interpreter was not found: $py" -ForegroundColor Red; exit 2 }
if (-not (Test-Path $script)) { Write-Host "REFUSED: the script was not found: $script" -ForegroundColor Red; exit 2 }
if (-not (Select-String -Path $script -Pattern '--thursday' -Quiet)) {
    Write-Host "REFUSED: $script has no --thursday mode yet. Merge the ACT-70 branch into $Repo first." -ForegroundColor Red
    exit 2
}

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "REFUSED: a task named '$TaskName' is already registered (state: $($existing.State)). Nothing was changed." -ForegroundColor Yellow
    Write-Host "  To replace it, delete it yourself first: Unregister-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
    exit 1
}

$argument = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$py' '$script' --thursday`""
$action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $Repo
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$settings.WakeToRun = $false
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Write-Host ""
Write-Host "Task      : $TaskName"
Write-Host "When      : every Thursday at $At"
Write-Host "Runs      : powershell.exe $argument"
Write-Host "Start in  : $Repo"
Write-Host "Settings  : StartWhenAvailable, WakeToRun OFF, one instance, 1 hour limit, runs on battery"
Write-Host "Effect    : reads files, emails the operator once (CFP_RECAP_TO); changes nothing else"
Write-Host ""

if ($PSCmdlet.ShouldProcess($TaskName, "Register the Thursday $At pre-flight scheduled task")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'CFP Thursday pre-flight (ACT-70): patches applied, awards waiting for ids, switches, customer sheets and coverage before Friday 02:00 and Saturday 02:00. Reads files; emails the operator only.' | Out-Null
    $t = Get-ScheduledTask -TaskName $TaskName
    Write-Host "REGISTERED '$TaskName' (state: $($t.State)). Next run: $((Get-ScheduledTaskInfo -TaskName $TaskName).NextRunTime)" -ForegroundColor Green
    Write-Host "Check it any time with:  Get-ScheduledTaskInfo -TaskName '$TaskName'"
} else {
    Write-Host "(-WhatIf: nothing was registered.)"
}
