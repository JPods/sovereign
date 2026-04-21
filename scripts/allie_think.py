#!/usr/bin/env python3
"""
allie_think.py — Allie's direct access to local Ollama models

For synthesis, comparison, and analysis. Not Athena's adversarial pipeline.
Allie uses this to think out loud, compare model responses, or consult a
specific model on a question without triggering a security review.

All queries and responses are logged to agent_log.jsonl.

Usage:
  python3 allie_think.py ask --model llama3.2 --prompt "..."
  python3 allie_think.py compare --prompt "..." [--models m1 m2 m3]
  python3 allie_think.py list
  python3 allie_think.py --home /path/to/sovereign ask ...

Examples:
  # Single model
  python3 allie_think.py ask --model athena --prompt "What are the privacy risks of storing ride timestamps?"

  # Compare all available models on the same question
  python3 allie_think.py compare --prompt "Should JPods store passenger IDs?"

  # Compare specific models
  python3 allie_think.py compare --prompt "..." --models llama3.2 deepseek-r1:8b gpt-oss:20b

  # Save output to file
  python3 allie_think.py compare --prompt "..." --out /Volumes/Allie/today/comparison.md
"""

import sys
import json
import datetime
import subprocess
import argparse
import pathlib
import os


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


def log_event(sovereign: pathlib.Path, entry: dict):
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    log_path = sovereign / "config" / "agent_log.jsonl"
    try:
        with log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"  [log error: {e}]", file=sys.stderr)


def list_models() -> list:
    """Return list of locally available Ollama model names."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10
        )
        models = []
        for line in result.stdout.splitlines()[1:]:  # skip header
            name = line.split()[0] if line.strip() else ""
            if name:
                models.append(name)
        return models
    except Exception as e:
        print(f"ERROR: could not list Ollama models: {e}")
        return []


def call_model(model: str, prompt: str, timeout: int = 120) -> tuple:
    """Call a model. Returns (response_text, elapsed_seconds, error)."""
    start = datetime.datetime.now()
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt, capture_output=True, text=True, timeout=timeout
        )
        elapsed = (datetime.datetime.now() - start).total_seconds()
        if result.returncode == 0:
            return result.stdout.strip(), elapsed, None
        else:
            return "", elapsed, result.stderr.strip()
    except subprocess.TimeoutExpired:
        elapsed = (datetime.datetime.now() - start).total_seconds()
        return "", elapsed, f"timed out after {timeout}s"
    except FileNotFoundError:
        return "", 0, "ollama not found"


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_list(args, sovereign):
    models = list_models()
    if not models:
        print("No models found. Is Ollama running?")
        return
    print(f"\n{len(models)} local model(s):\n")
    for m in models:
        print(f"  {m}")


def cmd_ask(args, sovereign):
    model = args.model
    prompt = args.prompt
    context = getattr(args, "context", "") or ""
    full_prompt = f"{context}\n\n{prompt}".strip() if context else prompt

    print(f"\n[Allie → {model}]")
    print(f"  {prompt[:80]}{'...' if len(prompt)>80 else ''}")
    print()

    response, elapsed, err = call_model(model, full_prompt, timeout=args.timeout)

    if err:
        print(f"ERROR: {err}")
        log_event(sovereign, {"event": "allie-think-error", "model": model,
                              "prompt": prompt[:200], "error": err})
        return

    print(response)
    print(f"\n  [{elapsed:.1f}s]")

    log_event(sovereign, {
        "event": "allie-think",
        "model": model,
        "prompt": prompt[:200],
        "response_chars": len(response),
        "elapsed_s": round(elapsed, 1),
    })

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"# Allie → {model}\n\n**Prompt:** {prompt}\n\n---\n\n{response}\n")
        print(f"\n  Saved: {out}")


def cmd_compare(args, sovereign):
    prompt = args.prompt
    context = getattr(args, "context", "") or ""
    full_prompt = f"{context}\n\n{prompt}".strip() if context else prompt

    # Resolve model list
    if args.models:
        models = args.models
    else:
        models = list_models()
        if not models:
            print("No models found. Is Ollama running?")
            return

    print(f"\n[Allie compare — {len(models)} model(s)]")
    print(f"  Prompt: {prompt[:80]}{'...' if len(prompt)>80 else ''}")
    print(f"  Models: {', '.join(models)}\n")

    date_str = datetime.date.today().isoformat()
    ts_str = datetime.datetime.now().strftime("%H%M%S")
    results = []

    for model in models:
        print(f"  [{model}]...", end=" ", flush=True)
        response, elapsed, err = call_model(model, full_prompt, timeout=args.timeout)
        if err:
            print(f"ERROR: {err}")
            results.append({"model": model, "error": err, "elapsed_s": round(elapsed, 1)})
        else:
            print(f"{elapsed:.1f}s / {len(response)} chars")
            results.append({"model": model, "response": response,
                            "elapsed_s": round(elapsed, 1), "chars": len(response)})

    log_event(sovereign, {
        "event": "allie-compare",
        "prompt": prompt[:200],
        "models": models,
        "results": [{"model": r["model"], "elapsed_s": r.get("elapsed_s"),
                     "chars": r.get("chars"), "error": r.get("error")} for r in results],
    })

    # Build output
    lines = [
        f"# Allie Model Comparison",
        f"*{date_str} {ts_str.replace(ts_str[4:],'') + ':' + ts_str[2:4] + ':' + ts_str[4:]}*",
        "",
        f"**Prompt:** {prompt}",
        "",
    ]
    for r in results:
        lines.append(f"---\n\n## {r['model']}  _{r.get('elapsed_s', '?')}s_\n")
        if "error" in r:
            lines.append(f"*ERROR: {r['error']}*\n")
        else:
            lines.append(r["response"] + "\n")

    output = "\n".join(lines)

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output)
        print(f"\n  Saved: {out}")
    else:
        # Default: save to today folder
        default_out = sovereign / "today" / f"{date_str}-compare-{ts_str}.md"
        default_out.parent.mkdir(parents=True, exist_ok=True)
        default_out.write_text(output)
        print(f"\n  Saved: {default_out}")

    # Also print to stdout
    print()
    print(output)


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Allie's direct Ollama access — ask, compare, explore"
    )
    parser.add_argument("--home", help="Sovereign home directory")
    sub = parser.add_subparsers(dest="cmd")

    # list
    sub.add_parser("list", help="List available local Ollama models")

    # ask
    p_ask = sub.add_parser("ask", help="Ask a single model")
    p_ask.add_argument("--model", required=True, help="Model name (e.g. llama3.2, athena)")
    p_ask.add_argument("--prompt", required=True, help="The question or prompt")
    p_ask.add_argument("--context", default="", help="Optional context prepended to prompt")
    p_ask.add_argument("--timeout", type=int, default=120, help="Seconds before timeout")
    p_ask.add_argument("--out", default=None, help="Save output to this file")

    # compare
    p_cmp = sub.add_parser("compare", help="Run the same prompt through multiple models")
    p_cmp.add_argument("--prompt", required=True, help="The question or prompt")
    p_cmp.add_argument("--context", default="", help="Optional context prepended to prompt")
    p_cmp.add_argument("--models", nargs="+", default=None,
                       help="Model names (default: all local models)")
    p_cmp.add_argument("--timeout", type=int, default=120, help="Seconds per model")
    p_cmp.add_argument("--out", default=None, help="Save comparison to this file")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    sovereign = get_sovereign_home(args.home)
    {"list": cmd_list, "ask": cmd_ask, "compare": cmd_compare}[args.cmd](args, sovereign)


if __name__ == "__main__":
    main()
