"""
Shared helpers for the test suite.

Imported by ``test_engine.py`` and ``test_terminal.py``. The helpers seed
the RNG deterministically and build fresh game states via the engine, so
they work the same regardless of which frontend the calling test targets.
"""

import io
import random
from contextlib import redirect_stdout

import engine


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
    return engine.new_game()


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
