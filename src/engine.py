#!/usr/bin/env python3
"""
Hallucination Inc. — game engine.

Pure game logic with no terminal I/O. Imports cleanly into any frontend
(terminal, web, headless simulator). The contract:

- All game state lives in a plain dict (see ``new_game``).
- Action functions (``do_buy_tokens``, ``do_craft``, ``do_sell_product``,
  ``do_travel``, ``do_borrow``, ``do_pay_debt``) return ``(ok: bool, msg: str)``
  and mutate state in place. The ``msg`` is a user-facing string but contains
  no ANSI codes — frontends can render it as-is.
- Time progression goes through ``advance_days``. Any event side effects,
  decay, drift, and roster rotation are funneled here.
- ``has_any_option`` is the bankruptcy oracle. ``is_bankrupt`` and
  ``is_game_over`` are pure-bool helpers frontends use to drive end screens.
- Two presentation hints live on the state dict: ``state["message"]`` for the
  most recent action result and ``state["last_event"]`` for the daily event
  banner. Engine writes them; frontends read and clear them.

If you add a new action that costs or produces resources, also reflect it in
``has_any_option`` or the game can soft-lock instead of ending cleanly.
"""

import random

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

MAX_DAYS              = 30
STARTING_CASH         = 100_000
STARTING_DEBT         = 100_000
DEBT_INTEREST         = 0.03    # 3% per day on outstanding debt
DEBT_FREE_BONUS       = 75_000  # bonus to net worth at game end if debt is fully paid
COLLATERAL_LTV        = 0.30    # max loan as % of finished product base value
TRAVEL_COST           = 30_000  # biz dev / sales travel — pitch decks aren't free
MAX_TOKENS            = 500     # max storage in millions of tokens
QUALITY_BONUS_CAP     = 1.5     # max premium for over-spec quality
ACTIVE_CLIENT_COUNT   = 6       # number of clients live on the board at once
CLIENT_ROTATION_MIN   = 3       # min days between partial rotations
CLIENT_ROTATION_MAX   = 7       # max days between partial rotations
CLIENT_DRIFT_CHANCE   = 0.10    # daily chance per client to shift a budget
CLIENT_DROP_CHANCE    = 0.05    # daily chance per client to drop a want
CLIENT_ADD_CHANCE     = 0.04    # daily chance per client to add a new want
CRAFT_DECAY_BASE      = 0.05    # base daily chance during craft
PRODUCT_DECAY_BASE    = 0.03    # base daily chance for sitting products
DECAY_SIZE_FACTOR     = 0.0006  # added to chance per M tokens of recipe size
TOKEN_TYPES = ["Code", "Reasoning", "Image", "Voice", "Video"]
# 2-letter codes used in compact recipe displays (e.g. "120Re · 60Co · 20Im").
TOKEN_ABBREV = {"Code": "Co", "Reasoning": "Re", "Image": "Im", "Voice": "Vo", "Video": "Vi"}

# ─────────────────────────────────────────────
# PROVIDERS — always on the map
# ─────────────────────────────────────────────
# Prices are PER MILLION TOKENS.

PROVIDERS = {
    # Prices roughly mirror real $/M token rates (with image/voice/video markups).
    "Anthropic": {
        "quality": 0.95,
        "desc": "Mature",
        "base_prices": {"Code": 8, "Reasoning": 50, "Image": 40, "Voice": 25, "Video": 50},
    },
    "OpenAI": {
        "quality": 0.90,
        "desc": "Mature",
        "base_prices": {"Code": 7, "Reasoning": 30, "Image": 20, "Voice": 15, "Video": 35},
    },
    "Google": {
        "quality": 0.80,
        "desc": "Growing",
        "base_prices": {"Code": 3, "Reasoning": 6, "Image": 2, "Voice": 3, "Video": 3},
    },
    "Meta": {
        "quality": 0.55,
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
        "craft_days": 2,
        "base_value": 85_000,
    },
    "Contract Analyzer": {
        "recipe":     {"Reasoning": 80, "Code": 40},
        "craft_days": 4,
        "base_value": 110_000,
    },
    "Brand Asset Generator": {
        "recipe":     {"Image": 60, "Code": 10},
        "craft_days": 2,
        "base_value": 65_000,
    },
    "Compliance Dashboard": {
        "recipe":     {"Reasoning": 150, "Code": 80, "Image": 30},
        "craft_days": 6,
        "base_value": 150_000,
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
        "craft_days": 3,
        "base_value": 95_000,
    },
}

# ─────────────────────────────────────────────
# CLIENTS — pool of buyers (subset active at a time)
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
        "wants": ["AI Customer Support", "Marketing Copilot", "Brand Asset Generator"],
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
        "wants": ["AI Customer Support", "Contract Analyzer", "Marketing Copilot", "Brand Asset Generator"],
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
    # SMB & mid-tier buyers — lower quality bars but wider budget swings so
    # deals are sometimes a steal and sometimes a chore. Each has a distinct
    # specialty so the cheap-provider strategy isn't a single uniform path.
    {
        # Productivity-tools SMB. Loves anything that saves an internal team
        # time; pays for it. Decent payouts but never lavish.
        "name": "Basecamp",
        "type": "Enterprise",
        "wants": ["Marketing Copilot", "AI Customer Support", "Contract Analyzer"],
        "budget_mult": (1.0, 1.5),
        "min_quality": 0.50,
    },
    {
        # Public-sector mid-tier. Slow and bureaucratic — wide payout variance
        # because every council negotiates differently.
        "name": "Local Gov Council",
        "type": "Government",
        "wants": ["AI Customer Support", "Training Video Platform", "Brand Asset Generator"],
        "budget_mult": (0.8, 1.6),
        "min_quality": 0.55,
    },
    {
        # Marketplace serving makers — lives or dies by brand assets. Pays
        # premium for visual stuff, scraps for everything else.
        "name": "Etsy",
        "type": "Enterprise",
        "wants": ["Brand Asset Generator", "Marketing Copilot", "AI Customer Support"],
        "budget_mult": (1.1, 1.8),
        "min_quality": 0.55,
    },
]

# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────

def _provider_price_spike(state, provider, token, factor):
    if provider in state["provider_prices"]:
        p = state["provider_prices"][provider][token]
        state["provider_prices"][provider][token] = max(1, round(p * factor))

def _provider_price_crash(state, provider, token, factor):
    if provider in state["provider_prices"]:
        p = state["provider_prices"][provider][token]
        state["provider_prices"][provider][token] = max(1, round(p * factor))

def _all_provider_spike(state, token, factor):
    for prov in state["provider_prices"]:
        p = state["provider_prices"][prov][token]
        state["provider_prices"][prov][token] = max(1, round(p * factor))

def _all_provider_crash(state, token, factor):
    for prov in state["provider_prices"]:
        p = state["provider_prices"][prov][token]
        state["provider_prices"][prov][token] = max(1, round(p * factor))

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
    """Return a fresh state dict. See module docstring for the schema contract."""
    state = {
        "cash":             STARTING_CASH,
        "debt":             STARTING_DEBT,
        "collateral_debt":  0,
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
    state["location"] = random.choice(list(PROVIDERS.keys()))
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
            noise = random.uniform(0.6, 1.6)
            state["provider_prices"][prov][token] = max(1, round(base * noise))

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
    """Pick the active client roster fresh (used at game start)."""
    n = min(ACTIVE_CLIENT_COUNT, len(ALL_CLIENTS))
    chosen = random.sample(ALL_CLIENTS, n)
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

def compute_market_demand(state):
    """Sum recipe tokens required to fulfil every open client contract."""
    demand = {}
    for client in state["active_clients"]:
        for prod_name in client["current_wants"]:
            for tok, qty in PRODUCTS[prod_name]["recipe"].items():
                demand[tok] = demand.get(tok, 0) + qty
    return demand

# ─────────────────────────────────────────────
# TIME
# ─────────────────────────────────────────────

def _recipe_size(product_name):
    return sum(PRODUCTS[product_name]["recipe"].values())

def advance_days(state, days):
    """Advance time: debt interest, craft progress + decay, product decay, events, drift, rotation."""
    event_log = []  # accumulate notes across the whole advance so multi-day waits don't lose them
    for _ in range(days):
        state["day"] += 1
        decay_notes = []
        per_day_notes = []

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
                final_q = state["crafting"]["quality"] * random.uniform(0.96, 1.04)
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
            per_day_notes.append(event["msg"])
        elif decay_notes:
            per_day_notes.append("📉 Model deprecation: " + "; ".join(decay_notes[:2]))

        # Daily client drift
        drift_clients(state)

        # Partial roster rotation
        if state["day"] >= state["next_rotation"]:
            replaced = partial_rotate_clients(state)
            if replaced:
                names = ", ".join(replaced)
                per_day_notes.append(f"📋 Roster shift — {names} dropped, new clients arrived.")

        if per_day_notes:
            prefix = f"Day {state['day']}: " if days > 1 else ""
            for note in per_day_notes:
                event_log.append(prefix + note)

    if event_log:
        state["last_event"] = "\n  ⚡ ".join(event_log)

# ─────────────────────────────────────────────
# ACTIONS
# ─────────────────────────────────────────────

def do_buy_tokens(state, token_type, qty):
    if qty < 1:
        return False, "Quantity must be at least 1M."
    prov = state["location"]
    price = state["provider_prices"][prov][token_type]
    cost = price * qty
    quality = PROVIDERS[prov]["quality"]
    if cost > state["cash"]:
        return False, f"Not enough cash (need ${cost:,}, have ${state['cash']:,})."
    if qty > token_free(state):
        return False, f"Not enough storage (need {qty}M, have {token_free(state)}M free)."
    state["cash"] -= cost
    if token_type not in state["tokens"]:
        state["tokens"][token_type] = {"qty": 0, "quality_sum": 0.0}
    state["tokens"][token_type]["qty"] += qty
    state["tokens"][token_type]["quality_sum"] += qty * quality
    return True, f"Bought {qty}M {token_type} tokens from {prov} for ${cost:,}. (quality: {quality:.0%})"

def can_craft(state, product_name):
    recipe = PRODUCTS[product_name]["recipe"]
    for token_type, needed in recipe.items():
        held = state["tokens"].get(token_type, {"qty": 0})["qty"]
        if held < needed:
            return False
    return True

def do_craft(state, product_name):
    if state["crafting"]:
        return False, f"Already crafting {state['crafting']['name']} ({state['crafting']['days_left']}d left)."
    prod = PRODUCTS[product_name]
    recipe = prod["recipe"]
    if not can_craft(state, product_name):
        missing = []
        for t, need in recipe.items():
            held = state["tokens"].get(t, {"qty": 0})["qty"]
            if held < need:
                missing.append(f"{t}: need {need}M, have {held}M")
        return False, "Missing tokens — " + ", ".join(missing)
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
    return True, f"Started crafting {product_name}! Ready in {prod['craft_days']} days. (quality: {quality:.0%})"

def do_sell_product(state, product_idx, client_idx):
    if client_idx < 0 or client_idx >= len(state["active_clients"]):
        return False, "Invalid client."
    if product_idx < 0 or product_idx >= len(state["products"]):
        return False, "Invalid product."
    client = state["active_clients"][client_idx]
    product = state["products"][product_idx]
    if product["name"] not in client["current_wants"]:
        return False, f"{client['name']} doesn't want {product['name']} right now."
    contract = client["current_wants"][product["name"]]
    if product["quality"] < contract["min_quality"]:
        return False, (f"❌ Quality too low ({product['quality']:.0%}). "
                       f"{client['name']} needs {contract['min_quality']:.0%}+.")
    quality_bonus = product["quality"] / contract["min_quality"]
    revenue = int(contract["budget"] * min(quality_bonus, QUALITY_BONUS_CAP))
    state["cash"] += revenue
    state["products"].pop(product_idx)
    del client["current_wants"][product["name"]]
    return True, f"💰 SOLD {product['name']} to {client['name']} for ${revenue:,}! Cash: ${state['cash']:,}"

def do_travel(state, dest_name, dest_type):
    if dest_name == state["location"]:
        return False, "You're already there."
    if state["cash"] < TRAVEL_COST:
        return False, f"Need ${TRAVEL_COST:,} travel budget (have ${state['cash']:,})."
    state["cash"] -= TRAVEL_COST
    state["location"] = dest_name
    state["location_type"] = dest_type
    if dest_type == "provider":
        prov = PROVIDERS[dest_name]
        state["provider_prices"][dest_name] = {}
        for token, base in prov["base_prices"].items():
            noise = random.uniform(0.6, 1.6)
            state["provider_prices"][dest_name][token] = max(1, round(base * noise))
    return True, f"Travelled to {dest_name}."

def borrow_limit(state):
    total_base = sum(PRODUCTS[p["name"]]["base_value"] for p in state["products"])
    return int(total_base * COLLATERAL_LTV)

def borrow_available(state):
    return max(0, borrow_limit(state) - state.get("collateral_debt", 0))

def do_borrow(state, amount):
    if amount <= 0:
        return False, "Enter a positive amount."
    if not state["products"]:
        return False, "You need at least one finished product as collateral."
    avail = borrow_available(state)
    if avail <= 0:
        return False, "Collateral fully tapped — sell or build more products to borrow again."
    if amount > avail:
        return False, f"Borrow limit is ${avail:,} (30% of finished product base value)."
    state["cash"] += amount
    state["debt"] += amount
    state["collateral_debt"] = state.get("collateral_debt", 0) + amount
    return True, f"💵 Borrowed ${amount:,} against inventory. Cash: ${state['cash']:,}, Debt: ${state['debt']:,}."

def do_pay_debt(state, amount):
    if amount <= 0:
        return False, "Enter a positive amount."
    if amount > state["cash"]:
        return False, "Not enough cash."
    if amount > state["debt"]:
        amount = state["debt"]
    state["cash"] -= amount
    state["debt"] -= amount
    if state.get("collateral_debt", 0) > state["debt"]:
        state["collateral_debt"] = state["debt"]
    return True, f"Paid ${amount:,} toward debt. Remaining: ${state['debt']:,}."

# ─────────────────────────────────────────────
# END-CONDITION ORACLES
# ─────────────────────────────────────────────
# Frontends call these to decide what to render. Keep them pure — no I/O.

def has_any_option(state):
    """Return True if the player has any productive move left.

    Bankruptcy oracle: every action that costs or produces resources has to be
    represented here, or the game can soft-lock instead of ending cleanly.
    """
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
    # At a client where a finished product matches min quality
    if state["location_type"] == "client":
        for c in state["active_clients"]:
            if c["name"] == state["location"]:
                for p in state["products"]:
                    contract = c["current_wants"].get(p["name"])
                    if contract and p["quality"] >= contract["min_quality"]:
                        return True
    return False

def is_bankrupt(state):
    """Cash gone and no productive move left. Frontends render a bankruptcy screen."""
    return state["cash"] <= 0 and not has_any_option(state)

def is_game_over(state):
    """Either the day limit ran out or the player went bankrupt."""
    return state["day"] > MAX_DAYS or is_bankrupt(state)
