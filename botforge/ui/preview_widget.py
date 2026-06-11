from __future__ import annotations
import time
from typing import Optional, Tuple
import numpy as np

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer, Signal, QPoint
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont

from ..core.capture import capture_screen
from ..core.vision import check_color_mask

try:
    import cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False


class PreviewWidget(QWidget):
    """Live preview of a screen region. Click to pick pixel color."""
    pixel_picked = Signal(int, int, int)      # B, G, R
    coords_picked = Signal(int, int)          # abs_x, abs_y (for click coordinate capture)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(200, 130)
        self.setStyleSheet("background: #11111b; border-radius: 6px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._canvas = QLabel()
        self._canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._canvas.setStyleSheet("background: transparent;")
        self._canvas.setMouseTracking(True)
        lay.addWidget(self._canvas)

        self._region: Optional[Tuple[int, int, int, int]] = None
        self._hsv_lower: Optional[list] = None
        self._hsv_upper: Optional[list] = None
        self._show_mask = False
        self._last_frame: Optional[np.ndarray] = None
        self._coord_mode = False   # next click → coords_picked
        self._pixel_mode = False   # next click → pixel_picked
        self._hover_pos: Optional[Tuple[int, int]] = None
        self._marker: Optional[Tuple[int, int]] = None   # frame coords of found match
        self._marker_expiry = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(66)  # 15 fps

        self.setMouseTracking(True)
        self._canvas.installEventFilter(self)

    def set_region(self, region: Optional[Tuple[int, int, int, int]]) -> None:
        self._region = region

    def current_region(self) -> Optional[Tuple[int, int, int, int]]:
        return self._region

    def set_mask_params(self, hsv_lower: list, hsv_upper: list, show: bool = True) -> None:
        self._hsv_lower = hsv_lower
        self._hsv_upper = hsv_upper
        self._show_mask = show

    def clear_mask(self) -> None:
        self._show_mask = False

    def show_match_marker(self, fx: int, fy: int, duration_ms: int = 4000) -> None:
        """Mark where a trigger matched. fx/fy — coords inside the region frame."""
        self._marker = (fx, fy)
        self._marker_expiry = time.monotonic() + duration_ms / 1000.0

    def enable_coord_pick(self, enabled: bool) -> None:
        """Next click in preview → emit coords_picked (absolute screen coords)."""
        self._coord_mode = enabled
        self._pixel_mode = False
        if enabled:
            self._canvas.setCursor(Qt.CursorShape.CrossCursor)
            self.setStyleSheet(
                "background: #11111b; border-radius:6px; border: 2px solid #89b4fa;"
            )
        else:
            self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
            self.setStyleSheet("background: #11111b; border-radius:6px;")

    def enable_pixel_pick(self, enabled: bool) -> None:
        """Next click in preview → emit pixel_picked (BGR color of clicked pixel)."""
        self._pixel_mode = enabled
        self._coord_mode = False
        if enabled:
            self._canvas.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setStyleSheet(
                "background: #11111b; border-radius:6px; border: 2px solid #cba6f7;"
            )
        else:
            self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
            self.setStyleSheet("background: #11111b; border-radius:6px;")

    def _tick(self) -> None:
        if self._region is None:
            self._show_placeholder()
            return
        frame = capture_screen(self._region)
        if frame is None or frame.size == 0:
            return
        self._last_frame = frame.copy()

        if self._show_mask and self._hsv_lower and self._hsv_upper and _CV2_OK:
            _, _, _, mask = check_color_mask(frame, self._hsv_lower, self._hsv_upper)
            if mask is not None:
                display = cv2.addWeighted(frame, 0.7, mask, 0.6, 0)
            else:
                display = frame
        else:
            display = frame

        self._draw_frame(display)

    def _show_placeholder(self) -> None:
        pix = QPixmap(self._canvas.size() or QPixmap(200, 130).size())
        pix.fill(QColor("#11111b"))
        painter = QPainter(pix)
        painter.setPen(QPen(QColor("#313244"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(4, 4, pix.width() - 8, pix.height() - 8)
        font = QFont()
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor("#45475a"))
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter,
                         "Область не выбрана\n\nНажмите «Выбрать на экране»")
        painter.end()
        self._canvas.setPixmap(pix)

    def _draw_frame(self, frame: np.ndarray) -> None:
        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
        h, w = frame.shape[:2]
        bpl = w * 3
        qimg = QImage(frame.data, w, h, bpl, QImage.Format.Format_BGR888)
        pix = QPixmap.fromImage(qimg)
        cw = self._canvas.width() or 200
        ch = self._canvas.height() or 130
        scaled = pix.scaled(cw, ch,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

        if self._coord_mode and self._hover_pos:
            # Draw crosshair
            p = QPainter(scaled)
            px, py = self._hover_pos
            p.setPen(QPen(QColor(100, 200, 255, 200), 1))
            p.drawLine(px, 0, px, scaled.height())
            p.drawLine(0, py, scaled.width(), py)
            p.end()

        # Match marker: where the trigger found its color/template
        if self._marker is not None:
            if time.monotonic() >= self._marker_expiry:
                self._marker = None
            elif w > 0 and h > 0:
                mx = int(self._marker[0] * scaled.width() / w)
                my = int(self._marker[1] * scaled.height() / h)
                p = QPainter(scaled)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                # Pulse: blink ~2 times per second
                visible = int(time.monotonic() * 4) % 2 == 0
                color = QColor(166, 227, 161) if visible else QColor(166, 227, 161, 120)
                p.setPen(QPen(color, 2))
                p.drawEllipse(QPoint(mx, my), 14, 14)
                p.drawEllipse(QPoint(mx, my), 3, 3)
                p.drawLine(mx - 22, my, mx - 8, my)
                p.drawLine(mx + 8, my, mx + 22, my)
                p.drawLine(mx, my - 22, mx, my - 8)
                p.drawLine(mx, my + 8, mx, my + 22)
                # Label
                font = QFont()
                font.setPixelSize(11)
                font.setBold(True)
                p.setFont(font)
                label = "НАЙДЕНО"
                lx = mx + 18 if mx < scaled.width() - 80 else mx - 78
                ly = my - 18 if my > 26 else my + 30
                p.setPen(QColor(0, 0, 0, 180))
                p.drawText(lx + 1, ly + 1, label)
                p.setPen(QColor(166, 227, 161))
                p.drawText(lx, ly, label)
                p.end()

        self._canvas.setPixmap(scaled)

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self._canvas:
            if event.type() == QEvent.Type.MouseMove:
                self._on_mouse_move(event)
            elif event.type() == QEvent.Type.MouseButtonPress:
                self._on_mouse_press(event)
        return super().eventFilter(obj, event)

    def _frame_pos(self, event) -> Optional[Tuple[int, int, int, int]]:
        """Returns (px, py, frame_x, frame_y) in frame coordinates."""
        if self._last_frame is None:
            return None
        pix = self._canvas.pixmap()
        if pix is None:
            return None
        cw, ch = self._canvas.width(), self._canvas.height()
        pw, ph = pix.width(), pix.height()
        ox = (cw - pw) // 2
        oy = (ch - ph) // 2
        px = int(event.position().x()) - ox
        py = int(event.position().y()) - oy
        if px < 0 or py < 0 or px >= pw or py >= ph:
            return None
        fh, fw = self._last_frame.shape[:2]
        fx = int(px * fw / pw)
        fy = int(py * fh / ph)
        return px, py, fx, fy

    def _on_mouse_move(self, event) -> None:
        if self._coord_mode:
            pix = self._canvas.pixmap()
            if pix:
                self._hover_pos = (int(event.position().x()), int(event.position().y()))

    def _on_mouse_press(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._frame_pos(event)
        if pos is None:
            return
        _, _, fx, fy = pos

        if self._coord_mode and self._region:
            abs_x = self._region[0] + fx
            abs_y = self._region[1] + fy
            self.coords_picked.emit(abs_x, abs_y)
            self.enable_coord_pick(False)
        elif self._pixel_mode:
            if self._last_frame is not None:
                fh, fw = self._last_frame.shape[:2]
                if 0 <= fy < fh and 0 <= fx < fw:
                    b, g, r = self._last_frame[fy, fx]
                    self.pixel_picked.emit(int(b), int(g), int(r))
            self.enable_pixel_pick(False)
