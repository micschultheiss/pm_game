# ADR 003: Split Engine from Terminal Frontend

**Status:** Accepted (Step 1 of a multi-step refactor)
**Date:** 2026-05-27

## Context

The game was a single file (`hallucination_inc.py`, ~1350 lines) that mixed:

1. Pure game logic — constants, state, action functions, time progression, the bankruptcy oracle.
2. Terminal presentation — ANSI codes, screen clearing, panel rendering, multi-step input menus, the blocking REPL.

A web frontend is planned. We didn't want two parallel implementations of the rules, and we didn't want either frontend to know about the other.

The seam was already there in the codebase — section comments (`# UI`, `# MENUS`, `# ACTIONS`) marked it, and `simulate.py` plus `test_hallucination_inc.py` only ever called the engine half. Making the seam structural was a small lift with an obvious payoff.

## Decision

Split into two modules:

- **`engine.py`** — all game logic. Imports `random` only. Exposes:
  - Tuning constants and catalog data (`PROVIDERS`, `PRODUCTS`, `ALL_CLIENTS`, `EVENTS`, `TOKEN_TYPES`, …).
  - `new_game()` returning a state dict.
  - Action functions `do_buy_tokens`, `do_craft`, `do_sell_product`, `do_travel`, `do_borrow`, `do_pay_debt` — each returns `(ok: bool, msg: str)` and mutates state in place. Messages are plain user-facing text, no ANSI codes.
  - `advance_days(state, days)` — the single time-progression entry point.
  - Query helpers: `token_total`, `token_free`, `token_avg_quality`, `net_worth`, `can_craft`, `borrow_limit`, `borrow_available`, `compute_market_demand`.
  - **End-condition oracles** (new in this split): `has_any_option`, `is_bankrupt`, `is_game_over`. Frontends call these to decide what to render; rendering stays in the frontend.

- **`hallucination_inc.py`** — terminal frontend. Imports `os` and `shutil` for terminal width / clearing, plus `from engine import *` for everything game-related. Holds: ANSI helpers, `header`, all `show_*` panels, `prompt_int/str`, all `menu_*` flows, `bankruptcy_screen`, `end_screen`, `game_loop`, `main`. This file is also still the entry point — `python3 hallucination_inc.py` continues to work.

State stays a plain dict, by ADR 002. Two fields are the documented hand-off between engine and frontend:

- `state["message"]` — the latest action result, written by engine, read + cleared by frontend.
- `state["last_event"]` — daily event banner, same contract.

## Transitional compatibility (resolved in step 3)

Initially `test_hallucination_inc.py` covered both engine and terminal symbols via `import hallucination_inc as g`, so `hallucination_inc.py` re-exported the engine surface (plus `_`-prefixed helpers) as a compatibility shim. **Step 3 of the split (commit on 2026-05-27) replaced that shim:** the test file split into `test_engine.py` and `test_terminal.py` — with shared fixtures in `test_helpers.py` — and they import the respective modules directly. `hallucination_inc.py` is now a 15-line launcher: `from terminal import main; main()`.

## Consequences

**Wins:**

- Web frontend can be added without copy-pasting any rule — it imports `engine` and renders state.
- `simulate.py` no longer routes through a UI module to reach the rules (it now `import engine as g`).
- Coverage gate in `run_tests.py` tracks both files; current coverage 91% engine / 95.5% terminal.
- The "single source of truth" boundary is now structural, not just a comment.

**Costs:**

- Two files where there was one. Slightly more navigation when reading the codebase end-to-end.
- The explicit private-symbol re-export list in `hallucination_inc.py` is a small carrying cost until tests target `engine` directly.

**Things to watch:**

- The CLAUDE.md convention now says "engine / frontend separation." New mechanics must go in `engine.py`, not the terminal file.
- Any new action that costs or produces resources still needs to be reflected in `has_any_option` (per ADR 002 / load-bearing mechanics).
- ANSI codes must stay confined to `hallucination_inc.py`. If a future engine change wants to add styled output, push the styling into the frontend instead.

## Related

- [ADR 001 — Tech stack](001-tech-stack.md)
- [ADR 002 — Game state](002-game-state.md)
- [architecture.md](../architecture.md) (updated)
