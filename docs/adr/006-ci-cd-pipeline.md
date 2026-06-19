# ADR 006: CI/CD Pipeline with a Staging Gate

**Status:** Accepted
**Date:** 2026-06-19

## Context

Until now the test suite + 90% coverage gate only ran in the local
`.git/hooks/pre-commit` hook, and the Fly deploy ([`fly-deploy.yml`]) fired on
*every* push to `main` with no gate — a commit that bypassed the hook
(`--no-verify`, or a clone without the hook installed) could ship a red build
straight to prod. ADR 004 deferred a real pipeline until we wanted deploys to
fire without local flyctl or to add a staging app. We now want both.

## Decision

Replace the single-stage deploy workflow with one
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) that runs a
three-stage pipeline: **test → deploy-staging → deploy-prod**.

- **test** — runs on every push and pull request. `pip install -r
  requirements.txt` (Flask is needed because `run_tests.py` imports `web.py` to
  measure its coverage), then `python3 tests/run_tests.py` — the same suite and
  gate the pre-commit hook runs. Python pinned to 3.12 to match the Dockerfile.
- **deploy-staging** — `needs: test`, gated to pushes on `main`. Deploys to a
  new **`hallucination-inc-staging`** Fly app, then health-checks
  `https://hallucination-inc-staging.fly.dev/` (curl for HTTP 200, retried to
  absorb cold starts).
- **deploy-prod** — `needs: deploy-staging`, gated to pushes on `main`. Deploys
  to the existing `hallucination-inc` app.

Because `needs` is transitive and a non-200 health check fails the staging job,
**prod only ships if tests pass AND staging deploys AND staging answers
healthy.**

Staging runs from [`fly/fly.staging.toml`](../../fly/fly.staging.toml) — a copy
of the prod config that scales to zero when idle (`auto_stop_machines = "stop"`,
`min_machines_running = 0`). Staging holds no durable state (the in-memory
`_games` dict, ADR 002), so scale-to-zero is free: a cold request starts a fresh
machine. Prod keeps `auto_stop_machines = "off"` so in-progress runs survive.

## Alternatives considered

- **Keep deploy ungated, just add a test workflow.** Simpler, but leaves the
  "red build reaches prod" hole open. Rejected — the whole point was the gate.
- **Two separate workflows linked by `workflow_run`.** More moving parts; the
  triggering-commit and secret-availability semantics of `workflow_run` are a
  common foot-gun. A single workflow with `needs` is clearer and atomic.
- **Manual approval gate before prod** (GitHub Environments + required
  reviewers). Heavier than a solo project needs; "green build auto-promotes"
  matches the push-to-`main` workflow. Easy to add later if a contributor joins.
- **No staging app, deploy prod straight after tests.** Loses the
  deploy-and-serve smoke signal that staging gives essentially for free.

## Consequences

**Wins:**

- A red build can no longer reach prod, regardless of local hook state.
- Staging is a real pre-prod smoke target on the identical Docker image.
- Tests now run on PRs and on every branch push, not just at commit time.

**Costs / things to watch:**

- **Token scope.** Both deploy jobs use the one `FLY_API_TOKEN` repo secret. It
  must be **org-scoped** (or scoped to both apps) — an app-scoped deploy token
  for `hallucination-inc` alone will fail the staging job. Mint with
  `fly tokens create org personal` and set via `gh secret set FLY_API_TOKEN`.
- Staging's scale-to-zero means its first request after idle is a cold start;
  the health check retries (6 × 10s) to cover this.
- The pipeline deploys staging *and* prod on every `main` push — roughly double
  the deploy time of the old single-stage flow. Acceptable for the safety.
- Fly may keep 2 staging machines for zero-downtime deploys despite
  `min_machines_running = 0`; they auto-stop when idle.

## Related

- [ADR 004 — Deployment on Fly.io](004-deployment-flyio.md) — this fulfils its
  deferred "CI/CD pipeline" item.
- [ADR 002 — Game state](002-game-state.md) — the in-memory dict that makes
  staging scale-to-zero safe.
