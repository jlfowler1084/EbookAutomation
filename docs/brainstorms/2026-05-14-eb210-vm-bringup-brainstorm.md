---
title: "brainstorm: EB-210 Hetzner VM bring-up + provider routing"
type: brainstorm
status: complete
date: 2026-05-14
origin: https://jlfowler1084.atlassian.net/browse/EB-210
feeds: ce:work (skip ce:plan — single-implementer scope)
---

# brainstorm: EB-210 Hetzner VM bring-up + provider routing

## Problem framing (confirmed)

Make PDF→Ebook conversion run on `claude-dev-01` (Hetzner Cloud, Ubuntu 24.04) without any desktop dependency. v1 scope is text-layer + scanned PDF → EPUB/AZW3. Route what used to call sb-chat (Qwen3.5-35B local) on the desktop to OpenRouter (`qwen/qwen3-vl-30b-a3b-instruct`) on the VM.

**Key reframe vs ticket title:** This is *not* greenfield bring-up. EB-45 Phase 1 already deployed FastAPI + Python pipeline + Calibre to this VM. EB-210's real delta is:

1. Linux config overlay (`Path` portability, `shutil.which("ebook-convert")` fallback in `settings.json` loader)
2. Provider-routing policy for the `local` provider on Linux (hard-fail — see decision below)
3. Filling any P1 install gaps not covered by EB-45 P1 (`ocrmypdf`, `tesseract`, PowerShell 7, working-dirs outside repo)
4. A reproducible runbook so the VM can be rebuilt from scratch in one command

## Execution shape (confirmed)

**Single-implementer ticket — no swarm.**

The five phases (P1 system env → P2 code sync → P3 Linux config → P4 functional gate → P5 runbook) form a sequential chain. The only independent stream is the code-side Linux portability audit (P3-1 + P3-2), which is pure repo work — not enough surface area to justify a parallelization map. Skip `ce:plan`; go straight to `ce:work` or direct implementation.

## Decisions locked during brainstorm

### `local` provider behavior on VM — hard-fail on selection

When the VM's runtime config selects `provider: local`, the provider factory raises an explicit `RuntimeError` at startup with a message pointing at OpenRouter. No silent rerouting. No warn-and-proceed.

**Why:** The hidden cost of silent rerouting is that someone copies a desktop config to the VM and "everything works" — until a regression test passes against `local`-on-desktop and fails against `openrouter`-on-VM with a model behavior delta. Hard-fail forces config to be reviewed before deployment. Aligns with the ticket's stated preference (P3 AC: "preferred — silent surprise has higher cost").

**How to apply:** In `tools/llm_providers/local_provider.py` (or wherever the factory lives), add a guard at instantiation time. The guard fires regardless of OS; the failure surfaces in the FastAPI startup logs and is reproducible via `python -c "from tools.llm_providers import get_provider; get_provider('local')"`.

### Large-file timeout (SCRUM-290 finding) — deferred to new ticket

Out of scope for EB-210. Opened as a separate ticket because the 120 s / 21 min mismatch is a product-policy question (tiered timeouts? lower file-size cap? size-derived dynamic timeout?) not a bring-up step.

See: the new follow-up ticket linked from EB-210 and EB-45.

## What needs to happen during implementation

In rough order (sequential):

1. **State audit** — `ssh claude-dev-01`, walk EB-210 P1 ACs against actual installed state. Capture diff as the actual TODO list. Likely most of P1 is no-op verification.
2. **Linux config overlay** (P3) — code change in `config/settings.py` loader to use `shutil.which("ebook-convert")` when the hardcoded Windows path isn't resolvable. Audit `Path` usage across `tools/` for `C:\` literals or `\\` separators (Grep for `r"[A-Z]:\\"` and similar). Add the local-provider hard-fail.
3. **Code sync** (P2) — push the P3 changes from desktop, pull on VM, `pip install -r requirements.txt`.
4. **Functional gate** (P4) — pick the smallest book in corpus (Atomic Habits per ticket), run `python tools/pdf_to_balabolka.py` end-to-end, then `python tools/visual_qa.py --provider openrouter --input <kfx>`. Both must produce schema-valid outputs.
5. **Runbook** (P5) — capture P1 install steps as `scripts/vm-bringup.sh` (idempotent). Verify by destroying and rebuilding the VM, or by inspection if rebuild is too expensive.

## Premise risks acknowledged

- **Actual VM state may differ from EB-45 P1 plan.** State audit (step 1) is the first action before assuming P1 is "mostly done."
- **OpenRouter image-byte ceiling (EB-156).** The ticket flags this — confirm the single-page-retry + DPI-reduce mitigations from EB-156 are present in `visual_qa.py` before running large-book regression on VM.
- **`local` provider's `extra_body` shim.** `tools/llm_providers/local_provider.py` requires `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` for sb-chat. This must NOT be passed to OpenRouter (no reasoning parser there). Hard-fail strategy makes this moot in practice — `local` never gets called on the VM — but the code path lives on for desktop use.
- **120s timeout vs reality.** Documented in the new follow-up ticket. Means the P4 functional gate must use a *small* book (Atomic Habits), not a representative-size one, or the gate will fail on timeout rather than on actual pipeline issues.

## Out of scope (explicit)

Mirrors EB-210's stated boundaries:

- Kokoro TTS / audiobook stack (SCRUM-325)
- SOPS `.env` migration (INFRA-179)
- Three-tier router service adoption (INFRA-187)
- systemd timer / cron / inotify auto-trigger
- File transfer ergonomics (Syncthing etc.)
- Removing `local` provider code from the desktop path

## Next action

`ce:work EB-210` or direct implementation. Plan artifact = this brainstorm + EB-210's P1-P5 ACs as the task list. No `ce:plan` needed.
