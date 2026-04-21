#!/usr/bin/env python3
"""
harvest.py — Sovereign daily synthesis
Reads the activity log + action queue + profile and produces a daily summary.

Usage:
  python3 harvest.py                      — today's log
  python3 harvest.py YYYY-MM-DD           — specific day
  python3 harvest.py --home /path/to/dir  — custom Sovereign home

Output: SOVEREIGN_HOME/today/YYYY-MM-DD-harvest.md
"""

import sys
import re
import json
import pathlib
import datetime
import argparse
from collections import defaultdict


def get_sovereign_home(args_home=None) -> pathlib.Path:
    if args_home:
        return pathlib.Path(args_home)
    # Try environment variable
    env = __import__("os").environ.get("SOVEREIGN_HOME")
    if env:
        return pathlib.Path(env)
    # Try well-known locations
    candidates = [
        pathlib.Path("/Volumes/Allie"),
        pathlib.Path.home() / "sovereign",
    ]
    for c in candidates:
        if (c / "config" / "profile.json").exists():
            return c
    print("ERROR: Cannot find Sovereign home. Set SOVEREIGN_HOME or use --home.")
    sys.exit(1)


def load_profile(sovereign: pathlib.Path) -> dict:
    path = sovereign / "config" / "profile.json"
    if not path.exists():
        return {"monitoring": {"projects": []}, "must_fix": [],
                "priorities": [], "assessment": {"checks": []},
                "audit": {"interval_hours": 24}}
    return json.loads(path.read_text())


def load_queue(sovereign: pathlib.Path) -> list:
    path = sovereign / "config" / "action_queue.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()).get("actions", [])
    except Exception:
        return []


def parse_log(log_path: pathlib.Path) -> dict:
    data = {
        "project_activity": defaultdict(list),
        "apps": [], "calendar": [], "warnings": [],
        "start_time": None, "stop_time": None, "total_events": 0,
    }
    if not log_path.exists():
        return data
    pattern = re.compile(r"\[(\d{2}:\d{2}:\d{2})\] \[([^\]]+)\] (.+)")
    for line in log_path.read_text().splitlines():
        m = pattern.match(line)
        if not m:
            continue
        ts, level, msg = m.groups()
        data["total_events"] += 1
        if level == "START":
            data["start_time"] = data["start_time"] or ts
        elif level == "STOP":
            data["stop_time"] = ts
        elif any(level.startswith(t) for t in ("CODE[", "MODEL[", "DATA[", "WRITE[", "FILE[")):
            proj = re.search(r"\[([^\]]+)\]", level)
            if proj:
                data["project_activity"][proj.group(1)].append((ts, level.split("[")[0], msg))
        elif level == "ALLIE":
            data["project_activity"]["allie"].append((ts, "WRITE", msg))
        elif level == "APP":
            data["apps"].append((ts, msg))
        elif level == "WARN":
            data["warnings"].append((ts, msg))
    return data


def parse_multi_day(sovereign: pathlib.Path, date_str: str, lookback: int) -> dict:
    activity = defaultdict(list)
    base = datetime.date.fromisoformat(date_str)
    for offset in range(lookback):
        day = base - datetime.timedelta(days=offset)
        log = sovereign / "today" / f"{day.isoformat()}-activity.log"
        day_data = parse_log(log)
        for proj, events in day_data["project_activity"].items():
            for ts, etype, msg in events:
                activity[proj].append((day.isoformat(), ts, etype, msg))
    return activity


def audit_check(actions: list, profile: dict, date_str: str) -> list:
    """Check for overdue audit items."""
    flags = []
    interval = profile.get("audit", {}).get("interval_hours", 24)
    now = datetime.datetime.now()
    pending = [a for a in actions if a.get("status") == "pending-audit"]
    overdue = []
    for a in pending:
        try:
            created = datetime.datetime.fromisoformat(a["created"])
            age_h = (now - created).total_seconds() / 3600
            if age_h > interval:
                overdue.append((a["id"], int(age_h), a.get("final_risk", "?"), a.get("action", "")[:60]))
        except Exception:
            pass
    if overdue:
        flags.append(f"⚠ **{len(overdue)} item(s) overdue for your review** (threshold: {interval}h):")
        for aid, age, risk, action in overdue:
            flags.append(f"  - [{aid}] {risk} | {age}h old | {action}")
        flags.append(f"  Run: `python3 {profile.get('audit',{}).get('ui_command','audit.py')}`")
    blocked = [a for a in actions if a.get("status") == "blocked"]
    if blocked:
        flags.append(f"⛔ **{len(blocked)} action(s) blocked by Athena** — review and re-propose:")
        for a in blocked[-3:]:
            flags.append(f"  - [{a['id']}] {a.get('action','')[:60]}")
    return flags


def noise_budget_check(sovereign: pathlib.Path, profile: dict, date_str: str) -> list:
    """Check Athena's escalation rate over the past 7 days."""
    flags = []
    max_per_week = profile.get("athena", {}).get("noise_budget", {}).get("max_escalations_per_week", 5)
    log_path = sovereign / "config" / "agent_log.jsonl"
    if not log_path.exists():
        return flags
    cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
    escalations = 0
    try:
        for line in log_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("event") in ("review-complete",) and \
               entry.get("status") == "pending-audit":
                ts = datetime.datetime.fromisoformat(entry.get("ts", "2000-01-01"))
                if ts > cutoff:
                    escalations += 1
    except Exception:
        pass
    if escalations > max_per_week:
        flags.append(
            f"⚠ **Athena noise alert**: {escalations} escalations in 7 days "
            f"(budget: {max_per_week}). Modelfiles may need recalibration."
        )
    return flags


def stagnation_check(profile: dict, multi_day: dict, date_str: str) -> list:
    flags = []
    lookback = profile["monitoring"].get("harvest_lookback_days", 7)
    for p in profile["monitoring"]["projects"]:
        if not p.get("enabled", True):
            continue
        pid = p["id"]
        threshold = p.get("stagnation_alert_days", 5)
        if pid not in multi_day:
            flags.append(f"- **{p['label']}** — no activity in {lookback}d lookback")
        else:
            most_recent = max(e[0] for e in multi_day[pid])
            days_ago = (datetime.date.fromisoformat(date_str) - datetime.date.fromisoformat(most_recent)).days
            if days_ago >= threshold:
                flags.append(f"- **{p['label']}** — last active {days_ago}d ago (threshold: {threshold}d)")
    return flags


def write_harvest(sovereign: pathlib.Path, date_str: str):
    profile = load_profile(sovereign)
    actions = load_queue(sovereign)
    labels = {p["id"]: p["label"] for p in profile["monitoring"]["projects"]}
    lookback = profile["monitoring"].get("harvest_lookback_days", 7)

    log_path = sovereign / "today" / f"{date_str}-activity.log"
    out_path = sovereign / "today" / f"{date_str}-harvest.md"

    data = parse_log(log_path)
    multi_day = parse_multi_day(sovereign, date_str, lookback)
    active = set(data["project_activity"].keys())
    checks = {c["id"]: c for c in profile["assessment"]["checks"] if c.get("enabled")}

    name = profile["profile"].get("name", "User")
    lines = [
        f"# Sovereign Harvest — {date_str}",
        f"*{name} · {profile['profile'].get('mode','unified')} mode*",
        "",
    ]

    # ── Needs your eyes today (top priority, always first) ────────────────────
    urgent = []
    urgent += audit_check(actions, profile, date_str)
    urgent += noise_budget_check(sovereign, profile, date_str)
    if urgent:
        lines += ["## ⚠ Needs Your Eyes Today", ""] + urgent + [""]

    # Session
    if data["start_time"] or data["stop_time"]:
        window = f"{data['start_time'] or '?'} → {data['stop_time'] or 'running'}"
        lines += [f"**Watcher:** {window} | **Events:** {data['total_events']}", ""]

    # App activity
    if data["apps"]:
        lines += ["## App Activity", ""]
        for ts, msg in data["apps"]:
            lines.append(f"- `{ts}` {msg}")
        lines.append("")

    # Project activity
    if data["project_activity"]:
        lines += ["## Project Activity", ""]
        for proj, events in sorted(data["project_activity"].items()):
            label = labels.get(proj, proj)
            lines.append(f"### {label}")
            by_type = defaultdict(list)
            for ts, etype, msg in events:
                by_type[etype].append(f"`{ts}` {msg}")
            for etype, items in sorted(by_type.items()):
                lines.append(f"**{etype}** ({len(items)})")
                for item in items[-5:]:
                    lines.append(f"  - {item}")
            lines.append(f"*{len(events)} events*")
            lines.append("")

    # Assessment
    assessment = []
    if "osl-resolution-rate" in checks:
        today_dt = datetime.date.fromisoformat(date_str)
        for item in profile.get("must_fix", []):
            if not item.get("resolved"):
                dl = item.get("deadline")
                overdue = ""
                if dl and datetime.date.fromisoformat(dl) < today_dt:
                    days = (today_dt - datetime.date.fromisoformat(dl)).days
                    overdue = f" ⚠ {days}d OVERDUE"
                assessment.append(f"- **{item['id']}** [{item['severity']}] ({item['project']}){overdue}: {item['description']}")
    if "stagnation" in checks:
        assessment += stagnation_check(profile, multi_day, date_str)
    if "priority-alignment" in checks:
        priorities = profile.get("priorities", [])
        for pri in sorted(priorities, key=lambda x: x["rank"])[:2]:
            if pri["id"] not in active and pri["status"] == "in-progress":
                assessment.append(f"- Priority #{pri['rank']} **{pri['id']}** (in-progress) had no activity today")
    if "cross-domain-debt" in checks and len(active) > 1:
        names = sorted(labels.get(p, p) for p in active)
        assessment.append(f"- Active in {len(active)} domains today: {', '.join(names)} — check cross-consequences")

    if assessment:
        lines += ["## Assessment", ""] + assessment + [""]

    # Warnings
    if data["warnings"]:
        lines += ["## Warnings", ""]
        for ts, msg in data["warnings"]:
            lines.append(f"- `{ts}` {msg}")
        lines.append("")

    if not data["project_activity"] and not data["apps"]:
        lines += ["*No activity recorded.*", ""]

    out_path.write_text("\n".join(lines))
    print(f"Harvest written: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Sovereign daily harvest")
    parser.add_argument("date", nargs="?", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--home", help="Sovereign home directory")
    args = parser.parse_args()

    sovereign = get_sovereign_home(args.home)
    date_str = args.date or datetime.date.today().isoformat()

    if not (sovereign / "today").exists():
        print(f"ERROR: {sovereign}/today not found.")
        sys.exit(1)

    write_harvest(sovereign, date_str)


if __name__ == "__main__":
    main()
