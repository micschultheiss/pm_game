"""Put src/ on sys.path so tests and the simulator can import the program
modules (engine, terminal, web).

Imported for its side effect as the very first import in each test module and
in simulate.py — before any `import engine`. Works under both the coverage
runner (run_tests.py) and plain `python3 -m unittest discover -s tests`,
since the tests dir is on sys.path in both cases.
"""

import os
import sys

_SRC = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
