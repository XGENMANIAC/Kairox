from tradesight.settings import RuntimeSettings


def test_defaults_when_file_missing(tmp_path):
    s = RuntimeSettings.load(tmp_path / "nope.json")
    assert s.learning_mode is False
    assert s.platform == "TradingView"
    assert s.platform_notes == ""
    assert s.cdp_url == "http://localhost:9222"
    assert s.draw_levels_enabled is True
    assert s.propose_orders_enabled is False
    assert s.demo_confirmed is False


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = RuntimeSettings(learning_mode=True, platform="MetaTrader Web",
                        platform_notes="Click the Trade tab, then Buy/Sell",
                        propose_orders_enabled=True, demo_confirmed=True)
    s.save(p)
    assert p.exists()
    assert RuntimeSettings.load(p) == s


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{ not valid json", encoding="utf-8")
    assert RuntimeSettings.load(p) == RuntimeSettings()


def test_unknown_keys_are_ignored(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"learning_mode": true, "obsolete_field": 42}',
                 encoding="utf-8")
    s = RuntimeSettings.load(p)
    assert s.learning_mode is True
    assert s == RuntimeSettings(learning_mode=True)


def test_automation_active():
    assert RuntimeSettings(learning_mode=True).automation_active() is True
    assert RuntimeSettings(learning_mode=False).automation_active() is False


def test_drawing_allowed_truth_table():
    assert RuntimeSettings(learning_mode=True,
                           draw_levels_enabled=True).drawing_allowed() is True
    assert RuntimeSettings(learning_mode=False,
                           draw_levels_enabled=True).drawing_allowed() is False
    assert RuntimeSettings(learning_mode=True,
                           draw_levels_enabled=False).drawing_allowed() is False


def test_orders_allowed_requires_all_three_gates():
    on = dict(learning_mode=True, propose_orders_enabled=True,
              demo_confirmed=True)
    assert RuntimeSettings(**on).orders_allowed() is True
    assert RuntimeSettings(**{**on, "demo_confirmed": False}).orders_allowed() \
        is False
    assert RuntimeSettings(**{**on,
                             "propose_orders_enabled": False}).orders_allowed() \
        is False
    assert RuntimeSettings(**{**on, "learning_mode": False}).orders_allowed() \
        is False
