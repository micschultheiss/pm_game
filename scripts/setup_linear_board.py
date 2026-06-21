#!/usr/bin/env python3
"""
One-off (idempotent) setup of the Linear board columns for the pm_game project.

The Linear MCP integration is read-only for workflow states, so this script talks
to the Linear GraphQL API directly with your personal key to:

  1. Ensure the team's workflow states (= board columns) are, left to right:
        later (backlog) → next → now → In Progress → In Review → Done
     Renames the stock `Backlog` → `later` and `Todo` → `now`, creates `next`,
     and orders `next` before `now` (and `In Progress` before `In Review`).
  2. Move the project's issues into now/next/later by priority
     (Urgent/High → now, Medium → next, Low/None → later). Issues already in a
     started/completed/canceled state are left alone.

Safe to re-run: it looks states up by name and only changes what's missing.
Creates nothing destructive — no states or issues are deleted.

Usage:
  LINEAR_API_KEY=lin_api_...  python3 scripts/setup_linear_board.py

Stdlib only (urllib + json). Create a key at https://linear.app/settings/api .
"""

import json
import os
import sys
import urllib.error
import urllib.request

TEAM_NAME = "Mics-playground"
PROJECT_NAME = "pm_game"
API_URL = "https://api.linear.app/graphql"

# priority value → target column name
PRIORITY_COLUMN = {1: "now", 2: "now", 3: "next", 0: "later", 4: "later"}
# states we never auto-move issues out of
KEEP_TYPES = {"started", "completed", "canceled"}
NEW_NEXT_COLOR = "#e2a336"  # amber, only used if `next` must be created


def gql(api_key, query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
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
        sys.exit(f"Linear GraphQL error: {json.dumps(payload['errors'], indent=2)}")
    return payload["data"]


def get_team(api_key):
    data = gql(api_key, """
      query($name: String!) {
        teams(filter: { name: { eq: $name } }, first: 1) {
          nodes {
            id
            states(first: 100) { nodes { id name type position } }
          }
        }
      }
    """, {"name": TEAM_NAME})
    nodes = data["teams"]["nodes"]
    if not nodes:
        sys.exit(f"Team {TEAM_NAME!r} not found.")
    team = nodes[0]
    return team["id"], {s["name"].lower(): s for s in team["states"]["nodes"]}


def create_state(api_key, team_id, name, state_type, color, position):
    data = gql(api_key, """
      mutation($input: WorkflowStateCreateInput!) {
        workflowStateCreate(input: $input) { workflowState { id name type position } }
      }
    """, {"input": {"teamId": team_id, "name": name, "type": state_type,
                    "color": color, "position": position}})
    print(f"  created  {name!r} ({state_type})")
    return data["workflowStateCreate"]["workflowState"]


def update_state(api_key, state_id, **fields):
    gql(api_key, """
      mutation($id: String!, $input: WorkflowStateUpdateInput!) {
        workflowStateUpdate(id: $id, input: $input) { workflowState { id name } }
      }
    """, {"id": state_id, "input": fields})


def rename_state(api_key, state, new_name):
    update_state(api_key, state["id"], name=new_name)
    print(f"  renamed  {state['name']!r} -> {new_name!r}")
    state["name"] = new_name
    return state


def ensure_states(api_key, team_id, by_name):
    """Make sure later/next/now exist (renaming the stock states), return the
    name->state map for the columns we care about."""
    # later  <- existing "later", else rename "Backlog", else create
    if "later" in by_name:
        later = by_name["later"]
    elif "backlog" in by_name:
        later = rename_state(api_key, by_name["backlog"], "later")
    else:
        later = create_state(api_key, team_id, "later", "backlog", "#bec2c8", 0.0)

    # now  <- existing "now", else rename "Todo", else create
    if "now" in by_name:
        now = by_name["now"]
    elif "todo" in by_name:
        now = rename_state(api_key, by_name["todo"], "now")
    else:
        now = create_state(api_key, team_id, "now", "unstarted", "#5e6ad2", 1.0)

    # next  <- existing "next", else create (unstarted)
    next_ = by_name.get("next") or create_state(
        api_key, team_id, "next", "unstarted", NEW_NEXT_COLOR, 0.0)

    # order: next before now (unstarted group); In Progress before In Review
    update_state(api_key, next_["id"], position=0.0)
    update_state(api_key, now["id"], position=1.0)
    if "in progress" in by_name:
        update_state(api_key, by_name["in progress"]["id"], position=0.0)
    if "in review" in by_name:
        update_state(api_key, by_name["in review"]["id"], position=1.0)
    print("  ordered  later -> next -> now -> In Progress -> In Review -> Done")

    return {"later": later, "next": next_, "now": now}


def move_issues(api_key, columns):
    data = gql(api_key, """
      query($name: String!) {
        issues(filter: { project: { name: { eq: $name } } }, first: 250) {
          nodes { id identifier priority state { id name type } }
        }
      }
    """, {"name": PROJECT_NAME})
    moved = 0
    for it in data["issues"]["nodes"]:
        if (it["state"]["type"] or "") in KEEP_TYPES:
            continue  # leave In Progress / Done / Canceled where they are
        target = columns[PRIORITY_COLUMN.get(it["priority"] or 0, "later")]
        if it["state"]["id"] == target["id"]:
            continue
        gql(api_key, """
          mutation($id: String!, $stateId: String!) {
            issueUpdate(id: $id, input: { stateId: $stateId }) { success }
          }
        """, {"id": it["id"], "stateId": target["id"]})
        print(f"  moved    {it['identifier']} -> {target['name']}")
        moved += 1
    print(f"  {moved} issue(s) moved (priority -> column).")


def main():
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        sys.exit("LINEAR_API_KEY not set. Create a personal key at "
                 "https://linear.app/settings/api and export it.")
    team_id, by_name = get_team(api_key)
    print(f"Team {TEAM_NAME} ({team_id})")
    print("Ensuring columns:")
    columns = ensure_states(api_key, team_id, by_name)
    print("Moving issues:")
    move_issues(api_key, columns)
    print("Done. On the board view, enable Display -> 'Show empty groups' so all "
          "columns show even when empty.")


if __name__ == "__main__":
    main()
