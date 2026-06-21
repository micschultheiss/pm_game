#!/usr/bin/env python3
"""
Regenerate docs/TODO.md from Linear. **Linear is the source of truth** — this is
a one-way pull (Linear → TODO.md). Edit issues in Linear, then run this to bring
the file back in sync. Do not hand-edit docs/TODO.md; your changes get
overwritten on the next sync.

Mapping:
  * Section  ← issue priority:  Urgent/High → "Now", Medium → "Next",
                                Low/None → "Later / ideas".
  * Checkbox ← issue state type: completed → [x], started → [~],
                                 else → [ ]; canceled issues are dropped.
  * Completed issues always land under "Done" regardless of priority.

Usage:
  LINEAR_API_KEY=lin_api_...  python3 scripts/sync_todo_from_linear.py
  LINEAR_API_KEY=lin_api_...  python3 scripts/sync_todo_from_linear.py --check

`--check` writes nothing and exits non-zero if TODO.md is out of date (for CI /
pre-commit). Create a personal API key at https://linear.app/settings/api .

Stdlib only (urllib + json) — no third-party deps, matching the repo convention.
"""

import json
import os
import sys
import urllib.error
import urllib.request

PROJECT_NAME = "pm_game"
API_URL = "https://api.linear.app/graphql"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODO_PATH = os.path.join(REPO_ROOT, "docs", "TODO.md")

# priority value (Linear: 0=None,1=Urgent,2=High,3=Medium,4=Low) → section key
SECTION_OF_PRIORITY = {1: "now", 2: "now", 3: "next", 0: "later", 4: "later"}
SECTIONS = [("now", "Now"), ("next", "Next"), ("later", "Later / ideas")]

QUERY = """
query($after: String) {
  issues(
    first: 250
    after: $after
    filter: { project: { name: { eq: "%s" } } }
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      identifier
      number
      title
      url
      priority
      state { type }
    }
  }
}
""" % PROJECT_NAME


def fetch_issues(api_key):
    """Pull every issue in the project, following pagination."""
    issues, after = [], None
    while True:
        body = json.dumps({"query": QUERY, "variables": {"after": after}}).encode()
        req = urllib.request.Request(
            API_URL,
            data=body,
            headers={"Authorization": api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            sys.exit(f"Linear API error {e.code}: {e.read().decode(errors='replace')}")
        if "errors" in payload:
            sys.exit(f"Linear GraphQL error: {json.dumps(payload['errors'])}")
        conn = payload["data"]["issues"]
        issues.extend(conn["nodes"])
        if not conn["pageInfo"]["hasNextPage"]:
            return issues
        after = conn["pageInfo"]["endCursor"]


def checkbox(state_type):
    return {"completed": "x", "started": "~"}.get(state_type, " ")


def render(issues):
    """Build the TODO.md text deterministically (stable order, no timestamp)."""
    buckets = {"now": [], "next": [], "later": [], "done": []}
    for it in issues:
        st = (it.get("state") or {}).get("type", "")
        if st == "canceled":
            continue  # canceled issues are dropped, not shown
        if st == "completed":
            buckets["done"].append(it)
        else:
            buckets[SECTION_OF_PRIORITY.get(it.get("priority") or 0, "later")].append(it)

    # started first, then by issue number — stable and reproducible
    def sort_key(it):
        started = 0 if (it.get("state") or {}).get("type") == "started" else 1
        return (started, it.get("number") or 0)

    def line(it):
        return f"- [{checkbox((it.get('state') or {}).get('type', ''))}] " \
               f"{it['title']} ([{it['identifier']}]({it['url']}))"

    out = [
        "# TODO",
        "",
        "> Generated from Linear — **do not edit by hand**. Linear is the source of truth.",
        f"> Project: {PROJECT_NAME} · team Mics-playground · "
        "regenerate with `python3 scripts/sync_todo_from_linear.py`.",
        "",
    ]
    for key, heading in SECTIONS:
        out.append(f"## {heading}")
        out.append("")
        rows = sorted(buckets[key], key=sort_key)
        out.extend(line(it) for it in rows) if rows else out.append("_(none)_")
        out.append("")
    out.append("## Done")
    out.append("")
    done = sorted(buckets["done"], key=lambda it: it.get("number") or 0)
    out.extend(line(it) for it in done) if done else out.append("_(none)_")
    out.append("")
    return "\n".join(out)


def main():
    check = "--check" in sys.argv[1:]
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        sys.exit("LINEAR_API_KEY not set. Create a personal key at "
                 "https://linear.app/settings/api and export it.")

    new_text = render(fetch_issues(api_key))
    old_text = ""
    if os.path.exists(TODO_PATH):
        with open(TODO_PATH, encoding="utf-8") as f:
            old_text = f.read()

    if check:
        if new_text != old_text:
            sys.exit("docs/TODO.md is out of sync with Linear — "
                     "run `python3 scripts/sync_todo_from_linear.py`.")
        print("docs/TODO.md is in sync with Linear.")
        return

    if new_text == old_text:
        print("docs/TODO.md already in sync — no change.")
        return
    with open(TODO_PATH, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"Wrote {TODO_PATH} ({new_text.count(chr(10) + '- ')} issues).")


if __name__ == "__main__":
    main()
