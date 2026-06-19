# TODO

Working backlog. Active items live here; longer-form requirements live in [docs/Hallucination_Inc_PRD.md](docs/Hallucination_Inc_PRD.md).

## Now

- [x] Fix splash not dismissing on Apple-trackpad two-finger tap — the title splash only listened for `click`, so a secondary/right click (`contextmenu`/`auxclick`, no `click`) left it up, looking like "Start did nothing". `welcome.html` now dismisses on `pointerdown` + `contextmenu` (preventDefault) as well; verified all pointer paths in the preview browser. 190 tests pass.
- [x] Add a Quit button to the web frontend — `/quit` ends the run by forcing `state.day = MAX_DAYS+1`, reusing the existing GAME OVER screen to lock in the final score
- [~] Rework Mobile Web Screens — game screen now fits on one phone screen: Market + Open Contracts are `<details>` disclosures that collapse to a one-line glance value on mobile (open + inert on desktop), so status, inventory and the full action menu sit above the fold. Spacing tightened, no font shrink. Briefing screen still TODO.
- [ ] Tweak Desktop Web Version
- [~] Add keyboard Support in the browser — ENTER now advances briefing→game and advances the day (done); more shortcuts (action hotkeys) still open
- [ ] Add mobile/tap support
- [ ] Add a similar splash screen to the terminal version

## Next

- [ ] debt free bonus is 100k - find a nice rectification for it
- [ ] Add one or two new event categories (e.g. open-source model release, hiring freeze)
- [ ] Surface why a productive move is unavailable when bankruptcy fires
- [ ] Brand Asset Generator still uneconomical — despite the buff, only 15 builds (0.6% share) across 1000 planner runs. 100% conversion when built, so demand is fine; recipe economics still don't compete. Try: lower Code requirement, raise base value, or add a higher-tier client to its wants list.
- [ ] Compliance Dashboard drift/decay — 24% of planner builds but only 52% conversion across 1000 runs. The 6-day build outpaces drift/decay; half end up unsellable. Options: shorten craft_days to 5, lower decay sensitivity for slow products, or split into two cheaper variants.
- [ ] Check token prices and software prices ratios and align with real world numbers

## Later / ideas

- [ ] Optional local session summary file for tracking runs
- [ ] End-of-run "what if" replay showing the best missed move
- [ ] Think about different pricing models like yearly licences, seat based pricing etc
- [ ] Externalize `_games` to Redis or SQLite so deploys / multi-worker / scale-to-zero stop wiping in-progress runs

## Done

- [x] CI/CD pipeline — `.github/workflows/ci.yml` runs `test → deploy-staging → deploy-prod`; prod ships only on a green test run + a healthy `hallucination-inc-staging` deploy. Replaces the ungated `fly-deploy.yml`. See [ADR 006](adr/006-ci-cd-pipeline.md). Follow-up: ensure `FLY_API_TOKEN` is org-scoped so the staging job can deploy.
- [x] ENTER advances the screen in the web frontend — on the briefing, ENTER submits "Start the run" (guarded so it doesn't fire while the boot splash is still up, where ENTER dismisses the splash instead); on the game screen, ENTER submits "Next day", but only when focus isn't in a form control so ENTER still natively submits Buy/Sell/Craft/Travel/Borrow/Pay. Pure presentation in `welcome.html` / `game.html`; verified both paths via the preview browser. 194 tests pass.
- [x] Add the boot-sequence title splash before the briefing — vendored the design's framework-free `hallu-engine.js` into `src/static/`; `welcome.html` mounts it into a full-screen `#splash` overlay (locked Glitch config: boot log → ASCII column-sweep reveal → tagline + blinking prompt + mock copyright). Enter/click/tap dismisses it to the briefing; scroll-locked while up; degrades gracefully with JS off. Softened the chromatic split (±2px desktop / ±1px mobile) and sized the wordmark `clamp(7px,1.9vw,26px)` so it fits every viewport. Verified desktop + mobile via the preview browser. 190 tests still pass. See [ADR 005](adr/005-web-visual-design.md) "Follow-up — title splash".
- [x] Reskin the web frontend to the Claude Design "Glitch terminal" direction — ported the handoff bundle (`Hallucination Inc Game Screens.html`): briefing screen (`welcome.html`) and game screen Option A "Terminal Classic" (`game.html`) rebuilt against `game.css`'s design tokens; new `src/static/style.css` design system; CSS chromatic glitch wordmark; color-coded recipe chips (Co/Re/Im/Vo/Vi) via a new `_recipe_chips` view helper. Mobile-friendly via real CSS media queries (replacing the design's JS-toggled `.g-mobile`); dense tables scroll horizontally on phones. End/bankruptcy screens restyled in the new palette. 190 tests pass, web coverage 100%. See [ADR 005](adr/005-web-visual-design.md).
- [x] Restructure repo: program modules → `src/` (engine, terminal, web, templates, static), tooling → `tests/` (run_tests, simulate), backlog → `docs/TODO.md`. Only the launcher stays in root (plus README/CLAUDE). `src/` reaches the import path via the launcher and `tests/_bootstrap.py`; Dockerfile gunicorn uses `--pythonpath src`; pre-commit runs `python3 tests/run_tests.py`. 190 tests pass, coverage unchanged.
- [x] Move deployment config into a `fly/` directory — `fly.toml`, `Dockerfile`, `.dockerignore` relocated via `git mv`; build context stays at repo root and the Actions workflow passes `--config/--dockerfile/--ignorefile` flags; `.dockerignore` + docs updated. `flyctl config validate` passes.
- [x] Move the test suite into a `tests/` directory — relocated `test_engine.py`, `test_terminal.py`, `test_web.py`, `test_helpers.py` via `git mv`; `run_tests.py` discovers `tests/` and pins `PROJECT_ROOT` on `sys.path`; pre-commit pattern + docs updated. 190 tests pass, coverage unchanged.
- [x] Add smoke tests for `web.py` — `test_web.py` covers the welcome → game flow, each action route round-trip + validation branches, `/new` reset, the stale-session bailout, every view helper, and both end screens. Added to the coverage gate; 100% on 208 stmts. Total suite now 190 tests.
- [x] Publish the web frontend on Fly.io (`hallucination-inc.fly.dev`) — first `fly launch` + `fly deploy` ran against the config from [ADR 004](docs/adr/004-deployment-flyio.md) (Dockerfile + fly.toml, region fra, single warm machine).
- [x] Wire GitHub Actions deploy pipeline — [.github/workflows/fly-deploy.yml](.github/workflows/fly-deploy.yml) runs `flyctl deploy --remote-only` on every push to `main`.
- [x] Step 4 of engine split — `web.py` Flask frontend reusing the engine. Routes for buy/craft/sell/travel/next/borrow/pay/new; in-memory state keyed by a cookie session id; Jinja2 template + CSS that mirror the terminal layout (banner, market grid, contracts table, action menu). `python3 hallucination_inc.py --web` dispatches into it; default still runs the terminal. Engine and terminal stay stdlib-only — Flask is the only project dep, pinned in `requirements.txt`. Smoke-tested end to end via Flask dev server + curl.
- [x] Step 3 of engine split — split `test_hallucination_inc.py` into `test_engine.py` (engine logic) + `test_terminal.py` (UI), with shared fixtures in `test_helpers.py`. Tests now import `engine` / `terminal` directly. `hallucination_inc.py` shed its re-export shim and is now a 15-line launcher (`from terminal import main; main()`). 154 tests still pass; coverage unchanged (92.7% engine, 96.0% terminal).
- [x] Step 2 of engine split — UI moved into its own `terminal.py`; `hallucination_inc.py` is now a thin entry-point launcher plus a transitional compat shim for `import hallucination_inc as g`. Dropped a stray duplicate `compute_market_demand` that lived in both engine and terminal. Coverage gate now tracks `engine.py` + `terminal.py` (the launcher is pure import-time glue, not worth gating). 154 tests still pass; coverage 92.7% engine, 96.0% terminal.
- [x] Step 1 of engine split — extracted `engine.py` (pure logic), kept `hallucination_inc.py` as terminal frontend re-exporting engine surface for test compatibility. Added `is_bankrupt` / `is_game_over` oracles. simulate.py now imports `engine` directly. 154 tests still pass; coverage 91% engine, 95.5% terminal.
- [x] Add unit tests + 90% stdlib coverage gate wired into pre-commit (current: 95.6% on hallucination_inc.py, 154 tests)
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
