# TradeSight AI — Phase 2: Chart Drawing via Playwright

**Date:** 2026-06-02
**Status:** Approved for implementation planning
**Builds on:** `2026-06-02-tradesight-automation-design.md` (Section A architecture, Phase 1 settings)

## Summary

When Learning Mode is on, a "Draw levels" button lets TradeSight attach to the
user's Chrome (over CDP), read the chart's price axis, and draw the detected
support/resistance as a **labeled annotation overlay on top of the chart**,
narrating each step. Platform-adaptive (no per-platform selectors), drawing
only — no orders (Phase 3).

## Locked Decisions

| Area | Decision |
|------|----------|
| Draw method | Annotation overlay (inject transparent SVG over the chart), positioned by vision calibration of the price axis |
| Trigger | Manual "Draw levels" button in the panel |
| Narration | Panel "ACTIONS" log + labels on each drawn line |
| Browser | Attach to the user's existing Chrome over CDP (`cdp_url` from settings) |
| Scope | Drawing S/R only; `propose_order()` is a stub for Phase 3 |

## Why an overlay (not native drawing tools)

The chart is a `<canvas>` — there is no DOM node at "price 4486", and every
platform's native drawing toolbar differs. An injected SVG overlay is
platform-agnostic (works on any site with a visible price axis), robust (we
control it, not fighting native tools), and lets each line carry its reasoning
as a label. Trade-off: the lines are our annotations, not saved into the
platform's own drawings, and placement is ~a few pixels approximate — acceptable
for an educational tool.

## Module Structure

New package `tradesight/automation/`:

```
automation/
  __init__.py
  browser.py       BrowserSession   — Playwright CDP attach, page pick, screenshot, inject/clear overlay
  calibration.py   PriceAxis        — price<->pixel mapping from a vision read of the axis
  actuator.py      ChartActuator    — orchestrates draw_levels(); enforces the gate; narrates
  service.py       ActuationService — owns a dedicated thread; UI submits draw tasks here
```

## Components

### calibration.py — `PriceAxis`
Pure math + a vision read, kept separate so it is unit-testable.
- `PriceAxis(anchors, plot)` where `anchors` is a list of `(price, pixel_y)` and
  `plot` is the chart plot-area box `{left, right, top, bottom}`.
- `y_for(price) -> float`: linear interpolation/extrapolation from the two
  outermost anchors (`y = y0 + (price - p0) * (y1 - y0) / (p1 - p0)`).
- `is_valid()`: at least 2 anchors with distinct prices, monotonic price↔y.
- `ChartActuator` builds a `PriceAxis` from the vision calibration JSON.

Calibration vision call (its own focused prompt, distinct from the analysis
prompt): given the page screenshot, return JSON:
```json
{
  "price_axis_anchors": [{"price": 4600.0, "pixel_y": 210}, {"price": 4400.0, "pixel_y": 430}],
  "plot_area": {"left": 60, "right": 980, "top": 80, "bottom": 560}
}
```
On failure / `is_valid()` false → drawing aborts with a narrated message.

### browser.py — `BrowserSession`
Wraps Playwright sync API. All methods run on the actuation thread (objects are
thread-affine). Interface:
- `attach(cdp_url)`: `chromium.connect_over_cdp(cdp_url)`; pick the chart page
  (first page whose URL/title matches the platform hint, else the active page).
- `screenshot() -> bytes`: PNG of the page (for calibration).
- `viewport() -> {width, height}`.
- `inject_overlay(lines)`: `page.evaluate(js, lines)` injects/refreshes one
  absolutely-positioned `<svg id="tradesight-overlay">` (pointer-events:none,
  high z-index) with a horizontal `<line>` + `<text>` label per entry.
  Each line: `{y, color, label}`.
- `clear_overlay()`: remove the injected node.
- `close()`: dispose Playwright (does NOT close the user's Chrome — CDP attach).
- Raises `BrowserError` (own type) with a clear message on attach/page failures.

### actuator.py — `ChartActuator`
Orchestrates one draw. Constructed with `(settings, browser, vision_client,
config, narrate)` where `narrate: Callable[[str], None]`.
- `draw_levels(analysis)`:
  1. If not `settings.drawing_allowed()` → `narrate("Enable Learning Mode →
     Draw levels in Settings.")`; return.
  2. `narrate("Attaching to Chrome…")`; `browser.attach(settings.cdp_url)`.
  3. `narrate("Reading the price axis…")`; screenshot → calibration vision call
     → `PriceAxis`. If invalid → narrate + return.
  4. For each `support_levels` (green) and `resistance_levels` (red) within the
     axis range: compute `y = axis.y_for(price)`, build
     `{y, color, label: f"{price} {kind}"}`, `narrate(f"Drawing {kind} {price}")`.
  5. `browser.inject_overlay(lines)`; `narrate(f"Drew {n} levels. {summary}")`
     where summary echoes the analysis's top reasoning bullet.
- All exceptions caught → `narrate(f"Couldn't draw: {msg}")`; never raises to UI.
- `propose_order(analysis)`: stub raising `NotImplementedError` (Phase 3).

### service.py — `ActuationService`
- Owns a dedicated daemon thread with a `queue.Queue` of callables.
- `submit(fn)`: enqueue work to run on the actuation thread.
- `draw(analysis)`: `submit(lambda: actuator.draw_levels(analysis))`.
- `shutdown()`: stop the thread, `browser.close()`.
- Constructs `BrowserSession` lazily on first use (so importing/headless is safe).

## UI (overlay.py)
- A **"Draw levels"** button, shown/enabled only when
  `settings.drawing_allowed()` (re-evaluated when the panel renders / after
  Settings save). Clicking calls the injected `on_draw` callback.
- A scrolling **"ACTIONS"** section in the scrollable body, appended to from
  action-tagged `ui_queue` messages. Narration messages are wrapped so `_drain`
  can tell them apart from status strings (e.g. an `("action", text)` tuple).
- Keeps the existing analysis rendering unchanged.

## Wiring (main.py)
- Build `ActuationService(settings, config, vision_client, narrate=<push action
  to ui_queue>)`.
- Pass `on_draw=lambda: self._actuation.draw(self._last_analysis)` to `Overlay`.
- Track `self._last_analysis` (set when a result is produced) so the button
  draws the most recent levels.
- `ActuationService.shutdown()` in the app's `finally`.

## Data Flow
```
"Draw levels" click (Tk main)
  -> ActuationService.draw(analysis)         [enqueue]
  -> actuation thread: ChartActuator.draw_levels
       gate -> attach -> screenshot -> vision calibrate -> PriceAxis
       -> compute y per level -> browser.inject_overlay
       -> narrate(...) at each step
  -> ui_queue (action messages) -> overlay ACTIONS log + chart labels
```

## Error Handling (all narrated, never crash)
- `playwright` not importable → "Install playwright: pip install playwright".
- CDP connect fails → "Start Chrome with --remote-debugging-port=9222 and open
  your chart, then try again."
- No chart page found → "Open your trading chart in the attached Chrome."
- Calibration invalid → "Couldn't read the price axis — try a clearer/larger
  chart."
- Drawing disabled by gate → "Enable Learning Mode → Draw levels in Settings."

## Testing
- `calibration.PriceAxis` — unit tests: `y_for` linear interpolation +
  extrapolation; `is_valid` rejects <2 anchors / equal prices / non-monotonic.
- `ChartActuator.draw_levels` — unit tests with a **fake BrowserSession** and a
  **fake vision client**:
  - gate off → no browser calls, narrates the enable message.
  - happy path → calibration parsed, correct `y` per level, line specs have
    right colors/labels, `inject_overlay` called once, narration emitted.
  - calibration invalid → aborts with narration, no `inject_overlay`.
  - browser attach error → narrated, no crash.
- Real `BrowserSession` (Playwright + Chrome over CDP) → manual smoke, not in
  the unit suite.

## Dependencies / Prereqs
- Add `playwright` to `requirements.txt` (CDP attach needs only the Python
  package, not `playwright install`).
- User launches Chrome with `--remote-debugging-port=9222` (documented in
  README / Settings hint).

## Out of Scope (Phase 3)
- Demo order execution, approval flow, order narration.
- Persisting drawings into the platform's native tools.
