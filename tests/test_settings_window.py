import tkinter as tk

import pytest

from tradesight.settings import RuntimeSettings
from tradesight.settings_window import SettingsWindow


def _root_or_skip():
    try:
        root = tk.Tk()
        root.withdraw()
        return root
    except tk.TclError as exc:  # headless CI
        pytest.skip(f"no display available: {exc}")


def test_save_writes_settings_and_updates_object(tmp_path):
    root = _root_or_skip()
    try:
        settings = RuntimeSettings()
        path = tmp_path / "settings.json"
        w = SettingsWindow(root, settings, path=str(path))

        # User turns on learning mode, picks a platform, confirms demo, opts in.
        w._learning.set(True)
        w._sync_enabled_state()
        w._platform.set("MetaTrader Web")
        w._notes.delete("1.0", "end")
        w._notes.insert("1.0", "Open the Trade panel, then click Buy/Sell.")
        w._cdp.set("http://localhost:9333")
        w._demo.set(True)
        w._sync_enabled_state()
        w._propose.set(True)
        w._save()

        # In-memory object mutated.
        assert settings.learning_mode is True
        assert settings.platform == "MetaTrader Web"
        assert "Buy/Sell" in settings.platform_notes
        assert settings.cdp_url == "http://localhost:9333"
        assert settings.orders_allowed() is True

        # Persisted and reloadable.
        assert path.exists()
        assert RuntimeSettings.load(path) == settings
    finally:
        root.destroy()


def test_propose_orders_forced_off_without_demo_confirmation(tmp_path):
    root = _root_or_skip()
    try:
        settings = RuntimeSettings()
        path = tmp_path / "settings.json"
        w = SettingsWindow(root, settings, path=str(path))

        w._learning.set(True)
        w._propose.set(True)       # try to opt in...
        w._demo.set(False)         # ...without confirming demo
        w._sync_enabled_state()
        w._save()

        assert settings.propose_orders_enabled is False
        assert settings.orders_allowed() is False
    finally:
        root.destroy()
