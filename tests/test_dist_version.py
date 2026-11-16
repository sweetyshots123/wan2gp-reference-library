"""The committed gallery/dist must be built from this version: the open-tab check (1.12.13) compares
__REFLIB_BUILD__ with the server version, so a stale dist shows a 'reload' bar that a reload cannot clear."""
import glob, json, os

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_dist_build_matches_plugin_version():
    version = json.load(open(os.path.join(ROOT, "plugin_info.json"), encoding="utf-8"))["version"]
    js = glob.glob(os.path.join(ROOT, "gallery", "dist", "assets", "index-*.js"))
    assert js, "gallery/dist not built"
    text = "".join(open(p, encoding="utf-8").read() for p in js)
    assert f'build:"{version}"' in text, f"gallery/dist was built for another version (expected build:\"{version}\"); run npm run build"
