from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QGroupBox, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette

from ..core.vision import bgr_to_hsv, make_hsv_range


class ColorSwatch(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setFrameShape(QFrame.Shape.Box)
        self.set_bgr(0, 0, 0)

    def set_bgr(self, b: int, g: int, r: int) -> None:
        self.setStyleSheet(f"background: rgb({r},{g},{b}); border-radius: 4px;")


class HSVSlider(QWidget):
    value_changed = Signal()

    def __init__(self, label: str, lo: int, hi: int, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label)
        lbl.setFixedWidth(20)
        lbl.setStyleSheet("color:#aaa; font-size:11px;")

        self._lo = QSlider(Qt.Orientation.Horizontal)
        self._lo.setRange(0, hi)
        self._lo.setValue(lo)

        self._hi = QSlider(Qt.Orientation.Horizontal)
        self._hi.setRange(0, hi)
        self._hi.setValue(hi)

        self._lo_lbl = QLabel(str(lo))
        self._hi_lbl = QLabel(str(hi))
        for l in (self._lo_lbl, self._hi_lbl):
            l.setFixedWidth(30)
            l.setStyleSheet("color:#ccc; font-size:11px;")

        self._lo.valueChanged.connect(self._on_change)
        self._hi.valueChanged.connect(self._on_change)

        layout.addWidget(lbl)
        layout.addWidget(self._lo)
        layout.addWidget(self._lo_lbl)
        layout.addWidget(self._hi)
        layout.addWidget(self._hi_lbl)

    def _on_change(self) -> None:
        self._lo_lbl.setText(str(self._lo.value()))
        self._hi_lbl.setText(str(self._hi.value()))
        self.value_changed.emit()

    def get_range(self) -> tuple[int, int]:
        return self._lo.value(), self._hi.value()

    def set_range(self, lo: int, hi: int) -> None:
        self._lo.blockSignals(True)
        self._hi.blockSignals(True)
        self._lo.setValue(lo)
        self._hi.setValue(hi)
        self._lo_lbl.setText(str(lo))
        self._hi_lbl.setText(str(hi))
        self._lo.blockSignals(False)
        self._hi.blockSignals(False)
        self.value_changed.emit()


class ColorPickerWidget(QWidget):
    """HSV range editor with eyedropper support."""
    range_changed = Signal(list, list)  # hsv_lower, hsv_upper

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        top = QHBoxLayout()
        self._swatch = ColorSwatch()
        swatch_lbl = QLabel("Текущий цвет:")
        swatch_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        top.addWidget(swatch_lbl)
        top.addWidget(self._swatch)
        top.addStretch()
        layout.addLayout(top)

        self._h = HSVSlider("H", 0, 179)
        self._s = HSVSlider("S", 0, 255)
        self._v = HSVSlider("V", 0, 255)
        layout.addWidget(self._h)
        layout.addWidget(self._s)
        layout.addWidget(self._v)

        self._h.value_changed.connect(self._emit)
        self._s.value_changed.connect(self._emit)
        self._v.value_changed.connect(self._emit)

        self._h.set_range(0, 30)
        self._s.set_range(100, 255)
        self._v.set_range(100, 255)

    def set_from_bgr(self, b: int, g: int, r: int) -> None:
        self._swatch.set_bgr(b, g, r)
        h, s, v = bgr_to_hsv((b, g, r))
        lo, hi = make_hsv_range(h, s, v)
        self._h.set_range(lo[0], hi[0])
        self._s.set_range(lo[1], hi[1])
        self._v.set_range(lo[2], hi[2])
        self._emit()

    def get_hsv_lower(self) -> list:
        return [self._h.get_range()[0], self._s.get_range()[0], self._v.get_range()[0]]

    def get_hsv_upper(self) -> list:
        return [self._h.get_range()[1], self._s.get_range()[1], self._v.get_range()[1]]

    def set_hsv_range(self, lower: list, upper: list) -> None:
        self._h.set_range(lower[0], upper[0])
        self._s.set_range(lower[1], upper[1])
        self._v.set_range(lower[2], upper[2])

    def _emit(self) -> None:
        self.range_changed.emit(self.get_hsv_lower(), self.get_hsv_upper())
