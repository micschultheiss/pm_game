# ADR 004: Deploy the Web Frontend on Fly.io

**Status:** Accepted
**Date:** 2026-05-28

## Context

The web frontend ([`web.py`](../../web.py)) was built so we could share the game beyond a local terminal session. It now needs a stable public URL.

Constraints that shaped the choice:

- **In-memory game state.** `web.py` keeps the `_games` dict in process memory (see ADR 002). Any host that scales horizontally or recycles instances on demand silently breaks player runs.
- **Single small Python service.** Flask + gunicorn behind TLS. No database, no background workers, no static-asset CDN needs.
- **Hobby-scale traffic.** A handful of concurrent sessions at most, days between bursts. Cost matters; ops surface area matters more.
- **Solo developer, push-to-`main` workflow** (per CLAUDE.md).

## Decision

Deploy as a single Docker container on **Fly.io** in region `fra` (Frankfurt), running gunicorn with **one worker** and **`auto_stop_machines = "off"`** so the machine stays warm and the in-memory dict survives the way players expect.

Configuration shipped with this ADR:

- **[`Dockerfile`](../../Dockerfile)** — `python:3.12-slim`, install `requirements.txt`, `CMD gunicorn -w 1 -b 0.0.0.0:8080 web:app`. The single-worker constraint is documented inline; it is load-bearing because `_games` is a module-level dict.
- **[`fly.toml`](../../fly.toml)** — `primary_region = "fra"`, `auto_stop_machines = "off"`, `min_machines_running = 1`, `shared-cpu-1x` / 256MB. No volumes, no secrets, no Postgres.
- **[`.dockerignore`](../../.dockerignore)** — excludes tests, sim, docs, `__pycache__`, `.git`. Keeps the image small and avoids shipping non-runtime code.
- **[`requirements.txt`](../../requirements.txt)** — `gunicorn` added next to `flask`.

No CI/CD pipeline at this stage — deploys are manual `fly deploy` from a working tree (see "Deferred" below).

## Alternatives considered

- **Google Cloud Run / serverless containers.** Best free-tier economics, but request-driven instance spin-up and shutdown wipes the in-memory `_games` dict at random — would force the state externalization work (Redis / SQLite) before the game is ready for it.
- **Render free tier.** Sleeps after 15 min idle; cold start wipes runs. Same in-memory problem, just on a longer fuse. Acceptable but worse player UX than a warm Fly machine.
- **DigitalOcean / Hetzner $5 VM.** Maximum control, similar cost, but we'd own the OS, TLS renewal, restart policy, and gunicorn supervision. Operational cost outweighs the flexibility for this app.
- **GitHub Pages / Vercel / Netlify.** Static / edge hosts. Flask needs a real long-lived server process; Vercel's Python functions reimport per request and wipe state.

Fly.io wins on the specific combination we need: long-lived single instance, free-tier-friendly, container-based (so the runtime is identical to what we test locally), one command to deploy.

## Consequences

**Wins:**

- Public HTTPS URL at `https://hallucination-inc.fly.dev` with no certificate management.
- Same Docker image runs locally and on Fly — no "works on my machine" surface area.
- Easy to migrate later: the Dockerfile is portable to any container host if we outgrow Fly.

**Costs:**

- `auto_stop_machines = "off"` + `min_machines_running = 1` means we pay for an always-on machine instead of scaling to zero. At `shared-cpu-1x` / 256MB this still fits comfortably in Fly's free allowance for one app.
- The single-region / single-machine choice is a hard ceiling at ~one box's worth of concurrent sessions. Acceptable until the game finds an audience.

**Things to watch:**

- Every `fly deploy` restarts the machine, which wipes in-progress runs. Document this for players (or live with it) until state is externalized.
- Adding a second worker, a second machine, or moving to a scale-to-zero host all require the same prerequisite: move `_games` to an external store (Redis or a tiny SQLite table keyed by `hinc_sid`). Don't relax the single-worker rule without that work.
- If memory pressure shows up (unlikely at 256MB given the state shape), bump to 512MB before adding complexity.

## Deferred

- **CI/CD pipeline.** Not needed while one person deploys from one machine. The hook to add later is a `.github/workflows/deploy.yml` that runs `python3 run_tests.py` and then `flyctl deploy --remote-only` on pushes to `main`, using a `FLY_API_TOKEN` repo secret. Worth setting up when either (a) another contributor joins, (b) we want deploys to fire without local flyctl, or (c) we add a separate staging app.
- **State externalization.** See "Things to watch."
- **Custom domain.** `*.fly.dev` is fine for now; switch later via `fly certs add`.

## Related

- [ADR 002 — Game state](002-game-state.md) — the in-memory dict choice this deploy works around.
- [architecture.md](../architecture.md) — updated with a deployment section.
