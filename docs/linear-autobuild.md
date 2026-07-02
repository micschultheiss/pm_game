# Linear board → auto-build/ship loop (hosted)

Move a card to **Todo** on the pm_game Linear board and a cloud Claude picks it
up, builds it on a branch, and parks it on **staging** for you to verify. Move
that card to **Deploy** and it ships to prod. Runs in **GitHub Actions** — no
open terminal, nothing on your Mac.

## The state machine

```
Todo ──build──▶ In Progress ──test + commit + deploy-staging──▶ In Review
                                                                 │  you verify on staging
                                                                 ▼  you move card to Deploy
                                                    merge main + deploy-prod ──▶ Done
```

- **Build phase never touches `main`.** It works on a per-ticket branch and
  deploys only to the staging Fly app. Prod stays untouched until you approve.
- **In Review is the human gate.** The tick stops there and comments the commit,
  the staging URL, tests, and a diffstat. You test on
  `https://hallucination-inc-staging.fly.dev/`.
- **Deploy = ship.** Moving a card into the Deploy column is your approval: the
  next tick merges the branch to `main`, deploys staging→prod, and moves the card
  to **Done** with a proof-of-work comment.

Both triggers are "card is in column X" (build = Todo, ship = Deploy), and each
action moves the card *out* of its trigger column, so ticks are naturally
idempotent — no state to track.

## Why GitHub Actions (not the in-session `/loop`)

The first cut ran an in-terminal `/loop`, but it only ran while that session was
open and depended on the interactive Linear MCP. The hosted version runs on a
schedule in GitHub's cloud, reads/writes Linear over the raw GraphQL API with
`LINEAR_API_KEY`, and reuses the Fly deploy tokens the CI pipeline already has —
so it works with your machine closed. It **polls** (Linear can't push to CI), but
since moving a card *is* the trigger, a tick acts within one interval.

## Pieces

| File | Role |
|------|------|
| [`.github/workflows/linear-autobuild.yml`](../.github/workflows/linear-autobuild.yml) | Scheduled workflow (every 5 min) + manual `workflow_dispatch`. Thin: checks out, installs deps + the Claude CLI, runs one tick. |
| [`scripts/autobuild.py`](../scripts/autobuild.py) | The tick driver. Classifies the board, ships Deploy cards, builds one Todo card. Owns git/flyctl/tests/Linear moves; delegates only the code-writing to headless `claude -p`. |
| [`scripts/linear_api.py`](../scripts/linear_api.py) | Stdlib Linear GraphQL client — read board, move card, comment, attach link. The write half the MCP can't do from CI. Also a standalone CLI (`board`/`state`/`comment`/`link`). |
| [`scripts/linear_watch.py`](../scripts/linear_watch.py) | Read-only classifier kept for local debugging: `LINEAR_API_KEY=… python3 scripts/linear_watch.py` prints what a tick *would* build/ship. |

## Setup

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Status | Used for |
|--------|--------|----------|
| `LINEAR_API_KEY` | ✅ already set | read board, move cards, comment |
| `FLY_API_TOKEN` | ✅ already set | deploy staging + prod |
| `ANTHROPIC_API_KEY` | ⚠️ **add this** | headless Claude for the build step |

Also ensure **Settings → Actions → General → Workflow permissions** allows
*Read and write* (the tick pushes branches and `main`). Until `ANTHROPIC_API_KEY`
is set the tick step is skipped, so nothing runs prematurely.

Deploy note: a `GITHUB_TOKEN` push to `main` does **not** re-trigger `ci.yml`, so
the ship phase deploys prod inline with the same `flyctl` commands `ci.yml` uses,
rather than relying on push-triggered CI.

## Running it

- **First run:** trigger it by hand — **Actions → Linear autobuild → Run
  workflow** — and watch the logs while a real card goes Todo → In Review.
- **After that:** it runs every ~5 minutes on its own. Drop a card in **Todo** to
  build; move a built card to **Deploy** to ship.

## Notes & limits

- A build that fails tests stays in **In Progress** with a failure comment; broken
  code is never committed. A merge conflict on ship leaves the card in **Deploy**
  with a note.
- One card is built per tick; extras wait for the next tick. Ships are processed
  first so approvals aren't delayed.
- **Terminal-only changes** (diff touches `src/terminal.py` but nothing the web
  app exercises) can't be verified on staging. The In Review comment detects this
  and instead gives the `git fetch`/`checkout` + `python3 hallucination_inc.py`
  commands to test locally.
- Cost: each build tick that has work spins up a full Claude run — mind the
  5-minute cadence if that matters. Widen the cron or gate it if needed.
- `docs/TODO.md` is a generated mirror (`scripts/sync_todo_from_linear.py`, ADR
  007). Every tick regenerates it on a clean `main` and commits **only if it
  drifted**, so board changes (manual or loop-driven) show up within one interval
  — no hand-run sync needed. Docs-only commit; prod is untouched.
