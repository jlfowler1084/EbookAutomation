#!/usr/bin/env python
"""send_to_kindle.py -- Send a book from Calibre library to a connected Kindle.

Usage (called via calibre-debug, NOT standard Python):
    calibre-debug -e send_to_kindle.py -- --library-path "C:\\Users\\Joe\\Calibre Library" --book-id 42 [--delete-after]

This script uses Calibre's MTP device driver to send books to MTP-connected
Kindle devices (Kindle Scribe, newer Kindles). Falls back to USBMS for
older Kindles that present as USB Mass Storage.

IMPORTANT: Runs inside Calibre's embedded Python (via calibre-debug -e).
Do NOT import anything outside Calibre or the Python standard library.
"""

import sys
import os
import argparse
import time
import json
import traceback


def find_kindle_mtp(timeout=60):
    """Detect a Kindle via the MTP driver (Kindle Scribe and newer).

    MTP devices require: startup() -> scan -> detect_managed_devices(scanner.devices).
    This is different from the USBMS path used by older Kindles.
    """
    from calibre.devices.mtp.driver import MTP_DEVICE
    from calibre.devices.scanner import DeviceScanner

    drv = MTP_DEVICE(None)
    drv.startup()

    start_time = time.time()
    detected = None

    while time.time() - start_time < timeout:
        scanner = DeviceScanner()
        scanner.scan()

        detected = drv.detect_managed_devices(scanner.devices)
        if detected:
            break
        elapsed = int(time.time() - start_time)
        print('[SendToKindle] Waiting for Kindle (MTP)... ({}s)'.format(elapsed))
        time.sleep(3)

    if not detected:
        drv.shutdown()
        return None

    drv.reset(log_packets=False,
              report_progress=lambda x, y: None,
              detected_device=detected)
    drv.open(detected, 'calibre-send-to-kindle')
    return drv


def find_kindle_usbms(timeout=60):
    """Detect a Kindle via USBMS driver (older Kindles with drive letters)."""
    from calibre.devices.scanner import DeviceScanner
    from calibre.customize.ui import device_plugins

    start_time = time.time()

    while time.time() - start_time < timeout:
        scanner = DeviceScanner()
        scanner.scan()

        for plugin in device_plugins():
            name = getattr(plugin, 'name', '').lower()
            if 'kindle' not in name:
                continue
            try:
                connected = scanner.is_device_connected(plugin)
                if isinstance(connected, tuple):
                    is_conn = connected[0]
                    if not is_conn:
                        continue
                elif not connected:
                    continue

                plugin.reset(log_packets=False,
                             report_progress=lambda x, y: None,
                             detected_device=connected)
                plugin.open(connected, library_uuid=None)
                return plugin
            except Exception:
                continue

        elapsed = int(time.time() - start_time)
        print('[SendToKindle] Waiting for Kindle (USBMS)... ({}s)'.format(elapsed))
        time.sleep(3)

    return None


def main():
    parser = argparse.ArgumentParser(description='Send book to connected Kindle via Calibre')
    parser.add_argument('--library-path', required=True, help='Path to Calibre library')
    parser.add_argument('--book-id', required=True, type=int, help='Calibre book ID to send')
    parser.add_argument('--delete-after', action='store_true', help='Remove book from library after sending')
    parser.add_argument('--timeout', type=int, default=60, help='Seconds to wait for device detection')

    args = parser.parse_args()

    book_id = args.book_id
    library_path = args.library_path
    timeout = args.timeout

    # --- Step 1: Open the Calibre library ---
    try:
        from calibre.library import db as LibraryDatabase
    except ImportError:
        try:
            from calibre.library import db
            LibraryDatabase = db
        except ImportError:
            print('[SendToKindle] ERROR: Cannot import calibre.library', file=sys.stderr)
            print(json.dumps({'success': False, 'error': 'import_failed'}))
            sys.exit(1)

    print('[SendToKindle] Opening library: {}'.format(library_path))
    try:
        db_instance = LibraryDatabase(library_path)
        db_api = db_instance.new_api
    except Exception as e:
        print('[SendToKindle] ERROR: Failed to open library: {}'.format(e), file=sys.stderr)
        print(json.dumps({'success': False, 'error': 'library_open_failed'}))
        sys.exit(1)

    # Verify book exists
    all_ids = db_api.all_book_ids()
    if book_id not in all_ids:
        print('[SendToKindle] ERROR: Book ID {} not found in library'.format(book_id), file=sys.stderr)
        print(json.dumps({'success': False, 'error': 'book_not_found'}))
        sys.exit(1)

    title = db_api.field_for('title', book_id)
    authors = db_api.field_for('authors', book_id)
    formats = db_api.formats(book_id)
    author_str = ', '.join(authors) if authors else 'Unknown'
    fmt_str = ', '.join(formats) if formats else 'none'
    print('[SendToKindle] Book: \'{}\' by {}'.format(title, author_str))
    print('[SendToKindle] Available formats: {}'.format(fmt_str))

    # --- Step 2: Detect connected Kindle device ---
    print('[SendToKindle] Scanning for Kindle (timeout: {}s)...'.format(timeout))

    # Try MTP first (Kindle Scribe, newer models), then USBMS (older models)
    device_plugin = None

    print('[SendToKindle] Trying MTP detection...')
    device_plugin = find_kindle_mtp(timeout=timeout)

    if not device_plugin:
        print('[SendToKindle] MTP not found, trying USBMS...')
        device_plugin = find_kindle_usbms(timeout=max(10, timeout - 30))

    if not device_plugin:
        print('[SendToKindle] ERROR: No Kindle device detected within {}s'.format(timeout), file=sys.stderr)
        print('[SendToKindle] Make sure your Kindle is connected via USB and recognized by Windows.', file=sys.stderr)
        print(json.dumps({'success': False, 'error': 'no_device'}))
        sys.exit(2)

    device_name = device_plugin.get_gui_name()
    print('[SendToKindle] Found device: {}'.format(device_name))

    # --- Step 3: Send book to device ---
    format_priority = ['KFX', 'AZW3', 'MOBI', 'EPUB', 'PDF']
    available_upper = [f.upper() for f in formats] if formats else []
    send_format = None
    for fmt in format_priority:
        if fmt in available_upper:
            send_format = fmt
            break

    if not send_format:
        print('[SendToKindle] ERROR: No Kindle-compatible format found. Available: {}'.format(fmt_str), file=sys.stderr)
        print(json.dumps({'success': False, 'error': 'no_compatible_format'}))
        sys.exit(3)

    print('[SendToKindle] Sending \'{}\' as {}...'.format(title, send_format))

    try:
        file_path = db_api.format_abspath(book_id, send_format)
        if not file_path or not os.path.exists(file_path):
            print('[SendToKindle] ERROR: Format file not found at expected path', file=sys.stderr)
            print(json.dumps({'success': False, 'error': 'file_not_found'}))
            sys.exit(4)

        mi = db_api.get_metadata(book_id, get_cover=True)

        from calibre.utils.filenames import ascii_filename
        device_filename = ascii_filename(
            '{} - {}.{}'.format(title, author_str, send_format.lower())
        )

        on_card = None  # Main memory

        # MTP driver uses upload_books(); USBMS uses upload_to_device()
        if hasattr(device_plugin, 'upload_books'):
            device_plugin.upload_books(
                files=[file_path],
                names=[device_filename],
                on_card=on_card,
                end_session=True,
                metadata=[mi]
            )
        else:
            device_plugin.upload_to_device(
                files_in=[(file_path, book_id)],
                names_on_device=[device_filename],
                metadata=[mi],
                on_card=on_card
            )

        print('[SendToKindle] SUCCESS: \'{}\' sent to {}'.format(title, device_name))

    except Exception as e:
        print('[SendToKindle] ERROR during send: {}'.format(e), file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(5)
    finally:
        try:
            device_plugin.eject()
        except Exception:
            pass
        if hasattr(device_plugin, 'shutdown'):
            try:
                device_plugin.shutdown()
            except Exception:
                pass

    # --- Step 4: Optionally remove from library ---
    if args.delete_after:
        print('[SendToKindle] Removing book ID {} from library...'.format(book_id))
        db_api.remove_books((book_id,))
        print('[SendToKindle] Removed from library')

    print(json.dumps({
        'success': True,
        'title': title,
        'format': send_format,
        'device': device_name
    }))


if __name__ == '__main__':
    main()
