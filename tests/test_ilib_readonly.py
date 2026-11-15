"""1.12.18: runs tests/ilib_readonly_check.py (read-only actions such as at_suggest / col_peek keep the catalog)."""
import os, subprocess, sys


def test_ilib_readonly():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ilib_readonly_check.py")
    r = subprocess.run([sys.executable, f], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "ilib_readonly_check: OK" in r.stdout, r.stdout + r.stderr
