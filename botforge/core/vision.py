from __future__ import annotations
import numpy as np
from typing import Tuple, Optional

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False


def check_color_mask(
    frame: np.ndarray,
    hsv_lower: list,
    hsv_upper: list,
    min_ratio: float = 0.05,
) -> Tuple[bool, Optional[int], Optional[int], Optional[np.ndarray]]:
    """
    Returns (triggered, center_x, center_y, mask_bgr).
    mask_bgr is a colorized mask for overlay in preview.
    Handles hue wrap-around (red channel: 0-10 and 170-180).
    """
    if not _CV2_OK or frame is None or frame.size == 0:
        return False, None, None, None

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lo = np.array(hsv_lower, dtype=np.uint8)
    hi = np.array(hsv_upper, dtype=np.uint8)

    if lo[0] > hi[0]:
        mask1 = cv2.inRange(hsv, np.array([lo[0], lo[1], lo[2]]), np.array([179, hi[1], hi[2]]))
        mask2 = cv2.inRange(hsv, np.array([0, lo[1], lo[2]]), np.array([hi[0], hi[1], hi[2]]))
        mask = cv2.bitwise_or(mask1, mask2)
    else:
        mask = cv2.inRange(hsv, lo, hi)

    total = frame.shape[0] * frame.shape[1]
    matched = cv2.countNonZero(mask)
    ratio = matched / total if total > 0 else 0
    triggered = ratio >= min_ratio

    cx, cy = None, None
    if triggered:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            M = cv2.moments(largest)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])

    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    mask_bgr[:, :, 0] = 0
    mask_bgr[:, :, 2] = 0

    return triggered, cx, cy, mask_bgr


def check_template(
    frame: np.ndarray,
    template: np.ndarray,
    threshold: float = 0.8,
) -> Tuple[bool, Optional[int], Optional[int]]:
    """Template matching. Returns (triggered, center_x, center_y)."""
    if not _CV2_OK or frame is None or template is None:
        return False, None, None
    if frame.shape[0] < template.shape[0] or frame.shape[1] < template.shape[1]:
        return False, None, None

    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        cx = max_loc[0] + template.shape[1] // 2
        cy = max_loc[1] + template.shape[0] // 2
        return True, cx, cy

    return False, None, None


def check_pixel_color(
    frame: np.ndarray,
    rgb: list,
    tolerance: int = 10,
) -> bool:
    """Check that the first pixel of frame matches rgb within tolerance."""
    if frame is None or frame.size == 0:
        return False
    b, g, r = (int(v) for v in frame[0, 0][:3])
    er, eg, eb = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return (abs(r - er) <= tolerance
            and abs(g - eg) <= tolerance
            and abs(b - eb) <= tolerance)


def check_change(
    frame: np.ndarray,
    prev_frame: Optional[np.ndarray],
    min_ratio: float = 0.05,
) -> Tuple[bool, Optional[int], Optional[int], Optional[np.ndarray]]:
    """
    Detect change between two consecutive frames of the same region.
    Returns (changed, center_x, center_y, diff_mask_bgr).
    """
    if not _CV2_OK or frame is None or prev_frame is None:
        return False, None, None, None
    if frame.shape != prev_frame.shape:
        return False, None, None, None

    diff = cv2.absdiff(frame, prev_frame)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)

    total = mask.shape[0] * mask.shape[1]
    ratio = cv2.countNonZero(mask) / total if total > 0 else 0
    changed = ratio >= min_ratio

    cx, cy = None, None
    if changed:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            M = cv2.moments(largest)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
        if cx is None:
            cx, cy = mask.shape[1] // 2, mask.shape[0] // 2

    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    mask_bgr[:, :, 0] = 0   # keep red channel only -> red overlay
    mask_bgr[:, :, 1] = 0

    return changed, cx, cy, mask_bgr


def bgr_to_hsv(bgr: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Convert a single BGR pixel to HSV."""
    if not _CV2_OK:
        return (0, 0, 0)
    pixel = np.array([[[bgr[0], bgr[1], bgr[2]]]], dtype=np.uint8)
    hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)
    h, s, v = int(hsv[0, 0, 0]), int(hsv[0, 0, 1]), int(hsv[0, 0, 2])
    return (h, s, v)


def make_hsv_range(h: int, s: int, v: int, h_tol: int = 15, sv_tol: int = 60) -> Tuple[list, list]:
    """Auto HSV range from a sampled pixel color."""
    lo = [max(0, h - h_tol), max(0, s - sv_tol), max(0, v - sv_tol)]
    hi = [min(179, h + h_tol), min(255, s + sv_tol), min(255, v + sv_tol)]
    return lo, hi
