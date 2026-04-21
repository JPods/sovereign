# Sovereign

**User-sovereignty AI framework.** Local-first, adversarial-review, consent-gated.

You own the agents. The agents work for you. Nothing executes without your approval.

---

## What it does

- **Watches** your projects 24/7 — files, apps, calendar
- **Harvests** a daily summary at session start
- **Athena** reviews every proposed action across 3 specialized LLMs before it reaches you
- **Audit console** — browser UI where you approve/reject/defer agent actions
- **Standing approvals** — pre-authorize routine actions so Athena isn't reviewing the same thing twice
- **Noise budget** — Athena tracks her own escalation rate; over-escalation is a calibration failure

## One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/JPods/sovereign/main/install.sh | bash
```

The installer will:
1. Check prerequisites (Homebrew, Ollama, Python 3, fswatch)
2. Ask where to install (local folder or external drive)
3. Run the profile wizard — plain-language questions, writes `profile.json`
4. Register Athena's three LLMs with Ollama
5. Start the watcher
6. Open the audit console at `http://localhost:7373`

## Prerequisites

- macOS (v1)
- [Homebrew](https://brew.sh)
- [Ollama](https://ollama.com) with at least one local model
- Python 3.9+

The installer checks and offers to install missing prerequisites.

## Architecture

```
You
 └── profile.json          sovereignty declaration — what agents may do

Allie (synthesis layer)
 └── watcher.sh            background daemon — watches files + apps
 └── harvest.py            daily summary — reads log, reads queue, writes harvest.md

Athena (adversarial review)
 └── athena-triage         llama3.2 — fast classifier (<5s)
 └── athena                gpt-oss:20b — deep security review
 └── athena-reason         deepseek-r1:8b — threat modeling
 └── athena_review.py      routes proposals through models, writes to action_queue.json

Bill / You
 └── audit.py              browser UI — approve/reject/defer queued actions
                           CLI fallback: python3 audit.py --cli
```

## State machine

```
Allie proposes
  → Athena-Triage classifies
    → PASS/routine → approved-routine (logged, not queued)
    → REVIEW → Athena-Deep
      → REASON domain → Athena-Reason (threat model)
        → BLOCK → blocked (logged, not approvable)
        → ESCALATE/CAUTION → pending-audit (requires your review)
        → SAFE → approved
    → BLOCK → blocked immediately

You review in audit console → approve / reject / defer
Every decision is timestamped in agent_log.jsonl
```

## Files

| File | Purpose |
|------|---------|
| `install.sh` | One-command installer |
| `setup/profile_wizard.py` | Interactive profile generator |
| `scripts/watcher.sh` | Background file + app watcher |
| `scripts/watcher-start.sh` | Start watcher |
| `scripts/watcher-stop.sh` | Stop watcher |
| `scripts/harvest.py` | Daily synthesis — reads log + queue + profile |
| `scripts/athena_review.py` | Athena's multi-model review pipeline |
| `scripts/audit.py` | Consent gate — browser + CLI |
| `athena/athena.modelfile` | Athena-Deep (gpt-oss:20b) |
| `athena/athena-triage.modelfile` | Athena-Triage (llama3.2) |
| `athena/athena-reason.modelfile` | Athena-Reason (deepseek-r1:8b) |
| `config/profile.template.json` | Profile template — copy to `config/profile.json` and edit |

## Philosophy

Sovereign is built on three principles:

1. **The user is sovereign.** `profile.json` is a declaration, not a settings file. It defines what agents are permitted to do, with scope and expiry. Agents operate within those limits.

2. **Adversarial review is a first-class agent.** Athena's job is to find what's wrong. Not to allow things — to scrutinize them. A security filter that defaults to yes is not security.

3. **The consent gate has teeth.** Overdue items escalate in `harvest.md`. The system applies pressure back on you. Approval is not optional — it is the mechanism by which you remain sovereign.

---

Built by [JPods](https://jpods.com). Solar, bottom-up, locally governed.
