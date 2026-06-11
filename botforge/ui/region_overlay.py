from __future__ import annotations
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, Signal, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QFont


class RegionOverlay(QWidget):
    """Full-screen selection overlay. Emits physical-pixel coordinates."""
    region_selected = Signal(int, int, int, int)   # x, y, w, h — physical pixels
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._drawing = False

    def showEvent(self, event):
        # Reset previous selection: a leftover cutout rect is fully transparent
        # and click-through on Windows, blocking re-selection of that area
        self._start = None
        self._end = None
        self._drawing = False
        screen = QApplication.primaryScreen()
        # setGeometry uses logical pixels; overlay covers the full logical screen
        self.setGeometry(screen.geometry())
        self.raise_()
        self.activateWindow()
        super().showEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.pos()
            self._end = event.pos()
            self._drawing = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._drawing:
            return
        self._end = event.pos()
        self._drawing = False
        self.hide()
        rect = self._get_rect()
        if rect.width() > 5 and rect.height() > 5:
            # Scale logical → physical pixels for mss / pydirectinput
            ratio = QApplication.primaryScreen().devicePixelRatio()
            self.region_selected.emit(
                int(rect.x() * ratio),
                int(rect.y() * ratio),
                int(rect.width() * ratio),
                int(rect.height() * ratio),
            )
        else:
            self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._drawing = False
            self.hide()
            self.cancelled.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._start and self._end:
            rect = self._get_rect()

            # Transparent cutout
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Border
            painter.setPen(QPen(QColor(100, 200, 255), 2))
            painter.drawRect(rect)

            # Corner handles
            for cx, cy in [(rect.x(), rect.y()), (rect.right(), rect.y()),
                           (rect.x(), rect.bottom()), (rect.right(), rect.bottom())]:
                painter.fillRect(cx - 4, cy - 4, 8, 8, QColor(100, 200, 255))

            # Size label (show physical px by applying devicePixelRatio)
            ratio = QApplication.primaryScreen().devicePixelRatio()
            phys_w = int(rect.width() * ratio)
            phys_h = int(rect.height() * ratio)
            font = QFont(); font.setPixelSize(14); font.setBold(True)
            painter.setFont(font)
            label = f"{phys_w} × {phys_h} px"
            lx = rect.x() + 6
            ly = rect.y() - 8 if rect.y() > 24 else rect.bottom() + 20
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(lx + 1, ly + 1, label)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(lx, ly, label)

        # Hint
        font = QFont(); font.setPixelSize(15)
        painter.setFont(font)
        hint = "Зажмите и тяните для выбора области   •   Esc = отмена"
        fw = painter.fontMetrics().horizontalAdvance(hint)
        hx = (self.width() - fw) // 2
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(hx + 1, 41, hint)
        painter.setPen(QColor(255, 255, 220))
        painter.drawText(hx, 40, hint)

    def _get_rect(self) -> QRect:
        if not self._start or not self._end:
            return QRect()
        return QRect(self._start, self._end).normalized()


class PointPickerOverlay(QWidget):
    """Full-screen overlay: click anywhere → emits physical-pixel coords."""
    point_picked = Signal(int, int)   # x, y — physical pixels
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self._pos: QPoint | None = None

    def showEvent(self, event):
        self._pos = None  # reset leftover crosshair from previous pick
        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.raise_()
        self.activateWindow()
        super().showEvent(event)

    def mouseMoveEvent(self, event):
        self._pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ratio = QApplication.primaryScreen().devicePixelRatio()
            x = int(event.pos().x() * ratio)
            y = int(event.pos().y() * ratio)
            self.hide()
            self.point_picked.emit(x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        if self._pos:
            x, y = self._pos.x(), self._pos.y()
            pen = QPen(QColor(255, 200, 60), 1)
            painter.setPen(pen)
            painter.drawLine(x, 0, x, self.height())
            painter.drawLine(0, y, self.width(), y)
            painter.fillRect(x - 5, y - 5, 10, 10, QColor(255, 200, 60, 180))

            # Coordinate label
            ratio = QApplication.primaryScreen().devicePixelRatio()
            px, py = int(x * ratio), int(y * ratio)
            font = QFont()
            font.setPixelSize(13)
            font.setBold(True)
            painter.setFont(font)
            label = f"  x={px}  y={py}  "
            lx = x + 14 if x < self.width() - 120 else x - 120
            ly = y - 10 if y > 30 else y + 24
            painter.setPen(QColor(0, 0, 0, 160))
            painter.drawText(lx + 1, ly + 1, label)
            painter.setPen(QColor(255, 200, 60))
            painter.drawText(lx, ly, label)

        font = QFont()
        font.setPixelSize(15)
        painter.setFont(font)
        hint = "Кликните на нужную точку для захвата координат   •   Esc = отмена"
        fw = painter.fontMetrics().horizontalAdvance(hint)
        hx = (self.width() - fw) // 2
        painter.setPen(QColor(0, 0, 0, 160))
        painter.drawText(hx + 1, 41, hint)
        painter.setPen(QColor(255, 255, 180))
        painter.drawText(hx, 40, hint)
