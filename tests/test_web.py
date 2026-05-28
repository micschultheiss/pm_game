#!/usr/bin/env python3
"""
Unit tests for web.py — Flask web frontend.

Smoke tests via Flask's test client. Verifies the welcome → game flow,
each action route round-trips through the engine, /new resets state,
and action POSTs against a stale session bail out gracefully instead
of silently advancing a phantom Day-1 game.

Engine logic tests live in test_engine.py; terminal frontend tests in
test_terminal.py.
"""

import importlib
import random
import unittest

import engine


def _reload_web():
    """Fresh web module = empty _games dict + fresh app instance."""
    import web
    importlib.reload(web)
    return web


class WebTestBase(unittest.TestCase):
    def setUp(self):
        random.seed(0)
        self.web = _reload_web()
        self.client = self.web.app.test_client()

    def _session(self):
        """Return the lone session dict in _games (asserts exactly one)."""
        sids = list(self.web._games.keys())
        self.assertEqual(len(sids), 1, f"expected 1 session, found {len(sids)}")
        return self.web._games[sids[0]]

    def _state(self):
        return self._session()["state"]

    def _start_game(self):
        """Visit / (creates session + cookie), then POST /start."""
        self.client.get("/")
        self.client.post("/start")


# ─────────────────────────────────────────────
# Welcome → game transition
# ─────────────────────────────────────────────

class WelcomeTests(WebTestBase):
    def test_fresh_get_shows_welcome(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_data(as_text=True)
        self.assertIn("Start the run", body)
        self.assertIn("HALLUCINATION INC.", body)

    def test_fresh_get_sets_cookie(self):
        resp = self.client.get("/")
        self.assertIn("hinc_sid=", resp.headers.get("Set-Cookie", ""))

    def test_start_dismisses_welcome(self):
        self._start_game()
        body = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("Start the run", body)
        self.assertIn("Day 1/", body)

    def test_start_redirects_with_303(self):
        self.client.get("/")
        resp = self.client.post("/start")
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(resp.headers["Location"], "/")


# ─────────────────────────────────────────────
# Action routes — happy-path round trips
# ─────────────────────────────────────────────

class ActionRouteTests(WebTestBase):
    def setUp(self):
        super().setUp()
        self._start_game()

    def test_next_day_advances(self):
        before = self._state()["day"]
        resp = self.client.post("/next")
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(self._state()["day"], before + 1)

    def test_buy_round_trip(self):
        self.assertEqual(self._state()["location_type"], "provider")
        before_cash = self._state()["cash"]
        before_day = self._state()["day"]
        resp = self.client.post("/buy", data={"token": "Code", "qty": "10"})
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(self._state()["tokens"]["Code"]["qty"], 10)
        self.assertLess(self._state()["cash"], before_cash)
        self.assertEqual(self._state()["day"], before_day + 1)  # _apply ticks a day

    def test_buy_validates_qty(self):
        cash_before = self._state()["cash"]
        self.client.post("/buy", data={"token": "Code", "qty": "garbage"})
        self.assertEqual(self._state()["cash"], cash_before)
        self.assertIn("positive number", self._state()["message"])

    def test_buy_rejects_unknown_token(self):
        self.client.post("/buy", data={"token": "Foo", "qty": "5"})
        self.assertIn("Unknown token", self._state()["message"])

    def test_buy_requires_provider(self):
        # Travel to a client first
        client_name = self._state()["active_clients"][0]["name"]
        self.client.post("/travel",
                         data={"dest_type": "client", "dest_name": client_name})
        self.client.post("/buy", data={"token": "Code", "qty": "5"})
        self.assertIn("provider", self._state()["message"])

    def test_craft_round_trip(self):
        # Brand Asset Generator: Image 60M + Code 10M, 2-day build
        self.client.post("/buy", data={"token": "Image", "qty": "60"})
        self.client.post("/buy", data={"token": "Code", "qty": "10"})
        self.client.post("/craft", data={"product": "Brand Asset Generator"})
        self.assertIsNotNone(self._state()["crafting"])
        self.assertEqual(self._state()["crafting"]["name"], "Brand Asset Generator")

    def test_craft_rejects_unknown_product(self):
        self.client.post("/craft", data={"product": "Nonexistent Widget"})
        self.assertIn("Unknown product", self._state()["message"])

    def test_travel_to_provider(self):
        before = self._state()["location"]
        target = next(p for p in engine.PROVIDERS if p != before)
        self.client.post("/travel",
                         data={"dest_type": "provider", "dest_name": target})
        self.assertEqual(self._state()["location"], target)

    def test_travel_to_client(self):
        client_name = self._state()["active_clients"][0]["name"]
        self.client.post("/travel",
                         data={"dest_type": "client", "dest_name": client_name})
        self.assertEqual(self._state()["location"], client_name)
        self.assertEqual(self._state()["location_type"], "client")

    def test_travel_validates_dest_type(self):
        before = self._state()["location"]
        self.client.post("/travel",
                         data={"dest_type": "elsewhere", "dest_name": "OpenAI"})
        self.assertEqual(self._state()["location"], before)
        self.assertIn("Invalid destination", self._state()["message"])

    def test_borrow_round_trip(self):
        # Borrow needs a product as collateral. Inject one directly.
        self._state()["products"].append({
            "name": "Brand Asset Generator", "quality": 0.9,
        })
        before_cash = self._state()["cash"]
        before_debt = self._state()["debt"]
        self.client.post("/borrow", data={"amount": "5000"})
        self.assertGreater(self._state()["cash"], before_cash)
        self.assertGreater(self._state()["debt"], before_debt)

    def test_borrow_validates_amount(self):
        cash_before = self._state()["cash"]
        self.client.post("/borrow", data={"amount": "-100"})
        self.assertEqual(self._state()["cash"], cash_before)
        self.assertIn("positive amount", self._state()["message"])

    def test_pay_round_trip(self):
        before_cash = self._state()["cash"]
        before_debt = self._state()["debt"]
        # Daily interest is 3% of debt (~$3K on the starting balance), so
        # pay more than that to see a net drop after _apply ticks a day.
        self.client.post("/pay", data={"amount": "10000"})
        self.assertEqual(self._state()["cash"], before_cash - 10000)
        self.assertLess(self._state()["debt"], before_debt)

    def test_pay_validates_amount(self):
        debt_before = self._state()["debt"]
        self.client.post("/pay", data={"amount": "0"})
        self.assertEqual(self._state()["debt"], debt_before)
        self.assertIn("positive amount", self._state()["message"])

    def test_sell_requires_client(self):
        # Still at a provider
        self.client.post("/sell", data={"product_idx": "0"})
        self.assertIn("client", self._state()["message"])

    def test_sell_round_trip(self):
        # Plant a finished product matching the first active client's wants
        client = self._state()["active_clients"][0]
        wanted = next(iter(client["current_wants"].keys()))
        self._state()["products"].append({"name": wanted, "quality": 0.95})

        self.client.post("/travel",
                         data={"dest_type": "client", "dest_name": client["name"]})
        before_cash = self._state()["cash"]
        before_count = len(self._state()["products"])
        self.client.post("/sell", data={"product_idx": "0"})
        self.assertGreater(self._state()["cash"], before_cash)
        self.assertEqual(len(self._state()["products"]), before_count - 1)

    def test_sell_invalid_product_idx(self):
        client = self._state()["active_clients"][0]
        self.client.post("/travel",
                         data={"dest_type": "client", "dest_name": client["name"]})
        self.client.post("/sell", data={"product_idx": "garbage"})
        self.assertIn("Invalid product", self._state()["message"])


# ─────────────────────────────────────────────
# /new resets state and returns to welcome
# ─────────────────────────────────────────────

class NewGameTests(WebTestBase):
    def test_new_wipes_progress_and_returns_to_welcome(self):
        self._start_game()
        self.client.post("/next")
        self.assertGreater(self._state()["day"], 1)
        self.client.post("/new")
        self.assertEqual(self._state()["day"], 1)
        self.assertFalse(self._session()["started"])
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("Start the run", body)


# ─────────────────────────────────────────────
# Stale-session guard — see cbf290c
# ─────────────────────────────────────────────

class StaleSessionTests(WebTestBase):
    def test_next_with_unknown_sid_bails_out(self):
        # Browser POSTs with a cookie the server doesn't recognise (e.g.
        # after a server restart wiped _games). Action must NOT silently
        # spin up a fresh game and tick it forward.
        resp = self.client.post("/next",
                                headers={"Cookie": "hinc_sid=phantom"})
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(self._state()["day"], 1)
        self.assertFalse(self._session()["started"])

    def test_all_action_routes_bail_out_on_unstarted_session(self):
        # Create a session via GET / (welcome), then hit every action.
        # None of them should advance state past Day 1.
        self.client.get("/")
        for path, data in [
            ("/buy",    {"token": "Code", "qty": "5"}),
            ("/craft",  {"product": "Brand Asset Generator"}),
            ("/sell",   {"product_idx": "0"}),
            ("/travel", {"dest_type": "provider", "dest_name": "OpenAI"}),
            ("/next",   {}),
            ("/borrow", {"amount": "5000"}),
            ("/pay",    {"amount": "100"}),
        ]:
            resp = self.client.post(path, data=data)
            self.assertEqual(resp.status_code, 303, f"{path} should redirect")
        self.assertEqual(self._state()["day"], 1)
        self.assertFalse(self._session()["started"])


# ─────────────────────────────────────────────
# View helpers (pure functions of state)
# ─────────────────────────────────────────────

class ViewHelperTests(WebTestBase):
    def setUp(self):
        super().setUp()
        self._start_game()

    def test_provider_grid_marks_current_location(self):
        rows = self.web._provider_grid(self._state())
        here_rows = [r for r in rows if r["here"]]
        self.assertEqual(len(here_rows), 1)
        self.assertEqual(here_rows[0]["name"], self._state()["location"])

    def test_destinations_excludes_current_location(self):
        dests = self.web._destinations(self._state())
        names = ([p["name"] for p in dests["providers"]] +
                 [c["name"] for c in dests["clients"]])
        self.assertNotIn(self._state()["location"], names)

    def test_location_info_provider(self):
        info = self.web._location_info(self._state())
        self.assertEqual(info["type"], "provider")
        self.assertIn("prices", info)

    def test_location_info_client(self):
        s = self._state()
        client = s["active_clients"][0]
        s["location"] = client["name"]
        s["location_type"] = "client"
        info = self.web._location_info(s)
        self.assertEqual(info["type"], "client")
        self.assertFalse(info["stale"])
        self.assertIn("wants", info)

    def test_location_info_stale_client(self):
        s = self._state()
        s["location"] = "Some Rotated-Out Client"
        s["location_type"] = "client"
        info = self.web._location_info(s)
        self.assertTrue(info["stale"])

    def test_inventory_view_empty(self):
        inv = self.web._inventory_view(self._state())
        self.assertEqual(inv["tokens"], [])
        self.assertEqual(inv["products"], [])
        self.assertIsNone(inv["crafting"])

    def test_inventory_view_with_tokens(self):
        self.client.post("/buy", data={"token": "Code", "qty": "10"})
        inv = self.web._inventory_view(self._state())
        self.assertTrue(any(t["type"] == "Code" and t["qty"] == 10
                            for t in inv["tokens"]))

    def test_contracts_view_sorted_by_budget(self):
        rows = self.web._contracts_view(self._state())
        budgets = [r["budget"] for r in rows]
        self.assertEqual(budgets, sorted(budgets, reverse=True))

    def test_sellables_empty_at_provider(self):
        self.assertEqual(
            self.web._sellables_at_current_location(self._state()), [])

    def test_sellables_at_matching_client(self):
        client = self._state()["active_clients"][0]
        wanted = next(iter(client["current_wants"].keys()))
        self._state()["products"].append({"name": wanted, "quality": 0.9})
        self._state()["location"] = client["name"]
        self._state()["location_type"] = "client"
        rows = self.web._sellables_at_current_location(self._state())
        self.assertTrue(any(r["name"] == wanted for r in rows))


# ─────────────────────────────────────────────
# End-of-run screens
# ─────────────────────────────────────────────

class EndScreenTests(WebTestBase):
    def test_game_over_screen_renders_after_max_days(self):
        self._start_game()
        self._state()["day"] = engine.MAX_DAYS + 1
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("GAME OVER", body)

    def test_bankruptcy_screen_renders_when_no_options(self):
        self._start_game()
        s = self._state()
        s["cash"] = 0
        s["debt"] = 100_000
        s["tokens"] = {}
        s["products"] = []
        s["crafting"] = None
        self.assertTrue(engine.is_bankrupt(s))
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("BANKRUPTCY", body)


if __name__ == "__main__":
    unittest.main()
