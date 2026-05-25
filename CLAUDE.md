# CLAUDE.md

Context for Claude Code when working in this repo.

## What this is

A single-file Python terminal game (`pm_wars.py`, banner title "VIBE WARS") that reskins the Drug Wars economic loop for AI product management. Players buy LLM tokens from providers, craft SaaS products from recipes, and sell to enterprise/government clients before debt eats their runway.

See [README.md](README.md) for how to run it and [docs/PM_Wars_PRD.md](docs/PM_Wars_PRD.md) for the full product spec.

## Layout

```
pm_wars.py            # the entire game — one file, stdlib only
simulate.py           # headless runner used to balance/regression-test the loop
TODO.md               # working backlog
docs/PM_Wars_PRD.md   # canonical product requirements
docs/                 # architecture, ADRs, game design notes
```

## Conventions

- **Python 3.8+, standard library only.** No `pip install`, no external deps. Do not add any.
- **One file.** `pm_wars.py` is intentionally monolithic. Don't split it into a package unless the user asks — the single-file constraint is part of the project's character.
- **Tone is meme-y on purpose.** UI copy, event headlines, and end-game grades are written with PM/AI satire. Keep that register when adding events, clients, or end-screen text.

## Load-bearing mechanics — do not simplify

These exist for balance reasons. Removing or watering them down breaks the game.

- **Token quality is averaged on purchase** and flows through crafting. Provider choice has to matter.
- **Refactor soft cap** (`REFACTOR_SOFT_CAP = 0.20`) prevents cheap-token spam from trivializing quality.
- **`has_any_option` bankruptcy oracle** must stay in sync with every action that costs or produces resources. If it drifts, the game soft-locks instead of ending cleanly.
- **Partial client rotation + daily drift** keeps the client board fresh without full resets.

## When changing balance

Use `simulate.py` to run headless games before/after a change. A change that shifts win rates, average net worth, or bankruptcy rate by a lot needs a deliberate justification — don't silently rebalance.

## Out of scope

- Networking, persistence, save files, multiplayer.
- GUI / web frontend.
- Adding dependencies.

## Git workflow
- After completing any task or subtask, commit with a conventional commit message
- Push to the current branch immediately after committing
- Do not wait to be asked
