#!/usr/bin/env python3
"""
Code Wars - Vibe Coding Edition
Buy LLM tokens (in millions) from AI providers, craft SaaS products,
and sell them to enterprise and government clients before your runway burns out.
"""

import random
import os

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

MAX_DAYS              = 30
STARTING_CASH         = 35_000
STARTING_DEBT         = 300_000
DEBT_INTEREST         = 0.02    # 2% per day on outstanding debt
TRAVEL_COST           = 30_000  # biz dev / sales travel — pitch decks aren't free
MAX_TOKENS            = 500     # max storage in millions of tokens
QUALITY_BONUS_CAP     = 1.2     # max premium for over-spec quality
CLIENT_ROTATION_MIN   = 3       # min days between partial rotations
CLIENT_ROTATION_MAX   = 7       # max days between partial rotations
CLIENT_DRIFT_CHANCE   = 0.10    # daily chance per client to shift a budget
CLIENT_DROP_CHANCE    = 0.05    # daily chance per client to drop a want
CLIENT_ADD_CHANCE     = 0.04    # daily chance per client to add a new want
CRAFT_DECAY_BASE      = 0.05    # base daily chance during craft
PRODUCT_DECAY_BASE    = 0.03    # base daily chance for sitting products
DECAY_SIZE_FACTOR     = 0.0006  # added to chance per M tokens of recipe size
REFACTOR_MIN_RATIO    = 0.70    # min token cost ratio vs original recipe size
REFACTOR_MAX_RATIO    = 1.20    # max token cost ratio (rolled per refactor)
REFACTOR_QUALITY_LIFT = 0.70    # closes 70% of the gap to refactor token quality
REFACTOR_SMALL_LIFT   = 0.04    # flat lift for any refactor (cleanup work)
REFACTOR_SOFT_CAP     = 0.20    # max above refactor_q — cheap tokens have limited reach
REFACTOR_DAYS_RATIO   = 0.60    # refactor takes this fraction of original craft_days

TOKEN_TYPES = ["Code", "Reasoning", "Image", "Voice", "Video"]

# ─────────────────────────────────────────────
# PROVIDERS — always on the map
# ─────────────────────────────────────────────
# Prices are PER MILLION TOKENS.

PROVIDERS = {
    # Prices roughly mirror real $/M token rates (with image/voice/video markups).
    "Anthropic": {
        "quality": 0.95,
        "desc": "Mature",
        "base_prices": {"Code": 8, "Reasoning": 30, "Image": 40, "Voice": 25, "Video": 50},
    },
    "OpenAI": {
        "quality": 0.90,
        "desc": "Mature",
        "base_prices": {"Code": 7, "Reasoning": 50, "Image": 20, "Voice": 15, "Video": 35},
    },
    "Google": {
        "quality": 0.70,
        "desc": "Growing",
        "base_prices": {"Code": 3, "Reasoning": 6, "Image": 2, "Voice": 3, "Video": 3},
    },
    "Meta": {
        "quality": 0.50,
        "desc": "Open Source",
        "base_prices": {"Code": 1, "Reasoning": 2, "Image": 3, "Voice": 4, "Video": 3},
    },
    "Mistral": {
        "quality": 0.62,
        "desc": "Emerging",
        "base_prices": {"Code": 2, "Reasoning": 5, "Image": 7, "Voice": 7, "Video": 5},
    },
}

# ─────────────────────────────────────────────
# PRODUCTS — crafting recipes (recipe units = millions of tokens)
# ─────────────────────────────────────────────

PRODUCTS = {
    # Recipe = millions of tokens consumed during the build (build + ops blend).
    # base_value = enterprise SaaS contract size, in dollars.
    "AI Customer Support": {
        "recipe":     {"Code": 50, "Voice": 30},
        "craft_days": 3,
        "base_value": 70_000,
    },
    "Contract Analyzer": {
        "recipe":     {"Reasoning": 80, "Code": 40},
        "craft_days": 4,
        "base_value": 110_000,
    },
    "Brand Asset Generator": {
        "recipe":     {"Image": 100, "Code": 20},
        "craft_days": 3,
        "base_value": 60_000,
    },
    "Compliance Dashboard": {
        "recipe":     {"Reasoning": 120, "Code": 60, "Image": 20},
        "craft_days": 5,
        "base_value": 240_000,
    },
    "Training Video Platform": {
        "recipe":     {"Video": 100, "Voice": 60, "Code": 30},
        "craft_days": 6,
        "base_value": 160_000,
    },
    "AI Security Scanner": {
        "recipe":     {"Reasoning": 80, "Code": 100},
        "craft_days": 4,
        "base_value": 130_000,
    },
    "Marketing Copilot": {
        "recipe":     {"Code": 60, "Image": 60, "Reasoning": 30},
        "craft_days": 4,
        "base_value": 90_000,
    },
}

# ─────────────────────────────────────────────
# CLIENTS — pool of buyers (4 active at a time)
# ─────────────────────────────────────────────

ALL_CLIENTS = [
    {
        "name": "Department of Defense",
        "type": "Government",
        "wants": ["Compliance Dashboard", "AI Security Scanner"],
        "budget_mult": (1.1, 1.6),
        "min_quality": 0.85,
    },
    {
        "name": "JPMorgan Chase",
        "type": "Enterprise",
        "wants": ["Contract Analyzer", "Compliance Dashboard", "AI Security Scanner"],
        "budget_mult": (1.0, 1.4),
        "min_quality": 0.78,
    },
    {
        "name": "Walmart",
        "type": "Enterprise",
        "wants": ["AI Customer Support", "Marketing Copilot"],
        "budget_mult": (0.8, 1.2),
        "min_quality": 0.65,
    },
    {
        "name": "NHS Digital",
        "type": "Government",
        "wants": ["Training Video Platform", "Compliance Dashboard"],
        "budget_mult": (1.0, 1.5),
        "min_quality": 0.80,
    },
    {
        "name": "Shopify",
        "type": "Enterprise",
        "wants": ["Marketing Copilot", "AI Customer Support", "Brand Asset Generator"],
        "budget_mult": (0.7, 1.1),
        "min_quality": 0.60,
    },
    {
        "name": "European Commission",
        "type": "Government",
        "wants": ["Compliance Dashboard", "Contract Analyzer"],
        "budget_mult": (1.2, 1.7),
        "min_quality": 0.88,
    },
    {
        "name": "Salesforce",
        "type": "Enterprise",
        "wants": ["AI Customer Support", "Contract Analyzer", "Marketing Copilot"],
        "budget_mult": (0.9, 1.3),
        "min_quality": 0.72,
    },
    {
        "name": "Deloitte",
        "type": "Enterprise",
        "wants": ["Training Video Platform", "Brand Asset Generator", "Compliance Dashboard"],
        "budget_mult": (0.8, 1.2),
        "min_quality": 0.68,
    },
    {
        "name": "US Veterans Affairs",
        "type": "Government",
        "wants": ["AI Customer Support", "Training Video Platform"],
        "budget_mult": (0.95, 1.35),
        "min_quality": 0.75,
    },
    {
        "name": "Stripe",
        "type": "Enterprise",
        "wants": ["AI Security Scanner", "Contract Analyzer"],
        "budget_mult": (0.9, 1.3),
        "min_quality": 0.75,
    },
]

# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────

def _provider_price_spike(state, provider, token, factor):
    if provider in state["provider_prices"]:
        p = state["provider_prices"][provider][token]
        state["provider_prices"][provider][token] = int(p * factor)

def _provider_price_crash(state, provider, token, factor):
    if provider in state["provider_prices"]:
        p = state["provider_prices"][provider][token]
        state["provider_prices"][provider][token] = max(5, int(p * factor))

def _all_provider_spike(state, token, factor):
    for prov in state["provider_prices"]:
        p = state["provider_prices"][prov][token]
        state["provider_prices"][prov][token] = int(p * factor)

def _all_provider_crash(state, token, factor):
    for prov in state["provider_prices"]:
        p = state["provider_prices"][prov][token]
        state["provider_prices"][prov][token] = max(5, int(p * factor))

def _client_budget_spike(state, product):
    for c in state["active_clients"]:
        if product in c["current_wants"]:
            c["current_wants"][product]["budget"] = int(c["current_wants"][product]["budget"] * 1.6)

def _client_budget_crash(state, product):
    for c in state["active_clients"]:
        if product in c["current_wants"]:
            c["current_wants"][product]["budget"] = int(c["current_wants"][product]["budget"] * 0.5)

def _gov_budget_boost(state):
    for c in state["active_clients"]:
        if c["type"] == "Government":
            for p in c["current_wants"]:
                c["current_wants"][p]["budget"] = int(c["current_wants"][p]["budget"] * 1.5)

def _bonus_cash(state, amount):
    state["cash"] = max(0, state["cash"] + amount)

def _craft_setback(state):
    if state["crafting"]:
        state["crafting"]["days_left"] += 2
        state["crafting"]["quality"] = max(0.3, state["crafting"]["quality"] - 0.1)

def _token_decay(state):
    """Quality of all stored tokens drops slightly (model deprecation)."""
    for data in state["tokens"].values():
        if data["qty"] > 0:
            current_avg = data["quality_sum"] / data["qty"]
            new_avg = max(0.3, current_avg - 0.08)
            data["quality_sum"] = new_avg * data["qty"]

EVENTS = [
    {
        "msg": "🔥 OpenAI rate limits spiked — Code tokens 2x at OpenAI!",
        "fn":  lambda s: _provider_price_spike(s, "OpenAI", "Code", 2.0),
    },
    {
        "msg": "🆓 Meta open-sourced a new model — their tokens are dirt cheap!",
        "fn":  lambda s: [_provider_price_crash(s, "Meta", t, 0.4) for t in TOKEN_TYPES],
    },
    {
        "msg": "🇪🇺 EU AI Act passed — Compliance Dashboards in huge demand!",
        "fn":  lambda s: _client_budget_spike(s, "Compliance Dashboard"),
    },
    {
        "msg": "🥶 AI winter fears — Reasoning token prices collapse everywhere.",
        "fn":  lambda s: _all_provider_crash(s, "Reasoning", 0.4),
    },
    {
        "msg": "📱 Viral AI app — everyone wants Code tokens! Prices doubled.",
        "fn":  lambda s: _all_provider_spike(s, "Code", 2.0),
    },
    {
        "msg": "🎨 Sora competitor launched — Video tokens flood the market.",
        "fn":  lambda s: _all_provider_crash(s, "Video", 0.5),
    },
    {
        "msg": "🔒 Major breach — AI Security Scanners in massive demand!",
        "fn":  lambda s: _client_budget_spike(s, "AI Security Scanner"),
    },
    {
        "msg": "📉 Enterprise budget freeze — all client budgets squeezed.",
        "fn":  lambda s: [_client_budget_crash(s, p) for p in PRODUCTS],
    },
    {
        "msg": "🏛️ Gov digital push — government clients raising budgets!",
        "fn":  lambda s: _gov_budget_boost(s),
    },
    {
        "msg": "🎉 You nailed a pitch! A client threw in a bonus — +$15,000.",
        "fn":  lambda s: _bonus_cash(s, 15_000),
    },
    {
        "msg": "💸 Your demo crashed mid-meeting. Embarrassing. -$12,000 in damages.",
        "fn":  lambda s: _bonus_cash(s, -12_000),
    },
    {
        "msg": "🤖 Anthropic shipped a breakthrough — their prices jump on demand!",
        "fn":  lambda s: [_provider_price_spike(s, "Anthropic", t, 1.5) for t in TOKEN_TYPES],
    },
    {
        "msg": "🗣️ Voice AI craze — Voice tokens triple everywhere!",
        "fn":  lambda s: _all_provider_spike(s, "Voice", 3.0),
    },
    {
        "msg": "📊 Google slashed prices to compete — everything cheap at Google!",
        "fn":  lambda s: [_provider_price_crash(s, "Google", t, 0.5) for t in TOKEN_TYPES],
    },
    {
        "msg": "🏢 Salesforce raised their budget — Marketing Copilots wanted!",
        "fn":  lambda s: _client_budget_spike(s, "Marketing Copilot"),
    },
    {
        "msg": "⚠️  Production bug! Your build hit a snag — +2 craft days, -10% quality.",
        "fn":  lambda s: _craft_setback(s),
    },
    {
        "msg": "📉 Model deprecations announced — stored token quality decayed.",
        "fn":  lambda s: _token_decay(s),
    },
    {
        "msg": "🏦 Investor margin call — surprise debt fee of $20,000.",
        "fn":  lambda s: _bonus_cash(s, -20_000),
    },
]

# ─────────────────────────────────────────────
# GAME STATE
# ─────────────────────────────────────────────

def new_game():
    state = {
        "cash":             STARTING_CASH,
        "debt":             STARTING_DEBT,
        "day":              1,
        "location":         None,
        "location_type":    None,
        "tokens":           {},
        "products":         [],
        "crafting":         None,
        "provider_prices":  {},
        "active_clients":   [],
        "last_event":       None,
        "message":          None,
        "next_rotation":    0,
    }
    state["location"] = list(PROVIDERS.keys())[0]
    state["location_type"] = "provider"
    refresh_provider_prices(state)
    rotate_clients(state)
    return state

def _schedule_next_rotation(state):
    state["next_rotation"] = state["day"] + random.randint(CLIENT_ROTATION_MIN, CLIENT_ROTATION_MAX)

def refresh_provider_prices(state):
    for prov, data in PROVIDERS.items():
        state["provider_prices"][prov] = {}
        for token, base in data["base_prices"].items():
            noise = random.uniform(0.7, 1.4)
            state["provider_prices"][prov][token] = max(5, int(base * noise))

def _make_client_from_template(template):
    """Generate a fresh active client with random wants/budgets."""
    num_wants = min(len(template["wants"]), random.randint(1, 2))
    wanted = random.sample(template["wants"], num_wants)
    current_wants = {}
    for prod_name in wanted:
        prod = PRODUCTS[prod_name]
        lo, hi = template["budget_mult"]
        mult = random.uniform(lo, hi)
        budget = int(prod["base_value"] * mult)
        current_wants[prod_name] = {
            "budget": budget,
            "min_quality": template["min_quality"],
        }
    return {
        "name":          template["name"],
        "type":          template["type"],
        "min_quality":   template["min_quality"],
        "current_wants": current_wants,
    }

def _find_template(name):
    for t in ALL_CLIENTS:
        if t["name"] == name:
            return t
    return None

def rotate_clients(state):
    """Pick 4 random clients fresh (used at game start)."""
    chosen = random.sample(ALL_CLIENTS, 4)
    state["active_clients"] = [_make_client_from_template(t) for t in chosen]
    _schedule_next_rotation(state)

def partial_rotate_clients(state):
    """Replace 1-2 active clients with fresh ones from the pool."""
    n_replace = random.randint(1, 2)
    n_replace = min(n_replace, len(state["active_clients"]))
    indices = random.sample(range(len(state["active_clients"])), n_replace)
    current_names = {c["name"] for c in state["active_clients"]}
    pool = [t for t in ALL_CLIENTS if t["name"] not in current_names]
    if not pool:
        _schedule_next_rotation(state)
        return []
    new_templates = random.sample(pool, min(n_replace, len(pool)))
    replaced = []
    for idx, template in zip(indices, new_templates):
        replaced.append(state["active_clients"][idx]["name"])
        state["active_clients"][idx] = _make_client_from_template(template)
    _schedule_next_rotation(state)
    return replaced

def drift_clients(state):
    """Each day, small chance for active clients to shift budgets, drop wants, or add new ones."""
    for c in state["active_clients"]:
        # shift one budget
        if c["current_wants"] and random.random() < CLIENT_DRIFT_CHANCE:
            prod = random.choice(list(c["current_wants"].keys()))
            shift = random.uniform(0.75, 1.25)
            c["current_wants"][prod]["budget"] = int(c["current_wants"][prod]["budget"] * shift)
        # drop a want (only if more than one, so client doesn't become useless silently)
        if len(c["current_wants"]) > 1 and random.random() < CLIENT_DROP_CHANCE:
            prod = random.choice(list(c["current_wants"].keys()))
            del c["current_wants"][prod]
        # add a new want
        if random.random() < CLIENT_ADD_CHANCE:
            template = _find_template(c["name"])
            if template:
                available = [w for w in template["wants"] if w not in c["current_wants"]]
                if available:
                    new_prod_name = random.choice(available)
                    prod = PRODUCTS[new_prod_name]
                    lo, hi = template["budget_mult"]
                    mult = random.uniform(lo, hi)
                    c["current_wants"][new_prod_name] = {
                        "budget":      int(prod["base_value"] * mult),
                        "min_quality": template["min_quality"],
                    }

def token_total(state):
    return sum(t["qty"] for t in state["tokens"].values())

def token_free(state):
    return MAX_TOKENS - token_total(state)

def token_avg_quality(state, token_type):
    t = state["tokens"].get(token_type)
    if not t or t["qty"] == 0:
        return 0.0
    return t["quality_sum"] / t["qty"]

def net_worth(state):
    return state["cash"] - state["debt"]

# ─────────────────────────────────────────────
# TIME
# ─────────────────────────────────────────────

def _recipe_size(product_name):
    return sum(PRODUCTS[product_name]["recipe"].values())

def advance_days(state, days):
    """Advance time: debt interest, craft progress + decay, product decay, events, drift, rotation."""
    for _ in range(days):
        state["day"] += 1
        decay_notes = []

        # Debt interest
        if state["debt"] > 0:
            interest = int(state["debt"] * DEBT_INTEREST)
            state["debt"] += interest

        # Crafting progress + per-day decay risk (bigger builds = riskier)
        if state["crafting"]:
            size = _recipe_size(state["crafting"]["name"])
            chance = CRAFT_DECAY_BASE + size * DECAY_SIZE_FACTOR
            if random.random() < chance:
                drop = random.uniform(0.04, 0.12)
                old_q = state["crafting"]["quality"]
                state["crafting"]["quality"] = max(0.30, old_q - drop)
                decay_notes.append(
                    f"build of {state['crafting']['name']} hit a snag "
                    f"({old_q:.0%}→{state['crafting']['quality']:.0%})"
                )
            state["crafting"]["days_left"] -= 1
            if state["crafting"]["days_left"] <= 0:
                # Final variance on completion
                final_q = state["crafting"]["quality"] * random.uniform(0.92, 1.05)
                final_q = max(0.30, min(1.0, final_q))
                finished = {
                    "name":    state["crafting"]["name"],
                    "quality": final_q,
                }
                state["products"].append(finished)
                state["message"] = (
                    f"✅ Finished {finished['name']}! Final quality: {finished['quality']:.0%}"
                )
                state["crafting"] = None

        # Per-day decay risk for finished products sitting on the shelf
        for p in state["products"]:
            size = _recipe_size(p["name"])
            chance = PRODUCT_DECAY_BASE + size * DECAY_SIZE_FACTOR
            if random.random() < chance:
                drop = random.uniform(0.03, 0.07)
                old_q = p["quality"]
                p["quality"] = max(0.30, old_q - drop)
                decay_notes.append(
                    f"{p['name']} deprecated ({old_q:.0%}→{p['quality']:.0%})"
                )

        # Event roll (~30% chance)
        if random.random() < 0.30:
            event = random.choice(EVENTS)
            event["fn"](state)
            state["last_event"] = event["msg"]
        elif decay_notes:
            # Surface decay if no other event already grabbed last_event
            state["last_event"] = "📉 Model deprecation: " + "; ".join(decay_notes[:2])

        # Daily client drift
        drift_clients(state)

        # Partial roster rotation
        if state["day"] >= state["next_rotation"]:
            replaced = partial_rotate_clients(state)
            if replaced and not state["last_event"]:
                names = ", ".join(replaced)
                state["last_event"] = f"📋 Roster shift — {names} dropped, new clients arrived."

# ─────────────────────────────────────────────
# ACTIONS
# ─────────────────────────────────────────────

def do_buy_tokens(state, token_type, qty):
    prov = state["location"]
    price = state["provider_prices"][prov][token_type]
    cost = price * qty
    quality = PROVIDERS[prov]["quality"]
    if cost > state["cash"]:
        return f"Not enough cash (need ${cost:,}, have ${state['cash']:,})."
    if qty > token_free(state):
        return f"Not enough storage (need {qty}M, have {token_free(state)}M free)."
    state["cash"] -= cost
    if token_type not in state["tokens"]:
        state["tokens"][token_type] = {"qty": 0, "quality_sum": 0.0}
    state["tokens"][token_type]["qty"] += qty
    state["tokens"][token_type]["quality_sum"] += qty * quality
    return f"Bought {qty}M {token_type} tokens from {prov} for ${cost:,}. (quality: {quality:.0%})"

def can_craft(state, product_name):
    recipe = PRODUCTS[product_name]["recipe"]
    for token_type, needed in recipe.items():
        held = state["tokens"].get(token_type, {"qty": 0})["qty"]
        if held < needed:
            return False
    return True

def do_craft(state, product_name):
    if state["crafting"]:
        return f"Already crafting {state['crafting']['name']} ({state['crafting']['days_left']}d left)."
    prod = PRODUCTS[product_name]
    recipe = prod["recipe"]
    if not can_craft(state, product_name):
        missing = []
        for t, need in recipe.items():
            held = state["tokens"].get(t, {"qty": 0})["qty"]
            if held < need:
                missing.append(f"{t}: need {need}M, have {held}M")
        return "Missing tokens — " + ", ".join(missing)
    total_tokens = sum(recipe.values())
    quality_sum = 0.0
    for token_type, needed in recipe.items():
        avg_q = token_avg_quality(state, token_type)
        quality_sum += avg_q * needed
        state["tokens"][token_type]["qty"] -= needed
        state["tokens"][token_type]["quality_sum"] -= avg_q * needed
        if state["tokens"][token_type]["qty"] <= 0:
            del state["tokens"][token_type]
    quality = quality_sum / total_tokens
    state["crafting"] = {
        "name":      product_name,
        "quality":   quality,
        "days_left": prod["craft_days"],
    }
    return f"Started crafting {product_name}! Ready in {prod['craft_days']} days. (quality: {quality:.0%})"

def _refactor_range(product_name):
    """Return (min_code, max_code) tokens used by a refactor (Code only, randomized)."""
    total = sum(PRODUCTS[product_name]["recipe"].values())
    return (int(round(total * REFACTOR_MIN_RATIO)),
            int(round(total * REFACTOR_MAX_RATIO)))

def _roll_refactor_cost(product_name):
    """Roll the actual Code-only refactor cost for this attempt."""
    total = sum(PRODUCTS[product_name]["recipe"].values())
    qty = int(round(total * random.uniform(REFACTOR_MIN_RATIO, REFACTOR_MAX_RATIO)))
    return {"Code": qty}

def do_refactor(state, product_idx):
    if state["crafting"]:
        return f"Already crafting {state['crafting']['name']} ({state['crafting']['days_left']}d left)."
    if product_idx < 0 or product_idx >= len(state["products"]):
        return "Invalid product."
    product = state["products"][product_idx]
    needed = _roll_refactor_cost(product["name"])

    missing = []
    for t, n in needed.items():
        held = state["tokens"].get(t, {"qty": 0})["qty"]
        if held < n:
            missing.append(f"{t}: need {n}M, have {held}M")
    if missing:
        return "Refactor rolled cost " + ", ".join(f"{n}M {t}" for t, n in needed.items()) + " — " + ", ".join(missing)

    # Token quality of what we'd spend (Code-only)
    total_q_sum = 0.0
    total_qty = 0
    for t, n in needed.items():
        avg_q = token_avg_quality(state, t)
        total_q_sum += avg_q * n
        total_qty += n
    refactor_q = total_q_sum / total_qty if total_qty else 0.0

    current_q = product["quality"]
    gap_lift = max(0, refactor_q - current_q) * REFACTOR_QUALITY_LIFT
    target_q = current_q + REFACTOR_SMALL_LIFT + gap_lift
    # Soft cap: cheap tokens can polish but can't push quality far past their own ceiling
    target_q = min(target_q, refactor_q + REFACTOR_SOFT_CAP)
    target_q = max(target_q, current_q)         # never decrease
    target_q = min(0.99, target_q)
    if target_q - current_q < 0.01:
        return (f"Refactor wouldn't help — {product['name']} at {current_q:.0%}, "
                f"refactor pool only {refactor_q:.0%} (capped at {refactor_q + REFACTOR_SOFT_CAP:.0%}). "
                f"Buy higher-quality tokens.")

    # Consume tokens
    for t, n in needed.items():
        avg_q = token_avg_quality(state, t)
        state["tokens"][t]["qty"] -= n
        state["tokens"][t]["quality_sum"] -= avg_q * n
        if state["tokens"][t]["qty"] <= 0:
            del state["tokens"][t]

    refactor_days = max(1, int(PRODUCTS[product["name"]]["craft_days"] * REFACTOR_DAYS_RATIO))
    state["crafting"] = {
        "name":      product["name"],
        "quality":   target_q,
        "days_left": refactor_days,
    }
    state["products"].pop(product_idx)
    return (f"🔧 Refactoring {product['name']}: {current_q:.0%} → ~{target_q:.0%} "
            f"in {refactor_days} day(s).")

def do_sell_product(state, product_idx, client_idx):
    if client_idx < 0 or client_idx >= len(state["active_clients"]):
        return "Invalid client."
    if product_idx < 0 or product_idx >= len(state["products"]):
        return "Invalid product."
    client = state["active_clients"][client_idx]
    product = state["products"][product_idx]
    if product["name"] not in client["current_wants"]:
        return f"{client['name']} doesn't want {product['name']} right now."
    contract = client["current_wants"][product["name"]]
    if product["quality"] < contract["min_quality"]:
        return (f"❌ Quality too low ({product['quality']:.0%}). "
                f"{client['name']} needs {contract['min_quality']:.0%}+.")
    quality_bonus = product["quality"] / contract["min_quality"]
    revenue = int(contract["budget"] * min(quality_bonus, QUALITY_BONUS_CAP))
    state["cash"] += revenue
    state["products"].pop(product_idx)
    del client["current_wants"][product["name"]]
    return f"💰 SOLD {product['name']} to {client['name']} for ${revenue:,}! Cash: ${state['cash']:,}"

def do_travel(state, dest_name, dest_type):
    if dest_name == state["location"]:
        return "You're already there."
    if state["cash"] < TRAVEL_COST:
        return f"Need ${TRAVEL_COST} travel budget."
    state["cash"] -= TRAVEL_COST
    state["location"] = dest_name
    state["location_type"] = dest_type
    if dest_type == "provider":
        prov = PROVIDERS[dest_name]
        state["provider_prices"][dest_name] = {}
        for token, base in prov["base_prices"].items():
            noise = random.uniform(0.7, 1.4)
            state["provider_prices"][dest_name][token] = max(5, int(base * noise))
    advance_days(state, 1)
    return None

def do_pay_debt(state, amount):
    if amount <= 0:
        return "Enter a positive amount."
    if amount > state["cash"]:
        return "Not enough cash."
    if amount > state["debt"]:
        amount = state["debt"]
    state["cash"] -= amount
    state["debt"] -= amount
    return f"Paid ${amount:,} toward debt. Remaining: ${state['debt']:,}."

# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────

WIDTH = 64

# Tasteful ANSI colors — visible info first, decoration second.
class _C:
    RESET     = "\033[0m"
    BOLD      = "\033[1m"
    DIM       = "\033[2m"
    RED       = "\033[31m"
    GREEN     = "\033[32m"
    YELLOW    = "\033[33m"
    BLUE      = "\033[34m"
    MAGENTA   = "\033[35m"
    CYAN      = "\033[36m"
    BR_RED    = "\033[91m"
    BR_GREEN  = "\033[92m"
    BR_YELLOW = "\033[93m"
    BR_CYAN   = "\033[96m"

def _col(text, *codes):
    return f"{''.join(codes)}{text}{_C.RESET}"

def _cash_color(amt):
    if amt >= 50_000: return _C.BR_GREEN
    if amt >= 10_000: return _C.GREEN
    if amt >=  5_000: return _C.YELLOW
    return _C.BR_RED

def _quality_color(q):
    if q >= 0.85: return _C.BR_GREEN
    if q >= 0.70: return _C.GREEN
    if q >= 0.55: return _C.YELLOW
    return _C.BR_RED

def _price_color(price, base):
    ratio = price / base if base else 1.0
    if ratio <= 0.85: return _C.GREEN
    if ratio >= 1.30: return _C.RED
    return _C.YELLOW

def _key(letter, rest):
    return f"[{_col(letter, _C.BOLD, _C.BR_CYAN)}]{rest}"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def rule(char="─"):
    if char == "═":
        print(_col(char * WIDTH, _C.BOLD, _C.BR_CYAN))
    else:
        print(_col(char * WIDTH, _C.DIM))

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
        loc_label += f" ({PROVIDERS[state['location']]['desc']})"
    else:
        for c in state["active_clients"]:
            if c["name"] == state["location"]:
                loc_label += f" ({c['type']})"
                break
    title = _col("CODE WARS", _C.BOLD, _C.BR_CYAN)
    day = _col(f"Day {state['day']}/{MAX_DAYS}", _C.BR_YELLOW)
    loc_color = _C.CYAN if state["location_type"] == "provider" else _C.MAGENTA
    loc = _col(loc_label, _C.BOLD, loc_color)
    print(f"  {title}  |  {day}  |  {loc}")
    rule("═")
    nw = net_worth(state)
    nw_sign = "+" if nw >= 0 else ""
    cash_str = _col(f"${state['cash']:>9,}", _cash_color(state["cash"]))
    nw_color = _C.BR_GREEN if nw >= 0 else _C.BR_RED
    nw_str = _col(f"{nw_sign}${nw:,}", nw_color)
    debt_str = _col(f"${state['debt']:>9,}", _C.RED if state["debt"] > 0 else _C.GREEN)
    tok = token_total(state)
    storage_str = _col(f"{tok}M/{MAX_TOKENS}M",
                       _C.YELLOW if tok > MAX_TOKENS * 0.8 else _C.CYAN)
    print(f"  💰 Cash: {cash_str}   🎯 Net Worth: {nw_str}")
    print(f"  💳 Debt: {debt_str}   📦 Token Storage: {storage_str}")
    if state["crafting"]:
        c = state["crafting"]
        name_str = _col(c["name"], _C.MAGENTA)
        q_str = _col(f"{c['quality']:.0%}", _quality_color(c["quality"]))
        days_str = _col(f"{c['days_left']}d", _C.YELLOW)
        print(f"  🔨 Crafting: {name_str} ({days_str} left, {q_str} quality)")
    rule()

def status_bar(state):
    """Compact one-liner re-stating cash/debt/day/storage right above the action prompt."""
    crafting = ""
    if state["crafting"]:
        c = state["crafting"]
        name_str = _col(c["name"], _C.MAGENTA)
        q_str = _col(f"{c['quality']:.0%}", _quality_color(c["quality"]))
        crafting = f"   🔨 {name_str} ({c['days_left']}d, {q_str})"
    cash_str = _col(f"${state['cash']:,}", _cash_color(state["cash"]))
    debt_str = _col(f"${state['debt']:,}", _C.RED if state["debt"] > 0 else _C.GREEN)
    day_str = _col(f"Day {state['day']}/{MAX_DAYS}", _C.BR_YELLOW)
    tok = token_total(state)
    storage_str = _col(f"{tok}M/{MAX_TOKENS}M",
                       _C.YELLOW if tok > MAX_TOKENS * 0.8 else _C.CYAN)
    rule()
    print(f"  💰 {cash_str}   💳 {debt_str}   📅 {day_str}   📦 {storage_str}{crafting}")
    rule()

def show_event(state):
    if state["last_event"]:
        print(_col(f"\n  ⚡ {state['last_event']}\n", _C.BR_YELLOW))
        state["last_event"] = None

def show_message(state):
    if state["message"]:
        rule()
        print(_col(f"  ➤  {state['message']}", _C.BOLD, _C.BR_CYAN))
        rule()
        state["message"] = None

def show_provider(state):
    prov = state["location"]
    quality = PROVIDERS[prov]["quality"]
    prices = state["provider_prices"][prov]
    base_prices = PROVIDERS[prov]["base_prices"]
    prov_str = _col(prov, _C.BOLD, _C.CYAN)
    q_str = _col(f"{quality:.0%}", _quality_color(quality))
    print(f"\n  Token prices at {prov_str} (quality: {q_str}, per million):\n")
    head = f"  {'#':<4} {'Token':<12} {'$/M':>8}   {'You Have':>10}"
    print(_col(head, _C.BOLD))
    print(f"  {_col('─'*4, _C.DIM)} {_col('─'*12, _C.DIM)} {_col('─'*8, _C.DIM)}   {_col('─'*10, _C.DIM)}")
    for i, token in enumerate(TOKEN_TYPES, 1):
        price = prices[token]
        base = base_prices[token]
        held = state["tokens"].get(token, {"qty": 0})["qty"]
        avg_q = token_avg_quality(state, token)
        price_str = _col(f"${price:>7,}", _price_color(price, base))
        tok_color = _C.CYAN if held > 0 else _C.DIM
        token_str = _col(f"{token:<12}", tok_color)
        if held > 0:
            q_part = _col(f"({avg_q:.0%}q)", _quality_color(avg_q))
            visible = f"{held}M ({avg_q:.0%}q)"
            held_str = " " * max(0, 10 - len(visible)) + f"{held}M {q_part}"
        else:
            held_str = " " * 9 + _col("—", _C.DIM)
        print(f"  {i:<4} {token_str} {price_str}   {held_str}")

def show_client_offers(state):
    loc_str = _col(state["location"], _C.BOLD, _C.MAGENTA)
    print(f"\n  {loc_str} wants:\n")
    client = None
    for c in state["active_clients"]:
        if c["name"] == state["location"]:
            client = c
            break
    if not client or not client["current_wants"]:
        print(_col("  (this client has no open contracts right now)", _C.DIM))
        return
    head = f"  {'#':<4} {'Product':<26} {'Pays':>8}   {'Min Quality':>11}"
    print(_col(head, _C.BOLD))
    print(f"  {_col('─'*4, _C.DIM)} {_col('─'*26, _C.DIM)} {_col('─'*8, _C.DIM)}   {_col('─'*11, _C.DIM)}")
    for i, (prod, info) in enumerate(client["current_wants"].items(), 1):
        prod_str = _col(f"{prod:<26}", _C.CYAN)
        budget_str = _col(f"${info['budget']:>7,}", _C.BR_GREEN)
        mq_str = _col(f"{info['min_quality']:>10.0%}", _quality_color(info["min_quality"]))
        print(f"  {i:<4} {prod_str} {budget_str}   {mq_str}")

def show_tokens(state):
    if not state["tokens"]:
        print(_col("\n  Tokens: (none)", _C.DIM))
        return
    print(_col("\n  Your tokens:", _C.BOLD))
    for token, data in state["tokens"].items():
        avg_q = data["quality_sum"] / data["qty"] if data["qty"] > 0 else 0
        tok_str = _col(f"{token:<12}", _C.CYAN)
        qty_str = _col(f"{data['qty']}M", _C.BR_CYAN)
        q_str = _col(f"{avg_q:.0%}", _quality_color(avg_q))
        print(f"    {tok_str} {qty_str}  (avg quality: {q_str})")

def show_products(state):
    if not state["products"]:
        print(_col("\n  Built products: (none)", _C.DIM))
        return
    print(_col("\n  Built products:", _C.BOLD))
    for i, p in enumerate(state["products"], 1):
        name_str = _col(p["name"], _C.MAGENTA)
        q_str = _col(f"{p['quality']:.0%}", _quality_color(p["quality"]))
        print(f"    {i}. {name_str}  (quality: {q_str})")

def show_craftable(state):
    print(_col("\n  Product catalog — costs to craft & base contract value:", _C.BOLD))
    head = f"  {'#':<3}{'Product':<24}{'Build':>6}  {'Recipe (M tokens)':<40}{'Base $':>8}  Ready"
    print(_col(head, _C.BOLD))
    print(f"  {_col('─'*3, _C.DIM)}{_col('─'*24, _C.DIM)}{_col('─'*6, _C.DIM)}  "
          f"{_col('─'*40, _C.DIM)}{_col('─'*8, _C.DIM)}  {_col('─'*5, _C.DIM)}")
    for i, (name, prod) in enumerate(PRODUCTS.items(), 1):
        recipe_str = " + ".join(f"{n}M {t}" for t, n in prod["recipe"].items())
        buildable = can_craft(state, name)
        ready_str = _col("✓", _C.BR_GREEN) if buildable else _col("·", _C.DIM)
        base_raw = f"${prod['base_value']//1000}K"
        base_str = _col(f"{base_raw:>8}", _C.BR_GREEN)
        name_str = _col(f"{name:<24}", _C.BR_CYAN if buildable else _C.CYAN)
        days_str = _col(f"{prod['craft_days']:>5}d", _C.YELLOW)
        print(f"  {i:<3}{name_str}{days_str}  {recipe_str:<40}{base_str}    {ready_str}")

def show_all_clients(state):
    print(_col("\n  Active client contracts:", _C.BOLD))
    for c in state["active_clients"]:
        is_gov = c["type"] == "Government"
        tag_color = _C.BLUE if is_gov else _C.MAGENTA
        tag = _col("GOV" if is_gov else "ENT", _C.BOLD, tag_color)
        name_str = _col(f"{c['name']:<25}", _C.BOLD)
        if c["current_wants"]:
            wants_str = _col(", ".join(c["current_wants"].keys()), _C.CYAN)
        else:
            wants_str = _col("(satisfied)", _C.DIM)
        print(f"    [{tag}] {name_str} wants: {wants_str}")

def prompt_int(label):
    try:
        val = input(f"  {label}: ").strip()
        return int(val)
    except (ValueError, EOFError):
        return None

def prompt_str(label):
    try:
        return input(f"  {label}: ").strip()
    except EOFError:
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
    if choice is None or choice == 0:
        return
    if not (1 <= choice <= len(TOKEN_TYPES)):
        state["message"] = "Invalid choice."
        return
    token = TOKEN_TYPES[choice - 1]
    qty = prompt_int("Quantity (millions)")
    if not qty or qty < 1:
        state["message"] = "Invalid quantity."
        return
    state["message"] = do_buy_tokens(state, token, qty)

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
    if pidx is None or pidx == 0:
        return
    state["message"] = do_sell_product(state, pidx - 1, client_idx)
    pause()

def menu_craft(state):
    if state["crafting"]:
        state["message"] = f"Already crafting {state['crafting']['name']} ({state['crafting']['days_left']}d left)."
        return
    show_tokens(state)
    show_craftable(state)
    print()
    choice = prompt_int(f"Product # to craft (1-{len(PRODUCTS)}, or 0 to cancel)")
    if choice is None or choice == 0:
        return
    if not (1 <= choice <= len(PRODUCTS)):
        state["message"] = "Invalid choice."
        return
    product_name = list(PRODUCTS.keys())[choice - 1]
    state["message"] = do_craft(state, product_name)

def menu_refactor(state):
    if state["crafting"]:
        state["message"] = f"Already crafting {state['crafting']['name']} ({state['crafting']['days_left']}d left)."
        return
    if not state["products"]:
        state["message"] = "No finished products to refactor. Craft something first."
        return
    show_tokens(state)
    code_held = state["tokens"].get("Code", {"qty": 0})["qty"]
    print(f"\n  Refactor a finished product (Code-only, random {REFACTOR_MIN_RATIO:.0%}-{REFACTOR_MAX_RATIO:.0%} of original recipe):")
    print(f"  {'#':<4} {'Product':<26} {'Cur Q':>6}   {'Cost range':<18} {'Worst-case OK?':>16}")
    print(f"  {'─'*4} {'─'*26} {'─'*6}   {'─'*18} {'─'*16}")
    for i, p in enumerate(state["products"], 1):
        lo, hi = _refactor_range(p["name"])
        cost_str = f"{lo}M-{hi}M Code"
        ok = code_held >= hi
        print(f"  {i:<4} {p['name']:<26} {p['quality']:>5.0%}   {cost_str:<18} {('Yes' if ok else f'risky ({code_held}M held)'):>16}")
    print(f"\n  Code Quality lifts: +{REFACTOR_SMALL_LIFT:.0%} flat, plus {REFACTOR_QUALITY_LIFT:.0%} of any positive gap.")
    print(f"  Cheap Code tokens give a small lift; capped at Code quality + {REFACTOR_SOFT_CAP:.0%}.")
    print(f"  Refactor takes ~{REFACTOR_DAYS_RATIO:.0%} of original craft days.\n")
    choice = prompt_int(f"Product # to refactor (1-{len(state['products'])}, or 0 to cancel)")
    if not choice or choice == 0:
        return
    if not (1 <= choice <= len(state["products"])):
        state["message"] = "Invalid choice."
        return
    state["message"] = do_refactor(state, choice - 1)

def menu_travel(state):
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
    for c in state["active_clients"]:
        if c["name"] != state["location"]:
            destinations.append((c["name"], "client"))
            idx = len(destinations)
            tag = "GOV" if c["type"] == "Government" else "ENT"
            wants = ", ".join(c["current_wants"].keys()) if c["current_wants"] else "(satisfied)"
            print(f"    {idx}. [{tag}] {c['name']}  — wants: {wants}")
    print(f"\n  (Travel costs ${TRAVEL_COST} + 1 day)\n")
    choice = prompt_int(f"Choose 1-{len(destinations)} (or 0 to cancel)")
    if choice is None or choice == 0:
        return
    if not (1 <= choice <= len(destinations)):
        state["message"] = "Invalid choice."
        return
    dest_name, dest_type = destinations[choice - 1]
    err = do_travel(state, dest_name, dest_type)
    if err:
        state["message"] = err
    else:
        if not state["message"]:
            state["message"] = f"Travelled to {dest_name}. Day advanced."

def menu_wait(state):
    days = prompt_int("Days to wait (1-5, or 0 to cancel)")
    if not days or days == 0:
        return
    days = max(1, min(5, days))
    advance_days(state, days)
    if not state["message"]:
        state["message"] = f"Waited {days} day(s)."

def menu_pay_debt(state):
    print(f"\n  Outstanding debt: ${state['debt']:,}")
    if state["debt"] == 0:
        state["message"] = "You're debt-free!"
        return
    amount = prompt_int("Amount to pay (0 to cancel)")
    if not amount or amount == 0:
        return
    state["message"] = do_pay_debt(state, amount)

# ─────────────────────────────────────────────
# END SCREEN
# ─────────────────────────────────────────────

def end_screen(state):
    clear()
    rule("═")
    print("  GAME OVER — Performance Review")
    rule("═")
    nw = net_worth(state)
    print(f"\n  Cash:        ${state['cash']:>10,}")
    print(f"  Debt:        ${state['debt']:>10,}")
    print(f"  Net Worth:   ${nw:>10,}")
    print(f"  Products built: {len(state['products'])} unsold\n")
    rule()
    if nw >= 1_000_000:
        grade = "🏆 UNICORN — You disrupted the market. IPO incoming."
    elif nw >= 500_000:
        grade = "🌟 SERIES A — Strong traction. Investors are lining up."
    elif nw >= 100_000:
        grade = "✅ RAMEN PROFITABLE — Scrappy, but you made it work."
    elif nw >= 0:
        grade = "😅 BROKE EVEN — The vibes were mid."
    else:
        grade = "💀 BANKRUPT — The vibes were NOT coding."
    print(f"\n  {grade}\n")
    rule("═")

# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def has_any_option(state):
    """Return True if the player has any productive move left."""
    cash = state["cash"]
    # Travel anywhere
    if cash >= TRAVEL_COST:
        return True
    # Crafting in progress will eventually finish
    if state["crafting"]:
        return True
    # At a provider — can buy at least one cheap token
    if state["location_type"] == "provider" and cash > 0 and token_free(state) > 0:
        prices = state["provider_prices"][state["location"]]
        if any(prices[t] <= cash for t in TOKEN_TYPES):
            return True
    # Have enough tokens to craft something
    for prod_name in PRODUCTS:
        if can_craft(state, prod_name):
            return True
    # Have a finished product + Code tokens for at least the minimum refactor cost
    for prod in state["products"]:
        min_code, _ = _refactor_range(prod["name"])
        held_code = state["tokens"].get("Code", {"qty": 0})["qty"]
        if held_code >= min_code:
            return True
    # At a client where a finished product matches min quality
    if state["location_type"] == "client":
        for c in state["active_clients"]:
            if c["name"] == state["location"]:
                for p in state["products"]:
                    contract = c["current_wants"].get(p["name"])
                    if contract and p["quality"] >= contract["min_quality"]:
                        return True
    return False

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
    print("  No way to buy, craft, refactor, sell, or travel.")
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

        if state["location_type"] == "provider":
            show_provider(state)
        else:
            show_client_offers(state)

        show_tokens(state)
        show_products(state)
        show_craftable(state)
        show_all_clients(state)
        show_message(state)
        status_bar(state)
        primary = _key("B", "uy") if state["location_type"] == "provider" else _key("S", "ell")
        menu = "  ".join([
            primary,
            _key("C", "raft"),
            _key("R", "efactor"),
            _key("T", "ravel"),
            _key("W", "ait"),
            _key("P", "ay"),
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
        elif cmd == "r":
            menu_refactor(state)
        elif cmd == "t":
            menu_travel(state)
        elif cmd == "w":
            menu_wait(state)
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
    print("  CODE WARS — Where AI Meets Enterprise")
    rule("═")
    print("""
  You're a vibe-coding Senior PM hustling AI products.
  Travel to LLM providers to work on partnership deals and 
  buy tokens at a discount (in millions).
  Craft enterprise SaaS products from those tokens, then
  pitch and sell them to government and corporate clients.

  Buy cheap tokens, craft high-quality products,
  and sell before your debt eats you alive.

  Starting cash: $35K. Starting debt: $300K (compounding 2%/day).

  - Travel/sales trip costs $30K + 1 day (flights, decks, dinners…)
  - Crafting takes 3-6 days (50-200M tokens per build)
  - Token storage capped at 500M
  - Clients rotate every 3-7 days
  - Token quality (model maturity) gates client sales
  - Cap on quality bonus — over-spec doesn't pay extra

  You have 30 days to clear the debt and build a real business.
""")
    rule()
    input("  Press ENTER to start...")
    state = new_game()
    game_loop(state)


if __name__ == "__main__":
    main()
