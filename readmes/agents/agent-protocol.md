# Agent Protocol — Machine-Readable Reference
**Last Updated:** 2026-04-21
**Purpose:** Precise call syntax, credential IDs, and behavioral rules for Allie, Alice, and Athena to interact with each other. This file is the contract; `19-agent-coordination.md` is the narrative explanation.

---

## Agent Registry

| Agent | WC User ID | WC Connection ID | Token helper | Primary domain |
|-------|-----------|-----------------|--------------|---------------|
| Allie  | 48 | 22 | `allie_wc_token.py` | Cross-domain synthesis, CarryOn, session watching |
| Athena | 49 | 23 | `allie_wc_token.py --agent athena` | Security review, privacy enforcement, action gate |
| Alice  | 50 | 24 | `allie_wc_token.py --agent alice`  | WebClerk data quality, billing, pattern recognition |

---

## Getting a Token

```bash
# Allie
TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py)

# Athena
TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py --agent athena)

# Alice
TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py --agent alice)
```

Token is cached in `/tmp/allie_wc_token_{agent}.json`, refreshed automatically 5 min before expiry.
Credentials stored in `/Volumes/Allie/config/wc_credentials.json` (mode 600).

---

## Channel 1: Allie ↔ Alice — WebClerk Notes

### Allie → Alice (task request)

```bash
TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py)
curl -s -X POST http://localhost:8000/wcapi/save/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "action",
    "title": "<short task summary>",
    "status": "open",
    "description": {
      "from": "allie",
      "to": "alice",
      "request": "...",
      "context": "...",
      "created_by": "allie",
      "category": "pending"
    }
  }'
```

**Use when:** Allie identifies a data quality issue, keyword gap, billing anomaly, or search problem in WebClerk that Alice should investigate.

### Alice → Allie (report / flag)

```bash
TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py --agent alice)
curl -s -X POST http://localhost:8000/wcapi/save/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "action",
    "title": "<finding summary>",
    "status": "open",
    "description": {
      "from": "alice",
      "to": "allie",
      "finding": "...",
      "needs_bill": true,
      "category": "alice_log"
    }
  }'
```

**Use when:** Alice has completed a task affecting Allie's cross-domain view, or has found an issue requiring Bill's judgment routed through Allie.

### Reading pending notes

```bash
TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py)
# Allie reads Alice's pending notes at session start
curl -s "http://localhost:8000/wcapi/get/?model_name=action&status=open" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for r in d.get('data',{}).get('results',[]):
    desc = r.get('description') or {}
    if isinstance(desc,str): import json as j; desc=j.loads(desc) if desc.startswith('{') else {}
    if desc.get('from') == 'alice':
        print(f\"[{r['id']}] {r.get('title')} — {desc.get('finding','')[:80]}\")
"
```

---

## Channel 2: Any Agent → Athena — Sovereign Review Pipeline

Every non-standing action proposed by Allie or Alice goes through Athena's three-model pipeline before it executes.

### Submit a proposal

```bash
python3 /Volumes/Allie/scripts/athena_review.py propose \
  --from allie \
  --action "Write passenger data summary to harvest.md" \
  --context "Daily harvest run, no PII" \
  --domain data

# With file content (up to 5000 chars read, per OSL-06)
python3 /Volumes/Allie/scripts/athena_review.py propose \
  --from alice \
  --action "Deploy keyword index change" \
  --context "refs.keywords update for WebClerk search" \
  --domain code \
  --file /path/to/file.py
```

### Check results

```bash
python3 /Volumes/Allie/scripts/athena_review.py status
python3 /Volumes/Allie/scripts/athena_review.py pending
```

### Athena's pipeline (state machine)

```
proposed
  → athena-triage (llama3.2, <5s)
      PASS/routine  → approved-routine   (log only, no queue entry)
      BLOCK         → blocked            (do not proceed; re-propose after fix)
      REVIEW        → athena-deep (gpt-oss:20b, up to 120s)
          SAFE      → approved
          CAUTION   → pending-audit      (Bill reviews in audit.py :7373)
          REASON    → athena-reason (deepseek-r1:8b, up to 180s)
              SAFE      → approved
              ESCALATE  → pending-audit
              BLOCK     → blocked
```

### Decision rules

| Status | Meaning | What to do |
|--------|---------|-----------|
| `approved-routine` | Standing-approved class | Proceed immediately |
| `approved-standing` | Matched profile.json standing approval | Proceed immediately |
| `approved` | Athena cleared | Proceed |
| `pending-audit` | Needs Bill's review | Wait; check audit.py at http://localhost:7373 |
| `blocked` | Athena blocked it | Do NOT proceed; fix the issue and re-propose |
| `rejected` | Bill rejected | Do not re-propose without new information |
| `deferred` | Bill deferred | Will re-queue; await |

### Standing approvals (auto-approved, skip Athena)

```
harvest-write       — append to harvest.md files
log-append          — append to agent_log.jsonl
document-index      — add/update document records in WebClerk
data-quality-check  — read-only analysis of WebClerk records
pattern-log         — log a pattern observation (Alice)
billing-read        — read billing/trip records
```

---

## Channel 3: Athena → Allie/Alice — Findings

Athena writes findings to `agent_log.jsonl` and the action queue. Agents read their findings:

```bash
# Read recent Athena findings
grep '"event"' /Volumes/Allie/config/agent_log.jsonl | tail -20

# Read queue items pending audit
python3 /Volumes/Allie/scripts/athena_review.py pending

# Open audit UI (Bill's review surface)
open http://localhost:7373
```

Athena also POSTs OSL filings to WebClerk as action records under project 25.

---

## Channel 4: Allie ↔ Athena — Mutual Review

Allie and Athena review each other's synthesis on a weekly cadence (or triggered by either agent).

**Log event format for mutual review:**

```json
{
  "ts": "2026-04-21T10:00:00",
  "event": "mutual-review",
  "reviewer": "athena",
  "reviewed": "allie",
  "subject": "harvest.md 2026-04-21",
  "verdict": "SAFE|CAUTION|ESCALATE",
  "findings": []
}
```

**The rule:** Allie reviews Athena's findings for over-escalation. Athena reviews Allie's synthesis for capture or drift. Neither can approve their own actions. Bill is always the final arbiter.

---

## Behavioral Contracts

### Allie
- Constructive posture: build what Bill intends, hold cross-domain context
- Submits non-standing actions to Athena before executing
- Reads Alice's pending notes at session start when working in WebClerk
- Never accumulates authority beyond what Bill grants
- Never centralizes what should be distributed

### Alice
- Data owner posture: WebClerk models (`contact`, `action`, `communication`, `connection`, `setting`, `document`)
- Submits non-standing actions to Athena before executing
- Pattern promotions to `setting` require Bill's activation (never automatic)
- Flags billing/data risks to Allie for cross-domain routing
- Trip record ingestion requires signed records from Natalie (NS-05 — not yet closed)

### Athena
- Adversarial posture: find what is wrong; do not soften findings
- Does not default to approve; CAUTION is a real verdict
- Logs every review in `agent_log.jsonl` and `action_queue.json`
- Holds the private key; signs all session tokens and agent README manifests
- LLM review pipeline (`athena_review.py`) is advisory; runtime guard (`jpod_console.rb`) is enforcing
- File truncation limit: 5000 chars (OSL-06 — under review)
- Deep model timeout: 120s; Reason model timeout: 180s

### All agents
- Payload is always readable. Sign for authenticity; never encrypt to obscure.
- Any agent can sign and require signatures without asking permission.
- Open questions belong in the agent's `.md` file, not held privately.
- Bill is the only one who can promote patterns, approve pending-audit items, or unblock a blocked action.

---

## Key File Locations

| What | Where |
|------|-------|
| Token helper | `/Volumes/Allie/scripts/allie_wc_token.py` |
| Credentials | `/Volumes/Allie/config/wc_credentials.json` (mode 600) |
| Athena review script | `/Volumes/Allie/scripts/athena_review.py` |
| Action queue | `/Volumes/Allie/config/action_queue.json` |
| Agent log | `/Volumes/Allie/config/agent_log.jsonl` |
| Audit UI | `python3 /Volumes/Allie/scripts/audit.py` → http://localhost:7373 |
| Sovereign profile | `/Volumes/Allie/config/profile.json` |
| Agent readmes | `/Volumes/Allie/readmes/agents/` |
| This file | `/Volumes/Allie/readmes/agents/agent-protocol.md` |
| Narrative protocol | `/Volumes/Allie/readmes/19-agent-coordination.md` |
