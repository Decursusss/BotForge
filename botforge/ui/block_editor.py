from __future__ import annotations
import os
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QGroupBox, QFormLayout, QFrame, QScrollArea, QSizePolicy,
    QFileDialog, QApplication, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap

from ..core.models import Block, Action, Trigger
from .color_picker import ColorPickerWidget

# ── Styles ──────────────────────────────────────────────────────────────────

INPUT_STYLE = """
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        color: #cdd6f4;
        padding: 4px 8px;
        font-size: 12px;
        min-height: 26px;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border-color: #89b4fa;
    }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background: #313244; color: #cdd6f4;
        border: 1px solid #45475a;
        selection-background-color: #45475a;
    }
"""

SECTION_STYLE = """
QGroupBox {
    color: #585b70; font-size: 10px; font-weight: bold; letter-spacing: 1px;
    border: 1px solid #313244; border-radius: 6px;
    margin-top: 12px; padding-top: 12px;
    background: #181825;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 10px;
    padding: 0 4px; background: #181825;
}
"""

REGION_BTN_STYLE = """
QPushButton {
    background: #1a3a1a; color: #a6e3a1;
    border: 1px solid #2a5a2a; border-radius: 6px;
    padding: 10px; font-size: 13px; font-weight: bold;
}
QPushButton:hover { background: #2a5a2a; }
"""

CAPTURE_BTN_STYLE = """
QPushButton {
    background: #1e3a5e; color: #89b4fa;
    border: 1px solid #45475a; border-radius: 4px;
    padding: 4px 10px; font-size: 11px;
}
QPushButton:hover { background: #2a4a7e; }
"""

KEY_RECORD_STYLE = """
QPushButton {
    background: #2a1a3a; color: #cba6f7;
    border: 1px solid #45475a; border-radius: 4px;
    padding: 4px 10px; font-size: 11px;
}
QPushButton:hover { background: #3a2a5a; }
QPushButton[recording="true"] {
    background: #4a1a5a; border-color: #cba6f7; color: #f5c2e7;
}
"""

EYEDROP_BTN_STYLE = """
QPushButton {
    background: #2a1a3a; color: #cba6f7;
    border: 1px solid #45475a; border-radius: 4px;
    padding: 5px 10px; font-size: 12px;
}
QPushButton:hover { background: #3a2a5a; }
"""

ACTION_LIST_STYLE = """
QListWidget {
    background: #11111b;
    border: 1px solid #313244;
    border-radius: 4px;
    outline: none;
}
QListWidget::item {
    color: #cdd6f4; font-size: 11px;
    padding: 5px 8px;
    border-bottom: 1px solid #1e2030;
}
QListWidget::item:selected {
    background: #1e3050;
    color: #89b4fa;
}
"""

SMALL_BTN_STYLE = """
QPushButton {
    background: #1e2030; color: #a6adc8;
    border: 1px solid #313244; border-radius: 4px;
    padding: 4px 8px; font-size: 11px;
}
QPushButton:hover { background: #252540; color: #cdd6f4; }
QPushButton:disabled { color: #45475a; border-color: #313244; }
"""


# ── Key recorder helper ──────────────────────────────────────────────────────

class KeyRecorder:
    """Listen for one key combo via pynput and call callback with result string."""

    def __init__(self, callback):
        self._callback = callback
        self._listener = None
        self._pressed: list = []

    def start(self) -> None:
        try:
            from pynput import keyboard as kb

            def on_press(key):
                self._pressed.append(key)

            def on_release(key):
                if not self._pressed:
                    return
                parts = []
                for k in self._pressed:
                    name = self._key_name(k)
                    if name and name not in parts:
                        parts.append(name)
                self._listener.stop()
                self._listener = None
                result = "+".join(parts)
                self._callback(result)

            self._listener = kb.Listener(on_press=on_press, on_release=on_release)
            self._listener.start()
        except Exception:
            pass

    def stop(self) -> None:
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    @staticmethod
    def _key_name(key) -> str:
        try:
            # Special keys: pynput Key enum
            name = key.name  # e.g. "ctrl_l", "shift", "alt_l"
            # Normalize: remove _l / _r suffix, use clean names
            mapping = {
                "ctrl_l": "ctrl", "ctrl_r": "ctrl",
                "alt_l": "alt", "alt_r": "alt",
                "shift_l": "shift", "shift_r": "shift",
                "cmd_l": "win", "cmd_r": "win",
                "caps_lock": "capslock",
            }
            return mapping.get(name, name)
        except AttributeError:
            pass
        try:
            return key.char  # regular printable key
        except AttributeError:
            return ""


# ── Main inspector widget ────────────────────────────────────────────────────

class InspectorWidget(QScrollArea):
    block_changed               = Signal(Block)
    trigger_changed             = Signal(Trigger)
    pick_region_requested       = Signal()
    pick_color_requested        = Signal()
    pick_coords_requested       = Signal()    # from preview widget
    pick_screen_point_requested = Signal()    # full-screen point picker
    pick_template_requested     = Signal()    # cut template image from screen
    pick_pixel_requested        = Signal()    # pick pixel coords + color from screen
    record_sound_requested      = Signal(int)  # record N seconds of system audio
    test_trigger_requested      = Signal(object)  # Trigger instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background: #1e1e2e;")

        self._block: Optional[Block] = None
        self._trigger: Optional[Trigger] = None
        self._triggers: List[Trigger] = []
        self._key_recorder: Optional[KeyRecorder] = None
        self._coord_target = "xy"   # "xy" | "xy2" — where picked coords land
        self._edit_action: Optional[Action] = None  # action being edited now
        self._act_sel_idx = 0       # selected row in the action chain list

        self._root = QWidget()
        self._root.setStyleSheet("background: #1e1e2e;")
        self.setWidget(self._root)
        self._vlay = QVBoxLayout(self._root)
        self._vlay.setContentsMargins(8, 8, 8, 8)
        self._vlay.setSpacing(8)
        self._vlay.addStretch()
        self._show_empty()

    # ── Public API ───────────────────────────────────────────────────────────

    def set_triggers(self, triggers: List[Trigger]) -> None:
        self._triggers = triggers

    def load_block(self, block: Block) -> None:
        self._stop_key_recorder()
        self._trigger = None
        self._block = block
        self._act_sel_idx = 0
        self._rebuild()

    def load_trigger(self, trigger: Trigger) -> None:
        self._stop_key_recorder()
        self._block = None
        self._edit_action = None
        self._trigger = trigger
        self._rebuild()

    def clear_selection(self) -> None:
        self._stop_key_recorder()
        self._block = None
        self._trigger = None
        self._edit_action = None
        self._rebuild()

    def clear_if_trigger(self, tid: str) -> None:
        if self._trigger and self._trigger.id == tid:
            self._trigger = None
            self._rebuild()

    def clear_if_block(self, bid: str) -> None:
        if self._block and self._block.id == bid:
            self._block = None
            self._rebuild()

    def update_trigger_region(self, x: int, y: int, w: int, h: int) -> None:
        if not self._trigger:
            return
        self._trigger.region = [x, y, w, h]
        if hasattr(self, "_region_info"):
            self._region_info.setText(f"x={x}  y={y}  w={w}  h={h}  пикс.")
        self.trigger_changed.emit(self._trigger)

    def current_trigger(self) -> Optional[Trigger]:
        return self._trigger

    def set_template_path(self, path: str) -> None:
        if not self._trigger:
            return
        self._trigger.template_path = path
        self._update_tpl_thumb()
        self.trigger_changed.emit(self._trigger)

    def _update_tpl_thumb(self) -> None:
        if not hasattr(self, "_tpl_thumb") or self._trigger is None:
            return
        path = self._trigger.template_path
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                self._tpl_thumb.setPixmap(pix.scaled(
                    200, 110,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                self._tpl_info.setText(f"{pix.width()}×{pix.height()} px")
                self._tpl_info.setStyleSheet("color: #a6adc8; font-size: 10px;")
                return
        self._tpl_thumb.setText("⚠ Образец не выбран")
        self._tpl_info.setText("Вырежьте картинку с экрана или выберите файл")
        self._tpl_info.setStyleSheet("color: #f9e2af; font-size: 10px;")

    def on_pixel_picked(self, b: int, g: int, r: int) -> None:
        if self._trigger and hasattr(self, "_color_picker"):
            self._color_picker.set_from_bgr(b, g, r)

    def on_coords_picked(self, ax: int, ay: int) -> None:
        if self._edit_action is None:
            return
        if self._coord_target == "xy2":
            self._set_action("x2", ax)
            self._set_action("y2", ay)
            spins = (getattr(self, "_x2_spin", None), getattr(self, "_y2_spin", None))
        else:
            self._set_action("x", ax)
            self._set_action("y", ay)
            spins = (getattr(self, "_x_spin", None), getattr(self, "_y_spin", None))
        for spin, val in zip(spins, (ax, ay)):
            if spin is not None:
                spin.blockSignals(True)
                spin.setValue(val)
                spin.blockSignals(False)
        self._coord_target = "xy"

    def show_test_result(self, fired: bool, cx, cy) -> None:
        if not hasattr(self, "_test_result_lbl"):
            return
        if fired:
            self._test_result_lbl.setText(f"✔ СРАБОТАЛ  (центр: {cx}, {cy})")
            self._test_result_lbl.setStyleSheet(
                "color: #a6e3a1; font-size: 12px; font-weight: bold;"
                " background: #1a3a1a; border-radius: 4px; padding: 6px;"
            )
        else:
            self._test_result_lbl.setText("✘ Не сработал — проверьте цвет и область")
            self._test_result_lbl.setStyleSheet(
                "color: #f38ba8; font-size: 12px; font-weight: bold;"
                " background: #3a1a1a; border-radius: 4px; padding: 6px;"
            )

    # ── Internal rebuild ─────────────────────────────────────────────────────

    def _clear(self) -> None:
        while self._vlay.count() > 1:
            item = self._vlay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_empty(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addStretch()
        icon = QLabel("☰")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("color: #313244; font-size: 36px;")
        msg = QLabel("Выберите триггер или блок\nчтобы изменить его настройки")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #45475a; font-size: 12px;")
        lay.addWidget(icon)
        lay.addWidget(msg)
        lay.addStretch()
        self._vlay.insertWidget(0, w)

    def _rebuild(self) -> None:
        self._clear()
        if self._trigger:
            self._build_trigger()
        elif self._block:
            self._build_block()
        else:
            self._show_empty()

    def _section(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(SECTION_STYLE)
        return box

    # ── Trigger editor ───────────────────────────────────────────────────────

    def _build_trigger(self) -> None:
        t = self._trigger

        hdr = self._make_header("🎯", "Настройка триггера")
        self._vlay.insertWidget(self._vlay.count() - 1, hdr)

        # 1. Name & type
        box1 = self._section("1  НАЗВАНИЕ И ТИП")
        f1 = QFormLayout(box1)
        f1.setSpacing(6)
        name_ed = QLineEdit(t.name)
        name_ed.setStyleSheet(INPUT_STYLE)
        name_ed.setPlaceholderText("Например: Поклёвка, Низкий HP...")
        name_ed.textChanged.connect(lambda v: self._set_trigger("name", v))
        f1.addRow("Имя:", name_ed)
        type_cb = QComboBox()
        type_cb.setStyleSheet(INPUT_STYLE)
        type_cb.addItem("🎨  Цветовая маска (HSV)", "color_mask")
        type_cb.addItem("🖼  Поиск картинки", "template")
        type_cb.addItem("🎯  Пиксель (точный цвет)", "pixel")
        type_cb.addItem("👁  Движение / изменение", "change")
        type_cb.addItem("🔊  Звук", "sound")
        type_idx = {"color_mask": 0, "template": 1, "pixel": 2, "change": 3, "sound": 4}
        type_cb.setCurrentIndex(type_idx.get(t.type, 0))
        type_cb.currentIndexChanged.connect(
            lambda i: self._on_trigger_type_change(type_cb.currentData()))
        f1.addRow("Тип:", type_cb)
        self._vlay.insertWidget(self._vlay.count() - 1, box1)

        # Pixel / sound triggers have no search region — own section replaces it
        if t.type == "pixel":
            self._build_pixel_section(t)
            self._build_test_section()
            return
        if t.type == "sound":
            self._build_sound_section(t)
            self._build_test_section()
            return

        # 2. Region — most important, show big
        box2 = self._section("2  ОБЛАСТЬ ПОИСКА  (где сканировать)")
        bl2 = QVBoxLayout(box2)
        bl2.setSpacing(6)
        region_btn = QPushButton("🖱  Выбрать область на экране")
        region_btn.setStyleSheet(REGION_BTN_STYLE)
        region_btn.setToolTip(
            "Окно спрячется — выделите нужную область мышью.\n"
            "Бот будет сканировать ТОЛЬКО эту область (не весь экран).\n"
            "Чем меньше область — тем быстрее работает проверка."
        )
        region_btn.clicked.connect(self.pick_region_requested.emit)
        bl2.addWidget(region_btn)

        full_btn = QPushButton("🖥  Весь экран")
        full_btn.setStyleSheet(CAPTURE_BTN_STYLE)
        full_btn.setToolTip(
            "Сканировать весь экран целиком.\n"
            "Медленнее, чем маленькая область — используйте если\n"
            "объект может появиться в любом месте."
        )
        full_btn.clicked.connect(self._set_fullscreen_region)
        bl2.addWidget(full_btn)
        has_region = t.region[2] > 0 and t.region[3] > 0
        self._region_info = QLabel(
            f"x={t.region[0]}  y={t.region[1]}  w={t.region[2]}  h={t.region[3]}  пикс."
            if has_region else "⚠ Область не выбрана"
        )
        self._region_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._region_info.setStyleSheet(
            "color: #a6adc8; font-size: 11px;" if has_region
            else "color: #f9e2af; font-size: 11px; font-weight: bold;"
        )
        bl2.addWidget(self._region_info)
        self._vlay.insertWidget(self._vlay.count() - 1, box2)

        # 3. Detection params — depends on trigger type
        if t.type == "color_mask":
            self._build_color_section(t)
        elif t.type == "template":
            self._build_template_section(t)
        elif t.type == "change":
            self._build_change_section(t)

        self._build_test_section()

    def _build_color_section(self, t: Trigger) -> None:
        box3 = self._section("3  ЦВЕТ / HSV ДИАПАЗОН")
        bl3 = QVBoxLayout(box3)
        bl3.setSpacing(6)
        eyedrop_row = QHBoxLayout()
        eyedrop_btn = QPushButton("💉  Взять цвет с превью")
        eyedrop_btn.setStyleSheet(EYEDROP_BTN_STYLE)
        eyedrop_btn.setToolTip(
            "1. Нажмите эту кнопку\n"
            "2. Кликните на нужный цвет в окне Превью (слева вверху)"
        )
        eyedrop_btn.clicked.connect(self.pick_color_requested.emit)
        eyedrop_row.addWidget(eyedrop_btn)
        eyedrop_row.addStretch()
        bl3.addLayout(eyedrop_row)
        self._color_picker = ColorPickerWidget()
        self._color_picker.set_hsv_range(t.hsv_lower, t.hsv_upper)
        self._color_picker.range_changed.connect(self._on_color_range)
        bl3.addWidget(self._color_picker)
        f3 = QFormLayout()
        f3.setSpacing(4)
        ratio_sp = QDoubleSpinBox()
        ratio_sp.setStyleSheet(INPUT_STYLE)
        ratio_sp.setRange(0.001, 1.0)
        ratio_sp.setDecimals(3)
        ratio_sp.setSingleStep(0.005)
        ratio_sp.setValue(t.min_match_ratio)
        ratio_sp.setToolTip("Доля пикселей нужного цвета для срабатывания (0.05 = 5%)")
        ratio_sp.valueChanged.connect(lambda v: self._set_trigger("min_match_ratio", v))
        f3.addRow("Чувствительность:", ratio_sp)
        bl3.addLayout(f3)
        self._vlay.insertWidget(self._vlay.count() - 1, box3)

    def _build_template_section(self, t: Trigger) -> None:
        box3 = self._section("3  ОБРАЗЕЦ  (что искать)")
        bl3 = QVBoxLayout(box3)
        bl3.setSpacing(6)

        cut_btn = QPushButton("✂  Вырезать образец с экрана")
        cut_btn.setStyleSheet(REGION_BTN_STYLE)
        cut_btn.setToolTip(
            "Окно спрячется — обведите рамкой нужную картинку\n"
            "(кнопку, иконку, надпись). Она сохранится как образец,\n"
            "и бот будет искать её внутри области поиска."
        )
        cut_btn.clicked.connect(self.pick_template_requested.emit)
        bl3.addWidget(cut_btn)

        file_btn = QPushButton("📂  Выбрать из файла...")
        file_btn.setStyleSheet(CAPTURE_BTN_STYLE)
        file_btn.setToolTip("Загрузить готовый образец (PNG/JPG/BMP)")
        file_btn.clicked.connect(self._pick_template_file)
        bl3.addWidget(file_btn)

        # Thumbnail
        self._tpl_thumb = QLabel()
        self._tpl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tpl_thumb.setMinimumHeight(60)
        self._tpl_thumb.setStyleSheet(
            "background: #11111b; border: 1px dashed #45475a;"
            " border-radius: 4px; color: #f9e2af; font-size: 11px; padding: 6px;"
        )
        bl3.addWidget(self._tpl_thumb)
        self._tpl_info = QLabel("")
        self._tpl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl3.addWidget(self._tpl_info)
        self._update_tpl_thumb()

        f3 = QFormLayout()
        f3.setSpacing(4)
        thr_sp = QDoubleSpinBox()
        thr_sp.setStyleSheet(INPUT_STYLE)
        thr_sp.setRange(0.50, 0.99)
        thr_sp.setDecimals(2)
        thr_sp.setSingleStep(0.01)
        thr_sp.setValue(t.template_threshold)
        thr_sp.setToolTip(
            "Порог совпадения 0.50–0.99.\n"
            "0.80 — стандарт. Выше = строже (меньше ложных срабатываний),\n"
            "ниже = мягче (находит даже частично изменённую картинку)."
        )
        thr_sp.valueChanged.connect(lambda v: self._set_trigger("template_threshold", v))
        f3.addRow("Порог совпадения:", thr_sp)
        bl3.addLayout(f3)
        self._vlay.insertWidget(self._vlay.count() - 1, box3)

    def _build_pixel_section(self, t: Trigger) -> None:
        box = self._section("2  ПИКСЕЛЬ И ЦВЕТ")
        bl = QVBoxLayout(box)
        bl.setSpacing(6)

        info = QLabel(
            "Самый быстрый тип триггера: проверяется ровно один\n"
            "пиксель экрана. Пример: «пиксель полоски HP стал серым»."
        )
        info.setStyleSheet(
            "background: #1a2a3a; color: #89b4fa; font-size: 11px; "
            "border-radius: 4px; padding: 8px; border: 1px solid #2a4a6a;"
        )
        info.setWordWrap(True)
        bl.addWidget(info)

        pick_btn = QPushButton("🎯  Выбрать пиксель на экране")
        pick_btn.setStyleSheet(REGION_BTN_STYLE)
        pick_btn.setToolTip(
            "Окно спрячется — кликните на нужный пиксель.\n"
            "Координаты и цвет запишутся автоматически."
        )
        pick_btn.clicked.connect(self.pick_pixel_requested.emit)
        bl.addWidget(pick_btn)

        # Current pixel info: coords + color swatch
        info_row = QHBoxLayout()
        info_row.setSpacing(8)
        self._pixel_swatch = QLabel()
        self._pixel_swatch.setFixedSize(28, 28)
        self._pixel_info = QLabel()
        self._pixel_info.setStyleSheet("color: #a6adc8; font-size: 11px;")
        info_row.addStretch()
        info_row.addWidget(self._pixel_swatch)
        info_row.addWidget(self._pixel_info)
        info_row.addStretch()
        bl.addLayout(info_row)
        self._refresh_pixel_info()

        f = QFormLayout()
        f.setSpacing(4)
        tol_sp = QSpinBox()
        tol_sp.setStyleSheet(INPUT_STYLE)
        tol_sp.setRange(0, 120)
        tol_sp.setValue(t.pixel_tolerance)
        tol_sp.setToolTip(
            "Допуск по каждому каналу R/G/B.\n"
            "0 = цвет точь-в-точь, 10 = небольшие отличия,\n"
            "30+ = широкий допуск (полупрозрачность, свечение)."
        )
        tol_sp.valueChanged.connect(lambda v: self._set_trigger("pixel_tolerance", v))
        f.addRow("Допуск ±:", tol_sp)
        bl.addLayout(f)
        self._vlay.insertWidget(self._vlay.count() - 1, box)

    def _refresh_pixel_info(self) -> None:
        if not hasattr(self, "_pixel_swatch") or self._trigger is None:
            return
        t = self._trigger
        has_pixel = t.pixel_x > 0 or t.pixel_y > 0
        r, g, b = (int(v) for v in t.pixel_rgb)
        if has_pixel:
            self._pixel_swatch.setStyleSheet(
                f"background: rgb({r},{g},{b}); border: 1px solid #45475a;"
                " border-radius: 4px;"
            )
            self._pixel_info.setText(f"({t.pixel_x}, {t.pixel_y})   RGB({r},{g},{b})")
            self._pixel_info.setStyleSheet("color: #a6adc8; font-size: 11px;")
        else:
            self._pixel_swatch.setStyleSheet(
                "background: #11111b; border: 1px dashed #45475a; border-radius: 4px;"
            )
            self._pixel_info.setText("⚠ Пиксель не выбран")
            self._pixel_info.setStyleSheet(
                "color: #f9e2af; font-size: 11px; font-weight: bold;")

    def update_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        """Called after the user picked a pixel on screen."""
        if not self._trigger:
            return
        t = self._trigger
        t.pixel_x = x
        t.pixel_y = y
        t.pixel_rgb = [r, g, b]
        # Region = small viewport around the pixel (for preview/click_on_trigger)
        rx = max(0, x - 60)
        ry = max(0, y - 40)
        t.region = [rx, ry, 120, 80]
        self._refresh_pixel_info()
        self.trigger_changed.emit(t)

    def _build_sound_section(self, t: Trigger) -> None:
        box = self._section("2  ЗВУК СИСТЕМЫ")
        bl = QVBoxLayout(box)
        bl.setSpacing(6)

        info = QLabel(
            "Триггер слушает звук, который играет в колонках\n"
            "(игра, программа). Пример: звук поклёвки, сигнал боя."
        )
        info.setStyleSheet(
            "background: #1a2a3a; color: #89b4fa; font-size: 11px; "
            "border-radius: 4px; padding: 8px; border: 1px solid #2a4a6a;"
        )
        info.setWordWrap(True)
        bl.addWidget(info)

        try:
            from ..core.audio import AUDIO_OK
        except Exception:
            AUDIO_OK = False
        if not AUDIO_OK:
            warn = QLabel("⚠ Установите пакет:  pip install soundcard")
            warn.setStyleSheet(
                "background: #3a1a1a; color: #f38ba8; font-size: 11px;"
                " border-radius: 4px; padding: 8px; font-weight: bold;"
            )
            bl.addWidget(warn)

        # Mode
        f0 = QFormLayout()
        f0.setSpacing(4)
        mode_cb = QComboBox()
        mode_cb.setStyleSheet(INPUT_STYLE)
        mode_cb.addItem("🎵  Распознать звук (образец)", "match")
        mode_cb.addItem("📢  Громкость (любой звук)", "level")
        mode_cb.setCurrentIndex(0 if t.sound_mode == "match" else 1)
        mode_cb.setToolTip(
            "Образец: запишите конкретный звук — триггер сработает,\n"
            "когда услышит именно его.\n"
            "Громкость: срабатывает на любой звук громче порога\n"
            "(удобно для тихих игр, где любой сигнал — событие)."
        )
        mode_cb.currentIndexChanged.connect(
            lambda: self._on_sound_mode_change(mode_cb.currentData()))
        f0.addRow("Режим:", mode_cb)
        bl.addLayout(f0)

        if t.sound_mode == "match":
            # Record controls
            rec_row = QHBoxLayout()
            rec_row.setSpacing(6)
            self._snd_dur_sp = QSpinBox()
            self._snd_dur_sp.setStyleSheet(INPUT_STYLE)
            self._snd_dur_sp.setRange(1, 10)
            self._snd_dur_sp.setValue(3)
            self._snd_dur_sp.setSuffix(" сек")
            self._snd_dur_sp.setToolTip("Длительность записи")
            rec_btn = QPushButton("⏺  Записать звук")
            rec_btn.setStyleSheet(REGION_BTN_STYLE)
            rec_btn.setToolTip(
                "Нажмите и сразу воспроизведите звук в игре.\n"
                "Запись начнётся немедленно, тишина по краям\n"
                "обрежется автоматически."
            )
            rec_btn.setEnabled(AUDIO_OK)
            rec_btn.clicked.connect(
                lambda: self.record_sound_requested.emit(self._snd_dur_sp.value()))
            rec_row.addWidget(rec_btn, 1)
            rec_row.addWidget(self._snd_dur_sp)
            bl.addLayout(rec_row)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)
            file_btn = QPushButton("📂  Из файла")
            file_btn.setStyleSheet(CAPTURE_BTN_STYLE)
            file_btn.setToolTip("Загрузить готовый WAV-файл")
            file_btn.clicked.connect(self._pick_sound_file)
            btn_row.addWidget(file_btn)

            play_btn = QPushButton("▶  Прослушать")
            play_btn.setStyleSheet(CAPTURE_BTN_STYLE)
            play_btn.clicked.connect(self._play_sound_sample)
            btn_row.addWidget(play_btn)

            trim_btn = QPushButton("✂  Обрезать тишину")
            trim_btn.setStyleSheet(CAPTURE_BTN_STYLE)
            trim_btn.setToolTip("Убрать тишину в начале и конце образца")
            trim_btn.clicked.connect(self._trim_sound_sample)
            btn_row.addWidget(trim_btn)
            bl.addLayout(btn_row)

            self._snd_info = QLabel("")
            self._snd_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(self._snd_info)
            self._refresh_sound_info()

            f = QFormLayout()
            f.setSpacing(4)
            thr_sp = QDoubleSpinBox()
            thr_sp.setStyleSheet(INPUT_STYLE)
            thr_sp.setRange(0.30, 0.95)
            thr_sp.setDecimals(2)
            thr_sp.setSingleStep(0.05)
            thr_sp.setValue(t.sound_threshold)
            thr_sp.setToolTip(
                "Порог похожести 0.30–0.95.\n"
                "0.60 — стандарт. Если ложные срабатывания — повысьте,\n"
                "если не ловит звук — понизьте."
            )
            thr_sp.valueChanged.connect(lambda v: self._set_trigger("sound_threshold", v))
            f.addRow("Порог похожести:", thr_sp)
            bl.addLayout(f)
        else:
            f = QFormLayout()
            f.setSpacing(4)
            lvl_sp = QDoubleSpinBox()
            lvl_sp.setStyleSheet(INPUT_STYLE)
            lvl_sp.setRange(0.01, 1.00)
            lvl_sp.setDecimals(2)
            lvl_sp.setSingleStep(0.01)
            lvl_sp.setValue(t.sound_level)
            lvl_sp.setToolTip(
                "Порог громкости (RMS) 0.01–1.00.\n"
                "0.05 — тихие звуки, 0.30 — только громкие."
            )
            lvl_sp.valueChanged.connect(lambda v: self._set_trigger("sound_level", v))
            f.addRow("Порог громкости:", lvl_sp)
            bl.addLayout(f)
            hint = QLabel("Сработает на ЛЮБОЙ звук громче порога")
            hint.setStyleSheet("color: #585b70; font-size: 10px;")
            bl.addWidget(hint)

        self._vlay.insertWidget(self._vlay.count() - 1, box)

    def _on_sound_mode_change(self, mode: str) -> None:
        self._set_trigger("sound_mode", mode)
        QTimer.singleShot(0, self._rebuild)

    def set_sound_path(self, path: str) -> None:
        if not self._trigger:
            return
        self._trigger.sound_path = path
        self._refresh_sound_info()
        self.trigger_changed.emit(self._trigger)

    def _refresh_sound_info(self) -> None:
        if not hasattr(self, "_snd_info") or self._trigger is None:
            return
        path = self._trigger.sound_path
        if path and os.path.exists(path):
            try:
                from ..core.audio import wav_duration_ms
                ms = wav_duration_ms(path)
            except Exception:
                ms = 0
            self._snd_info.setText(f"✔ Образец: {ms / 1000:.1f} сек")
            self._snd_info.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        else:
            self._snd_info.setText("⚠ Образец не записан")
            self._snd_info.setStyleSheet(
                "color: #f9e2af; font-size: 11px; font-weight: bold;")

    def _pick_sound_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать звук", "", "Аудио WAV (*.wav);;Все файлы (*)")
        if path:
            self.set_sound_path(path)

    def _play_sound_sample(self) -> None:
        t = self._trigger
        if not t or not t.sound_path or not os.path.exists(t.sound_path):
            return
        try:
            import winsound
            winsound.PlaySound(
                t.sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass

    def _trim_sound_sample(self) -> None:
        t = self._trigger
        if not t or not t.sound_path or not os.path.exists(t.sound_path):
            return
        try:
            from ..core.audio import load_wav, trim_silence, save_wav
            data = load_wav(t.sound_path)
            if data is None or len(data) == 0:
                return
            save_wav(t.sound_path, trim_silence(data))
        except Exception:
            return
        self._refresh_sound_info()
        self.trigger_changed.emit(t)

    def _build_change_section(self, t: Trigger) -> None:
        box = self._section("3  ДЕТЕКТОР ИЗМЕНЕНИЙ")
        bl = QVBoxLayout(box)
        bl.setSpacing(6)

        info = QLabel(
            "Срабатывает, когда картинка в области ИЗМЕНИЛАСЬ\n"
            "по сравнению с предыдущей проверкой.\n"
            "Идеально: поклёвка, появление моба, всплывающее окно.\n"
            "Не нужно знать заранее ни цвет, ни картинку."
        )
        info.setStyleSheet(
            "background: #3a2a1a; color: #fab387; font-size: 11px; "
            "border-radius: 4px; padding: 8px; border: 1px solid #5a4a2a;"
        )
        info.setWordWrap(True)
        bl.addWidget(info)

        f = QFormLayout()
        f.setSpacing(4)
        ratio_sp = QDoubleSpinBox()
        ratio_sp.setStyleSheet(INPUT_STYLE)
        ratio_sp.setRange(0.001, 1.0)
        ratio_sp.setDecimals(3)
        ratio_sp.setSingleStep(0.005)
        ratio_sp.setValue(t.min_match_ratio)
        ratio_sp.setToolTip(
            "Какая доля области должна измениться для срабатывания.\n"
            "0.02 (2%) — чувствительно, ловит мелкие движения.\n"
            "0.20 (20%) — только крупные изменения."
        )
        ratio_sp.valueChanged.connect(lambda v: self._set_trigger("min_match_ratio", v))
        f.addRow("Чувствительность:", ratio_sp)
        bl.addLayout(f)
        self._vlay.insertWidget(self._vlay.count() - 1, box)

    def _build_test_section(self) -> None:
        box4 = self._section("4  ПРОВЕРКА")
        bl4 = QVBoxLayout(box4)
        bl4.setSpacing(6)
        test_btn = QPushButton("⚡  Проверить триггер сейчас")
        test_btn.setStyleSheet(EYEDROP_BTN_STYLE)
        test_btn.setToolTip(
            "Мгновенная проверка: сработал бы триггер прямо сейчас?\n"
            "Бот запускать не нужно."
        )
        test_btn.clicked.connect(lambda: self.test_trigger_requested.emit(self._trigger))
        bl4.addWidget(test_btn)
        self._test_result_lbl = QLabel("")
        self._test_result_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._test_result_lbl.setWordWrap(True)
        bl4.addWidget(self._test_result_lbl)
        self._vlay.insertWidget(self._vlay.count() - 1, box4)

    def _on_trigger_type_change(self, new_type: str) -> None:
        self._set_trigger("type", new_type)
        # Rebuild editor: section 3 differs per type. Deferred — the combo
        # emitting this signal is inside the layout being rebuilt.
        QTimer.singleShot(0, self._rebuild)

    def _set_fullscreen_region(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.geometry()
        ratio = screen.devicePixelRatio()
        self.update_trigger_region(
            0, 0, int(geo.width() * ratio), int(geo.height() * ratio))

    def _pick_template_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать образец", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp);;Все файлы (*)")
        if path:
            self.set_template_path(path)

    # ── Block editor ─────────────────────────────────────────────────────────

    def _build_block(self) -> None:
        b = self._block

        icons = {
            "wait": "⏱", "action": "▶", "if_trigger": "⚡",
            "wait_trigger": "⏳", "while_trigger": "🔁",
        }
        names = {
            "wait": "Ожидание", "action": "Действие",
            "if_trigger": "Условие ЕСЛИ", "wait_trigger": "Ждать триггер",
            "while_trigger": "Цикл ПОКА",
        }
        hdr = self._make_header(icons.get(b.type, "●"), names.get(b.type, b.type))
        self._vlay.insertWidget(self._vlay.count() - 1, hdr)

        box_lbl = self._section("МЕТКА (необязательно)")
        fl = QFormLayout(box_lbl)
        lbl_ed = QLineEdit(b.label)
        lbl_ed.setStyleSheet(INPUT_STYLE)
        lbl_ed.setPlaceholderText("Своё описание блока...")
        lbl_ed.textChanged.connect(self._on_label_change)
        fl.addRow("", lbl_ed)
        self._vlay.insertWidget(self._vlay.count() - 1, box_lbl)

        if b.type == "wait":
            if b.action is None:
                b.action = Action(type="wait", ms=500)
            self._build_wait()
        elif b.type == "action":
            if b.action is None:
                b.action = Action(type="click_xy")
            self._build_action_box(b.action)
        elif b.type == "if_trigger":
            if b.action is None:
                b.action = Action(type="click_on_trigger")
            self._build_if_trigger()
        elif b.type == "wait_trigger":
            self._build_wait_trigger()
        elif b.type == "while_trigger":
            if b.action is None:
                b.action = Action(type="click_on_trigger")
            self._build_while_trigger()

    def _build_wait(self) -> None:
        self._edit_action = self._block.action
        box = self._section("ПАРАМЕТРЫ")
        f = QFormLayout(box)
        sp = QSpinBox()
        sp.setStyleSheet(INPUT_STYLE)
        sp.setRange(0, 300000)
        sp.setValue(self._block.action.ms or 500)
        sp.setSuffix(" мс")
        sp.setToolTip("Пауза в миллисекундах. 1000 мс = 1 секунда")
        sp.valueChanged.connect(lambda v: self._set_action("ms", v))
        f.addRow("Длительность:", sp)
        self._vlay.insertWidget(self._vlay.count() - 1, box)

    def _build_wait_trigger(self) -> None:
        b = self._block
        box = self._section("ЖДАТЬ ПОКА ТРИГГЕР НЕ СРАБОТАЕТ")
        lay = QVBoxLayout(box)
        lay.setSpacing(8)

        # Explanation banner
        info = QLabel(
            "Сценарий остановится здесь и будет ждать,\n"
            "пока выбранный триггер не обнаружит цвет/объект.\n"
            "После срабатывания — продолжит следующий блок."
        )
        info.setStyleSheet(
            "background: #1a2a3a; color: #89b4fa; font-size: 11px; "
            "border-radius: 4px; padding: 8px; border: 1px solid #2a4a6a;"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        f = QFormLayout()
        f.setSpacing(6)

        tc = QComboBox()
        tc.setStyleSheet(INPUT_STYLE)
        tc.addItem("— выбрать триггер —", None)
        for t in self._triggers:
            tc.addItem(f"🎯 {t.name}", t.id)
        if b.trigger_id:
            for i in range(tc.count()):
                if tc.itemData(i) == b.trigger_id:
                    tc.setCurrentIndex(i)
        tc.currentIndexChanged.connect(lambda: self._set_block_field("trigger_id", tc.currentData()))
        f.addRow("Ждать триггер:", tc)

        timeout_sp = QSpinBox()
        timeout_sp.setStyleSheet(INPUT_STYLE)
        timeout_sp.setRange(0, 300000)
        timeout_sp.setValue(b.wait_timeout_ms)
        timeout_sp.setSuffix(" мс")
        timeout_sp.setToolTip("0 = ждать бесконечно.\n10000 = ждать максимум 10 секунд.")
        timeout_sp.valueChanged.connect(lambda v: self._set_block_field("wait_timeout_ms", v))
        f.addRow("Таймаут:", timeout_sp)

        lay.addLayout(f)
        self._vlay.insertWidget(self._vlay.count() - 1, box)

    def _build_while_trigger(self) -> None:
        b = self._block
        box = self._section("ЦИКЛ: ПОКА ТРИГГЕР АКТИВЕН")
        lay = QVBoxLayout(box)
        lay.setSpacing(8)

        info = QLabel(
            "Действие будет повторяться в цикле,\n"
            "пока выполняется условие триггера.\n"
            "Пример: ПОКА видна кнопка — кликать по ней."
        )
        info.setStyleSheet(
            "background: #3a2a1a; color: #fab387; font-size: 11px; "
            "border-radius: 4px; padding: 8px; border: 1px solid #5a4a2a;"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        f = QFormLayout()
        f.setSpacing(6)

        # Condition mode
        cond_cb = QComboBox()
        cond_cb.setStyleSheet(INPUT_STYLE)
        cond_cb.addItem("ПОКА триггер АКТИВЕН", False)
        cond_cb.addItem("ПОКА триггер НЕ активен", True)
        cond_cb.setCurrentIndex(1 if b.invert else 0)
        cond_cb.setToolTip(
            "АКТИВЕН: повторять пока цвет/объект виден.\n"
            "НЕ активен: повторять пока цвет/объект НЕ появился\n"
            "(например: спамить клавишу пока не появится окно)."
        )
        cond_cb.currentIndexChanged.connect(
            lambda: self._set_block_field("invert", cond_cb.currentData()))
        f.addRow("Условие:", cond_cb)

        tc = QComboBox()
        tc.setStyleSheet(INPUT_STYLE)
        tc.addItem("— выбрать триггер —", None)
        for t in self._triggers:
            tc.addItem(f"🎯 {t.name}", t.id)
        if b.trigger_id:
            for i in range(tc.count()):
                if tc.itemData(i) == b.trigger_id:
                    tc.setCurrentIndex(i)
        tc.currentIndexChanged.connect(lambda: self._set_block_field("trigger_id", tc.currentData()))
        f.addRow("Триггер:", tc)

        delay_sp = QSpinBox()
        delay_sp.setStyleSheet(INPUT_STYLE)
        delay_sp.setRange(20, 60000)
        delay_sp.setValue(b.repeat_delay_ms)
        delay_sp.setSuffix(" мс")
        delay_sp.setToolTip("Пауза между повторами цикла")
        delay_sp.valueChanged.connect(lambda v: self._set_block_field("repeat_delay_ms", v))
        f.addRow("Пауза цикла:", delay_sp)

        max_sp = QSpinBox()
        max_sp.setStyleSheet(INPUT_STYLE)
        max_sp.setRange(0, 999999)
        max_sp.setValue(b.max_repeats)
        max_sp.setSpecialValueText("∞")
        max_sp.setToolTip(
            "Максимум повторов (защита от зацикливания).\n"
            "∞ (0) = пока условие не перестанет выполняться."
        )
        max_sp.valueChanged.connect(lambda v: self._set_block_field("max_repeats", v))
        f.addRow("Макс. повторов:", max_sp)

        lay.addLayout(f)
        self._vlay.insertWidget(self._vlay.count() - 1, box)

        self._build_actions_editor(b, title="ВЫПОЛНЯТЬ КАЖДЫЙ ЦИКЛ ПО ПОРЯДКУ")

    def _build_if_trigger(self) -> None:
        b = self._block
        box1 = self._section("УСЛОВИЕ")
        f1 = QFormLayout(box1)
        tc = QComboBox()
        tc.setStyleSheet(INPUT_STYLE)
        tc.addItem("— выбрать триггер —", None)
        for t in self._triggers:
            tc.addItem(f"🎯 {t.name}", t.id)
        if b.trigger_id:
            for i in range(tc.count()):
                if tc.itemData(i) == b.trigger_id:
                    tc.setCurrentIndex(i)
        tc.currentIndexChanged.connect(lambda: self._set_block_field("trigger_id", tc.currentData()))
        f1.addRow("ЕСЛИ активен:", tc)
        self._vlay.insertWidget(self._vlay.count() - 1, box1)

        self._build_actions_editor(b, title="ТО ВЫПОЛНИТЬ ПО ПОРЯДКУ")

    # ── Action chain editor (if/while blocks) ────────────────────────────────

    def _build_actions_editor(self, block: Block, title: str = "ДЕЙСТВИЯ") -> None:
        # Normalize legacy single action into the chain list
        if not block.actions:
            block.actions = [block.action or Action(type="click_on_trigger")]
            block.action = None
        if self._act_sel_idx >= len(block.actions):
            self._act_sel_idx = 0

        box = self._section(title)
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        self._act_list = QListWidget()
        self._act_list.setStyleSheet(ACTION_LIST_STYLE)
        for i, a in enumerate(block.actions):
            self._act_list.addItem(QListWidgetItem(self._action_summary(a, i)))
        self._act_list.setFixedHeight(
            min(28 * len(block.actions) + 10, 152))
        lay.addWidget(self._act_list)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        add_btn = QPushButton("+ Действие")
        add_btn.setStyleSheet(SMALL_BTN_STYLE)
        add_btn.setToolTip("Добавить ещё одно действие в цепочку")
        add_btn.clicked.connect(self._add_sub_action)
        del_btn = QPushButton("✕")
        del_btn.setStyleSheet(SMALL_BTN_STYLE)
        del_btn.setToolTip("Удалить выбранное действие")
        del_btn.setEnabled(len(block.actions) > 1)
        del_btn.clicked.connect(self._del_sub_action)
        up_btn = QPushButton("↑")
        up_btn.setStyleSheet(SMALL_BTN_STYLE)
        up_btn.clicked.connect(lambda: self._move_sub_action(-1))
        down_btn = QPushButton("↓")
        down_btn.setStyleSheet(SMALL_BTN_STYLE)
        down_btn.clicked.connect(lambda: self._move_sub_action(1))
        btns.addWidget(add_btn, 1)
        btns.addWidget(up_btn)
        btns.addWidget(down_btn)
        btns.addWidget(del_btn)
        lay.addLayout(btns)

        self._vlay.insertWidget(self._vlay.count() - 1, box)

        # Editor for the selected action of the chain
        self._build_action_box(
            block.actions[self._act_sel_idx],
            title=f"НАСТРОЙКА ДЕЙСТВИЯ {self._act_sel_idx + 1}")

        self._act_list.setCurrentRow(self._act_sel_idx)
        self._act_list.currentRowChanged.connect(self._on_sub_action_selected)

    def _action_summary(self, a: Action, idx: int) -> str:
        labels = dict(self._action_types())
        base = labels.get(a.type, a.type)
        extra = ""
        if a.type in ("click_xy", "double_click", "move_mouse"):
            extra = f"  ({a.x}, {a.y})"
        elif a.type == "mouse_hold":
            extra = f"  ({a.x}, {a.y})  {a.hold_ms}мс"
        elif a.type == "drag":
            extra = f"  →({a.x2}, {a.y2})"
        elif a.type == "key_press":
            extra = f"  [{a.key}]"
        elif a.type == "key_hold":
            extra = f"  [{a.key}]  {a.hold_ms}мс"
        elif a.type == "wait":
            extra = f"  {a.ms}мс"
        elif a.type == "random_wait":
            extra = f"  {a.ms}–{a.ms_max}мс"
        elif a.type == "text_type":
            extra = f"  «{a.text[:12]}»"
        return f"{idx + 1}.  {base}{extra}"

    def _refresh_action_item(self) -> None:
        """Update the summary text of the currently edited chain item."""
        b = self._block
        if b is None or not b.actions:
            return
        try:
            lst = getattr(self, "_act_list", None)
            if lst is None:
                return
            i = self._act_sel_idx
            if 0 <= i < lst.count() and i < len(b.actions):
                lst.item(i).setText(self._action_summary(b.actions[i], i))
        except RuntimeError:
            pass  # list widget from a previous rebuild is already deleted

    def _on_sub_action_selected(self, row: int) -> None:
        if row < 0 or row == self._act_sel_idx:
            return
        if self._block is None or not self._block.actions:
            return
        self._act_sel_idx = min(row, len(self._block.actions) - 1)
        self._stop_key_recorder()
        QTimer.singleShot(0, self._rebuild)

    def _add_sub_action(self) -> None:
        b = self._block
        if b is None:
            return
        b.actions.append(Action(type="wait", ms=500))
        self._act_sel_idx = len(b.actions) - 1
        self.block_changed.emit(b)
        QTimer.singleShot(0, self._rebuild)

    def _del_sub_action(self) -> None:
        b = self._block
        if b is None or len(b.actions) <= 1:
            return
        b.actions.pop(self._act_sel_idx)
        self._act_sel_idx = max(0, self._act_sel_idx - 1)
        self.block_changed.emit(b)
        QTimer.singleShot(0, self._rebuild)

    def _move_sub_action(self, delta: int) -> None:
        b = self._block
        if b is None:
            return
        i = self._act_sel_idx
        j = i + delta
        if j < 0 or j >= len(b.actions):
            return
        b.actions[i], b.actions[j] = b.actions[j], b.actions[i]
        self._act_sel_idx = j
        self.block_changed.emit(b)
        QTimer.singleShot(0, self._rebuild)

    # ── Single action editor ─────────────────────────────────────────────────

    def _build_action_box(self, action: Action, title: str = "ДЕЙСТВИЕ") -> None:
        self._edit_action = action
        box = self._section(title)
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        self._action_type_combo = QComboBox()
        self._action_type_combo.setStyleSheet(INPUT_STYLE)
        for val, label in self._action_types():
            self._action_type_combo.addItem(label, val)
        idx = next((i for i, (v, _) in enumerate(self._action_types()) if v == action.type), 0)
        self._action_type_combo.setCurrentIndex(idx)
        lay.addWidget(self._action_type_combo)

        # Container for dynamic params — we replace this widget on type change
        self._params_box_lay = lay
        self._action_params = QWidget()
        self._action_params.setStyleSheet("background: transparent;")
        lay.addWidget(self._action_params)

        self._vlay.insertWidget(self._vlay.count() - 1, box)
        self._fill_action_params()

        # Connect after initial fill to avoid double-fire during setup
        self._action_type_combo.currentIndexChanged.connect(self._on_action_type_change)

    def _action_types(self):
        return [
            ("click_xy",         "🖱  Клик по координатам"),
            ("double_click",     "🖱🖱  Двойной клик"),
            ("mouse_hold",       "🖱⏱  Зажать кнопку мыши"),
            ("click_on_trigger", "🎯  Клик по центру триггера"),
            ("drag",             "✋  Перетащить (drag)"),
            ("key_press",        "⌨  Клавиша / комбинация"),
            ("key_hold",         "⌨⏱  Зажать клавишу"),
            ("text_type",        "📝  Ввести текст"),
            ("move_mouse",       "→  Движение мыши"),
            ("scroll",           "⇕  Прокрутка колесом"),
            ("wait",             "⏱  Пауза (мс)"),
            ("random_wait",      "🎲  Случайная пауза"),
            ("beep",             "🔊  Звуковой сигнал"),
            ("stop_bot",         "🛑  Остановить бота"),
            ("restart_scenario", "🔄  Сценарий заново"),
        ]

    def _on_action_type_change(self, idx: int) -> None:
        val = self._action_type_combo.itemData(idx)
        if self._edit_action is not None:
            self._edit_action.type = val
        self._stop_key_recorder()
        self._replace_action_params()
        self._refresh_action_item()
        if self._block:
            self.block_changed.emit(self._block)

    def _replace_action_params(self) -> None:
        """Safely replace the action params widget to avoid layout crash."""
        if not hasattr(self, "_action_params") or self._action_params is None:
            return
        old = self._action_params
        idx = self._params_box_lay.indexOf(old)

        new = QWidget()
        new.setStyleSheet("background: transparent;")
        if idx >= 0:
            self._params_box_lay.insertWidget(idx, new)
            self._params_box_lay.removeWidget(old)
        old.hide()
        old.deleteLater()
        self._action_params = new
        self._fill_action_params()

    def _fill_action_params(self) -> None:
        """Build fields inside self._action_params based on current action type."""
        a = self._edit_action
        if a is None:
            return

        lay = QFormLayout(self._action_params)
        lay.setSpacing(6)
        lay.setContentsMargins(0, 6, 0, 0)
        atype = a.type

        if atype in ("click_xy", "double_click", "move_mouse", "drag", "mouse_hold"):
            self._x_spin = QSpinBox()
            self._x_spin.setStyleSheet(INPUT_STYLE)
            self._x_spin.setRange(0, 9999)
            self._x_spin.setValue(a.x or 0)
            self._x_spin.valueChanged.connect(lambda v: self._set_action("x", v))

            self._y_spin = QSpinBox()
            self._y_spin.setStyleSheet(INPUT_STYLE)
            self._y_spin.setRange(0, 9999)
            self._y_spin.setValue(a.y or 0)
            self._y_spin.valueChanged.connect(lambda v: self._set_action("y", v))

            xy_row = QHBoxLayout()
            xy_row.setSpacing(6)
            xy_row.addWidget(QLabel("X:"))
            xy_row.addWidget(self._x_spin)
            xy_row.addWidget(QLabel("Y:"))
            xy_row.addWidget(self._y_spin)
            xy_label = "Откуда:" if atype == "drag" else None
            if xy_label:
                lay.addRow(xy_label, xy_row)
            else:
                lay.addRow(xy_row)

            lay.addRow("Захват:" if atype != "drag" else "Захват начала:",
                       self._make_capture_row("xy"))

            if atype == "drag":
                self._x2_spin = QSpinBox()
                self._x2_spin.setStyleSheet(INPUT_STYLE)
                self._x2_spin.setRange(0, 9999)
                self._x2_spin.setValue(a.x2 or 0)
                self._x2_spin.valueChanged.connect(lambda v: self._set_action("x2", v))

                self._y2_spin = QSpinBox()
                self._y2_spin.setStyleSheet(INPUT_STYLE)
                self._y2_spin.setRange(0, 9999)
                self._y2_spin.setValue(a.y2 or 0)
                self._y2_spin.valueChanged.connect(lambda v: self._set_action("y2", v))

                xy2_row = QHBoxLayout()
                xy2_row.setSpacing(6)
                xy2_row.addWidget(QLabel("X:"))
                xy2_row.addWidget(self._x2_spin)
                xy2_row.addWidget(QLabel("Y:"))
                xy2_row.addWidget(self._y2_spin)
                lay.addRow("Куда:", xy2_row)

                lay.addRow("Захват конца:", self._make_capture_row("xy2"))

                dur_sp = QSpinBox()
                dur_sp.setStyleSheet(INPUT_STYLE)
                dur_sp.setRange(50, 10000)
                dur_sp.setValue(a.ms or 300)
                dur_sp.setSuffix(" мс")
                dur_sp.setToolTip("Длительность перетаскивания")
                dur_sp.valueChanged.connect(lambda v: self._set_action("ms", v))
                lay.addRow("Длительность:", dur_sp)

            if atype in ("click_xy", "double_click", "drag", "mouse_hold"):
                btn_cb = QComboBox()
                btn_cb.setStyleSheet(INPUT_STYLE)
                for btn_name in ("left", "right", "middle"):
                    btn_cb.addItem(btn_name)
                btn_cb.setCurrentText(a.button)
                btn_cb.currentTextChanged.connect(lambda v: self._set_action("button", v))
                lay.addRow("Кнопка мыши:", btn_cb)

            if atype == "mouse_hold":
                hold_sp = QSpinBox()
                hold_sp.setStyleSheet(INPUT_STYLE)
                hold_sp.setRange(50, 60000)
                hold_sp.setValue(a.hold_ms)
                hold_sp.setSuffix(" мс")
                hold_sp.setToolTip(
                    "Сколько держать кнопку мыши зажатой.\n"
                    "Пример: зажать ЛКМ на 3000 мс = удерживать 3 секунды\n"
                    "(натянуть лук, копать, держать кнопку прокачки)."
                )
                hold_sp.valueChanged.connect(lambda v: self._set_action("hold_ms", v))
                lay.addRow("Держать:", hold_sp)

            if atype in ("click_xy", "double_click"):
                off_sp = QSpinBox()
                off_sp.setStyleSheet(INPUT_STYLE)
                off_sp.setRange(0, 100)
                off_sp.setValue(a.offset_px)
                off_sp.setSuffix(" px")
                off_sp.setToolTip(
                    "Случайный разброс точки клика (гуманизация).\n"
                    "0 = кликать точно в координату.\n"
                    "5 = кликать в случайную точку ±5 пикселей."
                )
                off_sp.valueChanged.connect(lambda v: self._set_action("offset_px", v))
                lay.addRow("Разброс ±:", off_sp)

        elif atype == "click_on_trigger":
            tc = QComboBox()
            tc.setStyleSheet(INPUT_STYLE)
            tc.addItem("— центр любого активного триггера —", None)
            for t in self._triggers:
                tc.addItem(f"🎯 {t.name}", t.id)
            if a.trigger_id:
                for i in range(tc.count()):
                    if tc.itemData(i) == a.trigger_id:
                        tc.setCurrentIndex(i)
            tc.currentIndexChanged.connect(lambda: self._set_action("trigger_id", tc.currentData()))
            lay.addRow("Триггер:", tc)

            btn_cb = QComboBox()
            btn_cb.setStyleSheet(INPUT_STYLE)
            for btn_name in ("left", "right", "middle"):
                btn_cb.addItem(btn_name)
            btn_cb.setCurrentText(a.button)
            btn_cb.currentTextChanged.connect(lambda v: self._set_action("button", v))
            lay.addRow("Кнопка мыши:", btn_cb)

        elif atype in ("key_press", "key_hold"):
            self._key_edit = QLineEdit(a.key or "")
            self._key_edit.setStyleSheet(INPUT_STYLE)
            if atype == "key_press":
                self._key_edit.setPlaceholderText("a, space, enter, f1, ctrl+a, shift+tab ...")
            else:
                self._key_edit.setPlaceholderText("w, space, shift ...")
            self._key_edit.textChanged.connect(lambda v: self._set_action("key", v))
            lay.addRow("Клавиша:", self._key_edit)

            # Record button
            rec_row = QHBoxLayout()
            self._key_rec_btn = QPushButton("⏺  Захватить нажатие")
            self._key_rec_btn.setStyleSheet(KEY_RECORD_STYLE)
            self._key_rec_btn.setToolTip(
                "Нажмите кнопку, затем нажмите нужную клавишу или комбинацию.\n"
                "Она запишется автоматически."
            )
            self._key_rec_btn.clicked.connect(self._start_key_record)
            self._key_rec_lbl = QLabel("")
            self._key_rec_lbl.setStyleSheet("color: #f9e2af; font-size: 10px;")
            rec_row.addWidget(self._key_rec_btn)
            rec_row.addWidget(self._key_rec_lbl)
            rec_row.addStretch()
            lay.addRow(rec_row)

            if atype == "key_hold":
                hold_sp = QSpinBox()
                hold_sp.setStyleSheet(INPUT_STYLE)
                hold_sp.setRange(50, 60000)
                hold_sp.setValue(a.hold_ms)
                hold_sp.setSuffix(" мс")
                hold_sp.setToolTip("Сколько держать клавишу зажатой.\nНапример W на 2000 мс = идти вперёд 2 сек.")
                hold_sp.valueChanged.connect(lambda v: self._set_action("hold_ms", v))
                lay.addRow("Держать:", hold_sp)
            else:
                hint = QLabel(
                    "Комбо: ctrl+a  ·  shift+tab  ·  ctrl+shift+s\n"
                    "Спец-клавиши: space enter tab esc f1–f12 backspace delete\n"
                    "           win alt ctrl shift"
                )
                hint.setStyleSheet("color: #585b70; font-size: 10px;")
                hint.setWordWrap(True)
                lay.addRow(hint)

        elif atype == "text_type":
            text_ed = QLineEdit(a.text or "")
            text_ed.setStyleSheet(INPUT_STYLE)
            text_ed.setPlaceholderText("Текст для ввода...")
            text_ed.setToolTip(
                "Текст будет напечатан посимвольно.\n"
                "В режиме pydirectinput поддерживается только латиница и цифры."
            )
            text_ed.textChanged.connect(lambda v: self._set_action("text", v))
            lay.addRow("Текст:", text_ed)
            hint = QLabel("⚠ Для игр (pydirectinput): только латиница/цифры")
            hint.setStyleSheet("color: #585b70; font-size: 10px;")
            lay.addRow(hint)

        elif atype == "random_wait":
            lo_sp = QSpinBox()
            lo_sp.setStyleSheet(INPUT_STYLE)
            lo_sp.setRange(0, 300000)
            lo_sp.setValue(a.ms or 500)
            lo_sp.setSuffix(" мс")
            lo_sp.valueChanged.connect(lambda v: self._set_action("ms", v))
            lay.addRow("От:", lo_sp)

            hi_sp = QSpinBox()
            hi_sp.setStyleSheet(INPUT_STYLE)
            hi_sp.setRange(0, 300000)
            hi_sp.setValue(a.ms_max or 1500)
            hi_sp.setSuffix(" мс")
            hi_sp.valueChanged.connect(lambda v: self._set_action("ms_max", v))
            lay.addRow("До:", hi_sp)

            hint = QLabel("Пауза случайной длины — поведение бота менее предсказуемо")
            hint.setStyleSheet("color: #585b70; font-size: 10px;")
            hint.setWordWrap(True)
            lay.addRow(hint)

        elif atype == "scroll":
            sa = QSpinBox()
            sa.setStyleSheet(INPUT_STYLE)
            sa.setRange(-20, 20)
            sa.setValue(a.scroll_amount)
            sa.setToolTip("+N = вверх,  −N = вниз")
            sa.valueChanged.connect(lambda v: self._set_action("scroll_amount", v))
            lay.addRow("Тики (+ вверх / − вниз):", sa)

        elif atype == "wait":
            ms_sp = QSpinBox()
            ms_sp.setStyleSheet(INPUT_STYLE)
            ms_sp.setRange(0, 300000)
            ms_sp.setValue(a.ms or 500)
            ms_sp.setSuffix(" мс")
            ms_sp.valueChanged.connect(lambda v: self._set_action("ms", v))
            lay.addRow("Длительность:", ms_sp)

        elif atype == "beep":
            snd_cb = QComboBox()
            snd_cb.setStyleSheet(INPUT_STYLE)
            snd_cb.addItem("Сигнал (писк)", "beep")
            snd_cb.addItem("Тревога (3 сигнала)", "alarm")
            snd_cb.addItem("Системный звук", "system")
            cur = a.text if a.text in ("beep", "alarm", "system") else "beep"
            for i in range(snd_cb.count()):
                if snd_cb.itemData(i) == cur:
                    snd_cb.setCurrentIndex(i)
            snd_cb.currentIndexChanged.connect(
                lambda: self._set_action("text", snd_cb.currentData()))
            lay.addRow("Звук:", snd_cb)

            dur_sp = QSpinBox()
            dur_sp.setStyleSheet(INPUT_STYLE)
            dur_sp.setRange(50, 5000)
            dur_sp.setValue(a.ms or 300)
            dur_sp.setSuffix(" мс")
            dur_sp.setToolTip("Длительность (только для «Сигнал»)")
            dur_sp.valueChanged.connect(lambda v: self._set_action("ms", v))
            lay.addRow("Длительность:", dur_sp)

            hint = QLabel("Полезно: разбудить вас при редком событии (полу-AFK)")
            hint.setStyleSheet("color: #585b70; font-size: 10px;")
            hint.setWordWrap(True)
            lay.addRow(hint)

        elif atype == "stop_bot":
            hint = QLabel(
                "Бот полностью остановится на этом действии.\n"
                "Используйте в ЕСЛИ-блоке: например,\n"
                "«ЕСЛИ инвентарь полон → остановить бота»."
            )
            hint.setStyleSheet(
                "background: #3a1a1a; color: #f38ba8; font-size: 11px;"
                " border-radius: 4px; padding: 8px; border: 1px solid #5a2a2a;"
            )
            hint.setWordWrap(True)
            lay.addRow(hint)

        elif atype == "restart_scenario":
            hint = QLabel(
                "Сценарий начнётся заново с шага 1\n"
                "(не дожидаясь конца списка блоков).\n"
                "Пример: «ЕСЛИ персонаж умер → сценарий заново»."
            )
            hint.setStyleSheet(
                "background: #1a2a3a; color: #89b4fa; font-size: 11px;"
                " border-radius: 4px; padding: 8px; border: 1px solid #2a4a6a;"
            )
            hint.setWordWrap(True)
            lay.addRow(hint)

    def _make_capture_row(self, target: str) -> QHBoxLayout:
        """Row with two capture buttons routing picked coords to x/y or x2/y2."""
        row = QHBoxLayout()
        row.setSpacing(6)

        cap_preview_btn = QPushButton("📍  Из превью")
        cap_preview_btn.setStyleSheet(CAPTURE_BTN_STYLE)
        cap_preview_btn.setToolTip(
            "Кликните точку в окне Превью.\n"
            "Используйте если нужная точка видна в превью."
        )
        cap_preview_btn.clicked.connect(
            lambda checked=False, t=target: self._request_coords(t, screen=False))
        row.addWidget(cap_preview_btn)

        cap_screen_btn = QPushButton("🖥  С экрана")
        cap_screen_btn.setStyleSheet(CAPTURE_BTN_STYLE)
        cap_screen_btn.setToolTip(
            "Окно спрячется — кликните ЛЮБУЮ точку на экране."
        )
        cap_screen_btn.clicked.connect(
            lambda checked=False, t=target: self._request_coords(t, screen=True))
        row.addWidget(cap_screen_btn)
        return row

    def _request_coords(self, target: str, screen: bool) -> None:
        self._coord_target = target
        if screen:
            self.pick_screen_point_requested.emit()
        else:
            self.pick_coords_requested.emit()

    # ── Key recording ────────────────────────────────────────────────────────

    def _start_key_record(self) -> None:
        if not hasattr(self, "_key_rec_btn"):
            return
        self._key_rec_btn.setText("● Ожидание нажатия...")
        self._key_rec_btn.setEnabled(False)
        if hasattr(self, "_key_rec_lbl"):
            self._key_rec_lbl.setText("Нажмите клавишу или комбо")

        self._key_recorder = KeyRecorder(self._on_key_recorded)
        self._key_recorder.start()

    def _on_key_recorded(self, result: str) -> None:
        self._key_recorder = None
        if not result:
            return
        if self._edit_action is not None:
            self._edit_action.key = result
            if self._block:
                self.block_changed.emit(self._block)
        # Update UI from main thread via QTimer
        QTimer.singleShot(0, lambda: self._apply_recorded_key(result))

    def _apply_recorded_key(self, result: str) -> None:
        self._refresh_action_item()
        if hasattr(self, "_key_edit"):
            self._key_edit.blockSignals(True)
            self._key_edit.setText(result)
            self._key_edit.blockSignals(False)
        if hasattr(self, "_key_rec_btn"):
            self._key_rec_btn.setText("⏺  Захватить нажатие")
            self._key_rec_btn.setEnabled(True)
        if hasattr(self, "_key_rec_lbl"):
            self._key_rec_lbl.setText(f"✓ {result}")

    def _stop_key_recorder(self) -> None:
        if self._key_recorder:
            self._key_recorder.stop()
            self._key_recorder = None

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_header(self, icon: str, title: str) -> QWidget:
        hdr = QWidget()
        hdr.setStyleSheet("background: #181825; border-radius: 6px;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(10, 8, 10, 8)
        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 18px;")
        tl = QLabel(title)
        tl.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: bold;")
        hl.addWidget(ic)
        hl.addWidget(tl)
        hl.addStretch()
        return hdr

    def _set_trigger(self, field: str, value) -> None:
        if self._trigger:
            setattr(self._trigger, field, value)
            self.trigger_changed.emit(self._trigger)

    def _set_action(self, field: str, value) -> None:
        if self._edit_action is not None:
            setattr(self._edit_action, field, value)
            self._refresh_action_item()
            if self._block:
                self.block_changed.emit(self._block)

    def _set_block_field(self, field: str, value) -> None:
        if self._block:
            setattr(self._block, field, value)
            self.block_changed.emit(self._block)

    def _on_label_change(self, text: str) -> None:
        if self._block:
            self._block.label = text
            self.block_changed.emit(self._block)

    def _on_color_range(self, lower: list, upper: list) -> None:
        if self._trigger:
            self._trigger.hsv_lower = lower
            self._trigger.hsv_upper = upper
            self.trigger_changed.emit(self._trigger)


BlockEditorWidget = InspectorWidget
