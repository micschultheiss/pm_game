#!/usr/bin/env python3
"""
linear_watch.py — the transition detector behind the "move a card, Claude builds
it" loop. Pure diff engine: it does NOT talk to git, Fly, or run any build. It
answers one question each tick — *what changed on the board since I last looked?*
— and leaves the doing to the `/linear-tick` slash command that drives it.

Two triggers, matching the agreed state machine
(Todo → build/test/commit/deploy-staging → QA → *human verifies on staging* →
move out of QA → push/deploy-prod/close):

  * **to_build**  — issues currently sitting in the Todo column.
  * **to_ship**   — issues that were in the QA column last tick and have since
                    been moved *out* of it (any destination counts — "move it
                    out of QA and you can push").

State between ticks lives in a tiny local snapshot (`.claude/linear_watch_state.json`,
git-ignored — it is machine-local and per-checkout). Each run rewrites it with
the states seen *this* tick, so the next tick diffs against reality.

Input: the current board, as a JSON array the caller supplies via `--current`:

    [{"identifier": "MIC-12", "title": "...", "state": "Todo",
      "url": "https://...", "branchName": "mic/mic-12-..."}, ...]

`state` is the workflow-state (column) *name*. Only `identifier` and `state` are
required; the rest are passed through untouched so the caller can act on them.
The `/linear-tick` command fills `--current` from the authenticated Linear MCP,
so no LINEAR_API_KEY is needed. As a convenience for standalone/CLI use, if
`--current` is omitted and LINEAR_API_KEY is set, this script fetches the board
itself over GraphQL (same stdlib-only approach as sync_todo_from_linear.py).

Stdlib only (json + urllib), matching the repo convention.

Usage:
  python3 scripts/linear_watch.py --current now.json
  python3 scripts/linear_watch.py --current now.json --dry-run   # don't persist
  LINEAR_API_KEY=lin_api_... python3 scripts/linear_watch.py      # self-fetch

Output (stdout): JSON {"first_run": bool, "to_build": [...], "to_ship": [...]}.
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STATE = os.path.join(REPO_ROOT, ".claude", "linear_watch_state.json")

PROJECT_NAME = "pm_game"
API_URL = "https://api.linear.app/graphql"


def load_snapshot(path):
    """Return {identifier: state_name} from the last tick, or {} if none."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError):
        return {}
    # Stored as {"issues": {identifier: state}}; tolerate a bare dict too.
    return data.get("issues", data) if isinstance(data, dict) else {}


def save_snapshot(path, current):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    snapshot = {"issues": {i["identifier"]: i["state"] for i in current}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=True)
        fh.write("\n")


def diff(current, prev, todo_col, qa_col):
    """Compute build/ship worklists from current board vs. previous snapshot."""
    to_build = [i for i in current if i.get("state") == todo_col]
    to_ship = [
        i
        for i in current
        if prev.get(i["identifier"]) == qa_col and i.get("state") != qa_col
    ]
    return to_build, to_ship


def fetch_board():
    """Standalone fallback: pull pm_game issues over GraphQL. Needs LINEAR_API_KEY."""
    import urllib.error
    import urllib.request

    key = os.environ.get("LINEAR_API_KEY")
    if not key:
        sys.exit(
            "No --current file given and LINEAR_API_KEY is unset. "
            "Pass --current <board.json> (the /linear-tick command does this via "
            "the Linear MCP) or export a key for standalone use."
        )
    query = """
    query($project: String!) {
      issues(filter: {project: {name: {eq: $project}}}, first: 250) {
        nodes { identifier title url branchName state { name } }
      }
    }
    """
    body = json.dumps({"query": query, "variables": {"project": PROJECT_NAME}}).encode()
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Authorization": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.URLError as exc:
        sys.exit(f"Linear API request failed: {exc}")
    if "errors" in payload:
        sys.exit(f"Linear API error: {payload['errors']}")
    nodes = payload["data"]["issues"]["nodes"]
    return [
        {
            "identifier": n["identifier"],
            "title": n["title"],
            "url": n["url"],
            "branchName": n.get("branchName"),
            "state": (n.get("state") or {}).get("name"),
        }
        for n in nodes
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect Linear board transitions.")
    ap.add_argument("--current", help="JSON file: current board (array of issues).")
    ap.add_argument("--state", default=DEFAULT_STATE, help="Snapshot file path.")
    ap.add_argument("--todo-column", default="Todo", help="Build-trigger column.")
    ap.add_argument("--qa-column", default="QA", help="Ship-gate column.")
    ap.add_argument("--dry-run", action="store_true", help="Do not write snapshot.")
    args = ap.parse_args(argv)

    if args.current:
        with open(args.current, "r", encoding="utf-8") as fh:
            current = json.load(fh)
    else:
        current = fetch_board()

    # Normalise: keep only issues with an identifier + state.
    current = [i for i in current if i.get("identifier") and i.get("state")]

    snapshot_exists = os.path.exists(args.state)
    prev = load_snapshot(args.state)
    to_build, to_ship = diff(current, prev, args.todo_column, args.qa_column)

    if not args.dry_run:
        save_snapshot(args.state, current)

    print(json.dumps({
        "first_run": not snapshot_exists,
        "to_build": to_build,
        "to_ship": to_ship,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
