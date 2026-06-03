from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Union

log = logging.getLogger("tradesight")

DEFAULT_SETTINGS_PATH = "settings.json"


@dataclass
class RuntimeSettings:
    """User-tunable runtime toggles for the automation / learning-mode layer.

    Persisted to settings.json (separate from .env, which holds secrets/models).
    All automation is gated through the three helpers below — they are the
    single source of truth, so later phases never re-derive these conditions.
    """

    learning_mode: bool = False
    platform: str = "TradingView"
    platform_notes: str = ""
    cdp_url: str = "http://localhost:9222"
    draw_levels_enabled: bool = True
    propose_orders_enabled: bool = False
    demo_confirmed: bool = False

    @classmethod
    def load(cls, path: Union[str, Path] = DEFAULT_SETTINGS_PATH
             ) -> "RuntimeSettings":
        """Load settings, falling back to defaults if the file is missing or
        unreadable. Never raises — a bad file must not stop the app."""
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in known})
        except Exception as exc:  # noqa: BLE001 — corrupt file -> defaults
            log.warning("settings load failed (%s); using defaults", exc)
            return cls()

    def save(self, path: Union[str, Path] = DEFAULT_SETTINGS_PATH) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2),
                              encoding="utf-8")

    # ---- safety gates (single source of truth) ---------------------------
    def automation_active(self) -> bool:
        return self.learning_mode

    def drawing_allowed(self) -> bool:
        return self.learning_mode and self.draw_levels_enabled

    def orders_allowed(self) -> bool:
        return (self.learning_mode and self.propose_orders_enabled
                and self.demo_confirmed)
