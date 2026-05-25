# ADR 001: Tech Stack — Python 3, Standard Library Only, Single File

**Status:** Accepted
**Date:** 2026-05-25

## Context

Hallucination Inc. is a small terminal game built as an AI-assisted coding exercise. The audience is technically curious PMs, AI builders, and operators — people likely to have a terminal and Python already installed, and likely to read or fork the code.

We needed to pick:

1. A language and runtime.
2. Whether to allow third-party dependencies.
3. Whether to split the implementation across multiple files / modules.

## Decision

- **Python 3.8+** as the language.
- **Standard library only** — no `pip install`, no `requirements.txt`, no virtualenv required.
- **Single file** (`pm_wars.py`) for the entire game.

## Rationale

- **Python is ubiquitous on the target audience's machines.** macOS and most Linux distros ship with a usable Python 3. Windows users typically have it from other tooling. A zero-install game is dramatically easier to share than one that requires a setup step.
- **No dependencies removes a whole class of friction.** No environment management, no version pinning, no supply-chain consideration. The game runs the same on day 1 and day 1000.
- **One file is shareable.** People can read it on GitHub in a single tab, fork it, paste it into a gist, or hand it to an LLM as context. That fits the project's "AI-assisted coding exercise" framing.
- **The terminal is the right surface.** A text UI matches the Drug Wars heritage, keeps the dev loop tight, and avoids GUI/web complexity that would dwarf the game logic.

## Consequences

**Positive**

- Anyone with Python 3 can run it with one command.
- No CI infrastructure needed for dependency management.
- The whole project fits in working memory.

**Negative**

- `pm_wars.py` is large (~50KB) and will keep growing if we add features. Navigation relies on section comments rather than module boundaries.
- We cannot use ecosystem niceties (rich terminal rendering, pydantic-style validation, hypothesis for testing).
- Cross-platform terminal behavior (ANSI escapes, input handling) has to be handled by hand.

## When to revisit

- If the file crosses ~3000 lines or section navigation gets painful, reconsider splitting into a small package.
- If we ever want a GUI, web, or mobile front-end, this ADR is moot for that surface.
- If we add features that genuinely need a dependency (e.g. a renderer that would take 500 lines to reimplement), revisit the stdlib-only rule for that specific case.
