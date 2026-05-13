#Requires -Version 7.0
<#
.SYNOPSIS
Sync ebook_patterns.db from desktop to Hetzner VM over Tailscale SSH.

.DESCRIPTION
One-way desktop → VM sync using WSL rsync with --checksum to avoid
unnecessary 186MB transfers. Verifies row counts for fix_patterns,
book_overrides, and source_profiles after each sync.

.PARAMETER RemoteHost
Tailscale MagicDNS hostname of the VM (default: claude-dev-01).

.PARAMETER RemoteUser
SSH user on the VM (default: joe).

.PARAMETER RemotePath
Destination directory on the VM (default: ~/EbookAutomation/data/).

.PARAMETER LocalDb
Full Windows path to the local ebook_patterns.db (default: project data/).

.PARAMETER Register
Install a daily 2am Windows Task Scheduler job for this script.

.PARAMETER Unregister
Remove the Task Scheduler job created by -Register.

.PARAMETER SkipVerify
Skip the post-sync row-count verification step.

.EXAMPLE
# Manual sync with verification
pwsh -File tools\sync_pattern_db.ps1

.EXAMPLE
# Register daily Task Scheduler job (run once as admin)
pwsh -File tools\sync_pattern_db.ps1 -Register

.EXAMPLE
# Run from overnight batch (called automatically via Phase 0)
pwsh -File tools\sync_pattern_db.ps1 -SkipVerify:$false
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$RemoteHost = 'claude-dev-01',
    [string]$RemoteUser = 'joe',
    [string]$RemotePath = '~/EbookAutomation/data/',
    [string]$LocalDb    = 'F:\Projects\EbookAutomation\data\ebook_patterns.db',
    [switch]$Register,
    [switch]$Unregister,
    [switch]$SkipVerify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TaskName = 'EbookAutomation - Pattern DB Sync'

# ---------- helpers ----------

function Write-SyncLog {
    param([string]$Message, [string]$Level = 'INFO')
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "$ts [$Level] $Message"
}

function ConvertTo-WslPath {
    param([string]$WinPath)
    # F:\Projects\foo -> /mnt/f/Projects/foo
    $drive = $WinPath[0].ToString().ToLower()
    $rest  = $WinPath.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$rest"
}

# ---------- Task Scheduler registration ----------

if ($Unregister) {
    Write-SyncLog "Removing Task Scheduler job: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-SyncLog "Done."
    exit 0
}

if ($Register) {
    $scriptPath = $MyInvocation.MyCommand.Path
    Write-SyncLog "Registering daily Task Scheduler job: $TaskName"
    Write-SyncLog "Script: $scriptPath"

    $action  = New-ScheduledTaskAction `
        -Execute 'pwsh.exe' `
        -Argument "-NonInteractive -File `"$scriptPath`""

    $trigger = New-ScheduledTaskTrigger -Daily -At '02:00AM'

    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable

    $principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Highest

    Register-ScheduledTask `
        -TaskName  $TaskName `
        -Action    $action `
        -Trigger   $trigger `
        -Settings  $settings `
        -Principal $principal `
        -Force | Out-Null

    Write-SyncLog "Job registered: runs daily at 02:00 AM."
    Write-SyncLog "Verify in Task Scheduler or: Get-ScheduledTask -TaskName '$TaskName'"
    exit 0
}

# ---------- preflight ----------

if (-not (Test-Path $LocalDb)) {
    Write-SyncLog "LOCAL DB NOT FOUND: $LocalDb" 'ERROR'
    exit 1
}

$wslRsync = (wsl which rsync 2>$null)
if (-not $wslRsync) {
    Write-SyncLog "wsync not found in WSL. Install with: wsl sudo apt-get install rsync" 'ERROR'
    exit 1
}

$remote = "${RemoteUser}@${RemoteHost}"
$wslLocalDb = ConvertTo-WslPath $LocalDb

Write-SyncLog "Source:  $LocalDb  ($([math]::Round((Get-Item $LocalDb).Length / 1MB, 1)) MB)"
Write-SyncLog "Dest:    ${remote}:$RemotePath"
Write-SyncLog "Via:     WSL rsync $wslRsync"

# ---------- connectivity check ----------

Write-SyncLog "Checking Tailscale reachability..."
$pingResult = wsl timeout 5 ping -c 1 $RemoteHost 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-SyncLog "Cannot reach $RemoteHost via Tailscale. Is Tailscale running?" 'ERROR'
    Write-SyncLog $pingResult 'ERROR'
    exit 1
}
Write-SyncLog "Host reachable."

# ---------- local row counts (pre-sync reference) ----------

$verifyTables = @('fix_patterns', 'book_overrides', 'source_profiles')
$localCounts  = @{}

foreach ($tbl in $verifyTables) {
    $count = py -3.12 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
print(conn.execute('SELECT COUNT(*) FROM $tbl').fetchone()[0])
conn.close()
" $LocalDb 2>$null
    $localCounts[$tbl] = [int]$count
    Write-SyncLog "  Local ${tbl}: $count rows"
}

# ---------- rsync ----------

Write-SyncLog "Starting rsync (--checksum)..."
$rsyncStart = Get-Date

# -a  archive (recursive + preserve perms/times)
# -v  verbose
# -z  compress
# --checksum  compare checksums, not mtime+size (correct for SQLite)
# --stats     summary at end
# --no-perms  don't attempt to set Windows NTFS perms on remote side
$rsyncArgs = @(
    'rsync',
    '--checksum',
    '-avz',
    '--stats',
    '--no-perms',
    '-e', 'ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes',
    $wslLocalDb,
    "${remote}:${RemotePath}"
)

wsl @rsyncArgs
$rsyncExit = $LASTEXITCODE
$rsyncElapsed = [int]((Get-Date) - $rsyncStart).TotalSeconds

if ($rsyncExit -ne 0) {
    Write-SyncLog "rsync FAILED (exit=$rsyncExit, ${rsyncElapsed}s)" 'ERROR'
    Write-SyncLog "Check SSH access: wsl ssh $remote" 'ERROR'
    exit 1
}

Write-SyncLog "rsync complete in ${rsyncElapsed}s"

# ---------- post-sync verification ----------

if ($SkipVerify) {
    Write-SyncLog "Verification skipped (-SkipVerify)."
    exit 0
}

Write-SyncLog "Verifying row counts on $RemoteHost..."
$verifyFailed = $false

foreach ($tbl in $verifyTables) {
    # Pipe Python code via stdin to avoid shell escaping across WSL/SSH layers.
    $pyCode = "import sqlite3; conn=sqlite3.connect('/home/${RemoteUser}/EbookAutomation/data/ebook_patterns.db'); print(conn.execute('SELECT COUNT(*) FROM ${tbl}').fetchone()[0])"
    $remoteCount = ($pyCode | wsl ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes "${remote}" 'python3 -')

    $remoteCount = [int]($remoteCount -replace '\s', '')
    $localCount  = $localCounts[$tbl]

    if ($remoteCount -eq $localCount) {
        Write-SyncLog "  OK  $tbl : local=$localCount  remote=$remoteCount"
    } else {
        Write-SyncLog "  MISMATCH  $tbl : local=$localCount  remote=$remoteCount" 'WARN'
        $verifyFailed = $true
    }
}

if ($verifyFailed) {
    Write-SyncLog "Row count mismatch detected — sync may be incomplete." 'WARN'
    exit 2
}

Write-SyncLog "Verification passed. DB is consistent on $RemoteHost."
exit 0
