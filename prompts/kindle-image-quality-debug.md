# EB-17 FIX #3: Images Appear as Blank/Broken in KFX — Debug Extracted Image Quality

## Session Name
kindle-image-quality-debug

## Claude Code Model
**Opus** — Diagnosing image extraction quality issues across PyMuPDF, file system, and Calibre.

## Ticket
EB-17 — Image Preservation in PDF-to-Kindle (third fix round)

## Problem
After commits `60a5bfa` and `1db0d0c`, images ARE being referenced in the KFX output — `<figure>` tags with captions (Figure 2.1, Figure 2.2, etc.) appear correctly. However the actual images are **blank or broken**. 

When examining the extracted image files, they are tiny (e.g., `image_rsrcP.jpg` at 48×48 pixels). This is NOT a real photograph — it's a thumbnail, SMask artifact, or corrupt extraction. The `min_width=100` filter should have rejected 48×48 images, so either:
1. PyMuPDF metadata reports a larger size than the actual extracted data
2. The extraction is pulling SMask/alpha masks instead of the real image XObjects
3. The image file is written incorrectly (truncated, wrong format)
4. Calibre is seeing the path but can't decode the image content

The 666 "extracted images" from Astronomy-LR are likely almost all artifacts, not real content images.

## CRITICAL: Debug-first, verify-with-proof approach

Same rules as previous sessions. Must show ACTUAL image dimensions and file sizes of extracted images, and must confirm at least one real photograph renders in the KFX.

## Phase 1: Inspect the extracted images (READ ONLY)

### 1a. Find the .intermediates directory
```powershell
Get-ChildItem -Path "F:\Projects\EbookAutomation\output\kindle" -Recurse -Directory -Filter ".intermediates"
Get-ChildItem -Path "F:\Projects\EbookAutomation\output\kindle" -Recurse -Directory -Filter "images"
```

### 1b. Inspect actual image files
```powershell
# List ALL image files with sizes
$imagesDir = "F:\Projects\EbookAutomation\output\kindle\.intermediates\images"  # adjust path
Get-ChildItem $imagesDir | Sort-Object Length | Select-Object Name, Length, @{N='KB';E={[math]::Round($_.Length/1KB,1)}} | Format-Table -AutoSize

# Count by size buckets
$images = Get-ChildItem $imagesDir
Write-Host "Total: $($images.Count)"
Write-Host "Under 1KB: $(($images | Where-Object { $_.Length -lt 1024 }).Count)"
Write-Host "1-5KB: $(($images | Where-Object { $_.Length -ge 1024 -and $_.Length -lt 5120 }).Count)"
Write-Host "5-50KB: $(($images | Where-Object { $_.Length -ge 5120 -and $_.Length -lt 51200 }).Count)"
Write-Host "50KB+: $(($images | Where-Object { $_.Length -ge 51200 }).Count)"
```

### 1c. Check actual image dimensions (not just metadata)
Write a quick Python script to verify actual pixel dimensions:
```python
import os, sys
from pathlib import Path

try:
    import fitz  # PyMuPDF can read images too
except ImportError:
    pass

images_dir = sys.argv[1] if len(sys.argv) > 1 else "."
for f in sorted(Path(images_dir).glob("*")):
    if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff'):
        size_kb = f.stat().st_size / 1024
        # Try to get actual dimensions
        try:
            from PIL import Image
            with Image.open(f) as img:
                w, h = img.size
                print(f"{f.name:40s}  {w:5d}x{h:<5d}  {size_kb:8.1f} KB")
        except:
            print(f"{f.name:40s}  ???x???    {size_kb:8.1f} KB")
```

### 1d. Read the extract_pdf_images() function
Use `grep -n "def extract_pdf_images"` to find it, then read the full function. Specifically check:
- How does it extract images? `doc.extract_image(xref)` or something else?
- What size does it check — the metadata width/height or the actual decoded pixel dimensions?
- Does it filter out SMask images? (SMask = soft mask / alpha channel — these are NOT content images)
- Does it skip images with `/Subtype /SMask` or `/Subtype /Mask`?

### 1e. Check PyMuPDF's image list for Astronomy
Run this diagnostic on Astronomy-LR.pdf to see what PyMuPDF actually reports:
```python
import fitz
doc = fitz.open(r"C:\Users\Joe\Downloads\Astronomy-LR.pdf")
# Check first 10 pages
for page_num in range(min(10, len(doc))):
    page = doc[page_num]
    images = page.get_images(full=True)
    for img in images:
        xref, smask, w, h, bpc, cs, alt, name, ref_name = img[:9] if len(img) >= 9 else img + (None,) * (9 - len(img))
        img_data = doc.extract_image(xref)
        actual_size = len(img_data['image']) if img_data else 0
        ext = img_data.get('ext', '?') if img_data else '?'
        actual_w = img_data.get('width', 0) if img_data else 0
        actual_h = img_data.get('height', 0) if img_data else 0
        print(f"Page {page_num+1}: xref={xref}, smask={smask}, reported={w}x{h}, actual={actual_w}x{actual_h}, size={actual_size/1024:.1f}KB, ext={ext}, cs={cs}")
doc.close()
```

Key things to look for:
- **smask != 0**: If the `smask` field in `get_images()` output is non-zero, this image has a soft mask. The smask xref is often extracted as a separate grayscale image — this is NOT a content image.
- **Colorspace**: `cs` should be DeviceRGB or similar for real images. If it's DeviceGray and tiny, it's likely an SMask.
- **reported vs actual dimensions**: Do they match?

## Phase 2: Document findings

Before making changes, write down:
- How many of the 666 images are real content images vs artifacts/SMasks
- What the actual file sizes and dimensions are
- What the filtering logic currently does vs what it should do

## Phase 3: Fix

Based on Phase 1 findings, likely fixes:

### If SMask xrefs are being extracted as separate images:
PyMuPDF's `page.get_images(full=True)` returns tuples where index [1] is the smask xref. Filter these out:
```python
seen_smasks = set()
for img in image_list:
    smask_xref = img[1]  # smask xref, 0 if none
    if smask_xref:
        seen_smasks.add(smask_xref)

# Then skip any image whose xref is in seen_smasks
for img in image_list:
    xref = img[0]
    if xref in seen_smasks:
        continue  # This is a mask, not a content image
```

### If metadata dimensions don't match actual extracted dimensions:
Use the actual dimensions from `doc.extract_image(xref)` for filtering, not the reported dimensions from `get_images()`:
```python
img_data = doc.extract_image(xref)
actual_w = img_data['width']
actual_h = img_data['height']
actual_size_kb = len(img_data['image']) / 1024
if actual_w < min_width or actual_h < min_height or actual_size_kb < min_size_kb:
    skipped_tiny += 1
    continue
```

### If images are being saved in wrong format:
Check that the file extension matches the actual image data. PyMuPDF's `extract_image()` returns an `ext` field — use it:
```python
ext = img_data['ext']  # 'png', 'jpeg', etc.
filename = f"img_p{page+1}_{idx}.{ext}"
with open(filepath, 'wb') as f:
    f.write(img_data['image'])
```

### Additional quality filters to add:
- Skip images with `bpc` (bits per component) = 1 (these are masks/stamps)
- Skip images where colorspace is DeviceGray AND dimensions are small
- Skip images that are exact duplicates by content hash (not just xref)

## Phase 4: Verify with proof

### Run the diagnostic BEFORE and AFTER the fix:
```powershell
# AFTER fix — reconvert
Import-Module .\module\EbookAutomation.psd1 -Force
Convert-ToKindle -InputFile "C:\Users\Joe\Downloads\Astronomy-LR.pdf"

# Check extracted images
$imagesDir = # find the images dir
$images = Get-ChildItem $imagesDir
Write-Host "Total images: $($images.Count)"
Write-Host "Under 1KB: $(($images | Where-Object { $_.Length -lt 1024 }).Count)"
Write-Host "50KB+: $(($images | Where-Object { $_.Length -ge 51200 }).Count)"
Write-Host "Largest: $(($images | Sort-Object Length -Descending | Select-Object -First 1).Name) — $([math]::Round(($images | Sort-Object Length -Descending | Select-Object -First 1).Length/1KB,0)) KB"
```

### Open the HTML in a browser
Open the intermediate HTML in a browser. Do real images render (photographs, diagrams, maps)?

### Open the KFX in Kindle Previewer
Do real images render? Not just placeholders — actual photographs of astronomical objects, diagrams, etc.

### Required proof:
- [ ] At least 10 images over 50KB in the images/ directory (real photos are typically 50-500KB)
- [ ] HTML shows real photographs when opened in browser
- [ ] KFX shows real photographs when opened in Kindle Previewer
- [ ] Total image count is LOWER than 666 (proving the artifact filtering works)
- [ ] 39/41 tests still pass

**DO NOT mark complete without these specific numbers and confirmations.**

## Phase 5: Commit
```
git add -A
git commit -m "fix: EB-17 — filter SMask artifacts and validate extracted image quality"
git push
```

## Phase 6: Jira
Add comment to EB-17 with root cause and verified image counts/sizes.

## Test file
Astronomy-LR.pdf — 1,197 pages, 331 meaningful images per scan-image-density.py (which used different filtering). Expect the corrected extraction to find somewhere between 50-300 real content images.
