# Architecture

## Overview

PM Wars is a single-process, single-file Python terminal game. The entire runtime — state, game loop, UI, and rules — lives in [pm_wars.py](../pm_wars.py). A separate [simulate.py](../simulate.py) drives the same rules headlessly for balance testing.

There is no server, no database, no save file, no network call. A run starts when you invoke `python3 pm_wars.py` and ends when the player quits, runs out of days, or goes bankrupt.

## Components

```
┌──────────────────────────────────────────────────────────┐
│                       pm_wars.py                         │
│                                                          │
│  ┌────────────┐   ┌─────────────┐   ┌────────────────┐   │
│  │  Constants │   │ Game state  │   │   Daily tick   │   │
│  │  (prices,  │──▶│  (cash,     │──▶│  (interest,    │   │
│  │  recipes,  │   │  inventory, │   │  decay, events,│   │
│  │  clients)  │   │  clients)   │   │  client drift) │   │
│  └────────────┘   └─────────────┘   └────────────────┘   │
│         │                │                   │           │
│         ▼                ▼                   ▼           │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Action handlers: buy / craft / refactor / sell /  │  │
│  │  travel / wait / pay debt / quit                   │  │
│  └────────────────────────────────────────────────────┘  │
│                          │                               │
│                          ▼                               │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Terminal UI: status panel, command prompt,        │  │
│  │  event headline, end-game screen                   │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

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

`simulate.py` imports `pm_wars` and runs N headless games with a scripted or random policy. It's used for balance work — comparing win/loss/bankruptcy distributions across rule changes — not as part of the player experience.

## Why this shape

- **One file, stdlib only.** Easy to read, easy to fork, easy to share. The whole project fits in a tab.
- **No persistence.** Every run is fresh. Removes a class of bugs and keeps the design pressure on the core loop.
- **One global tick.** Centralizing time progression is what makes the events / decay / drift mechanics composable. Splitting them out is the first thing that goes wrong when this kind of game grows.

See [adr/001-tech-stack.md](adr/001-tech-stack.md) and [adr/002-game-state.md](adr/002-game-state.md) for the decisions behind these choices.
