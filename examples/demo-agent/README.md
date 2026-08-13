# Agent ToolTrust — Demo Agent

The reference demo agent for **Agent ToolTrust v0.1.0** (WBS M8 Task 1 & 2). It
wraps a handful of plain Python tool-callables with the raw
[`@engine.guard`](../../src/agent_tooltrust/adapters/raw.py) adapter and shows the
engine's full decision spectrum — **allow, audit, escalate, deny, and replan** —
in a single guided session, plus an adversarial variant that is blocked no
matter what tricks are tried.

## What it demonstrates

| Decision | Scenario |
|----------|----------|
| **allow** | Low-risk read (`query_logs`) in a safe environment (staging / internal) |
| **audit** | Destructive op (`drop_database`) in staging by a trusted, low-risk agent — logged, not blocked |
| **escalate** | Write to production (`deploy_service`) requires an on-call approver |
| **deny** | Destructive write to production (`drop_database`) is hard-blocked |
| **replan** | A blocked write is replanned to a benign read, which the engine allows |
| **adversarial** | Prompt injection + Unicode/homoglyph obfuscation are denied regardless |

## Run it

```bash
# 5-call decision spectrum
python examples/demo-agent/demo.py

# adversarial variant
python examples/demo-agent/demo_adversarial.py
```

Both outputs below were captured from a clean run on the released engine.

## Demo output — decision spectrum

```
========================================================================
  1. ALLOW  - low-risk read in a safe environment
========================================================================
  decision: ALLOW (allow_low_risk)
  explain : query_logs (read) in staging on internal data is within the allow band. Proceeding.
  -> executed: rows for "SELECT * FROM errors WHERE level='critical'"

========================================================================
  2. AUDIT  - destructive op, safe env, trusted agent (logged)
========================================================================
  decision: AUDIT (audit_sensitive_data)
  explain : drop_database (delete) in staging on restricted data is logged for review. Proceeding with enhanced audit.
  -> executed: dropped temp_scratch in staging

========================================================================
  3. ESCALATE - write to production requires an approver
========================================================================
  decision: ESCALATE (escalate_prod_write)
  explain : Write action (deploy) in production on restricted data requires approval. Route to the on-call approver. Policy rule: Write actions in production require approval.
  -> not executed (engine blocked)

========================================================================
  4. DENY  - destructive write to production is blocked
========================================================================
  decision: DENY (deny_critical_op)
  explain : drop_database (delete) in production on restricted data is blocked: destructive operation on sensitive data with irreversible side effects. Use a read-only alternative or move to a lower-risk environment. Policy rule: Deletes in production are blocked.
  -> not executed (engine blocked)

========================================================================
  5. REPLAN - blocked destructive write -> safe read
========================================================================
  [Denied] deny_critical_op
  [Replan] switching to a benign read...
  decision: ALLOW (allow_low_risk)
  explain : query_logs (read) in staging on internal data is within the allow band. Proceeding.
  -> executed: rows for 'SELECT count(*) FROM archive_2020'
```

## Demo output — adversarial variant

```
========================================================================
  ADVERSARIAL 1 - prompt injection inside a tool argument
========================================================================
  [DENY] deny_critical_op
         drop_database (delete) in production on restricted data is blocked: destructive operation on sensitive data with irreversible side effects. Use a read-only alternative or move to a lower-risk environment. Policy rule: Deletes in production are blocked.

========================================================================
  ADVERSARIAL 2 - Unicode / homoglyph obfuscation
========================================================================
  [DENY] deny_critical_op
         normalized 'drop_databаse' -> drop_database (delete) in production on restricted data is blocked: destructive operation on sensitive data with irreversible side effects. Use a read-only alternative or move to a lower-risk environment. Policy rule: Deletes in production are blocked.
```

## Stage-by-stage walkthrough

The demo shows how a single engine evaluation flows through the pipeline
(`normalize → score → decide → explain`), and what each decision means:

1. **ALLOW** — low-risk reads land in the `low` band → `allow`. The tool body runs.
2. **AUDIT** — the same destructive `delete` in **staging** by a trusted,
   low-risk agent (`release-bot`) scores `medium` → `audit`. Not blocked, but
   logged for review.
3. **ESCALATE** — any *write* in **production** triggers
   `escalate_prod_write`; the raw adapter raises `ToolTrustDecisionError`, and
   the call is routed to an approver instead of executing.
4. **DENY** — a destructive *delete* in **production** is
   `deny_critical_op`: fail-closed, irreversible, never executed.
5. **REPLAN** — the corrective loop: a denied write is switched to a safe
   `query_logs` read that the engine allows.

### Adversarial behaviour

- **Prompt injection** smuggled inside a tool argument does not change the
  verdict: the argument is data, and a destructive production call is denied
  regardless of content.
- **Unicode / homoglyph obfuscation** (`drop_datab` + Cyrillic U+0430 instead of
  ASCII `a`) is folded by normalization (`NFKC → casefold → confusable
  transliteration` in `normalize.py`) back to `drop_database`, which is then
  denied. Obfuscation cannot bypass the engine.

## Layout

```
examples/demo-agent/
├── demo.py                 # 5-call decision spectrum (allow/audit/escalate/deny/replan)
├── demo_adversarial.py     # prompt injection + Unicode/homoglyph denial
└── README.md               # this file (with captured outputs)
```

## Success against WBS M8

- **Task 1** — 5-call demo scenario via raw Python adapter ✅
- **Task 2** — 2 adversarial calls correctly denied ✅
- All 4 decision types + replan demonstrated in one session ✅
