#Requires -Version 7.0
<#
.SYNOPSIS
    Resend delivery-webhook round-trip smoke (EB-330).

.DESCRIPTION
    Confirms that Resend's delivery webhook reaches POST /webhooks/resend and
    transitions a job's kindle_delivery_status past the immediate-post-accept
    baseline. Companion to tools/verify_send_to_kindle.ps1.

    What this proves that the CI test cannot: the real Resend -> Svix -> the
    public /webhooks/resend endpoint -> Cloudflare WAF -> nginx origin-lockdown
    -> the app delivery path. The pytest e2e (tests/test_web_send_to_kindle_signed.py)
    signs a payload locally and POSTs straight to the app, so it never exercises
    the public ingress.

    Flow:
      1. Read /status/{job_id}. Expect kindle_delivery_status = accepted_by_resend
         (i.e. a send already happened - run verify_send_to_kindle.ps1 first, or
         pass -SendFirst with a -Recipient to do the send here).
      2. Poll until the status transitions to a delivery state
         (delivered_to_mail_server / bounced / failed / delivery_delayed) or the
         timeout elapses.
      3. Report the transition. A timeout at accepted_by_resend usually means the
         Resend webhook is not registered/reaching the origin (check Lane B WAF +
         Lane D webhook registration), NOT necessarily a failed delivery.

.PARAMETER AppUrl
    Base URL of the running FastAPI app. Defaults to http://localhost:8000.

.PARAMETER JobId
    The id of a job that has had a Send-to-Kindle (status accepted_by_resend). Required.

.PARAMETER SendFirst
    Trigger the send here first (delegates to verify_send_to_kindle.ps1). Requires -Recipient.

.PARAMETER Recipient
    Kindle address used only with -SendFirst. Must be @kindle.com / @free.kindle.com.

.PARAMETER TimeoutSec
    Max seconds to poll for a delivery transition. Default 120.

.PARAMETER IntervalSec
    Seconds between polls. Default 5.

.EXAMPLE
    pwsh tools/verify_resend_webhook.ps1 -JobId abc123
    # Poll an already-sent job for the delivery transition.

.EXAMPLE
    pwsh tools/verify_resend_webhook.ps1 -AppUrl https://api.leafbind.io -JobId abc123 -SendFirst -Recipient mytest@kindle.com
    # Send, then watch the webhook round-trip on production.

.NOTES
    EB-330 Lane A. Status field reference: web_service/routes/status.py
    (kindle_delivery_status + resend_message_id surface at the top level).
#>

[CmdletBinding()]
param(
    [string]$AppUrl = "http://localhost:8000",
    [Parameter(Mandatory = $true)]
    [string]$JobId,
    [switch]$SendFirst,
    [string]$Recipient,
    [int]$TimeoutSec = 120,
    [int]$IntervalSec = 5
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Message) Write-Host ""; Write-Host "===> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "  [OK] $Message" -ForegroundColor Green }
function Write-Fail { param([string]$Message) Write-Host "  [FAIL] $Message" -ForegroundColor Red }
function Write-Note { param([string]$Message) Write-Host "  $Message" -ForegroundColor Gray }

$TerminalStates = @("delivered_to_mail_server", "bounced", "failed")
$DeliveryStates = $TerminalStates + @("delivery_delayed")

function Get-JobStatus {
    param([string]$Url, [string]$Id)
    $resp = Invoke-WebRequest -Uri "$Url/status/$Id" -Method GET -UseBasicParsing -TimeoutSec 10
    return ($resp.Content | ConvertFrom-Json)
}

# ---------------------------------------------------------------------------
# Optional: trigger the send first via the companion script.
# ---------------------------------------------------------------------------

if ($SendFirst) {
    if (-not $Recipient) { Write-Fail "-SendFirst requires -Recipient."; exit 1 }
    $companion = Join-Path $PSScriptRoot "verify_send_to_kindle.ps1"
    if (-not (Test-Path $companion)) { Write-Fail "Companion verify_send_to_kindle.ps1 not found."; exit 1 }
    Write-Step "Sending first via verify_send_to_kindle.ps1"
    & $companion -AppUrl $AppUrl -JobId $JobId -Recipient $Recipient
    if ($LASTEXITCODE -ne 0) { Write-Fail "Send step failed (exit $LASTEXITCODE); aborting webhook poll."; exit $LASTEXITCODE }
}

# ---------------------------------------------------------------------------
# Step 1: baseline status
# ---------------------------------------------------------------------------

Write-Step "Reading baseline status for job $JobId"
try {
    $job = Get-JobStatus -Url $AppUrl -Id $JobId
} catch {
    Write-Fail "Could not read /status/$JobId : $($_.Exception.Message)"
    exit 1
}

$current = $job.kindle_delivery_status
Write-Note "kindle_delivery_status = $($current ?? '<null>')   resend_message_id = $($job.resend_message_id ?? '<null>')"

if ($null -eq $current) {
    Write-Fail "Job has no Send-to-Kindle state (kindle_delivery_status is null). Run a send first (-SendFirst -Recipient ...)."
    exit 2
}
if ($DeliveryStates -contains $current) {
    Write-Ok "Already at a delivery state: $current. Webhook round-trip previously confirmed."
    exit 0
}
if ($current -ne "accepted_by_resend") {
    Write-Note "Unexpected starting status '$current'; polling anyway."
}

# ---------------------------------------------------------------------------
# Step 2: poll for the transition
# ---------------------------------------------------------------------------

Write-Step "Polling up to ${TimeoutSec}s (every ${IntervalSec}s) for a delivery transition"
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$final = $current
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $IntervalSec
    try {
        $job = Get-JobStatus -Url $AppUrl -Id $JobId
    } catch {
        Write-Note "poll error (will retry): $($_.Exception.Message)"
        continue
    }
    $now = $job.kindle_delivery_status
    if ($now -ne $final) {
        Write-Note "transition: $final -> $now"
        $final = $now
    }
    if ($DeliveryStates -contains $now) { break }
}

# ---------------------------------------------------------------------------
# Step 3: verdict
# ---------------------------------------------------------------------------

Write-Step "Result"
if ($TerminalStates -contains $final) {
    Write-Ok "Delivery webhook round-trip confirmed. Final status: $final"
    exit 0
} elseif ($final -eq "delivery_delayed") {
    Write-Ok "Webhook reached the app (status: delivery_delayed). Resend is retrying delivery; re-poll later for a terminal state."
    exit 0
} else {
    Write-Fail "No delivery transition within ${TimeoutSec}s; still at '$final'."
    Write-Note "Likely causes (in order): Resend webhook not registered at https://api.leafbind.io/webhooks/resend"
    Write-Note "(Lane D); Cloudflare WAF blocking /webhooks/resend (Lane B); nginx origin-lockdown rejecting the"
    Write-Note "Resend/Svix source (Lane C); or WEB_RESEND_WEBHOOK_SECRET mismatch (401 on verify). Check the"
    Write-Note "Resend dashboard webhook delivery log and the app logs for /webhooks/resend entries."
    exit 3
}
