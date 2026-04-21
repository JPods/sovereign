# Sovereign — Forward Plan

*Updated: April 21, 2026*

**Domain reserved:** `secureSovereign.io` (parked — site deferred until JPods and WebClerk are operational)

---

## The Immediate Goal

Allie, Athena, and Alice need to work autonomously on the two live platforms:
- **JPods** — SketchUp plugin, control system, robot hardware
- **WebClerk** — open-source local commerce, DynamicCatalogs, agent layer

Sovereign is the consent and oversight layer that keeps those agents honest and Bill in control.

---

## Phase 1 — Ship v1 (now → May 1, 2026)

| Item | Status | Owner |
|------|--------|-------|
| GitHub repo, README, all scripts | ✅ done | — |
| `jpod_privacy.rb` — six passenger promises as enforced Ruby code | not started | Alice |
| `19-agent-coordination.md` — update for Athena pipeline + state machine | not started | Allie |
| End-to-end install test (fresh path) | not started | Allie |

---

## Phase 2 — Agents Operating on Their Own (May → June 2026)

This is the core objective: Allie, Athena, and Alice aware of both platforms, coordinating without Bill in the middle.

### Allie (synthesis)
- Reads JPods watcher log + WebClerk `alice_log` daily
- Produces a single `harvest.md` that spans both platforms
- Flags cross-domain consequences: e.g., a JPods privacy decision that affects WebClerk identity
- Proposes actions to Athena before acting

### Athena (adversarial review)
- Reviews proposals from both Allie and Alice
- Same three-model pipeline for both platforms
- Files OSL items directly to `profile.json` `must_fix`
- Tracks her own noise budget — calibration failure if >5 escalations/week
- Time-box approvals for bounded-risk actions

### Alice (WebClerk agent)
- Submits proposed actions to Athena via `athena_review.py propose`
- Reads `action_queue.json` for her own pending items
- Reads `agent_log.jsonl` to understand what Athena has already flagged
- Never executes a non-standing action without queue status = `approved`

### What gets built in Phase 2
- **Time-box approvals** — approve for N hours, auto-expire
- **OSL auto-filing** — Athena writes directly to `must_fix` array on `osl-file` response
- **Cross-platform harvest** — single `harvest.md` covering JPods + WebClerk
- **Alice → Athena protocol** — standardized `propose` call format for WebClerk actions
- **Noise budget display** in `audit.py` — week-over-week escalation rate

---

## Phase 3 — Harden and Extend (June → Sept 2026)

- **External probes live** — test OpenAI + Anthropic probe paths on real BLOCK cases
- **Standing approvals UI** — manage in browser, not just JSON
- **Sovereign local API** — HTTP endpoint so any agent can submit proposals
- **Linux support** — remove macOS-only constraint
- **MyCarryOn integration** — sovereignty declaration (profile.json) travels with the user

---

## Phase 4 — Platform (2027)

- `secureSovereign.io` as product and community — open governance, bottom-up, not JPods-controlled
- **Agent Consent Protocol** — formalize the state machine as a spec other frameworks can implement
- Reference implementations for Home Assistant, Open WebUI, and other personal AI ecosystems

---

## Agent Trio — Operating Model

```
Bill
  └── profile.json          sovereignty declaration
  └── audit.py              daily consent gate

Allie (synthesis)
  reads:  watcher log, alice_log, harvest_lookback_days
  writes: harvest.md, agent_log.jsonl
  asks:   Athena before proposing anything that touches state

Athena (adversarial review)
  receives: proposals from Allie + Alice
  routes:   triage → deep → reason
  writes:   action_queue.json, agent_log.jsonl, must_fix (on osl-file)
  reports:  to Bill via audit.py + harvest.md escalation

Alice (WebClerk agent)
  receives: tasks from Bill via wcapi notes
  checks:   action_queue.json before executing
  submits:  proposals to Athena for anything not standing-approved
  reads:    agent_log.jsonl to understand Athena's prior findings
```

**The rule:** Nothing executes that hasn't cleared Athena. Standing approvals exist for genuine routine actions. Everything else goes through the queue and waits for Bill.

---

## Open Items (OSL)

| ID | Severity | Project | Description | Deadline |
|----|----------|---------|-------------|----------|
| OSL-01 | HIGH | Sovereign | End-to-end install test on fresh path | 2026-05-01 |
| OSL-02 | HIGH | JPods | `jpod_privacy.rb` — six passenger promises as code | 2026-05-01 |
| OSL-03 | MEDIUM | Sovereign | Alice → Athena protocol documented and tested | 2026-05-15 |
| OSL-04 | MEDIUM | Sovereign | Time-box approvals implemented | 2026-06-01 |
