#!/usr/bin/env python3
"""
Hallucination Inc. — entry point.

Dispatches to a frontend:

- default: terminal UI (``python3 hallucination_inc.py``)
- ``--web``: Flask web frontend (``python3 hallucination_inc.py --web``);
  requires Flask — install via ``pip install -r requirements.txt``.
"""

import os
import sys

# Program modules live in src/; put it on the path so the frontend imports
# below (and their `import engine` / `from engine import ...`) resolve.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def main():
    if "--web" in sys.argv:
        from web import main as web_main
        web_main()
    else:
        from terminal import main as terminal_main
        terminal_main()


if __name__ == "__main__":
    main()
