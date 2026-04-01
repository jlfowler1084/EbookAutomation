#!/usr/bin/env python3
"""Scan a folder of PDFs and report image density per book.

Identifies books with meaningful embedded images (maps, charts, illustrations)
vs. scanned books (1 image per page = full-page scan, not useful for testing).

Usage:
    python scan-image-density.py                          # scans inbox/
    python scan-image-density.py --folder "F:\Books"      # scans custom folder
    python scan-image-density.py --folder inbox --min-images 5
"""

import argparse
import json
import os
import sys
from pathlib import Path


def scan_pdf_images(pdf_path):
    """Count images per page using PyMuPDF. Returns detailed stats."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: python -m pip install pymupdf", file=sys.stderr)
        sys.exit(1)

    stats = {
        'path': str(pdf_path),
        'filename': pdf_path.name,
        'total_pages': 0,
        'total_images': 0,
        'pages_with_images': 0,
        'images_per_page': 0.0,
        'likely_scan': False,
        'meaningful_images': 0,  # images on pages that aren't full-page scans
        'page_details': [],      # per-page breakdown
        'error': None,
    }

    try:
        doc = fitz.open(str(pdf_path))
        stats['total_pages'] = len(doc)

        if len(doc) == 0:
            doc.close()
            return stats

        scan_pages = 0  # pages with exactly 1 large image (likely scans)

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            page_width = page.rect.width
            page_height = page.rect.height
            page_area = page_width * page_height

            page_info = {
                'page': page_num + 1,
                'image_count': len(image_list),
                'images': [],
            }

            meaningful_on_page = 0

            for img in image_list:
                xref = img[0]
                try:
                    img_meta = doc.extract_image(xref)
                    if img_meta:
                        w = img_meta.get('width', 0)
                        h = img_meta.get('height', 0)
                        size_kb = len(img_meta.get('image', b'')) / 1024

                        # Classify: tiny icon (<50px either dim), full-page scan, or meaningful
                        if w < 50 or h < 50:
                            category = 'icon'
                        elif w * h > page_area * 0.7:
                            category = 'full-page'
                        elif size_kb < 2:
                            category = 'tiny'
                        else:
                            category = 'meaningful'
                            meaningful_on_page += 1

                        page_info['images'].append({
                            'xref': xref,
                            'width': w,
                            'height': h,
                            'size_kb': round(size_kb, 1),
                            'category': category,
                        })
                except Exception:
                    pass

            stats['total_images'] += len(image_list)
            stats['meaningful_images'] += meaningful_on_page

            if len(image_list) > 0:
                stats['pages_with_images'] += 1

            # Detect scan pages: exactly 1 image that covers most of the page
            if len(image_list) == 1 and len(page_info['images']) == 1:
                if page_info['images'][0]['category'] == 'full-page':
                    scan_pages += 1

            if page_info['images']:  # only store pages that have images
                stats['page_details'].append(page_info)

        doc.close()

        stats['images_per_page'] = round(stats['total_images'] / stats['total_pages'], 2) if stats['total_pages'] > 0 else 0
        stats['likely_scan'] = scan_pages >= stats['total_pages'] * 0.7

    except Exception as e:
        stats['error'] = str(e)

    return stats


def main():
    parser = argparse.ArgumentParser(description='Scan PDFs for image density')
    parser.add_argument('--folder', default='inbox',
                        help='Folder to scan (default: inbox)')
    parser.add_argument('--min-images', type=int, default=3,
                        help='Minimum meaningful images to report (default: 3)')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON')
    parser.add_argument('--include-scans', action='store_true',
                        help='Include likely-scanned books in results')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show per-page image details for top candidates')
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_absolute():
        # Resolve relative to project root
        project_root = os.environ.get('EBOOK_AUTOMATION_ROOT',
                                       os.path.dirname(os.path.abspath(__file__)))
        folder = Path(project_root) / folder

    if not folder.exists():
        print(f"ERROR: Folder not found: {folder}", file=sys.stderr)
        sys.exit(1)

    pdfs = sorted(folder.glob('*.pdf'))
    if not pdfs:
        print(f"No PDF files found in {folder}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {len(pdfs)} PDFs in {folder}...\n")

    results = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"  [{i}/{len(pdfs)}] {pdf.name}...", end='', flush=True)
        stats = scan_pdf_images(pdf)
        results.append(stats)
        if stats['error']:
            print(f" ERROR: {stats['error']}")
        elif stats['likely_scan']:
            print(f" SCAN ({stats['total_pages']} pages, {stats['total_images']} images)")
        else:
            print(f" {stats['meaningful_images']} meaningful images / {stats['total_pages']} pages")

    # Filter and sort
    candidates = [r for r in results if not r['error']]
    if not args.include_scans:
        candidates = [r for r in candidates if not r['likely_scan']]
    candidates = [r for r in candidates if r['meaningful_images'] >= args.min_images]
    candidates.sort(key=lambda r: r['meaningful_images'], reverse=True)

    if args.json:
        # Strip page_details for clean JSON output unless verbose
        output = []
        for c in candidates:
            entry = {k: v for k, v in c.items() if k != 'page_details'}
            if args.verbose:
                entry['page_details'] = c['page_details']
            output.append(entry)
        print(json.dumps(output, indent=2))
        return

    # Display results
    print(f"\n{'='*80}")
    print(f"IMAGE DENSITY REPORT — {len(candidates)} books with {args.min_images}+ meaningful images")
    print(f"{'='*80}\n")

    if not candidates:
        print("No books found matching criteria. Try --min-images 1 or --include-scans")
        return

    print(f"{'Rank':<5} {'Meaningful':>10} {'Total':>8} {'Pages':>7} {'Img/Pg':>7}  {'Filename'}")
    print(f"{'-'*5} {'-'*10} {'-'*8} {'-'*7} {'-'*7}  {'-'*40}")

    for i, c in enumerate(candidates, 1):
        print(f"{i:<5} {c['meaningful_images']:>10} {c['total_images']:>8} "
              f"{c['total_pages']:>7} {c['images_per_page']:>7.2f}  {c['filename']}")

    # Show top 3 recommendations
    top = candidates[:5]
    print(f"\n{'='*80}")
    print("TOP TEST CANDIDATES (highest meaningful image count, not scans)")
    print(f"{'='*80}")
    for i, c in enumerate(top, 1):
        print(f"\n  {i}. {c['filename']}")
        print(f"     {c['meaningful_images']} meaningful images across {c['total_pages']} pages")
        print(f"     {c['pages_with_images']} pages contain at least one image")

        if args.verbose and c['page_details']:
            meaningful_pages = [p for p in c['page_details']
                                if any(img['category'] == 'meaningful' for img in p['images'])]
            if meaningful_pages:
                pages_str = ', '.join(str(p['page']) for p in meaningful_pages[:20])
                if len(meaningful_pages) > 20:
                    pages_str += f' ... (+{len(meaningful_pages)-20} more)'
                print(f"     Pages with meaningful images: {pages_str}")

    print(f"\nTo convert top candidates:")
    print(f"  Import-Module .\\module\\EbookAutomation.psd1")
    for c in top[:3]:
        stem = Path(c['filename']).stem
        print(f'  Convert-ToKindle -InputFile "inbox\\{c["filename"]}"')


if __name__ == '__main__':
    main()
