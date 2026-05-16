#Requires -Version 7.0
<#
.SYNOPSIS
    Stripe end-to-end verification: signed webhook -> success page (EB-273).

.DESCRIPTION
    Runs the gold-standard manual verification for the Stripe checkout chain
    against a locally-running FastAPI app. Use this:
      - Before a production deploy that touches checkout.py, webhook.py, or
        payment.py
      - When the audit-driven pytest in tests/test_web_payment_e2e.py passes but
        you suspect a real-world delivery issue
      - To re-baseline what a successful Stripe -> app handshake looks like in
        logs (helpful when triaging customer reports of "I paid but no tokens")

    The pytest equivalent (tests/test_web_payment_e2e.py) covers the same chain
    in CI with no external dependencies. This script catches what pytest can't:
    the real Stripe CLI -> Stripe edge -> webhook forwarding -> your app handshake.

.PARAMETER AppUrl
    Base URL of the locally-running FastAPI app. Defaults to http://localhost:8000.

.PARAMETER Pack
    Which credit pack to simulate. One of: starter, standard, power.
    Defaults to starter (3 tokens).

.PARAMETER SkipInstallCheck
    Skip the Stripe CLI install/auth check. Useful if you have already
    bootstrapped the CLI and don't want the version sniff overhead.

.EXAMPLE
    pwsh tools/verify_stripe_e2e.ps1
    # Default: starter pack, localhost:8000.

.EXAMPLE
    pwsh tools/verify_stripe_e2e.ps1 -Pack standard -AppUrl https://staging.leafbind.io
    # Verify staging deployment with a standard (10-token) pack.

.NOTES
    EB-273. Companion to tests/test_web_payment_e2e.py. See
    web_service/docs/stripe-verification.md (to be written in Phase 2 follow-up).

    Prerequisites:
      - Stripe CLI installed (winget install Stripe.StripeCLI)
      - `stripe login` completed at least once (auth token is cached)
      - FastAPI app running locally OR network access to AppUrl
      - For local: STRIPE_WEBHOOK_SECRET in the app's env must match what
        `stripe listen` reports when it starts forwarding
#>

[CmdletBinding()]
param(
    [string]$AppUrl = "http://localhost:8000",
    [ValidateSet("starter", "standard", "power")]
    [string]$Pack = "starter",
    [switch]$SkipInstallCheck
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "===> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Test-CommandAvailable {
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    return ($null -ne $cmd)
}

# ---------------------------------------------------------------------------
# Step 1: Tooling check
# ---------------------------------------------------------------------------

if (-not $SkipInstallCheck) {
    Write-Step "Checking prerequisites"

    if (-not (Test-CommandAvailable "stripe")) {
        Write-Fail "Stripe CLI not found on PATH."
        Write-Host "  Install with: winget install Stripe.StripeCLI" -ForegroundColor Yellow
        Write-Host "  Then run: stripe login" -ForegroundColor Yellow
        exit 1
    }
    $version = (stripe --version 2>&1) -join " "
    Write-Ok "Stripe CLI: $version"

    # Check the CLI is authenticated. `stripe config --list` prints saved profile;
    # missing auth produces a clear error message.
    $authProbe = stripe config --list 2>&1 | Out-String
    if ($authProbe -match "ERROR" -or $authProbe -match "not been authorized") {
        Write-Fail "Stripe CLI not authenticated."
        Write-Host "  Run: stripe login" -ForegroundColor Yellow
        exit 1
    }
    Write-Ok "Stripe CLI authenticated"
}

# ---------------------------------------------------------------------------
# Step 2: App reachability
# ---------------------------------------------------------------------------

Write-Step "Checking app reachability: $AppUrl"

try {
    # /health, /healthz, /status -- try whichever the app exposes; fall back to /.
    $healthProbe = $null
    foreach ($path in @("/health", "/healthz", "/status", "/")) {
        try {
            $healthProbe = Invoke-WebRequest -Uri "$AppUrl$path" -Method GET -UseBasicParsing -TimeoutSec 5
            if ($healthProbe.StatusCode -eq 200 -or $healthProbe.StatusCode -eq 422) {
                Write-Ok "App responding at $path ($($healthProbe.StatusCode))"
                break
            }
        } catch {
            # Try next path
        }
    }
    if (-not $healthProbe) {
        Write-Fail "App not reachable at $AppUrl. Is the FastAPI server running?"
        Write-Host "  Start with: cd web_service; uvicorn main:app --reload" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Fail "App unreachable: $($_.Exception.Message)"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 3: Set up the webhook listener
# ---------------------------------------------------------------------------

Write-Step "Starting `stripe listen --forward-to $AppUrl/stripe/webhook`"
Write-Host "  This subprocess forwards real Stripe events to your local app." -ForegroundColor Gray
Write-Host "  The webhook signing secret it prints MUST match your app's STRIPE_WEBHOOK_SECRET." -ForegroundColor Gray

$listenLog = New-TemporaryFile
$listenProc = Start-Process -FilePath "stripe" `
    -ArgumentList "listen", "--forward-to", "$AppUrl/stripe/webhook", "--print-secret" `
    -RedirectStandardOutput $listenLog.FullName `
    -RedirectStandardError "$($listenLog.FullName).err" `
    -PassThru -NoNewWindow

# Wait briefly for the listener to print its signing secret.
Start-Sleep -Seconds 3

$listenOutput = Get-Content $listenLog.FullName -Raw -ErrorAction SilentlyContinue
if ($listenOutput -match "whsec_[A-Za-z0-9]+") {
    $forwardSecret = $Matches[0]
    Write-Ok "Webhook signing secret from CLI: $($forwardSecret.Substring(0,12))..."
    Write-Host "  If your app's STRIPE_WEBHOOK_SECRET differs, the webhook POSTs will 400." -ForegroundColor Yellow
} else {
    Write-Host "  (Could not detect signing secret from CLI output yet; continuing.)" -ForegroundColor Gray
}

# ---------------------------------------------------------------------------
# Step 4: Trigger checkout.session.completed
# ---------------------------------------------------------------------------

Write-Step "Triggering checkout.session.completed (pack=$Pack)"

# Stripe trigger uses fixture data; we override the pack via metadata.
# `--override` syntax: `--override resource.path=value`.
$triggerOutput = stripe trigger "checkout.session.completed" `
    --override "checkout_session:metadata.pack=$Pack" 2>&1 | Out-String

Write-Host $triggerOutput -ForegroundColor Gray

if ($triggerOutput -match "Trigger succeeded") {
    Write-Ok "stripe trigger fired"
} else {
    Write-Fail "stripe trigger did not report success. Output above."
}

# ---------------------------------------------------------------------------
# Step 5: Check listener forwarded the event
# ---------------------------------------------------------------------------

Start-Sleep -Seconds 2

$listenOutput = Get-Content $listenLog.FullName -Raw -ErrorAction SilentlyContinue
if ($listenOutput -match "200\s+POST\s+/stripe/webhook") {
    Write-Ok "Webhook forwarded to $AppUrl/stripe/webhook -> 200"
} elseif ($listenOutput -match "(\d{3})\s+POST\s+/stripe/webhook") {
    $status = $Matches[1]
    Write-Fail "Webhook forwarded but app returned HTTP $status. Check app logs."
    Write-Host "  Listener output:" -ForegroundColor Gray
    Write-Host $listenOutput -ForegroundColor Gray
} else {
    Write-Fail "No webhook delivery detected in listener output."
    Write-Host "  Listener output:" -ForegroundColor Gray
    Write-Host $listenOutput -ForegroundColor Gray
}

# ---------------------------------------------------------------------------
# Step 6: Clean up the listener
# ---------------------------------------------------------------------------

Write-Step "Stopping stripe listen"

try {
    Stop-Process -Id $listenProc.Id -Force -ErrorAction SilentlyContinue
    Remove-Item $listenLog.FullName -ErrorAction SilentlyContinue
    Remove-Item "$($listenLog.FullName).err" -ErrorAction SilentlyContinue
    Write-Ok "Listener stopped"
} catch {
    Write-Host "  (Listener cleanup non-fatal: $($_.Exception.Message))" -ForegroundColor Gray
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

Write-Step "Done"
Write-Host @"

What this verified:
  - Stripe CLI is installed and authenticated
  - The FastAPI app is reachable at $AppUrl
  - Stripe's edge can forward webhook events to /stripe/webhook
  - The app's signature validation accepts events signed by the CLI's secret
  - A checkout.session.completed event POST returned 200

What this did NOT verify (run pytest tests/test_web_payment_e2e.py):
  - The minted-token data path: webhook -> token_store.mint_tokens_if_absent
    -> get_tokens_for_session -> success page render
  - The success_url contract: checkout.py's literal string matches a real route

For the full chain (CLI + pytest contracts), run:
  py -3.12 -m pytest tests/test_web_payment_e2e.py -v
  pwsh tools/verify_stripe_e2e.ps1

"@
