from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime, timezone

from openai import OpenAI

from .analyzer import ChartAnalyzer
from .capture import CaptureService
from .config import Config, ConfigError
from .context import SessionContext
from .news import NewsService

logging.basicConfig(
    filename="tradesight.log", level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tradesight")


class TradeSightApp:
    def __init__(self, config: Config):
        self._cfg = config
        self._client = OpenAI(base_url=config.base_url, api_key=config.nim_api_key)
        self._capture = CaptureService(region=config.capture_region,
                                       diff_threshold=config.pixel_diff_threshold)
        self._analyzer = ChartAnalyzer(self._client, config)
        self._news = NewsService(self._client, config)
        self._ui_queue: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._refresh_now = threading.Event()
        self._last_pair: str | None = None

        # Imported here so headless test environments can import this module.
        from .overlay import Overlay
        self._overlay = Overlay(self._ui_queue, on_refresh=self._request_refresh)

    def _request_refresh(self):
        self._refresh_now.set()

    def _one_cycle(self):
        img = self._capture.grab()
        if not self._capture.has_changed(img) and not self._refresh_now.is_set():
            return  # screen unchanged; skip API spend
        self._refresh_now.clear()

        session = SessionContext.describe(datetime.now(timezone.utc))
        news_text = None
        if self._last_pair:
            news_text, _ = self._news.sentiment(self._last_pair)

        b64 = self._capture.to_base64_png(img)
        result = self._analyzer.analyze(b64, session, news_text)
        if result.pair:
            self._last_pair = result.pair
        result.session_context = result.session_context or session.session
        self._ui_queue.put(result)

    def _worker(self):
        # Force the first cycle even if the screen looks static at startup.
        self._refresh_now.set()
        while not self._stop.is_set():
            try:
                self._one_cycle()
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                log.exception("cycle failed: %s", exc)
                self._ui_queue.put("Analysis unavailable — retrying")
            self._stop.wait(self._cfg.capture_interval)

    def run(self):
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        try:
            self._overlay.run()  # blocks on Tk mainloop
        finally:
            self._stop.set()


def main():
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"[TradeSight] {exc}")
        return
    TradeSightApp(config).run()


if __name__ == "__main__":
    main()
