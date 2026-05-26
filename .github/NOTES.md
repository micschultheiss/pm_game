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
