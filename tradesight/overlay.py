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
_ACCENT = "#1db954"


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
        # Start expanded so the overlay is unmistakable on first launch;
        # the user can collapse to the tab afterwards.
        self._expand()
        self._raise_above()

        self.root.after(100, self._drain)

    # ---- geometry ---------------------------------------------------------
    def _raise_above(self):
        """Force the borderless window to the front (topmost can be flaky)."""
        self.root.lift()
        self.root.attributes("-topmost", True)

    def _place_right_edge(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        # Wide enough for the label to fit at any DPI scaling.
        self.root.geometry(f"150x40+{sw - 162}+200")

    def _build_tab(self):
        btn = tk.Label(self._tab, text="TradeSight ▶", bg=_ACCENT,
                       fg="#0b0c0f", font=("Segoe UI", 11, "bold"),
                       cursor="hand2", padx=8, pady=8)
        btn.pack(fill="both", expand=True)
        btn.bind("<Button-1>", lambda _e: self._expand())
        self._tab.configure(highlightbackground=_ACCENT, highlightthickness=2)

    def _build_panel(self):
        self._labels = {}

        # --- fixed header (always visible at top) ---
        header = tk.Frame(self._panel, bg=_BG)
        header.pack(fill="x", side="top")
        tk.Label(header, text="TradeSight AI", bg=_BG, fg=_FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=6, pady=4)
        collapse = tk.Button(header, text="▼", bd=0, bg=_BG, fg=_FG,
                             activebackground=_ACCENT, cursor="hand2")
        collapse.configure(command=lambda: self._click(collapse, self._collapse))
        collapse.pack(side="right", padx=2)

        # --- fixed footer (buttons + status + disclaimer, always visible) ---
        footer = tk.Frame(self._panel, bg=_BG)
        footer.pack(fill="x", side="bottom")
        btns = tk.Frame(footer, bg=_BG)
        btns.pack(fill="x", pady=6)
        self._refresh_btn = tk.Button(btns, text="Refresh Now", bd=2,
                                      relief="raised", bg="#2a2f3a", fg=_FG,
                                      activebackground=_ACCENT, cursor="hand2")
        self._refresh_btn.configure(
            command=lambda: self._click(self._refresh_btn, self._on_refresh))
        self._refresh_btn.pack(side="left", padx=8)
        self._settings_btn = tk.Button(btns, text="Settings", bd=2,
                                       relief="raised", bg="#2a2f3a", fg=_FG,
                                       activebackground=_ACCENT, cursor="hand2")
        self._settings_btn.configure(
            command=lambda: self._click(self._settings_btn, self._on_settings))
        self._settings_btn.pack(side="left")
        self._status_label = tk.Label(footer, text="Starting…", bg=_BG,
                                       fg=_MUTED, font=("Segoe UI", 7))
        self._status_label.pack(anchor="w", padx=8)
        tk.Label(footer, text="⚠ Not financial advice — AI can misread charts",
                 bg=_BG, fg=_MUTED, font=("Segoe UI", 7)).pack(pady=(2, 6))

        # --- scrollable body between header and footer ---
        body = tk.Frame(self._panel, bg=_BG)
        body.pack(fill="both", expand=True, side="top")
        canvas = tk.Canvas(body, bg=_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=_BG)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(win, width=e.width))
        # Mouse-wheel scrolling while the pointer is over the panel.
        canvas.bind("<Enter>", lambda _e: canvas.bind_all(
            "<MouseWheel>",
            lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units")))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        def row(key, title):
            tk.Label(inner, text=title, bg=_BG, fg=_MUTED,
                     font=("Segoe UI", 7)).pack(anchor="w", padx=8)
            lbl = tk.Label(inner, text="—", bg=_BG, fg=_FG, justify="left",
                           wraplength=288, font=("Segoe UI", 9), anchor="w")
            lbl.pack(anchor="w", fill="x", padx=8)
            self._labels[key] = lbl

        row("pair", "PAIR DETECTED")
        row("session", "SESSION")
        self._event_label = tk.Label(inner, text="", bg=_BG,
                                     fg=_SIGNAL_COLORS["SELL"], justify="left",
                                     wraplength=288, font=("Segoe UI", 8, "bold"),
                                     anchor="w")
        self._event_label.pack(anchor="w", fill="x", padx=8)
        self._signal = tk.Label(inner, text="—", bg=_BG, fg=_FG,
                                font=("Segoe UI", 16, "bold"))
        self._signal.pack(anchor="w", padx=8, pady=(6, 0))
        row("confidence", "CONFIDENCE")
        row("plan", "TRADE PLAN")
        row("reasoning", "REASONING")
        row("watch", "WHAT TO WATCH")
        row("invalidation", "INVALIDATION")
        row("hold", "WHY HOLD")
        row("news", "NEWS IMPACT")
        row("updated", "LAST UPDATED")

    def _click(self, btn: tk.Button, action: Callable[[], None]):
        """Give a visible press (sunken→raised flash) then run the action."""
        try:
            btn.configure(relief="sunken")
            btn.after(120, lambda: btn.configure(relief="raised"))
        except tk.TclError:
            pass
        action()

    def _clear_rows(self):
        for key in ("session", "confidence", "plan", "reasoning", "watch",
                    "invalidation", "hold", "news", "updated"):
            self._labels[key].configure(text="—")
        self._signal.configure(text="—", fg=_FG)
        self._event_label.configure(text="")

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
        self._raise_above()

    def _collapse(self):
        self._expanded = False
        self._place_right_edge()
        self._show_tab()
        self._raise_above()

    # ---- rendering --------------------------------------------------------
    def set_status(self, text: str):
        self._status_label.configure(text=text)

    def render(self, a: Analysis):
        if not a.chart_detected:
            self._clear_rows()
            self._labels["pair"].configure(text="No chart detected on screen")
            self.set_status("Waiting for a chart…")
            return
        if a.error:
            self._clear_rows()
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
        if a.signal in ("BUY", "SELL") and a.entry_zone:
            rr = f"   R:R {a.risk_reward}" if a.risk_reward else ""
            plan = (f"Entry {a.entry_zone}\n"
                    f"Stop {a.stop_loss or '—'}    Target {a.take_profit or '—'}"
                    f"{rr}")
        else:
            plan = "—"
        self._labels["plan"].configure(text=plan)
        bullets = "\n".join(f"• {r}" for r in (a.reasoning or [])) or "—"
        self._labels["reasoning"].configure(text=bullets)
        self._labels["watch"].configure(text=a.what_to_watch or "—")
        self._labels["invalidation"].configure(
            text=a.invalidation_condition or "—")
        self._labels["hold"].configure(text=a.hold_reason or "—")
        news = a.news_impact or ("news unavailable" if not a.news_available
                                 else "—")
        if a.news_sentiment:
            news = f"[{a.news_sentiment}] {news}"
        self._labels["news"].configure(text=news)
        self._event_label.configure(
            text=("⚠ High-impact news imminent — caution advised"
                  if a.event_risk_imminent else ""))
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
