from __future__ import annotations
import numpy as np
from typing import Optional, Tuple

try:
    import mss
    _MSS_OK = True
except ImportError:
    _MSS_OK = False


def capture_screen(region: Optional[Tuple[int, int, int, int]] = None) -> Optional[np.ndarray]:
    if not _MSS_OK:
        return None
    with mss.mss() as sct:
        if region:
            x, y, w, h = region
            mon = {"left": x, "top": y, "width": max(w, 1), "height": max(h, 1)}
        else:
            mon = sct.monitors[1]
        shot = sct.grab(mon)
        # BGRA -> BGR; ascontiguousarray is required: the channel slice is a
        # non-contiguous view and QImage/cv2 need a contiguous buffer
        frame = np.ascontiguousarray(np.array(shot)[:, :, :3])
    return frame


def capture_full() -> Optional[np.ndarray]:
    return capture_screen(None)


def get_pixel_color(x: int, y: int) -> Optional[Tuple[int, int, int]]:
    frame = capture_screen((x, y, 1, 1))
    if frame is None or frame.size == 0:
        return None
    b, g, r = frame[0, 0]
    return (int(b), int(g), int(r))
