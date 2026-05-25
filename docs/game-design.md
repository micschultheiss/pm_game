# Game Design

The canonical product spec lives in [reqs/PM_Wars_PRD.md](../reqs/PM_Wars_PRD.md). This doc focuses on the *design intent* — why the loop is shaped the way it is.

## Pitch

Drug Wars, reskinned for the AI product-management bubble. You have 30 in-game days, a runway that compounds against you, and a market that won't stop moving. Source tokens, craft products, sell before the demand rotates, decide whether to pay down debt or take one more swing.

## The core loop

```
   ┌──────────────────────────────────────────────────┐
   │                                                  │
   ▼                                                  │
 Travel  ──▶  Buy tokens  ──▶  Craft product  ──▶  Sell to client
   │                                                  │
   │                                                  ▼
   │                                            Pay down debt
   │                                                  │
   └──────────────── time passes ◀────────────────────┘
                    (debt compounds,
                     events fire,
                     products decay,
                     clients drift)
```

Every player turn either spends cash, advances time, or both. Time is the scarce resource — not cash — because debt compounds and inventory decays.

## Pillars

### 1. Token quality is the spine

Each provider has a fixed quality rating (Anthropic 0.95, OpenAI 0.90, Google 0.70, Mistral 0.62, Meta 0.50). Token quality is averaged on purchase and flows through crafting. This is what makes provider choice matter and what makes the cheap-vs-premium tradeoff real.

### 2. Clients are quality-gated, with capped over-spec bonus

Clients pay `budget * (quality / min_quality)`, capped at **1.2×**. The cap is load-bearing: without it, over-engineering trivially prints money. With it, the player has to actually match supply to demand instead of always shipping the highest-quality build.

### 3. Refactor exists, with a soft cap

Refactor lets the player spend Code tokens to lift a finished product's quality. The soft cap is `refactor_pool_quality + 0.20`. This means cheap tokens can rescue a near-miss build but can't push a junk product to premium. Removing the cap collapses the strategy space.

### 4. Partial rotation, not hard resets

The active client board rotates partially — some clients stay, some leave, new ones appear — and budgets/wants drift daily. This keeps the board fresh without wiping the player's plan from under them.

### 5. Bankruptcy is an ending, not a soft-lock

If cash hits zero, the bankruptcy oracle checks whether *any* productive move remains. If not, the run ends with a screen rather than trapping the player. This is the safety rail that lets every other system be aggressive.

## End-game grades

Final net worth = cash − debt. Bands (and tone) are intentionally meme-y:

| Net worth | Grade |
|-----------|-------|
| $1M+ | Unicorn |
| $500K+ | Series A |
| $100K+ | Ramen Profitable |
| $0+ | Broke Even |
| < $0 | Bankrupt |

## Tone

UI copy, event headlines, and end-screen messages lean into PM/AI satire. "Vibe coding," "the vibes were NOT coding," EU AI Act shocks, investor margin calls, model deprecation decay. The satire is part of the product — keep the register when extending.

## What we are not building

- Multiplayer. Async or sync.
- Persistent campaigns or unlocks across runs.
- A GUI or web version.
- A tutorial mode — the UI teaches through clear labels and inline validation.
