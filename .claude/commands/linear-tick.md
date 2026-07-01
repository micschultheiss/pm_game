---
description: One poll of the pm_game Linear board — build Todo cards, ship cards in Deploy.
allowed-tools: Bash, Read, Edit, Write, mcp__plugin_productivity_linear__list_issues, mcp__plugin_productivity_linear__save_issue, mcp__plugin_productivity_linear__save_comment, mcp__plugin_productivity_linear__get_issue, mcp__plugin_productivity_linear__list_issue_statuses
---

# /linear-tick — Linear board → auto-build/ship (one poll)

You are one iteration of the board watcher for the **pm_game** project (Linear
team **Mics-playground**). Do a single poll and act on it, then stop. This
command is meant to be driven on an interval by `/loop` — keep each tick lean and
**idempotent**: doing nothing when nothing changed is the common, correct case.

The state machine (agreed with the user):

```
Todo ──build──▶ In Progress ──test+commit+deploy-staging──▶ In Review
                                                             │  (human verifies on staging)
                                                             ▼  human moves card to Deploy
                                                    push main → CI test→staging→prod ──▶ Done
```

- **Build trigger:** card in **Todo**.
- **Staging gate:** **In Review** — where you park a built card for the human to
  verify on staging. You stop here.
- **Ship trigger:** card in **Deploy** — the human moved it there to approve; ship
  it to prod.

Never push to `main` during the build phase — the CI pipeline ships prod on every
`main` push (ADR 006). The build phase lives entirely on a per-ticket branch and
deploys **only** to staging locally. Pushing to prod happens **only** for cards
the human has moved to Deploy.

## 1. Read the board & classify

1. Call `list_issues` with `project: "pm_game"`, `includeArchived: false`, a high
   `limit` (e.g. 100).
2. Normalise the result into a compact array and write it to the scratchpad, e.g.
   `<session scratchpad>/linear_now.json`. Each element:
   `{"identifier","title","state","url","branchName"}` where `state` is the
   **column name** (e.g. `"Todo"`, `"Deploy"`).
3. Run the classifier:
   ```bash
   python3 scripts/linear_watch.py --current <that file>
   ```
   It prints `{"to_build":[...], "to_ship":[...]}` — cards in Todo and cards in
   Deploy. **Only** act on those lists. If both are empty, report "board quiet —
   nothing to do" and stop.

> Safety: process **one** card per tick if several are queued (finish a build
> before starting another). The next tick picks up the rest.

## 2. Build phase — for each card in `to_build`

1. **Claim it:** `save_issue` to move the issue to **In Progress**. (This alone
   removes it from Todo, so no later tick re-triggers it.)
2. **Branch:** from an up-to-date `main`, create a work branch named after
   Linear's suggested `branchName` if present, else `mic/<identifier-lower>-<slug>`.
   Never work on `main`.
3. **Build the ticket.** Read the issue description (`get_issue`) for scope.
   Follow the repo conventions in `CLAUDE.md`: engine logic lands in
   `src/engine.py` first (stdlib only), then each frontend wires up UI. Keep the
   meme-y tone. Respect the load-bearing mechanics.
4. **Test:** run `python3 tests/run_tests.py` (tests + coverage gate). It **must
   pass**. For balance-affecting changes, run `tests/simulate.py` before/after.
   - **If tests fail and you cannot fix them:** leave the card in **In Progress**,
     add a `save_comment` explaining the failure (paste the output), and stop.
     Do **not** advance to In Review. Do **not** commit broken code.
5. **Commit locally** (conventional message; do NOT push). End the message with:
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
6. **Deploy to staging** (local flyctl, prod untouched):
   ```bash
   fly deploy --config fly/fly.staging.toml
   ```
   Then health-check: `curl -sSf https://hallucination-inc-staging.fly.dev/`
   (retry a few times — staging scales to zero, first hit is a cold start).
7. **Hand off to the gate:** `save_issue` to move the issue to **In Review**, and
   `save_comment` with the three things `CLAUDE.md` requires — **commits** (full
   GitHub URLs `https://github.com/micschultheiss/pm_game/commit/<sha>`),
   **proof of work** (test pass count + coverage, staging URL you verified and
   the outcome), and a 1–3 sentence **description**. Tell the user: *verify on
   staging, then move the card to **Deploy** to ship.* Stop. **Do not push.**

## 3. Ship phase — for each card in `to_ship` (in Deploy)

The card is in Deploy → the human approved the staging build. Ship it to prod
through the CI gate.

1. Check out the card's work branch. Ensure it's rebased on the latest `main` and
   that `python3 tests/run_tests.py` still passes.
2. Merge/fast-forward the branch into `main` and **`git push`**. CI (ADR 006)
   runs test → deploy-staging → deploy-prod; prod ships only if all pass.
3. Watch the push land (`gh run watch` if available, or report the run URL). If CI
   fails, `save_comment` the failure and leave the card in Deploy — do not force.
4. On green: `save_issue` to move the issue to **Done**, and `save_comment` with
   commits (prod merge/commit URLs), proof of work (CI result + prod URL
   `https://hallucination-inc.fly.dev/`), and a short description. Attach the
   commit URL via `save_issue` `links` per `CLAUDE.md`.

## 4. Wrap up

Give the user a one-line summary of what this tick did (built X → In Review,
shipped Y → Done, or "quiet"). The `/loop` wrapper will fire the next tick on its
interval.

**Prereqs (verify once, warn if missing):** the **Deploy** column must exist in
the Mics-playground workflow (`list_issue_statuses`) — it's the ship trigger. The
`fly` CLI must be authenticated (`fly auth whoami`) or staging deploys fail.
Working tree should be clean at the start of a build.
