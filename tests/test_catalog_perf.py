"""1.12.16: runs tests/catalog_perf_check.py in its own process (it sets REFLIB_DATA_DIR before importing reflib_core)."""
import os, subprocess, sys


def test_catalog_perf():
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog_perf_check.py")
    r = subprocess.run([sys.executable, f], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "catalog_perf_check: OK" in r.stdout, r.stdout + r.stderr
