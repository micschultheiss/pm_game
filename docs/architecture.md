# Architecture

## Overview

Hallucination Inc. is a Python game split across an engine and two peer frontends:

- **`engine.py`** — pure game logic (constants, state, actions, time, oracles). Standard library only. No I/O.
- **`terminal.py`** — the terminal frontend. ANSI-coloured UI, menus, prompts, blocking REPL. Standard library only.
- **`web.py`** — the web frontend. A small Flask app that maps HTTP requests onto engine actions and renders state as HTML. Uses Jinja2 templates in `templates/` and CSS in `static/`. Adds Flask as the project's only runtime dependency (see [`requirements.txt`](../requirements.txt)).
- **`hallucination_inc.py`** — entry point. A 15-line launcher that dispatches to `terminal.main()` by default and `web.main()` under `--web`.

A separate [simulate.py](../simulate.py) imports `engine` directly to drive headless games for balance testing.

The terminal frontend runs in-process; the web frontend boots Flask's dev server on `0.0.0.0:5050` (override via `PORT`) and keeps games in a module-level dict keyed by a cookie session id. Restarting the web server drops in-progress runs — there is no database, no save file. A run ends when the player quits, runs out of days, or goes bankrupt.

## Components

```
                       ┌──────────────────────────────┐
                       │     hallucination_inc.py     │
                       │        (entry point)         │
                       │                              │
                       │  default → terminal.main()   │
                       │  --web   → web.main()        │
                       │  ~15 lines total.            │
                       └──────────────┬───────────────┘
                                      │ dispatches to
                ┌─────────────────────┴─────────────────────┐
                ▼                                           ▼
   ┌─────────────────────────────┐         ┌─────────────────────────────┐
   │       terminal.py           │         │           web.py            │
   │   (terminal frontend)       │         │       (web frontend)        │
   │                             │         │                             │
   │  Header / panels / show_*   │         │  Flask routes              │
   │  prompt_int / prompt_str    │         │  /, /buy, /craft, /sell,    │
   │  menu_buy / craft / sell    │         │  /travel, /next,            │
   │  bankruptcy_screen          │         │  /borrow, /pay, /new        │
   │  end_screen / game_loop     │         │  Cookie session → state     │
   │  stdlib only.               │         │  Jinja2 templates + CSS     │
   └──────────────┬──────────────┘         └──────────────┬──────────────┘
                  │                                       │
                  └────────────────┬──────────────────────┘
                                   │ both import
                                   ▼
                  ┌────────────────────────────────┐
                  │           engine.py            │
                  │       (pure game logic)        │
                  │                                │
                  │  Constants ─▶ State ─▶ Tick    │
                  │  Actions: do_buy / craft /     │
                  │  sell / travel / borrow / pay  │
                  │  Events / drift / decay        │
                  │  Oracles: has_any_option,      │
                  │  is_bankrupt, is_game_over     │
                  │  stdlib only.                  │
                  └────────────────┬───────────────┘
                                   ▲
                                   │ also imported by
                                   │
                            ┌──────┴──────┐
                            │ simulate.py │  headless policy runner
                            └─────────────┘
```

## The engine ↔ frontend contract

- Action functions (`do_*`) return `(ok: bool, msg: str)` and mutate the state dict in place. The message is plain user-facing text — no ANSI codes — so any frontend can render it as-is.
- Two presentation hints live on the state: `state["message"]` for the most recent action result, `state["last_event"]` for the daily event banner. The engine writes, the frontend reads and clears.
- End-condition checks are pure-bool functions in the engine: `is_bankrupt(state)`, `is_game_over(state)`. The frontend owns the rendering of bankruptcy / game-over screens.
- Engine knows nothing about the frontend. Add new mechanics in `engine.py` first; then wire UI for them in each frontend.

## Key data shapes

- **Inventory** — tokens are tracked by type (Code / Reasoning / Image / Voice / Video) with a quantity in millions and a running weighted-average quality. Quality is recomputed on every purchase.
- **Finished products** — each carries its name, base product type, and final quality (a single float).
- **Active build** — at most one craft or refactor is in flight at any time. The build holds product type, days remaining, and the quality of the consumed token pool.
- **Clients** — an active board of 4 drawn from a larger pool. Each client has wants (product types), per-want budgets, and a minimum quality floor.

## The daily tick

Every action that advances time funnels through the same daily-tick sequence, in this order:

1. Advance day counter
2. Accrue debt interest
3. Progress the active build (or roll decay against it)
4. Apply shelf decay to finished products
5. Roll a random event (or surface a decay note as the headline)
6. Drift active clients (budgets shift, wants drop, new wants appear)
7. Occasionally rotate the active client roster

Keeping this in one place is why decay, events, and client drift stay consistent across travel, wait, and crafting completion.

## Bankruptcy oracle

`has_any_option` is the single source of truth for "can the player still do anything productive?" It checks whether the player can buy, craft, refactor, sell, or travel given current cash and inventory. If cash is at or below zero **and** the oracle returns false, the run ends with a bankruptcy screen rather than soft-locking.

Any new action that costs or produces resources has to be reflected in the oracle, or the game can soft-lock.

## Simulator

`simulate.py` imports `hallucination_inc` and runs N headless games with a scripted or random policy. It's used for balance work — comparing win/loss/bankruptcy distributions across rule changes — not as part of the player experience.

## Deployment

The web frontend ships as a single Docker container on **Fly.io**, region `fra`, running gunicorn with **one worker** so the in-memory `_games` dict stays consistent. Machines are pinned warm (`auto_stop_machines = "off"`, `min_machines_running = 1`) — scale-to-zero or multi-worker would wipe in-progress runs. Deploys run automatically via GitHub Actions ([`.github/workflows/fly-deploy.yml`](../.github/workflows/fly-deploy.yml)) on every push to `main`, and can also be triggered manually with `flyctl deploy`; either way the machine restarts, dropping any active sessions; this is acknowledged.

Configuration lives in [`fly/`](../fly): [`Dockerfile`](../fly/Dockerfile), [`fly.toml`](../fly/fly.toml), [`.dockerignore`](../fly/.dockerignore). The build context stays at the repo root so the Dockerfile's `COPY . .` can reach the app source, so deploys pass the config explicitly: `flyctl deploy --config fly/fly.toml --dockerfile fly/Dockerfile --ignorefile fly/.dockerignore .`. See [ADR 004](adr/004-deployment-flyio.md) for the rationale, alternatives, and the prerequisites for relaxing the single-instance constraint.

## Why this shape

- **One file, stdlib only.** Easy to read, easy to fork, easy to share. The whole project fits in a tab.
- **No persistence.** Every run is fresh. Removes a class of bugs and keeps the design pressure on the core loop.
- **One global tick.** Centralizing time progression is what makes the events / decay / drift mechanics composable. Splitting them out is the first thing that goes wrong when this kind of game grows.

See [adr/001-tech-stack.md](adr/001-tech-stack.md) and [adr/002-game-state.md](adr/002-game-state.md) for the decisions behind these choices.
