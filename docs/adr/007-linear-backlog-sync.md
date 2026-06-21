# ADR 007: Linear is the Backlog Source of Truth; TODO.md is Generated

**Status:** Accepted
**Date:** 2026-06-21

## Context

The working backlog lived in [`docs/TODO.md`](../TODO.md) — a hand-maintained
checklist. As the project grew it accumulated long inline notes (research dumps,
balance rationale) and was edited by hand on every task, which drifts and is hard
to query, prioritise, or assign. We now track work in **Linear** (project
`pm_game`, team Mics-playground). Two sources of truth for the same backlog
guarantees they diverge.

## Decision

**Linear is the single source of truth for the backlog.** `docs/TODO.md` becomes
a generated, read-only mirror so the repo still carries a glanceable backlog
without a network call.

- One-way sync, **Linear → file**, via
  [`scripts/sync_todo_from_linear.py`](../../scripts/sync_todo_from_linear.py).
  It pulls every issue in the project over the Linear GraphQL API and rewrites
  `docs/TODO.md` deterministically.
- **Mapping:** issue priority → section (Urgent/High → *Now*, Medium → *Next*,
  Low/None → *Later / ideas*); state type → checkbox (`completed` → `[x]`,
  `started` → `[~]`, else `[ ]`); canceled issues are dropped; completed issues
  collect under *Done*. Each line links back to its Linear issue (`MIC-…`).
- **Stdlib only** (`urllib` + `json`) — no new dependency, matching the
  engine/terminal zero-install convention. Reads `LINEAR_API_KEY` from the env
  (a personal key from <https://linear.app/settings/api>); never hardcoded.
- **Idempotent + no timestamp** in the output, so re-running produces identical
  bytes. `--check` writes nothing and exits non-zero on drift — usable in CI or
  a pre-commit hook.
- `CLAUDE.md` updated: agents edit the backlog in Linear and regenerate the file,
  never hand-edit `docs/TODO.md`.

## Alternatives considered

- **Two-way sync.** Tempting, but conflict resolution is the whole problem; a
  designated source of truth (Linear) with a one-way mirror is simpler and
  unambiguous. File edits are intentionally disposable.
- **Drop `docs/TODO.md` entirely.** Loses the offline, in-repo glance and the
  git-visible backlog history. The generated mirror keeps both for free.
- **Keep hand-editing `TODO.md`, mirror to Linear.** Inverts the authority and
  reintroduces drift the moment someone files an issue directly in Linear (the
  common case).
- **Use the Linear MCP from CI.** The MCP is an interactive/session tool; a
  self-contained script with an API key is the portable, automatable path.

## Consequences

**Wins:**

- No divergence: the file is a pure projection of Linear.
- Backlog gains Linear's real affordances (priority, state, assignee, links,
  filtering) while the repo keeps a committed snapshot.
- The richer per-task notes now live in issue descriptions, not the file.

**Costs / things to watch:**

- Running the sync needs a `LINEAR_API_KEY`; without it the file goes stale. A
  `--check` step in CI (with the key as a secret) would enforce freshness — not
  wired up yet, since it needs the secret and network egress in the pipeline.
- The project name (`pm_game`) is hardcoded in the script; renaming the Linear
  project means editing `PROJECT_NAME`.
- History/rationale that used to sit inline in `TODO.md` (e.g. the 2026
  token-price research) now lives in Linear issue descriptions and
  `.github/NOTES.md`; the file only carries titles + links.

## Related

- [`scripts/sync_todo_from_linear.py`](../../scripts/sync_todo_from_linear.py) — the sync tool.
- [`docs/TODO.md`](../TODO.md) — the generated mirror.
- `CLAUDE.md` → "Memory & docs maintenance" — the updated workflow.
