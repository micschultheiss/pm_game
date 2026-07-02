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

# A reviewer requests changes on an In Review card with a comment starting "[Fix]".
# The loop reworks the branch and replies with a comment containing REWORK_MARKER;
# a [Fix] is "addressed" once a marked reply exists after it (see pending_fix).
FIX_PREFIX = "[fix]"                 # matched case-insensitively
REWORK_MARKER = "Autobuild reworked"  # substring present in every rework reply

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


# Paths the web app (and therefore staging) exercises. If a diff touches none of
# these but does touch the terminal frontend, staging can't demonstrate it.
WEB_SURFACE = ("src/web.py", "src/engine.py", "src/templates/", "src/static/",
               "requirements.txt")


def is_terminal_only(changed_files):
    """True when the change is terminal-frontend-only — staging won't show it."""
    touches_terminal = any(f.startswith("src/terminal.py") for f in changed_files)
    touches_web = any(f.startswith(w) for f in changed_files for w in WEB_SURFACE)
    return touches_terminal and not touches_web


def verify_instructions(terminal_only, branch):
    """The 'how to verify' line for the In Review comment, per change surface."""
    if terminal_only:
        return (
            "⚠️ **Terminal-only change — staging (the web app) won't show this.** "
            "Pull the branch and run the terminal locally:\n"
            f"```bash\ngit fetch origin {branch}\n"
            f"git checkout {branch}\n"
            "python3 hallucination_inc.py\n```\n"
            "When it looks right, move this card to **Deploy** to ship to prod."
        )
    return (f"Verify on staging ({STAGING_URL}), then move this card to **Deploy** "
            "to ship to prod.")


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


def rework_prompt(issue, fix_text):
    return f"""You are REWORKING an already-built ticket in the Hallucination Inc.
codebase based on reviewer feedback. The current branch already contains the
previous implementation — adjust it in place to address the feedback below.

Linear ticket {issue['identifier']}: {issue['title']}

Original description:
{issue['description'] or '(none)'}

Reviewer feedback to address ([Fix] comment from the In Review gate):
{fix_text}

Rules:
- Address the feedback. Follow CLAUDE.md (engine logic in src/engine.py first,
  stdlib only; frontends wire their own UI; keep the meme-y tone; respect the
  load-bearing mechanics).
- The test suite MUST pass: `python3 tests/run_tests.py`. Update tests as needed.
- Do NOT run git, flyctl, or touch Linear. Do NOT commit or push. ONLY edit the
  working tree. The surrounding automation handles commit, deploy, and Linear.
- End your final message with a one-line summary of exactly what you changed.
"""


def run_claude(prompt, capture=False):
    """Delegate to headless Claude. Edits the working tree only. Returns Claude's
    final text when capture=True (used to summarise a rework), else ""."""
    cmd = ["claude", "-p", prompt,
           "--dangerously-skip-permissions", "--max-turns", "80"]
    # ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN inherited from env (CI secret).
    res = sh(cmd, capture=capture)
    return (res.stdout or "") if capture else ""


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

    run_claude(build_prompt(issue))

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
    changed = git("diff", "--name-only", "origin/main...HEAD", capture=True).stdout.split()
    diffstat = git("diff", "--stat", "origin/main...HEAD", capture=True).stdout.strip()
    tail = "\n".join(log.strip().splitlines()[-8:])
    terminal_only = is_terminal_only(changed)

    move(ident, GATE_COLUMN)
    note(ident, (
        f"🤖 **Autobuild → In Review.** Built on `{branch}`, deployed to staging.\n\n"
        f"**Commit:** {COMMIT_URL}{sha}\n\n"
        f"**Proof of work:**\n- Tests:\n```\n{tail}\n```\n"
        f"- Staging: {STAGING_URL} — health check "
        f"{'✅ 200' if staged else '⚠️ did not return 200'}\n\n"
        f"**Changes:**\n```\n{diffstat}\n```\n\n"
        f"{verify_instructions(terminal_only, branch)}"
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


def pending_fix(comment_list):
    """Return the text of an unaddressed [Fix] comment on an In Review card, else None.

    A [Fix] is unaddressed when no rework reply (containing REWORK_MARKER) exists
    at/after it. Comparing the latest [Fix] against the latest reply means a fresh
    [Fix] after a prior rework re-triggers, but a reworked one won't loop.
    """
    ordered = sorted(comment_list, key=lambda c: c.get("createdAt") or "")
    last_fix = last_reply = None
    for c in ordered:
        body = (c.get("body") or "").strip()
        if body.lower().startswith(FIX_PREFIX):
            last_fix = c
        if REWORK_MARKER in body:
            last_reply = c
    if not last_fix:
        return None
    if last_reply and (last_reply.get("createdAt") or "") >= (last_fix.get("createdAt") or ""):
        return None  # already reworked after the latest [Fix]
    return last_fix["body"].strip()[len(FIX_PREFIX):].strip() or "(no detail given)"


def do_rework(issue, fix_text):
    """Rework an In Review card's branch to address a [Fix] comment, redeploy
    staging, and leave it In Review with a reply describing what changed."""
    ident = issue["identifier"]
    branch = branch_for(issue)
    print(f"== REWORK {ident}: {fix_text[:70]} ==", flush=True)

    git("fetch", "origin", branch)
    git("checkout", "-B", branch, f"origin/{branch}")
    git("reset", "--hard", f"origin/{branch}")

    summary = run_claude(rework_prompt(issue, fix_text), capture=True).strip()

    if not git("status", "--porcelain", capture=True).stdout.strip():
        note(ident, f"🤖 **Autobuild reworked** {ident}: the [Fix] produced no code "
                    f"changes — left In Review.\n\n> {fix_text}")
        git("checkout", "-f", "main", check=False)
        return f"{ident}: rework no-op"

    ok, log = tests_pass()
    if not ok:
        tail = "\n".join(log.strip().splitlines()[-20:])
        note(ident, f"🤖 **Autobuild reworked** {ident} but tests **failed** — nothing "
                    f"committed, left In Review.\n\n> {fix_text}\n\n```\n{tail}\n```")
        git("checkout", "-f", "main", check=False)  # discard broken edits
        return f"{ident}: rework tests failed"

    git("add", "-A")
    git("commit", "-m", f"fix: rework {ident} per review feedback",
        "-m", f"Addressed [Fix]: {fix_text}", "-m", COAUTHOR_TRAILER)
    sha = head_sha()
    git("push", "--force-with-lease", "-u", "origin", branch)

    sh(FLY_STAGING)
    staged = health_ok(STAGING_URL)
    changed = git("diff", "--name-only", "origin/main...HEAD", capture=True).stdout.split()
    diffstat = git("diff", "--stat", "origin/main...HEAD", capture=True).stdout.strip()
    what = "\n".join(summary.splitlines()[-6:]) if summary else "(no summary)"

    move(ident, GATE_COLUMN)  # stays In Review (idempotent)
    note(ident, (
        f"🤖 **Autobuild reworked** {ident} → still **In Review**. Addressed the "
        f"[Fix] on `{branch}`.\n\n"
        f"> {fix_text}\n\n"
        f"**New commit:** {COMMIT_URL}{sha}\n\n"
        f"**What changed:**\n{what}\n\n"
        f"**Files:**\n```\n{diffstat}\n```\n"
        f"- Staging redeployed: {STAGING_URL} — health check "
        f"{'✅ 200' if staged else '⚠️ did not return 200'}\n\n"
        f"{verify_instructions(is_terminal_only(changed), branch)}"
    ))
    return f"{ident}: reworked (staging {'ok' if staged else 'WARN'})"


def sync_todo():
    """Regenerate docs/TODO.md from Linear; commit to main only if it drifted.

    TODO.md is a generated mirror (ADR 007) — the loop keeps it live so board
    changes (manual or loop-driven) show up without a hand-run sync. Runs on a
    clean main so the commit never lands on a build branch. Docs-only: a
    GITHUB_TOKEN push doesn't re-trigger ci.yml and TODO.md doesn't affect the
    app, so prod is untouched. Returns a summary string only when it committed.
    """
    git("fetch", "origin", "main")
    git("checkout", "-f", "main")            # -f: discard any build-branch leftovers
    git("reset", "--hard", "origin/main")
    sh(["python3", "scripts/sync_todo_from_linear.py"])
    if not git("status", "--porcelain", "docs/TODO.md", capture=True).stdout.strip():
        return None                          # already in sync — stay quiet
    git("add", "docs/TODO.md")
    git("commit", "-m", "docs: sync TODO.md from Linear (autobuild)",
        "-m", COAUTHOR_TRAILER)
    git("push", "origin", "main")
    return "TODO.md synced"


def find_rework(in_review):
    """First (issue, fix_text) among In Review cards with an unaddressed [Fix]."""
    for issue in in_review:
        try:
            fix = pending_fix(linear_api.comments(issue["identifier"]))
        except linear_api.LinearError as exc:
            print(f"!! could not read comments for {issue['identifier']}: {exc}", flush=True)
            continue
        if fix:
            return issue, fix
    return None, None


def tick():
    issues = linear_api.board()
    to_build = [i for i in issues if i.get("state") == BUILD_COLUMN]
    to_ship = [i for i in issues if i.get("state") == SHIP_COLUMN]
    in_review = [i for i in issues if i.get("state") == GATE_COLUMN]
    print(f"tick: {len(to_ship)} to ship, {len(in_review)} in review, "
          f"{len(to_build)} to build", flush=True)

    results = []
    had_error = False  # hard/infra errors fail the run; expected gates don't
    # Ship approved cards first (don't make the human wait).
    for issue in to_ship:
        try:
            results.append(do_ship(issue))
        except Exception as exc:  # noqa: BLE001 — one bad card must not kill the tick
            had_error = True
            results.append(f"{issue['identifier']}: ERROR {exc}")
            note(issue["identifier"], f"🤖 Autobuild ship errored: {exc}")

    # Then EITHER rework one In Review card with a pending [Fix], OR build one Todo
    # — at most one Claude-heavy op per tick. Rework wins: finish in-flight work
    # before starting new work.
    rework_issue, fix_text = find_rework(in_review)
    if rework_issue:
        try:
            results.append(do_rework(rework_issue, fix_text))
        except Exception as exc:  # noqa: BLE001
            had_error = True
            results.append(f"{rework_issue['identifier']}: ERROR {exc}")
            note(rework_issue["identifier"], f"🤖 Autobuild rework errored: {exc}")
    elif to_build:
        issue = to_build[0]  # one build per tick; the rest wait for the next
        try:
            results.append(do_build(issue))
        except Exception as exc:  # noqa: BLE001
            had_error = True
            results.append(f"{issue['identifier']}: ERROR {exc}")
            # Infra error (bad key, git/fly failure) — put the card back in Todo so
            # a fixed retry re-triggers it, rather than stranding it In Progress.
            try:
                linear_api.set_state(issue["identifier"], BUILD_COLUMN)
            except linear_api.LinearError:
                pass
            note(issue["identifier"], f"🤖 Autobuild build errored (returned to "
                                      f"{BUILD_COLUMN} for retry): {exc}")

    # Keep the generated TODO.md mirror in step with the board every tick.
    try:
        synced = sync_todo()
        if synced:
            results.append(synced)
    except Exception as exc:  # noqa: BLE001 — a docs sync must never fail the tick
        print(f"!! TODO.md sync failed: {exc}", flush=True)

    if not results:
        print("board quiet — nothing to do.", flush=True)
    else:
        print("tick summary:", flush=True)
        for r in results:
            print(f"  - {r}", flush=True)
    # Fail the workflow run on hard errors so a broken tick shows red, not green.
    return 1 if had_error else 0


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
