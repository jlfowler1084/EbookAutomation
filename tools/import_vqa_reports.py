#!/usr/bin/env python3
"""Import existing VQA report JSON files into the pattern database.

Scans output/kindle/ (or a specified directory) for *_visual_qa_report*.json
files and imports them into the SQLite pattern database, seeding it with
historical data from prior test runs.

Usage:
    python tools/import_vqa_reports.py                     # Scan default output/kindle/
    python tools/import_vqa_reports.py --dir "F:\\other"    # Scan specific directory
    python tools/import_vqa_reports.py --dry-run            # Show what would be imported
"""

import argparse
import json
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SCAN_DIR = _PROJECT_ROOT / "output" / "kindle"

# Import from sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pattern_db


def _parse_metadata_from_filename(filename):
    """Parse title and author from ebook filename.

    Handles patterns like:
        "Title - Author.ext"
        "Title - Subtitle - Author.ext"
        "Title.ext"
    """
    stem = Path(filename).stem

    # Remove VQA report suffixes
    for suffix in ('_visual_qa_report', '_visual_qa_report_LEGACY',
                   '_visual_qa_report_HTML'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]

    parts = stem.rsplit(' - ', 1)
    if len(parts) == 2:
        title = parts[0].strip()
        author = parts[1].strip()
    else:
        title = stem.strip()
        author = None

    return title, author


def _guess_extraction_path(report_path):
    """Guess extraction path from the report filename."""
    name = report_path.stem.lower()
    if '_legacy' in name:
        return 'legacy'
    elif '_html' in name:
        return 'html_extraction'
    elif '_column' in name:
        return 'column_aware'
    return 'html_extraction'


def find_reports(scan_dir):
    """Find all VQA report JSON files in a directory."""
    scan_path = Path(scan_dir)
    if not scan_path.exists():
        return []
    return sorted(scan_path.glob("*_visual_qa_report*.json"))


def import_report(report_path, db_path=None, dry_run=False):
    """Import a single VQA report into the database.

    Returns a dict with import summary, or None on error.
    """
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  Error reading {report_path}: {e}", file=sys.stderr)
        return None

    book_filename = report.get("book", report_path.stem)
    title, author = _parse_metadata_from_filename(book_filename)
    fmt = Path(book_filename).suffix.lstrip('.') or 'kfx'
    page_count = report.get("pages_total")
    vqa_score = report.get("overall_score")
    extraction_path = _guess_extraction_path(report_path)

    token_usage = report.get("token_usage", {})
    input_tokens = token_usage.get("input_tokens", 0)
    output_tokens = token_usage.get("output_tokens", 0)
    cost = token_usage.get("estimated_cost_usd", 0)

    # Count issues
    issue_count = sum(
        len(page.get("issues", []))
        for page in report.get("pages", [])
    )

    summary = {
        "report_path": str(report_path),
        "book_filename": book_filename,
        "title": title,
        "author": author,
        "format": fmt,
        "page_count": page_count,
        "extraction_path": extraction_path,
        "vqa_score": vqa_score,
        "issue_count": issue_count,
        "cost_usd": cost,
    }

    if dry_run:
        return summary

    # Actually import
    book_id = pattern_db.get_or_create_book(
        book_filename,
        title=title,
        author=author,
        format=fmt,
        page_count=page_count,
        db_path=db_path,
    )

    conv_id = pattern_db.add_conversion(
        book_id=book_id,
        extraction_path=extraction_path,
        vqa_score=vqa_score,
        vqa_report_path=str(report_path),
        api_input_tokens=input_tokens,
        api_output_tokens=output_tokens,
        cost_usd=cost,
        db_path=db_path,
    )

    actual_issues = pattern_db.add_issues_from_vqa_report(
        conv_id, book_id, report, db_path=db_path
    )

    summary["book_id"] = book_id
    summary["conversion_id"] = conv_id
    summary["issue_count"] = actual_issues
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Import VQA reports into the pattern database"
    )
    parser.add_argument(
        '--dir', default=str(_DEFAULT_SCAN_DIR),
        help=f"Directory to scan for VQA reports (default: {_DEFAULT_SCAN_DIR})"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Show what would be imported without modifying the database"
    )
    parser.add_argument(
        '--db-path', default=None,
        help="Database path (default: data/ebook_patterns.db)"
    )
    args = parser.parse_args()

    reports = find_reports(args.dir)
    if not reports:
        print(f"No VQA reports found in: {args.dir}")
        sys.exit(0)

    print(f"Found {len(reports)} VQA report(s) in: {args.dir}")
    if args.dry_run:
        print("(DRY RUN - no changes will be made)\n")
    else:
        # Ensure DB exists
        pattern_db.init_db(args.db_path)
        print()

    imported = 0
    skipped = 0
    total_issues = 0
    total_cost = 0.0

    for report_path in reports:
        result = import_report(report_path, db_path=args.db_path,
                               dry_run=args.dry_run)
        if result is None:
            skipped += 1
            continue

        imported += 1
        total_issues += result.get("issue_count", 0)
        total_cost += result.get("cost_usd", 0)

        score_str = str(result.get("vqa_score", '?'))
        name = result.get("title") or result.get("book_filename", "?")
        path = result.get("extraction_path", "?")
        issues = result.get("issue_count", 0)

        if args.dry_run:
            print(f"  Would import: {name}")
            print(f"    Score: {score_str}, Path: {path}, "
                  f"Issues: {issues}, Cost: ${result.get('cost_usd', 0):.4f}")
        else:
            print(f"  Imported: {name}")
            print(f"    Book ID: {result.get('book_id')}, "
                  f"Conv ID: {result.get('conversion_id')}")
            print(f"    Score: {score_str}, Path: {path}, "
                  f"Issues: {issues}, Cost: ${result.get('cost_usd', 0):.4f}")

    print(f"\n{'=' * 50}")
    action = "Would import" if args.dry_run else "Imported"
    print(f"{action}: {imported} report(s), skipped: {skipped}")
    print(f"Total issues: {total_issues}")
    print(f"Total API cost: ${total_cost:.4f}")


if __name__ == '__main__':
    main()
