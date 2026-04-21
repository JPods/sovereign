#!/usr/bin/env python3
"""
athena_review.py — Athena's multi-model review pipeline

Routes proposed actions through three specialized LLMs:
  1. athena-triage  (llama3.2 — fast, <5s)
  2. athena         (gpt-oss:20b — deep security review)
  3. athena-reason  (deepseek-r1:8b — adversarial threat modeling)

Per-model findings are stored separately in the queue item.
External probes (OpenAI, Anthropic) triggered on BLOCK, disagreement, or explicit request.

Usage:
  python3 athena_review.py propose --action "..." --context "..." [--from allie] [--domain privacy] [--file path]
  python3 athena_review.py status
  python3 athena_review.py pending
  python3 athena_review.py --home /path/to/sovereign ...
"""

import sys
import json
import uuid
import datetime
import subprocess
import argparse
import pathlib
import os
import urllib.request


def get_sovereign_home(args_home=None) -> pathlib.Path:
    if args_home:
        return pathlib.Path(args_home)
    env = os.environ.get("SOVEREIGN_HOME")
    if env:
        return pathlib.Path(env)
    for c in [pathlib.Path("/Volumes/Allie"), pathlib.Path.home() / "sovereign"]:
        if (c / "config" / "profile.json").exists():
            return c
    print("ERROR: Cannot find Sovereign home. Set SOVEREIGN_HOME or use --home.")
    sys.exit(1)


RISK_LEVELS = ["SAFE", "CAUTION", "ESCALATE", "BLOCK"]
REASON_DOMAINS = {"privacy", "security", "code", "infrastructure"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_profile(sovereign: pathlib.Path) -> dict:
    path = sovereign / "config" / "profile.json"
    return json.loads(path.read_text()) if path.exists() else {}


def load_queue(sovereign: pathlib.Path) -> dict:
    path = sovereign / "config" / "action_queue.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"actions": []}


def save_queue(sovereign: pathlib.Path, queue: dict):
    (sovereign / "config" / "action_queue.json").write_text(json.dumps(queue, indent=2))


def log_event(sovereign: pathlib.Path, entry: dict):
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with (sovereign / "config" / "agent_log.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")


def is_standing_approved(sovereign: pathlib.Path, profile: dict, action: str, domain: str) -> bool:
    """Check if this action class has a standing approval."""
    for sa in profile.get("standing_approvals", []):
        if not sa.get("expires") or datetime.date.fromisoformat(sa["expires"]) >= datetime.date.today():
            if sa["class"] in action.lower() or sa["class"] in domain:
                return True
    return False


# ── Model calls ───────────────────────────────────────────────────────────────

def call_ollama(model: str, prompt: str, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() if result.returncode == 0 else f"ERROR: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"ERROR: {model} timed out after {timeout}s"
    except FileNotFoundError:
        return "ERROR: ollama not found"


def call_external(provider: dict, prompt: str) -> str:
    """Call an external LLM API (OpenAI or Anthropic format)."""
    api_key = os.environ.get(provider["api_key_env"], "")
    if not api_key:
        return f"ERROR: {provider['api_key_env']} not set"

    pid = provider["id"]
    try:
        if pid == "openai":
            payload = json.dumps({
                "model": provider["model"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
            }).encode()
            req = urllib.request.Request(
                provider["endpoint"],
                data=payload,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]

        elif pid == "anthropic":
            payload = json.dumps({
                "model": provider["model"],
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(
                provider["endpoint"],
                data=payload,
                headers={"x-api-key": api_key,
                         "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data["content"][0]["text"]
    except Exception as e:
        return f"ERROR: {e}"
    return "ERROR: unknown provider"


# ── Parse model outputs ───────────────────────────────────────────────────────

def parse_triage(text: str) -> dict:
    result = {"triage": "REVIEW", "domain": "routine", "flag": text,
              "raw": text, "model": "athena-triage"}
    for line in text.splitlines():
        if line.startswith("TRIAGE:"):
            result["triage"] = line.split(":", 1)[1].strip()
        elif line.startswith("DOMAIN:"):
            result["domain"] = line.split(":", 1)[1].strip()
        elif line.startswith("FLAG:"):
            result["flag"] = line.split(":", 1)[1].strip()
    return result


def parse_deep(text: str, model: str) -> dict:
    result = {"risk": "CAUTION", "recommendation": "escalate-to-bill",
              "conditions": "", "raw": text, "model": model,
              "probe_requested": False}
    for line in text.splitlines():
        if line.startswith("RISK:"):
            result["risk"] = line.split(":", 1)[1].strip()
        elif line.startswith("RECOMMENDATION:"):
            result["recommendation"] = line.split(":", 1)[1].strip()
        elif line.startswith("CONDITIONS:"):
            result["conditions"] = line.split(":", 1)[1].strip()
        elif line.startswith("PROBE:") and "YES" in line.upper():
            result["probe_requested"] = True
    return result


def worst_risk(risks: list) -> str:
    return max(risks, key=lambda r: RISK_LEVELS.index(r) if r in RISK_LEVELS else 0)


def models_disagree(r1: str, r2: str) -> bool:
    """True if models are 2+ levels apart."""
    if r1 not in RISK_LEVELS or r2 not in RISK_LEVELS:
        return False
    return abs(RISK_LEVELS.index(r1) - RISK_LEVELS.index(r2)) >= 2


# ── Main review pipeline ──────────────────────────────────────────────────────

def review(sovereign: pathlib.Path, profile: dict,
           from_agent: str, action_text: str, context: str,
           domain_hint: str = None, evidence_file: str = None) -> dict:

    action_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.now().isoformat(timespec="seconds")
    athena_cfg = profile.get("athena", {})
    models = athena_cfg.get("models", {
        "triage": "athena-triage", "deep": "athena", "reason": "athena-reason"
    })
    ext_cfg = athena_cfg.get("external_probes", {"enabled": False, "providers": []})
    auto_triggers = set(ext_cfg.get("auto_trigger", ["BLOCK", "model-disagreement"]))

    # Read evidence file if provided
    evidence = ""
    if evidence_file:
        try:
            evidence = f"\n\nEVIDENCE FILE ({evidence_file}):\n" + \
                       pathlib.Path(evidence_file).read_text()[:3000]
        except Exception as e:
            evidence = f"\n\nEVIDENCE FILE ERROR: {e}"

    print(f"\n[Athena] Review {action_id} | from: {from_agent}")
    print(f"  Action: {action_text[:72]}{'...' if len(action_text)>72 else ''}")

    # Standing approval check
    domain = domain_hint or "routine"
    if is_standing_approved(sovereign, profile, action_text, domain):
        item = _make_item(action_id, now, from_agent, action_text, context, domain,
                         "approved-standing", "SAFE", [], None, None, None)
        log_event(sovereign, {"event": "standing-approved", "action_id": action_id})
        print("  ✓ Standing approval — skipping Athena review")
        return item

    per_model_findings = []

    # ── Stage 1: Triage ───────────────────────────────────────────────────────
    print(f"  [1/3] {models['triage']}...", end=" ", flush=True)
    triage_prompt = (
        f"Proposed action from {from_agent}:\n\n"
        f"ACTION: {action_text}\n\nCONTEXT: {context}"
        + (f"\nDOMAIN HINT: {domain_hint}" if domain_hint else "")
        + evidence
    )
    triage_raw = call_ollama(models["triage"], triage_prompt, timeout=30)
    triage = parse_triage(triage_raw)
    domain = domain_hint or triage["domain"]
    triage["model"] = models["triage"]
    per_model_findings.append({"stage": "triage", **triage})
    print(f"→ {triage['triage']} / {domain}")

    log_event(sovereign, {"event": "triage", "action_id": action_id,
                          "triage": triage["triage"], "domain": domain, "flag": triage["flag"]})

    if triage["triage"] == "BLOCK":
        item = _make_item(action_id, now, from_agent, action_text, context, domain,
                         "blocked", "BLOCK", per_model_findings, None, None, None)
        log_event(sovereign, {"event": "blocked-at-triage", "action_id": action_id})
        print(f"  ⛔ BLOCKED at triage")
        return item

    if triage["triage"] == "PASS" and domain == "routine":
        item = _make_item(action_id, now, from_agent, action_text, context, domain,
                         "approved-routine", "SAFE", per_model_findings, None, None, None)
        log_event(sovereign, {"event": "approved-routine", "action_id": action_id})
        print(f"  ✓ Approved (routine)")
        return item

    # ── Stage 2: Deep review ──────────────────────────────────────────────────
    print(f"  [2/3] {models['deep']}...", end=" ", flush=True)
    deep_prompt = (
        f"Triage: {triage['triage']} / {domain} — {triage['flag']}\n\n"
        f"Proposed action from {from_agent}:\nACTION: {action_text}\nCONTEXT: {context}"
        + evidence
    )
    deep_raw = call_ollama(models["deep"], deep_prompt, timeout=120)
    deep = parse_deep(deep_raw, models["deep"])
    per_model_findings.append({"stage": "deep", **deep})
    print(f"→ {deep['risk']} / {deep['recommendation']}")

    log_event(sovereign, {"event": "deep-review", "action_id": action_id,
                          "risk": deep["risk"], "recommendation": deep["recommendation"]})

    # ── Stage 3: Reason ───────────────────────────────────────────────────────
    reason = None
    needs_reason = (domain in REASON_DOMAINS or triage["triage"] == "REASON"
                    or deep["risk"] in ("ESCALATE", "BLOCK"))
    if needs_reason:
        print(f"  [3/3] {models['reason']}...", end=" ", flush=True)
        reason_prompt = (
            f"Deep review: {deep['risk']} — {deep['recommendation']}\n\n"
            f"ACTION: {action_text}\nCONTEXT: {context}\nDOMAIN: {domain}\n\n"
            f"Prior finding summary: {deep_raw[:400]}" + evidence
        )
        reason_raw = call_ollama(models["reason"], reason_prompt, timeout=180)
        reason = parse_deep(reason_raw, models["reason"])
        per_model_findings.append({"stage": "reason", **reason})
        print(f"→ {reason['risk']} / {reason['recommendation']}")
        log_event(sovereign, {"event": "reason-review", "action_id": action_id,
                              "risk": reason["risk"], "recommendation": reason["recommendation"]})
    else:
        print(f"  [3/3] Threat modeling — skipped (domain: {domain})")

    # ── External probes ───────────────────────────────────────────────────────
    external_findings = []
    all_risks = [f["risk"] for f in per_model_findings if "risk" in f]
    final_risk_so_far = worst_risk(all_risks) if all_risks else "SAFE"

    should_probe = (
        ext_cfg.get("enabled") and (
            ("BLOCK" in auto_triggers and final_risk_so_far == "BLOCK") or
            ("model-disagreement" in auto_triggers and reason and
             models_disagree(deep["risk"], reason["risk"])) or
            ("probe-requested" in auto_triggers and
             any(f.get("probe_requested") for f in per_model_findings))
        )
    )

    if should_probe:
        for provider in ext_cfg.get("providers", []):
            if not provider.get("enabled"):
                continue
            print(f"  [probe] {provider['label']}...", end=" ", flush=True)
            probe_prompt = (
                f"Security review request. You are an adversarial reviewer.\n\n"
                f"ACTION: {action_text}\nCONTEXT: {context}\nDOMAIN: {domain}\n\n"
                f"Local model findings:\n"
                + "\n".join(f"- {f['stage']}: {f.get('risk','?')} / {f.get('recommendation','')}\n  "
                            f"{f.get('flag', f.get('conditions',''))}" for f in per_model_findings)
                + "\n\nPlease provide your independent assessment. Be adversarial. Find what the local models may have missed."
            )
            probe_result = call_external(provider, probe_prompt)
            probe_parsed = parse_deep(probe_result, provider["label"])
            probe_parsed["stage"] = f"external:{provider['id']}"
            per_model_findings.append(probe_parsed)
            external_findings.append(probe_parsed)
            print(f"→ {probe_parsed['risk']}")
            log_event(sovereign, {"event": "external-probe", "action_id": action_id,
                                  "provider": provider["id"], "risk": probe_parsed["risk"]})

    # ── Final verdict ─────────────────────────────────────────────────────────
    all_risks = [f["risk"] for f in per_model_findings if "risk" in f]
    final_risk = worst_risk(all_risks) if all_risks else "CAUTION"
    disagreement = (reason is not None and models_disagree(deep["risk"], reason["risk"]))

    if final_risk == "BLOCK":
        status = "blocked"
    elif final_risk in ("ESCALATE",) or disagreement:
        status = "pending-audit"
    elif final_risk == "CAUTION":
        status = "pending-audit"
    else:
        status = "approved"

    item = _make_item(action_id, now, from_agent, action_text, context, domain,
                     status, final_risk, per_model_findings,
                     disagreement, external_findings or None, None)

    log_event(sovereign, {"event": "review-complete", "action_id": action_id,
                          "final_risk": final_risk, "status": status,
                          "model_count": len(per_model_findings),
                          "disagreement": disagreement})

    icons = {"blocked": "⛔", "pending-audit": "⚠️ ", "approved": "✓"}
    print(f"  {icons.get(status,'?')} {final_risk} → {status}"
          + (" [MODELS DISAGREE]" if disagreement else ""))
    return item


def _make_item(action_id, now, from_agent, action_text, context, domain,
              status, final_risk, per_model_findings,
              disagreement, external_findings, bill_audit) -> dict:
    return {
        "id": action_id,
        "created": now,
        "from": from_agent,
        "action": action_text,
        "context": context,
        "domain": domain,
        "status": status,
        "final_risk": final_risk,
        "model_findings": per_model_findings,   # per-model, listed separately
        "models_disagree": bool(disagreement),
        "external_findings": external_findings,
        "bill_audit": bill_audit,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_propose(args, sovereign):
    profile = load_profile(sovereign)
    item = review(
        sovereign=sovereign,
        profile=profile,
        from_agent=args.from_agent,
        action_text=args.action,
        context=args.context,
        domain_hint=args.domain,
        evidence_file=args.file,
    )
    if item["status"] not in ("approved-routine", "approved-standing"):
        queue = load_queue(sovereign)
        queue["actions"].append(item)
        save_queue(sovereign, queue)
        print(f"  Queued: {item['id']} (status: {item['status']})")


def cmd_status(args, sovereign):
    queue = load_queue(sovereign)
    actions = queue.get("actions", [])
    by_status = {}
    for a in actions:
        s = a.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    print(f"\nAction Queue — {len(actions)} total")
    for s, count in sorted(by_status.items()):
        print(f"  {s}: {count}")


def cmd_pending(args, sovereign):
    queue = load_queue(sovereign)
    pending = [a for a in queue.get("actions", []) if a.get("status") == "pending-audit"]
    if not pending:
        print("\nNo items pending audit.")
        return
    print(f"\n{len(pending)} pending:\n")
    for a in pending:
        risk = a.get("final_risk", "?")
        disagree = " [DISAGREE]" if a.get("models_disagree") else ""
        print(f"  [{a['id']}] {a['created'][:10]} | {risk}{disagree} | {a['action'][:60]}")


def main():
    parser = argparse.ArgumentParser(description="Athena review pipeline")
    parser.add_argument("--home", help="Sovereign home directory")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("propose")
    p.add_argument("--from", dest="from_agent", default="allie")
    p.add_argument("--action", required=True)
    p.add_argument("--context", default="")
    p.add_argument("--domain", default=None,
                   choices=["routine", "data", "privacy", "security", "code", "infrastructure"])
    p.add_argument("--file", default=None, help="Path to evidence file Athena should read")

    sub.add_parser("status")
    sub.add_parser("pending")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    sovereign = get_sovereign_home(args.home)
    {"propose": cmd_propose, "status": cmd_status, "pending": cmd_pending}[args.cmd](args, sovereign)


if __name__ == "__main__":
    main()
