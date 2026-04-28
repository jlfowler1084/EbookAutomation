# LAME MP3 Encoder Installation

## Why LAME?

balcon.exe synthesises speech to raw PCM and writes it to stdout. To produce
an MP3 file, the raw PCM is piped to `lame.exe`, which encodes it:

```
balcon -f book.txt -o --raw -fr 22 | lame -r -s 22.05 -m m -h - book.mp3
```

LAME is NOT bundled with balcon for licensing reasons (see below). It must be
installed separately.

## What the install script does

`tools\install-lame.ps1` installs LAME by trying two methods in order:

1. **winget** (preferred) - installs `LAME.LAME` 3.100.1 from the Windows
   Package Manager repository. This places `lame.exe` on PATH via the winget
   links directory (`%LOCALAPPDATA%\Microsoft\WinGet\Links\`).

2. **Direct download fallback** - if winget is unavailable (e.g., older
   Windows Server), the script downloads the official 3.100 Windows x64 zip
   from SourceForge and extracts `lame.exe` into `tools\balcon\`. balcon checks
   its own directory before PATH, so the bundled binary is found automatically.

After installation the script verifies `lame --version` (must exit 0) and runs
a WAV pipe smoke test if balcon.exe is present.

## Running the installer

```powershell
# Standard install (runs smoke test if balcon.exe is present):
pwsh -File tools\install-lame.ps1

# Skip the smoke test (useful on CI with no SAPI voice):
pwsh -File tools\install-lame.ps1 -SkipSmoke

# Re-install even if already present:
pwsh -File tools\install-lame.ps1 -Force
```

## Where lame.exe ends up

| Scenario | Location |
|---|---|
| winget install succeeded | `%LOCALAPPDATA%\Microsoft\WinGet\Links\lame.exe` (on PATH) |
| Fallback direct download | `tools\balcon\lame.exe` (found by balcon before PATH check) |

## Verifying the install

After running the script, open a new PowerShell session and run:

```powershell
lame --version
```

Expected output begins with:
```
LAME 64bits version 3.100.1 (https://lame.sourceforge.io)
```

For a full round-trip test:

```powershell
$balcon = 'F:\Projects\EbookAutomation\tools\balcon\balcon.exe'
$out    = "$env:TEMP\test.mp3"
'Hello world.' | Set-Content "$env:TEMP\test.txt" -Encoding UTF8
cmd /c "`"$balcon`" -f `"$env:TEMP\test.txt`" -o --raw -fr 22 | lame -r -s 22.05 -m m -h - `"$out`""
(Get-Item $out).Length   # should be > 0
```

## Licensing note

LAME is distributed under the **GNU Library General Public License (LGPL)
version 2 or later**. Because of this license, LAME is not bundled directly
with balcon (which is freeware) or with this project's repository. The winget
install fetches the binary from the official LAME project; the direct-download
fallback also fetches from the official SourceForge mirror.

Full license text: https://www.gnu.org/licenses/old-licenses/lgpl-2.0.html
LAME homepage: https://lame.sourceforge.io/

## Pipeline integration

The EbookAutomation pipeline currently uses **ffmpeg** (not LAME) for the
WAV-to-MP3 encoding step in `Invoke-Balabolka`. LAME is installed here to
enable the direct balcon-pipe-to-lame invocation pattern documented in
balcon's readme, which is useful for:

- Manual one-shot conversions via the command line
- Alternative encoding pipeline if ffmpeg is unavailable
- Third-party scripts that call `balcon ... | lame ...` directly

See `tools\install-lame.ps1` for the full installer source.
