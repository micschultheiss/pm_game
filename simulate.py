#!/usr/bin/env python3
"""
Headless Hallucination Inc. simulator.

Runs N games under different bot policies, aggregates outcomes, and surfaces
balance / mechanic insights.

Usage:
    python3 simulate.py                       # 200 games, all policies
    python3 simulate.py --runs 1000           # 1000 games each policy
    python3 simulate.py --policy planner      # one policy only
    python3 simulate.py --seed 42             # reproducible
    python3 simulate.py --json out.json       # dump raw per-run records
"""

import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict

import hallucination_inc as g


# ─────────────────────────────────────────────
# HEADLESS DRIVER
# ─────────────────────────────────────────────
# Calls game logic directly. Replicates the UI's location-gating so bots play
# under the same constraints a human does.

def execute(state, action):
    """Apply one action. Returns (ok, note). Enforces UI-level restrictions.

    Each successful action advances exactly one day — the game is turn-based.
    """
    if action is None:
        g.advance_days(state, 1)
        return True, "noop"
    kind = action[0]
    if kind == "buy":
        if state["location_type"] != "provider":
            return False, "buy requires provider location"
        _, token, qty = action
        ok, _ = g.do_buy_tokens(state, token, qty)
        if ok:
            g.advance_days(state, 1)
        return True, "buy"
    if kind == "craft":
        _, product = action
        ok, _ = g.do_craft(state, product)
        if ok:
            g.advance_days(state, 1)
        return True, "craft"
    if kind == "sell":
        if state["location_type"] != "client":
            return False, "sell requires client location"
        _, p_idx, c_idx = action
        ok, _ = g.do_sell_product(state, p_idx, c_idx)
        if ok:
            g.advance_days(state, 1)
        return True, "sell"
    if kind == "travel":
        _, dest_name, dest_type = action
        ok, _ = g.do_travel(state, dest_name, dest_type)
        if ok:
            g.advance_days(state, 1)
        return True, "travel"
    if kind == "wait":
        # Bots can still request multi-day skips by repeating the action;
        # the UI's Next is single-day, but the simulator keeps N for convenience.
        _, days = action
        g.advance_days(state, max(1, min(5, days)))
        return True, "wait"
    if kind == "pay":
        _, amount = action
        ok, _ = g.do_pay_debt(state, amount)
        if ok:
            g.advance_days(state, 1)
        return True, "pay"
    return False, f"unknown action {kind}"


def play_one_game(policy, turn_limit=4000, trace=False):
    """Play one full game with the given policy. Returns telemetry dict."""
    state = g.new_game()
    tally = defaultdict(int)
    revenue = 0
    products_sold = Counter()
    products_built = Counter()
    providers_visited = Counter()

    last_cash = state["cash"]

    for _ in range(turn_limit):
        if state["day"] > g.MAX_DAYS:
            break
        if state["cash"] <= 0 and not g.has_any_option(state):
            break

        action = policy(state)

        # Snapshot for tracking sells/crafts (state mutates inside execute).
        pre_products = list(state["products"])
        pre_crafting = state["crafting"]["name"] if state["crafting"] else None

        ok, note = execute(state, action)
        if not ok:
            g.advance_days(state, 1)
            tally["invalid"] += 1
            if trace:
                print(f"  d{state['day']:>2} INVALID  {action}  @{state['location']}")
            continue
        tally[note] += 1
        if trace:
            shelf = [f"{p['name']}({p['quality']:.0%})" for p in state["products"]]
            crafting_str = (f" craft={state['crafting']['name']}({state['crafting']['days_left']}d)"
                            if state["crafting"] else "")
            print(f"  d{state['day']:>2} {note:<6} {action}  "
                  f"@{state['location']:<22} cash=${state['cash']:>7,} "
                  f"shelf={shelf}{crafting_str}")

        # Detect a successful sale: cash went up AND products shrank.
        if note == "sell" and state["cash"] > last_cash:
            revenue += state["cash"] - last_cash
            # Identify which product was sold by diffing.
            post_names = Counter(p["name"] for p in state["products"])
            pre_names = Counter(p["name"] for p in pre_products)
            for name in (pre_names - post_names):
                products_sold[name] += 1
        # Detect a craft start (crafting field went from None → something).
        if note == "craft" and pre_crafting is None and state["crafting"] is not None:
            products_built[state["crafting"]["name"]] += 1

        last_cash = state["cash"]

        if note == "travel" and state["location_type"] == "provider":
            providers_visited[state["location"]] += 1

    nw = g.net_worth(state)
    return {
        "net_worth": nw,
        "cash": state["cash"],
        "debt": state["debt"],
        "day_ended": state["day"],
        "bankrupt": state["cash"] <= 0 and not g.has_any_option(state),
        "products_unsold": len(state["products"]),
        "crafting_unfinished": state["crafting"] is not None,
        "grade": _grade(nw),
        "actions": dict(tally),
        "revenue_total": revenue,
        "providers_visited": dict(providers_visited),
        "products_built": dict(products_built),
        "products_sold": dict(products_sold),
    }


def _grade(nw):
    if nw >= 1_000_000:
        return "UNICORN"
    if nw >= 500_000:
        return "SERIES_A"
    if nw >= 100_000:
        return "RAMEN"
    if nw >= 0:
        return "BROKE_EVEN"
    return "BANKRUPT"


# ─────────────────────────────────────────────
# BOT POLICIES
# ─────────────────────────────────────────────
# Each policy takes state and returns an action tuple (or None to wait 1 day).

def policy_random(state):
    """Random valid-ish action. Baseline noise."""
    choices = ["wait", "travel"]
    if state["location_type"] == "provider" and state["cash"] > 0 and g.token_free(state) > 0:
        choices.append("buy")
    if state["location_type"] == "client" and state["products"]:
        choices.append("sell")
    if any(g.can_craft(state, p) for p in g.PRODUCTS) and not state["crafting"]:
        choices.append("craft")
    if state["debt"] > 0 and state["cash"] > 5000:
        choices.append("pay")

    kind = random.choice(choices)
    if kind == "wait":
        return ("wait", random.randint(1, 3))
    if kind == "travel":
        destinations = [(p, "provider") for p in g.PROVIDERS if p != state["location"]]
        destinations += [(c["name"], "client") for c in state["active_clients"]
                         if c["name"] != state["location"]]
        if not destinations:
            return ("wait", 1)
        dest, dtype = random.choice(destinations)
        return ("travel", dest, dtype)
    if kind == "buy":
        prov = state["location"]
        prices = state["provider_prices"][prov]
        token = random.choice(g.TOKEN_TYPES)
        max_qty = min(g.token_free(state), state["cash"] // max(prices[token], 1))
        if max_qty < 1:
            return ("wait", 1)
        qty = random.randint(1, max(1, min(80, max_qty)))
        return ("buy", token, qty)
    if kind == "sell":
        client_idx = next((i for i, c in enumerate(state["active_clients"])
                           if c["name"] == state["location"]), None)
        if client_idx is None:
            return ("wait", 1)
        p_idx = random.randrange(len(state["products"]))
        return ("sell", p_idx, client_idx)
    if kind == "craft":
        craftable = [p for p in g.PRODUCTS if g.can_craft(state, p)]
        return ("craft", random.choice(craftable))
    if kind == "pay":
        amount = min(state["cash"] // 2, state["debt"])
        return ("pay", amount)
    return ("wait", 1)


def policy_greedy(state):
    """
    Greedy: at provider buy cheapest token, craft highest-base-value when
    possible, travel to a client with a matching open contract and sell. No
    quality awareness, no planning, no debt payment.
    """
    # 1. Sell immediately if at a client and we have a matching, qualifying product.
    if state["location_type"] == "client" and state["products"]:
        client = next((c for c in state["active_clients"]
                       if c["name"] == state["location"]), None)
        if client:
            for i, p in enumerate(state["products"]):
                contract = client["current_wants"].get(p["name"])
                if contract and p["quality"] >= contract["min_quality"]:
                    return ("sell", i, state["active_clients"].index(client))

    # 2. Craft the highest-value product we can.
    if not state["crafting"]:
        craftable = [(p, g.PRODUCTS[p]["base_value"])
                     for p in g.PRODUCTS if g.can_craft(state, p)]
        if craftable:
            craftable.sort(key=lambda x: -x[1])
            return ("craft", craftable[0][0])

    # 3. If we have any finished product, travel to a client that wants it.
    if state["products"]:
        for p in state["products"]:
            for c in state["active_clients"]:
                contract = c["current_wants"].get(p["name"])
                if contract and p["quality"] >= contract["min_quality"]:
                    if c["name"] != state["location"]:
                        return ("travel", c["name"], "client")
                    break

    # 4. At a provider — buy cheapest token by $/M up to storage limit.
    if state["location_type"] == "provider" and g.token_free(state) > 0:
        prov = state["location"]
        prices = state["provider_prices"][prov]
        cheapest = min(g.TOKEN_TYPES, key=lambda t: prices[t])
        unit = prices[cheapest]
        if unit > 0 and state["cash"] >= unit:
            qty = min(g.token_free(state), state["cash"] // unit, 100)
            if qty >= 1:
                return ("buy", cheapest, qty)

    # 5. Otherwise travel to the cheapest provider (random pick).
    other_provs = [p for p in g.PROVIDERS if p != state["location"]]
    if other_provs and state["cash"] >= g.TRAVEL_COST:
        return ("travel", random.choice(other_provs), "provider")

    return ("wait", 1)


def policy_planner(state):
    """
    Planner: looks at open contracts, picks the single best target by expected
    margin, sources only the tokens that contract needs from a quality-matching
    provider, crafts, travels, sells. Pays down debt with surplus cash to slow
    the debt interest bleed.
    """
    # 1. Sell finished product if at the right client.
    if state["location_type"] == "client":
        client_idx = next((i for i, c in enumerate(state["active_clients"])
                           if c["name"] == state["location"]), None)
        if client_idx is not None:
            client = state["active_clients"][client_idx]
            best_sale = None
            for i, p in enumerate(state["products"]):
                contract = client["current_wants"].get(p["name"])
                if contract and p["quality"] >= contract["min_quality"]:
                    payout = int(contract["budget"] *
                                 min(p["quality"] / contract["min_quality"],
                                     g.QUALITY_BONUS_CAP))
                    if best_sale is None or payout > best_sale[0]:
                        best_sale = (payout, i)
            if best_sale:
                return ("sell", best_sale[1], client_idx)

    # 2. Score every open contract by (budget * quality_cap) - (token sourcing cost).
    #    Filter to ones we can actually afford given current cash + reserve for travel.
    target = _pick_target_contract(state)

    # 3. If we already have a finished product matching ANY open contract → travel to sell.
    for p in state["products"]:
        for c in state["active_clients"]:
            contract = c["current_wants"].get(p["name"])
            if contract and p["quality"] >= contract["min_quality"]:
                if c["name"] != state["location"]:
                    if state["cash"] >= g.TRAVEL_COST:
                        return ("travel", c["name"], "client")
                    return ("wait", 1)

    # 4. If crafting in progress: travel toward a buyer for what we're building,
    #    so we're parked at a client when it lands. Then wait. Pay debt with
    #    surplus cash to slow the debt interest bleed.
    if state["crafting"]:
        building = state["crafting"]["name"]
        days_left = state["crafting"]["days_left"]
        buyer = next((c for c in state["active_clients"]
                      if building in c["current_wants"]), None)
        if buyer and state["location"] != buyer["name"] and state["cash"] >= g.TRAVEL_COST + 5_000:
            return ("travel", buyer["name"], "client")
        if days_left > 1 and state["debt"] > 0 and state["cash"] > 80_000:
            payment = min(state["cash"] - 60_000, state["debt"])
            if payment > 0:
                return ("pay", payment)
        return ("wait", 1)

    if not target:
        # No actionable contract — wait for client rotation.
        return ("wait", 2)

    contract_info, prod_name, client_idx, _ = target
    recipe = g.PRODUCTS[prod_name]["recipe"]
    # Source against the safe quality, not the contract minimum, so worst-case
    # final variance still clears.
    min_quality = contract_info["min_quality"] / 0.92

    # 5. Do we have all tokens? If yes, craft.
    if g.can_craft(state, prod_name) and _quality_ok_for_recipe(state, recipe, min_quality):
        return ("craft", prod_name)

    # 6. Else: figure out the next token we need and travel to the best provider for it.
    needed = _next_token_need(state, recipe)
    if needed is None:
        return ("wait", 1)
    token, qty_needed = needed

    here = state["location"]
    here_ok = (state["location_type"] == "provider"
               and g.PROVIDERS[here]["quality"] >= min_quality)
    cheapest = _best_provider_for(state, token, min_quality)

    # Stay put unless switching saves more than the travel cost (for the
    # *remaining* tokens we'll buy, summed across the whole recipe).
    if here_ok:
        target_provider = here
        if cheapest and cheapest != here:
            remaining_savings = 0
            for tok, need in recipe.items():
                held = state["tokens"].get(tok, {"qty": 0})["qty"]
                short = max(0, need - held)
                if short <= 0:
                    continue
                cand = _best_provider_for(state, tok, min_quality)
                if not cand:
                    continue
                p_here = state["provider_prices"][here].get(tok, 999)
                p_cand = state["provider_prices"][cand][tok]
                remaining_savings += short * max(0, p_here - p_cand)
            if remaining_savings > g.TRAVEL_COST * 1.1:
                target_provider = cheapest
    else:
        target_provider = cheapest or max(g.PROVIDERS.keys(),
                                          key=lambda p: g.PROVIDERS[p]["quality"])

    if state["location"] != target_provider:
        if state["cash"] >= g.TRAVEL_COST + 5_000:
            return ("travel", target_provider, "provider")
        return ("wait", 1)
    best_provider = target_provider

    # At the right provider. Buy what we need (cash-bounded), but keep one
    # travel-cost in reserve so we can reach the client to sell.
    price = state["provider_prices"][best_provider][token]
    reserve = g.TRAVEL_COST + 2_000
    budget = max(0, state["cash"] - reserve)
    affordable = budget // max(price, 1)
    free = g.token_free(state)
    qty = min(qty_needed, affordable, free)
    if qty < 1:
        # Can't afford even one without breaking reserve.
        # If we already have *most* of the recipe, accept partial cash; else wait.
        held_pct = _recipe_progress(state, prod_name)
        if held_pct > 0.6 and state["cash"] >= price:
            qty = min(qty_needed, state["cash"] // price, free)
            if qty < 1:
                return ("wait", 1)
        else:
            return ("wait", 1)
    return ("buy", token, qty)


def _recipe_progress(state, product_name):
    """Fraction of recipe tokens currently held (capped at 1.0 per token)."""
    recipe = g.PRODUCTS[product_name]["recipe"]
    held = 0
    total = 0
    for tok, need in recipe.items():
        h = state["tokens"].get(tok, {"qty": 0})["qty"]
        held += min(h, need)
        total += need
    return held / total if total else 0


def _pick_target_contract(state):
    """Return (contract_info, product_name, client_idx, score) for best target.

    Score = expected margin, with a heavy affordability penalty when the
    estimated build cost can't be covered by current cash. Crafting time also
    discounts long builds (more chance the contract drifts away)."""
    best = None
    cash = state["cash"]
    for ci, client in enumerate(state["active_clients"]):
        for prod_name, info in client["current_wants"].items():
            recipe = g.PRODUCTS[prod_name]["recipe"]
            # Final-variance worst case is 0.92×, so we need tokens with
            # quality ≥ min_quality / 0.92 to be confident of a sale.
            safe_q = info["min_quality"] / 0.92
            est_cost = 0
            feasible = True
            for tok, need in recipe.items():
                held = state["tokens"].get(tok, {"qty": 0})["qty"]
                short = max(0, need - held)
                cheapest = _best_provider_for(state, tok, safe_q)
                if cheapest is None:
                    # No provider can reliably hit this contract — disqualify.
                    feasible = False
                    break
                est_cost += short * state["provider_prices"][cheapest][tok]
            if not feasible:
                continue
            est_cost += 2 * g.TRAVEL_COST
            craft_days = g.PRODUCTS[prod_name]["craft_days"]
            drift_discount = (1 - 0.10) ** craft_days
            score = info["budget"] * drift_discount - est_cost
            if est_cost > cash * 1.1:
                score -= (est_cost - cash) * 2
            if best is None or score > best[3]:
                best = (info, prod_name, ci, score)
    return best


def _next_token_need(state, recipe):
    """Pick the first token in the recipe we don't have enough of."""
    for tok, need in recipe.items():
        held = state["tokens"].get(tok, {"qty": 0})["qty"]
        if held < need:
            return tok, need - held
    return None


def _best_provider_for(state, token, min_quality):
    """Cheapest provider whose quality >= min_quality for this token."""
    candidates = [
        (state["provider_prices"][p][token], p)
        for p in g.PROVIDERS
        if g.PROVIDERS[p]["quality"] >= min_quality
    ]
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _quality_ok_for_recipe(state, recipe, min_quality):
    """Check held tokens' average quality is enough for the contract."""
    for tok in recipe:
        avg = g.token_avg_quality(state, tok)
        if avg < min_quality:
            return False
    return True


POLICIES = {
    "random":  policy_random,
    "greedy":  policy_greedy,
    "planner": policy_planner,
}


# ─────────────────────────────────────────────
# AGGREGATION
# ─────────────────────────────────────────────

def run_batch(policy_name, n_runs, seed=None):
    if seed is not None:
        random.seed(seed)
    policy = POLICIES[policy_name]
    runs = []
    for i in range(n_runs):
        runs.append(play_one_game(policy))
    return runs


def summarize(policy_name, runs):
    n = len(runs)
    grades = Counter(r["grade"] for r in runs)
    nws = [r["net_worth"] for r in runs]
    days = [r["day_ended"] for r in runs]
    bankrupt = sum(1 for r in runs if r["bankrupt"])
    revenue = [r["revenue_total"] for r in runs]
    unsold = [r["products_unsold"] for r in runs]

    action_totals = Counter()
    provider_totals = Counter()
    built_totals = Counter()
    sold_totals = Counter()
    for r in runs:
        for k, v in r["actions"].items():
            action_totals[k] += v
        for k, v in r["providers_visited"].items():
            provider_totals[k] += v
        for k, v in r.get("products_built", {}).items():
            built_totals[k] += v
        for k, v in r.get("products_sold", {}).items():
            sold_totals[k] += v

    def pct(x):
        return f"{100*x/n:.1f}%"

    lines = []
    lines.append(f"\n=== {policy_name.upper()} — {n} runs ===")
    lines.append(f"  Net worth:   mean ${int(statistics.mean(nws)):>10,}   "
                 f"median ${int(statistics.median(nws)):>10,}   "
                 f"min ${min(nws):>10,}   max ${max(nws):>10,}")
    lines.append(f"  Revenue:     mean ${int(statistics.mean(revenue)):>10,}   "
                 f"median ${int(statistics.median(revenue)):>10,}")
    lines.append(f"  Days played: mean {statistics.mean(days):.1f}   "
                 f"bankrupt {bankrupt} ({pct(bankrupt)})")
    lines.append(f"  Unsold finished products at end: mean {statistics.mean(unsold):.2f}")
    lines.append("  Grade distribution:")
    for grade in ("UNICORN", "SERIES_A", "RAMEN", "BROKE_EVEN", "BANKRUPT"):
        c = grades.get(grade, 0)
        bar = "█" * int(40 * c / n)
        lines.append(f"    {grade:<11} {c:>4} ({pct(c):>6})  {bar}")
    lines.append(f"  Action counts (totals): {dict(action_totals.most_common())}")
    lines.append(f"  Provider visits (totals): {dict(provider_totals.most_common())}")
    if built_totals or sold_totals:
        lines.append("  Product mix (built → sold across all runs):")
        for prod in g.PRODUCTS:
            b = built_totals.get(prod, 0)
            s = sold_totals.get(prod, 0)
            conv = f"{100*s/b:.0f}%" if b else "—"
            lines.append(f"    {prod:<26} built {b:>4}   sold {s:>4}   conv {conv}")
    return "\n".join(lines)


def design_insights(by_policy):
    """Compare results across policies and flag suspected balance issues."""
    out = ["", "=== DESIGN INSIGHTS ==="]

    # 1. Is strategy load-bearing?
    medians = {p: statistics.median(r["net_worth"] for r in runs)
               for p, runs in by_policy.items()}
    if "random" in medians and "planner" in medians:
        gap = medians["planner"] - medians["random"]
        out.append(f"  Median NW gap planner − random: ${int(gap):,}  "
                   f"(planner ${int(medians['planner']):,} vs random ${int(medians['random']):,})")
        if gap < 50_000:
            out.append("    ⚠ small gap — strategy may not matter enough; consider raising "
                       "consequences for thoughtless play (debt rate, decay, travel cost).")
        else:
            out.append("    ✓ healthy gap — planning beats noise.")

    # 2. Bankruptcy rate per policy.
    for p, runs in by_policy.items():
        rate = sum(1 for r in runs if r["bankrupt"]) / len(runs)
        out.append(f"  {p:<8} bankruptcy rate: {rate*100:.1f}%")
        if p == "planner" and rate > 0.3:
            out.append("    ⚠ planner still busts >30% — early-game cash crunch may be too "
                       "tight, or RNG variance too punishing.")
        if p == "random" and rate < 0.5:
            out.append("    ⚠ random survives >50% — game may be too forgiving.")

    # 3. Win rates (RAMEN+).
    for p, runs in by_policy.items():
        wins = sum(1 for r in runs if r["grade"] in ("UNICORN", "SERIES_A", "RAMEN"))
        out.append(f"  {p:<8} win rate (≥RAMEN): {100*wins/len(runs):.1f}%")

    # 4. Provider usage — is anyone unused?
    all_provs = set(g.PROVIDERS.keys())
    for p, runs in by_policy.items():
        visited = set()
        for r in runs:
            visited.update(r["providers_visited"].keys())
        unused = all_provs - visited
        if unused:
            out.append(f"  {p:<8} never visits: {sorted(unused)}  "
                       f"⚠ dead content under this policy.")

    # 5. Product balance under the planner (most informative bot).
    if "planner" in by_policy:
        built = Counter()
        sold = Counter()
        for r in by_policy["planner"]:
            for k, v in r.get("products_built", {}).items():
                built[k] += v
            for k, v in r.get("products_sold", {}).items():
                sold[k] += v
        total_built = sum(built.values()) or 1
        out.append("  Planner product mix (share of builds):")
        for prod in g.PRODUCTS:
            share = built.get(prod, 0) / total_built
            conv = sold.get(prod, 0) / built[prod] if built.get(prod) else 0
            flag = ""
            if share < 0.02:
                flag = "  ⚠ rarely built — recipe may be uneconomical"
            elif share > 0.40:
                flag = "  ⚠ dominates — consider rebalancing base_value or recipe"
            elif built.get(prod, 0) >= 50 and conv < 0.55:
                flag = f"  ⚠ low conversion ({conv:.0%}) — drift/decay outpaces build"
            out.append(f"    {prod:<26} {share*100:>5.1f}% of builds   {flag}")

    return "\n".join(out)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=200,
                    help="games per policy (default 200)")
    ap.add_argument("--policy", choices=list(POLICIES) + ["all"], default="all")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json", type=str, default=None,
                    help="write raw per-run records to this path")
    ap.add_argument("--trace", action="store_true",
                    help="trace one game per policy (turn-by-turn). Implies --runs 1.")
    args = ap.parse_args()

    if args.trace:
        for name in (list(POLICIES) if args.policy == "all" else [args.policy]):
            if args.seed is not None:
                random.seed(args.seed)
            print(f"\n--- TRACE: {name} ---")
            result = play_one_game(POLICIES[name], trace=True)
            print(f"  END day={result['day_ended']} cash=${result['cash']:,} "
                  f"debt=${result['debt']:,} nw=${result['net_worth']:,} "
                  f"grade={result['grade']}")
            print(f"  built={result['products_built']} sold={result['products_sold']}")
        return

    policies = list(POLICIES) if args.policy == "all" else [args.policy]

    print(f"Simulating {args.runs} runs × {len(policies)} polic"
          f"{'ies' if len(policies) > 1 else 'y'}"
          f"{f' (seed {args.seed})' if args.seed is not None else ''}...",
          file=sys.stderr)

    by_policy = {}
    for i, name in enumerate(policies):
        seed = (args.seed + i * 1000) if args.seed is not None else None
        by_policy[name] = run_batch(name, args.runs, seed=seed)

    for name in policies:
        print(summarize(name, by_policy[name]))

    if len(policies) > 1:
        print(design_insights(by_policy))

    if args.json:
        with open(args.json, "w") as f:
            json.dump(by_policy, f, indent=2)
        print(f"\nRaw records → {args.json}")


if __name__ == "__main__":
    main()
