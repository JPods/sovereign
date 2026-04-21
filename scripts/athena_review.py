#!/usr/bin/env python3
"""
athena_review.py
Athena's autonomous multi-model review pipeline.

Called by Allie when proposing an action. Runs three models in sequence:
  1. athena-triage  (llama3.2 — fast classifier, <5s)
  2. athena         (gpt-oss:20b — deep security review, called if REVIEW/REASON)
  3. athena-reason  (deepseek-r1:8b — threat modeling, called if REASON domain)

Writes one entry to /Volumes/Allie/config/agent_log.jsonl per review.
Writes approved/flagged actions to /Volumes/Allie/config/action_queue.json.

Usage:
  python3 athena_review.py propose --from allie --action "..." --context "..." [--domain privacy]
  python3 athena_review.py propose --from allie --action "..." --context "..." --file /path/to/file.rb
  python3 athena_review.py status          — show queue summary
  python3 athena_review.py pending         — list items awaiting Bill's audit

Allie's protocol: every proposed action MUST pass through this script before entering the queue.
Nothing reaches Bill without Athena's review logged.
"""

import sys
import json
import uuid
import datetime
import subprocess
import argparse
import pathlib

ALLIE = pathlib.Path("/Volumes/Allie")
QUEUE_PATH = ALLIE / "config" / "action_queue.json"
LOG_PATH = ALLIE / "config" / "agent_log.jsonl"

# Model routing table
MODELS = {
    "triage": "athena-triage",
    "deep":   "athena",
    "reason": "athena-reason",
}

# Domains that always invoke athena-reason
REASON_DOMAINS = {"privacy", "security", "code", "infrastructure"}


# ── Ollama calls ──────────────────────────────────────────────────────────────

def call_ollama(model: str, prompt: str, timeout: int = 120) -> str:
    """Call an Ollama model and return the response text."""
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip()}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return f"ERROR: {model} timed out after {timeout}s"
    except FileNotFoundError:
        return "ERROR: ollama not found in PATH"


# ── Triage parse ──────────────────────────────────────────────────────────────

def parse_triage(text: str) -> dict:
    """Extract TRIAGE, DOMAIN, FLAG from athena-triage response."""
    result = {"triage": "REVIEW", "domain": "routine", "flag": text}
    for line in text.splitlines():
        if line.startswith("TRIAGE:"):
            result["triage"] = line.split(":", 1)[1].strip()
        elif line.startswith("DOMAIN:"):
            result["domain"] = line.split(":", 1)[1].strip()
        elif line.startswith("FLAG:"):
            result["flag"] = line.split(":", 1)[1].strip()
    return result


def parse_deep(text: str) -> dict:
    """Extract RISK and RECOMMENDATION from athena / athena-reason response."""
    result = {"risk": "CAUTION", "recommendation": "escalate-to-bill", "full_text": text}
    for line in text.splitlines():
        if line.startswith("RISK:"):
            result["risk"] = line.split(":", 1)[1].strip()
        elif line.startswith("RECOMMENDATION:"):
            result["recommendation"] = line.split(":", 1)[1].strip()
    return result


# ── Log ───────────────────────────────────────────────────────────────────────

def log_event(entry: dict):
    """Append one JSON line to agent_log.jsonl."""
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Queue ─────────────────────────────────────────────────────────────────────

def load_queue() -> dict:
    if QUEUE_PATH.exists():
        try:
            return json.loads(QUEUE_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"actions": []}


def save_queue(queue: dict):
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def add_to_queue(item: dict):
    queue = load_queue()
    queue["actions"].append(item)
    save_queue(queue)


# ── Review pipeline ───────────────────────────────────────────────────────────

def review(from_agent: str, action_text: str, context: str, domain_hint: str = None) -> dict:
    """
    Run the full Athena review pipeline.
    Returns a queue item dict with review results embedded.
    """
    action_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"\n[Athena] Starting review {action_id}")
    print(f"  From:    {from_agent}")
    print(f"  Action:  {action_text[:80]}{'...' if len(action_text) > 80 else ''}")

    # ── Stage 1: Triage ───────────────────────────────────────────────────────
    print(f"  [1/3] Triage ({MODELS['triage']})...", end=" ", flush=True)
    triage_prompt = f"""Proposed action from {from_agent}:

ACTION: {action_text}

CONTEXT: {context}
{f'DOMAIN HINT: {domain_hint}' if domain_hint else ''}

Classify this action."""

    triage_raw = call_ollama(MODELS["triage"], triage_prompt, timeout=30)
    triage = parse_triage(triage_raw)
    domain = domain_hint or triage["domain"]
    print(f"→ {triage['triage']} / {domain}")

    log_event({
        "event": "triage",
        "action_id": action_id,
        "from": from_agent,
        "triage": triage["triage"],
        "domain": domain,
        "flag": triage["flag"],
    })

    # BLOCK at triage — no further review needed
    if triage["triage"] == "BLOCK":
        item = {
            "id": action_id,
            "created": now,
            "from": from_agent,
            "action": action_text,
            "context": context,
            "domain": domain,
            "status": "blocked",
            "triage": triage,
            "deep_review": None,
            "reason_review": None,
            "bill_audit": None,
        }
        log_event({"event": "blocked-at-triage", "action_id": action_id, "flag": triage["flag"]})
        print(f"  ⛔ BLOCKED at triage: {triage['flag']}")
        return item

    # PASS at triage — skip deep review for truly routine items
    if triage["triage"] == "PASS" and domain == "routine":
        item = {
            "id": action_id,
            "created": now,
            "from": from_agent,
            "action": action_text,
            "context": context,
            "domain": domain,
            "status": "approved-routine",
            "triage": triage,
            "deep_review": None,
            "reason_review": None,
            "bill_audit": None,
        }
        log_event({"event": "approved-routine", "action_id": action_id})
        print(f"  ✓ Approved (routine, no deep review needed)")
        return item

    # ── Stage 2: Deep review ──────────────────────────────────────────────────
    print(f"  [2/3] Deep review ({MODELS['deep']})...", end=" ", flush=True)
    deep_prompt = f"""Triage result: {triage['triage']} / domain: {domain}
Triage flag: {triage['flag']}

Proposed action from {from_agent}:
ACTION: {action_text}
CONTEXT: {context}

Perform your full security review."""

    deep_raw = call_ollama(MODELS["deep"], deep_prompt, timeout=120)
    deep = parse_deep(deep_raw)
    print(f"→ {deep['risk']} / {deep['recommendation']}")

    log_event({
        "event": "deep-review",
        "action_id": action_id,
        "risk": deep["risk"],
        "recommendation": deep["recommendation"],
    })

    # ── Stage 3: Reason (for high-risk domains) ───────────────────────────────
    reason = None
    if domain in REASON_DOMAINS or triage["triage"] == "REASON" or deep["risk"] in ("ESCALATE", "BLOCK"):
        print(f"  [3/3] Threat modeling ({MODELS['reason']})...", end=" ", flush=True)
        reason_prompt = f"""Deep review result: {deep['risk']} — {deep['recommendation']}

Proposed action from {from_agent}:
ACTION: {action_text}
CONTEXT: {context}
DOMAIN: {domain}

Previous finding: {deep['full_text'][:500]}

Perform adversarial threat modeling."""

        reason_raw = call_ollama(MODELS["reason"], reason_prompt, timeout=180)
        reason = parse_deep(reason_raw)
        reason["full_text"] = reason_raw
        print(f"→ {reason['risk']} / {reason['recommendation']}")

        log_event({
            "event": "reason-review",
            "action_id": action_id,
            "risk": reason["risk"],
            "recommendation": reason["recommendation"],
        })
    else:
        print(f"  [3/3] Threat modeling — skipped (domain: {domain})")

    # ── Final verdict ─────────────────────────────────────────────────────────
    # Worst risk wins
    risks = ["SAFE", "CAUTION", "ESCALATE", "BLOCK"]
    all_risks = [deep["risk"]]
    if reason:
        all_risks.append(reason["risk"])
    final_risk = max(all_risks, key=lambda r: risks.index(r) if r in risks else 0)

    # Status based on final risk
    if final_risk == "BLOCK":
        status = "blocked"
    elif final_risk in ("ESCALATE",) or (reason and reason["recommendation"] == "escalate-to-bill"):
        status = "pending-audit"   # requires Bill's explicit approval
    elif final_risk == "CAUTION":
        status = "pending-audit"   # surfaced to Bill at next harvest
    else:
        status = "approved"        # SAFE across all models

    item = {
        "id": action_id,
        "created": now,
        "from": from_agent,
        "action": action_text,
        "context": context,
        "domain": domain,
        "status": status,
        "final_risk": final_risk,
        "triage": triage,
        "deep_review": {
            "risk": deep["risk"],
            "recommendation": deep["recommendation"],
            "summary": deep["full_text"][:1000],
        },
        "reason_review": {
            "risk": reason["risk"],
            "recommendation": reason["recommendation"],
            "summary": reason["full_text"][:1000],
        } if reason else None,
        "bill_audit": None,
    }

    log_event({
        "event": "review-complete",
        "action_id": action_id,
        "final_risk": final_risk,
        "status": status,
    })

    status_icon = {"blocked": "⛔", "pending-audit": "⚠️ ", "approved": "✓"}.get(status, "?")
    print(f"  {status_icon} Final: {final_risk} → {status}")
    return item


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_propose(args):
    context = args.context
    if args.review_file:
        file_path = pathlib.Path(args.review_file)
        if not file_path.exists():
            print(f"ERROR: --file path not found: {file_path}")
            sys.exit(1)
        try:
            file_content = file_path.read_text(encoding="utf-8", errors="replace")
            # Limit to 8000 chars to stay within model context windows
            if len(file_content) > 8000:
                file_content = file_content[:8000] + "\n... [truncated]"
            context = context + f"\n\nFILE: {file_path.name}\n---\n{file_content}\n---"
        except OSError as e:
            print(f"ERROR: Could not read --file: {e}")
            sys.exit(1)
    item = review(
        from_agent=args.from_agent,
        action_text=args.action,
        context=context,
        domain_hint=args.domain,
    )
    if item["status"] not in ("approved-routine",):
        add_to_queue(item)
        print(f"\n  Queued as {item['id']} (status: {item['status']})")
    else:
        print(f"\n  Routine action logged only (not queued)")


def cmd_status(args):
    queue = load_queue()
    actions = queue.get("actions", [])
    by_status = {}
    for a in actions:
        s = a.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    print(f"\nAction Queue — {len(actions)} total")
    for s, count in sorted(by_status.items()):
        print(f"  {s}: {count}")


def cmd_pending(args):
    queue = load_queue()
    pending = [a for a in queue.get("actions", []) if a.get("status") == "pending-audit"]
    if not pending:
        print("\nNo items pending Bill's audit.")
        return
    print(f"\n{len(pending)} item(s) pending audit:\n")
    for a in pending:
        created = a.get("created", "?")[:10]
        risk = a.get("final_risk", a.get("triage", {}).get("triage", "?"))
        print(f"  [{a['id']}] {created} | {risk} | {a['from']} → {a['action'][:60]}")


def main():
    parser = argparse.ArgumentParser(description="Athena review pipeline")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("propose", help="Submit a proposed action for review")
    p.add_argument("--from", dest="from_agent", default="allie", help="Proposing agent")
    p.add_argument("--action", required=True, help="Description of the proposed action")
    p.add_argument("--context", default="", help="Why this action is being proposed")
    p.add_argument("--domain", default=None,
                   choices=["routine", "data", "privacy", "security", "code", "infrastructure"],
                   help="Force a specific domain (overrides triage classification)")
    p.add_argument("--file", dest="review_file", default=None,
                   help="Path to a file for Athena to review (content appended to context)")

    sub.add_parser("status", help="Show queue summary")
    sub.add_parser("pending", help="List items awaiting Bill's audit")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    if not (ALLIE / "config").exists():
        print(f"ERROR: {ALLIE}/config not found. Is the Allie drive mounted?")
        sys.exit(1)

    {"propose": cmd_propose, "status": cmd_status, "pending": cmd_pending}[args.cmd](args)


if __name__ == "__main__":
    main()
