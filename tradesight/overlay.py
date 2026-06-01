from __future__ import annotations

import queue
import tkinter as tk
from datetime import timezone
from typing import Callable, Optional

from .analyzer import Analysis

_SIGNAL_COLORS = {"BUY": "#1db954", "SELL": "#e0245e", "HOLD": "#888888"}
_BG = "#15171c"
_FG = "#e6e6e6"
_MUTED = "#7a7f8a"


class Overlay:
    def __init__(self, ui_queue: "queue.Queue",
                 on_refresh: Callable[[], None],
                 on_settings: Optional[Callable[[], None]] = None):
        self._queue = ui_queue
        self._on_refresh = on_refresh
        self._on_settings = on_settings or (lambda: None)
        self._expanded = False

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg=_BG)
        self._place_right_edge()

        self._tab = tk.Frame(self.root, bg=_BG)
        self._panel = tk.Frame(self.root, bg=_BG)
        self._build_tab()
        self._build_panel()
        self._show_tab()

        self.root.after(100, self._drain)

    # ---- geometry ---------------------------------------------------------
    def _place_right_edge(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"60x30+{sw - 64}+200")

    def _build_tab(self):
        btn = tk.Label(self._tab, text="TradeSight ▶", bg=_BG, fg=_FG,
                       font=("Segoe UI", 8), cursor="hand2", padx=4, pady=6)
        btn.pack(fill="both", expand=True)
        btn.bind("<Button-1>", lambda _e: self._expand())

    def _build_panel(self):
        self._labels = {}
        header = tk.Frame(self._panel, bg=_BG)
        header.pack(fill="x")
        tk.Label(header, text="TradeSight AI", bg=_BG, fg=_FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=6, pady=4)
        tk.Button(header, text="▼", command=self._collapse, bd=0, bg=_BG,
                  fg=_FG).pack(side="right", padx=2)

        def row(key, title):
            tk.Label(self._panel, text=title, bg=_BG, fg=_MUTED,
                     font=("Segoe UI", 7)).pack(anchor="w", padx=8)
            lbl = tk.Label(self._panel, text="—", bg=_BG, fg=_FG,
                           justify="left", wraplength=300,
                           font=("Segoe UI", 9), anchor="w")
            lbl.pack(anchor="w", fill="x", padx=8)
            self._labels[key] = lbl

        row("pair", "PAIR DETECTED")
        row("session", "SESSION")
        self._signal = tk.Label(self._panel, text="—", bg=_BG, fg=_FG,
                                font=("Segoe UI", 16, "bold"))
        self._signal.pack(anchor="w", padx=8, pady=(6, 0))
        row("confidence", "CONFIDENCE")
        row("reasoning", "REASONING")
        row("news", "NEWS IMPACT")
        row("updated", "LAST UPDATED")

        btns = tk.Frame(self._panel, bg=_BG)
        btns.pack(fill="x", pady=6)
        tk.Button(btns, text="Refresh Now", command=self._on_refresh, bd=0,
                  bg="#2a2f3a", fg=_FG).pack(side="left", padx=8)
        tk.Button(btns, text="Settings", command=self._on_settings, bd=0,
                  bg="#2a2f3a", fg=_FG).pack(side="left")

        self._status_label = tk.Label(self._panel, text="Starting…", bg=_BG,
                                       fg=_MUTED, font=("Segoe UI", 7))
        self._status_label.pack(anchor="w", padx=8)
        tk.Label(self._panel,
                 text="⚠ Not financial advice — AI can misread charts",
                 bg=_BG, fg=_MUTED, font=("Segoe UI", 7)).pack(pady=(2, 6))

    # ---- state transitions ------------------------------------------------
    def _show_tab(self):
        self._panel.pack_forget()
        self._tab.pack(fill="both", expand=True)

    def _expand(self):
        self._expanded = True
        self._tab.pack_forget()
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"320x480+{sw - 332}+120")
        self._panel.pack(fill="both", expand=True)

    def _collapse(self):
        self._expanded = False
        self._place_right_edge()
        self._show_tab()

    # ---- rendering --------------------------------------------------------
    def set_status(self, text: str):
        self._status_label.configure(text=text)

    def render(self, a: Analysis):
        if not a.chart_detected:
            self._signal.configure(text="—", fg=_FG)
            self._labels["pair"].configure(text="No chart detected on screen")
            self.set_status("Waiting for a chart…")
            return
        if a.error:
            self._labels["pair"].configure(
                text="Analysis unavailable — retrying")
            self.set_status(a.error)
            return
        self._labels["pair"].configure(
            text=f"{a.pair or '—'}  {a.timeframe or ''}")
        self._labels["session"].configure(text=a.session_context or "—")
        self._signal.configure(text=a.signal,
                               fg=_SIGNAL_COLORS.get(a.signal, _FG))
        self._labels["confidence"].configure(text=f"{a.confidence}%")
        bullets = "\n".join(f"• {r}" for r in (a.reasoning or [])) or "—"
        self._labels["reasoning"].configure(text=bullets)
        news = a.news_impact or ("news unavailable" if not a.news_available
                                 else "—")
        self._labels["news"].configure(text=news)
        stamp = a.updated_at.astimezone(timezone.utc).strftime("%H:%M:%S UTC")
        self._labels["updated"].configure(text=stamp)
        self.set_status("Updated")

    def _drain(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if isinstance(item, Analysis):
                    self.render(item)
                elif isinstance(item, str):
                    self.set_status(item)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def run(self):
        self.root.mainloop()
