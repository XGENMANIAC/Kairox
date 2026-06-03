from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .settings import RuntimeSettings, DEFAULT_SETTINGS_PATH

log = logging.getLogger("tradesight")

_BG = "#15171c"
_FG = "#e6e6e6"
_MUTED = "#7a7f8a"
_ACCENT = "#1db954"
_DANGER = "#e0245e"
_PLATFORMS = ["TradingView", "MetaTrader Web", "Other"]


class SettingsWindow:
    """Modal-ish Toplevel that edits a RuntimeSettings instance in place.

    Runs on the Tk main thread (opened from the Settings button callback).
    On Save it mutates the passed-in settings object and persists settings.json.
    """

    def __init__(self, parent: tk.Misc, settings: RuntimeSettings,
                 path: str = DEFAULT_SETTINGS_PATH):
        self._settings = settings
        self._path = path

        self.win = tk.Toplevel(parent)
        self.win.title("TradeSight — Settings")
        self.win.configure(bg=_BG)
        self.win.attributes("-topmost", True)
        self.win.geometry("360x520")

        # Tk variables mirror the settings fields.
        self._learning = tk.BooleanVar(value=settings.learning_mode)
        self._platform = tk.StringVar(value=settings.platform)
        self._notes_initial = settings.platform_notes
        self._cdp = tk.StringVar(value=settings.cdp_url)
        self._draw = tk.BooleanVar(value=settings.draw_levels_enabled)
        self._propose = tk.BooleanVar(value=settings.propose_orders_enabled)
        self._demo = tk.BooleanVar(value=settings.demo_confirmed)

        self._build()
        self._sync_enabled_state()

    # ---- layout -----------------------------------------------------------
    def _label(self, parent, text, **kw):
        kw.setdefault("fg", _FG)
        return tk.Label(parent, text=text, bg=_BG, anchor="w",
                        justify="left", **kw)

    def _build(self):
        pad = dict(padx=12, anchor="w")

        tk.Label(self.win, text="Learning Mode", bg=_BG, fg=_FG,
                 font=("Segoe UI", 12, "bold")).pack(pady=(12, 2), **pad)
        self._label(self.win,
                    "Let TradeSight act on your platform (draw levels, and "
                    "later place demo orders). Everything below is off unless "
                    "this is on.", fg=_MUTED, wraplength=330,
                    font=("Segoe UI", 8)).pack(**pad)

        self._master_chk = tk.Checkbutton(
            self.win, text="Enable Learning Mode", variable=self._learning,
            command=self._sync_enabled_state, bg=_BG, fg=_FG,
            selectcolor=_BG, activebackground=_BG, activeforeground=_ACCENT,
            font=("Segoe UI", 10, "bold"))
        self._master_chk.pack(pady=(4, 8), **pad)

        # Container for everything gated behind learning mode.
        self._gated = []

        # Platform
        self._label(self.win, "PLATFORM", fg=_MUTED,
                    font=("Segoe UI", 7)).pack(**pad)
        plat = ttk.Combobox(self.win, values=_PLATFORMS,
                            textvariable=self._platform, state="normal")
        plat.pack(fill="x", padx=12)
        self._gated.append(plat)

        self._label(self.win, "PLATFORM NOTES (how to act on your platform)",
                    fg=_MUTED, font=("Segoe UI", 7)).pack(pady=(8, 0), **pad)
        self._notes = tk.Text(self.win, height=3, width=40, bg="#1e2128",
                              fg=_FG, insertbackground=_FG, wrap="word",
                              font=("Segoe UI", 8))
        self._notes.insert("1.0", self._notes_initial)
        self._notes.pack(fill="x", padx=12)
        self._gated.append(self._notes)

        # Drawing
        draw = tk.Checkbutton(
            self.win, text="Draw support/resistance on the chart",
            variable=self._draw, bg=_BG, fg=_FG, selectcolor=_BG,
            activebackground=_BG, activeforeground=_ACCENT,
            font=("Segoe UI", 9))
        draw.pack(pady=(8, 2), **pad)
        self._gated.append(draw)

        # CDP URL
        self._label(self.win, "CHROME CDP URL", fg=_MUTED,
                    font=("Segoe UI", 7)).pack(pady=(6, 0), **pad)
        cdp = tk.Entry(self.win, textvariable=self._cdp, bg="#1e2128", fg=_FG,
                       insertbackground=_FG)
        cdp.pack(fill="x", padx=12)
        self._gated.append(cdp)
        self._label(self.win, "Launch Chrome with --remote-debugging-port=9222",
                    fg=_MUTED, font=("Segoe UI", 7)).pack(**pad)

        # Demo gate (red bordered)
        gate = tk.Frame(self.win, bg=_BG, highlightbackground=_DANGER,
                        highlightthickness=1)
        gate.pack(fill="x", padx=12, pady=(10, 6))
        self._demo_chk = tk.Checkbutton(
            gate, text="I confirm I am using a DEMO / paper-trading account",
            variable=self._demo, command=self._sync_enabled_state, bg=_BG,
            fg=_DANGER, selectcolor=_BG, activebackground=_BG,
            wraplength=300, justify="left", font=("Segoe UI", 8, "bold"))
        self._demo_chk.pack(anchor="w", padx=6, pady=4)
        self._gated.append(self._demo_chk)

        self._propose_chk = tk.Checkbutton(
            gate, text="Let the AI propose demo orders (you approve each one)",
            variable=self._propose, bg=_BG, fg=_FG, selectcolor=_BG,
            activebackground=_BG, wraplength=300, justify="left",
            font=("Segoe UI", 8))
        self._propose_chk.pack(anchor="w", padx=6, pady=(0, 4))

        # Buttons
        btns = tk.Frame(self.win, bg=_BG)
        btns.pack(side="bottom", fill="x", pady=10)
        tk.Button(btns, text="Save", command=self._save, bd=2, relief="raised",
                  bg=_ACCENT, fg="#0b0c0f", font=("Segoe UI", 9, "bold"),
                  cursor="hand2").pack(side="right", padx=12)
        tk.Button(btns, text="Cancel", command=self.win.destroy, bd=2,
                  relief="raised", bg="#2a2f3a", fg=_FG,
                  cursor="hand2").pack(side="right")

        self._status = self._label(self.win, "", fg=_DANGER,
                                    font=("Segoe UI", 8))
        self._status.pack(side="bottom", **pad)

    # ---- behavior ---------------------------------------------------------
    def _sync_enabled_state(self):
        """Grey out gated controls when learning mode is off; the 'propose
        orders' option stays disabled until the demo box is checked."""
        on = self._learning.get()
        state = "normal" if on else "disabled"
        for w in self._gated:
            try:
                w.configure(state=state)
            except tk.TclError:
                pass
        # propose-orders needs BOTH learning mode and the demo confirmation.
        if on and self._demo.get():
            self._propose_chk.configure(state="normal")
        else:
            self._propose_chk.configure(state="disabled")
            if not (on and self._demo.get()):
                self._propose.set(False)

    def _save(self):
        s = self._settings
        s.learning_mode = self._learning.get()
        s.platform = self._platform.get().strip() or "TradingView"
        s.platform_notes = self._notes.get("1.0", "end").strip()
        s.cdp_url = self._cdp.get().strip() or "http://localhost:9222"
        s.draw_levels_enabled = self._draw.get()
        s.demo_confirmed = self._demo.get()
        # Enforce the gate even if the UI was bypassed somehow.
        s.propose_orders_enabled = bool(
            self._propose.get() and s.learning_mode and s.demo_confirmed)
        try:
            s.save(self._path)
        except Exception as exc:  # noqa: BLE001 — show, never crash
            log.warning("settings save failed: %s", exc)
            self._status.configure(text=f"Could not save: {exc}")
            return
        self.win.destroy()
