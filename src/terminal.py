#!/usr/bin/env python3
"""
Hallucination Inc. — terminal frontend.

ANSI-coloured terminal UI for the game: banner header, action menus,
prompts, end screens, and the blocking REPL that drives turns forward.
Game state, actions, and oracles live in `engine.py` — this module is
presentation only.

Entry point: ``python3 hallucination_inc.py`` dispatches here via
``terminal.main()``. Importing this module directly also works.
"""

import os
import shutil

from engine import (
    ACTIVE_CLIENT_COUNT,
    DEBT_FREE_BONUS,
    MAX_DAYS,
    MAX_TOKENS,
    MAX_VISIBLE_CONTRACTS,
    PRODUCTS,
    PROVIDERS,
    TOKEN_ABBREV,
    TOKEN_TYPES,
    TRAVEL_COST,
    advance_days,
    borrow_available,
    borrow_limit,
    can_craft,
    compute_market_demand,
    do_borrow,
    do_buy_tokens,
    do_craft,
    do_pay_debt,
    do_sell_product,
    do_travel,
    has_any_option,
    net_worth,
    new_game,
    token_avg_quality,
    token_free,
    token_total,
)

# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────

def _term_width():
    """Live terminal width, clamped to keep tables readable."""
    cols = shutil.get_terminal_size((80, 24)).columns
    return max(64, min(cols, 120))

# Only color is the action-menu hotkey letter (bright cyan / light blue).
_CY  = "\033[96m"
_BLD = "\033[1m"
_RST = "\033[0m"

def _key(letter, rest):
    return f"[{_BLD}{_CY}{letter}{_RST}]{rest}"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def rule(char="─"):
    print(char * _term_width())

def pause(label="Press ENTER to continue..."):
    try:
        input(f"\n  {label}")
    except (EOFError, KeyboardInterrupt):
        pass

def header(state):
    clear()
    rule("═")
    loc_label = f"📍 {state['location']}"
    if state["location_type"] == "provider":
        prov = PROVIDERS[state["location"]]
        loc_label += f" ({prov['desc']}, {prov['quality']:.0%})"
    else:
        for c in state["active_clients"]:
            if c["name"] == state["location"]:
                loc_label += f" ({c['type']})"
                break
    print(f"  HALLUCINATION INC. · Day {state['day']}/{MAX_DAYS} · {loc_label}")
    crafting = "🔨 idle"
    if state["crafting"]:
        c = state["crafting"]
        crafting = f"🔨 {c['name']} ({c['days_left']}d, {c['quality']:.0%})"
    print(f"  💰 ${state['cash']:,}   💳 ${state['debt']:,}   "
          f"📦 {token_total(state)}M/{MAX_TOKENS}M   {crafting}")
    rule("═")

def status_bar(state):
    """Compact one-liner re-stating cash/debt/day/storage right above the action prompt."""
    crafting = ""
    if state["crafting"]:
        c = state["crafting"]
        crafting = f"   🔨 {c['name']} ({c['days_left']}d, {c['quality']:.0%})"
    rule()
    print(f"  💰 ${state['cash']:,}   💳 ${state['debt']:,}   "
          f"📅 Day {state['day']}/{MAX_DAYS}   📦 {token_total(state)}M/{MAX_TOKENS}M{crafting}")
    rule()

def show_event(state):
    if state["last_event"]:
        print(f"\n  ⚡ {state['last_event']}\n")
        state["last_event"] = None

def show_message(state):
    if state["message"]:
        rule()
        print(f"  ➤  {state['message']}")
        rule()
        state["message"] = None

def show_provider_price_grid(state):
    """Full provider-vs-token price grid. Used on day 1 so the player sees the
    whole market at a glance; subsequent days fall back to the one-line panel."""
    name_w = max(len(n) for n in PROVIDERS)
    col_w = max(len("Reasoning"), 6)
    here = state["location"] if state["location_type"] == "provider" else None
    header_row = (
        f"    {'Provider'.ljust(name_w)}   Qual  "
        + "  ".join(f"{t:>{col_w}}" for t in TOKEN_TYPES)
    )
    print("  Today's market — $/M tokens at every provider:")
    print(header_row)
    for name, data in sorted(PROVIDERS.items(), key=lambda kv: -kv[1]["quality"]):
        prices = state["provider_prices"][name]
        cells = "  ".join(f"{'$' + str(prices[t]):>{col_w}}" for t in TOKEN_TYPES)
        marker = "→ " if name == here else "  "
        print(f"  {marker}{name.ljust(name_w)}   {data['quality']:>3.0%}  {cells}")

def show_location_panel(state):
    """Current-location context. Provider prices are rendered separately by the
    market grid (show_provider_price_grid), so this panel only surfaces the
    'you are at a client' wants line."""
    if state["location_type"] == "provider":
        return
    client = next((c for c in state["active_clients"]
                   if c["name"] == state["location"]), None)
    if not client or not client["current_wants"]:
        print(f"  At {state['location']} — no open contracts here.")
    else:
        parts = [f"{p} (${i['budget']:,}, ≥{i['min_quality']:.0%})"
                 for p, i in client["current_wants"].items()]
        print(f"  At {state['location']}:  {' · '.join(parts)}")

def show_inventory_inline(state):
    """Tokens + products as one line each."""
    if state["tokens"]:
        parts = []
        for tok in TOKEN_TYPES:
            data = state["tokens"].get(tok)
            if data and data["qty"] > 0:
                avg_q = data["quality_sum"] / data["qty"]
                parts.append(f"{tok} {data['qty']}M ({avg_q:.0%}q)")
        print(f"  Tokens:        {' · '.join(parts) if parts else '(none)'}")
    else:
        print(f"  Tokens:        (none)")
    parts = [f"{p['name']} ({p['quality']:.0%})" for p in state["products"]]
    if state["crafting"]:
        c = state["crafting"]
        parts.append(f"🔨 {c['name']} ({c['days_left']}d left, {c['quality']:.0%})")
    if parts:
        print(f"  Products:      {' · '.join(parts)}")
    else:
        print(f"  Products:      (none)")

def show_market_demand(state):
    demand = compute_market_demand(state)
    if not demand:
        print("  Market demand:  (no open contracts)")
        return
    parts = [f"{tok} {demand[tok]}M" for tok in TOKEN_TYPES if demand.get(tok, 0) > 0]
    print(f"  Market demand:  {' · '.join(parts)}")

def _recipe_short(product_name):
    """Compact recipe string in canonical token order, e.g. '60Co · 120Re · 20Im'."""
    recipe = PRODUCTS[product_name]["recipe"]
    return " · ".join(f"{recipe[t]}{TOKEN_ABBREV[t]}" for t in TOKEN_TYPES if t in recipe)

def show_open_contracts(state):
    """All client wants, sorted by payout descending. Shows the recipe to build each."""
    rows = []
    for client in state["active_clients"]:
        tag = "GOV" if client["type"] == "Government" else "ENT"
        for prod_name, info in client["current_wants"].items():
            rows.append((info["budget"], tag, client["name"], prod_name, info["min_quality"]))
    rows.sort(reverse=True, key=lambda r: r[0])
    rows = rows[:MAX_VISIBLE_CONTRACTS]
    if not rows:
        print("  Open contracts: (none right now)")
        return
    print("  Open contracts (by payout):")
    for budget, tag, name, prod, minq in rows:
        recipe = _recipe_short(prod)
        print(f"    [{tag}] {name:<22} {prod:<24} {recipe:<24} ${budget:>7,}  ≥{minq:.0%}")

def show_provider(state):
    prov = state["location"]
    quality = PROVIDERS[prov]["quality"]
    prices = state["provider_prices"][prov]
    print(f"\n  Token prices at {prov} (quality: {quality:.0%}, per million):\n")
    print(f"  {'#':<4} {'Token':<12} {'$/M':>8}   {'You Have':>10}")
    print(f"  {'─'*4} {'─'*12} {'─'*8}   {'─'*10}")
    for i, token in enumerate(TOKEN_TYPES, 1):
        price = prices[token]
        held = state["tokens"].get(token, {"qty": 0})["qty"]
        avg_q = token_avg_quality(state, token)
        held_str = f"{held}M" if held else "—"
        if held > 0:
            held_str += f" ({avg_q:.0%}q)"
        print(f"  {i:<4} {token:<12} ${price:>7,}   {held_str:>10}")

def show_client_offers(state):
    print(f"\n  {state['location']} wants:\n")
    client = None
    for c in state["active_clients"]:
        if c["name"] == state["location"]:
            client = c
            break
    if not client or not client["current_wants"]:
        print("  (this client has no open contracts right now)")
        return
    print(f"  {'#':<4} {'Product':<26} {'Pays':>8}   {'Min Quality':>11}")
    print(f"  {'─'*4} {'─'*26} {'─'*8}   {'─'*11}")
    for i, (prod, info) in enumerate(client["current_wants"].items(), 1):
        print(f"  {i:<4} {prod:<26} ${info['budget']:>7,}   {info['min_quality']:>10.0%}")

def show_tokens(state):
    if not state["tokens"]:
        print("\n  Tokens: (none)")
        return
    print("\n  Your tokens:")
    for token, data in state["tokens"].items():
        avg_q = data["quality_sum"] / data["qty"] if data["qty"] > 0 else 0
        print(f"    {token:<12} {data['qty']}M  (avg quality: {avg_q:.0%})")

def show_products(state):
    if not state["products"]:
        print("\n  Built products: (none)")
        return
    print("\n  Built products:")
    for i, p in enumerate(state["products"], 1):
        print(f"    {i}. {p['name']}  (quality: {p['quality']:.0%})")

def show_craftable(state):
    print("\n  Product catalog — costs to craft & base contract value:")
    print(f"  {'#':<3}{'Product':<24}{'Build':>6}  {'Recipe (M tokens)':<40}{'Base $':>8}  Ready")
    print(f"  {'─'*3}{'─'*24}{'─'*6}  {'─'*40}{'─'*8}  {'─'*5}")
    for i, (name, prod) in enumerate(PRODUCTS.items(), 1):
        recipe_str = " + ".join(f"{n}M {t}" for t, n in prod["recipe"].items())
        ready = "✓" if can_craft(state, name) else "·"
        base_str = f"${prod['base_value']//1000}K"
        print(f"  {i:<3}{name:<24}{prod['craft_days']:>5}d  {recipe_str:<40}{base_str:>8}    {ready}")

def show_all_clients(state):
    print("\n  Active client contracts:")
    for c in state["active_clients"]:
        tag = "GOV" if c["type"] == "Government" else "ENT"
        wants_str = ", ".join(c["current_wants"].keys()) if c["current_wants"] else "(satisfied)"
        print(f"    [{tag}] {c['name']:<25} wants: {wants_str}")

# Sentinel returned by prompt_int when the user typed something that isn't a number.
# Distinct from None (empty input / EOF / Ctrl-C = "cancel") so menus can give feedback.
INVALID_INPUT = object()

def prompt_int(label):
    try:
        raw = input(f"  {label}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return INVALID_INPUT

def prompt_str(label):
    try:
        return input(f"  {label}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""

# ─────────────────────────────────────────────
# MENUS
# ─────────────────────────────────────────────

def menu_buy(state):
    if state["location_type"] != "provider":
        state["message"] = "You need to be at a provider to buy tokens."
        return
    show_provider(state)
    print()
    status_bar(state)
    choice = prompt_int(f"Token # (1-{len(TOKEN_TYPES)}, or 0 to cancel)")
    if choice is INVALID_INPUT:
        state["message"] = "Please enter a number for the token choice."
        return
    if choice is None or choice == 0:
        return
    if not (1 <= choice <= len(TOKEN_TYPES)):
        state["message"] = f"Pick a token between 1 and {len(TOKEN_TYPES)}."
        return
    token = TOKEN_TYPES[choice - 1]
    qty = prompt_int(f"Quantity of {token} in millions (0 to cancel)")
    if qty is INVALID_INPUT:
        state["message"] = "Please enter a number for the quantity."
        return
    if qty is None or qty == 0:
        return
    if qty < 1:
        state["message"] = "Quantity must be a positive number of millions."
        return
    ok, msg = do_buy_tokens(state, token, qty)
    if ok:
        advance_days(state, 1)
    if not state["message"]:
        state["message"] = msg

def menu_sell(state):
    if state["location_type"] != "client":
        state["message"] = "You need to be at a client to sell."
        return
    client = None
    client_idx = None
    for i, c in enumerate(state["active_clients"]):
        if c["name"] == state["location"]:
            client = c
            client_idx = i
            break
    if not client:
        state["message"] = f"⚠️ {state['location']} is no longer in the active roster. Travel elsewhere."
        return
    if not state["products"]:
        state["message"] = "You have no built products to sell. Craft something first."
        return
    if not client["current_wants"]:
        state["message"] = f"{client['name']} has no open contracts. Try another client."
        return
    show_client_offers(state)
    show_products(state)
    print()
    status_bar(state)
    pidx = prompt_int(f"Product # to sell (1-{len(state['products'])}, or 0 to cancel)")
    if pidx is INVALID_INPUT:
        state["message"] = "Please enter a number for the product choice."
        return
    if pidx is None or pidx == 0:
        return
    if not (1 <= pidx <= len(state["products"])):
        state["message"] = f"Pick a product between 1 and {len(state['products'])}."
        return
    ok, msg = do_sell_product(state, pidx - 1, client_idx)
    # Show the outcome inline so the player sees it before the screen redraws.
    print(f"\n  ➤  {msg}")
    pause()
    if ok:
        advance_days(state, 1)
    if not state["message"]:
        state["message"] = msg

def menu_craft(state):
    if state["crafting"]:
        state["message"] = f"Already crafting {state['crafting']['name']} ({state['crafting']['days_left']}d left)."
        return
    show_tokens(state)
    show_craftable(state)
    print()
    choice = prompt_int(f"Product # to craft (1-{len(PRODUCTS)}, or 0 to cancel)")
    if choice is INVALID_INPUT:
        state["message"] = "Please enter a number for the product choice."
        return
    if choice is None or choice == 0:
        return
    if not (1 <= choice <= len(PRODUCTS)):
        state["message"] = f"Pick a product between 1 and {len(PRODUCTS)}."
        return
    product_name = list(PRODUCTS.keys())[choice - 1]
    ok, msg = do_craft(state, product_name)
    if ok:
        advance_days(state, 1)
    if not state["message"]:
        state["message"] = msg

def menu_travel(state):
    print()
    show_provider_price_grid(state)
    print("\n  Destinations:\n")
    destinations = []
    print("  --- LLM Providers ---")
    for prov in PROVIDERS:
        if prov != state["location"]:
            destinations.append((prov, "provider"))
            idx = len(destinations)
            q = PROVIDERS[prov]["quality"]
            print(f"    {idx}. {prov}  ({PROVIDERS[prov]['desc']}, quality: {q:.0%})")
    print("\n  --- Clients ---")
    def _client_sort_key(c):
        budgets = [w["budget"] for w in c["current_wants"].values()]
        # Satisfied clients (no wants) sink to the bottom; otherwise sort by best payout desc.
        return (0 if budgets else 1, -max(budgets) if budgets else 0)
    sorted_clients = sorted(state["active_clients"], key=_client_sort_key)
    for c in sorted_clients:
        if c["name"] != state["location"]:
            destinations.append((c["name"], "client"))
            idx = len(destinations)
            tag = "GOV" if c["type"] == "Government" else "ENT"
            wants = ", ".join(c["current_wants"].keys()) if c["current_wants"] else "(satisfied)"
            print(f"    {idx}. [{tag}] {c['name']}  — wants: {wants}")
    print(f"\n  (Travel costs ${TRAVEL_COST:,} + 1 day)\n")
    choice = prompt_int(f"Choose 1-{len(destinations)} (or 0 to cancel)")
    if choice is INVALID_INPUT:
        state["message"] = "Please enter a number for the destination."
        return
    if choice is None or choice == 0:
        return
    if not (1 <= choice <= len(destinations)):
        state["message"] = f"Pick a destination between 1 and {len(destinations)}."
        return
    dest_name, dest_type = destinations[choice - 1]
    ok, msg = do_travel(state, dest_name, dest_type)
    if ok:
        advance_days(state, 1)
    if not state["message"]:
        state["message"] = msg

def menu_next(state):
    advance_days(state, 1)
    if not state["message"]:
        state["message"] = "Day advanced."

def menu_borrow(state):
    limit = borrow_limit(state)
    avail = borrow_available(state)
    print(f"\n  Collateral line: ${limit:,} (30% of finished product base value)")
    print(f"  Already borrowed against inventory: ${state.get('collateral_debt', 0):,}")
    print(f"  Available to borrow now: ${avail:,}")
    if avail <= 0:
        if not state["products"]:
            state["message"] = "You need at least one finished product as collateral."
        else:
            state["message"] = "Collateral fully tapped — sell or build more products to borrow again."
        return
    amount = prompt_int("Amount to borrow (0 to cancel)")
    if amount is INVALID_INPUT:
        state["message"] = "Please enter a dollar amount."
        return
    if amount is None or amount == 0:
        return
    ok, msg = do_borrow(state, amount)
    if ok:
        advance_days(state, 1)
    if not state["message"]:
        state["message"] = msg

def menu_pay_debt(state):
    print(f"\n  Outstanding debt: ${state['debt']:,}")
    if state["debt"] == 0:
        state["message"] = "You're debt-free!"
        return
    amount = prompt_int("Amount to pay (0 to cancel)")
    if amount is INVALID_INPUT:
        state["message"] = "Please enter a dollar amount."
        return
    if amount is None or amount == 0:
        return
    ok, msg = do_pay_debt(state, amount)
    if ok:
        advance_days(state, 1)
    if not state["message"]:
        state["message"] = msg

# ─────────────────────────────────────────────
# END SCREEN
# ─────────────────────────────────────────────

def end_screen(state):
    clear()
    rule("═")
    print("  GAME OVER — Performance Review")
    rule("═")
    nw = net_worth(state)
    debt_free_bonus = DEBT_FREE_BONUS if state["debt"] == 0 else 0
    final_score = nw + debt_free_bonus
    print(f"\n  Cash:        ${state['cash']:>10,}")
    print(f"  Debt:        ${state['debt']:>10,}")
    print(f"  Net Worth:   ${nw:>10,}")
    if debt_free_bonus:
        print(f"  Debt-free bonus: +${debt_free_bonus:,}")
        print(f"  Final Score: ${final_score:>10,}")
    print(f"  Products built: {len(state['products'])} unsold\n")
    rule()
    if final_score >= 1_000_000:
        grade = "🏆 UNICORN — You disrupted the market. IPO incoming."
    elif final_score >= 500_000:
        grade = "🌟 SERIES A — Strong traction. Investors are lining up."
    elif final_score >= 100_000:
        grade = "✅ RAMEN PROFITABLE — Scrappy, but you made it work."
    elif final_score >= 0:
        grade = "😅 BROKE EVEN — The hallucinations were mid."
    else:
        grade = "💀 BANKRUPT — Turns out it was all hallucinated."
    print(f"\n  {grade}\n")
    rule("═")

# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────
# `has_any_option`, `is_bankrupt`, and `is_game_over` live in engine.py and
# are pulled in by the `from engine import *` at the top of this file.

def bankruptcy_screen(state):
    clear()
    rule("═")
    print("  💀 BANKRUPTCY")
    rule("═")
    print()
    print(f"  Day {state['day']}: cash $0, no path forward.")
    print(f"  Debt: ${state['debt']:,}")
    print(f"  Tokens: {token_total(state)}M, Products: {len(state['products'])}")
    print()
    print("  No way to buy, craft, sell, or travel.")
    print("  The runway is gone. Game over.")
    print()
    rule("═")
    input("  Press ENTER to continue...")

def game_loop(state):
    while state["day"] <= MAX_DAYS:
        # Bankruptcy check: out of cash AND no productive move available
        if state["cash"] <= 0 and not has_any_option(state):
            bankruptcy_screen(state)
            break

        # If our location is a client that got rotated out, kick a notice
        if state["location_type"] == "client":
            if not any(c["name"] == state["location"] for c in state["active_clients"]):
                if not state["message"]:
                    state["message"] = f"⚠️ {state['location']} rotated out. Travel to another destination."

        header(state)
        show_event(state)
        if state["message"]:
            print(f"  ➤  {state['message']}\n")
            state["message"] = None

        print()
        show_location_panel(state)
        show_inventory_inline(state)
        print()
        rule()
        show_provider_price_grid(state)
        rule()
        show_open_contracts(state)
        rule()
        primary = _key("B", "uy") if state["location_type"] == "provider" else _key("S", "ell")
        menu = "  ".join([
            primary,
            _key("C", "raft"),
            _key("T", "ravel"),
            _key("L", "end"),
            _key("P", "ay"),
            _key("N", "ext"),
            _key("Q", "uit"),
        ])
        print(f"  {menu}")
        rule()
        try:
            cmd = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "b":
            menu_buy(state)
        elif cmd == "s":
            menu_sell(state)
        elif cmd == "c":
            menu_craft(state)
        elif cmd == "t":
            menu_travel(state)
        elif cmd == "n" or cmd == "":
            menu_next(state)
        elif cmd == "l":
            menu_borrow(state)
        elif cmd == "p":
            menu_pay_debt(state)
        elif cmd == "q":
            break
        else:
            state["message"] = "Unknown command."

    end_screen(state)


def main():
    clear()
    rule("═")
    print(f"  {_BLD}HALLUCINATION INC.{_RST} — Where AI Meets Enterprise")
    rule("═")
    b = _BLD
    r = _RST
    print(f"""
  AI is eating your lunch. You've just been laid off from your cushy PM gig
  at one of the big tech giants — and now you're out to cash in on the
  {b}SaaSocalypse{r}. Nobody has cracked enterprise-grade software with the new
  AI coding tools yet. That's where you come in.

  {b}$100,000 in debt{r}. {b}3% interest per day{r}. {b}30 days{r} to turn it into a real
  business.


  THE BASICS (in plain English)
  • {b}Tokens{r} are the fuel AI runs on. You buy them by the million from AI
    providers — the big labs like Anthropic, OpenAI, and Google. Prices
    move daily, and pricier providers ship higher-quality output.
  • {b}Products{r} are finished AI SaaS solutions — a support bot, a compliance
    dashboard, and so on. You build each from a recipe of tokens over a
    few days. Your pitch: reliable enterprise software, shipped in days.
  • {b}Clients{r} are the companies and government agencies that buy your
    products. {ACTIVE_CLIENT_COUNT} are live at any time. Each pays a fixed budget
    — but only if your product clears their minimum quality bar.


  YOUR JOB
  {b}Buy tokens cheap{r}  →  {b}build quality products{r}  →  {b}sell for a profit{r},
  all before your debt eats you alive.


  GOOD TO KNOW
  • You start with {b}$100K cash{r} and {b}$100K debt{r} that grows {b}3% a day{r}.
    Pay it off before day 30 for a {b}+$75K{r} debt-free bonus.
  • A sales trip costs {b}$30K{r} and burns a day.
  • Builds take {b}2-6 days{r} and {b}50-225M tokens{r}; storage caps at {b}500M{r}.
  • {ACTIVE_CLIENT_COUNT} clients live at once — they rotate every few days. Grab good deals fast.
  • Beating a client's quality bar pays up to {b}1.5×{r} the budget.
    Tokens and finished products lose quality as they age.

  {b}30 days on the clock.{r} Good luck.
""")
    rule()
    input("  Press ENTER to start...")
    state = new_game()
    game_loop(state)


if __name__ == "__main__":
    main()
