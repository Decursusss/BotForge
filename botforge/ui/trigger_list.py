from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame
)
from PySide6.QtCore import Signal, Qt, QTimer, QSize
from PySide6.QtGui import QPainter, QColor, QBrush
from ..core.models import Trigger

# ── StatusDot ─────────────────────────────────────────────────────────────────

class StatusDot(QWidget):
    """A small painted circle indicator — never renders as a black box."""

    _COLORS = {
        "idle":     QColor("#3d4058"),
        "selected": QColor("#89b4fa"),
        "active":   QColor("#a6e3a1"),
        "waiting":  QColor("#f9e2af"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._state = "idle"
        self._pulse_alpha = 255
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_dir = -1

    def set_state(self, state: str) -> None:
        self._state = state
        if state == "active":
            self._pulse_timer.start(40)
        else:
            self._pulse_timer.stop()
            self._pulse_alpha = 255
        self.update()

    def _pulse_tick(self) -> None:
        self._pulse_alpha += self._pulse_dir * 15
        if self._pulse_alpha <= 80:
            self._pulse_dir = 1
        elif self._pulse_alpha >= 255:
            self._pulse_dir = -1
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._COLORS.get(self._state, self._COLORS["idle"]))
        if self._state == "active":
            color.setAlpha(self._pulse_alpha)
            # Outer glow
            glow = QColor(color)
            glow.setAlpha(60)
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, 10, 10)
            # Inner circle
            color.setAlpha(self._pulse_alpha)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 6, 6)


# ── Card styles ───────────────────────────────────────────────────────────────

CARD_STYLE_NORMAL = """
QFrame#TriggerCard {
    border: 1px solid #313244;
    border-radius: 6px;
}
"""
CARD_STYLE_SELECTED = """
QFrame#TriggerCard {
    border: 1px solid #89b4fa;
    border-radius: 6px;
}
"""
CARD_STYLE_ACTIVE = """
QFrame#TriggerCard {
    border: 1px solid #a6e3a1;
    border-radius: 6px;
}
"""

DEL_BTN_STYLE = """
QPushButton {
    background: transparent;
    color: #45475a;
    border: none;
    font-size: 12px;
    border-radius: 3px;
    padding: 2px 4px;
}
QPushButton:hover {
    color: #f38ba8;
    background: #3a1a1a;
}
"""


# ── TriggerCard ───────────────────────────────────────────────────────────────

class TriggerCard(QFrame):
    selected = Signal(str)
    deleted  = Signal(str)

    def __init__(self, trigger: Trigger, parent=None):
        super().__init__(parent)
        self.setObjectName("TriggerCard")
        self.trigger_id = trigger.id
        self._is_selected = False
        self._is_active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(50)
        self.setStyleSheet(CARD_STYLE_NORMAL)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(8)

        # Status dot
        self._dot = StatusDot()

        # Type badge
        self._badge = QLabel()
        self._badge.setFixedSize(20, 20)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_badge(trigger.type)

        # Name
        self._name = QLabel(trigger.name)
        self._name.setStyleSheet("color: #cdd6f4; font-size: 12px;")

        # Region indicator
        self._region_lbl = QLabel()
        self._set_region_label(trigger)

        self._del_btn = QPushButton("✕")
        self._del_btn.setFixedSize(22, 22)
        self._del_btn.setStyleSheet(DEL_BTN_STYLE)
        self._del_btn.setToolTip("Удалить триггер")
        self._del_btn.clicked.connect(lambda: self.deleted.emit(self.trigger_id))

        lay.addWidget(self._dot)
        lay.addWidget(self._badge)
        lay.addWidget(self._name)
        lay.addStretch()
        lay.addWidget(self._region_lbl)
        lay.addSpacing(4)
        lay.addWidget(self._del_btn)

    _BADGES = {
        "color_mask": ("H", "#2a1a4a", "#cba6f7", "Цветовая маска (HSV)"),
        "template":   ("T", "#1a2a4a", "#89b4fa", "Поиск картинки (Template)"),
        "pixel":      ("P", "#1a3a2a", "#a6e3a1", "Пиксель (точный цвет)"),
        "change":     ("Δ", "#3a2a1a", "#fab387", "Движение / изменение"),
        "sound":      ("S", "#1a3a3a", "#94e2d5", "Звук системы"),
    }

    def _set_badge(self, ttype: str) -> None:
        text, bg, fg, tip = self._BADGES.get(ttype, self._BADGES["color_mask"])
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"background: {bg}; color: {fg}; font-size: 9px; font-weight: bold;"
            " border-radius: 4px;"
        )
        self._badge.setToolTip(tip)

    def set_selected(self, v: bool) -> None:
        self._is_selected = v
        self._refresh_style()
        self._dot.set_state("selected" if v and not self._is_active else
                            "active" if self._is_active else "idle")

    def set_active(self, v: bool) -> None:
        self._is_active = v
        self._dot.set_state("active" if v else ("selected" if self._is_selected else "idle"))
        self._refresh_style()

    def _refresh_style(self) -> None:
        if self._is_active:
            self.setStyleSheet(CARD_STYLE_ACTIVE)
        elif self._is_selected:
            self.setStyleSheet(CARD_STYLE_SELECTED)
        else:
            self.setStyleSheet(CARD_STYLE_NORMAL)

    def _set_region_label(self, trigger: Trigger) -> None:
        if trigger.type == "sound":
            ok = bool(trigger.sound_path) or trigger.sound_mode == "level"
            self._region_lbl.setText("звук" if ok else "нет образца")
            self._region_lbl.setStyleSheet(
                "color: #585b70; font-size: 10px;" if ok
                else "color: #f9e2af; font-size: 10px;")
            return
        if trigger.type == "pixel":
            ok = trigger.pixel_x > 0 or trigger.pixel_y > 0
            self._region_lbl.setText(
                f"({trigger.pixel_x},{trigger.pixel_y})" if ok else "нет пикселя")
            self._region_lbl.setStyleSheet(
                "color: #585b70; font-size: 10px;" if ok
                else "color: #f9e2af; font-size: 10px;")
            return
        has_region = trigger.region[2] > 0 and trigger.region[3] > 0
        self._region_lbl.setText(
            f"{trigger.region[2]}×{trigger.region[3]}" if has_region else "нет области")
        self._region_lbl.setStyleSheet(
            "color: #585b70; font-size: 10px;" if has_region
            else "color: #f9e2af; font-size: 10px;")

    def update_trigger(self, trigger: Trigger) -> None:
        self._name.setText(trigger.name)
        self._set_badge(trigger.type)
        self._set_region_label(trigger)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.trigger_id)
        super().mousePressEvent(event)


# ── TriggerListWidget ─────────────────────────────────────────────────────────

class TriggerListWidget(QWidget):
    trigger_selected = Signal(str)
    trigger_deleted  = Signal(str)
    add_requested    = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setStyleSheet("background: #181825;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 8, 8, 8)
        title = QLabel("ТРИГГЕРЫ")
        title.setStyleSheet(
            "color: #585b70; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
        )
        add_btn = QPushButton("+ Добавить")
        add_btn.setStyleSheet("""
            QPushButton {
                background: #313244; color: #89b4fa;
                border: 1px solid #45475a; border-radius: 4px;
                padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #45475a; }
        """)
        add_btn.clicked.connect(self.add_requested.emit)
        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(add_btn)
        lay.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #313244;")
        lay.addWidget(sep)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: #181825;")

        self._container = QWidget()
        self._container.setStyleSheet("background: #181825;")
        self._vlay = QVBoxLayout(self._container)
        self._vlay.setContentsMargins(6, 6, 6, 6)
        self._vlay.setSpacing(4)

        self._empty_lbl = QLabel("Нет триггеров.\nНажмите «+ Добавить»\nчтобы создать первый.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setStyleSheet("color: #45475a; font-size: 11px; padding: 12px;")
        self._vlay.addWidget(self._empty_lbl)
        self._vlay.addStretch()

        scroll.setWidget(self._container)
        lay.addWidget(scroll, 1)

        self._cards: dict[str, TriggerCard] = {}
        self._selected_id: str | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def add_trigger(self, trigger: Trigger) -> None:
        if self._empty_lbl.isVisible():
            self._empty_lbl.hide()
        card = TriggerCard(trigger)
        card.selected.connect(self._on_card_selected)
        card.deleted.connect(self._on_card_deleted)
        self._cards[trigger.id] = card
        self._vlay.insertWidget(self._vlay.count() - 1, card)

    def _on_card_selected(self, tid: str) -> None:
        if self._selected_id and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(False)
        self._selected_id = tid
        if tid in self._cards:
            self._cards[tid].set_selected(True)
        self.trigger_selected.emit(tid)

    def _on_card_deleted(self, tid: str) -> None:
        self.remove_trigger(tid)
        self.trigger_deleted.emit(tid)

    def remove_trigger(self, tid: str) -> None:
        if tid not in self._cards:
            return
        card = self._cards.pop(tid)
        self._vlay.removeWidget(card)
        card.deleteLater()
        if self._selected_id == tid:
            self._selected_id = None
        if not self._cards:
            self._empty_lbl.show()

    def update_trigger(self, trigger: Trigger) -> None:
        if trigger.id in self._cards:
            self._cards[trigger.id].update_trigger(trigger)

    def set_active(self, tid: str, active: bool) -> None:
        if tid in self._cards:
            self._cards[tid].set_active(active)

    def clear_active(self) -> None:
        for card in self._cards.values():
            card.set_active(False)

    def clear_all(self) -> None:
        for tid in list(self._cards.keys()):
            self.remove_trigger(tid)
        self._selected_id = None
