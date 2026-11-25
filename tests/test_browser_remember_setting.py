"""Settings & backend tests for browser_remember_state (synthetic data only)."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
_MOD = None


def _get_plugin_mod():
    global _MOD
    if _MOD is not None:
        return _MOD
    # Pre-import numpy so patch.dict never unloads it across tests.
    import numpy  # noqa: F401
    tmp_init = tempfile.mkdtemp(prefix="reflib-keepstate-init-")
    os.environ["REFLIB_DATA_DIR"] = tmp_init

    pkg = ModuleType("reflib_pkg_test")
    pkg.__path__ = [str(ROOT)]
    pkg.__package__ = "reflib_pkg_test"
    sys.modules["reflib_pkg_test"] = pkg

    try:
        import gradio  # noqa: F401
    except ImportError:
        m_gr = ModuleType("gradio")
        m_gr.skip = lambda: SimpleNamespace(_skip=True)
        m_gr.update = lambda **kw: kw
        sys.modules["gradio"] = m_gr
    try:
        from shared.utils.plugins import WAN2GPPlugin  # noqa: F401
    except ImportError:
        m_shared = ModuleType("shared")
        m_utils = ModuleType("shared.utils")
        m_plugins = ModuleType("shared.utils.plugins")

        class _StubPlugin:
            def __init__(self, *a, **kw):
                pass

        m_plugins.WAN2GPPlugin = _StubPlugin
        m_shared.utils = m_utils
        m_utils.plugins = m_plugins
        sys.modules.update({"shared": m_shared, "shared.utils": m_utils, "shared.utils.plugins": m_plugins})

    spec = importlib.util.spec_from_file_location("reflib_pkg_test.plugin", ROOT / "plugin.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reflib_pkg_test.plugin"] = mod
    spec.loader.exec_module(mod)
    _MOD = mod
    return mod


def test_default_setting_and_i18n():
    mod = _get_plugin_mod()
    assert mod.DEFAULT_SETTINGS["browser_remember_state"] is True
    assert mod.TEXT["en"]["browser_remember_state"] == "Remember search and filters on reopen"
    assert mod.TEXT["es"]["browser_remember_state"] == "Recordar búsqueda y filtros al reabrir"
    assert "browser_remember_state_info" in mod.TEXT["en"]
    assert "browser_remember_state_info" in mod.TEXT["es"]


def test_save_from_ui_and_payload_roundtrip(tmp_path):
    mod = _get_plugin_mod()
    plug = mod.ReferenceLibraryPlugin()
    plug.tab_updates = lambda lang: ()
    plug._ordered_bar_updates = lambda lang: ()
    plug._prompt_ui_updates = lambda lang: ()

    with patch.object(mod, "SETTINGS_PATH", str(tmp_path / "settings.json")):
        assert mod.load_settings()["browser_remember_state"] is True
        assert plug._ilib_payload("es")["remember_state"] is True

        plug._save_from_ui(
            "replace", False, True, True, 3.5, "es", "offer",
            True, "auto", "auto", False, "", False, True, "date_desc", 5,
            browser_remember_state=False,
        )
        assert mod.load_settings()["browser_remember_state"] is False
        assert plug._ilib_payload("es")["remember_state"] is False

        plug._save_from_ui(
            "replace", False, True, True, 3.5, "es", "offer",
            True, "auto", "auto", False, "", False, True, "date_desc", 5,
            browser_remember_state=True,
        )
        assert mod.load_settings()["browser_remember_state"] is True
        assert plug._ilib_payload("es")["remember_state"] is True


def test_ui_pref_and_build_js(tmp_path):
    mod = _get_plugin_mod()
    plug = mod.ReferenceLibraryPlugin()
    with patch.object(mod, "SETTINGS_PATH", str(tmp_path / "settings.json")):
        out_raw = plug.ilib(json.dumps({"id": "1", "action": "ui_pref", "browser_remember_state": False}))
        out = json.loads(out_raw)
        assert out["ok"] is True
        assert out["browser_remember_state"] is False
        assert mod.load_settings()["browser_remember_state"] is False

        js = mod.build_js()
        assert "ReflibViewState" in js
        assert '"browser_remember_state": false' in js or '"browser_remember_state":false' in js.replace(" ", "")
