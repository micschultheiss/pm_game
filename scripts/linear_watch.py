#!/usr/bin/env python3
"""
linear_watch.py — the trigger detector behind the "move a card, Claude builds
it" loop. Pure classifier: it does NOT talk to git, Fly, or run any build. It
answers one question each tick — *which cards are sitting on a trigger column
right now?* — and leaves the doing to the `/linear-tick` slash command.

Two triggers, matching the agreed state machine
(Todo → build/test/commit/deploy-staging → In Review → *human verifies on
staging* → move to Deploy → push/deploy-prod → Done):

  * **to_build** — issues in the **Todo** column.
  * **to_ship**  — issues in the **Deploy** column (the human moved them there to
                   approve the staging build → ship to prod).

Both triggers are terminal moves: the build phase moves a card *out of* Todo (to
In Progress → In Review) and the ship phase moves it *out of* Deploy (to Done),
so a card is never re-triggered on a later tick. That makes this classifier
**stateless** — no local snapshot to keep in sync.

Input: the current board, as a JSON array the caller supplies via `--current`:

    [{"identifier": "MIC-12", "title": "...", "state": "Todo",
      "url": "https://...", "branchName": "mic/mic-12-..."}, ...]

`state` is the workflow-state (column) *name*. Only `identifier` and `state` are
required; the rest pass through untouched so the caller can act on them. The
`/linear-tick` command fills `--current` from the authenticated Linear MCP, so no
LINEAR_API_KEY is needed. As a convenience for standalone/CLI use, if `--current`
is omitted and LINEAR_API_KEY is set, this script fetches the board itself over
GraphQL (same stdlib-only approach as sync_todo_from_linear.py).

Stdlib only (json + urllib), matching the repo convention.

Usage:
  python3 scripts/linear_watch.py --current now.json
  LINEAR_API_KEY=lin_api_... python3 scripts/linear_watch.py      # self-fetch

Output (stdout): JSON {"to_build": [...], "to_ship": [...]}.
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROJECT_NAME = "pm_game"
API_URL = "https://api.linear.app/graphql"


def classify(current, build_col, ship_col):
    """Split the board into build/ship worklists by current column."""
    to_build = [i for i in current if i.get("state") == build_col]
    to_ship = [i for i in current if i.get("state") == ship_col]
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
    ap = argparse.ArgumentParser(description="Classify Linear board trigger columns.")
    ap.add_argument("--current", help="JSON file: current board (array of issues).")
    ap.add_argument("--build-column", default="Todo", help="Build-trigger column.")
    ap.add_argument("--ship-column", default="Deploy", help="Ship-trigger column.")
    args = ap.parse_args(argv)

    if args.current:
        with open(args.current, "r", encoding="utf-8") as fh:
            current = json.load(fh)
    else:
        current = fetch_board()

    # Normalise: keep only issues with an identifier + state.
    current = [i for i in current if i.get("identifier") and i.get("state")]

    to_build, to_ship = classify(current, args.build_column, args.ship_column)
    print(json.dumps({"to_build": to_build, "to_ship": to_ship}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
