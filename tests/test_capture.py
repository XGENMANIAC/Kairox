import base64

from PIL import Image

from tradesight.capture import CaptureService


def solid(color):
    return Image.new("RGB", (320, 240), color)


def test_first_frame_always_changed():
    cap = CaptureService(diff_threshold=2.0)
    assert cap.has_changed(solid((0, 0, 0))) is True


def test_identical_frame_not_changed():
    cap = CaptureService(diff_threshold=2.0)
    cap.has_changed(solid((10, 10, 10)))
    assert cap.has_changed(solid((10, 10, 10))) is False


def test_large_change_detected():
    cap = CaptureService(diff_threshold=2.0)
    cap.has_changed(solid((0, 0, 0)))
    assert cap.has_changed(solid((255, 255, 255))) is True


def test_to_base64_png_roundtrips():
    cap = CaptureService()
    b64 = cap.to_base64_png(solid((1, 2, 3)))
    raw = base64.b64decode(b64)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
