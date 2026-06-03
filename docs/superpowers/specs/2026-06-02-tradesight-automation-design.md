# TradeSight AI — Automation / Learning Mode Design

**Date:** 2026-06-02
**Status:** Phase 1 approved for implementation

## Summary

Add an opt-in "Learning Mode" that lets TradeSight act on the user's trading
platform via Playwright: draw the support/resistance it detected, and (with
explicit per-trade approval) place **demo / paper-trading** orders — narrating
its reasoning as it acts. Built in three staged, independently-shippable phases.
This spec covers the overall architecture (Section A) and **Phase 1** (Settings
+ Learning Mode toggle; no Playwright yet).

## Section A — Architecture

A new automation layer, separate from the existing analysis pipeline (capture →
analyzer → overlay stays unchanged). Automation plugs in alongside.

```
settings.py        RuntimeSettings   -> settings.json (UI toggles, persisted)
automation/
  actuator.py      Actuator (interface): draw_levels(), propose_order(), ...
  playwright_actuator.py  Playwright over CDP (Phase 2/3), platform-adaptive
  approval.py      AI proposes -> user approves/rejects -> act + narrate
```

**Platform-adaptive (key requirement).** The actuator is NOT hardcoded to one
broker. The user picks their `platform` and can add free-text `platform_notes`
describing how their site works. Phase 2/3 feed that context to the model so it
adapts its selectors/actions to whatever platform the user runs (TradingView
Paper Trading, an MT4/MT5 web terminal, a broker demo, etc.). Default target is
TradingView Paper Trading; attach is via the user's existing Chrome over CDP.

**Two config sources, separated by purpose:**
- `.env` (`Config`) — secrets & models (NIM/Gemini/Tavily keys, model IDs).
- `settings.json` (`RuntimeSettings`) — behavior toggles the Settings window
  edits at runtime.

**Hard safety invariants (all phases):**
1. Automation only runs when `learning_mode` is ON.
2. Order placement is impossible unless `demo_confirmed` is checked.
3. Every order is approval-gated — the AI proposes, narrates, and waits for an
   explicit click. Nothing auto-fires.
4. Drawing S/R (Phase 2) is allowed in learning mode without the demo gate (it
   places no orders).

**Phases:** 1) Settings + Learning Mode (this spec).  2) Playwright actuator +
chart drawing (educational, no orders).  3) Demo order execution, approval-gated.

## Phase 1 — Settings + Learning Mode (no Playwright)

### tradesight/settings.py — `RuntimeSettings`

A dataclass persisted to `settings.json` (project root, gitignored). Fields +
defaults:

| Field | Default | Purpose |
|-------|---------|---------|
| `learning_mode` | `False` | master switch for all automation |
| `platform` | `"TradingView"` | which trading platform to act on |
| `platform_notes` | `""` | free-text user guidance so the model adapts |
| `cdp_url` | `"http://localhost:9222"` | Chrome remote-debugging endpoint (Phase 2) |
| `draw_levels_enabled` | `True` | allow drawing S/R on the chart |
| `propose_orders_enabled` | `False` | allow proposing demo orders |
| `demo_confirmed` | `False` | user attests this is a demo/paper account |

- `load(path)` → returns defaults if the file is missing or corrupt (logs a
  warning, never raises). Unknown keys in the file are ignored; missing keys
  fall back to defaults.
- `save(path)` → writes JSON (pretty-printed).
- Safety helpers (single source of truth, unit-tested):
  - `automation_active()` → `learning_mode`
  - `drawing_allowed()` → `learning_mode and draw_levels_enabled`
  - `orders_allowed()` → `learning_mode and propose_orders_enabled and demo_confirmed`

### tradesight/settings_window.py — `SettingsWindow`

A Tkinter `Toplevel` opened from the Settings button (main thread — safe).
Contents:
- ☑ **Learning Mode** (master). When off, the rest is disabled/greyed.
- **Platform**: an editable combobox (presets: TradingView, MetaTrader Web,
  Other) bound to `platform`.
- **Platform notes**: a small multi-line text box bound to `platform_notes`
  ("Describe your platform / how to place an order so the AI can adapt").
- ☑ Draw support/resistance on chart (`draw_levels_enabled`).
- **CDP URL** entry (default `http://localhost:9222`) with a hint: "Launch
  Chrome with `--remote-debugging-port=9222`" (used in Phase 2).
- A red-bordered **demo gate**: ☑ "I confirm I am using a DEMO / paper-trading
  account" (`demo_confirmed`). The ☑ "Let the AI propose demo orders"
  (`propose_orders_enabled`) option is **force-disabled until `demo_confirmed`
  is checked**.
- **Save** (writes `settings.json`, updates the in-memory settings object) /
  **Cancel** (closes without saving).

The window mutates the passed-in `RuntimeSettings` instance in place on Save, so
the rest of the app sees changes immediately.

### Wiring (main.py)

Load `RuntimeSettings` at startup (`settings.json` in project root). `Overlay`'s
existing `on_settings` callback → `self._open_settings()` which opens
`SettingsWindow(self._overlay.root, self._settings)`. The Settings button is
already wired to `on_settings`, so this is a small change.

### What Phase 1 delivers

A working, persisted Settings window with all toggles, the platform fields, and
the demo safety gate. Nothing consumes `learning_mode` yet — Phases 2/3 do. It's
usable and testable standalone.

### Testing

- `settings.py` — real unit tests: defaults when no file; corrupt file →
  defaults; save→load round-trip; the three safety-helper truth tables
  (including the demo gate for `orders_allowed`).
- `SettingsWindow` — non-blocking smoke test: build the Toplevel, flip the vars,
  call Save, assert `settings.json` written with the new values (same pattern
  used for the overlay).

### Error handling

- Corrupt/unreadable `settings.json` → defaults + logged warning, never crash.
- Save failure (e.g. permissions) → message shown in the window, never crash.

## Out of scope for Phase 1 (later phases)

- Any Playwright / browser control (Phase 2).
- Drawing S/R on the chart (Phase 2).
- Demo order execution + approval/narration flow (Phase 3).
- Platform-specific selector logic (Phase 2/3, driven by `platform` +
  `platform_notes`).
