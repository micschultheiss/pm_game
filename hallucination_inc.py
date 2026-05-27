#!/usr/bin/env python3
"""
Hallucination Inc. — entry point.

Dispatches to a frontend. The terminal UI is the default and only frontend
today; a web frontend is planned and will be selected here via a flag.

This module also re-exports the engine + terminal surface as a transitional
compatibility shim so callers that do ``import hallucination_inc as g``
keep working unchanged. Step 3 of the engine split will point the test
suite at ``engine`` and ``terminal`` directly and let this shim shrink.

Run with ``python3 hallucination_inc.py``.
"""

# Re-export engine surface (`from engine import *` skips underscore-prefixed
# names, so private helpers are pulled explicitly for tests that touch them).
from engine import *  # noqa: F401,F403
from engine import (
    _all_provider_crash,  # noqa: F401
    _all_provider_spike,  # noqa: F401
    _bonus_cash,  # noqa: F401
    _client_budget_crash,  # noqa: F401
    _client_budget_spike,  # noqa: F401
    _craft_setback,  # noqa: F401
    _find_template,  # noqa: F401
    _gov_budget_boost,  # noqa: F401
    _make_client_from_template,  # noqa: F401
    _provider_price_crash,  # noqa: F401
    _provider_price_spike,  # noqa: F401
    _recipe_size,  # noqa: F401
    _token_decay,  # noqa: F401
)

# Re-export terminal surface (UI helpers, menus, screens, REPL).
from terminal import *  # noqa: F401,F403
from terminal import (
    _key,  # noqa: F401
    _recipe_short,  # noqa: F401
    _term_width,  # noqa: F401
)


def main():
    """Launch the default frontend. Add ``--web`` dispatch here when web.py lands."""
    from terminal import main as terminal_main
    terminal_main()


if __name__ == "__main__":
    main()
