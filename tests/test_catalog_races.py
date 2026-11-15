"""1.12.17: runs tests/catalog_race_check.py (each case in its own process with a temp REFLIB_DATA_DIR)."""
import os, subprocess, sys


def test_catalog_races():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog_race_check.py")
    r = subprocess.run([sys.executable, f], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0 and "catalog_race_check: OK" in r.stdout, r.stdout + r.stderr
