# Linear board → auto-build/ship loop

Move a card to **Todo** on the pm_game Linear board and an in-session Claude
picks it up, builds it, and parks it on **staging** for you to verify. Move that
card **out of QA** and Claude ships it to prod. This doc explains the moving
parts and how to run it.

## The state machine

```
Todo ──build──▶ In Progress ──test + commit + deploy-staging──▶ QA
                                                                 │  you verify on staging
                                                                 ▼  you move card OUT of QA
                                                        push main → CI test→staging→prod ──▶ Done
```

- **Build phase never touches `main`.** It works on a per-ticket branch and
  deploys only to the staging Fly app (`fly/fly.staging.toml`). This is
  deliberate: the CI pipeline (see [ADR 006](adr/006-ci-cd-pipeline.md)) ships
  **prod on every `main` push**, so prod stays untouched until you approve.
- **QA is the human gate.** Claude stops at QA and comments the commits, the
  staging URL it verified, and a short description. You test on
  `https://hallucination-inc-staging.fly.dev/`.
- **Leaving QA = ship.** Any move out of the QA column is read as approval:
  Claude merges the branch to `main` and pushes, and CI runs
  test → deploy-staging → deploy-prod. On green the card goes to **Done** with a
  proof-of-work comment.

## Why polling (not a webhook)

Linear can't push events to your laptop without hosting a webhook receiver. The
watcher therefore **polls** the board on an interval — but because moving a card
out of Todo (or QA) is itself the trigger, it fires within one poll interval of
your action, which is effectively "the moment you move it."

## Pieces

| File | Role |
|------|------|
| [`.claude/commands/linear-tick.md`](../.claude/commands/linear-tick.md) | The `/linear-tick` slash command — one poll + act. The playbook Claude follows each tick. |
| [`scripts/linear_watch.py`](../scripts/linear_watch.py) | Pure diff engine. Reads the board (via the caller) + a local snapshot, returns `to_build` / `to_ship`. No git/Fly/build side effects. |
| `.claude/linear_watch_state.json` | Per-checkout transition snapshot (git-ignored). How "was in QA last tick" is remembered. |

The watcher reads the board through the authenticated **Linear MCP** in-session,
so it needs **no `LINEAR_API_KEY`**. (The script can self-fetch with a key for
standalone CLI use, but the loop path doesn't require one.)

## One-time setup

1. **Add the `QA` column.** The board watcher needs a workflow state named `QA`.
   It can't be created via tooling (the Linear MCP has no create-status call), so
   add it by hand: **Linear → Settings → Team `Mics-playground` → Workflow →**
   add a state **`QA`** in the **Started** group, positioned after *In Progress*.
2. **Authenticate `fly`** so staging/prod deploys work: `fly auth whoami`.
3. That's it — the snapshot file self-creates on first tick.

## Running it

Drive `/linear-tick` on an interval with the built-in `/loop` skill, in an open
Claude Code session:

```
/loop 3m /linear-tick
```

Each tick is idempotent: if nothing moved, it reports "board quiet" and waits for
the next interval. It processes one card per tick (finishing a build before
starting the next). Because the watcher lives inside a `/loop`, it runs only
while that session is open — close the session to stop watching.

## Notes & limits

- A build that fails tests stays in **In Progress** with a failure comment; it is
  never advanced to QA and broken code is never committed.
- If several cards sit in Todo at once, they're built one per tick.
- `docs/TODO.md` is generated from Linear and now includes a **QA** section
  (`scripts/sync_todo_from_linear.py`).
