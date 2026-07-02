#!/usr/bin/env python3
"""
linear_api.py — a tiny Linear GraphQL client for the hosted autobuild loop.

Unlike the in-session Linear MCP (which is interactively authenticated and absent
from headless/cloud runs), this talks to Linear over the raw GraphQL API using
`LINEAR_API_KEY` — so it works inside a GitHub Actions runner. Stdlib only
(urllib + json), matching the repo convention.

It is the *write* half the board watcher needs: read the board, move a card
between columns, post a comment, and attach a link. `scripts/autobuild.py` uses
these as a library; the CLI below makes each usable standalone / testable.

CLI:
  LINEAR_API_KEY=lin_api_... python3 scripts/linear_api.py board
  ...                        python3 scripts/linear_api.py state MIC-12 "In Review"
  ...                        python3 scripts/linear_api.py comment MIC-12 "text..."
  ...                        python3 scripts/linear_api.py link MIC-12 https://... "Title"

`board` prints the pm_game issues as a JSON array (the same shape
`scripts/linear_watch.py` consumes). Everything is keyed by human identifier
(e.g. MIC-12); IDs are resolved internally.
"""

import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.linear.app/graphql"
PROJECT_NAME = "pm_game"
TEAM_NAME = "Mics-playground"


class LinearError(RuntimeError):
    pass


def _key():
    key = os.environ.get("LINEAR_API_KEY")
    if not key:
        raise LinearError("LINEAR_API_KEY is not set.")
    return key


def _gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Authorization": _key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise LinearError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}")
    except urllib.error.URLError as exc:
        raise LinearError(f"request failed: {exc}")
    if payload.get("errors"):
        raise LinearError(json.dumps(payload["errors"]))
    return payload["data"]


# --- reads ----------------------------------------------------------------

def board():
    """Return pm_game issues as [{identifier,title,url,branchName,description,state}]."""
    query = """
    query($project: String!) {
      issues(filter: {project: {name: {eq: $project}}}, first: 250) {
        nodes { id identifier title url branchName description state { id name } }
      }
    }
    """
    nodes = _gql(query, {"project": PROJECT_NAME})["issues"]["nodes"]
    return [
        {
            "id": n["id"],
            "identifier": n["identifier"],
            "title": n["title"],
            "url": n["url"],
            "branchName": n.get("branchName"),
            "description": n.get("description") or "",
            "state": (n.get("state") or {}).get("name"),
        }
        for n in nodes
    ]


def comments(identifier):
    """Return an issue's comments as [{body, createdAt}], oldest-first-ish.

    Authorship isn't returned: the loop posts via the same LINEAR_API_KEY as the
    human, so bot vs. human is told apart by body markers, not by author.
    """
    query = """
    query($id: String!) {
      issue(id: $id) { comments(first: 100) { nodes { body createdAt } } }
    }
    """
    issue = _gql(query, {"id": identifier}).get("issue")
    if not issue:
        raise LinearError(f"issue {identifier} not found")
    return issue["comments"]["nodes"]


def _issue_id(identifier):
    """Resolve a human identifier (MIC-12) to its UUID."""
    query = "query($id: String!) { issue(id: $id) { id } }"
    issue = _gql(query, {"id": identifier}).get("issue")
    if not issue:
        raise LinearError(f"issue {identifier} not found")
    return issue["id"]


def _state_id(name):
    """Resolve a workflow-state (column) name to its UUID within the team."""
    query = """
    query($team: String!) {
      workflowStates(filter: {team: {name: {eq: $team}}}, first: 100) {
        nodes { id name }
      }
    }
    """
    nodes = _gql(query, {"team": TEAM_NAME})["workflowStates"]["nodes"]
    for n in nodes:
        if n["name"].lower() == name.lower():
            return n["id"]
    have = ", ".join(sorted(n["name"] for n in nodes))
    raise LinearError(f"no workflow state named {name!r}. Have: {have}")


# --- writes ---------------------------------------------------------------

def set_state(identifier, state_name):
    """Move an issue to the named column. Returns True on success."""
    query = """
    mutation($id: String!, $stateId: String!) {
      issueUpdate(id: $id, input: {stateId: $stateId}) { success }
    }
    """
    data = _gql(query, {"id": _issue_id(identifier), "stateId": _state_id(state_name)})
    return bool(data["issueUpdate"]["success"])


def comment(identifier, body):
    """Post a comment on an issue. Returns True on success."""
    query = """
    mutation($id: String!, $body: String!) {
      commentCreate(input: {issueId: $id, body: $body}) { success }
    }
    """
    data = _gql(query, {"id": _issue_id(identifier), "body": body})
    return bool(data["commentCreate"]["success"])


def link(identifier, url, title):
    """Attach a URL link to an issue (shows in the issue's Links). Returns True."""
    query = """
    mutation($id: String!, $url: String!, $title: String!) {
      attachmentCreate(input: {issueId: $id, url: $url, title: $title}) { success }
    }
    """
    data = _gql(query, {"id": _issue_id(identifier), "url": url, "title": title})
    return bool(data["attachmentCreate"]["success"])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.exit("usage: linear_api.py {board|comments|state|comment|link} ...")
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "board":
            print(json.dumps(board(), indent=2))
        elif cmd == "comments":
            (identifier,) = rest
            print(json.dumps(comments(identifier), indent=2))
        elif cmd == "state":
            identifier, state_name = rest
            print("ok" if set_state(identifier, state_name) else "failed")
        elif cmd == "comment":
            identifier, body = rest
            print("ok" if comment(identifier, body) else "failed")
        elif cmd == "link":
            identifier, url, title = rest
            print("ok" if link(identifier, url, title) else "failed")
        else:
            sys.exit(f"unknown command: {cmd}")
    except LinearError as exc:
        sys.exit(f"Linear API error: {exc}")
    except ValueError:
        sys.exit(f"wrong arguments for {cmd!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
