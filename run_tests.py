#!/usr/bin/env python3
"""
Run the test suite and report line coverage for hallucination_inc.py.

Stdlib only (unittest + trace + ast — no third-party deps). Exits non-zero if
tests fail or coverage falls below COVERAGE_THRESHOLD. Wired into
.git/hooks/pre-commit so commits can't drop the bar.
"""

import argparse
import ast
import io
import os
import sys
import trace
import unittest
from contextlib import redirect_stdout

# Files we care about. Other project files (simulate.py, test_*.py) are
# excluded from the gate but tracked for visibility.
TARGET_FILES = ["engine.py", "terminal.py"]
COVERAGE_THRESHOLD = 90.0
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def executable_lines(filepath):
    """All line numbers that contain an executable statement.

    Walks the AST and returns the line of every ``stmt`` node — close enough
    to what coverage.py considers executable, without the dependency.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=filepath)
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            lines.add(node.lineno)
    return lines


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


def covered_lines(tracer_counts, target_path):
    """Subset of tracer counts that hit the target file."""
    hit = set()
    for (fname, lineno), count in tracer_counts.items():
        if count > 0 and _same_file(fname, target_path):
            hit.add(lineno)
    return hit


def _discover_suite():
    loader = unittest.TestLoader()
    return loader.discover(PROJECT_ROOT, pattern="test_*.py")


def run_tests_with_coverage(verbosity=1, quiet_app_output=True):
    """Drive unittest under a stdlib tracer. Returns (test_result, counts)."""
    suite = _discover_suite()
    runner = unittest.TextTestRunner(verbosity=verbosity, stream=sys.stderr)

    tracer = trace.Trace(
        count=True,
        trace=False,
        ignoredirs=[sys.prefix, sys.exec_prefix],
    )

    # Box the result out so runfunc doesn't need to return it via stdlib magic.
    box = {}

    def _run():
        if quiet_app_output:
            # Game prints heavily; keep CI output clean by tossing stdout
            # from the suite. Test failures still surface via stderr.
            with redirect_stdout(io.StringIO()):
                box["result"] = runner.run(suite)
        else:
            box["result"] = runner.run(suite)

    tracer.runfunc(_run)
    return box["result"], tracer.results().counts


def report(counts, threshold):
    """Print a per-file coverage table. Returns True if the gate passes."""
    print()
    print(f"{'File':<32} {'Stmts':>6} {'Miss':>6} {'Cover':>7}")
    print("-" * 55)
    all_pass = True
    for target in TARGET_FILES:
        path = os.path.join(PROJECT_ROOT, target)
        total = executable_lines(path)
        hit = covered_lines(counts, path)
        miss = total - hit
        pct = 100.0 * len(hit) / len(total) if total else 100.0
        marker = "✓" if pct >= threshold else "✗"
        print(f"{target:<32} {len(total):>6} {len(miss):>6} {pct:>6.1f}% {marker}")
        if pct < threshold:
            all_pass = False
            print(f"  ↳ missed lines: {sorted(miss)[:30]}"
                  + (" …" if len(miss) > 30 else ""))
    print("-" * 55)
    print(f"Threshold: {threshold:.1f}%")
    return all_pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=COVERAGE_THRESHOLD,
                        help="Minimum line coverage percent (default: %(default)s)")
    parser.add_argument("--verbose", "-v", action="count", default=1,
                        help="unittest verbosity (-v -v for more)")
    parser.add_argument("--show-output", action="store_true",
                        help="Don't suppress the game's stdout during tests")
    args = parser.parse_args()

    result, counts = run_tests_with_coverage(
        verbosity=args.verbose,
        quiet_app_output=not args.show_output,
    )

    if not result.wasSuccessful():
        print("\nTests failed — skipping coverage gate.", file=sys.stderr)
        sys.exit(1)

    if not report(counts, args.threshold):
        print(
            f"\nCoverage below {args.threshold:.1f}% — commit blocked.",
            file=sys.stderr,
        )
        sys.exit(2)

    print("\nAll tests passed and coverage gate cleared.")
    sys.exit(0)


if __name__ == "__main__":
    main()
