#!/usr/bin/env python
"""send_to_kindle.py -- Send a book from Calibre library to a connected Kindle.

Usage (called via calibre-debug, NOT standard Python):
    calibre-debug -e send_to_kindle.py -- --library-path "C:\\Users\\Joe\\Calibre Library" --book-id 42 [--delete-after]

This script uses Calibre's internal device APIs to replicate the GUI's
"Send to device" behavior, including cover/thumbnail generation.

IMPORTANT: Runs inside Calibre's embedded Python (via calibre-debug -e).
Do NOT import anything outside Calibre or the Python standard library.
"""

import sys
import os
import argparse
import time
import json
import traceback


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
            print('[SendToKindle] ERROR: Cannot import calibre.library — is this running via calibre-debug -e?', file=sys.stderr)
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
    from calibre.devices.scanner import DeviceScanner
    from calibre.customize.ui import device_plugins

    print('[SendToKindle] Scanning for connected devices (timeout: {}s)...'.format(timeout))
    scanner = DeviceScanner()
    scanner.scan()

    connected_device = None
    device_plugin = None
    start_time = time.time()

    while time.time() - start_time < timeout:
        for plugin in device_plugins():
            # Look for Kindle-compatible device drivers
            plugin_name = getattr(plugin, 'name', '').lower()
            plugin_mfr = getattr(plugin, 'manufacturer', '').lower()
            is_kindle = ('kindle' in plugin_name or 'amazon' in plugin_mfr
                         or hasattr(plugin, 'VENDOR_ID'))
            if not is_kindle:
                continue
            try:
                connected = scanner.is_device_connected(plugin)
                if connected:
                    plugin.reset(
                        log_packets=False,
                        report_progress=lambda x, y: None,
                        detected_device=scanner.create_device_info(plugin)
                    )
                    plugin.open(connected, library_uuid=None)
                    connected_device = connected
                    device_plugin = plugin
                    break
            except Exception:
                continue
        if device_plugin:
            break
        elapsed = int(time.time() - start_time)
        print('[SendToKindle] Waiting for Kindle... ({}s)'.format(elapsed))
        time.sleep(3)
        scanner.scan()

    if not device_plugin:
        print('[SendToKindle] ERROR: No Kindle device detected within {}s'.format(timeout), file=sys.stderr)
        print('[SendToKindle] Make sure your Kindle is connected via USB and recognized by Windows.', file=sys.stderr)
        print(json.dumps({'success': False, 'error': 'no_device'}))
        sys.exit(2)

    device_name = getattr(device_plugin, 'get_gui_name', lambda: 'Unknown Device')()
    print('[SendToKindle] Found device: {}'.format(device_name))

    # --- Step 3: Send book to device ---
    # Prefer KFX > AZW3 > MOBI > EPUB > PDF
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
        # Get the file path from the library
        file_path = db_api.format_abspath(book_id, send_format)
        if not file_path or not os.path.exists(file_path):
            print('[SendToKindle] ERROR: Format file not found at expected path', file=sys.stderr)
            print(json.dumps({'success': False, 'error': 'file_not_found'}))
            sys.exit(4)

        # Get book metadata
        mi = db_api.get_metadata(book_id, get_cover=True)

        from calibre.utils.filenames import ascii_filename

        # Build the on-device filename
        device_filename = ascii_filename(
            '{} - {}.{}'.format(title, author_str, send_format.lower())
        )

        # Use the device plugin's upload method
        # USBMS-based Kindle driver expects:
        #   upload_to_device(files_in, names_on_device, metadata, on_card)
        on_card = None  # Main memory, not SD card

        result = device_plugin.upload_to_device(
            files_in=[(file_path, book_id)],
            names_on_device=[device_filename],
            metadata=[mi],
            on_card=on_card
        )

        print('[SendToKindle] SUCCESS: \'{}\' sent to {}'.format(title, device_name))

        # Send cover/thumbnail if the device supports it
        try:
            if hasattr(device_plugin, 'upload_cover'):
                cover_data = db_api.cover(book_id)
                if cover_data:
                    device_plugin.upload_cover(
                        os.path.dirname(file_path),
                        os.path.basename(file_path),
                        mi, cover_data
                    )
                    print('[SendToKindle] Cover image uploaded to device')
                else:
                    print('[SendToKindle] No cover image available -- skipping thumbnail')
        except Exception as e:
            print('[SendToKindle] WARN: Cover upload failed: {}'.format(e))

    except Exception as e:
        print('[SendToKindle] ERROR during send: {}'.format(e), file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(5)
    finally:
        # Always eject/close the device cleanly
        try:
            device_plugin.eject()
        except Exception:
            pass

    # --- Step 4: Optionally remove from library ---
    if args.delete_after:
        print('[SendToKindle] Removing book ID {} from library...'.format(book_id))
        db_api.remove_books((book_id,))
        print('[SendToKindle] Removed from library')

    # Output JSON result for PowerShell to parse
    print(json.dumps({
        'success': True,
        'title': title,
        'format': send_format,
        'device': device_name
    }))


if __name__ == '__main__':
    main()
