#!/usr/bin/env python3
"""
Unit tests for hallucination_inc.py.

Stdlib only (unittest + unittest.mock). Aims for 90%+ line coverage of the
single-file game. Run via ``python3 run_tests.py`` (which measures coverage
and gates commits via .git/hooks/pre-commit).
"""

import io
import os
import random
import unittest
from contextlib import redirect_stdout
from unittest import mock

import hallucination_inc as g


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _capture(fn, *args, **kwargs):
    """Run fn and return (return_value, captured_stdout)."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        rv = fn(*args, **kwargs)
    return rv, buf.getvalue()


def _silent(fn, *args, **kwargs):
    """Run fn, throw away stdout, return its return value."""
    rv, _ = _capture(fn, *args, **kwargs)
    return rv


def _bare_state():
    """Return a fully-seeded fresh game state with a deterministic RNG."""
    random.seed(0)
    return g.new_game()


def _state_with(location_type="provider", location=None, cash=None, debt=None,
                tokens=None, products=None, crafting=None):
    """Make a state with overrides for targeted scenarios."""
    s = _bare_state()
    if cash is not None:
        s["cash"] = cash
    if debt is not None:
        s["debt"] = debt
    if tokens is not None:
        s["tokens"] = tokens
    if products is not None:
        s["products"] = products
    if crafting is not None:
        s["crafting"] = crafting
    if location_type == "client":
        # Pick an active client as location.
        client = s["active_clients"][0]
        s["location"] = client["name"]
        s["location_type"] = "client"
    elif location is not None:
        s["location"] = location
        s["location_type"] = location_type
    return s


# ─────────────────────────────────────────────
# Module-level data sanity
# ─────────────────────────────────────────────

class ConstantsTests(unittest.TestCase):
    def test_token_abbreviations_cover_all_token_types(self):
        for t in g.TOKEN_TYPES:
            self.assertIn(t, g.TOKEN_ABBREV)
            self.assertEqual(len(g.TOKEN_ABBREV[t]), 2)

    def test_providers_have_prices_for_every_token(self):
        for prov, data in g.PROVIDERS.items():
            for t in g.TOKEN_TYPES:
                self.assertIn(t, data["base_prices"], f"{prov} missing {t}")
                self.assertGreater(data["base_prices"][t], 0)

    def test_products_recipes_use_known_token_types(self):
        for name, data in g.PRODUCTS.items():
            for t in data["recipe"]:
                self.assertIn(t, g.TOKEN_TYPES)
            self.assertGreater(data["base_value"], 0)
            self.assertGreater(data["craft_days"], 0)

    def test_clients_reference_known_products(self):
        for c in g.ALL_CLIENTS:
            for p in c["wants"]:
                self.assertIn(p, g.PRODUCTS)


# ─────────────────────────────────────────────
# State setup
# ─────────────────────────────────────────────

class NewGameTests(unittest.TestCase):
    def test_new_game_initial_values(self):
        s = _bare_state()
        self.assertEqual(s["cash"], g.STARTING_CASH)
        self.assertEqual(s["debt"], g.STARTING_DEBT)
        self.assertEqual(s["day"], 1)
        self.assertEqual(s["location_type"], "provider")
        self.assertIn(s["location"], g.PROVIDERS)
        self.assertEqual(s["tokens"], {})
        self.assertEqual(s["products"], [])
        self.assertIsNone(s["crafting"])
        self.assertEqual(len(s["active_clients"]), g.ACTIVE_CLIENT_COUNT)

    def test_refresh_provider_prices_generates_every_combo(self):
        s = _bare_state()
        g.refresh_provider_prices(s)
        for prov in g.PROVIDERS:
            for t in g.TOKEN_TYPES:
                self.assertIn(t, s["provider_prices"][prov])
                self.assertGreaterEqual(s["provider_prices"][prov][t], 1)

    def test_find_template_finds_known_client(self):
        sample = g.ALL_CLIENTS[0]["name"]
        self.assertEqual(g._find_template(sample)["name"], sample)

    def test_find_template_returns_none_for_unknown(self):
        self.assertIsNone(g._find_template("Some Made-Up Co"))

    def test_make_client_from_template_yields_at_least_one_want(self):
        template = g.ALL_CLIENTS[0]
        random.seed(1)
        c = g._make_client_from_template(template)
        self.assertEqual(c["name"], template["name"])
        self.assertTrue(len(c["current_wants"]) >= 1)


# ─────────────────────────────────────────────
# Token / inventory helpers
# ─────────────────────────────────────────────

class InventoryHelperTests(unittest.TestCase):
    def test_token_total_and_free(self):
        s = _bare_state()
        s["tokens"] = {"Code": {"qty": 50, "quality_sum": 40.0}}
        self.assertEqual(g.token_total(s), 50)
        self.assertEqual(g.token_free(s), g.MAX_TOKENS - 50)

    def test_token_avg_quality_present_and_missing(self):
        s = _bare_state()
        s["tokens"] = {"Code": {"qty": 10, "quality_sum": 8.0}}
        self.assertAlmostEqual(g.token_avg_quality(s, "Code"), 0.8)
        self.assertEqual(g.token_avg_quality(s, "Voice"), 0.0)

    def test_token_avg_quality_zero_qty(self):
        s = _bare_state()
        s["tokens"] = {"Code": {"qty": 0, "quality_sum": 0.0}}
        self.assertEqual(g.token_avg_quality(s, "Code"), 0.0)

    def test_net_worth(self):
        s = _bare_state()
        s["cash"] = 200_000
        s["debt"] = 50_000
        self.assertEqual(g.net_worth(s), 150_000)

    def test_recipe_size(self):
        recipe_size = g._recipe_size("AI Customer Support")
        expected = sum(g.PRODUCTS["AI Customer Support"]["recipe"].values())
        self.assertEqual(recipe_size, expected)


# ─────────────────────────────────────────────
# Buy / craft / sell mechanics
# ─────────────────────────────────────────────

class BuyTokenTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()
        # Force location to a known cheap provider.
        self.s["location"] = "Meta"
        self.s["location_type"] = "provider"
        # Reset prices to known values so we can predict cost.
        self.s["provider_prices"]["Meta"] = {
            "Code": 1, "Reasoning": 2, "Image": 3, "Voice": 4, "Video": 3
        }

    def test_buy_below_minimum_quantity(self):
        ok, msg = g.do_buy_tokens(self.s, "Code", 0)
        self.assertFalse(ok)
        self.assertIn("at least 1M", msg)

    def test_buy_success_updates_cash_and_inventory(self):
        cash0 = self.s["cash"]
        ok, msg = g.do_buy_tokens(self.s, "Code", 10)
        self.assertTrue(ok)
        self.assertEqual(self.s["cash"], cash0 - 10)
        self.assertEqual(self.s["tokens"]["Code"]["qty"], 10)
        self.assertAlmostEqual(
            self.s["tokens"]["Code"]["quality_sum"],
            10 * g.PROVIDERS["Meta"]["quality"],
        )
        self.assertIn("Bought 10M Code", msg)

    def test_buy_accumulates(self):
        g.do_buy_tokens(self.s, "Code", 10)
        g.do_buy_tokens(self.s, "Code", 5)
        self.assertEqual(self.s["tokens"]["Code"]["qty"], 15)

    def test_buy_blocked_by_insufficient_cash(self):
        self.s["cash"] = 5  # 10 Code @ $1 would still fit, so make qty bigger
        ok, msg = g.do_buy_tokens(self.s, "Code", 10)
        self.assertFalse(ok)
        self.assertIn("Not enough cash", msg)

    def test_buy_blocked_by_storage(self):
        self.s["tokens"] = {"Code": {"qty": g.MAX_TOKENS, "quality_sum": 0.5 * g.MAX_TOKENS}}
        ok, msg = g.do_buy_tokens(self.s, "Code", 1)
        self.assertFalse(ok)
        self.assertIn("storage", msg)


class CraftTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def _stock_tokens_for(self, product_name):
        for t, qty in g.PRODUCTS[product_name]["recipe"].items():
            self.s["tokens"][t] = {"qty": qty, "quality_sum": 0.8 * qty}

    def test_can_craft_true_when_inventory_sufficient(self):
        self._stock_tokens_for("AI Customer Support")
        self.assertTrue(g.can_craft(self.s, "AI Customer Support"))

    def test_can_craft_false_when_missing(self):
        self.assertFalse(g.can_craft(self.s, "AI Customer Support"))

    def test_do_craft_starts_with_correct_quality(self):
        self._stock_tokens_for("AI Customer Support")
        ok, msg = g.do_craft(self.s, "AI Customer Support")
        self.assertTrue(ok)
        self.assertEqual(self.s["crafting"]["name"], "AI Customer Support")
        self.assertAlmostEqual(self.s["crafting"]["quality"], 0.8, places=4)
        # Tokens fully consumed.
        self.assertNotIn("Code", self.s["tokens"])
        self.assertNotIn("Voice", self.s["tokens"])

    def test_do_craft_when_already_crafting(self):
        self._stock_tokens_for("AI Customer Support")
        g.do_craft(self.s, "AI Customer Support")
        ok, msg = g.do_craft(self.s, "AI Customer Support")
        self.assertFalse(ok)
        self.assertIn("Already crafting", msg)

    def test_do_craft_missing_tokens(self):
        ok, msg = g.do_craft(self.s, "AI Customer Support")
        self.assertFalse(ok)
        self.assertIn("Missing tokens", msg)

    def test_do_craft_partial_consume_keeps_remaining(self):
        product = "AI Customer Support"
        # Stock 2x to be sure leftovers remain.
        for t, qty in g.PRODUCTS[product]["recipe"].items():
            self.s["tokens"][t] = {"qty": qty * 2, "quality_sum": 0.7 * qty * 2}
        ok, _ = g.do_craft(self.s, product)
        self.assertTrue(ok)
        for t, qty in g.PRODUCTS[product]["recipe"].items():
            self.assertEqual(self.s["tokens"][t]["qty"], qty)


class SellTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()
        # Inject a controlled client and product.
        self.s["active_clients"] = [{
            "name": "TestCo",
            "type": "Enterprise",
            "min_quality": 0.6,
            "current_wants": {
                "AI Customer Support": {"budget": 100_000, "min_quality": 0.6}
            },
        }]
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        self.s["location"] = "TestCo"
        self.s["location_type"] = "client"

    def test_sell_success_pays_capped_premium(self):
        cash0 = self.s["cash"]
        ok, msg = g.do_sell_product(self.s, 0, 0)
        self.assertTrue(ok)
        # quality_bonus = 0.9 / 0.6 = 1.5 → exactly QUALITY_BONUS_CAP.
        self.assertEqual(self.s["cash"], cash0 + int(100_000 * g.QUALITY_BONUS_CAP))
        self.assertEqual(self.s["products"], [])
        self.assertEqual(self.s["active_clients"][0]["current_wants"], {})
        self.assertIn("SOLD", msg)

    def test_sell_invalid_client(self):
        ok, msg = g.do_sell_product(self.s, 0, 99)
        self.assertFalse(ok)
        self.assertIn("Invalid client", msg)

    def test_sell_invalid_product(self):
        ok, msg = g.do_sell_product(self.s, 99, 0)
        self.assertFalse(ok)
        self.assertIn("Invalid product", msg)

    def test_sell_unwanted_product(self):
        self.s["products"] = [{"name": "Contract Analyzer", "quality": 0.9}]
        ok, msg = g.do_sell_product(self.s, 0, 0)
        self.assertFalse(ok)
        self.assertIn("doesn't want", msg)

    def test_sell_low_quality_rejected(self):
        self.s["products"][0]["quality"] = 0.4
        ok, msg = g.do_sell_product(self.s, 0, 0)
        self.assertFalse(ok)
        self.assertIn("Quality too low", msg)


# ─────────────────────────────────────────────
# Travel / borrow / pay
# ─────────────────────────────────────────────

class TravelTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()
        self.s["location"] = "Anthropic"
        self.s["location_type"] = "provider"

    def test_travel_to_same_location_blocked(self):
        ok, msg = g.do_travel(self.s, "Anthropic", "provider")
        self.assertFalse(ok)
        self.assertIn("already there", msg)

    def test_travel_blocked_by_low_cash(self):
        self.s["cash"] = 100
        ok, msg = g.do_travel(self.s, "Google", "provider")
        self.assertFalse(ok)
        self.assertIn("travel budget", msg)

    def test_travel_to_provider_resets_prices(self):
        cash0 = self.s["cash"]
        ok, msg = g.do_travel(self.s, "Google", "provider")
        self.assertTrue(ok)
        self.assertEqual(self.s["location"], "Google")
        self.assertEqual(self.s["location_type"], "provider")
        self.assertEqual(self.s["cash"], cash0 - g.TRAVEL_COST)
        for t in g.TOKEN_TYPES:
            self.assertIn(t, self.s["provider_prices"]["Google"])

    def test_travel_to_client(self):
        client_name = self.s["active_clients"][0]["name"]
        ok, msg = g.do_travel(self.s, client_name, "client")
        self.assertTrue(ok)
        self.assertEqual(self.s["location"], client_name)
        self.assertEqual(self.s["location_type"], "client")


class BorrowTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_no_collateral(self):
        self.assertEqual(g.borrow_limit(self.s), 0)
        self.assertEqual(g.borrow_available(self.s), 0)

    def test_borrow_blocked_zero_amount(self):
        ok, msg = g.do_borrow(self.s, 0)
        self.assertFalse(ok)
        self.assertIn("positive", msg)

    def test_borrow_requires_product(self):
        ok, msg = g.do_borrow(self.s, 1000)
        self.assertFalse(ok)
        self.assertIn("collateral", msg)

    def test_borrow_caps_at_ltv(self):
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        limit = g.borrow_limit(self.s)
        self.assertEqual(limit, int(g.PRODUCTS["AI Customer Support"]["base_value"] * g.COLLATERAL_LTV))
        # Borrow over limit:
        ok, msg = g.do_borrow(self.s, limit + 1)
        self.assertFalse(ok)
        self.assertIn("Borrow limit", msg)

    def test_borrow_success_then_exhausted(self):
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        limit = g.borrow_limit(self.s)
        cash0, debt0 = self.s["cash"], self.s["debt"]
        ok, msg = g.do_borrow(self.s, limit)
        self.assertTrue(ok)
        self.assertEqual(self.s["cash"], cash0 + limit)
        self.assertEqual(self.s["debt"], debt0 + limit)
        # Now exhausted.
        self.assertEqual(g.borrow_available(self.s), 0)
        ok, msg = g.do_borrow(self.s, 1)
        self.assertFalse(ok)
        self.assertIn("fully tapped", msg)


class PayDebtTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_pay_zero(self):
        ok, msg = g.do_pay_debt(self.s, 0)
        self.assertFalse(ok)
        self.assertIn("positive", msg)

    def test_pay_more_than_cash(self):
        ok, msg = g.do_pay_debt(self.s, self.s["cash"] + 1)
        self.assertFalse(ok)
        self.assertIn("Not enough cash", msg)

    def test_pay_more_than_debt_clamps(self):
        self.s["cash"] = 200_000
        self.s["debt"] = 1_000
        ok, msg = g.do_pay_debt(self.s, 5_000)
        self.assertTrue(ok)
        self.assertEqual(self.s["debt"], 0)
        self.assertEqual(self.s["cash"], 199_000)

    def test_pay_decreases_collateral_when_above_debt(self):
        self.s["cash"] = 200_000
        self.s["debt"] = 50_000
        self.s["collateral_debt"] = 40_000
        ok, _ = g.do_pay_debt(self.s, 30_000)
        self.assertTrue(ok)
        # debt now 20k, collateral_debt should clamp down to 20k
        self.assertEqual(self.s["debt"], 20_000)
        self.assertEqual(self.s["collateral_debt"], 20_000)


# ─────────────────────────────────────────────
# advance_days and events
# ─────────────────────────────────────────────

class AdvanceDaysTests(unittest.TestCase):
    def test_debt_accrues_interest(self):
        s = _bare_state()
        s["debt"] = 100_000
        with mock.patch("random.random", return_value=0.99):  # no event
            g.advance_days(s, 1)
        self.assertEqual(s["debt"], 103_000)
        self.assertEqual(s["day"], 2)

    def test_craft_progress_decrements(self):
        s = _bare_state()
        s["crafting"] = {"name": "AI Customer Support", "quality": 0.8, "days_left": 2}
        # Force no decay, no event.
        with mock.patch("random.random", return_value=0.99), \
             mock.patch("random.uniform", return_value=1.0):
            g.advance_days(s, 1)
        self.assertEqual(s["crafting"]["days_left"], 1)

    def test_craft_completion_emits_product(self):
        s = _bare_state()
        s["crafting"] = {"name": "AI Customer Support", "quality": 0.8, "days_left": 1}
        with mock.patch("random.random", return_value=0.99), \
             mock.patch("random.uniform", return_value=1.0):
            g.advance_days(s, 1)
        self.assertIsNone(s["crafting"])
        self.assertEqual(len(s["products"]), 1)
        self.assertEqual(s["products"][0]["name"], "AI Customer Support")
        self.assertIn("Finished", s["message"])

    def test_craft_decay_drops_quality(self):
        s = _bare_state()
        s["crafting"] = {"name": "AI Customer Support", "quality": 0.9, "days_left": 5}
        # Force every random.random() call to fire the decay branch and the no-event branch (0.0 < CRAFT_DECAY_BASE; 0.0 < 0.30 too, so an event will fire).
        # Use a side_effect to control sequence.
        # Sequence per day inside advance_days: decay roll, event roll, then
        # per-client drift rolls (3 per client × clients) — set decay=0 to
        # trigger, then push the rest above all thresholds.
        random_seq = iter([0.0, 0.99] + [0.99] * 200)
        uniform_seq = iter([0.05] + [1.0] * 200)
        with mock.patch("random.random", side_effect=lambda: next(random_seq)), \
             mock.patch("random.uniform", side_effect=lambda *a, **k: next(uniform_seq)):
            g.advance_days(s, 1)
        self.assertLess(s["crafting"]["quality"], 0.9)

    def test_product_decay(self):
        s = _bare_state()
        s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        # Trigger decay on the product (first random.random call <
        # PRODUCT_DECAY_BASE), then no event.
        random_seq = iter([0.0, 0.99] + [0.99] * 200)
        uniform_seq = iter([0.05] + [1.0] * 200)
        with mock.patch("random.random", side_effect=lambda: next(random_seq)), \
             mock.patch("random.uniform", side_effect=lambda *a, **k: next(uniform_seq)):
            g.advance_days(s, 1)
        self.assertLess(s["products"][0]["quality"], 0.9)

    def test_event_fires_and_logs(self):
        s = _bare_state()
        # Force event branch (random < 0.30) and pick a deterministic event.
        random_seq = iter([0.0] + [0.99] * 200)
        with mock.patch("random.random", side_effect=lambda: next(random_seq)), \
             mock.patch("random.choice", side_effect=lambda seq: seq[0]):
            g.advance_days(s, 1)
        self.assertIsNotNone(s["last_event"])

    def test_advance_multiday_prefixes_day(self):
        s = _bare_state()
        random_seq = iter([0.0, 0.99] + [0.0, 0.99] * 200)
        with mock.patch("random.random", side_effect=lambda: next(random_seq)), \
             mock.patch("random.choice", side_effect=lambda seq: seq[0]):
            g.advance_days(s, 2)
        self.assertIn("Day", s["last_event"] or "")

    def test_rotation_fires_when_scheduled(self):
        s = _bare_state()
        s["next_rotation"] = s["day"] + 1  # ensure next tick triggers rotation
        original_names = {c["name"] for c in s["active_clients"]}
        with mock.patch("random.random", return_value=0.99):  # no events / drift
            g.advance_days(s, 1)
        new_names = {c["name"] for c in s["active_clients"]}
        self.assertNotEqual(original_names, new_names)


class EventHelperTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_provider_price_spike(self):
        before = self.s["provider_prices"]["Anthropic"]["Code"]
        g._provider_price_spike(self.s, "Anthropic", "Code", 2.0)
        self.assertEqual(self.s["provider_prices"]["Anthropic"]["Code"], max(1, round(before * 2.0)))

    def test_provider_price_spike_missing_provider_noop(self):
        g._provider_price_spike(self.s, "GhostProvider", "Code", 2.0)
        # nothing raised, no change

    def test_provider_price_crash(self):
        self.s["provider_prices"]["Anthropic"]["Code"] = 10
        g._provider_price_crash(self.s, "Anthropic", "Code", 0.4)
        self.assertEqual(self.s["provider_prices"]["Anthropic"]["Code"], 4)

    def test_all_provider_spike_and_crash(self):
        g._all_provider_spike(self.s, "Code", 2.0)
        g._all_provider_crash(self.s, "Code", 0.5)
        for prov in g.PROVIDERS:
            self.assertGreaterEqual(self.s["provider_prices"][prov]["Code"], 1)

    def test_client_budget_spike_and_crash(self):
        # Inject a known want.
        self.s["active_clients"][0]["current_wants"]["Compliance Dashboard"] = {
            "budget": 100_000, "min_quality": 0.8
        }
        g._client_budget_spike(self.s, "Compliance Dashboard")
        self.assertEqual(
            self.s["active_clients"][0]["current_wants"]["Compliance Dashboard"]["budget"],
            160_000,
        )
        g._client_budget_crash(self.s, "Compliance Dashboard")
        self.assertEqual(
            self.s["active_clients"][0]["current_wants"]["Compliance Dashboard"]["budget"],
            80_000,
        )

    def test_gov_budget_boost(self):
        gov = next((c for c in self.s["active_clients"] if c["type"] == "Government"), None)
        if not gov:
            # Force one if random sample didn't include gov.
            gov_template = next(t for t in g.ALL_CLIENTS if t["type"] == "Government")
            self.s["active_clients"][0] = g._make_client_from_template(gov_template)
            gov = self.s["active_clients"][0]
        if gov["current_wants"]:
            before = next(iter(gov["current_wants"].values()))["budget"]
            g._gov_budget_boost(self.s)
            after = next(iter(gov["current_wants"].values()))["budget"]
            self.assertEqual(after, int(before * 1.5))

    def test_bonus_cash_clamps_to_zero(self):
        self.s["cash"] = 100
        g._bonus_cash(self.s, -1_000_000)
        self.assertEqual(self.s["cash"], 0)
        g._bonus_cash(self.s, 5_000)
        self.assertEqual(self.s["cash"], 5_000)

    def test_craft_setback_with_active_craft(self):
        self.s["crafting"] = {"name": "AI Customer Support", "quality": 0.9, "days_left": 2}
        g._craft_setback(self.s)
        self.assertEqual(self.s["crafting"]["days_left"], 4)
        self.assertAlmostEqual(self.s["crafting"]["quality"], 0.8, places=4)

    def test_craft_setback_without_active_craft_noop(self):
        self.s["crafting"] = None
        g._craft_setback(self.s)
        self.assertIsNone(self.s["crafting"])

    def test_token_decay_reduces_quality(self):
        self.s["tokens"] = {"Code": {"qty": 10, "quality_sum": 8.0}}
        g._token_decay(self.s)
        avg = self.s["tokens"]["Code"]["quality_sum"] / self.s["tokens"]["Code"]["qty"]
        self.assertAlmostEqual(avg, 0.72, places=2)

    def test_token_decay_ignores_empty(self):
        self.s["tokens"] = {"Code": {"qty": 0, "quality_sum": 0.0}}
        g._token_decay(self.s)
        self.assertEqual(self.s["tokens"]["Code"]["quality_sum"], 0.0)

    def test_each_event_runs_without_error(self):
        # Every event function executes against a fresh state without raising.
        for ev in g.EVENTS:
            s = _bare_state()
            s["crafting"] = {"name": "AI Customer Support", "quality": 0.9, "days_left": 2}
            s["tokens"] = {"Code": {"qty": 10, "quality_sum": 8.0}}
            ev["fn"](s)  # must not raise


# ─────────────────────────────────────────────
# Client roster drift / partial rotation
# ─────────────────────────────────────────────

class ClientDriftTests(unittest.TestCase):
    def test_partial_rotate_replaces_clients(self):
        s = _bare_state()
        original = {c["name"] for c in s["active_clients"]}
        replaced = g.partial_rotate_clients(s)
        # At least one slot should have changed.
        self.assertTrue(replaced)
        new_names = {c["name"] for c in s["active_clients"]}
        self.assertNotEqual(original, new_names)

    def test_partial_rotate_with_exhausted_pool(self):
        s = _bare_state()
        # Make every client in the pool active so the candidate pool is empty.
        s["active_clients"] = [g._make_client_from_template(t) for t in g.ALL_CLIENTS]
        replaced = g.partial_rotate_clients(s)
        self.assertEqual(replaced, [])

    def test_drift_can_drop_add_or_shift(self):
        s = _bare_state()
        # Force all probability branches: drift+drop+add for every client.
        with mock.patch("random.random", return_value=0.0), \
             mock.patch("random.uniform", return_value=1.0):
            g.drift_clients(s)
        # nothing crashed; some wants may have been added/dropped/shifted

    def test_drift_when_unknown_template_noop(self):
        s = _bare_state()
        # Inject a client whose name isn't in ALL_CLIENTS to hit the
        # _find_template fallback inside drift_clients.
        s["active_clients"] = [{
            "name": "Phantom Corp",
            "type": "Enterprise",
            "min_quality": 0.5,
            "current_wants": {"AI Customer Support": {"budget": 50_000, "min_quality": 0.5}},
        }]
        with mock.patch("random.random", return_value=0.0):
            g.drift_clients(s)


# ─────────────────────────────────────────────
# has_any_option (the bankruptcy oracle)
# ─────────────────────────────────────────────

class HasAnyOptionTests(unittest.TestCase):
    def test_can_travel(self):
        s = _bare_state()
        s["cash"] = g.TRAVEL_COST
        self.assertTrue(g.has_any_option(s))

    def test_crafting_in_progress(self):
        s = _bare_state()
        s["cash"] = 0
        s["crafting"] = {"name": "AI Customer Support", "quality": 0.7, "days_left": 1}
        self.assertTrue(g.has_any_option(s))

    def test_can_buy_cheap_token(self):
        s = _bare_state()
        s["cash"] = 5  # less than TRAVEL_COST
        s["location"] = "Meta"
        s["location_type"] = "provider"
        s["provider_prices"]["Meta"] = {t: 1 for t in g.TOKEN_TYPES}
        self.assertTrue(g.has_any_option(s))

    def test_can_craft_from_stock(self):
        s = _bare_state()
        s["cash"] = 0
        for t, qty in g.PRODUCTS["AI Customer Support"]["recipe"].items():
            s["tokens"][t] = {"qty": qty, "quality_sum": 0.9 * qty}
        self.assertTrue(g.has_any_option(s))

    def test_can_sell_at_current_client(self):
        s = _bare_state()
        s["cash"] = 0
        s["active_clients"] = [{
            "name": "TestCo",
            "type": "Enterprise",
            "min_quality": 0.5,
            "current_wants": {"AI Customer Support": {"budget": 50_000, "min_quality": 0.5}},
        }]
        s["location"] = "TestCo"
        s["location_type"] = "client"
        s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        self.assertTrue(g.has_any_option(s))

    def test_dead_end(self):
        s = _bare_state()
        s["cash"] = 0
        s["tokens"] = {}
        s["products"] = []
        s["crafting"] = None
        s["location"] = "Meta"
        s["location_type"] = "provider"
        # Make all prices exceed cash (0).
        s["provider_prices"]["Meta"] = {t: 5 for t in g.TOKEN_TYPES}
        self.assertFalse(g.has_any_option(s))


# ─────────────────────────────────────────────
# UI rendering (smoke tests — should not raise)
# ─────────────────────────────────────────────

class UIRenderTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_term_width_clamps(self):
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((40, 20))):
            self.assertEqual(g._term_width(), 64)
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((9999, 20))):
            self.assertEqual(g._term_width(), 120)
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((90, 20))):
            self.assertEqual(g._term_width(), 90)

    def test_key_formats_letter(self):
        out = g._key("B", "uy")
        self.assertIn("B", out)
        self.assertIn("uy", out)

    def test_rule_prints(self):
        out = _silent(g.rule)
        self.assertIsNone(out)  # rule returns nothing

    def test_clear_calls_os_system(self):
        with mock.patch("os.system") as sys_mock:
            g.clear()
            sys_mock.assert_called_once()

    def test_header_at_provider(self):
        with mock.patch("os.system"):
            _silent(g.header, self.s)

    def test_header_at_client(self):
        with mock.patch("os.system"):
            self.s["location"] = self.s["active_clients"][0]["name"]
            self.s["location_type"] = "client"
            _silent(g.header, self.s)

    def test_header_with_crafting(self):
        with mock.patch("os.system"):
            self.s["crafting"] = {"name": "AI Customer Support", "quality": 0.8, "days_left": 2}
            _silent(g.header, self.s)

    def test_status_bar_with_and_without_crafting(self):
        _silent(g.status_bar, self.s)
        self.s["crafting"] = {"name": "AI Customer Support", "quality": 0.8, "days_left": 2}
        _silent(g.status_bar, self.s)

    def test_show_event(self):
        self.s["last_event"] = "Something happened"
        _, out = _capture(g.show_event, self.s)
        self.assertIn("Something happened", out)
        self.assertIsNone(self.s["last_event"])
        # Second call with event cleared prints nothing.
        _, out2 = _capture(g.show_event, self.s)
        self.assertEqual(out2, "")

    def test_show_message(self):
        self.s["message"] = "hello"
        _, out = _capture(g.show_message, self.s)
        self.assertIn("hello", out)
        self.assertIsNone(self.s["message"])
        _, out2 = _capture(g.show_message, self.s)
        self.assertEqual(out2, "")

    def test_show_provider_price_grid(self):
        _, out = _capture(g.show_provider_price_grid, self.s)
        for prov in g.PROVIDERS:
            self.assertIn(prov, out)

    def test_show_provider_price_grid_at_client(self):
        self.s["location"] = self.s["active_clients"][0]["name"]
        self.s["location_type"] = "client"
        _silent(g.show_provider_price_grid, self.s)

    def test_show_location_panel_at_provider_returns_silently(self):
        _, out = _capture(g.show_location_panel, self.s)
        self.assertEqual(out, "")

    def test_show_location_panel_at_client_with_wants(self):
        client = self.s["active_clients"][0]
        # Ensure at least one want exists.
        if not client["current_wants"]:
            client["current_wants"]["AI Customer Support"] = {"budget": 50000, "min_quality": 0.5}
        self.s["location"] = client["name"]
        self.s["location_type"] = "client"
        _, out = _capture(g.show_location_panel, self.s)
        self.assertIn(client["name"], out)

    def test_show_location_panel_at_client_without_wants(self):
        client = self.s["active_clients"][0]
        client["current_wants"] = {}
        self.s["location"] = client["name"]
        self.s["location_type"] = "client"
        _, out = _capture(g.show_location_panel, self.s)
        self.assertIn("no open contracts", out)

    def test_show_inventory_inline_paths(self):
        # Empty tokens & products.
        _, out = _capture(g.show_inventory_inline, self.s)
        self.assertIn("Tokens", out)
        self.assertIn("Products", out)
        # Populated.
        self.s["tokens"] = {"Code": {"qty": 10, "quality_sum": 8.0}}
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.8}]
        self.s["crafting"] = {"name": "Contract Analyzer", "quality": 0.7, "days_left": 3}
        _, out = _capture(g.show_inventory_inline, self.s)
        self.assertIn("Code", out)
        self.assertIn("AI Customer Support", out)
        self.assertIn("Contract Analyzer", out)

    def test_compute_market_demand(self):
        demand = g.compute_market_demand(self.s)
        self.assertIsInstance(demand, dict)

    def test_show_market_demand_paths(self):
        _silent(g.show_market_demand, self.s)
        # Empty case
        for c in self.s["active_clients"]:
            c["current_wants"] = {}
        _, out = _capture(g.show_market_demand, self.s)
        self.assertIn("no open contracts", out)

    def test_recipe_short_includes_all_tokens(self):
        s = g._recipe_short("AI Customer Support")
        self.assertIn("Co", s)
        self.assertIn("Vo", s)

    def test_show_open_contracts_with_and_without(self):
        _silent(g.show_open_contracts, self.s)
        for c in self.s["active_clients"]:
            c["current_wants"] = {}
        _, out = _capture(g.show_open_contracts, self.s)
        self.assertIn("none", out)

    def test_show_provider(self):
        self.s["location"] = "Anthropic"
        self.s["location_type"] = "provider"
        _, out = _capture(g.show_provider, self.s)
        self.assertIn("Anthropic", out)
        # With existing stocks.
        self.s["tokens"] = {"Code": {"qty": 10, "quality_sum": 8.0}}
        _, out = _capture(g.show_provider, self.s)
        self.assertIn("Code", out)

    def test_show_client_offers_paths(self):
        client = self.s["active_clients"][0]
        client["current_wants"] = {"AI Customer Support": {"budget": 50_000, "min_quality": 0.5}}
        self.s["location"] = client["name"]
        self.s["location_type"] = "client"
        _, out = _capture(g.show_client_offers, self.s)
        self.assertIn("AI Customer Support", out)
        client["current_wants"] = {}
        _, out = _capture(g.show_client_offers, self.s)
        self.assertIn("no open contracts", out)
        # Location pointing to a stale client name.
        self.s["location"] = "GhostCo"
        _, out = _capture(g.show_client_offers, self.s)
        self.assertIn("no open contracts", out)

    def test_show_tokens_paths(self):
        _, out = _capture(g.show_tokens, self.s)
        self.assertIn("none", out)
        self.s["tokens"] = {"Code": {"qty": 5, "quality_sum": 4.0}}
        _, out = _capture(g.show_tokens, self.s)
        self.assertIn("Code", out)

    def test_show_products_paths(self):
        _, out = _capture(g.show_products, self.s)
        self.assertIn("none", out)
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        _, out = _capture(g.show_products, self.s)
        self.assertIn("AI Customer Support", out)

    def test_show_craftable(self):
        _, out = _capture(g.show_craftable, self.s)
        for p in g.PRODUCTS:
            self.assertIn(p, out)

    def test_show_all_clients(self):
        _, out = _capture(g.show_all_clients, self.s)
        self.assertTrue(out)

    def test_pause_handles_eof(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            g.pause()
        with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            g.pause()
        with mock.patch("builtins.input", return_value=""):
            g.pause()


class PromptTests(unittest.TestCase):
    def test_prompt_int_valid(self):
        with mock.patch("builtins.input", return_value="42"):
            self.assertEqual(g.prompt_int("x"), 42)

    def test_prompt_int_empty(self):
        with mock.patch("builtins.input", return_value=""):
            self.assertIsNone(g.prompt_int("x"))

    def test_prompt_int_invalid(self):
        with mock.patch("builtins.input", return_value="abc"):
            self.assertIs(g.prompt_int("x"), g.INVALID_INPUT)

    def test_prompt_int_eof(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(g.prompt_int("x"))

    def test_prompt_str(self):
        with mock.patch("builtins.input", return_value=" hello "):
            self.assertEqual(g.prompt_str("x"), "hello")
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertEqual(g.prompt_str("x"), "")


# ─────────────────────────────────────────────
# Menu wrappers (interactive prompts)
# ─────────────────────────────────────────────

class MenuBuyTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()
        self.s["location"] = "Meta"
        self.s["location_type"] = "provider"
        self.s["provider_prices"]["Meta"] = {t: 1 for t in g.TOKEN_TYPES}

    def test_buy_blocked_at_client_location(self):
        self.s["location_type"] = "client"
        _silent(g.menu_buy, self.s)
        self.assertIn("provider", self.s["message"])

    def test_buy_invalid_token_input(self):
        with mock.patch("builtins.input", return_value="abc"):
            _silent(g.menu_buy, self.s)
        self.assertIn("number", self.s["message"])

    def test_buy_cancel_on_zero(self):
        with mock.patch("builtins.input", return_value="0"):
            _silent(g.menu_buy, self.s)
        self.assertIsNone(self.s["message"])

    def test_buy_token_out_of_range(self):
        with mock.patch("builtins.input", return_value="99"):
            _silent(g.menu_buy, self.s)
        self.assertIn("Pick a token", self.s["message"])

    def test_buy_invalid_qty(self):
        with mock.patch("builtins.input", side_effect=["1", "abc"]):
            _silent(g.menu_buy, self.s)
        self.assertIn("number", self.s["message"])

    def test_buy_qty_cancel(self):
        with mock.patch("builtins.input", side_effect=["1", "0"]):
            _silent(g.menu_buy, self.s)

    def test_buy_qty_negative(self):
        with mock.patch("builtins.input", side_effect=["1", "-1"]):
            _silent(g.menu_buy, self.s)
        self.assertIn("positive", self.s["message"])

    def test_buy_success_advances_day(self):
        day0 = self.s["day"]
        with mock.patch("builtins.input", side_effect=["1", "5"]), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.menu_buy, self.s)
        self.assertEqual(self.s["day"], day0 + 1)


class MenuSellTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()
        self.s["active_clients"][0] = {
            "name": "TestCo",
            "type": "Enterprise",
            "min_quality": 0.5,
            "current_wants": {"AI Customer Support": {"budget": 50_000, "min_quality": 0.5}},
        }
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        self.s["location"] = "TestCo"
        self.s["location_type"] = "client"

    def test_sell_blocked_at_provider_location(self):
        self.s["location_type"] = "provider"
        _silent(g.menu_sell, self.s)
        self.assertIn("client", self.s["message"])

    def test_sell_with_stale_location(self):
        self.s["location"] = "GhostCorp"
        _silent(g.menu_sell, self.s)
        self.assertIn("no longer", self.s["message"])

    def test_sell_with_no_products(self):
        self.s["products"] = []
        _silent(g.menu_sell, self.s)
        self.assertIn("no built products", self.s["message"].lower())

    def test_sell_client_no_wants(self):
        self.s["active_clients"][0]["current_wants"] = {}
        _silent(g.menu_sell, self.s)
        self.assertIn("no open contracts", self.s["message"])

    def test_sell_invalid_choice(self):
        with mock.patch("builtins.input", side_effect=["abc", ""]):
            _silent(g.menu_sell, self.s)
        self.assertIn("number", self.s["message"])

    def test_sell_cancel_zero(self):
        with mock.patch("builtins.input", side_effect=["0", ""]):
            _silent(g.menu_sell, self.s)

    def test_sell_out_of_range(self):
        with mock.patch("builtins.input", side_effect=["99", ""]):
            _silent(g.menu_sell, self.s)
        self.assertIn("Pick a product", self.s["message"])

    def test_sell_success(self):
        day0 = self.s["day"]
        with mock.patch("builtins.input", side_effect=["1", ""]), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.menu_sell, self.s)
        self.assertEqual(self.s["day"], day0 + 1)
        self.assertEqual(self.s["products"], [])


class MenuCraftTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_craft_already_busy(self):
        self.s["crafting"] = {"name": "Contract Analyzer", "quality": 0.7, "days_left": 2}
        _silent(g.menu_craft, self.s)
        self.assertIn("Already crafting", self.s["message"])

    def test_craft_invalid_input(self):
        with mock.patch("builtins.input", return_value="abc"):
            _silent(g.menu_craft, self.s)
        self.assertIn("number", self.s["message"])

    def test_craft_cancel_zero(self):
        with mock.patch("builtins.input", return_value="0"):
            _silent(g.menu_craft, self.s)

    def test_craft_out_of_range(self):
        with mock.patch("builtins.input", return_value="99"):
            _silent(g.menu_craft, self.s)
        self.assertIn("Pick a product", self.s["message"])

    def test_craft_success(self):
        for t, qty in g.PRODUCTS["AI Customer Support"]["recipe"].items():
            self.s["tokens"][t] = {"qty": qty, "quality_sum": 0.9 * qty}
        day0 = self.s["day"]
        with mock.patch("builtins.input", return_value="1"), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.menu_craft, self.s)
        self.assertIsNotNone(self.s["crafting"])
        self.assertEqual(self.s["day"], day0 + 1)


class MenuTravelTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_travel_invalid_input(self):
        with mock.patch("builtins.input", return_value="abc"):
            _silent(g.menu_travel, self.s)
        self.assertIn("number", self.s["message"])

    def test_travel_cancel_zero(self):
        with mock.patch("builtins.input", return_value="0"):
            _silent(g.menu_travel, self.s)

    def test_travel_out_of_range(self):
        with mock.patch("builtins.input", return_value="999"):
            _silent(g.menu_travel, self.s)
        self.assertIn("Pick a destination", self.s["message"])

    def test_travel_success(self):
        day0 = self.s["day"]
        # First destination is a provider; pick "1" to travel.
        with mock.patch("builtins.input", return_value="1"), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.menu_travel, self.s)
        self.assertEqual(self.s["day"], day0 + 1)


class MenuBorrowTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_borrow_no_products(self):
        _silent(g.menu_borrow, self.s)
        self.assertIn("collateral", self.s["message"])

    def test_borrow_fully_tapped(self):
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        self.s["collateral_debt"] = g.borrow_limit(self.s)
        _silent(g.menu_borrow, self.s)
        self.assertIn("fully tapped", self.s["message"])

    def test_borrow_invalid_input(self):
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        with mock.patch("builtins.input", return_value="abc"):
            _silent(g.menu_borrow, self.s)
        self.assertIn("dollar amount", self.s["message"])

    def test_borrow_cancel_zero(self):
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        with mock.patch("builtins.input", return_value="0"):
            _silent(g.menu_borrow, self.s)

    def test_borrow_success(self):
        self.s["products"] = [{"name": "AI Customer Support", "quality": 0.9}]
        with mock.patch("builtins.input", return_value="100"), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.menu_borrow, self.s)
        self.assertIn("Borrowed", self.s["message"])


class MenuPayDebtTests(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.s = g.new_game()

    def test_pay_no_debt(self):
        self.s["debt"] = 0
        _silent(g.menu_pay_debt, self.s)
        self.assertIn("debt-free", self.s["message"])

    def test_pay_invalid(self):
        with mock.patch("builtins.input", return_value="abc"):
            _silent(g.menu_pay_debt, self.s)
        self.assertIn("dollar amount", self.s["message"])

    def test_pay_cancel_zero(self):
        with mock.patch("builtins.input", return_value="0"):
            _silent(g.menu_pay_debt, self.s)

    def test_pay_success_advances_day(self):
        day0 = self.s["day"]
        with mock.patch("builtins.input", return_value="100"), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.menu_pay_debt, self.s)
        self.assertEqual(self.s["day"], day0 + 1)


class MenuNextTests(unittest.TestCase):
    def test_menu_next_advances_day(self):
        random.seed(0)
        s = g.new_game()
        day0 = s["day"]
        with mock.patch("random.random", return_value=0.99):
            g.menu_next(s)
        self.assertEqual(s["day"], day0 + 1)


# ─────────────────────────────────────────────
# End / bankruptcy screens
# ─────────────────────────────────────────────

class EndScreenTests(unittest.TestCase):
    def _run_end(self, cash, debt, products=()):
        s = _bare_state()
        s["cash"] = cash
        s["debt"] = debt
        s["products"] = list(products)
        with mock.patch("os.system"):
            _, out = _capture(g.end_screen, s)
        return out

    def test_unicorn(self):
        out = self._run_end(1_500_000, 0)
        self.assertIn("UNICORN", out)
        self.assertIn("Debt-free bonus", out)

    def test_series_a(self):
        out = self._run_end(600_000, 0)
        self.assertIn("SERIES A", out)

    def test_ramen(self):
        out = self._run_end(200_000, 0)
        self.assertIn("RAMEN", out)

    def test_broke_even(self):
        out = self._run_end(50_000, 50_000)
        self.assertIn("BROKE EVEN", out)

    def test_bankrupt(self):
        out = self._run_end(0, 500_000)
        self.assertIn("BANKRUPT", out)


class BankruptcyScreenTests(unittest.TestCase):
    def test_bankruptcy_screen_prints_summary(self):
        s = _bare_state()
        s["cash"] = 0
        s["debt"] = 300_000
        with mock.patch("os.system"), mock.patch("builtins.input", return_value=""):
            _, out = _capture(g.bankruptcy_screen, s)
        self.assertIn("BANKRUPTCY", out)


# ─────────────────────────────────────────────
# game_loop + main (top-level entry points)
# ─────────────────────────────────────────────

class GameLoopTests(unittest.TestCase):
    def test_loop_quits_immediately(self):
        random.seed(0)
        s = g.new_game()
        with mock.patch("os.system"), mock.patch("builtins.input", return_value="q"):
            _silent(g.game_loop, s)

    def test_loop_unknown_command_then_quit(self):
        random.seed(0)
        s = g.new_game()
        with mock.patch("os.system"), mock.patch("builtins.input", side_effect=["zzz", "q"]):
            _silent(g.game_loop, s)
        self.assertEqual(s["message"], None)  # message consumed by header

    def test_loop_each_hotkey(self):
        random.seed(0)
        s = g.new_game()
        # Each hotkey is followed by "0" (cancel inner prompt) where needed.
        # Travel/buy/sell/craft/borrow/pay/next/quit.
        inputs = iter([
            "n",      # next
            "b", "0", # buy → cancel
            "c", "0", # craft → cancel
            "t", "0", # travel → cancel
            "l",      # borrow (no products → message, no inner prompt)
            "p", "0", # pay → cancel
            "s",      # sell (provider location → message)
            "q",
        ])
        with mock.patch("os.system"), \
             mock.patch("builtins.input", side_effect=lambda *a, **k: next(inputs)), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.game_loop, s)

    def test_loop_terminates_on_eof(self):
        random.seed(0)
        s = g.new_game()
        with mock.patch("os.system"), mock.patch("builtins.input", side_effect=EOFError):
            _silent(g.game_loop, s)

    def test_loop_runs_to_max_days(self):
        random.seed(0)
        s = g.new_game()
        s["day"] = g.MAX_DAYS  # one more iteration
        with mock.patch("os.system"), mock.patch("builtins.input", return_value="n"), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.game_loop, s)
        self.assertGreater(s["day"], g.MAX_DAYS)

    def test_loop_triggers_bankruptcy(self):
        random.seed(0)
        s = g.new_game()
        s["cash"] = 0
        s["tokens"] = {}
        s["products"] = []
        s["crafting"] = None
        s["location"] = "Anthropic"
        s["location_type"] = "provider"
        # Force all prices high so has_any_option returns False.
        s["provider_prices"]["Anthropic"] = {t: 100_000 for t in g.TOKEN_TYPES}
        with mock.patch("os.system"), mock.patch("builtins.input", return_value=""):
            _silent(g.game_loop, s)

    def test_loop_with_stale_client_location(self):
        random.seed(0)
        s = g.new_game()
        s["location"] = "GhostClient"
        s["location_type"] = "client"
        with mock.patch("os.system"), mock.patch("builtins.input", return_value="q"):
            _silent(g.game_loop, s)


class MainTests(unittest.TestCase):
    def test_main_runs_with_immediate_quit(self):
        with mock.patch("os.system"), \
             mock.patch("builtins.input", side_effect=["", "q"]), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.main)


if __name__ == "__main__":
    unittest.main()
