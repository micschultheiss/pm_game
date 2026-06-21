# CLAUDE.md

Context for Claude Code when working in this repo.

## What this is

A Python terminal game (banner title "HALLUCINATION INC.") that reskins the Drug Wars economic loop for AI product management. Players buy LLM tokens from providers, craft SaaS products from recipes, and sell to enterprise/government clients before debt eats their runway.

The codebase is split into an **engine** (pure game logic) and **frontends** (presentation). The terminal is the only frontend today; a web frontend is planned and will reuse the same engine.

See [README.md](README.md) for how to run it and [docs/Hallucination_Inc_PRD.md](docs/Hallucination_Inc_PRD.md) for the full product spec.

## Layout

```
hallucination_inc.py  # entry point (root) — puts src/ on the path, dispatches to a frontend
                       # (terminal default, `--web` for Flask).
src/                  # program modules:
  engine.py           #   pure game logic — state, actions, time, oracles. No I/O. stdlib only.
  terminal.py         #   terminal frontend — ANSI UI, menus, prompts, REPL. stdlib only.
  web.py              #   Flask web frontend — HTTP server, HTML rendering, in-memory sessions.
  templates/, static/ #   Jinja2 templates + CSS for the web frontend.
tests/                # tests + tooling (all import src/ via _bootstrap.py):
  test_engine.py      #   engine logic
  test_terminal.py    #   terminal frontend
  test_web.py         #   Flask web frontend
  test_helpers.py     #   shared test helpers (state builders, stdout capture)
  _bootstrap.py       #   puts src/ on sys.path (imported first by tests + simulate)
  run_tests.py        #   coverage-gated test runner (tracks engine.py, terminal.py, web.py)
  simulate.py         #   headless runner used to balance/regression-test the loop
fly/                  # Fly.io deployment config (fly.toml, Dockerfile, .dockerignore)
requirements.txt      # web-frontend dependencies (Flask). Not needed for terminal or sim.
docs/                 # architecture, ADRs, game design notes, TODO.md backlog
docs/Hallucination_Inc_PRD.md   # canonical product requirements
```

Run terminal mode: `python3 hallucination_inc.py`.
Run web mode: `pip install -r requirements.txt && python3 hallucination_inc.py --web`
(serves on http://localhost:5050).
Run tests: `python3 tests/run_tests.py` (tests + coverage gate).

The launcher in the repo root puts `src/` on `sys.path`; tests and `simulate.py`
do the same via `tests/_bootstrap.py` (imported first, before `import engine`).

## Conventions

- **Python 3.8+.** `src/engine.py` and the terminal frontend use the standard library only — keep it that way so simulators and the terminal stay zero-install. Other frontends may add dependencies if they're worth it (the web frontend uses Flask). Document new deps in `requirements.txt`.
- **Engine / frontend separation.** All game logic lives in `src/engine.py`. Frontends import from it; they never reimplement rules. New mechanics go in `src/engine.py` first, then each frontend wires up its own UI for them.
- **Action functions return `(ok, msg)`.** The `msg` is plain user-facing text with no ANSI codes — frontends render it as-is. `state["message"]` and `state["last_event"]` are the documented hand-off: engine writes, frontends read + clear.
- **Tone is meme-y on purpose.** UI copy, event headlines, and end-game grades are written with PM/AI satire. Keep that register when adding events, clients, or end-screen text.

## Load-bearing mechanics — do not simplify

These exist for balance reasons. Removing or watering them down breaks the game.

- **Token quality is averaged on purchase** and flows through crafting. Provider choice has to matter.
- **Refactor soft cap** (`REFACTOR_SOFT_CAP = 0.20`) prevents cheap-token spam from trivializing quality.
- **`has_any_option` bankruptcy oracle** must stay in sync with every action that costs or produces resources. If it drifts, the game soft-locks instead of ending cleanly.
- **Partial client rotation + daily drift** keeps the client board fresh without full resets.

## When changing balance

Use `tests/simulate.py` to run headless games before/after a change. A change that shifts win rates, average net worth, or bankruptcy rate by a lot needs a deliberate justification — don't silently rebalance.

## Out of scope for now

- Networking, persistence, save files, multiplayer.
- GUI / web frontend.
- Adding dependencies.

## Git workflow
- After completing any task or subtask, commit with a conventional commit message
- Push to the current branch immediately after committing
- Do not wait to be asked

## Memory & docs maintenance

After completing any task that changes behaviour, architecture, or decisions:
- Update the backlog **in Linear** — Linear is the source of truth for the
  `pm_game` project (team Mics-playground). Check off / add / re-prioritise
  issues there, not in `docs/TODO.md`.
- `docs/TODO.md` is **generated** from Linear — do not hand-edit it. Regenerate
  with `python3 scripts/sync_todo_from_linear.py` (needs `LINEAR_API_KEY`; one-way
  Linear → file). `--check` exits non-zero on drift. See [ADR 007](docs/adr/007-linear-backlog-sync.md).
- Append to `.github/NOTES.md` with date + what changed and why
- If a new technical decision was made, create or update the relevant `docs/adr/`
- If architecture changed, update `docs/architecture.md`
