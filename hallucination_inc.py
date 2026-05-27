#!/usr/bin/env python3
"""
Hallucination Inc. — entry point.

Dispatches to a frontend. The terminal UI is the default and only frontend
today; a web frontend is planned and will be selected here via a flag.

Run with ``python3 hallucination_inc.py``.
"""

from terminal import main


if __name__ == "__main__":
    main()
