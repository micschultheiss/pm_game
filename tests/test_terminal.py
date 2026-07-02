#!/usr/bin/env python3
"""
Unit tests for terminal.py — terminal frontend.

Covers UI rendering smoke tests, prompts, menu wrappers, end screens, and
the game loop / main entry point. Engine logic tests live in
test_engine.py.
"""

import io
import os
import random
import unittest
from contextlib import redirect_stdout
from unittest import mock

import _bootstrap  # noqa: F401  (side effect: puts src/ on sys.path)
import terminal as g

from test_helpers import _capture, _silent, _bare_state, _state_with


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


class BootSplashTests(unittest.TestCase):
    def test_boot_status_color_branches(self):
        self.assertEqual(g._boot_status_color("SKIPPED"), g._RED)
        self.assertEqual(g._boot_status_color("1100%"), g._DIM)
        self.assertEqual(g._boot_status_color("OK"), g._CY)

    def test_glyph_rows_unknown_char_falls_back_to_dot_glyph(self):
        rows = g._glyph_rows("H?")
        self.assertEqual(len(rows), g._GLYPH_ROWS)
        self.assertEqual(rows, g._glyph_rows("H."))

    def test_render_rows_reveal_sweeps_columns(self):
        rows = g._glyph_rows("HI")
        full = g._render_rows(rows)
        partial = g._render_rows(rows, cols=1)
        self.assertEqual(len(partial[0]), 1)
        self.assertGreater(len(full[0]), len(partial[0]))

    def test_boot_splash_non_tty_is_instant_and_prints_full_sequence(self):
        # Default test stdout (StringIO) is not a tty, so no sleeps/animation
        # frames run — this exercises the wide-terminal logo-reveal branch.
        with mock.patch("os.system"), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 30))):
            _, out = _capture(g.boot_splash)
        for label, status in g._BOOT_LOG:
            self.assertIn(label, out)
            self.assertIn(status, out)
        self.assertIn("Move fast and break things", out)

    def test_boot_splash_narrow_terminal_falls_back_to_plain_logo(self):
        with mock.patch("os.system"), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((64, 20))):
            _, out = _capture(g.boot_splash)
        self.assertIn("HALLUCINATION INC.", out)

    def test_boot_splash_animated_plays_sweep_frames(self):
        buf = io.StringIO()
        buf.isatty = lambda: True
        with mock.patch("os.system"), mock.patch("time.sleep"), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 30))), \
             redirect_stdout(buf):
            g.boot_splash(delay=0)
        out = buf.getvalue()
        self.assertIn("Move fast and break things", out)

    def test_boot_splash_keyboard_interrupt_skips_cleanly(self):
        buf = io.StringIO()
        buf.isatty = lambda: True
        with mock.patch("os.system"), mock.patch("time.sleep", side_effect=KeyboardInterrupt), \
             redirect_stdout(buf):
            g.boot_splash(delay=0)
        out = buf.getvalue()
        self.assertIn("Where AI Meets Enterprise", out)


class MainTests(unittest.TestCase):
    def test_main_runs_with_immediate_quit(self):
        with mock.patch("os.system"), \
             mock.patch("builtins.input", side_effect=["", "q"]), \
             mock.patch("random.random", return_value=0.99):
            _silent(g.main)


if __name__ == "__main__":
    unittest.main()
