# ADR 005 — Web frontend visual design: the "Glitch terminal" direction

Status: Accepted · 2026-05-29

## Context

The web frontend (`src/web.py` + `templates/` + `static/style.css`) shipped with a
functional but plain dark-terminal stylesheet. A visual design was commissioned via
Claude Design (claude.ai/design) and delivered as an HTML/CSS/JS handoff bundle. The
chat transcript shows the user iterating through five title-screen directions, locking
**Option 3 — "Hallucinated Glitch"** (RGB chromatic split, teal accent, near-black,
magenta hits), then choosing **game-screen Option A — "Terminal Classic"** (dense data
tables, bracket `[ Buy ]` actions) over the Panel-HUD and Card-Deck alternatives. The
primary handoff file, `Hallucination Inc Game Screens.html`, composes two screens: the
**briefing/lore** screen and the **game** screen.

The bundle is a React + Babel prototype. The handoff README is explicit: recreate the
*visual output* in whatever technology fits the target codebase; don't copy the
prototype's internal structure.

## Decision

Recreate the design natively in the existing Flask + Jinja2 + CSS stack rather than
adopting React.

- **`src/static/style.css`** is rewritten as the design's glitch-terminal system,
  porting the design tokens and component vocabulary from the bundle's `game.css`
  (palette, `.g-*` classes, chromatic `.g-glitch` wordmark, tables, chips, action dock,
  intro/briefing, end screens).
- **`welcome.html`** mirrors the design's `IntroScreen` (briefing): eyebrow, glitch
  wordmark, lede, three stat tiles, "the basics / your job / good to know" blocks, and
  the blinking start prompt. All numbers stay bound to engine constants
  (`MAX_DAYS`, `DEBT_FREE_BONUS`, `TRAVEL_COST`, `MAX_TOKENS`, `ACTIVE_CLIENT_COUNT`).
- **`game.html`** mirrors the design's `OptA` (Terminal Classic): glitch status bar,
  inventory line, market table (current provider highlighted), open-contracts table with
  GOV/ENT tags and color-coded recipe chips, and the action dock. The existing CSS-tabs
  action machinery and every functional form (Buy/Sell/Craft/Travel/Borrow/Pay/Next)
  are preserved and restyled — the design's buttons were static mockups.
- **`web.py`** gains a `_recipe_chips` view helper so recipes render as individually
  colored chips (Co/Re/Im/Vo/Vi) like the design's `<Recipe>` component, alongside the
  existing `_recipe_short` string used elsewhere.

### Responsiveness

The design toggled a `.g-mobile` class from JavaScript (the design canvas knew the
artboard width). A server-rendered page has one DOM and no width knowledge, so the
mobile variants are reimplemented as real CSS `@media (max-width: 640px)` rules: padding
shrinks, the status bar wraps, action buttons go full-width, and forms stack. The dense
Terminal-Classic tables scroll horizontally inside a `.g-scroll` wrapper on narrow
screens rather than reflowing into a separate card DOM — this keeps the single
server-rendered markup and preserves the table aesthetic the user explicitly chose.

## Consequences

- No new dependency: Flask remains the only web dep; engine + terminal stay stdlib-only.
- The terminal frontend is untouched — this is a web-only presentation change.
- Web smoke tests stayed green (one assertion updated: the status bar now splits the day
  counter into label/value spans, so the test asserts `"1/30"` + `class="g-stat"`
  instead of the old literal `"Day 1/"`). 190 tests pass, web coverage 100%.
- The full boot-sequence **title splash** (the separate `Hallucination Inc Title
  Screen.html`, driven by `hallu-engine.js`) was out of scope for this pass — the open
  handoff file was the Game Screens (briefing + game). The CSS chromatic wordmark from
  that direction is included; the animated boot loop is a possible follow-up.
