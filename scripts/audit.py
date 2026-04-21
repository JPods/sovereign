#!/usr/bin/env python3
"""
audit.py — Sovereign consent gate
Browser UI + CLI for reviewing and approving agent actions.

Usage:
  python3 audit.py                   — browser at http://localhost:7373
  python3 audit.py --cli             — terminal interactive review
  python3 audit.py --home /path/dir  — custom Sovereign home

Rules:
- Nothing with status=pending-audit executes until approved here.
- Every decision is timestamped and logged to agent_log.jsonl.
- Overdue items escalate in harvest.md.
- Blocked items are read-only — investigate and re-propose.
"""

import sys
import json
import datetime
import pathlib
import webbrowser
import http.server
import threading
import urllib.parse
import os
from http import HTTPStatus

PORT = 7373


def get_sovereign_home(args_home=None) -> pathlib.Path:
    if args_home:
        return pathlib.Path(args_home)
    env = os.environ.get("SOVEREIGN_HOME")
    if env:
        return pathlib.Path(env)
    for c in [pathlib.Path("/Volumes/Allie"), pathlib.Path.home() / "sovereign"]:
        if (c / "config" / "profile.json").exists():
            return c
    print("ERROR: Cannot find Sovereign home.")
    sys.exit(1)


def load_queue(sovereign):
    path = sovereign / "config" / "action_queue.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"actions": []}


def save_queue(sovereign, queue):
    (sovereign / "config" / "action_queue.json").write_text(json.dumps(queue, indent=2))


def load_profile(sovereign):
    path = sovereign / "config" / "profile.json"
    return json.loads(path.read_text()) if path.exists() else {"audit": {"interval_hours": 24}}


def log_event(sovereign, entry):
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with (sovereign / "config" / "agent_log.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")


def apply_decision(sovereign, action_id, decision, note=""):
    queue = load_queue(sovereign)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for a in queue["actions"]:
        if a["id"] == action_id:
            if a["status"] == "blocked":
                return False
            a["status"] = {"approve": "approved", "reject": "rejected", "defer": "deferred"}.get(decision, decision)
            a["bill_audit"] = {"decision": decision, "ts": now, "note": note}
            save_queue(sovereign, queue)
            log_event(sovereign, {"event": f"bill-{decision}", "action_id": action_id, "note": note})
            return True
    return False


RISK_COLOR = {"SAFE": "#2d7a2d", "CAUTION": "#b07000", "ESCALATE": "#c04000", "BLOCK": "#8b0000"}
STAGE_COLOR = {"triage": "#555", "deep": "#336", "reason": "#363", "external:openai": "#663", "external:anthropic": "#633"}
STATUS_BADGE = {
    "pending-audit":    ("⚠️ Pending Review", "#b07000"),
    "approved":         ("✓ Approved", "#2d7a2d"),
    "approved-routine": ("✓ Routine", "#555"),
    "approved-standing":("✓ Standing", "#336"),
    "rejected":         ("✗ Rejected", "#8b0000"),
    "deferred":         ("⏸ Deferred", "#555"),
    "blocked":          ("⛔ Blocked", "#8b0000"),
}


def render_model_findings(findings):
    if not findings:
        return ""
    html = '<div class="model-findings"><strong>Per-Model Findings</strong>'
    for f in findings:
        stage = f.get("stage", "?")
        model = f.get("model", stage)
        risk = f.get("risk", f.get("triage", "?"))
        rec = f.get("recommendation", f.get("flag", ""))
        col = RISK_COLOR.get(risk, "#888")
        stage_col = STAGE_COLOR.get(stage, "#444")
        raw = f.get("raw", "")[:600]
        html += f"""
        <details class="model-finding">
          <summary>
            <span class="stage-badge" style="background:{stage_col}">{stage}</span>
            <span class="model-name">{model}</span>
            <span class="risk-inline" style="color:{col}">■ {risk}</span>
            <span class="rec-inline">{rec[:60]}</span>
          </summary>
          <pre>{raw}</pre>
        </details>"""
    html += "</div>"
    return html


def render_action(sovereign, a, profile, show_form=True):
    risk = a.get("final_risk", "?")
    risk_col = RISK_COLOR.get(risk, "#555")
    status = a.get("status", "?")
    badge_text, badge_col = STATUS_BADGE.get(status, (status, "#555"))
    created = a.get("created", "")[:16].replace("T", " ")
    interval = profile.get("audit", {}).get("interval_hours", 24)
    now = datetime.datetime.now()
    try:
        age_h = (now - datetime.datetime.fromisoformat(a["created"])).total_seconds() / 3600
    except Exception:
        age_h = 0
    overdue = age_h > interval and status == "pending-audit"
    disagree = a.get("models_disagree", False)
    audit = a.get("bill_audit") or {}

    html = f"""
    <div class="action {'overdue' if overdue else ''} {'disagree' if disagree else ''}">
      <div class="action-header">
        <span class="id">#{a['id']}</span>
        <span class="risk" style="color:{risk_col}">■ {risk}</span>
        {('<span class="disagree-badge">⚡ MODELS DISAGREE</span>') if disagree else ''}
        <span class="badge" style="background:{badge_col}">{badge_text}</span>
        <span class="meta">{a.get('from','?')} · {created} · {age_h:.0f}h ago
          {'· ⚠ OVERDUE' if overdue else ''}</span>
      </div>
      <div class="action-body">
        <div class="field"><strong>Action:</strong> {a.get('action','')}</div>
        <div class="field"><strong>Context:</strong> {a.get('context','') or '<em>none</em>'}</div>
        <div class="field"><strong>Domain:</strong> {a.get('domain','?')}</div>
        {render_model_findings(a.get('model_findings', []))}
    """
    if audit:
        html += f'<div class="field audit-record">Bill: <strong>{audit.get("decision","?")}'\
                f'</strong> at {audit.get("ts","?")[:16]}'\
                + (f' — {audit["note"]}' if audit.get("note") else '') + '</div>'

    if show_form and status == "pending-audit":
        html += f"""
        <form class="decision-form" method="POST" action="/decide">
          <input type="hidden" name="id" value="{a['id']}">
          <textarea name="note" placeholder="Optional note..." rows="2"></textarea>
          <div class="buttons">
            <button type="submit" name="decision" value="approve" class="btn-approve">✓ Approve</button>
            <button type="submit" name="decision" value="reject" class="btn-reject">✗ Reject</button>
            <button type="submit" name="decision" value="defer" class="btn-defer">⏸ Defer</button>
          </div>
        </form>"""
    elif status == "blocked":
        html += '<div class="blocked-notice">⛔ Blocked by Athena. Investigate and re-propose a corrected action.</div>'

    html += "</div></div>"
    return html


def render_page(sovereign, queue, profile, message=""):
    actions = queue.get("actions", [])
    pending = [a for a in actions if a.get("status") == "pending-audit"]
    done = [a for a in actions if a.get("status") not in ("pending-audit",)]
    interval = profile.get("audit", {}).get("interval_hours", 24)
    name = profile.get("profile", {}).get("name", "User")

    pending_html = "".join(render_action(sovereign, a, profile, True) for a in reversed(pending))
    done_html = "".join(render_action(sovereign, a, profile, False) for a in reversed(done[-20:]))
    msg_html = f'<div class="message">{message}</div>' if message else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Sovereign · Audit</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#111;color:#ddd;padding:24px}}
    h1{{color:#fff;font-size:1.4rem;margin-bottom:4px}}
    .subtitle{{color:#888;font-size:.85rem;margin-bottom:24px}}
    h2{{color:#aaa;font-size:1rem;margin:24px 0 12px;border-bottom:1px solid #333;padding-bottom:6px}}
    .message{{background:#1a3a1a;border-left:3px solid #4a4;padding:10px 14px;margin-bottom:16px;border-radius:4px;color:#8f8}}
    .action{{background:#1a1a1a;border:1px solid #333;border-radius:8px;margin-bottom:16px;overflow:hidden}}
    .action.overdue{{border-color:#8b3a00}}
    .action.disagree{{border-color:#665500}}
    .action-header{{display:flex;align-items:center;gap:10px;padding:10px 14px;background:#222;flex-wrap:wrap}}
    .id{{font-family:monospace;color:#888;font-size:.8rem}}
    .risk{{font-weight:700;font-size:.9rem}}
    .badge{{padding:2px 8px;border-radius:12px;font-size:.75rem;color:#fff}}
    .disagree-badge{{background:#665500;padding:2px 8px;border-radius:12px;font-size:.75rem;color:#ff9}}
    .meta{{color:#666;font-size:.78rem;margin-left:auto}}
    .action-body{{padding:14px}}
    .field{{margin-bottom:10px;font-size:.9rem;line-height:1.5}}
    .model-findings{{margin:10px 0;border:1px solid #2a2a2a;border-radius:6px;overflow:hidden}}
    .model-findings>strong{{display:block;padding:6px 10px;background:#1e1e1e;color:#888;font-size:.8rem}}
    .model-finding{{border-top:1px solid #2a2a2a}}
    .model-finding summary{{display:flex;align-items:center;gap:8px;padding:6px 10px;cursor:pointer;font-size:.82rem}}
    .model-finding summary:hover{{background:#222}}
    .stage-badge{{padding:1px 6px;border-radius:4px;font-size:.7rem;color:#fff}}
    .model-name{{color:#aaa}}
    .risk-inline{{font-weight:600;font-size:.82rem}}
    .rec-inline{{color:#666;font-size:.78rem}}
    pre{{background:#0d0d0d;padding:10px;font-size:.78rem;white-space:pre-wrap;word-break:break-word;color:#bbb;margin:0}}
    .audit-record{{background:#1a2a1a;padding:8px;border-radius:4px;color:#8f8;font-size:.85rem}}
    .blocked-notice{{background:#1a0d0d;padding:8px;border-radius:4px;color:#f88;font-size:.85rem}}
    .decision-form{{margin-top:14px;border-top:1px solid #333;padding-top:14px}}
    textarea{{width:100%;background:#0d0d0d;border:1px solid #333;color:#ccc;padding:8px;border-radius:4px;font-size:.85rem;resize:vertical}}
    .buttons{{display:flex;gap:10px;margin-top:10px}}
    button{{padding:8px 20px;border:none;border-radius:5px;font-size:.9rem;cursor:pointer;font-weight:600}}
    .btn-approve{{background:#2d7a2d;color:#fff}}.btn-approve:hover{{background:#3a9a3a}}
    .btn-reject{{background:#7a2d2d;color:#fff}}.btn-reject:hover{{background:#9a3a3a}}
    .btn-defer{{background:#444;color:#ccc}}.btn-defer:hover{{background:#555}}
    .empty{{color:#555;font-style:italic;padding:16px 0}}
    .stats{{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}}
    .stat{{background:#1a1a1a;border:1px solid #333;padding:10px 18px;border-radius:6px;text-align:center}}
    .stat-n{{font-size:1.6rem;font-weight:700;color:#fff}}
    .stat-l{{font-size:.75rem;color:#777}}
    details{{margin-bottom:0}}
  </style>
</head>
<body>
  <h1>Sovereign · Audit Console</h1>
  <div class="subtitle">{name} · Review cycle: {interval}h · All agent actions requiring approval appear here.</div>
  {msg_html}
  <div class="stats">
    <div class="stat"><div class="stat-n">{len(pending)}</div><div class="stat-l">Pending</div></div>
    <div class="stat"><div class="stat-n">{len([a for a in actions if a.get('status')=='approved'])}</div><div class="stat-l">Approved</div></div>
    <div class="stat"><div class="stat-n">{len([a for a in actions if a.get('status')=='rejected'])}</div><div class="stat-l">Rejected</div></div>
    <div class="stat"><div class="stat-n">{len([a for a in actions if a.get('status')=='blocked'])}</div><div class="stat-l">Blocked</div></div>
    <div class="stat"><div class="stat-n">{len([a for a in actions if a.get('models_disagree')])}</div><div class="stat-l">Disagreements</div></div>
  </div>
  <h2>Pending Your Review ({len(pending)})</h2>
  {pending_html or '<div class="empty">No items pending review.</div>'}
  <h2>Recent Decisions (last 20)</h2>
  {done_html or '<div class="empty">No decisions recorded yet.</div>'}
</body>
</html>"""


class AuditHandler(http.server.BaseHTTPRequestHandler):
    sovereign = None
    def log_message(self, format, *args): pass

    def send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        q = load_queue(self.sovereign)
        p = load_profile(self.sovereign)
        self.send_html(render_page(self.sovereign, q, p))

    def do_POST(self):
        if self.path != "/decide":
            self.send_response(HTTPStatus.NOT_FOUND); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        params = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode("utf-8")))
        action_id = params.get("id", "")
        decision = params.get("decision", "")
        note = params.get("note", "").strip()
        if action_id and decision in ("approve", "reject", "defer"):
            found = apply_decision(self.sovereign, action_id, decision, note)
            msg = f"Action {action_id} — {decision}d." if found else "Not found or blocked."
        else:
            msg = "Invalid decision."
        q = load_queue(self.sovereign)
        p = load_profile(self.sovereign)
        self.send_html(render_page(self.sovereign, q, p, message=msg))


def cli_review(sovereign):
    queue = load_queue(sovereign)
    pending = [a for a in queue.get("actions", []) if a.get("status") == "pending-audit"]
    if not pending:
        print("No items pending audit."); return
    for a in pending:
        risk = a.get("final_risk", "?")
        disagree = " [MODELS DISAGREE]" if a.get("models_disagree") else ""
        print(f"\n[{a['id']}] {risk}{disagree} | {a.get('from','?')} | {a.get('created','')[:16]}")
        print(f"  Action:  {a['action']}")
        for f in a.get("model_findings", []):
            print(f"  {f.get('stage','?')} ({f.get('model','?')}): {f.get('risk','?')} — {f.get('flag', f.get('recommendation',''))}")
        if a.get("status") == "blocked":
            input("  ⛔ BLOCKED. Press Enter."); continue
        while True:
            c = input("  [a=approve / r=reject / d=defer / s=skip]: ").strip().lower()
            if c in "ards": break
        if c == "s": continue
        decision = {"a": "approve", "r": "reject", "d": "defer"}[c]
        note = input("  Note: ").strip()
        apply_decision(sovereign, a["id"], decision, note)
        print(f"  → {decision}d.")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", help="Sovereign home directory")
    parser.add_argument("--cli", action="store_true")
    args = parser.parse_args()

    sovereign = get_sovereign_home(args.home)

    if args.cli:
        cli_review(sovereign); return

    AuditHandler.sovereign = sovereign
    server = http.server.HTTPServer(("127.0.0.1", PORT), AuditHandler)
    url = f"http://localhost:{PORT}"
    print(f"\nSovereign Audit Console\n  {url}\n  Ctrl+C to stop\n")
    threading.Thread(target=lambda: (__import__("time").sleep(0.5), webbrowser.open(url)), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAudit console stopped.")


if __name__ == "__main__":
    main()
