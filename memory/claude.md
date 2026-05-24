# Code Wars — Project Summary

A single-file terminal game (`pm_wars.py`) inspired by Drug Wars,
reskinned as a vibe-coding PM hustle. The player has 30 days to turn
$35K cash and $300K debt (2%/day compounding interest) into a real
business before bankruptcy.

## Core Loop
- Travel between 5 **LLM providers** (Anthropic, OpenAI, Google, Meta,
  Mistral) and 4 active **clients** rotated from a pool of 10
  (Enterprise + Government).
- **Buy tokens** (Code, Reasoning, Image, Voice, Video) by the million.
  Each provider has its own quality tier and noisy daily prices.
- **Craft** one of 7 SaaS products from token recipes (3-6 days).
  Output quality = weighted avg of token quality consumed.
- **Refactor** finished products with Code tokens to lift quality
  (capped — cheap tokens have limited reach).
- **Sell** to clients whose `current_wants` match — quality must clear
  their `min_quality` threshold; over-spec earns a bonus up to 1.2x.

## Key Systems
- **Events** (~30%/day): provider price spikes/crashes, client budget
  shifts, AI winter, breaches, viral apps, craft setbacks, token decay.
- **Client drift**: daily chance to shift budgets, drop wants, or add
  new ones. Full partial-rotation every 3-7 days.
- **Decay risk**: bigger recipes = higher daily chance of quality
  drops during craft AND while products sit unsold.
- **Bankruptcy check**: triggers when cash ≤ 0 AND no productive move
  exists (can't buy, craft, refactor, sell, or travel).

## Economy Constants
- Starting: $35K cash, $300K debt, 30-day window
- Travel: $30K + 1 day per trip
- Storage cap: 500M tokens
- Debt interest: 2%/day compounding

## End Grades (by net worth)
- $1M+ → Unicorn (IPO)
- $500K+ → Series A
- $100K+ → Ramen Profitable
- $0+ → Broke Even
- < $0 → Bankrupt

## File Layout
- `pm_wars.py` — entire game (constants, state, actions, UI, loop)
- `README.md` — top-level pitch
- `reqs/` — design docs / PRD
