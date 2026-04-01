# EB-40 — Add Python requirements.txt

## Session Name
python-requirements

## Claude Code Model
**Sonnet** — Simple dependency audit and file generation.

## Ticket
EB-40 — Add Python requirements.txt for dependency management

## Objective
Audit all Python imports across the project, create `requirements.txt` with pinned versions, and create `dev-requirements.txt` for test-only dependencies.

---

## Task 1: Audit Imports

Scan all `.py` files in the project for third-party imports:

```bash
grep -rh "^import \|^from \|^\s*import \|^\s*from " tools/*.py module/*.py *.py 2>/dev/null | grep -v "^\s*#"
```

Filter out standard library modules and local project imports. The known third-party packages (from pre-audit) are:

| Import Name | PyPI Package |
|---|---|
| `bs4` | `beautifulsoup4` |
| `ebooklib` | `ebooklib` |
| `fitz` / `pymupdf` | `pymupdf` |
| `google.generativeai` | `google-generativeai` |
| `pdf2image` | `pdf2image` |
| `pdfminer` | `pdfminer.six` |
| `pypdf` | `pypdf` |
| `pytesseract` | `pytesseract` |
| `requests` | `requests` |
| `spellchecker` | `pyspellchecker` |
| `dotenv` | `python-dotenv` |
| `pytest` | `pytest` (dev only) |

Verify this list against actual imports — there may be additional packages I missed.

## Task 2: Get Installed Versions

Run this to get current pinned versions from Joe's Python 3.12 install:

```powershell
python -m pip list --format=freeze | Select-String "beautifulsoup4|ebooklib|pymupdf|google-generativeai|pdf2image|pdfminer|pypdf|pytesseract|requests|pyspellchecker|python-dotenv|pytest|lxml|Pillow|anthropic"
```

Note: `lxml`, `Pillow`, and `anthropic` may be installed even if not directly imported — check and include if they are.

## Task 3: Create `requirements.txt`

At the project root. Format: one package per line, pinned with `==`. Group with comments:

```
# Core PDF extraction
pypdf==X.X.X
pdfminer.six==XXXXXXXX
pymupdf==X.X.X
pdf2image==X.X.X
pytesseract==X.X.X

# EPUB/ebook support
ebooklib==X.X.X
beautifulsoup4==X.X.X

# AI/API
google-generativeai==X.X.X
requests==X.X.X

# Text processing
pyspellchecker==X.X.X

# Config
python-dotenv==X.X.X
```

Use the actual versions from Task 2. If a package is installed but not directly imported by any project file, add it in a `# Transitive / optional` section with a comment explaining why (e.g., "# Required by ebooklib" for lxml).

## Task 4: Create `dev-requirements.txt`

```
-r requirements.txt

# Testing
pytest==X.X.X
```

## Task 5: Add to CLAUDE.md

Find the `## Dependencies Reference` section in CLAUDE.md (grep for it) and add a note about requirements.txt:

```markdown
Install all dependencies: `python -m pip install -r requirements.txt --break-system-packages`
Dev/test dependencies: `python -m pip install -r dev-requirements.txt --break-system-packages`
```

## Task 6: Update feature-manifest.json

Add both files to the `critical_files` array:

```json
{"path": "requirements.txt", "type": "dependency_manifest", "min_lines": 8},
{"path": "dev-requirements.txt", "type": "dependency_manifest", "min_lines": 3}
```

---

## Verification

1. `python -m pip install -r requirements.txt --break-system-packages --dry-run` — should resolve without errors
2. `python tools/test_pipeline.py --quick` — all tests pass
3. `powershell -File tools\verify-manifest.ps1` — manifest verification passes
4. Git commit: `chore: EB-40 — add requirements.txt and dev-requirements.txt`
5. Git push
6. Transition EB-40 to Done (transition ID 31) via Atlassian MCP
7. Add completion comment with package count
