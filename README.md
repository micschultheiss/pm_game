# Hallucination Inc.

Hallucination Inc. is a simple game that reimagines the Drug Wars economic loop for AI product management. Players have 30 in-game days to buy LLM tokens, craft AI SaaS products, sell them to enterprise and government clients, manage compounding debt, and avoid bankruptcy. The target audience is technically curious product managers, AI builders, and startup operators game fans who enjoy strategic resource optimization with a meme-forward AI industry theme.

> This project is one of my AI-assisted coding exercises — the design, code, and iteration loop were developed collaboratively with an AI coding assistant.

## Gameplay at a glance

- **30 in-game days** to turn $100,000 cash + $100,000 of debt into a profitable AI SaaS business. Pay the debt off before day 30 for a $75,000 debt-free bonus.
- **Buy tokens** (Code, Reasoning, Image, Voice, Video) from providers like Anthropic, OpenAI, Google, Meta, and Mistral. Each provider has its own quality tier and price curve, and prices jitter daily.
- **Craft products** (e.g. AI Customer Support, Compliance Dashboard, AI Security Scanner) using token recipes — higher-quality tokens yield higher-quality products, but cost more.
- **Sell** to rotating enterprise and government clients whose budgets and wants drift, drop, and appear over time.
- **Watch the clock**: debt compounds at 3% per day, products decay, and the market shifts under you.
- Each run **starts at a random provider** and opens with a full market-price grid so you can plan your first move with full information.

## Requirements

- Python 3.8+
- A terminal — for the terminal frontend
- (Optional) Flask — for the web frontend: `pip install -r requirements.txt`

## Run it

```bash
# Terminal frontend (default — standard library only)
python3 hallucination_inc.py

# Web frontend (Flask) — http://localhost:5000
pip install -r requirements.txt
python3 hallucination_inc.py --web
```

The terminal frontend runs entirely with text prompts. The web frontend
serves an HTML page that mirrors the terminal layout, with one game per
browser cookie. Override the port with `PORT=5050 python3 hallucination_inc.py --web`.

To expose the web frontend over the internet for ad-hoc sharing:

```bash
# In another terminal:
cloudflared tunnel --url http://localhost:5000
```

## Project structure

```
pm_game/
├── engine.py                     # pure game logic — state, actions, time, oracles
├── terminal.py                   # terminal frontend (ANSI UI, REPL)
├── web.py                        # Flask web frontend
├── templates/, static/           # web frontend assets
├── hallucination_inc.py          # entry point — dispatches terminal / --web
├── simulate.py                   # headless runner for balance / regression testing
├── test_engine.py                # unittest suite — engine logic
├── test_terminal.py              # unittest suite — terminal frontend
├── test_helpers.py               # shared test fixtures
├── run_tests.py                  # stdlib coverage runner (90% gate)
├── requirements.txt              # web-frontend dependencies (Flask)
├── scripts/
│   ├── pre-commit                # git hook source-of-truth
│   └── install-hooks.sh          # one-shot installer for fresh clones
├── README.md
├── CLAUDE.md                     # repo conventions for AI-assisted edits
├── TODO.md                       # working backlog
├── .github/
│   └── NOTES.md                  # running log of behaviour / decision changes
└── docs/
    ├── Hallucination_Inc_PRD.md  # canonical product requirements
    ├── architecture.md           # high-level architecture overview
    ├── game-design.md            # design notes and balance rationale
    └── adr/                      # architecture decision records
        ├── 001-tech-stack.md
        ├── 002-game-state.md
        └── 003-engine-frontend-split.md
```

The engine and terminal frontend stay stdlib-only; only the web frontend
adds a dependency. `simulate.py` plays headless games against several
policies (random / greedy / planner) and prints win-rate, bankruptcy, and
product-mix stats — used to validate any balance change.

## Tests

The test suite is `unittest`-based and uses only the Python standard library:

```bash
python3 run_tests.py           # tests + coverage gate (90% threshold)
python3 -m unittest -v         # just the tests, no coverage
```

`run_tests.py` measures line coverage with the stdlib `trace` module and an
AST-based denominator (`ast`). Current coverage: ~93% on `engine.py`, ~96%
on `terminal.py`. The web frontend isn't coverage-gated yet.

A pre-commit git hook runs the gate on every commit that touches Python files.
To enable it after a fresh clone:

```bash
./scripts/install-hooks.sh
```

Bypass the hook (rarely) with `git commit --no-verify`.

## Status

Playable end-to-end. Tuning, balancing, and additional events are ongoing.

## Author

Built by [Michael Schultheiss](https://github.com/micschultheiss) as an AI-assisted coding exercise.
