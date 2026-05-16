# Recovery-Rail Measurement (EB-292) — Operator Notes

**Started:** 2026-05-16
**Target re-evaluation date:** ~2026-06-15 (file a follow-up ticket then)
**Status:** Active data collection

## Why this exists

Two consecutive Phase 3 brainstorm+plan cycles in 2026-05 both got the same
critique from the product-lens reviewer during document-review:

> *"You're building stateful infrastructure for an unmeasured problem."*

This ticket adds the instrumentation needed to decide — based on evidence,
not guesswork — whether Phase 3 recovery work (accounts, magic-link auth,
Stripe-customer-binding recovery, or anything in that family) is actually
justified.

The decision is gated on three data sources collected over a 30-60 day
window:

1. **`/api/recover` POST volume** — how often users actually paste a
   session_id into the recovery form
2. **`/recover` page-view localStorage state distribution** — how often
   users arrive at the recovery page with empty/expired/invalid localStorage
3. **`/payment/success` revisit count** — how often users come back to a
   completed session URL (the most common Phase 2 recovery path)
4. **Support-inbox volume for recovery-related complaints** — counted
   manually via the tagging convention below

If aggregate signals are below the thresholds in the EB-292 ticket's
"Success criteria" section, the entire Phase 3 recovery problem is
hypothetical and the paused brainstorm at
`docs/brainstorms/2026-05-16-eb45-phase3b-stripe-customer-binding-and-light-mailing-list-requirements.md`
can be retired.

## Operator support-email tagging convention

When a support email arrives at `support@leafbind.io` that mentions:

- "lost tokens"
- "can't find my credits"
- "lost my purchase"
- "I bought credits but..." (any variation)
- "where did my tokens go"
- "missing tokens"
- Any other phrasing that maps to "I bought credits and now I can't use them"

…apply the **`recovery-support`** label in Gmail (or whichever inbox
client is in use). The 2026-06-15 review will count these by querying
`label:recovery-support after:2026/05/16 before:2026/06/15`.

The label should be:

- Applied to the **inbound** email, not the reply
- Applied even if the user's actual issue turns out to be a different cause
  (e.g. expired tokens) — the goal is to count *complaints*, not validated
  recovery cases
- Cumulative — do not remove the label once applied

If the operator answers the support ticket with a recovery solution that
worked, add a second label `recovery-resolved` so the 2026-06-15 review
can compute a resolution rate. If the user reports the tokens were
unrecoverable, leave only `recovery-support` (the unresolved count
matters too — it's the population Phase 3 would actually help).

## Data review query (after 2026-06-15)

```powershell
# From the FastAPI VM:
sqlite3 /opt/leafbind/data/web_service.db "
  SELECT event_type, COUNT(*) AS events_30d
  FROM recovery_events
  WHERE created_at > strftime('%s','now') - 30*86400
  GROUP BY event_type
  ORDER BY events_30d DESC
"
```

Expected output shape:

```
api_recover_post|N1
payment_success_revisit|N2
recover_page_view|N3
```

Cross-reference with the localStorage state distribution:

```powershell
sqlite3 /opt/leafbind/data/web_service.db "
  SELECT json_extract(details, '$.localStorage_state') AS state, COUNT(*) AS n
  FROM recovery_events
  WHERE event_type = 'recover_page_view'
    AND created_at > strftime('%s','now') - 30*86400
  GROUP BY state
  ORDER BY n DESC
"
```

## Decision tree (per EB-292 success criteria)

After 30-60 days of collection:

| Signal | Threshold | Decision |
|---|---|---|
| `/api/recover` POSTs | < 10 / month | Recovery is hypothetical |
| `recover_page_view` with `empty` localStorage | < 5% of all views | Recovery is hypothetical |
| `recovery-support` labelled tickets | < 2 / month | Recovery is hypothetical |
| ALL THREE below threshold | — | **Retire the paused brainstorm. Phase 3B will not ship.** |
| `/api/recover` POSTs | ≥ 10 / month | Recovery is real |
| `empty` localStorage rate | ≥ 10% | Real |
| `recovery-support` labelled tickets | ≥ 5 / month | Real |
| ANY meaningful signal | — | **Unpause the brainstorm. Address the `customer_creation="if_required"` feasibility F1 finding first as a Phase 2 prerequisite patch, then proceed to plan + ship Phase 3B.** |
| Borderline (mixed signals) | — | **Extend measurement window 30 more days; revisit then.** |

## Files affected

- `web_service/recovery_events_store.py` — the SQLite table + log_event() API
- `web_service/routes/recover.py` — instrumented at every POST
- `web_service/routes/recovery_events.py` — `/api/recovery-events/recover-view` endpoint
- `web_service/routes/payment.py` — instrumented at the revisit path
- `web_service/main.py` — lifespan init + router mount
- `web_service/frontend/components/RecoverClient.tsx` — fetch on mount
- `web_service/frontend/next.config.js` — proxy rewrite for the new endpoint

## Related artifacts

- Ticket: [EB-292](https://jlfowler1084.atlassian.net/browse/EB-292)
- Paused brainstorm (reusable if data justifies):
  `docs/brainstorms/2026-05-16-eb45-phase3b-stripe-customer-binding-and-light-mailing-list-requirements.md`
- Retired brainstorm:
  `docs/brainstorms/2026-05-16-eb45-phase3-accounts-persistent-tokens-requirements.md`
- Retired plan:
  `docs/plans/2026-05-16-001-feat-eb45-phase3-accounts-persistent-tokens-plan.md`
- Closed Phase 3 epic: [EB-284](https://jlfowler1084.atlassian.net/browse/EB-284) (+ EB-285 through EB-289)
