# run_end_to_end.ps1 - research, gate, import, verify, reconcile, publish. In that order.
#
#   .\scripts\run_end_to_end.ps1                    # report only - shows the plan, spends nothing
#   .\scripts\run_end_to_end.ps1 -Apply             # the real thing
#   .\scripts\run_end_to_end.ps1 -Apply -SkipResearch   # everything downstream of research
#   .\scripts\run_end_to_end.ps1 -Apply -Markets Utility,Cybersecurity
#
# WHY THIS EXISTS
# run_monthly.ps1 ends by printing "NEXT, BY HAND: gate each market, then import and verify
# downstream." Those manual steps are where the cycle stalls: research finishes at 04:00, nobody
# gates it, and the fresh data sits in the Markets folder until someone remembers. Every stage
# below already existed as a documented command. Prose cannot enforce an order or a precondition
# - the same reason run_full_cycle.py exists for the delivery half.
#
# THE ONE RULE THAT MATTERS
# **The gate decides.** A delivery that does not come back ACCEPTED is never imported, and this
# script stops rather than continuing past it. accept_delivery.py returns INCOMPLETE (not
# ACCEPTED) whenever a check was skipped, so "it ran green" cannot mean "it ran partially".
#
# COST
# The research leg is roughly 400 grounded requests and takes about two hours at the 16-second
# pacing. Everything downstream of it is free - no LLM calls at all. The audit's own circuit
# breaker stops on quota exhaustion (exit 3) after two failed requests, so an unattended run
# cannot burn the key down, and it resumes where it stopped.

param(
    [switch]$Apply,
    [switch]$SkipResearch,
    [string[]]$Markets = @('Robotics','Semiconductor','ConsumerElectronics','Bioeconomy',
                           'BioMedTech','Cybersecurity','Utility','AdditiveMfg'),
    [string]$Live      = "$env:LOCALAPPDATA\CFP-Monitor",
    [string]$Upstream  = "$env:USERPROFILE\Desktop\Nicolia-PR-Prime\Markets",
    [string]$Handoff   = "$env:USERPROFILE\Desktop\Nicolia-PR-Prime\handoff-files",
    [string]$Delivery  = ""
)

$ErrorActionPreference = "Continue"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$today  = Get-Date -Format "yyyy-MM-dd"
$py     = Join-Path $Live "venv\Scripts\python.exe"
$snaps  = Join-Path $Upstream "customer_snapshots"
$out    = Join-Path $Live "runs_out"
$log    = Join-Path $out "endtoend_$stamp.log"
if (-not $Delivery) { $Delivery = Join-Path $Upstream "delivery_v14_citefix_43col.csv" }

$script:failed = $null
function Stage([string]$n, [string]$what) {
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkGray
    Write-Host "  $n  $what" -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor DarkGray
}
function Say([string]$m, [string]$c = "Gray") { Write-Host "    $m" -ForegroundColor $c }

Write-Host ""
Write-Host "END-TO-END CYCLE  $stamp" -ForegroundColor White
Write-Host "  mode      : $(if ($Apply) { 'APPLY - this writes' } else { 'REPORT ONLY - nothing written, nothing spent' })"
Write-Host "  markets   : $($Markets -join ', ')"
Write-Host "  live build: $Live"
Write-Host "  delivery  : $(Split-Path $Delivery -Leaf)"
Write-Host "  log       : $log"

# ---------------------------------------------------------------- 0. preflight
Stage "0" "Preflight - every one of these has silently degraded a run"
if (-not (Test-Path $py))       { Say "MISSING interpreter: $py" Red;  exit 2 }
if (-not (Test-Path $Live))     { Say "MISSING live build: $Live" Red; exit 2 }
Say "interpreter   ok"
$dbPath = Join-Path $Live "cfp_monitor.db"
if (-not (Test-Path $dbPath))   { Say "MISSING database: $dbPath" Red; exit 2 }
Say "database      ok"
if (-not $SkipResearch -and -not $env:GEMINI_API_KEY) {
    Say "GEMINI_API_KEY is not set - the research leg would spend nothing and exit." Yellow
    Say "Set it, or pass -SkipResearch to run the free half deliberately." Yellow
    if ($Apply) { exit 2 }
}
Push-Location $Live
& $py scripts\cdp_ctl.py check *> $null
if ($LASTEXITCODE -ne 0) {
    Say "CDP Chrome not on 9222 - hard anti-bot sites will be SKIPPED, not hammered." Yellow
    Say "That rung recovered 53 claims on 2026-08-10. run_weekly.bat starts it itself." Yellow
} else { Say "CDP           ok" }
Pop-Location

# ---------------------------------------------------------------- 1. invariants BEFORE
Stage "1" "Invariants BEFORE - a run that starts broken must not be blamed on what we do next"
Push-Location $Live
if ($Apply) {
    & $py scripts\check_invariants.py --db cfp_monitor.db --seed-dir market_sheets 2>&1 |
        Tee-Object -FilePath $log -Append | Select-Object -Last 4
    if ($LASTEXITCODE -ne 0) { Say "INVARIANTS FAILED - stopping before anything is touched." Red; Pop-Location; exit 3 }
} else { Say "would run check_invariants.py" }
Pop-Location

# ---------------------------------------------------------------- 2. research
Stage "2" "Research - the ONLY leg that spends quota (~400 requests, ~2 hours)"
if ($SkipResearch) {
    Say "skipped by request"
} elseif ($Apply) {
    $rm = Join-Path $Upstream "run_monthly.ps1"
    if (-not (Test-Path $rm)) { Say "MISSING $rm - skipping research, continuing downstream." Yellow }
    else {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $rm -Markets $Markets 2>&1 |
            Tee-Object -FilePath $log -Append | Select-Object -Last 6
        if ($LASTEXITCODE -eq 3) { Say "OUT OF QUOTA - re-run after the window resets; it resumes." Red }
    }
} else {
    Say "would archive the previous cycle and re-audit $($Markets.Count) market(s)"
    Say "cost: ~400 grounded requests. Preview it exactly with:  run_monthly.ps1 -WhatIf"
}

# ---------------------------------------------------------------- 3. THE GATE
Stage "3" "The gate - NOTHING is imported that does not come back ACCEPTED"
Push-Location $Live
if (Test-Path $Delivery) {
    # Positional, not -i. Networked deliberately: --no-network SKIPS criteria 2 and 3, the only
    # two that fetch a cited page, and a gate that skipped them cannot say ACCEPTED.
    & $py scripts\accept_delivery.py $Delivery --db cfp_monitor.db 2>&1 |
        Tee-Object -FilePath $log -Append | Select-Object -Last 14
    $gate = $LASTEXITCODE
    if ($gate -ne 0) {
        Say "" ; Say "GATE DID NOT PASS (exit $gate). Stopping here." Red
        Say "INCOMPLETE means a check was SKIPPED, not that it passed. Read the output above." Red
        Pop-Location; exit 4
    }
    Say "gate passed" Green
} else { Say "delivery not found: $Delivery" Yellow }
Pop-Location

# ---------------------------------------------------------------- 4. import + reconcile
Stage "4" "Import, then reconcile - a mutation needs a reconciliation"
Push-Location $Live
if ($Apply) {
    Copy-Item $dbPath (Join-Path $Live "cfp_monitor.backup-pre-e2e-$stamp.db") -Force
    Say "backup taken"
    & $py scripts\import_grounding.py --db cfp_monitor.db --csv $Delivery 2>&1 |
        Tee-Object -FilePath $log -Append | Select-Object -Last 5
    & $py scripts\check_invariants.py --db cfp_monitor.db --seed-dir market_sheets 2>&1 |
        Tee-Object -FilePath $log -Append | Select-Object -Last 4
    if ($LASTEXITCODE -ne 0) { Say "INVARIANTS FAILED AFTER IMPORT - restore the backup." Red; Pop-Location; exit 5 }
} else { Say "would back up, import_grounding.py, then check_invariants.py" }
Pop-Location

# ---------------------------------------------------------------- 5. verify
Stage "5" "Verify - free, no LLM calls. Claims against live pages, plus every customer link"
Push-Location $Live
if ($Apply) {
    & $py scripts\weekly_verify.py --db cfp_monitor.db 2>&1 |
        Tee-Object -FilePath $log -Append | Select-Object -Last 8
} else { Say "would run weekly_verify.py (this is what the Sunday job already does)" }
Pop-Location

# ---------------------------------------------------------------- 6. the customer's sheet
Stage "6" "The customer's sheet - snapshot, load, match, diff"
Say "EXPORT IS STILL MANUAL. The sheets need an authenticated browser session, so this" Yellow
Say "stage cannot run unattended yet. Export each client's sheet to CSV first, then:" Yellow
Say ""
Say "  scripts\snapshot_customer_sheet.py --csv <export> --client <key> --out-dir $snaps"
Say "  scripts\load_client_sheet.py       --db cfp_monitor.db --csv <snapshot> ..."
Say "  scripts\match_customer_sheet.py    --sheet <snapshot> --market <M> ..."
Say "  scripts\apply_client_match.py      --db cfp_monitor.db --matches <out> ..."
Say ""
if (Test-Path $snaps) {
    Get-ChildItem $snaps -Directory | ForEach-Object {
        $c = $_.Name
        $n = (Get-ChildItem $_.FullName -Filter "$c`_*.csv" | Measure-Object).Count
        Say "$c : $n snapshot(s)$(if ($n -lt 2) { '  - need 2 to diff; this week is the baseline' })"
        if ($n -ge 2 -and $Apply) {
            Push-Location $Live
            & $py scripts\diff_client_sheet.py --client $c --snapshots $snaps --today $today `
                -o (Join-Path $out "clientdiff_${c}_$stamp.md") 2>&1 |
                Tee-Object -FilePath $log -Append | Select-Object -Last 20
            Pop-Location
        }
    }
} else { Say "no snapshot directory yet at $snaps" Yellow }

# ---------------------------------------------------------------- 7. publish
Stage "7" "Publish - the customer page, built from the delivery"
Push-Location $Live
if ($Apply) {
    $checks = Join-Path $out "checks_$stamp.csv"
    $hosts  = Join-Path $out "dead_hosts_$stamp.txt"
    $page   = Join-Path $Handoff "Conference Review $today.html"
    & $py scripts\export_checks.py --db cfp_monitor.db -o $checks 2>&1 | Select-Object -Last 3
    & $py scripts\check_dns.py --db cfp_monitor.db --out $hosts 2>&1 | Select-Object -Last 2
    & $py scripts\build_review_page.py -i $Delivery -o $page --date $today `
        --db cfp_monitor.db --checks $checks --dead-hosts $hosts 2>&1 | Select-Object -Last 3
    Say "page: $page" Green
} else { Say "would export checks, sweep DNS, and rebuild the customer page" }
Pop-Location

Stage "" "Done"
if (-not $Apply) {
    Write-Host "  REPORT ONLY - nothing was written and no quota was spent." -ForegroundColor Yellow
    Write-Host "  Re-run with -Apply to execute." -ForegroundColor Yellow
} else {
    Write-Host "  Log: $log" -ForegroundColor Green
}
Write-Host ""
