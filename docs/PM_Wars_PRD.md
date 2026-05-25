# Code Wars

### TL;DR

Code Wars is a simple game that reimagines the Drug Wars economic loop for AI product management. Players have 30 in-game days to buy LLM tokens, craft AI SaaS products, sell them to enterprise and government clients, manage compounding debt, and avoid bankruptcy. The target audience is technically curious product managers, AI builders, and startup operators game fans who enjoy strategic resource optimization with a meme-forward AI industry theme.

---

## Goals

### Business Goals

* Deliver a complete, replayable game
* Create a distinctive AI product-management themed game loop that is easy to share, fork, and demonstrate.
* Achieve high replayability through dynamic provider pricing, client rotation, random events, quality decay, and end-game grading.
* Preserve the intentionally meme-y tone and PM/AI satire as a core differentiator.
* Establish a clean, maintainable implementation that can support future expansions without breaking core mechanics.
* Make sure it is addictive

### User Goals

* Make interesting tradeoffs between cheap low-quality tokens and expensive high-quality tokens.
* Build and sell the right SaaS products before debt, market changes, or model decay destroy profitability.
* Understand current game state quickly.
* Experience a satisfying risk/reward loop with clear feedback after every action.
* Replay the game and discover new strategies across different client rosters, market events, and provider prices.

### Non-Goals

* 

---

## User Stories

Product Manager / Strategy Game Player

* As a player, I want to compare token prices and quality across providers, so that I can decide whether to optimize for margin or product quality.
* As a player, I want to craft different AI SaaS products from token recipes, so that I can pursue different market opportunities.
* As a player, I want to sell finished products to clients with different budgets and quality thresholds, so that I can maximize revenue.
* As a player, I want clear end-game grades, so that I understand how well I performed and want to replay.

AI Builder / Developer

* As a developer-player, I want understandable game mechanics, so that I can inspect, modify, or extend the game.
* As a developer-player, I want random events and economic variability, so that each run feels meaningfully different.

Casual Game Fan

* As a casual player, I want the interface to show my cash, debt, location, inventory, build status, and available actions, so that I can make decisions without memorizing hidden state.
* As a casual player, I want single-letter commands, so that turns are quick and frictionless.
* As a casual player, I want funny event copy and end-state messages, so that the experience feels playful rather than spreadsheet-like.

Maintainer / Future Contributor

* As a maintainer, I want core mechanics encoded clearly, so that future changes do not accidentally break balance-critical systems.
* As a maintainer, I want a reliable bankruptcy check, so that players cannot get trapped in a soft-lock.

---

## Functional Requirements

* Game Setup and Progression (Priority: P0)

  * New Game Initialization: Start each game with 30 days, $35,000 cash, $300,000 debt, 2% daily compounding interest, and no stored tokens or finished products.
  * End-Game Evaluation: At day 60 or quit, calculate final net worth as cash minus debt and assign a grade: Unicorn at $1M+, Series A at $500K+, Ramen Profitable at $100K+, Broke Even at $0+, and Bankrupt below $0.
  * Daily Time Tick: Advance the day counter, accrue debt interest, progress builds, apply decay, roll events, update clients, and rotate the roster in the correct sequence whenever time passes.
  * Bankruptcy Check: End the game only when cash is zero or below and no productive move is available.

* Provider and Token Economy (Priority: P0)

  * Provider Roster: Include Anthropic, OpenAI, Google, Meta, and Mistral with fixed quality ratings of 95%, 90%, 70%, 50%, and 62% respectively.
  * Token Types: Support Code, Reasoning, Image, Voice, and Video tokens, tracked in millions.
  * Dynamic Prices: Refresh provider prices on visit with roughly -30% to +40% variance from base prices and a $5 minimum floor.
  * Token Purchase: Allow players to buy tokens at the current provider, deduct cash, add inventory, and maintain average quality by token type.
  * Storage Limit: Enforce a total inventory cap of 500 million tokens.

* Product Crafting (Priority: P0)

  * Product Catalog: Support seven craftable products: AI Customer Support, Contract Analyzer, Brand Asset Generator, Compliance Dashboard, Training Video Platform, AI Security Scanner, and Marketing Copilot.
  * Recipes: Require the exact token mix, build days, and base values specified in the game specification.
  * Build Constraints: Allow only one active craft or refactor build at a time.
  * Quality Calculation: Set product quality as the weighted average of consumed token quality, with final build-day variance of plus or minus 5%.
  * Build Completion: Move completed products into finished inventory with name, quality, and base product type.

* Clients and Selling (Priority: P0)

  * Active Client Board: Maintain 4 active clients selected from a pool of 10 enterprise and government templates.
  * Client Wants: Randomize active wants and budgets based on client templates when a client appears.
  * Client Quality Floors: Enforce minimum product quality before sale.
  * Contract Revenue: Calculate sale revenue as contract budget multiplied by product quality divided by client minimum quality, capped at a 1.2x quality bonus.
  * Product Consumption: Remove the sold product from inventory and remove that want from the client after a successful sale.
  * Client Drift: Each day, allow budgets, wants, and active client roster to change according to specified probabilities.

* Random Events and Decay (Priority: P0)

  * Event Roll: Apply approximately a 30% daily chance of a random event.
  * Event Categories: Include provider price shocks, client demand shocks, cash hits or bonuses, and production hazards.
  * In-Progress Decay: Apply recipe-size-scaled quality decay to active builds with approximately 5% base daily chance.
  * Shelf Decay: Apply recipe-size-scaled quality decay to finished products with approximately 3% base daily chance.
  * Event Messaging: Surface the random event or, if no event fires, the most relevant decay note as the day headline.

* Refactoring (Priority: P1)

  * Refactor Finished Product: Allow players to spend Code tokens to improve finished product quality.
  * Refactor Cost: Roll Code token cost between 70% and 120% of the original recipe's total token count.
  * Refactor Lift: Apply a flat 4% lift plus 70% of the positive gap between Code token quality and current product quality.
  * Refactor Caps: Enforce soft cap of refactor Code quality plus 20% and hard cap of 99% quality.
  * Refactor Refusal: Refuse refactors when projected lift is under 1% and explain that better tokens are needed.

* Player Actions and Controls (Priority: P0)

  * Buy Tokens: Let the player buy token quantities at provider locations.
  * Sell Product: Let the player sell eligible finished products at client locations.
  * Craft Product: Let the player start a product build when inventory satisfies the recipe.
  * Refactor Product: Let the player start a refactor build when eligible.
  * Travel: Let the player travel to any provider or client for $30,000 and 1 day.
  * Wait: Let the player wait 1 to 5 days.
  * Pay Debt: Let the player pay any positive cash amount toward outstanding debt.
  * Quit: Let the player exit and view the end-game result.

---

## User Experience

Entry Point & First-Time User Experience

* The first screen introduces the premise: the player is a vibe-coding Senior PM trying to turn AI tokens into SaaS contracts before debt compounds into bankruptcy.
* The game explains the starting state: 30 days, $35,000 cash, $300,000 debt, and 2% daily debt interest.
* The player sees the current location, initial provider or client state, inventory, active client roster, and command shortcuts.
* No lengthy tutorial is required; the interface should teach through clear labels, action validation, and helpful error messages.

Core Experience

* Step 1: Assess current state.

  * The player reviews cash, debt, net worth, day count, location, token inventory, finished products, active build, and recent event messages.
  * The UI should make bankruptcy risk and storage usage highly visible.
  * The command bar should only show actions that are valid or explain why actions are unavailable.

* Step 2: Buy tokens from an LLM provider.

  * At a provider location, the player sees token prices by type and the provider's quality profile.
  * The player chooses token type and quantity.
  * The game validates cash, storage capacity, and quantity.
  * After purchase, the game updates cash, storage, and weighted average token quality.

* Step 3: Travel between providers and clients.

  * The player can move to another provider or client for $30,000 and 1 day.
  * On arrival at a provider, prices refresh.
  * The game applies the daily tick during travel, including interest, decay, events, and client updates.
  * If the player cannot afford travel, the game blocks the action unless another productive move exists.

* Step 4: Craft a SaaS product.

  * The player selects a product from the recipe catalog.
  * The game validates required token inventory and confirms build duration.
  * The game consumes recipe tokens immediately and starts the build.
  * The active build panel shows product name, days remaining, and current quality estimate.
  * Each passing day may damage the build through decay.

* Step 5: Complete and manage finished products.

  * On completion, the product receives final quality variance and moves to finished inventory.
  * Finished products can decay while sitting on the shelf.
  * The player can decide whether to sell quickly, wait for a better client, or refactor for higher quality.

* Step 6: Sell to a client.

  * At a client location, the player sees requested products, budgets, and minimum quality requirements.
  * The player selects an eligible finished product to sell.
  * The game validates that the client wants the product and that quality meets the minimum.
  * Revenue is calculated using the quality bonus formula and capped at 1.2x.
  * The sold product and fulfilled client want are removed.

* Step 7: Pay down debt or continue risk-taking.

  * The player can use cash to reduce debt and lower future compounding pressure.
  * The decision should feel strategic: paying debt improves survival, while holding cash funds token purchases and travel.

* Step 8: Reach the end state.

  * The game ends at day 60, by quit action, or by bankruptcy.
  * The final screen shows cash, debt, net worth, grade, and a tone-consistent summary message.

Advanced Features & Edge Cases

* If no random event fires but decay occurred, show decay as the headline so the player understands why quality changed.
* If a client drops a want that the player was targeting, the roster should update clearly and not silently invalidate strategy.
* If the player tries to refactor with low-quality Code tokens and projected lift is under 1%, refuse with a clear explanation.
* If cash reaches zero or below, the bankruptcy oracle must check every productive move before ending the game.
* If multiple products or clients match a sale condition, the UI should let the player choose rather than auto-select.
* If storage is full, token purchase should be blocked with a clear storage-cap message.

---

## Narrative

You are a vibe-coding Senior Product Manager with a dangerous amount of confidence, $35,000 in cash, and $300,000 of debt compounding at 2% per day. The market is moving fast: Anthropic is premium, Meta is cheap, Google is flooding the zone, and every enterprise client wants AI yesterday as long as it passes procurement. Your job is to arbitrage the chaos.

Each day, you decide where to spend scarce cash and time. You can buy cheap tokens and ship fast, but low-quality ingredients may fail government quality floors. You can overpay for premium tokens and chase big contracts, but debt compounds while builds decay and client priorities shift. A Compliance Dashboard might be worth a fortune after an EU AI Act shock, or it might sit on the shelf long enough to become yesterday's model wrapper.

Code Wars turns AI hype into a compact strategy loop: source tokens, craft products, refactor when quality is close, sell before demand rotates away, and decide whether to pay down debt or take one more risky swing. At the end of 30 days, the market renders judgment. Maybe you become a Unicorn. Maybe you scrape into Ramen Profitable. Or maybe the vibes were not coding.

---

## Success Metrics

### User-Centric Metrics

* First-run completion rate: Percentage of players who reach an end-game screen rather than abandoning mid-run.
* Replay rate: Percentage of players who start a second run after finishing one game.
* Average decisions per session: Number of meaningful player actions taken before exit.
* Strategy diversity: Distribution of products crafted, providers used, and clients sold to across completed runs.
* Player comprehension: Qualitative feedback indicating players understand why they won, lost, or went bankrupt.

### Business Metrics

* Shareability: Number of GitHub stars, forks, downloads, or direct shares if distributed publicly.
* Activation: Percentage of users who successfully run the game
* Retention proxy: Percentage of users who play more than one full game in a session.
* Expansion signal: Number of requests or contributions for new events, clients, products, or modes.

### Technical Metrics

* Crash-free sessions: Target near-zero unhandled exceptions during normal gameplay.
* Soft-lock rate: Zero known soft-locks from bankruptcy or invalid action states.
* Turn latency: UI redraw and action processing should feel instantaneous.
* State integrity: No negative token quantities, impossible products, invalid client wants, or broken debt calculations.

### Tracking Plan

* Since the initial version is local and dependency-free, tracking should be implemented as optional local session summaries rather than external analytics.
* Track game start and game end with final day, grade, cash, debt, and net worth.
* Track action counts by type: buy, sell, craft, refactor, travel, wait, pay debt, quit.
* Track products crafted, products sold, and products lost to decay or unsold inventory.
* Track provider purchase volume by token type and average quality.
* Track random event frequency and event category distribution.
* Track bankruptcy reasons and whether the bankruptcy oracle found no productive moves.