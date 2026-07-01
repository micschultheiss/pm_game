#!/usr/bin/env python3
"""
autobuild.py — one tick of the hosted Linear board watcher, for GitHub Actions.

This is the cloud replacement for the in-session `/loop`. A scheduled workflow
(`.github/workflows/linear-autobuild.yml`) runs `python3 scripts/autobuild.py
tick` every few minutes. Each tick:

  * ships every card sitting in **Deploy** → prod (the human approved it), then
  * builds the first card in **Todo** → branch → tests → staging → **In Review**.

State machine (agreed with the user):

    Todo ─build/test/commit/deploy-staging─▶ In Review ─(human verifies on
    staging)─▶ Deploy ─merge main/deploy-prod─▶ Done

The build phase never touches `main` — it works on a per-ticket branch and
deploys only to staging. Prod ships only for cards the human moved to Deploy.

Determinism lives here (git, flyctl, Linear moves/comments via
`scripts/linear_api.py`); the one non-deterministic step — writing the code for a
ticket — is delegated to headless Claude (`claude -p`). Claude only edits the
working tree; this driver owns tests, commits, deploys, and the Linear updates.

Stdlib only. Meant to run in CI where LINEAR_API_KEY, ANTHROPIC_API_KEY, and
FLY_API_TOKEN are present as env/secrets.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # for `import linear_api`
import linear_api  # noqa: E402  (sibling module in scripts/)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BUILD_COLUMN = "Todo"
GATE_COLUMN = "In Review"
SHIP_COLUMN = "Deploy"
DONE_COLUMN = "Done"

REPO_SLUG = "micschultheiss/pm_game"
COMMIT_URL = f"https://github.com/{REPO_SLUG}/commit/"
STAGING_URL = "https://hallucination-inc-staging.fly.dev/"
PROD_URL = "https://hallucination-inc.fly.dev/"

FLY_STAGING = ["flyctl", "deploy", "--remote-only", "--config", "fly/fly.staging.toml",
               "--dockerfile", "fly/Dockerfile", "--ignorefile", "fly/.dockerignore", "."]
FLY_PROD = ["flyctl", "deploy", "--remote-only", "--config", "fly/fly.toml",
            "--dockerfile", "fly/Dockerfile", "--ignorefile", "fly/.dockerignore", "."]

COAUTHOR_TRAILER = "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"


# --- shell helpers --------------------------------------------------------

def sh(cmd, check=True, capture=False, **kw):
    """Run a command in the repo. Returns CompletedProcess (text)."""
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}", flush=True)
    res = subprocess.run(
        cmd, cwd=REPO, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        **kw,
    )
    if check and res.returncode != 0:
        out = res.stdout or ""
        raise RuntimeError(f"command failed ({res.returncode}): {cmd}\n{out}")
    return res


def git(*args, **kw):
    return sh(["git", *args], **kw)


# --- naming ---------------------------------------------------------------

def branch_for(issue):
    """Prefer Linear's suggested branch name; else derive a safe one."""
    name = (issue.get("branchName") or "").strip()
    if name:
        return name
    slug = re.sub(r"[^a-z0-9]+", "-", issue["title"].lower()).strip("-")[:40]
    return f"auto/{issue['identifier'].lower()}-{slug}"


def commit_subject(issue):
    title = issue["title"].strip()
    if re.match(r"^(feat|fix|chore|docs|refactor|test|build|ci|perf)(\(|:)", title):
        return title
    return f"feat: {title}"


# --- the Claude build step ------------------------------------------------

def build_prompt(issue):
    return f"""You are implementing a single ticket in the Hallucination Inc.
codebase (a Python terminal + web game; see CLAUDE.md for conventions).

Linear ticket {issue['identifier']}: {issue['title']}

Description:
{issue['description'] or '(no description — infer scope from the title and CLAUDE.md)'}

Rules:
- Follow CLAUDE.md. Engine logic goes in src/engine.py FIRST (stdlib only), then
  each frontend (src/terminal.py, src/web.py) wires up its own UI. Never
  reimplement rules in a frontend. Respect the load-bearing mechanics.
- Keep the meme-y PM/AI-satire tone in any user-facing copy.
- The test suite MUST pass: `python3 tests/run_tests.py` (tests + 90% coverage
  gate). Add or update tests for new behaviour. Iterate until it is green.
- Do NOT run git, flyctl, or touch Linear. Do NOT commit or push. ONLY edit the
  working tree. The surrounding automation handles commit, deploy, and Linear.
"""


def run_claude(issue):
    """Delegate implementation to headless Claude. Edits the working tree only."""
    cmd = ["claude", "-p", build_prompt(issue),
           "--dangerously-skip-permissions", "--max-turns", "80"]
    # ANTHROPIC_API_KEY is inherited from the environment (CI secret).
    sh(cmd)


# --- Linear helpers (never fatal — a note failure shouldn't abort a tick) --

def note(identifier, body):
    try:
        linear_api.comment(identifier, body)
    except linear_api.LinearError as exc:
        print(f"!! could not comment on {identifier}: {exc}", flush=True)


def move(identifier, state):
    linear_api.set_state(identifier, state)


# --- phases ---------------------------------------------------------------

def tests_pass():
    res = sh(["python3", "tests/run_tests.py"], check=False, capture=True)
    return res.returncode == 0, (res.stdout or "")


def health_ok(url, tries=6):
    for i in range(1, tries + 1):
        res = sh(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                 check=False, capture=True)
        code = (res.stdout or "").strip()
        print(f"health {url} attempt {i} -> {code}", flush=True)
        if code == "200":
            return True
        sh(["sleep", "10"], check=False)
    return False


def head_sha():
    return git("rev-parse", "HEAD", capture=True).stdout.strip()


def do_build(issue):
    ident = issue["identifier"]
    branch = branch_for(issue)
    print(f"== BUILD {ident}: {issue['title']} (branch {branch}) ==", flush=True)
    move(ident, "In Progress")

    # Fresh branch off the latest main.
    git("fetch", "origin", "main")
    git("checkout", "main")
    git("reset", "--hard", "origin/main")
    git("branch", "-D", branch, check=False)
    git("checkout", "-b", branch)

    run_claude(issue)

    if not git("status", "--porcelain", capture=True).stdout.strip():
        note(ident, f"🤖 Autobuild ran on {ident} but Claude produced no changes. "
                    "Left in In Progress for a human to look at.")
        return f"{ident}: no changes"

    ok, log = tests_pass()
    if not ok:
        tail = "\n".join(log.strip().splitlines()[-25:])
        note(ident, f"🤖 Autobuild: tests **failed** for {ident} — left in In "
                    f"Progress, nothing committed.\n\n```\n{tail}\n```")
        git("checkout", "main", check=False)
        return f"{ident}: tests failed"

    git("add", "-A")
    git("commit", "-m", commit_subject(issue),
        "-m", f"{ident} — implemented by hosted autobuild.",
        "-m", COAUTHOR_TRAILER)
    sha = head_sha()
    git("push", "--force-with-lease", "-u", "origin", branch)

    sh(FLY_STAGING)
    staged = health_ok(STAGING_URL)
    diffstat = git("diff", "--stat", "origin/main...HEAD", capture=True).stdout.strip()
    tail = "\n".join(log.strip().splitlines()[-8:])

    move(ident, GATE_COLUMN)
    note(ident, (
        f"🤖 **Autobuild → In Review.** Built on `{branch}`, deployed to staging.\n\n"
        f"**Commit:** {COMMIT_URL}{sha}\n\n"
        f"**Proof of work:**\n- Tests:\n```\n{tail}\n```\n"
        f"- Staging: {STAGING_URL} — health check "
        f"{'✅ 200' if staged else '⚠️ did not return 200'}\n\n"
        f"**Changes:**\n```\n{diffstat}\n```\n\n"
        f"Verify on staging, then move this card to **Deploy** to ship to prod."
    ))
    try:
        linear_api.link(ident, f"{COMMIT_URL}{sha}", commit_subject(issue))
    except linear_api.LinearError:
        pass
    return f"{ident}: built → In Review ({'staging ok' if staged else 'staging WARN'})"


def do_ship(issue):
    ident = issue["identifier"]
    branch = branch_for(issue)
    print(f"== SHIP {ident}: {issue['title']} (branch {branch}) ==", flush=True)

    git("fetch", "origin", "main", branch)
    git("checkout", "main")
    git("reset", "--hard", "origin/main")
    merge = git("merge", "--no-ff", f"origin/{branch}",
                "-m", f"Merge {branch} for {ident} (autobuild ship)", check=False)
    if merge.returncode != 0:
        git("merge", "--abort", check=False)
        note(ident, f"🤖 Autobuild: could not merge `{branch}` into main cleanly "
                    f"for {ident} (conflict). Left in Deploy — needs a manual merge.")
        return f"{ident}: merge conflict"

    ok, _ = tests_pass()
    if not ok:
        note(ident, f"🤖 Autobuild: tests failed on merged main for {ident}. "
                    "Not pushing / deploying; left in Deploy.")
        return f"{ident}: tests failed on merge"

    sha = head_sha()
    # Push main (GITHUB_TOKEN push won't re-trigger ci.yml, so we deploy inline).
    git("push", "origin", "main")
    sh(FLY_STAGING)
    if not health_ok(STAGING_URL):
        note(ident, f"🤖 Autobuild: staging health check failed for {ident} after "
                    "merge — did NOT deploy prod. Left in Deploy.")
        return f"{ident}: staging unhealthy"
    sh(FLY_PROD)
    prod_ok = health_ok(PROD_URL)

    move(ident, DONE_COLUMN)
    note(ident, (
        f"🤖 **Autobuild → Done. Shipped to prod.**\n\n"
        f"**Commit (merge to main):** {COMMIT_URL}{sha}\n\n"
        f"**Proof of work:** tests green on merged main; staging + prod deployed via "
        f"flyctl. Prod: {PROD_URL} — health check "
        f"{'✅ 200' if prod_ok else '⚠️ did not return 200'}.\n\n"
        f"Merged `{branch}` and deployed the prod Fly app."
    ))
    try:
        linear_api.link(ident, f"{COMMIT_URL}{sha}", f"Prod: {commit_subject(issue)}")
    except linear_api.LinearError:
        pass
    return f"{ident}: shipped → Done ({'prod ok' if prod_ok else 'prod WARN'})"


def tick():
    issues = linear_api.board()
    to_build = [i for i in issues if i.get("state") == BUILD_COLUMN]
    to_ship = [i for i in issues if i.get("state") == SHIP_COLUMN]
    print(f"tick: {len(to_ship)} to ship, {len(to_build)} to build", flush=True)

    results = []
    # Ship approved cards first (don't make the human wait), then build one.
    for issue in to_ship:
        try:
            results.append(do_ship(issue))
        except Exception as exc:  # noqa: BLE001 — one bad card must not kill the tick
            results.append(f"{issue['identifier']}: ERROR {exc}")
            note(issue["identifier"], f"🤖 Autobuild ship errored: {exc}")
    if to_build:
        issue = to_build[0]  # one build per tick; the rest wait for the next
        try:
            results.append(do_build(issue))
        except Exception as exc:  # noqa: BLE001
            results.append(f"{issue['identifier']}: ERROR {exc}")
            note(issue["identifier"], f"🤖 Autobuild build errored: {exc}")

    if not results:
        print("board quiet — nothing to do.", flush=True)
    else:
        print("tick summary:", flush=True)
        for r in results:
            print(f"  - {r}", flush=True)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "tick"
    if cmd != "tick":
        sys.exit("usage: autobuild.py tick")
    try:
        return tick()
    except linear_api.LinearError as exc:
        sys.exit(f"Linear API error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
