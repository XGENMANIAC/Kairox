# TradeSight Phase 2 — Chart Drawing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Learning Mode is on, a "Draw levels" button attaches to the user's Chrome over CDP, reads the chart's price axis via a vision call, and draws the detected support/resistance as a labeled SVG overlay, narrating each step into a panel ACTIONS log.

**Architecture:** New `tradesight/automation/` package. Pure calibration math (`PriceAxis`) + an orchestrator (`ChartActuator`) are unit-tested with fakes; the Playwright wrapper (`BrowserSession`) is manual-smoke. An `ActuationService` runs all browser work on one dedicated thread (Playwright objects are thread-affine); narration flows back through the existing `ui_queue`.

**Tech Stack:** Python 3.13, Playwright (sync, CDP attach), the existing OpenAI-compatible vision client (Gemini), Tkinter, pytest.

---

## File Structure

```
tradesight/automation/
  __init__.py
  calibration.py   PriceAxis — price<->pixel map from vision calibration JSON
  actuator.py      ChartActuator — draw_levels(); gate + calibrate + build lines + narrate
  browser.py       BrowserSession — Playwright CDP attach, screenshot, inject/clear overlay
  service.py       ActuationService — dedicated thread; UI submits draw tasks
tests/
  test_calibration.py
  test_actuator.py
  test_browser.py        (pure page-pick helper only)
  test_actuation_service.py
```
Modified: `requirements.txt`, `tradesight/overlay.py`, `tradesight/main.py`.

Conventions: `python -m pytest`; every task ends with a commit using
`git -c user.name='TradeSight' -c user.email='nicodemusmuema76@gmail.com' commit`.

---

## Task 0: Dependency + package scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `tradesight/automation/__init__.py`

- [ ] **Step 1: Add playwright to `requirements.txt`**

Append this line:
```
playwright>=1.40
```

- [ ] **Step 2: Create empty `tradesight/automation/__init__.py`**

Empty file.

- [ ] **Step 3: Install playwright (Python package only — no browser download)**

Run: `python -m pip install playwright`
Expected: installs successfully. (CDP attach uses the user's Chrome, so
`playwright install` is NOT required.)

- [ ] **Step 4: Verify import + suite still green**

Run: `python -c "import playwright; print('ok')" && python -m pytest -q`
Expected: `ok` then all existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tradesight/automation/__init__.py
git commit -m "chore: add playwright + automation package scaffold"
```

---

## Task 1: calibration.py — PriceAxis

**Files:**
- Create: `tradesight/automation/calibration.py`
- Test: `tests/test_calibration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration.py
from tradesight.automation.calibration import PriceAxis


def test_y_for_interpolates_between_anchors():
    axis = PriceAxis(anchors=[(4600.0, 210.0), (4400.0, 430.0)], plot={})
    # halfway in price -> halfway in pixels
    assert axis.y_for(4500.0) == 320.0


def test_y_for_extrapolates_above_range():
    axis = PriceAxis(anchors=[(4600.0, 210.0), (4400.0, 430.0)], plot={})
    assert axis.y_for(4700.0) == 100.0


def test_y_for_uses_widest_price_separation_unsorted():
    # anchors out of order; endpoints by price are (4400) and (4600)
    axis = PriceAxis(anchors=[(4500.0, 320.0), (4600.0, 210.0),
                              (4400.0, 430.0)], plot={})
    assert axis.y_for(4500.0) == 320.0


def test_is_valid_requires_two_distinct_prices():
    assert PriceAxis([(4600.0, 210.0), (4400.0, 430.0)], {}).is_valid() is True
    assert PriceAxis([(4600.0, 210.0)], {}).is_valid() is False
    assert PriceAxis([(4600.0, 210.0), (4600.0, 400.0)], {}).is_valid() is False


def test_from_calibration_parses_json_shape():
    data = {
        "price_axis_anchors": [{"price": 4600, "pixel_y": 210},
                               {"price": 4400, "pixel_y": 430}],
        "plot_area": {"left": 60, "right": 980, "top": 80, "bottom": 560},
    }
    axis = PriceAxis.from_calibration(data)
    assert axis.is_valid() is True
    assert axis.plot["right"] == 980
    assert axis.y_for(4500.0) == 320.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: FAIL — `ModuleNotFoundError: tradesight.automation.calibration`

- [ ] **Step 3: Write `tradesight/automation/calibration.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class PriceAxis:
    """Linear map between chart price and vertical pixel position, derived from
    a vision read of the price axis."""

    anchors: List[Tuple[float, float]]  # (price, pixel_y)
    plot: dict = field(default_factory=dict)  # {left,right,top,bottom}

    def is_valid(self) -> bool:
        if len(self.anchors) < 2:
            return False
        prices = {round(p, 6) for p, _ in self.anchors}
        return len(prices) >= 2

    def _endpoints(self):
        ordered = sorted(self.anchors, key=lambda a: a[0])
        return ordered[0], ordered[-1]

    def y_for(self, price: float) -> float:
        (p0, y0), (p1, y1) = self._endpoints()
        return y0 + (price - p0) * (y1 - y0) / (p1 - p0)

    @classmethod
    def from_calibration(cls, data: dict) -> "PriceAxis":
        anchors = []
        for a in data.get("price_axis_anchors", []) or []:
            try:
                anchors.append((float(a["price"]), float(a["pixel_y"])))
            except (KeyError, TypeError, ValueError):
                continue
        plot = data.get("plot_area") or {}
        return cls(anchors=anchors, plot=plot)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibration.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/automation/calibration.py tests/test_calibration.py
git commit -m "feat: PriceAxis price<->pixel calibration"
```

---

## Task 2: actuator.py — ChartActuator

**Files:**
- Create: `tradesight/automation/actuator.py`
- Test: `tests/test_actuator.py`

`ChartActuator` depends on a `browser` object with `attach(cdp_url)`,
`screenshot() -> bytes`, `inject_overlay(lines)`, and a `vision_client` with the
OpenAI shape. Tests use fakes for both.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actuator.py
import json

from tradesight.automation.actuator import ChartActuator
from tradesight.config import Config
from tradesight.settings import RuntimeSettings


CALIB = json.dumps({
    "price_axis_anchors": [{"price": 4600, "pixel_y": 210},
                           {"price": 4400, "pixel_y": 430}],
    "plot_area": {"left": 60, "right": 980, "top": 80, "bottom": 560},
})


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeVision:
    def __init__(self, content):
        outer = self
        self.calls = 0

        class _C:
            def create(self, **kw):
                outer.calls += 1
                return _Resp(content)
        self.chat = type("Chat", (), {"completions": _C()})()


class FakeBrowser:
    def __init__(self):
        self.attached = None
        self.injected = None
        self.shots = 0

    def attach(self, cdp_url):
        self.attached = cdp_url

    def screenshot(self):
        self.shots += 1
        return b"\x89PNG\r\n\x1a\n"  # bytes are enough; vision is faked

    def inject_overlay(self, lines):
        self.injected = lines


class Analysis:  # minimal stand-in with the fields the actuator reads
    def __init__(self, support, resistance, reasoning=None):
        self.support_levels = support
        self.resistance_levels = resistance
        self.reasoning = reasoning or []


def cfg():
    return Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})


def make(settings, browser, vision):
    msgs = []
    actuator = ChartActuator(settings, browser, vision, cfg(), msgs.append)
    return actuator, msgs


def test_gate_blocks_when_drawing_not_allowed():
    browser = FakeBrowser()
    actuator, msgs = make(RuntimeSettings(learning_mode=False), browser,
                          FakeVision(CALIB))
    actuator.draw_levels(Analysis([4400], [4600]))
    assert browser.attached is None
    assert any("Learning Mode" in m for m in msgs)


def test_happy_path_draws_levels_with_correct_pixels():
    browser = FakeBrowser()
    settings = RuntimeSettings(learning_mode=True, draw_levels_enabled=True,
                               cdp_url="http://localhost:9222")
    actuator, msgs = make(settings, browser, FakeVision(CALIB))
    actuator.draw_levels(Analysis(support=[4400.0], resistance=[4600.0]))

    assert browser.attached == "http://localhost:9222"
    assert browser.shots == 1
    lines = browser.injected
    assert len(lines) == 2
    by_label = {ln["label"]: ln for ln in lines}
    assert by_label["4400.0 support"]["y"] == 430.0
    assert by_label["4400.0 support"]["color"] == "#1db954"
    assert by_label["4600.0 resistance"]["y"] == 210.0
    assert by_label["4600.0 resistance"]["color"] == "#e0245e"
    assert any("Drew 2" in m for m in msgs)


def test_invalid_calibration_aborts_without_injecting():
    browser = FakeBrowser()
    settings = RuntimeSettings(learning_mode=True, draw_levels_enabled=True)
    bad = json.dumps({"price_axis_anchors": [{"price": 4600, "pixel_y": 210}]})
    actuator, msgs = make(settings, browser, FakeVision(bad))
    actuator.draw_levels(Analysis([4400], [4600]))
    assert browser.injected is None
    assert any("price axis" in m.lower() for m in msgs)


def test_browser_error_is_narrated_not_raised():
    class Boom(FakeBrowser):
        def attach(self, cdp_url):
            raise RuntimeError("no chrome")
    settings = RuntimeSettings(learning_mode=True, draw_levels_enabled=True)
    actuator, msgs = make(settings, Boom(), FakeVision(CALIB))
    actuator.draw_levels(Analysis([4400], [4600]))  # must not raise
    assert any("couldn't draw" in m.lower() for m in msgs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_actuator.py -v`
Expected: FAIL — `ModuleNotFoundError: tradesight.automation.actuator`

- [ ] **Step 3: Write `tradesight/automation/actuator.py`**

```python
from __future__ import annotations

import base64
from typing import Any, Callable

from ..config import Config
from ..jsonutil import parse_json_object
from ..settings import RuntimeSettings
from .calibration import PriceAxis

SUPPORT_COLOR = "#1db954"
RESISTANCE_COLOR = "#e0245e"

CALIBRATION_PROMPT = """\
You are calibrating a trading chart's price axis from a screenshot.
Read the vertical price scale (usually on the right edge) and return ONLY JSON:
{
  "price_axis_anchors": [
    {"price": <number from a visible axis label>, "pixel_y": <its vertical pixel center, measured from the TOP of the image>},
    {"price": <another visible axis label>, "pixel_y": <its vertical pixel center>}
  ],
  "plot_area": {"left": <int>, "right": <int>, "top": <int>, "bottom": <int>}
}
Use at least two clearly-labeled price ticks with DIFFERENT prices and their
true pixel positions. No prose, JSON only.
"""


class ChartActuator:
    def __init__(self, settings: RuntimeSettings, browser: Any,
                 vision_client: Any, config: Config,
                 narrate: Callable[[str], None]):
        self._settings = settings
        self._browser = browser
        self._vision = vision_client
        self._cfg = config
        self._narrate = narrate

    def _calibrate(self, png: bytes) -> PriceAxis:
        b64 = base64.b64encode(png).decode("ascii")
        resp = self._vision.chat.completions.create(
            model=self._cfg.vision_model,
            messages=[
                {"role": "system", "content": CALIBRATION_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Calibrate this chart's price axis."},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]},
            ],
            temperature=0.0, max_tokens=512, timeout=60.0)
        data = parse_json_object(resp.choices[0].message.content)
        return PriceAxis.from_calibration(data)

    def draw_levels(self, analysis: Any) -> None:
        if not self._settings.drawing_allowed():
            self._narrate("Enable Learning Mode → Draw levels in Settings.")
            return
        try:
            self._narrate("Attaching to Chrome…")
            self._browser.attach(self._settings.cdp_url)

            self._narrate("Reading the price axis…")
            axis = self._calibrate(self._browser.screenshot())
            if not axis.is_valid():
                self._narrate("Couldn't read the price axis — try a clearer "
                              "or larger chart.")
                return

            lines = []
            for price in (analysis.support_levels or []):
                y = axis.y_for(float(price))
                lines.append({"y": y, "color": SUPPORT_COLOR,
                              "label": f"{price} support"})
                self._narrate(f"Drawing support {price}")
            for price in (analysis.resistance_levels or []):
                y = axis.y_for(float(price))
                lines.append({"y": y, "color": RESISTANCE_COLOR,
                              "label": f"{price} resistance"})
                self._narrate(f"Drawing resistance {price}")

            if not lines:
                self._narrate("No support/resistance levels to draw.")
                return

            self._browser.inject_overlay(lines)
            top_reason = (analysis.reasoning or [""])[0]
            self._narrate(f"Drew {len(lines)} levels. {top_reason}".strip())
        except Exception as exc:  # noqa: BLE001 — narrate, never crash the app
            self._narrate(f"Couldn't draw: {exc}")

    def propose_order(self, analysis: Any) -> None:
        raise NotImplementedError("order execution is Phase 3")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_actuator.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/automation/actuator.py tests/test_actuator.py
git commit -m "feat: ChartActuator draws calibrated S/R overlay with narration"
```

---

## Task 3: browser.py — BrowserSession (Playwright)

**Files:**
- Create: `tradesight/automation/browser.py`
- Test: `tests/test_browser.py` (pure page-pick helper only)

The Playwright calls are manual-smoke (need Chrome). Only the pure page-pick
helper is unit-tested.

- [ ] **Step 1: Write the failing test (pure helper)**

```python
# tests/test_browser.py
from tradesight.automation.browser import pick_page


class FakePage:
    def __init__(self, url, title="t"):
        self.url = url
        self._title = title

    def title(self):
        return self._title


def test_pick_page_prefers_platform_hint_match():
    pages = [FakePage("https://mail.google.com"),
             FakePage("https://www.tradingview.com/chart/abc")]
    chosen = pick_page(pages, "TradingView")
    assert chosen.url.endswith("/chart/abc")


def test_pick_page_falls_back_to_last_page_when_no_match():
    pages = [FakePage("https://a.com"), FakePage("https://b.com")]
    chosen = pick_page(pages, "TradingView")
    assert chosen.url == "https://b.com"


def test_pick_page_none_when_empty():
    assert pick_page([], "TradingView") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_browser.py -v`
Expected: FAIL — `ModuleNotFoundError: tradesight.automation.browser`

- [ ] **Step 3: Write `tradesight/automation/browser.py`**

```python
from __future__ import annotations

from typing import Any, List, Optional

_OVERLAY_JS = """
(lines) => {
  const id = 'tradesight-overlay';
  const existing = document.getElementById(id);
  if (existing) existing.remove();
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.id = id;
  Object.assign(svg.style, {position:'fixed', left:'0', top:'0',
    width:'100vw', height:'100vh', pointerEvents:'none', zIndex:2147483647});
  svg.setAttribute('width', window.innerWidth);
  svg.setAttribute('height', window.innerHeight);
  for (const ln of lines) {
    const line = document.createElementNS(NS, 'line');
    line.setAttribute('x1', 0); line.setAttribute('x2', window.innerWidth);
    line.setAttribute('y1', ln.y); line.setAttribute('y2', ln.y);
    line.setAttribute('stroke', ln.color);
    line.setAttribute('stroke-width', 1.5);
    line.setAttribute('stroke-dasharray', '6 4');
    svg.appendChild(line);
    const text = document.createElementNS(NS, 'text');
    text.setAttribute('x', 8); text.setAttribute('y', ln.y - 4);
    text.setAttribute('fill', ln.color); text.setAttribute('font-size', '12');
    text.setAttribute('font-family', 'Segoe UI, Arial, sans-serif');
    text.setAttribute('paint-order', 'stroke');
    text.setAttribute('stroke', 'rgba(0,0,0,0.6)');
    text.setAttribute('stroke-width', '3');
    text.textContent = ln.label;
    svg.appendChild(text);
  }
  document.body.appendChild(svg);
  return lines.length;
}
"""


class BrowserError(Exception):
    """Raised with a user-facing instruction when attach/page fails."""


def pick_page(pages: List[Any], platform_hint: str) -> Optional[Any]:
    """Choose the chart tab: first whose URL/title contains a token from the
    platform hint, else the last open page (most recently focused), else None."""
    if not pages:
        return None
    tokens = [t for t in platform_hint.lower().replace("/", " ").split() if t]
    for page in pages:
        hay = (getattr(page, "url", "") or "").lower()
        try:
            hay += " " + (page.title() or "").lower()
        except Exception:  # noqa: BLE001 — title() may fail on a closed page
            pass
        if any(tok in hay for tok in tokens):
            return page
    return pages[-1]


class BrowserSession:
    def __init__(self, platform_hint: str = ""):
        self._hint = platform_hint
        self._pw = None
        self._browser = None
        self._page = None

    def attach(self, cdp_url: str) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserError("Install playwright: pip install playwright") \
                from exc
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:  # noqa: BLE001
            self._cleanup()
            raise BrowserError(
                "Couldn't reach Chrome. Start it with "
                "--remote-debugging-port=9222 and open your chart, then retry."
            ) from exc
        pages = [p for ctx in self._browser.contexts for p in ctx.pages]
        page = pick_page(pages, self._hint)
        if page is None:
            self._cleanup()
            raise BrowserError("Open your trading chart in the attached Chrome.")
        self._page = page

    def screenshot(self) -> bytes:
        return self._page.screenshot()

    def inject_overlay(self, lines) -> None:
        self._page.evaluate(_OVERLAY_JS, lines)

    def clear_overlay(self) -> None:
        self._page.evaluate(
            "() => document.getElementById('tradesight-overlay')?.remove()")

    def close(self) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        # Do NOT close the user's Chrome — we only attached over CDP.
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self._pw = None
        self._browser = None
        self._page = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_browser.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/automation/browser.py tests/test_browser.py
git commit -m "feat: BrowserSession Playwright CDP attach + SVG overlay"
```

---

## Task 4: service.py — ActuationService

**Files:**
- Create: `tradesight/automation/service.py`
- Test: `tests/test_actuation_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actuation_service.py
import threading

from tradesight.automation.service import ActuationService
from tradesight.config import Config
from tradesight.settings import RuntimeSettings


def cfg():
    return Config.load(env={"NIM_API_KEY": "n", "TAVILY_API_KEY": "t"})


def test_submit_runs_callable_on_worker_thread():
    svc = ActuationService(RuntimeSettings(), cfg(), vision_client=None,
                           narrate=lambda _m: None)
    done = threading.Event()
    seen = {}

    def work():
        seen["thread"] = threading.current_thread().name
        done.set()

    svc.submit(work)
    assert done.wait(timeout=3)
    assert seen["thread"] != threading.current_thread().name
    svc.shutdown()


def test_draw_without_analysis_narrates_and_skips():
    msgs = []
    svc = ActuationService(RuntimeSettings(), cfg(), vision_client=None,
                           narrate=msgs.append)
    svc.draw(None)
    svc.shutdown()
    assert any("no analysis" in m.lower() for m in msgs)


def test_draw_submits_actuator_with_injected_browser():
    # Inject a fake browser factory + fake vision so no Playwright/Chrome needed.
    class FakeBrowser:
        def __init__(self):
            self.injected = None
        def attach(self, url):
            pass
        def screenshot(self):
            return b"png"
        def inject_overlay(self, lines):
            self.injected = lines

    import json

    class _Resp:
        def __init__(self, c):
            self.choices = [type("M", (), {"message": type("X", (), {"content": c})})]

    class FakeVision:
        def __init__(self, c):
            o = self
            class _C:
                def create(self, **kw):
                    return _Resp(c)
            self.chat = type("Chat", (), {"completions": _C()})()

    calib = json.dumps({"price_axis_anchors": [{"price": 4600, "pixel_y": 210},
                                               {"price": 4400, "pixel_y": 430}]})
    fake_browser = FakeBrowser()
    done = threading.Event()
    msgs = []

    def narrate(m):
        msgs.append(m)
        if m.startswith("Drew"):
            done.set()

    svc = ActuationService(
        RuntimeSettings(learning_mode=True, draw_levels_enabled=True),
        cfg(), vision_client=FakeVision(calib), narrate=narrate,
        browser_factory=lambda hint: fake_browser)

    class A:
        support_levels = [4400.0]
        resistance_levels = [4600.0]
        reasoning = ["bearish"]

    svc.draw(A())
    assert done.wait(timeout=5)
    assert fake_browser.injected is not None
    svc.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_actuation_service.py -v`
Expected: FAIL — `ModuleNotFoundError: tradesight.automation.service`

- [ ] **Step 3: Write `tradesight/automation/service.py`**

```python
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Optional

from ..config import Config
from ..settings import RuntimeSettings
from .actuator import ChartActuator
from .browser import BrowserSession

log = logging.getLogger("tradesight")


class ActuationService:
    """Owns a dedicated thread for all browser work (Playwright objects are
    thread-affine). The UI submits tasks; narration flows out via `narrate`."""

    def __init__(self, settings: RuntimeSettings, config: Config,
                 vision_client: Any, narrate: Callable[[str], None],
                 browser_factory: Callable[[str], Any] = BrowserSession):
        self._settings = settings
        self._cfg = config
        self._vision = vision_client
        self._narrate = narrate
        self._browser_factory = browser_factory
        self._browser: Optional[Any] = None
        self._q: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="actuation")
        self._thread.start()

    def _run(self):
        while True:
            fn = self._q.get()
            if fn is None:
                return
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — keep the thread alive
                log.exception("actuation task failed: %s", exc)
                self._narrate(f"Action failed: {exc}")

    def submit(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    def draw(self, analysis: Any) -> None:
        if analysis is None:
            self._narrate("No analysis yet — wait for a signal, then draw.")
            return
        self.submit(lambda: self._actuator().draw_levels(analysis))

    def _actuator(self) -> ChartActuator:
        if self._browser is None:
            self._browser = self._browser_factory(self._settings.platform)
        return ChartActuator(self._settings, self._browser, self._vision,
                             self._cfg, self._narrate)

    def shutdown(self) -> None:
        self._q.put(None)
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # noqa: BLE001
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_actuation_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tradesight/automation/service.py tests/test_actuation_service.py
git commit -m "feat: ActuationService dedicated browser thread"
```

---

## Task 5: overlay.py — Draw button + ACTIONS log

**Files:**
- Modify: `tradesight/overlay.py`

The overlay stays dumb about settings: the button is always present; the gate is
enforced (and narrated) by the actuator.

- [ ] **Step 1: Add an `on_draw` callback param**

In `Overlay.__init__`, change the signature and store it:
```python
    def __init__(self, ui_queue: "queue.Queue",
                 on_refresh: Callable[[], None],
                 on_settings: Optional[Callable[[], None]] = None,
                 on_draw: Optional[Callable[[], None]] = None):
        self._queue = ui_queue
        self._on_refresh = on_refresh
        self._on_settings = on_settings or (lambda: None)
        self._on_draw = on_draw or (lambda: None)
        self._expanded = False
```

- [ ] **Step 2: Add the "Draw levels" button to the footer button row**

Find the footer `btns` frame in `_build_panel` (where Refresh/Settings live) and
add after the Settings button:
```python
        self._draw_btn = tk.Button(btns, text="Draw levels", bd=2,
                                   relief="raised", bg="#2a2f3a", fg=_FG,
                                   activebackground=_ACCENT, cursor="hand2")
        self._draw_btn.configure(
            command=lambda: self._click(self._draw_btn, self._on_draw))
        self._draw_btn.pack(side="left", padx=8)
```

- [ ] **Step 3: Add an ACTIONS log to the scrollable body**

In `_build_panel`, after the `row("updated", "LAST UPDATED")` call (still inside
the scrollable `inner` frame), add:
```python
        tk.Label(inner, text="ACTIONS", bg=_BG, fg=_MUTED,
                 font=("Segoe UI", 7)).pack(anchor="w", padx=8, pady=(6, 0))
        self._actions = tk.Text(inner, height=6, width=40, bg="#0e1014",
                                fg=_MUTED, wrap="word", font=("Segoe UI", 8),
                                state="disabled", bd=0)
        self._actions.pack(fill="x", padx=8, pady=(0, 6))
```

- [ ] **Step 4: Add an `add_action` method and handle action messages in `_drain`**

Add this method (next to `set_status`):
```python
    def add_action(self, text: str):
        self._actions.configure(state="normal")
        self._actions.insert("end", text + "\n")
        self._actions.see("end")
        self._actions.configure(state="disabled")
```

In `_drain`, change the message handling to recognise `("action", text)` tuples:
```python
    def _drain(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if isinstance(item, Analysis):
                    self.render(item)
                elif isinstance(item, tuple) and item and item[0] == "action":
                    self.add_action(str(item[1]))
                elif isinstance(item, str):
                    self.set_status(item)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)
```

- [ ] **Step 5: Manual smoke test (non-blocking)**

Run:
```bash
python -c "import queue; from tradesight.overlay import Overlay; o=Overlay(queue.Queue(), lambda:None, on_draw=lambda: print('draw')); o._expand(); o.add_action('Attaching to Chrome…'); o.add_action('Drew 2 levels'); o.root.update(); o.root.update_idletasks(); print('actions ok'); o.root.destroy()"
```
Expected: prints `actions ok` with no error (the ACTIONS box accepted two lines).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass (overlay change doesn't break existing tests).

- [ ] **Step 7: Commit**

```bash
git add tradesight/overlay.py
git commit -m "feat: Draw levels button + ACTIONS narration log in overlay"
```

---

## Task 6: main.py — wire ActuationService

**Files:**
- Modify: `tradesight/main.py`

- [ ] **Step 1: Import ActuationService**

Add to the imports block:
```python
from .automation.service import ActuationService
```

- [ ] **Step 2: Build the service, track last analysis, pass on_draw**

In `__init__`, after `self._settings = RuntimeSettings.load()` and after
`vision_client` is determined, add (before the Overlay is created):
```python
        self._last_analysis = None
        self._actuation = ActuationService(
            self._settings, config, vision_client,
            narrate=lambda text: self._ui_queue.put(("action", text)))
```
Then change the Overlay construction to pass `on_draw`:
```python
        self._overlay = Overlay(self._ui_queue, on_refresh=self._request_refresh,
                                on_settings=self._open_settings,
                                on_draw=self._on_draw)
```
Add the handler method:
```python
    def _on_draw(self):
        self._actuation.draw(self._last_analysis)
```

- [ ] **Step 3: Record the latest analysis in the cycle**

In `_one_cycle`, after `result = self._analyzer.analyze(...)` and the
`session_context` line, before `self._ui_queue.put(result)`, add:
```python
        self._last_analysis = result
```

- [ ] **Step 4: Shut the service down on exit**

In `run()`, change the `finally` block:
```python
        try:
            self._overlay.run()  # blocks on Tk mainloop
        finally:
            self._stop.set()
            self._actuation.shutdown()
```

- [ ] **Step 5: Verify import + full suite**

Run: `python -c "import tradesight.main; print('ok')" && python -m pytest -q`
Expected: `ok` then all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tradesight/main.py
git commit -m "feat: wire ActuationService + Draw levels into the app"
```

---

## Manual end-to-end verification (after Task 6)

1. Close Chrome, then launch it in debug mode with your chart:
   `& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222`
   Open your TradingView XAU/USD chart in it.
2. In Settings: enable **Learning Mode**, keep **Draw support/resistance** on,
   CDP URL `http://localhost:9222`, Save.
3. Let an analysis complete (real pair + levels), then click **Draw levels**.
4. Expect: dashed green/red lines appear over the chart at the support/resistance
   prices, each labeled; the ACTIONS log narrates "Attaching… / Reading the
   price axis… / Drawing support … / Drew N levels."
5. With Learning Mode OFF, clicking Draw levels narrates the enable message and
   does nothing.

---

## Self-Review Notes

- **Spec coverage:** overlay annotation (Task 2/3), vision calibration + PriceAxis (Task 1/2), manual Draw button (Task 5), ACTIONS log + chart labels (Task 2/5), CDP attach + page pick + screenshot + inject/clear (Task 3), dedicated thread (Task 4), gate via `drawing_allowed` (Task 2), narrated error handling (Task 2/3), playwright dep (Task 0), wiring + last-analysis (Task 6). `propose_order` stub present (Task 2).
- **Type consistency:** browser interface `attach(cdp_url)/screenshot()->bytes/inject_overlay(lines)/close()` used identically in actuator, service, and BrowserSession; line dicts `{y,color,label}` consistent between actuator and `_OVERLAY_JS`; `narrate: Callable[[str],None]` everywhere; `("action", text)` queue protocol matches overlay `_drain`.
- **No live deps in unit tests:** calibration is pure; actuator/service use fake browser + fake vision; BrowserSession's only unit test is the pure `pick_page`. Real Playwright/Chrome is manual smoke.
