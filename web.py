#!/usr/bin/env python3
"""
Hallucination Inc. — web frontend.

Flask app that serves the game over HTTP. Imports the same `engine` module
as the terminal frontend — all game rules live there. This module only
maps HTTP requests onto engine actions and renders state as HTML.

State lives in a module-level dict keyed by a cookie session id, so each
browser gets its own game. Restarting the server drops in-progress runs;
acceptable while the game is still finding its shape.

Run with::

    python3 hallucination_inc.py --web

or directly::

    python3 web.py
"""

import os
import secrets

from flask import Flask, redirect, render_template, request, url_for

import engine


app = Flask(__name__)

# In-memory store of games keyed by cookie session id. Each entry is
# {"state": <engine state dict>, "started": bool}. The ``started`` flag is
# a presentation concern: it gates the welcome screen, kept out of the
# engine state to keep that dict's shape engine-pure.
# Wiped on every server restart — fine for the casual-play stage.
_games: dict = {}

COOKIE_NAME = "hinc_sid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


# ─────────────────────────────────────────────
# Session + action plumbing
# ─────────────────────────────────────────────

def _new_session_entry():
    return {"state": engine.new_game(), "started": False}


def _get_or_create_session():
    """Return (sid, session_dict). Creates a fresh game for new browsers."""
    sid = request.cookies.get(COOKIE_NAME)
    if sid and sid in _games:
        return sid, _games[sid]
    sid = secrets.token_urlsafe(16)
    _games[sid] = _new_session_entry()
    return sid, _games[sid]


def _get_or_create_state():
    """Convenience wrapper for routes that only care about the engine state."""
    sid, sess = _get_or_create_session()
    return sid, sess["state"]


def _apply(state, result):
    """Mirror the terminal frontend's menu wrapper flow:

    - On a successful action, tick exactly one day forward.
    - Surface the action's message as ``state["message"]`` unless
      ``advance_days`` already wrote one (e.g. a crafting completion).
    """
    ok, msg = result
    if ok:
        engine.advance_days(state, 1)
    if not state.get("message"):
        state["message"] = msg


def _redirect_home(sid):
    """303 to '/' (so refresh doesn't re-POST), sticky session cookie attached."""
    resp = redirect(url_for("index"), code=303)
    resp.set_cookie(COOKIE_NAME, sid, max_age=COOKIE_MAX_AGE, samesite="Lax")
    return resp


def _parse_int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    sid, sess = _get_or_create_session()
    state = sess["state"]

    # First visit (or after a fresh /new): show the story / intro screen.
    if not sess["started"]:
        resp = app.make_response(render_template(
            "welcome.html",
            MAX_DAYS=engine.MAX_DAYS,
            ACTIVE_CLIENT_COUNT=engine.ACTIVE_CLIENT_COUNT,
            TRAVEL_COST=engine.TRAVEL_COST,
            DEBT_FREE_BONUS=engine.DEBT_FREE_BONUS,
            MAX_TOKENS=engine.MAX_TOKENS,
        ))
        resp.set_cookie(COOKIE_NAME, sid, max_age=COOKIE_MAX_AGE, samesite="Lax")
        return resp

    # Read-and-clear contract for transient hints. The terminal frontend
    # does the same: render once, then wipe.
    event = state.get("last_event")
    msg = state.get("message")
    state["last_event"] = None
    state["message"] = None

    ctx = {
        "state":            state,
        "event":            event,
        "msg":              msg,
        "location_info":    _location_info(state),
        "inventory":        _inventory_view(state),
        "contracts":        _contracts_view(state),
        "sellables":        _sellables_at_current_location(state),
        "market_grid":      _provider_grid(state),
        "destinations":     _destinations(state),
        "is_game_over":     engine.is_game_over(state),
        "is_bankrupt":      engine.is_bankrupt(state),
        "net_worth":        engine.net_worth(state),
        "borrow_available": engine.borrow_available(state),
        "borrow_limit":     engine.borrow_limit(state),
        "token_total":      engine.token_total(state),
        "token_free":       engine.token_free(state),
        # constants for templates
        "MAX_DAYS":         engine.MAX_DAYS,
        "MAX_TOKENS":       engine.MAX_TOKENS,
        "TRAVEL_COST":      engine.TRAVEL_COST,
        "DEBT_FREE_BONUS":  engine.DEBT_FREE_BONUS,
        "TOKEN_TYPES":      engine.TOKEN_TYPES,
        "PRODUCTS":         engine.PRODUCTS,
        "PROVIDERS":        engine.PROVIDERS,
    }

    resp = app.make_response(render_template("game.html", **ctx))
    resp.set_cookie(COOKIE_NAME, sid, max_age=COOKIE_MAX_AGE, samesite="Lax")
    return resp


@app.post("/start")
def start_game():
    """Dismiss the welcome screen and drop the player onto the game page."""
    sid, sess = _get_or_create_session()
    sess["started"] = True
    return _redirect_home(sid)


@app.post("/new")
def new_game():
    """Wipe progress and return to the welcome screen."""
    sid, _ = _get_or_create_session()
    _games[sid] = _new_session_entry()
    return _redirect_home(sid)


@app.post("/buy")
def buy():
    sid, state = _get_or_create_state()
    token = request.form.get("token")
    qty = _parse_int(request.form.get("qty"))
    if state["location_type"] != "provider":
        state["message"] = "You need to be at a provider to buy tokens."
    elif token not in engine.TOKEN_TYPES:
        state["message"] = "Unknown token type."
    elif qty is None or qty < 1:
        state["message"] = "Quantity must be a positive number of millions."
    else:
        _apply(state, engine.do_buy_tokens(state, token, qty))
    return _redirect_home(sid)


@app.post("/craft")
def craft():
    sid, state = _get_or_create_state()
    product = request.form.get("product")
    if product not in engine.PRODUCTS:
        state["message"] = "Unknown product."
    else:
        _apply(state, engine.do_craft(state, product))
    return _redirect_home(sid)


@app.post("/sell")
def sell():
    sid, state = _get_or_create_state()
    if state["location_type"] != "client":
        state["message"] = "You need to be at a client to sell."
        return _redirect_home(sid)
    pidx = _parse_int(request.form.get("product_idx"))
    if pidx is None:
        state["message"] = "Invalid product."
        return _redirect_home(sid)
    client_idx = next(
        (i for i, c in enumerate(state["active_clients"])
         if c["name"] == state["location"]),
        None,
    )
    if client_idx is None:
        state["message"] = f"⚠️ {state['location']} rotated out. Travel elsewhere."
        return _redirect_home(sid)
    _apply(state, engine.do_sell_product(state, pidx, client_idx))
    return _redirect_home(sid)


@app.post("/travel")
def travel():
    sid, state = _get_or_create_state()
    dest_name = request.form.get("dest_name")
    dest_type = request.form.get("dest_type")
    if dest_type not in ("provider", "client") or not dest_name:
        state["message"] = "Invalid destination."
    else:
        _apply(state, engine.do_travel(state, dest_name, dest_type))
    return _redirect_home(sid)


@app.post("/next")
def next_day():
    sid, state = _get_or_create_state()
    engine.advance_days(state, 1)
    if not state.get("message"):
        state["message"] = "Day advanced."
    return _redirect_home(sid)


@app.post("/borrow")
def borrow():
    sid, state = _get_or_create_state()
    amount = _parse_int(request.form.get("amount"))
    if amount is None or amount <= 0:
        state["message"] = "Enter a positive amount."
    else:
        _apply(state, engine.do_borrow(state, amount))
    return _redirect_home(sid)


@app.post("/pay")
def pay():
    sid, state = _get_or_create_state()
    amount = _parse_int(request.form.get("amount"))
    if amount is None or amount <= 0:
        state["message"] = "Enter a positive amount."
    else:
        _apply(state, engine.do_pay_debt(state, amount))
    return _redirect_home(sid)


# ─────────────────────────────────────────────
# View helpers (pure functions of state → dicts the template renders)
# ─────────────────────────────────────────────

def _location_info(state):
    name = state["location"]
    loc_type = state["location_type"]
    if loc_type == "provider":
        prov = engine.PROVIDERS[name]
        return {
            "name":     name,
            "type":     loc_type,
            "desc":     prov["desc"],
            "quality":  prov["quality"],
            "prices":   state["provider_prices"][name],
        }
    client = next((c for c in state["active_clients"] if c["name"] == name), None)
    if not client:
        return {"name": name, "type": loc_type, "desc": "stale", "quality": None,
                "wants": {}, "stale": True}
    return {"name": name, "type": loc_type, "desc": client["type"],
            "quality": None, "wants": client["current_wants"], "stale": False}


def _inventory_view(state):
    tokens = []
    for tok in engine.TOKEN_TYPES:
        data = state["tokens"].get(tok)
        if data and data["qty"] > 0:
            tokens.append({
                "type":    tok,
                "qty":     data["qty"],
                "quality": data["quality_sum"] / data["qty"],
            })
    products = [{"idx": i, "name": p["name"], "quality": p["quality"]}
                for i, p in enumerate(state["products"])]
    return {"tokens": tokens, "products": products, "crafting": state["crafting"]}


def _recipe_short(product_name):
    recipe = engine.PRODUCTS[product_name]["recipe"]
    return " · ".join(
        f"{recipe[t]}{engine.TOKEN_ABBREV[t]}"
        for t in engine.TOKEN_TYPES if t in recipe
    )


def _contracts_view(state):
    rows = []
    for client in state["active_clients"]:
        tag = "GOV" if client["type"] == "Government" else "ENT"
        for prod_name, info in client["current_wants"].items():
            rows.append({
                "tag":         tag,
                "client":      client["name"],
                "product":     prod_name,
                "budget":      info["budget"],
                "min_quality": info["min_quality"],
                "recipe":      _recipe_short(prod_name),
            })
    rows.sort(key=lambda r: -r["budget"])
    return rows


def _sellables_at_current_location(state):
    """Products held that the current client (if any) wants. Drives the sell form."""
    if state["location_type"] != "client":
        return []
    client = next((c for c in state["active_clients"]
                   if c["name"] == state["location"]), None)
    if not client:
        return []
    rows = []
    for i, p in enumerate(state["products"]):
        contract = client["current_wants"].get(p["name"])
        if contract:
            rows.append({
                "idx":         i,
                "name":        p["name"],
                "quality":     p["quality"],
                "budget":      contract["budget"],
                "min_quality": contract["min_quality"],
                "ok":          p["quality"] >= contract["min_quality"],
            })
    return rows


def _provider_grid(state):
    rows = []
    here = state["location"] if state["location_type"] == "provider" else None
    for name, data in sorted(engine.PROVIDERS.items(), key=lambda kv: -kv[1]["quality"]):
        prices = state["provider_prices"][name]
        rows.append({
            "name":    name,
            "quality": data["quality"],
            "here":    name == here,
            "prices":  [(t, prices[t]) for t in engine.TOKEN_TYPES],
        })
    return rows


def _destinations(state):
    here = state["location"]
    provs = [
        {"name": n, "type": "provider", "quality": p["quality"], "desc": p["desc"]}
        for n, p in engine.PROVIDERS.items() if n != here
    ]

    def _client_key(c):
        budgets = [w["budget"] for w in c["current_wants"].values()]
        return (0 if budgets else 1, -max(budgets) if budgets else 0)

    clients = sorted(state["active_clients"], key=_client_key)
    cdests = [
        {
            "name":  c["name"],
            "type":  "client",
            "tag":   "GOV" if c["type"] == "Government" else "ENT",
            "wants": list(c["current_wants"].keys()),
        }
        for c in clients if c["name"] != here
    ]
    return {"providers": provs, "clients": cdests}


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    """Launch the dev server. Binds to 0.0.0.0 so the app is reachable over
    LAN or a Cloudflare Tunnel without extra config."""
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5050"))
    print(f"Hallucination Inc. — web frontend at http://localhost:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
