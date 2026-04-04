# Test Hints — EbookAutomation

## Purpose

This file provides Cowork (running on macOS VM) with verification steps for features in EbookAutomation. When a Discord update appears in #ebook-updates, Cowork should:

1. Read the Discord message for the Jira ticket ID and summary
2. Query Jira via MCP for full ticket context
3. Find the matching feature section below
4. Follow the verification steps
5. Report results back to #ebook-updates (pass/fail with details)

## Access

- **Project files:** /Volumes/VMware Shared Folders/Projects/EbookAutomation
- **Book files:** /Volumes/VMware Shared Folders/Books
- **Jira project:** SCRUM

## Notes

EbookAutomation is a Python project. Cowork verification will primarily involve checking file outputs, script exit codes, and directory structure rather than UI interactions.

## Features

### Script Execution

- Verify Python scripts run without import errors
- Check that scripts produce expected output files in the correct directories
- Confirm scripts handle missing input files gracefully (no unhandled exceptions)

### File Processing

- Verify output files are generated in the expected format
- Check that output file sizes are reasonable (not zero-byte, not truncated)
- Confirm file encoding is correct (cp1252 expected on Windows source files)

### Directory Structure

- Verify expected project directories exist
- Check that output directories are created if missing
- Confirm no temp files are left behind after processing

### Error Handling

- Run scripts with invalid input and verify graceful failure
- Check that error messages are descriptive
- Verify no stack traces leak to stdout in production mode
