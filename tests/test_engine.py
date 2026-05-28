#!/usr/bin/env python3
"""
Unit tests for engine.py — pure game logic.

Covers constants, state setup, action functions, time progression, events,
client drift/rotation, and the bankruptcy oracle. UI tests live in
test_terminal.py.
"""

import random
import unittest
from unittest import mock

import _bootstrap  # noqa: F401  (side effect: puts src/ on sys.path)
import engine as g

from test_helpers import _bare_state, _state_with


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


if __name__ == "__main__":
    unittest.main()
