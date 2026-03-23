#!/usr/bin/env python
"""email_to_kindle.py -- Send an ebook file to a Kindle via Amazon's Send-to-Kindle email service.

Handles SMTP delivery with format-aware size routing:
  - EPUB: send directly, or try Calibre image compression if over limit
  - PDF <=25MB: send directly
  - PDF 25MB-max: ZIP and send
  - PDF ZIP still over max: compress via Ghostscript or PyMuPDF, re-ZIP
  - PDF still over max after compression: split into parts (max 5 parts)

Usage (called via PowerShell Start-Process):
    python tools/email_to_kindle.py \
        --file "output\\kindle\\Book.epub" \
        --kindle-address "name@kindle.com" \
        --smtp-server smtp.gmail.com \
        --smtp-port 587 \
        --smtp-user "sender@gmail.com" \
        --book-title "My Book" \
        --convert-subject \
        --split-max-mb 50

Outputs JSON to stdout for PowerShell to parse.
Exit codes: 0=success, 1=config error, 2=auth failure, 3=recipient rejected,
            4=size error, 5=network error, 6=unknown error
"""

import sys
import os
import argparse
import json
import logging
import math
import re
import shutil
import smtplib
import socket
import ssl
import subprocess
import tempfile
import time
import zipfile
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# --- Windows UTF-8 stdout/stderr --------------------------------------------------
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# --- Logging setup ----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='[EmailToKindle] %(levelname)s: %(message)s',
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

# Script location (used for temp file placement)
SCRIPT_DIR = Path(__file__).resolve().parent


# =================================================================================
# Compression helpers
# =================================================================================

def compress_pdf(input_path: str, output_path: str, ghostscript_path: str = None) -> int:
    """Compress a PDF using Ghostscript if available, otherwise PyMuPDF.

    Returns the size of the output file in bytes.
    Raises RuntimeError if compression fails.
    """
    gs_exe = ghostscript_path

    # Probe PATH if not explicitly provided
    if not gs_exe:
        gs_exe = shutil.which('gswin64c') or shutil.which('gs')

    if gs_exe and os.path.isfile(gs_exe):
        log.info('Compressing PDF with Ghostscript: %s', gs_exe)
        cmd = [
            gs_exe,
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/ebook',
            '-dDownsampleColorImages=true',
            '-dColorImageResolution=150',
            '-dNOPAUSE',
            '-dBATCH',
            f'-sOutputFile={output_path}',
            input_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                timeout=300,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f'Ghostscript exited {result.returncode}: '
                    f'{result.stderr.decode("utf-8", errors="replace").strip()}'
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError('Ghostscript compression timed out after 300 seconds')
    else:
        # PyMuPDF fallback
        log.info('Ghostscript not found — compressing PDF with PyMuPDF (fitz)')
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                'PyMuPDF (fitz) is not installed and Ghostscript was not found. '
                'Install PyMuPDF: python -m pip install pymupdf'
            )
        doc = fitz.open(input_path)
        doc.save(output_path, deflate=True, garbage=4, clean=True)
        doc.close()

    if not os.path.exists(output_path):
        raise RuntimeError(f'Compression produced no output file at: {output_path}')

    out_size = os.path.getsize(output_path)
    log.info(
        'PDF compression complete: %.1f MB -> %.1f MB',
        os.path.getsize(input_path) / (1024 * 1024),
        out_size / (1024 * 1024),
    )
    return out_size


def try_compress_epub(input_path: str, max_size_mb: float, calibre_path: str = None):
    """Attempt to compress an EPUB via Calibre image compression.

    Returns the path to the compressed EPUB if it fits within max_size_mb,
    otherwise returns None.
    """
    ebook_convert = calibre_path
    if not ebook_convert:
        ebook_convert = shutil.which('ebook-convert')
    if not ebook_convert:
        log.warning('ebook-convert not found; cannot compress EPUB')
        return None

    stem = Path(input_path).stem
    output_path = str(Path(input_path).parent / f'{stem}_compressed.epub')

    log.info('Compressing EPUB with Calibre: %s', ebook_convert)
    try:
        result = subprocess.run(
            [ebook_convert, input_path, output_path,
             '--compress-images', '--jpeg-quality', '60'],
            timeout=300,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            log.warning(
                'Calibre EPUB compression failed (exit %d): %s',
                result.returncode,
                result.stderr.decode('utf-8', errors='replace').strip(),
            )
            return None
    except subprocess.TimeoutExpired:
        log.warning('Calibre EPUB compression timed out')
        return None

    if not os.path.exists(output_path):
        log.warning('Calibre produced no output file at: %s', output_path)
        return None

    compressed_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info('EPUB compression complete: %.1f MB', compressed_mb)

    if compressed_mb <= max_size_mb:
        return output_path

    log.warning(
        'Compressed EPUB still too large: %.1f MB > %.1f MB limit',
        compressed_mb,
        max_size_mb,
    )
    return None


def zip_file(input_path: str, output_path: str) -> int:
    """Wrap a single file in a ZIP archive using DEFLATE compression.

    Returns the size of the ZIP file in bytes.
    """
    log.info('Creating ZIP: %s', output_path)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(input_path, os.path.basename(input_path))
    zip_size = os.path.getsize(output_path)
    log.info('ZIP created: %.1f MB', zip_size / (1024 * 1024))
    return zip_size


# =================================================================================
# PDF splitting
# =================================================================================

def _split_page_ranges(total_pages: int, pages_per_part: int):
    """Yield (start, end) page ranges for splitting."""
    for start in range(0, total_pages, pages_per_part):
        yield start, min(start + pages_per_part, total_pages)


def split_pdf(input_path: str, max_size_mb: float, output_dir: str):
    """Split a PDF into parts that each fit within max_size_mb.

    Uses a 0.75x safety factor on the average-page-size estimate to account
    for uneven page sizes in scanned PDFs.  After splitting, any oversized
    part is re-split with fewer pages.

    Returns (list_of_part_paths, None) on success,
    or (None, error_message) if splitting is not feasible.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None, (
            'PyMuPDF (fitz) is not installed. '
            'Install it: python -m pip install pymupdf'
        )

    doc = fitz.open(input_path)
    total_pages = doc.page_count

    if total_pages == 0:
        doc.close()
        return None, 'PDF has no pages'

    file_size_bytes = os.path.getsize(input_path)
    avg_page_size = file_size_bytes / total_pages
    max_size_bytes = max_size_mb * 1024 * 1024

    # 0.75x safety factor — scanned PDFs have wildly uneven page sizes
    pages_per_part = max(10, int(max_size_bytes * 0.75 / avg_page_size))
    num_parts = math.ceil(total_pages / pages_per_part)

    if num_parts > 5:
        doc.close()
        return None, (
            f'File too large for email (would need {num_parts} parts). '
            'Use USB delivery.'
        )

    log.info(
        'Splitting %d pages into %d parts (~%d pages each, 0.75x safety factor)',
        total_pages,
        num_parts,
        pages_per_part,
    )

    stem = Path(input_path).stem
    part_paths = []
    part_counter = 0

    # Build initial page ranges
    ranges = list(_split_page_ranges(total_pages, pages_per_part))

    for start_page, end_page in ranges:
        part_counter += 1
        part_filename = f'{stem}_part{part_counter}.pdf'
        part_path = os.path.join(output_dir, part_filename)

        part_doc = fitz.open()
        part_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)
        part_doc.save(part_path)
        part_doc.close()

        part_size_mb = os.path.getsize(part_path) / (1024 * 1024)

        if part_size_mb > max_size_mb and (end_page - start_page) > 10:
            # Post-split verification failed — re-split this part with half the pages
            log.info(
                'Part %d oversized (%.1f MB > %.0f MB) — re-splitting',
                part_counter, part_size_mb, max_size_mb,
            )
            os.remove(part_path)
            part_counter -= 1  # rewind counter

            half = max(10, (end_page - start_page) // 2)
            sub_ranges = list(_split_page_ranges(end_page - start_page, half))
            for sub_start, sub_end in sub_ranges:
                part_counter += 1
                if part_counter > 5:
                    doc.close()
                    # Clean up already-written parts
                    for p in part_paths:
                        if os.path.exists(p):
                            os.remove(p)
                    return None, (
                        f'File too large for email (re-split would need >5 parts). '
                        'Use USB delivery.'
                    )
                sub_filename = f'{stem}_part{part_counter}.pdf'
                sub_path = os.path.join(output_dir, sub_filename)

                sub_doc = fitz.open()
                sub_doc.insert_pdf(doc,
                                   from_page=start_page + sub_start,
                                   to_page=start_page + sub_end - 1)
                sub_doc.save(sub_path)
                sub_doc.close()

                sub_size_mb = os.path.getsize(sub_path) / (1024 * 1024)
                log.info(
                    'Part %d (re-split): pages %d-%d -> %.1f MB -> %s',
                    part_counter,
                    start_page + sub_start + 1,
                    start_page + sub_end,
                    sub_size_mb,
                    sub_filename,
                )
                part_paths.append(sub_path)
        else:
            log.info(
                'Part %d/%d: pages %d-%d -> %.1f MB -> %s',
                part_counter,
                num_parts,
                start_page + 1,
                end_page,
                part_size_mb,
                part_filename,
            )
            part_paths.append(part_path)

    doc.close()
    return part_paths, None


def _sanitize_filename(name: str) -> str:
    """Remove filesystem-unsafe characters from a filename (not the extension)."""
    # Strip characters that are invalid in filenames or look ugly in Kindle library
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


# =================================================================================
# SMTP sending
# =================================================================================

def _build_mime_message(
    sender: str,
    recipient: str,
    subject: str,
    file_path: str,
    attachment_name: str = None,
) -> MIMEMultipart:
    """Build a MIME multipart email with a single file attachment.

    attachment_name overrides the filename shown to the recipient (and used
    by Amazon as the Kindle library title).  Defaults to the basename of
    file_path if not provided.
    """
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject

    # Minimal body text — Amazon only cares about the attachment
    msg.attach(MIMEText('', 'plain'))

    with open(file_path, 'rb') as fh:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(fh.read())

    encoders.encode_base64(part)
    display_name = attachment_name or os.path.basename(file_path)
    part.add_header(
        'Content-Disposition',
        'attachment',
        filename=display_name,
    )
    msg.attach(part)
    return msg


def _connect_smtp(server: str, port: int) -> smtplib.SMTP:
    """Open an authenticated-ready SMTP connection (no login yet)."""
    if port == 465:
        log.info('Connecting via SMTP_SSL on port 465')
        conn = smtplib.SMTP_SSL(server, port, timeout=60)
    else:
        log.info('Connecting via SMTP + STARTTLS on port %d', port)
        conn = smtplib.SMTP(server, port, timeout=60)
        conn.ehlo()
        conn.starttls()
        conn.ehlo()
    return conn


def send_email(
    file_path: str,
    kindle_address: str,
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    subject: str,
    attachment_name: str = None,
) -> None:
    """Send a single file to the Kindle address via SMTP.

    attachment_name overrides the MIME filename (used by Amazon as the
    Kindle library title).

    Raises specific exceptions on failure; retries once on transient errors.
    Exit-code-mapped exceptions propagate to main().
    """
    msg = _build_mime_message(smtp_user, kindle_address, subject, file_path,
                              attachment_name=attachment_name)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    log.info(
        'Sending "%s" (%.1f MB) to %s via %s:%d',
        os.path.basename(file_path),
        file_size_mb,
        kindle_address,
        smtp_server,
        smtp_port,
    )

    last_exc = None
    for attempt in range(2):  # try once, retry once on transient failure
        if attempt > 0:
            log.info('Retrying in 5 seconds...')
            time.sleep(5)
        try:
            conn = _connect_smtp(smtp_server, smtp_port)
            conn.login(smtp_user, smtp_password)
            conn.sendmail(smtp_user, [kindle_address], msg.as_bytes())
            conn.quit()
            log.info('Email sent successfully')
            return  # success
        except smtplib.SMTPAuthenticationError:
            # Auth failure is not transient — don't retry
            raise
        except smtplib.SMTPRecipientsRefused:
            # Recipient rejection is not transient — don't retry
            raise
        except smtplib.SMTPDataError as exc:
            if exc.smtp_code == 552:
                raise  # size rejection — don't retry
            last_exc = exc
        except (socket.timeout, ConnectionRefusedError):
            last_exc = sys.exc_info()[1]
        except ssl.SSLError:
            last_exc = sys.exc_info()[1]
        except smtplib.SMTPException as exc:
            last_exc = exc

    # Exhausted retries — re-raise the last exception
    if last_exc is not None:
        raise last_exc
    raise RuntimeError('send_email: unexpected fall-through')


# =================================================================================
# Subject line
# =================================================================================

def build_subject(title: str, file_path: str, convert_subject: bool,
                  part_n: int = 0, total_parts: int = 0) -> str:
    """Return the email subject line per Amazon Send-to-Kindle rules.

    - PDF files: subject is always just the title (no Convert: prefix)
    - Other formats + --convert-subject flag: "Convert: {title}"
    - Without --convert-subject: just "{title}"
    - Split parts: append " (Part N of M)"
    """
    is_pdf = file_path.lower().endswith('.pdf')

    if convert_subject and not is_pdf:
        subject = f'Convert: {title}'
    else:
        subject = title

    if part_n and total_parts:
        subject = f'{subject} (Part {part_n} of {total_parts})'

    return subject


# =================================================================================
# Error output helpers
# =================================================================================

def _fail(error_code: str, message: str, exit_code: int) -> None:
    """Print a JSON failure object and exit."""
    print(json.dumps({'success': False, 'error': error_code, 'message': message}))
    sys.exit(exit_code)


# =================================================================================
# Metadata injection
# =================================================================================

def inject_metadata_if_needed(file_path, metadata, temp_dir):
    """Inject metadata into a PDF if its internal metadata is empty.

    Args:
        file_path: Path to the PDF file.
        metadata: Dict with keys like 'title', 'authors', 'subject'.
        temp_dir: Directory for writing the modified copy.

    Returns:
        Path to the file to send (original if metadata was already present,
        or a new file in temp_dir with metadata injected).
    """
    if not file_path.lower().endswith('.pdf') or not metadata:
        return file_path

    try:
        import fitz
    except ImportError:
        log.warning('PyMuPDF not installed — cannot inject PDF metadata')
        return file_path

    doc = fitz.open(file_path)
    existing = doc.metadata or {}

    if existing.get('author') and existing.get('title'):
        doc.close()
        return file_path

    doc.set_metadata({
        'author': metadata.get('authors', ''),
        'title': metadata.get('title', ''),
        'subject': metadata.get('subject', ''),
        'creator': 'EbookAutomation',
    })
    stem = Path(file_path).stem
    suffix = Path(file_path).suffix
    output = os.path.join(temp_dir, f'{stem}_metadata{suffix}')
    doc.save(output)
    doc.close()
    log.info('Injected metadata into PDF: title=%s, author=%s',
             metadata.get('title', ''), metadata.get('authors', ''))
    return output


# =================================================================================
# Argument parsing
# =================================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Send an ebook file to a Kindle via Amazon Send-to-Kindle email.'
    )
    p.add_argument('--file', required=True,
                   help='Path to the ebook file to send (PDF, EPUB, ZIP, etc.)')
    p.add_argument('--kindle-address', required=True,
                   help='Kindle email address (name@kindle.com)')
    p.add_argument('--smtp-server', required=True,
                   help='SMTP server hostname (e.g. smtp.gmail.com)')
    p.add_argument('--smtp-port', required=True, type=int,
                   help='SMTP port (587 for STARTTLS, 465 for SSL)')
    p.add_argument('--smtp-user', required=True,
                   help='Sender email address / SMTP username')
    p.add_argument('--book-title', required=True,
                   help='Book title used in the email subject line')
    p.add_argument('--convert-subject', action='store_true',
                   help='Prefix subject with "Convert:" for non-PDF files')
    p.add_argument('--compress', action='store_true',
                   help='Force PDF compression even when under 25 MB')
    p.add_argument('--split-max-mb', type=int, default=None,
                   help='Max attachment size in MB; files over this are split (PDF) '
                        'or compressed (EPUB). Defaults to 50.')
    p.add_argument('--ghostscript-path', default=None,
                   help='Explicit path to Ghostscript executable (gswin64c / gs)')
    p.add_argument('--calibre-path', default=None,
                   help='Path to ebook-convert (for EPUB compression). '
                        'Probed from PATH if omitted.')
    p.add_argument('--password-env-var', default='EBOOK_SMTP_PASSWORD',
                   help='Name of the environment variable holding the SMTP password '
                        '(default: EBOOK_SMTP_PASSWORD)')
    p.add_argument('--metadata-file', default=None,
                   help='Path to JSON file with book metadata (title, authors, etc.) '
                        'for injecting into PDFs with empty internal metadata')
    return p


# =================================================================================
# Main
# =================================================================================

def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    # --- Resolve file path -------------------------------------------------------
    file_path = os.path.abspath(args.file)
    if not os.path.isfile(file_path):
        _fail('file_not_found', f'Input file not found: {file_path}', 1)

    # --- Read SMTP password from environment -------------------------------------
    smtp_password = os.environ.get(args.password_env_var)
    if not smtp_password:
        _fail(
            'missing_password',
            f'Environment variable {args.password_env_var!r} is not set. '
            'Set it to your SMTP app password before running this script.',
            2,
        )

    max_size_mb = args.split_max_mb if args.split_max_mb else 50
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    is_pdf = file_path.lower().endswith('.pdf')
    is_epub = file_path.lower().endswith('.epub')

    file_to_send = file_path  # may be replaced by compressed/zipped version
    method = 'direct'

    # Use a temp directory alongside the script for intermediate files
    # (not system temp — Windows cleans that up aggressively)
    tmp_dir = str(SCRIPT_DIR.parent / 'processing')
    os.makedirs(tmp_dir, exist_ok=True)

    # --- Load metadata from JSON file if provided ---
    book_metadata = None
    if args.metadata_file and os.path.isfile(args.metadata_file):
        try:
            with open(args.metadata_file, 'r', encoding='utf-8') as mf:
                book_metadata = json.load(mf)
            log.info('Loaded metadata from %s', args.metadata_file)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning('Failed to load metadata file: %s', exc)

    # --- Format-aware size routing -----------------------------------------------
    if is_epub:
        log.info('EPUB detected (%.1f MB); max allowed: %.0f MB', file_size_mb, max_size_mb)
        if file_size_mb > max_size_mb:
            compressed = try_compress_epub(file_to_send, max_size_mb, args.calibre_path)
            if compressed:
                file_to_send = compressed
                file_size_mb = os.path.getsize(file_to_send) / (1024 * 1024)
                method = 'compressed'
            if file_size_mb > max_size_mb:
                _fail(
                    'epub_too_large',
                    f'EPUB too large for email ({file_size_mb:.1f} MB after compression). '
                    'Use USB delivery.',
                    4,
                )

    elif is_pdf:
        log.info('PDF detected (%.1f MB); max allowed: %.0f MB', file_size_mb, max_size_mb)

        # Optionally force compression even under 25 MB
        if args.compress and file_size_mb <= 25:
            compressed_path = os.path.join(
                tmp_dir, Path(file_path).stem + '_compressed.pdf'
            )
            try:
                compress_pdf(file_path, compressed_path, args.ghostscript_path)
                file_to_send = compressed_path
                file_size_mb = os.path.getsize(file_to_send) / (1024 * 1024)
                method = 'compressed'
            except RuntimeError as exc:
                log.warning('Compression failed (will send as-is): %s', exc)

        elif 25 < file_size_mb <= max_size_mb:
            # ZIP it — deflate often shaves off enough
            zip_path = os.path.join(tmp_dir, Path(file_path).stem + '.zip')
            zip_size = zip_file(file_to_send, zip_path)
            zip_size_mb = zip_size / (1024 * 1024)
            if zip_size_mb <= max_size_mb:
                file_to_send = zip_path
                file_size_mb = zip_size_mb
                method = 'zip'
            else:
                # ZIP didn't help enough — compress then re-ZIP
                log.info('ZIP still %.1f MB; trying compression first', zip_size_mb)
                compressed_path = os.path.join(
                    tmp_dir, Path(file_path).stem + '_compressed.pdf'
                )
                try:
                    compress_pdf(file_path, compressed_path, args.ghostscript_path)
                    rezip_path = os.path.join(
                        tmp_dir, Path(file_path).stem + '_compressed.zip'
                    )
                    rezip_size = zip_file(compressed_path, rezip_path)
                    rezip_size_mb = rezip_size / (1024 * 1024)
                    if rezip_size_mb <= max_size_mb:
                        file_to_send = rezip_path
                        file_size_mb = rezip_size_mb
                        method = 'compressed_zip'
                    else:
                        # Fall through to splitting below
                        file_to_send = compressed_path
                        file_size_mb = os.path.getsize(file_to_send) / (1024 * 1024)
                        method = 'compressed'
                except RuntimeError as exc:
                    log.warning('Compression failed: %s', exc)
                    # file_to_send stays as original; splitting will be triggered

        elif file_size_mb > max_size_mb:
            # Too large even to ZIP — compress first, then check again
            compressed_path = os.path.join(
                tmp_dir, Path(file_path).stem + '_compressed.pdf'
            )
            try:
                compress_pdf(file_path, compressed_path, args.ghostscript_path)
                comp_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
                if comp_size_mb <= max_size_mb:
                    file_to_send = compressed_path
                    file_size_mb = comp_size_mb
                    method = 'compressed'
                else:
                    # Still too large — re-ZIP compressed version then check
                    rezip_path = os.path.join(
                        tmp_dir, Path(file_path).stem + '_compressed.zip'
                    )
                    rezip_size_mb = zip_file(compressed_path, rezip_path) / (1024 * 1024)
                    if rezip_size_mb <= max_size_mb:
                        file_to_send = rezip_path
                        file_size_mb = rezip_size_mb
                        method = 'compressed_zip'
                    else:
                        # Fall through to splitting; operate on compressed PDF
                        file_to_send = compressed_path
                        file_size_mb = comp_size_mb
                        method = 'compressed'
            except RuntimeError as exc:
                log.warning('Compression failed: %s; will attempt splitting original', exc)
                # file_to_send stays as original

    # --- Inject metadata into PDF if internal metadata is missing ---
    if book_metadata and file_to_send.lower().endswith('.pdf'):
        file_to_send = inject_metadata_if_needed(file_to_send, book_metadata, tmp_dir)

    # --- Check again after routing; if still over max and is PDF → split ----------
    final_size_mb = os.path.getsize(file_to_send) / (1024 * 1024)
    if final_size_mb > max_size_mb and (
        file_to_send.lower().endswith('.pdf')
    ):
        log.info(
            'File still %.1f MB after compression attempts; splitting into parts',
            final_size_mb,
        )
        part_paths, split_error = split_pdf(file_to_send, max_size_mb, tmp_dir)
        if split_error:
            _fail('split_failed', split_error, 4)

        total_parts = len(part_paths)
        log.info('Sending %d parts', total_parts)
        parts_sent = []

        for idx, part_path in enumerate(part_paths, start=1):
            part_subject = build_subject(
                args.book_title, part_path, args.convert_subject,
                part_n=idx, total_parts=total_parts,
            )
            part_size_mb = os.path.getsize(part_path) / (1024 * 1024)
            log.info(
                'Sending part %d/%d (%.1f MB): subject="%s"',
                idx, total_parts, part_size_mb, part_subject,
            )
            # Inject metadata into split part
            if book_metadata:
                part_meta = dict(book_metadata)
                part_meta['title'] = f"{book_metadata.get('title', args.book_title)} - Part {idx} of {total_parts}"
                part_path = inject_metadata_if_needed(part_path, part_meta, tmp_dir)

            ext = Path(part_path).suffix
            clean_part_name = _sanitize_filename(
                '{} - Part {} of {}{}'.format(args.book_title, idx, total_parts, ext)
            )
            try:
                send_email(
                    file_path=part_path,
                    kindle_address=args.kindle_address,
                    smtp_server=args.smtp_server,
                    smtp_port=args.smtp_port,
                    smtp_user=args.smtp_user,
                    smtp_password=smtp_password,
                    subject=part_subject,
                    attachment_name=clean_part_name,
                )
                parts_sent.append({
                    'part': idx,
                    'file': os.path.basename(part_path),
                    'size_mb': round(part_size_mb, 2),
                })
            except smtplib.SMTPAuthenticationError:
                _fail(
                    'auth_failure',
                    'SMTP authentication failed. Check your app password and that '
                    '2-factor authentication is enabled. For Gmail, use an App Password '
                    '(not your account password).',
                    2,
                )
            except smtplib.SMTPRecipientsRefused:
                _fail(
                    'recipient_rejected',
                    f'Amazon rejected the recipient address {args.kindle_address!r}. '
                    'Verify it is added to your Approved Personal Document Email List '
                    'in Manage Your Content and Devices.',
                    3,
                )
            except smtplib.SMTPDataError as exc:
                if exc.smtp_code == 552:
                    _fail(
                        'attachment_too_large',
                        f'Part {idx} attachment was rejected by the server (552 too large). '
                        f'Try a smaller --split-max-mb value (current: {max_size_mb}).',
                        4,
                    )
                _fail('smtp_error', f'SMTP data error on part {idx}: {exc}', 6)
            except (socket.timeout, ConnectionRefusedError) as exc:
                _fail(
                    'network_error',
                    f'Network error sending part {idx}: {exc}. '
                    f'Check that {args.smtp_server}:{args.smtp_port} is reachable.',
                    5,
                )
            except ssl.SSLError as exc:
                _fail(
                    'tls_error',
                    f'TLS handshake failed on part {idx}: {exc}. '
                    'Check your SMTP port and server TLS configuration.',
                    5,
                )
            except Exception as exc:
                _fail(
                    'unknown_error',
                    f'Unexpected error sending part {idx}: {type(exc).__name__}: {exc}',
                    6,
                )

        # All parts sent
        print(json.dumps({
            'success': True,
            'parts_sent': total_parts,
            'method': 'split',
            'parts': parts_sent,
        }))
        sys.exit(0)

    # --- Single-file send ---------------------------------------------------------
    subject = build_subject(args.book_title, file_to_send, args.convert_subject)
    send_size_mb = os.path.getsize(file_to_send) / (1024 * 1024)
    log.info(
        'Sending single file: %s (%.1f MB), subject="%s"',
        os.path.basename(file_to_send),
        send_size_mb,
        subject,
    )

    ext = Path(file_to_send).suffix
    clean_name = _sanitize_filename('{}{}'.format(args.book_title, ext))

    try:
        send_email(
            file_path=file_to_send,
            kindle_address=args.kindle_address,
            smtp_server=args.smtp_server,
            smtp_port=args.smtp_port,
            smtp_user=args.smtp_user,
            smtp_password=smtp_password,
            subject=subject,
            attachment_name=clean_name,
        )
    except smtplib.SMTPAuthenticationError:
        _fail(
            'auth_failure',
            'SMTP authentication failed. Check your app password and that '
            '2-factor authentication is enabled. For Gmail, use an App Password '
            '(not your account password).',
            2,
        )
    except smtplib.SMTPRecipientsRefused:
        _fail(
            'recipient_rejected',
            f'Amazon rejected the recipient address {args.kindle_address!r}. '
            'Verify it is added to your Approved Personal Document Email List '
            'in Manage Your Content and Devices.',
            3,
        )
    except smtplib.SMTPDataError as exc:
        if exc.smtp_code == 552:
            _fail(
                'attachment_too_large',
                f'Attachment rejected by server as too large (552). '
                f'Current size: {send_size_mb:.1f} MB. '
                f'Try --split-max-mb with a smaller value, or use USB delivery.',
                4,
            )
        _fail('smtp_error', f'SMTP data error: {exc}', 6)
    except (socket.timeout, ConnectionRefusedError) as exc:
        _fail(
            'network_error',
            f'Network error: {exc}. '
            f'Check that {args.smtp_server}:{args.smtp_port} is reachable.',
            5,
        )
    except ssl.SSLError as exc:
        _fail(
            'tls_error',
            f'TLS handshake failed: {exc}. '
            'Check your SMTP port and server TLS configuration.',
            5,
        )
    except Exception as exc:
        _fail(
            'unknown_error',
            f'Unexpected error: {type(exc).__name__}: {exc}',
            6,
        )

    # Success
    print(json.dumps({
        'success': True,
        'file': os.path.basename(file_to_send),
        'size_mb': round(send_size_mb, 2),
        'method': method,
    }))
    sys.exit(0)


if __name__ == '__main__':
    main()
