#Requires -Version 7.0
<#
.SYNOPSIS
    Send-to-Kindle manual smoke: real send through the live app via Resend (EB-330).

.DESCRIPTION
    The gold-standard manual verification for the Send-to-Kindle send path,
    companion to the CI test tests/test_web_send_to_kindle_signed.py. Use this:
      - Before a production deploy that touches send_to_kindle.py, email_client.py,
        validation.py, or the Resend provisioning
      - Right after flipping WEB_SEND_TO_KINDLE_ENABLED=true, to confirm a real
        send reaches Resend with the verified sender + API key
      - When triaging a customer report of "I sent to my Kindle but nothing arrived"

    Unlike the pytest e2e (which mocks Resend), this script POSTs to the live app
    so the real WEB_RESEND_API_KEY + WEB_SEND_TO_KINDLE_FROM are exercised and a
    real message lands in the Resend dashboard. The companion script
    tools/verify_resend_webhook.ps1 then confirms the delivery webhook round-trips
    and transitions kindle_delivery_status past accepted_by_resend.

    Prerequisite: a DONE job whose output is an EPUB still on disk. Convert a file
    at the AppUrl first (the result page shows the job id in the URL), or pass the
    id of any recent done EPUB job via -JobId.

.PARAMETER AppUrl
    Base URL of the running FastAPI app. Defaults to http://localhost:8000.
    For a staging/prod check use e.g. https://api.leafbind.io.

.PARAMETER JobId
    The id of a DONE job with an EPUB output on disk. Required.

.PARAMETER Recipient
    The destination Kindle address. MUST be @kindle.com or @free.kindle.com
    (the server-side allowlist rejects everything else). Use an internal test
    Kindle address you control. Required.

.PARAMETER PollDelivery
    After a successful send, chain into the webhook round-trip check by polling
    /status/{job_id} for the delivery transition (equivalent to running
    tools/verify_resend_webhook.ps1 afterward).

.EXAMPLE
    pwsh tools/verify_send_to_kindle.ps1 -JobId abc123 -Recipient mytest@kindle.com
    # Local smoke against a done EPUB job.

.EXAMPLE
    pwsh tools/verify_send_to_kindle.ps1 -AppUrl https://api.leafbind.io -JobId abc123 -Recipient mytest@kindle.com -PollDelivery
    # Production smoke + delivery-webhook round-trip.

.NOTES
    EB-330 Lane A. Companion: tools/verify_resend_webhook.ps1 and the CI test
    tests/test_web_send_to_kindle_signed.py. The send path stays dark until
    WEB_SEND_TO_KINDLE_ENABLED=true on the target deploy: a 503 SERVICE_DISABLED
    response means the flag is still off.
#>

[CmdletBinding()]
param(
    [string]$AppUrl = "http://localhost:8000",
    [Parameter(Mandatory = $true)]
    [string]$JobId,
    [Parameter(Mandatory = $true)]
    [string]$Recipient,
    [switch]$PollDelivery
)

$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Message) Write-Host ""; Write-Host "===> $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "  [OK] $Message" -ForegroundColor Green }
function Write-Fail { param([string]$Message) Write-Host "  [FAIL] $Message" -ForegroundColor Red }
function Write-Note { param([string]$Message) Write-Host "  $Message" -ForegroundColor Gray }

# ---------------------------------------------------------------------------
# Step 0: client-side recipient sanity (mirror the server allowlist so an
# obvious typo fails fast before we POST).
# ---------------------------------------------------------------------------

if ($Recipient -notmatch '^[^@\s]+@(free\.)?kindle\.com$') {
    Write-Fail "Recipient '$Recipient' is not a bare @kindle.com / @free.kindle.com address."
    Write-Note "The server rejects display names, plus-aliases, and other domains."
    exit 1
}

# ---------------------------------------------------------------------------
# Step 1: app reachability
# ---------------------------------------------------------------------------

Write-Step "Checking app reachability: $AppUrl"
$reachable = $false
foreach ($path in @("/health", "/healthz", "/", "/status/$JobId")) {
    try {
        $probe = Invoke-WebRequest -Uri "$AppUrl$path" -Method GET -UseBasicParsing -TimeoutSec 5
        if ($probe.StatusCode -in 200, 422) {
            Write-Ok "App responding at $path ($($probe.StatusCode))"
            $reachable = $true
            break
        }
    } catch {
        # 404 here still proves the app is up; only a connection failure means down.
        if ($_.Exception.Response) { Write-Ok "App responding at $path ($($_.Exception.Response.StatusCode.value__))"; $reachable = $true; break }
    }
}
if (-not $reachable) {
    Write-Fail "App not reachable at $AppUrl. Is the FastAPI server running?"
    Write-Note "Start with: cd web_service; uvicorn main:app --reload"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 2: POST the send
# ---------------------------------------------------------------------------

Write-Step "POST /send-to-kindle/$JobId  (recipient: $Recipient)"

$sendStatus = $null
$sendBody = $null
try {
    $resp = Invoke-WebRequest -Uri "$AppUrl/send-to-kindle/$JobId" -Method POST `
        -Body @{ recipient = $Recipient } -UseBasicParsing -TimeoutSec 30
    $sendStatus = [int]$resp.StatusCode
    $sendBody = $resp.Content | ConvertFrom-Json
} catch {
    if ($_.Exception.Response) {
        $sendStatus = [int]$_.Exception.Response.StatusCode.value__
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $raw = $reader.ReadToEnd()
        try { $sendBody = $raw | ConvertFrom-Json } catch { $sendBody = $raw }
    } else {
        Write-Fail "Send request failed at the transport layer: $($_.Exception.Message)"
        exit 1
    }
}

# Interpret the documented response codes from web_service/routes/send_to_kindle.py.
switch ($sendStatus) {
    200 {
        $status = $sendBody.status
        if ($status -eq "sent") {
            Write-Ok "Resend accepted the send (status: sent)."
        } elseif ($status -eq "already_sent") {
            Write-Ok "Idempotent no-op (status: already_sent) - same (job, recipient) within the 60s window."
        } else {
            Write-Ok "200 with status: $status"
        }
    }
    503 {
        Write-Fail "503 SERVICE_DISABLED - WEB_SEND_TO_KINDLE_ENABLED is still false on this deploy."
        Write-Note "Flip the flag in /etc/web_service.env and restart the web_service unit (EB-330 Lane E)."
        exit 2
    }
    404 { Write-Fail "404 JOB_NOT_FOUND - no job with id '$JobId' on this deploy."; exit 2 }
    410 { Write-Fail "410 OUTPUT_EXPIRED - the job's EPUB output is no longer on disk (TTL swept). Convert again."; exit 2 }
    422 {
        $code = if ($sendBody.detail) { $sendBody.detail.code } else { $sendBody.code }
        Write-Fail "422 validation rejected the request (code: $code)."
        Write-Note "INVALID_JOB_STATE = job not done; FORMAT_NOT_KINDLE_ELIGIBLE = output is not EPUB;"
        Write-Note "OUTPUT_TOO_LARGE_FOR_KINDLE = over the 25 MiB cap; INVALID_RECIPIENT_* = address form/domain."
        exit 2
    }
    502 {
        Write-Fail "502 SEND_FAILED - the app reached the route but the Resend call failed."
        Write-Note "Check the Resend dashboard + that WEB_RESEND_API_KEY / WEB_SEND_TO_KINDLE_FROM are provisioned."
        exit 2
    }
    500 {
        $code = if ($sendBody.detail) { $sendBody.detail.code } else { $sendBody.code }
        Write-Fail "500 (code: $code). KINDLE_SEND_INVARIANT_VIOLATION means the output path failed the P1-4 boundary check."
        exit 2
    }
    default { Write-Fail "Unexpected HTTP $sendStatus. Body: $($sendBody | ConvertTo-Json -Compress)"; exit 2 }
}

# ---------------------------------------------------------------------------
# Step 3: manual verification pointers
# ---------------------------------------------------------------------------

Write-Step "Next checks"
Write-Note "1. Resend dashboard -> Emails: a new message to (a hashed/internal) recipient with your EPUB attached."
Write-Note "2. The destination Kindle library should receive the book within a few minutes (Amazon-side delay varies)."
Write-Note "3. Delivery webhook round-trip: kindle_delivery_status should advance past 'accepted_by_resend'."

if ($PollDelivery -and $sendStatus -eq 200 -and $sendBody.status -eq "sent") {
    Write-Step "Polling /status/$JobId for the delivery-webhook transition"
    $companion = Join-Path $PSScriptRoot "verify_resend_webhook.ps1"
    if (Test-Path $companion) {
        & $companion -AppUrl $AppUrl -JobId $JobId
    } else {
        Write-Note "Companion script not found next to this one; run tools/verify_resend_webhook.ps1 manually."
    }
}

Write-Step "Done"
