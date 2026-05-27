# Notes

Loose working notes for the project. Active backlog lives in [TODO.md](../TODO.md); long-form spec lives in [docs/Hallucination_Inc_PRD.md](../docs/Hallucination_Inc_PRD.md).

## Open questions

- Is 30 days the right run length, or should it flex to 45/60 with proportional debt?
- Do we want a deterministic seed mode for sharing "same-game" runs between players?
- Should the simulator ship a baseline policy report so balance changes have a reference number to move against?

## Things to watch for in PRs

- Any new action that spends cash or consumes inventory needs to be reflected in the bankruptcy oracle.
- Any new event needs to round-trip through the daily-tick sequence (interest → build → decay → event → drift → rotation).
- Tone of new UI copy — keep the meme-y register, don't drift into corporate.

## Parking lot

- "Sandbox mode" with debt off and infinite days, for poking at the economy.
- Per-provider event affinities (Anthropic-flavored events vs. Meta-flavored).
- A daily news ticker that surfaces multiple small events instead of one headline.

## Changelog

- **2026-05-27** — **Engine / frontend split, step 2.** Moved the terminal UI into its own `terminal.py` module. `hallucination_inc.py` is now a thin entry-point launcher (`from terminal import main; main()`) plus a transitional compatibility shim that re-exports both the engine and terminal surfaces so `import hallucination_inc as g` still works for the existing test suite. Dropped a stray duplicate `compute_market_demand` that ended up in both engine and terminal during step 1. `run_tests.py` `TARGET_FILES` now `["engine.py", "terminal.py"]` — the launcher is pure import-time glue and not meaningful to coverage-gate. 154 tests still pass; coverage 92.7% engine / 96.0% terminal. Next: split tests along the new module boundary.
- **2026-05-27** — **Engine / frontend split, step 1.** Extracted all game logic into a new `engine.py` (constants, EVENTS, state, time, actions, oracles). `hallucination_inc.py` is now the terminal frontend: UI helpers, prompts, menus, end screens, REPL. It pulls the engine surface in via `from engine import *` plus an explicit list of `_`-prefixed helpers so existing tests that go through `import hallucination_inc as g` keep working unchanged. Added `is_bankrupt(state)` and `is_game_over(state)` as pure oracles on the engine so future frontends don't reimplement the end-condition logic. `simulate.py` now imports `engine` directly (it was already engine-only). `run_tests.py` tracks coverage on both files; 154 tests pass, coverage 91% engine / 95.5% terminal. CLAUDE.md updated — the "one file" rule is gone, replaced with an engine/frontend separation convention.
- **2026-05-27** — Added `test_hallucination_inc.py` (154 unittest tests) and `run_tests.py`, a stdlib-only coverage runner (uses `trace` + `ast` for line accounting — no pip deps). Threshold is 90%; current coverage of `hallucination_inc.py` is 95.6%. The runner is wired into `.git/hooks/pre-commit` (with a versioned copy at `scripts/pre-commit` and an installer at `scripts/install-hooks.sh` so fresh clones can run `./scripts/install-hooks.sh` to enable the gate). Hook only fires when staged files include `.py` or test files. Bypass with `--no-verify`.
- **2026-05-25** — Renamed the game from "Code Wars" / "PM Wars" / "Vibe Wars" to **Hallucination Inc.** in all UI copy and docs. Then renamed `pm_wars.py` → `hallucination_inc.py` and `docs/PM_Wars_PRD.md` → `docs/Hallucination_Inc_PRD.md`.
- **2026-05-25** — Surfaced in-progress build on the inventory dashboard's `Products:` line (alongside completed products) so remaining build days are visible without scanning the header.
- **2026-05-25** — Made the game properly turn-based: every successful action (buy/sell/craft/travel/borrow/pay) now advances exactly one day. Replaced the multi-day `Wait` prompt with a single-day `Next` action, moved to the end of the menu. `do_*` functions now return `(ok, msg)` tuples so menus can gate the day-advance on success; `do_travel` no longer advances internally. Simulator `execute()` mirrors the new rules. Planner win-rate dropped 66.5% → 46.0% (median NW $341k → $41k) as a result — flagged in TODO as the next rebalancing pass.
- **2026-05-26** — Big rebalance pass driven by 10K-run simulations. Five changes shipped:
  - **V1**: `DEBT_INTEREST` 5% → 3%/day, plus `+$75K` debt-free completion bonus at end screen.
  - **V2**: Compliance Dashboard nerfed (base $240K → $200K, recipe expanded). Brand Asset Generator (3d→2d, lighter recipe), Marketing Copilot (4d→3d, $90K→$95K), AI Customer Support (3d→2d, $70K→$85K) all buffed for faster-flip strategies.
  - **V3**: Active client roster expanded 4 → 6 via new `ACTIVE_CLIENT_COUNT` constant. Three mid-tier clients added (TechCrunch Startups, Local Gov Council, Etsy) with ≤0.55 min_quality so cheap providers (Google/Meta/Mistral) become viable.
  - **V4**: Final-craft variance tightened 0.92-1.05 → 0.96-1.04, `QUALITY_BONUS_CAP` 1.2 → 1.5.
  - **V5**: New starting-bundle choice in `main()` before `game_loop`. `new_game()` now takes optional `bundle`/`specialty_provider` params. Three options: YC Demo Day (+$50K cash / -5 days), Bootstrap Loan (+$50K cash / +$50K debt), Specialty Partnership (25% lifetime discount at chosen provider). `do_travel` re-applies the specialty discount on arrival so price refresh doesn't wipe it.
  - **Outcomes (10K planner runs)**: median NW $35K → $169K (4.9×), win rate 44% → 58%, soft-lock bankruptcy 5.9% → 4.0%, strategy gap planner-vs-random $197K → $261K. Google visits 224 → 2,282 (10×). Open issues: Compliance Dashboard still dominant at 55% of builds, Brand Asset Generator still rarely chosen by the bot, Meta still unvisited by the planner (logged in TODO).
- **2026-05-26** — Second-pass rebalance focused on killing the Compliance Dashboard monoculture. Three changes:
  - **Compliance Dashboard further nerfed**: base $200K → $150K, craft_days 5 → 6, recipe expanded to {Reasoning: 150, Code: 80, Image: 30}.
  - **V5 starting bundles removed** (per user request — wasn't pulling its weight in sim and added pre-game friction). `new_game()` back to no-arg; `_choose_starting_bundle`/`_choose_specialty_provider`/`_apply_specialty_discount` deleted; `do_travel` no longer re-applies discount.
  - **Low-tier clients reworked**: "TechCrunch Startups" → "Basecamp" (productivity-tools SMB). All three (Basecamp, Local Gov Council, Etsy) now have distinct specialties and wider budget_mult ranges (1.0-1.5 / 0.8-1.6 / 1.1-1.8) so deals vary more. Etsy leans into Brand Asset Generator with 1.1-1.8 mult to give that product a real customer.
  - **Outcomes**: Compliance Dashboard share 55.0% → 17.8% (monoculture broken). Top product now AI Security Scanner at 26.4%; five products at ≥10% share. Google visits 2.3K → 6.5K (3×), Mistral now occasionally visited (185). Trade-off: planner median NW $169K → $100K, win rate 58% → 50% — accepted cost for strategic diversity. Bankruptcy stayed at 3.7%. Brand Asset Generator still rare (0.3%) due to structural scarcity in want lists, not bot strategy.
- **2026-05-26** — Third-pass rebalance, closing the two open items from pass 2:
  - **Meta provider rescued**: quality 0.50 → 0.55 so it can clear mid-tier 0.55 contracts after the 0.96 variance floor. Planner now visits Meta 181 times per 10K games (was 0).
  - **Brand Asset Generator buffed**: base $55K → $65K. Added BAG to Walmart and Salesforce want lists so its demand pool grows from 4 → 6 client templates. Planner build share 0.3% → 1.0% (3.3×).
  - **simulate.py planner buffer corrected**: the bot's safe-quality buffer was `/0.92` (pre-V4 variance) in two spots; updated to `/0.96` to match the actual variance floor. Bot now sources marginally cheaper, which mildly favors recipe-heavy products like Compliance Dashboard.
  - **Outcomes (10K planner runs)**: BAG sales 230 (was 70), Meta visits 181 (was 0), product diversity 5 → 6 products at ≥10% share. Side effect: Compliance share crept 17.8% → 25.9% (bot's cheaper sourcing favored its large recipe); still well below the 55% monoculture. Median NW $100K → $77K, win rate 50% → 46.6% — small regression within noise, accepted for the diversity gains. New open item: Mistral now eclipsed by Meta (cheaper across the board, same effective quality tier).
