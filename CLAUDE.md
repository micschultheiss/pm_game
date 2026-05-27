# CLAUDE.md

Context for Claude Code when working in this repo.

## What this is

A Python terminal game (banner title "HALLUCINATION INC.") that reskins the Drug Wars economic loop for AI product management. Players buy LLM tokens from providers, craft SaaS products from recipes, and sell to enterprise/government clients before debt eats their runway.

The codebase is split into an **engine** (pure game logic) and **frontends** (presentation). The terminal is the only frontend today; a web frontend is planned and will reuse the same engine.

See [README.md](README.md) for how to run it and [docs/Hallucination_Inc_PRD.md](docs/Hallucination_Inc_PRD.md) for the full product spec.

## Layout

```
engine.py             # pure game logic — state, actions, time, oracles. No I/O.
terminal.py           # terminal frontend — ANSI UI, menus, prompts, REPL.
hallucination_inc.py  # entry point — dispatches to a frontend (terminal today, web later).
simulate.py           # headless runner used to balance/regression-test the loop
test_engine.py        # unittest suite for engine logic
test_terminal.py      # unittest suite for terminal frontend
test_helpers.py       # shared test helpers (state builders, stdout capture)
run_tests.py          # coverage-gated test runner (tracks engine.py + terminal.py)
TODO.md               # working backlog
docs/Hallucination_Inc_PRD.md   # canonical product requirements
docs/                 # architecture, ADRs, game design notes
```

Run with `python3 hallucination_inc.py` (the canonical entry point) or
`python3 -m terminal` if you want to skip the launcher.

## Conventions

- **Python 3.8+, standard library only.** No `pip install`, no external deps. Do not add any.
- **Engine / frontend separation.** All game logic lives in `engine.py`. Frontends import from it; they never reimplement rules. New mechanics go in `engine.py` first, then each frontend wires up its own UI for them.
- **Action functions return `(ok, msg)`.** The `msg` is plain user-facing text with no ANSI codes — frontends render it as-is. `state["message"]` and `state["last_event"]` are the documented hand-off: engine writes, frontends read + clear.
- **Tone is meme-y on purpose.** UI copy, event headlines, and end-game grades are written with PM/AI satire. Keep that register when adding events, clients, or end-screen text.

## Load-bearing mechanics — do not simplify

These exist for balance reasons. Removing or watering them down breaks the game.

- **Token quality is averaged on purchase** and flows through crafting. Provider choice has to matter.
- **Refactor soft cap** (`REFACTOR_SOFT_CAP = 0.20`) prevents cheap-token spam from trivializing quality.
- **`has_any_option` bankruptcy oracle** must stay in sync with every action that costs or produces resources. If it drifts, the game soft-locks instead of ending cleanly.
- **Partial client rotation + daily drift** keeps the client board fresh without full resets.

## When changing balance

Use `simulate.py` to run headless games before/after a change. A change that shifts win rates, average net worth, or bankruptcy rate by a lot needs a deliberate justification — don't silently rebalance.

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
- Update `TODO.md` — check off done items, add newly discovered tasks
- Append to `.github/NOTES.md` with date + what changed and why
- If a new technical decision was made, create or update the relevant `docs/adr/`
- If architecture changed, update `docs/architecture.md`
