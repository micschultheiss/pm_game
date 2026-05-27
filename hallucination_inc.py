#!/usr/bin/env python3
"""
Hallucination Inc. — entry point.

Dispatches to a frontend:

- default: terminal UI (``python3 hallucination_inc.py``)
- ``--web``: Flask web frontend (``python3 hallucination_inc.py --web``);
  requires Flask — install via ``pip install -r requirements.txt``.
"""

import sys


def main():
    if "--web" in sys.argv:
        from web import main as web_main
        web_main()
    else:
        from terminal import main as terminal_main
        terminal_main()


if __name__ == "__main__":
    main()
