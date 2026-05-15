[EB-210] PDF→Ebook conversion on Hetzner VM — bring-up + provider routing

## Model Tier
**Sonnet** — Executes a sequential ticket against locked decisions. No planning needed.

## Source artifacts (read these first, in this order)

1. **Ticket:** https://jlfowler1084.atlassian.net/browse/EB-210 — the P1–P5 acceptance criteria are your task list.
2. **Brainstorm:** `docs/brainstorms/2026-05-14-eb210-vm-bringup-brainstorm.md` — locked decisions, premise risks, reframe vs ticket title.
3. **Predecessor plan:** `docs/plans/2026-05-13-001-feat-eb45-freemium-web-service-plan.md` — what's *already* on `claude-dev-01` from EB-45 Phase 1.

## Locked decisions — do not re-litigate

- **Single-implementer execution.** No swarm. No `ce:plan`. Sequential P1 → P5.
- **`local` provider on VM: hard-fail on selection.** When VM config resolves `provider: local`, raise `RuntimeError` at instantiation with a message pointing at OpenRouter. No silent rerouting, no warn-and-proceed. Applies regardless of OS — the guard fires for any `local` selection.
- **SCRUM-290 large-file timeout (120s vs measured 21 min for 101 MB) is OUT OF SCOPE.** Tracked separately as EB-237. The P4 functional gate uses *Atomic Habits* (small) so the timeout is not exercised. Do NOT bump the timeout, change the file-size cap, or wire tiered timeouts inside this ticket.

## Reframe — this is NOT greenfield bring-up

EB-45 Phase 1 already deployed code + FastAPI + Calibre + Python pipeline to `claude-dev-01`. EB-210's real delta is:

1. Linux config overlay (`Path` portability, `shutil.which("ebook-convert")` fallback in `settings.json` loader)
2. The `local`-provider hard-fail guard
3. Any P1 install gaps not covered by EB-45 P1 (likely `ocrmypdf`, `tesseract`, PowerShell 7, working-dirs outside repo)
4. A reproducible runbook so the VM can be rebuilt from scratch in one command

**Therefore: state audit first.** Do not assume P1 is "todo" — assume it's "mostly done" and the work is to identify and close the gaps.

## Branch + worktree

This ticket touches Python code (`tools/llm_providers/`, `config/settings.py` loader, possibly `tools/pdf_to_balabolka.py`). Worktree required.

```powershell
git checkout master
git pull origin master
git worktree add .worktrees/EB-210-vm-bringup -b worktree/EB-210-vm-bringup
cd .worktrees/EB-210-vm-bringup
```

All code edits, the `scripts/vm-bringup.sh` runbook, and the operations runbook go on this branch. **Do NOT** create filesystem junctions inside the worktree pointing at `archive/`, `output/`, `inbox/`, or `processing/` — `Remove-Item -Recurse` on the worktree traverses junctions and will wipe the target data (recovered from this on 2026-04-22 during SCRUM-301). Run pipeline scripts from the main working tree if you need real data; keep the worktree code-only.

## VM access

- `claude-dev-01` is on Hetzner Cloud, Ubuntu 24.04, Tailscale-enrolled.
- SSH via Tailscale overlay. Hostname is `claude-dev-01` (Tailscale MagicDNS).
- Operations playbook: `~/.claude/skills/hetzner-management/SKILL.md`.

## Execution sequence

### Step 1 — State audit on `claude-dev-01` (THIS IS THE FIRST IMPLEMENTATION STEP)

`ssh claude-dev-01`. Walk EB-210's P1 ACs against actual installed state. Capture a delta:

```bash
# Check each P1 AC
which python3.12 pwsh ebook-convert tesseract ocrmypdf gs git git-lfs
python3.12 --version
ebook-convert --version
tesseract --version
ocrmypdf --version

# Repo presence
ls -la ~/EbookAutomation/ ~/EbookAutomation/.venv/bin/python 2>&1
ls -la ~/ebook-data/{inbox,processing,archive,output} 2>&1

# Env template
ls -la ~/EbookAutomation/.env.template ~/EbookAutomation/.env 2>&1
```

Write findings to `docs/operations/2026-05-14-claude-dev-01-state-audit.md` (committed on the worktree branch). For each P1 AC, record: present / missing / unexpected. The audit is the input to all subsequent steps.

### Step 2 — Linux config overlay (P3 ACs)

These are pure repo changes. Land them in the worktree before touching the VM further.

**2a. `shutil.which` fallback in settings loader.** Find where `paths.calibre` is resolved from `config/settings.json`. Add a fallback: if the hardcoded path doesn't exist on disk, fall through to `shutil.which("ebook-convert")`. Same config should work on Windows and Linux with no per-machine edits. Test on the desktop (Windows path resolves first) and assert via `python -c "from <loader> import resolve_calibre; print(resolve_calibre())"`.

**2b. `local` provider hard-fail.** In `tools/llm_providers/local_provider.py` (or wherever `get_provider("local")` instantiates), add a guard at construction time:

```python
raise RuntimeError(
    "local provider is hard-failed (EB-210). Route to OpenRouter "
    "via provider: openrouter, model: qwen/qwen3-vl-30b-a3b-instruct."
)
```

The guard fires regardless of OS. Verify via `python -c "from tools.llm_providers import get_provider; get_provider('local')"` raises the expected error on desktop too — this is the intended behavior across platforms.

**2c. `Path` portability audit.** Grep `tools/` for:
- `r"[A-Z]:\\"` (drive letters)
- Hardcoded `\\` separators
- `.exe` literals (EB-221/EB-224 fix territory)
- Direct `$env:TEMP` usage (null on Linux)

Patch any findings to use `pathlib.Path`, `os.path.sep`, `tempfile.gettempdir()`, or platform-aware shims. The EB-221 / EB-224 / BookSmith-plan precedents in `docs/solutions/` are the reference for the patterns.

### Step 3 — Push code + sync to VM (P2 ACs)

```bash
git add -A
git status  # confirm only intended files
git commit -m "feat(EB-210): Linux config overlay + local-provider hard-fail"
git push -u origin worktree/EB-210-vm-bringup
```

On the VM:
```bash
ssh claude-dev-01
cd ~/EbookAutomation
git fetch && git checkout worktree/EB-210-vm-bringup
source .venv/bin/activate
pip install -r requirements.txt
pwsh tools/verify-manifest.ps1 -Verbose  # zero removed features
python -c "import tools.test_pipeline"  # importable
```

### Step 4 — Fill P1 install gaps surfaced by Step 1 audit

For anything the Step-1 audit flagged as missing, install via `apt` (per the ticket's P1 list). Capture each `apt install` line in the runbook script (Step 6) as you go. **Do not** install anything not on the EB-210 P1 list — out-of-scope additions break reproducibility.

### Step 5 — Functional gate (P4 ACs)

Use **Atomic Habits** (smallest book in corpus, per ticket). Confirm the .kfx file is on the VM under `~/ebook-data/archive/` or copy from desktop first.

```bash
# End-to-end pipeline on VM
python tools/pdf_to_balabolka.py "~/ebook-data/archive/Atomic Habits.pdf"
# Expect: EPUB output via Calibre ebook-convert

# VQA run
python tools/visual_qa.py --provider openrouter --input ~/ebook-data/output/<kfx-output>
# Expect: schema-valid VQA report
```

Both must succeed end-to-end. If either fails:
- **Provider/key error** → check `.env` has `OPENROUTER_API_KEY` populated
- **Calibre path error** → Step 2a `shutil.which` fallback isn't firing; debug the loader
- **Timeout error** → STOP. EB-237 territory; do not fix in this ticket. Pick a smaller book or report back.

### Step 6 — Idempotent runbook + ops doc (P5 ACs)

**6a. `scripts/vm-bringup.sh`** — idempotent bash script that, given a fresh Ubuntu 24.04 VM and a populated `.env`, executes all P1 install steps and produces a working environment. Idempotent means: running it twice does no harm. Use `apt install -y` (will skip already-installed packages), `mkdir -p`, conditional clones.

**6b. `docs/operations/vm-pipeline-runbook.md`** — manual SSH-triggered run procedure. Sections:
- Fresh VM bring-up (paste `.env`, run `scripts/vm-bringup.sh`, expected duration)
- Single PDF conversion (the `python tools/pdf_to_balabolka.py <path>` command + expected output location)
- VQA run (the `python tools/visual_qa.py` command)
- Troubleshooting: provider selection errors (where the hard-fail message fires + how to fix), missing keys, Calibre path failures, large-file timeouts (pointer to EB-237)

**6c. Convergence smoke test** — if the VM can be rebuilt cheaply, do it: destroy + recreate + run `scripts/vm-bringup.sh` + paste `.env` + reach Step 5's functional gate. If rebuild is too expensive, document the deferred verification on the ticket comment.

### Step 7 — Open the PR

```bash
git push origin worktree/EB-210-vm-bringup
gh pr create \
  --title "feat(EB-210): VM bring-up + provider routing for claude-dev-01" \
  --body "$(cat <<'EOF'
## Summary

- Linux config overlay (`shutil.which` fallback, `Path` portability) so the same config works on desktop and VM
- `local` provider hard-fails on selection (no silent rerouting to OpenRouter on VM)
- Fills the P1 install gaps surfaced by the Step-1 state audit on `claude-dev-01`
- `scripts/vm-bringup.sh` idempotent bring-up script + `docs/operations/vm-pipeline-runbook.md` operator runbook

## Test plan

- [ ] State audit committed at `docs/operations/2026-05-14-claude-dev-01-state-audit.md`
- [ ] `python -c "from <loader> import resolve_calibre"` resolves on both Windows and Linux
- [ ] `python -c "from tools.llm_providers import get_provider; get_provider('local')"` raises RuntimeError on both
- [ ] `python tools/pdf_to_balabolka.py "Atomic Habits"` produces EPUB on VM
- [ ] `python tools/visual_qa.py --provider openrouter --input <kfx>` produces schema-valid VQA report on VM
- [ ] `tools/verify-manifest.ps1` reports zero removed features
- [ ] `scripts/vm-bringup.sh` is idempotent (second run is no-op)

## Out of scope (deferred)

- Large-file timeout (SCRUM-290 finding) — tracked separately as **EB-237**
- Kokoro TTS, SOPS migration, three-tier router, auto-trigger, file-transfer ergonomics

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Step 8 — Close out

After PR is merged (main session has merge authority):

- Add a Jira comment on EB-210 with: state-audit findings summary, the P1 install delta that was filled, the P4 functional gate evidence (output paths / sizes / VQA report ID).
- Transition EB-210 to Done.
- Compound the work: write `docs/solutions/best-practices/<topic>-2026-05-14.md` with anything non-obvious (per CLAUDE.md INFRA-183 — `ce:compound` runs at end of every plan).

## Constraints

- Worktree branch only. No direct commits to master.
- Do NOT touch `web_service/frontend/` — locked by active EB-233 design swarm.
- Do NOT change the 120s job timeout or file-size caps — EB-237 territory.
- No filesystem junctions inside the worktree pointing at gitignored data dirs.
- Use the global secret-handling rules — `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` live in `.env` (0600, gitignored). Don't `cat`/`echo` `.env`.
- Run `pwsh tools/verify-manifest.ps1` before *and* after code changes. If any feature manifest entry goes PASS→FAIL, stop and fix before continuing.
- Per CLAUDE.md regression rule: never report "no regression" without running `python tools/test_pipeline.py`.

## Premise risks to keep in mind during execution

- The VM may have drift from EB-45 P1 plan (unrelated commits, manual installs). State audit catches this; don't paper over surprises — document them.
- OpenRouter image-byte ceiling (EB-156): verify single-page-retry + DPI-reduce mitigations are present in `visual_qa.py` *before* running Step 5. If absent, surface to the user — don't fix silently in this ticket.
- `local` provider's `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` shim is sb-chat-only. The hard-fail makes this moot on the VM, but the desktop path keeps it. Don't refactor the shim out in this ticket.
- Calibre writes errors to stdout, not stderr (EB-142). Capture both when shelling out.
- Calibre can exit 0 with 0-byte KFX output (SCRUM-290). Gate "done" on `exit_code == 0 AND file_exists AND file_size > 0`.
- `pdf_to_balabolka.py` has top-level `tkinter` imports. Must be invoked as subprocess on headless Linux, not imported. (Already true in EB-45 P1 architecture — don't change it here.)

## Report back when complete

PR URL, state-audit summary (one paragraph), what the install delta actually was, P4 evidence, and a one-sentence answer to: "did anything surprise you that the user should know before merge?"
