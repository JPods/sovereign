#!/usr/bin/env python3
"""
allie_index_files.py
Allie's file indexer — creates document records in WebClerk for local files.

Scans a directory for matching file types and upserts a document record for each.
Uses checksum to avoid duplicates — re-running is safe (idempotent).

Usage:
  python3 allie_index_files.py <directory> [--ext .skp .json .rb] [--project 25] [--tag jpods]

Examples:
  # Index JPods SketchUp plugin
  python3 allie_index_files.py \
    "/Users/williamjames/Library/Application Support/SketchUp 2026/SketchUp/Plugins/JPods" \
    --ext .skp .json .rb \
    --project 25 \
    --tag jpods sketchup

  # Index JPods network json files only
  python3 allie_index_files.py ~/jpods-networks --ext .json --project 25 --tag jpods network

Requires: WC_TOKEN env var, or pass --token.
  export WC_TOKEN=$(python3 /Volumes/Allie/scripts/allie_wc_token.py)
"""

import sys
import os
import json
import hashlib
import datetime
import argparse
import pathlib
import urllib.request
import urllib.error

ALLIE = pathlib.Path("/Volumes/Allie")
LOG_PATH = ALLIE / "config" / "agent_log.jsonl"
WC_BASE = "http://localhost:8000"

MIME_TYPES = {
    ".skp":  "application/vnd.sketchup.skp",
    ".json": "application/json",
    ".rb":   "text/x-ruby",
    ".html": "text/html",
    ".md":   "text/markdown",
    ".txt":  "text/plain",
    ".py":   "text/x-python",
    ".sh":   "text/x-shellscript",
}

SKIP_DIRS = {".git", "venv", "venv312", "node_modules", "__pycache__", ".DS_Store"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def log_event(entry: dict):
    entry["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def wc_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{WC_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def wc_post(path: str, token: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{WC_BASE}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


# ── Checksum lookup ─────────────────────────────────────────────────────────────

def find_existing(checksum: str, token: str) -> int | None:
    """Return existing document id if checksum already indexed, else None."""
    try:
        resp = wc_get(f"/wcapi/get/?model_name=document&checksum={checksum}&limit=1", token)
        results = resp.get("data", {}).get("results", [])
        if results:
            return results[0]["id"]
    except Exception:
        pass
    return None


# ── Index one file ────────────────────────────────────────────────────────────────

def index_file(file_path: pathlib.Path, token: str, project_id: int,
               tags: list[str], base_dir: pathlib.Path) -> dict:
    """Create or update a WebClerk document record for one file."""
    suffix = file_path.suffix.lower()
    mime = MIME_TYPES.get(suffix, "application/octet-stream")
    size = file_path.stat().st_size
    checksum = sha256(file_path)
    rel_path = str(file_path.relative_to(base_dir))

    # Skip binary files too large to describe (>10MB)
    if size > 10_000_000 and suffix == ".skp":
        body = None
    elif suffix in (".json",):
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
            body = raw[:4000] if len(raw) > 4000 else raw
        except OSError:
            body = None
    else:
        body = None

    existing_id = find_existing(checksum, token)
    verb = "updated" if existing_id else "created"

    payload = {
        "model_name": "document",
        "name": file_path.name,
        "description": f"JPods SketchUp file — {rel_path}",
        "mime_type": mime,
        "size_bytes": size,
        "checksum": checksum,
        "status": "indexed",
        "body": body,
        "path": {
            "full": str(file_path),
            "relative": rel_path,
            "storage": "local",
        },
        "data": {
            "project_id": project_id,
            "indexed_by": "allie",
            "indexed_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "base_dir": str(base_dir),
        },
        "refs": {
            "tags": tags,
            "links": {"item": [], "contact": []},
            "parents": [{"model": "project", "id": project_id}],
            "keywords": tags,
            "categories": [suffix.lstrip(".")],
            "depends_on": {},
            "related_ids": [],
        },
    }

    if existing_id:
        payload["id"] = existing_id

    resp = wc_post("/wcapi/save/", token, payload)
    wc_id = resp.get("data", {}).get("id") or existing_id

    log_event({
        "event": "document-indexed",
        "file": str(file_path),
        "wc_id": wc_id,
        "checksum": checksum,
        "verb": verb,
        "mime": mime,
        "size_bytes": size,
    })

    return {"file": rel_path, "wc_id": wc_id, "verb": verb, "ok": "error" not in resp.get("status", "")}


# ── Scan directory ────────────────────────────────────────────────────────────────

def scan(directory: pathlib.Path, extensions: list[str]) -> list[pathlib.Path]:
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in filenames:
            if any(fname.lower().endswith(ext) for ext in extensions):
                files.append(pathlib.Path(root) / fname)
    return sorted(files)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Index local files as WebClerk documents")
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument("--ext", nargs="+", default=[".skp", ".json"],
                        help="File extensions to index (default: .skp .json)")
    parser.add_argument("--project", type=int, default=25,
                        help="WebClerk project ID to link documents to (default: 25)")
    parser.add_argument("--tag", nargs="*", dest="tags", default=[],
                        help="Tags to apply to all indexed documents")
    parser.add_argument("--token", default=os.environ.get("WC_TOKEN", ""),
                        help="WebClerk Bearer token (or set WC_TOKEN env var)")
    args = parser.parse_args()

    if not args.token:
        print("ERROR: WebClerk token required. Set WC_TOKEN env var or use --token.")
        sys.exit(1)

    base_dir = pathlib.Path(args.directory).expanduser().resolve()
    if not base_dir.exists():
        print(f"ERROR: Directory not found: {base_dir}")
        sys.exit(1)

    extensions = [e if e.startswith(".") else f".{e}" for e in args.ext]
    print(f"\nAllie file indexer")
    print(f"  Directory: {base_dir}")
    print(f"  Extensions: {extensions}")
    print(f"  Project: {args.project}")
    print(f"  Tags: {args.tags}")

    files = scan(base_dir, extensions)
    print(f"  Found: {len(files)} file(s)\n")

    created = updated = errors = 0
    for f in files:
        try:
            result = index_file(f, args.token, args.project, args.tags, base_dir)
            icon = "+" if result["verb"] == "created" else "~"
            print(f"  {icon} [{result.get('wc_id','?'):>5}] {result['file']}")
            if result["verb"] == "created":
                created += 1
            else:
                updated += 1
        except Exception as e:
            print(f"  ! ERROR {f.name}: {e}")
            errors += 1

    print(f"\n  Done — {created} created, {updated} updated, {errors} errors")
    log_event({
        "event": "index-run-complete",
        "directory": str(base_dir),
        "extensions": extensions,
        "project": args.project,
        "created": created,
        "updated": updated,
        "errors": errors,
    })


if __name__ == "__main__":
    main()
