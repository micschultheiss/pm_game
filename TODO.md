# TODO

Working backlog. Active items live here; longer-form requirements live in [docs/Hallucination_Inc_PRD.md](docs/Hallucination_Inc_PRD.md).

## Now

- [ ] Add proper unit tests and test coverage as a pre-commit mechanics
- [ ] Refactor and structure the app, different modules, e.g. engine and representation layer to preempt 2nd frontend

## Next

- [ ] Add one or two new event categories (e.g. open-source model release, hiring freeze)
- [ ] Surface why a productive move is unavailable when bankruptcy fires
- [ ] Brand Asset Generator still uneconomical — despite the buff, only 15 builds (0.6% share) across 1000 planner runs. 100% conversion when built, so demand is fine; recipe economics still don't compete. Try: lower Code requirement, raise base value, or add a higher-tier client to its wants list.
- [ ] Compliance Dashboard drift/decay — 24% of planner builds but only 52% conversion across 1000 runs. The 6-day build outpaces drift/decay; half end up unsellable. Options: shorten craft_days to 5, lower decay sensitivity for slow products, or split into two cheaper variants.
- [ ] Check token prices and software prices ratios and align with real world numbers

## Later / ideas

- [ ] Optional local session summary file for tracking runs
- [ ] End-of-run "what if" replay showing the best missed move
- [ ] Think about different pricing models like yearly licences, seat based pricing etc

## Done

- [x] Make empty enter the next turn
- [x] Rebalance the game mechanics (planner win 44% → 58%, median NW $35K → $169K after 5-variant pass)
- [x] Sort the travel destinations (customers as on the customer list)
- [x] Randomize starting provider — each run opens at a different lab
- [x] Show full provider price grid consistently — always on the dashboard and at the top of the travel menu (peer to the open-contracts board)
- [x] Widen lower-tier price variance — dropped the $5 floor that was flatlining Google/Mistral/Meta to a uniform $5
- [x] Tune debt interest vs. starting cash after recent rebalance (5% → 3% + debt-free bonus)
- [x] Buff Brand Asset Generator — added to Walmart/Salesforce wants, base value $55K → $65K (share 0.3% → 1.0%)
- [x] Rescue Meta provider — quality 0.50 → 0.55 (now visited 181 times in 10K planner games)
- [x] ~~Rescue Mistral provider~~ — resolved by the price-variance fix; 1000-run planner sim shows Mistral 173 visits vs. Meta 108, so Mistral is no longer eclipsed
- [x] More client templates (mid-market, agency, startup) — added TechCrunch Startups, Local Gov Council, Etsy
