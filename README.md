# Code Wars

Code Wars is a simple game that reimagines the Drug Wars economic loop for AI product management. Players have 30 in-game days to buy LLM tokens, craft AI SaaS products, sell them to enterprise and government clients, manage compounding debt, and avoid bankruptcy. The target audience is technically curious product managers, AI builders, and startup operators game fans who enjoy strategic resource optimization with a meme-forward AI industry theme.

> This project is one of my AI-assisted coding exercises — the design, code, and iteration loop were developed collaboratively with an AI coding assistant.

## Gameplay at a glance

- **30 in-game days** to turn a starting balance of $35,000 (and $300,000 of debt) into a profitable AI SaaS business.
- **Buy tokens** (Code, Reasoning, Image, Voice, Video) from providers like Anthropic, OpenAI, Google, Meta, and Mistral. Each provider has its own quality tier and price curve.
- **Craft products** (e.g. AI Customer Support, and others) using token recipes — higher-quality tokens yield higher-quality products, but cost more.
- **Sell** to rotating enterprise and government clients whose budgets and wants drift, drop, and appear over time.
- **Watch the clock**: debt compounds at 2% per day, products decay, and the market shifts under you.

## Requirements

- Python 3.8+ (uses only the standard library — no `pip install` required)
- A terminal

## Run it

```bash
python3 pm_wars.py
```

The game runs entirely in the terminal with text prompts.

## Project structure

```
pm_game/
├── pm_wars.py         # the game
├── reqs/
│   └── PM_Wars_PRD.md # product requirements doc
└── README.md
```

## Status

Playable end-to-end. Tuning, balancing, and additional events are ongoing.

## Author

Built by [Michael Schultheiss](https://github.com/micschultheiss) as an AI-assisted coding exercise.
