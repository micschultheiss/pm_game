# ADR 002: Game State — In-Memory, Single Tick Function, No Persistence

**Status:** Accepted
**Date:** 2026-05-25

## Context

PM Wars has a non-trivial amount of state per run: cash, debt, day counter, location, token inventory (with weighted quality per type), one active build, finished products, an active client board with drift, recent event headlines.

We needed to decide:

1. How that state is represented.
2. How time progression is coordinated across actions.
3. Whether to persist state between sessions.

## Decision

- **All state is in-memory** in plain Python data structures (dicts, lists, small dataclass-shaped dicts). No save files, no database, no JSON dump.
- **Time progression goes through a single daily-tick function.** Any action that advances time — travel, wait, crafting completion — calls the same tick, which applies interest, decay, events, and client drift in a fixed order.
- **No persistence between runs.** Quitting or finishing ends the run. Starting again starts fresh.

## Rationale

- **One tick function = one source of truth.** Events, decay, debt interest, and client drift all interact. If each action implemented its own time progression, drift between them would create balance bugs that are very hard to track. Centralizing the tick is the single most important structural decision in the codebase.
- **In-memory state is sufficient.** A run is short (30 in-game days, maybe 15–30 minutes of wall time). There is no value in surviving process restart.
- **No persistence keeps the design honest.** Every run starts from the same initial conditions. Balance, randomness, and player skill are the only variables. Adding save files would invite save-scumming and we'd have to design around it.
- **Plain dicts over classes.** The state is small enough that the indirection of classes/dataclasses doesn't earn its keep. Direct dict access keeps the code readable for someone reading top-to-bottom.

## Consequences

**Positive**

- New mechanics (a new event, a new decay rule) plug into the existing tick in one place.
- Run startup is instant — no migration, no schema check, no file IO.
- Easy to drive headlessly from [simulate.py](../../simulate.py) for balance testing: instantiate state, call actions, inspect the result.

**Negative**

- A crash mid-run loses the run. Acceptable given run length.
- The bankruptcy oracle (`has_any_option`) has to be kept in sync with every action that costs or produces resources. If a new action gets added and the oracle isn't updated, the game can soft-lock.
- No telemetry across sessions. If we ever want to study run distributions in the wild, we'd need to add opt-in local logging.

## When to revisit

- If runs ever grow past ~1 hour of play time, the no-save tradeoff starts to bite.
- If we add a campaign / progression system, persistence becomes mandatory.
- If the bankruptcy oracle becomes a recurring source of bugs, consider deriving "valid actions" from a declarative action registry instead of a hand-written check.
