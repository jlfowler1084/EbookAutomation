# EB-17 FIX #2: Images in HTML but Not in KFX — Debug Calibre Handoff

## Session Name
kindle-image-calibre-debug

## Claude Code Model
**Opus** — Multi-layer debugging across Python image extraction, PSM1 file handling, and Calibre conversion.

## Ticket
EB-17 — Image Preservation in PDF-to-Kindle (second fix round)

## Problem
After commit `1327553`, images ARE being extracted and inserted into intermediate HTML correctly (confirmed: Brother of Jesus HTML shows images in browser). However:

1. **Images do NOT appear in the final KFX output** — Kindle shows pure text, no images
2. **Astronomy-LR has no HTML file at all** — only a .kfx was produced, no intermediate HTML alongside it. The quality report also has no image-related fields.

The image extraction and HTML insertion work. The bug is somewhere between "HTML with images" and "KFX file on disk."

## CRITICAL: Debug-first, verify-with-proof approach

Same rules as last session: DO NOT claim fixed without concrete evidence. Must show image counts in both HTML AND KFX.

## Phase 1: Trace the Calibre handoff (READ ONLY)

### 1a. Where does Calibre get invoked?
Find the `ebook-convert` invocation in `EbookAutomation.psm1`. The key line is approximately:
```powershell
$argString = "`"$convertInput`" `"$outFile`""
```
At this exact moment:
- What is `$convertInput`? (Full path — is it in a temp dir? A filtered copy?)
- What is `$outFile`? (The final .kfx path)
- Does an `images/` subdirectory exist alongside `$convertInput`?

### 1b. Does filtering break image paths?
The filter step (filter_content.py) creates a `.filtered.html` copy. Check:
- Is `$convertInput` the original HTML or the filtered copy?
- If it's the filtered copy, does the filtered HTML still contain `<figure>` and `<img>` tags? (It should, since `-NoImages` wasn't passed)
- Is the filtered HTML in the same directory as the `images/` folder?

### 1c. Does Calibre receive the images directory?
Calibre resolves `<img src="images/filename.jpg">` relative to the input HTML's directory. Check:
- Is the `images/` directory in the same folder as whichever HTML file Calibre actually receives?
- Run a test: Add a temporary log line RIGHT BEFORE the Calibre invocation:
```powershell
Write-EbookLog "DEBUG: convertInput = $convertInput"
Write-EbookLog "DEBUG: images dir exists = $(Test-Path (Join-Path (Split-Path $convertInput) 'images'))"
Write-EbookLog "DEBUG: images count = $((Get-ChildItem (Join-Path (Split-Path $convertInput) 'images') -File -ErrorAction SilentlyContinue | Measure-Object).Count)"
```

### 1d. Why does Astronomy have no HTML?
Check these possibilities:
- Is Astronomy going through a cache hit path that serves pre-extracted text?
- Is the `_inject_images_into_html()` post-processor actually running?
- Is the HTML written to a temp dir that gets cleaned up?
- Check: after conversion completes, where does the output go? Is there a copy step that preserves HTML alongside the KFX?

### 1e. Check Calibre's image handling
Look at the Calibre options in `settings.json` — is there a `--no-images` flag?
```powershell
grep -i "image\|no.image" config/settings.json
```
Also check if the output format matters — KFX via Calibre may handle images differently than EPUB.

## Phase 2: Document specific findings

Write down:
- The exact path of `$convertInput` when Calibre runs
- Whether `images/` directory exists at that path at Calibre invocation time
- How many image files are in that directory
- Whether the filtered HTML still has `<img>` tags
- What Calibre's stderr output says about images (if anything)
- Why Astronomy specifically has no HTML output

## Phase 3: Fix

Based on findings, likely fixes include:

**If images/ directory isn't alongside the HTML Calibre receives:**
- Copy or move the images/ directory to be alongside whichever HTML file Calibre actually processes (could be the filtered copy)

**If Calibre strips images during KFX conversion:**
- Try converting to EPUB first, then EPUB→KFX as a two-step
- Or add Calibre flags to preserve images: `--keep-images` or check if there's a conversion option

**If the filtered HTML loses images:**
- Ensure filter_content.py preserves `<figure>/<img>` tags when `-NoImages` is NOT set

**If Astronomy has no HTML because of caching:**
- Ensure the cache-hit path still produces an HTML file (not just TXT)
- Ensure `_inject_images_into_html()` runs and the result is written to disk

**If the temp dir cleanup removes the HTML before it can be inspected:**
- Copy the HTML + images/ to the final output directory alongside the KFX for debugging
- This is also useful long-term: users may want to inspect or edit the HTML

## Phase 4: Verify with proof

### Test 1: Convert Astronomy-LR and verify images in KFX
```powershell
Import-Module .\module\EbookAutomation.psd1 -Force
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\Astronomy-LR.pdf"
```

After conversion:
```powershell
# 1. Find all output files
Get-ChildItem -Path "F:\Projects\EbookAutomation\output\kindle" -Recurse -Filter "Astronomy*" | Format-Table FullName, Length

# 2. Check for images directory
Get-ChildItem -Path "F:\Projects\EbookAutomation\output\kindle" -Recurse -Directory -Filter "images" | Format-Table FullName

# 3. Count figure tags in HTML (if HTML exists)
$htmlFile = Get-ChildItem -Path "F:\Projects\EbookAutomation\output\kindle" -Recurse -Filter "Astronomy*.html" | Select-Object -First 1
if ($htmlFile) {
    $content = Get-Content $htmlFile.FullName -Raw
    $figCount = ([regex]::Matches($content, '<figure>')).Count
    $imgCount = ([regex]::Matches($content, '<img ')).Count
    Write-Host "HTML: $figCount figure tags, $imgCount img tags"
} else {
    Write-Host "NO HTML FILE FOUND"
}

# 4. Check KFX size (images should make it larger)
Get-ChildItem -Path "F:\Projects\EbookAutomation\output\kindle" -Recurse -Filter "Astronomy*.kfx" | Format-Table FullName, @{N='SizeMB';E={[math]::Round($_.Length/1MB,1)}}
```

### Test 2: Verify images render on Kindle
Open the KFX file in Kindle Previewer or send to Kindle Scribe. Do images appear?

### Required proof before marking complete:
- [ ] Astronomy-LR HTML exists with X `<figure>` tags
- [ ] `images/` directory exists with Y image files
- [ ] KFX file size is significantly larger than text-only version
- [ ] At least one image confirmed visible when KFX is opened
- [ ] 39/41 tests still pass (or better)

**DO NOT mark complete without reporting these specific numbers.**

## Phase 5: Commit
```
git add -A
git commit -m "fix: EB-17 — ensure images survive Calibre HTML-to-KFX conversion"
git push
```

## Phase 6: Jira
Add comment to EB-17 with root cause and image counts. Do NOT transition (already Done).

## Key files
- `module/EbookAutomation.psm1` — Calibre invocation, temp dir management, file copying
- `tools/pdf_to_balabolka.py` — `extract_pdf_images()`, `process_kindle_html()`, `_inject_images_into_html()`
- `tools/filter_content.py` — `_strip_images()` (should only strip when `--no-images` is passed)
- `config/settings.json` — Calibre options

## Reminders
- Use `grep -n` for all line lookups
- The temp dir pattern is `ebook_kindle_YYYYMMDD_HHmmss` in `$env:TEMP`
- PyMuPDF = 0-based pages, para_dicts = 1-based page_number
- Astronomy-LR has 331 meaningful images per scan — expect dozens after filtering
