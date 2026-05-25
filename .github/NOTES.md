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
