#!/usr/bin/env python3
"""
profile_wizard.py
Interactive plain-language setup. Generates profile.json from answers.
No JSON knowledge required.

Usage (called by install.sh):
  python3 profile_wizard.py --home /path/to/sovereign

Usage (standalone re-run):
  python3 profile_wizard.py --home /path/to/sovereign --update
"""

import json
import pathlib
import argparse
import sys
import datetime
import os


def ask(prompt, default=None, required=True):
    """Ask a question, return answer. Blank = default if provided."""
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"  {prompt}{suffix}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default
        if not required:
            return ""
        print("  (required — please answer)")


def ask_yes(prompt, default=True):
    default_str = "Y/n" if default else "y/N"
    answer = input(f"  {prompt} [{default_str}]: ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")


def ask_path(prompt, default=None):
    """Ask for a directory path. Expand ~ and validate."""
    raw = ask(prompt, default=default, required=False)
    if not raw:
        return ""
    expanded = str(pathlib.Path(raw).expanduser())
    return expanded


def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


def build_profile(home: pathlib.Path) -> dict:
    print("\n" + "═"*50)
    print("  Sovereign — Profile Setup")
    print("  Answer in plain English. No JSON needed.")
    print("═"*50)

    # ── Identity ──────────────────────────────────────────────────────────────
    section("Who are you?")
    name = ask("Your name", default=os.environ.get("USER", "User"))
    mode = "unified"
    is_unified = ask_yes(
        "Do you blend work and personal in one context? (unified mode)\n"
        "  Say no if you want strict work/personal separation (divided mode)",
        default=True
    )
    mode = "unified" if is_unified else "divided"

    # ── Projects ──────────────────────────────────────────────────────────────
    section("What projects should Sovereign watch?")
    print("  Enter each project as: nickname | /path/to/folder | stagnation alert days")
    print("  Example: webclerk | ~/Documents/webclerk | 3")
    print("  Press Enter with no input when done.")
    print()

    projects = []
    idx = 1
    while True:
        raw = input(f"  Project {idx} (or Enter to finish): ").strip()
        if not raw:
            if idx == 1:
                print("  (add at least one project)")
                continue
            break
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 2:
            print("  Format: nickname | /path | days   (days optional, default 5)")
            continue
        pid = parts[0].lower().replace(" ", "-")
        path = str(pathlib.Path(parts[1]).expanduser())
        days = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 5
        projects.append({
            "id": pid,
            "label": parts[0].title(),
            "path": path,
            "enabled": True,
            "stagnation_alert_days": days
        })
        print(f"  ✓ Added: {pid} → {path} (alert after {days}d inactive)")
        idx += 1

    # ── Priorities ────────────────────────────────────────────────────────────
    section("What are your top priorities right now?")
    print("  Rank them in order. Sovereign will flag when you drift from this.")
    print("  Format: project-nickname | goal description | deadline (optional YYYY-MM-DD)")
    print("  Press Enter with no input when done (max 5 recommended).")
    print()

    priorities = []
    rank = 1
    known_ids = {p["id"] for p in projects}
    while rank <= 5:
        raw = input(f"  Priority #{rank} (or Enter to finish): ").strip()
        if not raw:
            if rank == 1:
                print("  (add at least one priority)")
                continue
            break
        parts = [p.strip() for p in raw.split("|")]
        pid = parts[0].lower().replace(" ", "-")
        goal = parts[1] if len(parts) > 1 else parts[0]
        deadline = parts[2] if len(parts) > 2 else None
        priorities.append({
            "rank": rank,
            "project": pid,
            "goal": goal,
            "deadline": deadline,
            "status": "in-progress"
        })
        print(f"  ✓ Rank {rank}: {pid} — {goal}")
        rank += 1

    # ── Audit schedule ────────────────────────────────────────────────────────
    section("How often will you review agent actions?")
    print("  Athena queues actions for your approval. You should review regularly.")
    hours = ask(
        "Review at least every N hours (24 = daily, 168 = weekly)",
        default="24"
    )
    try:
        audit_hours = int(hours)
    except ValueError:
        audit_hours = 24

    # ── Standing approvals ────────────────────────────────────────────────────
    section("Standing approvals (skip Athena review for routine actions)")
    standing = []
    if ask_yes(
        "Pre-approve routine log writes and harvest generation?\n"
        "  (Recommended — these are low-risk and constant)",
        default=True
    ):
        sovereign_str = str(home)
        standing += [
            {"class": "harvest-write", "scope": str(home / "today"),
             "granted": datetime.date.today().isoformat(), "expires": None},
            {"class": "log-append", "scope": str(home / "config" / "agent_log.jsonl"),
             "granted": datetime.date.today().isoformat(), "expires": None},
        ]
        print("  ✓ Standing approvals set for harvest and log")

    # ── Athena model selection ─────────────────────────────────────────────────
    section("Athena models")
    print("  Athena uses three specialized local LLMs for security review.")
    print("  These must be available in Ollama. Defaults work if you used install.sh.")
    triage_model = ask("Fast triage model", default="athena-triage")
    deep_model = ask("Deep review model", default="athena")
    reason_model = ask("Threat modeling model", default="athena-reason")

    # ── Build profile ─────────────────────────────────────────────────────────
    profile = {
        "profile": {
            "name": name,
            "mode": mode,
            "note": "unified = work and personal in one context. divided = strict separation.",
            "created": datetime.date.today().isoformat()
        },
        "monitoring": {
            "projects": projects,
            "apps": [
                {"process": "Code",          "label": "VS Code",   "enabled": True},
                {"process": "zoom.us",       "label": "Zoom",      "enabled": True},
                {"process": "Google Chrome", "label": "Chrome",    "enabled": True},
            ],
            "harvest_lookback_days": 7
        },
        "priorities": priorities,
        "must_fix": [],
        "standing_approvals": standing,
        "audit": {
            "interval_hours": audit_hours,
            "note": "Sovereign will escalate in harvest.md if you skip beyond this interval.",
            "ui_command": f"python3 {home}/scripts/audit.py",
            "cli_command": f"python3 {home}/scripts/audit.py --cli"
        },
        "athena": {
            "models": {
                "triage": triage_model,
                "deep":   deep_model,
                "reason": reason_model
            },
            "review_script": f"python3 {home}/scripts/athena_review.py propose",
            "noise_budget": {
                "max_escalations_per_week": 5,
                "note": "If Athena exceeds this, harvest.md flags a calibration problem."
            },
            "external_probes": {
                "enabled": False,
                "auto_trigger": ["BLOCK", "model-disagreement", "probe-requested"],
                "providers": [
                    {"id": "openai", "label": "OpenAI GPT-4o",
                     "endpoint": "https://api.openai.com/v1/chat/completions",
                     "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY", "enabled": False},
                    {"id": "anthropic", "label": "Anthropic Claude",
                     "endpoint": "https://api.anthropic.com/v1/messages",
                     "model": "claude-opus-4-5", "api_key_env": "ANTHROPIC_API_KEY", "enabled": False}
                ]
            }
        },
        "assessment": {
            "checks": [
                {"id": "osl-resolution-rate", "enabled": True,
                 "description": "Flag unresolved must_fix items past deadline"},
                {"id": "stagnation", "enabled": True,
                 "description": "Alert when a project exceeds its stagnation_alert_days"},
                {"id": "priority-alignment", "enabled": True,
                 "description": "Flag when activity doesn't match stated priorities"},
                {"id": "cross-domain-debt", "enabled": True,
                 "description": "Prompt cross-project consequence check when multiple domains active"},
                {"id": "audit-overdue", "enabled": True,
                 "description": "Escalate when pending-audit items exceed interval_hours"}
            ]
        }
    }
    return profile


def main():
    parser = argparse.ArgumentParser(description="Sovereign profile wizard")
    parser.add_argument("--home", required=True, help="Sovereign home directory")
    parser.add_argument("--update", action="store_true",
                        help="Re-run wizard and overwrite existing profile")
    args = parser.parse_args()

    home = pathlib.Path(args.home)
    profile_path = home / "config" / "profile.json"

    if profile_path.exists() and not args.update:
        print(f"Profile exists at {profile_path}. Use --update to overwrite.")
        sys.exit(0)

    profile = build_profile(home)

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, indent=2))
    print(f"\n  ✓ Profile written to {profile_path}")
    print(f"  Edit anytime: open {profile_path}")


if __name__ == "__main__":
    main()
