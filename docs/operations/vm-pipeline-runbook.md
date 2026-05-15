# VM Pipeline Runbook — claude-dev-01

**Ticket:** EB-210  
**Updated:** 2026-05-14  
**Host:** `claude-dev-01` (Hetzner Cloud, Ubuntu 24.04, Tailscale-enrolled)  
**SSH:** `ssh claude-dev-01` (root, via Tailscale MagicDNS)

---

## Quick-start: SSH access

```bash
ssh claude-dev-01          # root user, via Tailscale MagicDNS
```

Tailscale resolves `claude-dev-01` automatically. If Tailscale is not connected,
fall back to the bare Tailscale IP: `ssh root@100.68.98.58`.

---

## Fresh VM bring-up (rebuild from scratch)

Run the idempotent bringup script from your desktop:

```bash
ssh claude-dev-01 'bash -s' < scripts/vm-bringup.sh
```

After the script completes, populate the `.env` file with real API keys:

```bash
ssh claude-dev-01
cp ~/EbookAutomation/.env.template ~/EbookAutomation/.env
chmod 600 ~/EbookAutomation/.env
nano ~/EbookAutomation/.env   # fill in OPENROUTER_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY
```

---

## Single PDF conversion (text-layer pipeline)

```bash
ssh claude-dev-01
cd ~/EbookAutomation
source .venv/bin/activate

# Extract + generate HTML + convert to EPUB via Calibre
python tools/pdf_to_balabolka.py \
    --input ~/ebook-data/inbox/book.pdf \
    --output-dir ~/ebook-data/output

# Output: ~/ebook-data/output/Author - Title.epub (or .azw3)
```

Calibre's `ebook-convert` is on PATH (`/usr/bin/ebook-convert`) after the apt install.
No Windows path needed — the pipeline detects it via `shutil.which("ebook-convert")`.

---

## VQA run (OpenRouter provider)

```bash
source ~/EbookAutomation/.venv/bin/activate

python ~/EbookAutomation/tools/visual_qa.py \
    --provider openrouter \
    --model qwen/qwen3-vl-30b-a3b-instruct \
    --input ~/ebook-data/output/Author\ -\ Title.epub \
    --output-dir ~/ebook-data/output/vqa/
```

**Provider selection:**
- Use `--provider openrouter` (required on VM — `local` hard-fails on Linux)
- Default model for VM: `qwen/qwen3-vl-30b-a3b-instruct`
- Requires `OPENROUTER_API_KEY` in `.env`

---

## Log location

```
~/EbookAutomation/logs/ebook-automation-YYYY-MM-DD.log
```

Check for Windows path leakage with:

```bash
grep -i 'C:\\' ~/EbookAutomation/logs/ebook-automation-$(date +%Y-%m-%d).log | head -20
```

---

## Troubleshooting

### `local` provider selected → RuntimeError on startup

```
RuntimeError: LocalVisionProvider is not available on Linux.
Update your config to use provider='openrouter' ...
```

**Fix:** Change `provider` in `config/settings.json` (or `--provider` CLI flag) from
`local` to `openrouter`. The `local` provider is intentionally hard-failed on Linux
(EB-210 decision) — it requires sb-chat which only runs on the primary desktop.

### Missing API key

```
KeyError: 'OPENROUTER_API_KEY'
```

**Fix:** Verify `~/EbookAutomation/.env` is populated and mode 0600:
```bash
ls -la ~/EbookAutomation/.env
head -5 ~/EbookAutomation/.env   # should show key=value lines
```

### Calibre not found

```bash
which ebook-convert          # should return /usr/bin/ebook-convert
ebook-convert --version      # should return Calibre 7.x
```

If missing: `apt-get install -y calibre`

### OpenRouter image-byte ceiling (large books)

For books >200 pages, the per-call image-bytes ceiling may trigger. Mitigations
(from EB-156) are built into `visual_qa.py`: single-page retry + DPI reduction.
If you still hit limits, use `--max-pages 10` to reduce batch size.

---

## Code sync (desktop → VM)

After making changes on the desktop, push and pull on VM:

```bash
# Desktop
git push origin feat/eb-210-vm-portability  # or master after merge

# VM
ssh claude-dev-01 "cd ~/EbookAutomation && git pull --ff-only && source .venv/bin/activate && pip install -q -r requirements.txt"
```
