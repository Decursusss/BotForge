from __future__ import annotations
from typing import Optional
import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QToolBar, QStatusBar, QLabel, QPushButton, QCheckBox,
    QSpinBox, QFileDialog, QMessageBox, QFrame, QComboBox,
    QScrollArea, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

import copy

from ..core.models import BotConfig, Block, Action, Trigger, new_id
from ..core.engine import BotEngine
from ..core.recorder import Recorder
from ..core.storage import save_config, load_config
from ..core.capture import capture_screen
from ..core.vision import (
    check_color_mask, check_template, check_pixel_color, check_change,
)

from .preview_widget import PreviewWidget
from .region_overlay import RegionOverlay, PointPickerOverlay
from .block_list import BlockListWidget
from .block_editor import InspectorWidget
from .trigger_list import TriggerListWidget


# ─── Styles ────────────────────────────────────────────────────────────────

APP_STYLE = """
QMainWindow, QWidget           { background: #1e1e2e; color: #cdd6f4; }
QToolBar                       { background: #181825; border-bottom: 1px solid #313244; padding: 4px 8px; }
QStatusBar                     { background: #11111b; color: #585b70; font-size: 11px; border-top: 1px solid #313244; }
QSplitter::handle              { background: #313244; width: 1px; }
QScrollBar:vertical            { background: #181825; width: 6px; border: none; }
QScrollBar::handle:vertical    { background: #45475a; border-radius: 3px; min-height: 20px; }
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical  { height: 0; }
QPushButton {
    background: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 5px;
    padding: 6px 14px; font-size: 12px;
}
QPushButton:hover  { background: #45475a; color: #fff; }
QPushButton:pressed { background: #181825; }
QPushButton:disabled { color: #45475a; border-color: #313244; }
QCheckBox          { color: #a6adc8; font-size: 11px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #45475a; border-radius: 3px; background: #313244; }
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QLabel             { color: #cdd6f4; }
QSpinBox {
    background: #313244; border: 1px solid #45475a;
    border-radius: 4px; color: #cdd6f4; padding: 3px 6px; font-size: 11px;
}
QComboBox {
    background: #313244; border: 1px solid #45475a;
    border-radius: 4px; color: #cdd6f4; padding: 3px 6px; font-size: 11px;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #313244; color: #cdd6f4;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
}
"""

BTN_RUN  = "background:#1a3a1a; color:#a6e3a1; border:1px solid #2a5a2a; border-radius:5px; padding:6px 18px; font-size:12px; font-weight:bold;"
BTN_STOP = "background:#3a1a1a; color:#f38ba8; border:1px solid #5a2a2a; border-radius:5px; padding:6px 18px; font-size:12px; font-weight:bold;"
BTN_REC  = "background:#3a2a10; color:#f9e2af; border:1px solid #5a4a20; border-radius:5px; padding:6px 14px; font-size:12px;"
BTN_REC_ACTIVE = "background:#5a3010; color:#fab387; border:1px solid #7a5030; border-radius:5px; padding:6px 14px; font-size:12px; font-weight:bold;"


class MainWindow(QMainWindow):
    # Thread-safe bridges: recorder/audio run in worker threads, widgets live here
    _recorded_block_sig = Signal(object)
    _sound_recorded_sig = Signal(str)   # wav path, "" on failure

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BotForge")
        self.resize(1300, 820)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(APP_STYLE)

        self._config = BotConfig()
        self._current_file: Optional[str] = None
        self._engine: Optional[BotEngine] = None
        self._recorder: Optional[Recorder] = None
        self._recording = False
        self._overlay_target = "preview"   # "preview" | "trigger" | "template"
        self._point_target = "coords"      # "coords" | "pixel"

        # Region overlay (select area)
        self._overlay = RegionOverlay()
        self._overlay.region_selected.connect(self._on_region_done)
        self._overlay.cancelled.connect(self._on_overlay_cancelled)

        # Point picker overlay (pick single screen coordinate)
        self._point_picker = PointPickerOverlay()
        self._point_picker.point_picked.connect(self._on_screen_point_picked)
        self._point_picker.cancelled.connect(self._on_overlay_cancelled)

        self._build_ui()
        self._connect_signals()
        self._recorded_block_sig.connect(self._on_recorded_block)
        self._sound_recorded_sig.connect(self._on_sound_recorded)

    # ─── Build UI ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.addToolBar(self._make_toolbar())

        # Main 3-panel splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # LEFT: triggers + settings
        left = self._make_left_panel()
        left.setMinimumWidth(240)
        left.setMaximumWidth(340)
        splitter.addWidget(left)

        # CENTER: sequence
        self._block_list = BlockListWidget()
        splitter.addWidget(self._block_list)

        # RIGHT: preview + inspector
        right = self._make_right_panel()
        right.setMinimumWidth(420)
        right.setMaximumWidth(620)
        splitter.addWidget(right)

        splitter.setSizes([210, 560, 340])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        self.setCentralWidget(splitter)
        self._make_statusbar()

    def _make_toolbar(self) -> QToolBar:
        tb = QToolBar()
        tb.setMovable(False)

        def btn(text, tip, slot, style=None):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            if style:
                b.setStyleSheet(style)
            tb.addWidget(b)
            return b

        btn("🗋 Новый",    "Новый проект (Ctrl+N)",    self._act_new)
        btn("📂 Открыть",  "Открыть проект (Ctrl+O)",  self._act_open)
        self._save_btn = btn("💾 Сохранить", "Сохранить проект (Ctrl+S)", self._act_save)
        tb.addSeparator()

        self._rec_btn = QPushButton("⏺ Запись")
        self._rec_btn.setToolTip("Записать клики и клавиши в блоки")
        self._rec_btn.setStyleSheet(BTN_REC)
        self._rec_btn.clicked.connect(self._toggle_recording)
        tb.addWidget(self._rec_btn)
        tb.addSeparator()

        self._run_btn = QPushButton("▶ Запустить")
        self._run_btn.setStyleSheet(BTN_RUN)
        self._run_btn.setToolTip("Запустить бота (F5)")
        self._run_btn.clicked.connect(self._act_run)
        tb.addWidget(self._run_btn)

        self._stop_btn = QPushButton("■ Стоп")
        self._stop_btn.setStyleSheet(BTN_STOP)
        self._stop_btn.setToolTip("Остановить бота (F12 — аварийный стоп)")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._act_stop)
        tb.addWidget(self._stop_btn)

        tb.addSeparator()

        # Project name
        tb.addWidget(QLabel("  Проект: "))
        self._proj_lbl = QLabel("Новый бот")
        self._proj_lbl.setStyleSheet("color: #89b4fa; font-size: 12px; font-weight: bold;")
        tb.addWidget(self._proj_lbl)

        return tb

    def _make_left_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #181825;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Trigger list (grows)
        self._trigger_list = TriggerListWidget()
        lay.addWidget(self._trigger_list, 1)

        # Settings section
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        lay.addWidget(sep)

        settings = QWidget()
        settings.setStyleSheet("background: #181825;")
        sl = QVBoxLayout(settings)
        sl.setContentsMargins(10, 10, 10, 10)
        sl.setSpacing(8)

        hdr = QLabel("НАСТРОЙКИ")
        hdr.setStyleSheet("color: #585b70; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        sl.addWidget(hdr)

        self._loop_cb = QCheckBox("Повторять сценарий")
        self._loop_cb.setChecked(True)
        sl.addWidget(self._loop_cb)

        delay_row = QHBoxLayout()
        delay_lbl = QLabel("Задержка:")
        delay_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self._delay_sp = QSpinBox()
        self._delay_sp.setRange(0, 10000)
        self._delay_sp.setValue(50)
        self._delay_sp.setSuffix(" мс")
        self._delay_sp.setToolTip("Задержка между итерациями цикла")
        delay_row.addWidget(delay_lbl)
        delay_row.addWidget(self._delay_sp)
        sl.addLayout(delay_row)

        iters_row = QHBoxLayout()
        iters_lbl = QLabel("Повторы:")
        iters_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self._iters_sp = QSpinBox()
        self._iters_sp.setRange(0, 999999)
        self._iters_sp.setValue(0)
        self._iters_sp.setSpecialValueText("∞")
        self._iters_sp.setToolTip("Сколько раз повторить сценарий.\n∞ (0) = бесконечно, до остановки.")
        iters_row.addWidget(iters_lbl)
        iters_row.addWidget(self._iters_sp)
        sl.addLayout(iters_row)

        backend_row = QHBoxLayout()
        backend_lbl = QLabel("Ввод:")
        backend_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self._backend_cb = QComboBox()
        self._backend_cb.addItem("pydirectinput", "pydirectinput")
        self._backend_cb.addItem("pyautogui", "pyautogui")
        self._backend_cb.setToolTip("pydirectinput работает в большинстве игр")
        backend_row.addWidget(backend_lbl)
        backend_row.addWidget(self._backend_cb)
        sl.addLayout(backend_row)

        lay.addWidget(settings)
        return w

    def _make_right_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #1e1e2e;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Vertical splitter: preview (top) | inspector (bottom)
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setHandleWidth(4)
        v_split.setStyleSheet("QSplitter::handle { background: #313244; }")

        # ── Preview section ──────────────────────────────────────────
        prev_container = QWidget()
        prev_container.setStyleSheet("background: #181825;")
        pc_lay = QVBoxLayout(prev_container)
        pc_lay.setContentsMargins(0, 0, 0, 0)
        pc_lay.setSpacing(0)

        prev_hdr = QWidget()
        prev_hdr.setStyleSheet("background: #181825; border-bottom: 1px solid #313244;")
        ph = QHBoxLayout(prev_hdr)
        ph.setContentsMargins(10, 4, 10, 4)
        prev_title = QLabel("ПРЕВЬЮ")
        prev_title.setStyleSheet("color: #585b70; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        self._preview_status = QLabel("")
        self._preview_status.setStyleSheet("color: #45475a; font-size: 10px;")

        prev_region_btn = QPushButton("📐 Область")
        prev_region_btn.setStyleSheet("""
            QPushButton {
                background: #313244; color: #89b4fa;
                border: 1px solid #45475a; border-radius: 4px;
                padding: 2px 8px; font-size: 10px;
            }
            QPushButton:hover { background: #45475a; }
        """)
        prev_region_btn.setToolTip(
            "Выбрать область экрана для превью.\n"
            "Не привязана к триггеру — просто наблюдение.\n"
            "Выделите окно игры/программы чтобы видеть его здесь."
        )
        prev_region_btn.clicked.connect(self._open_preview_region_overlay)

        ph.addWidget(prev_title)
        ph.addStretch()
        ph.addWidget(self._preview_status)
        ph.addSpacing(6)
        ph.addWidget(prev_region_btn)
        pc_lay.addWidget(prev_hdr)

        self._preview = PreviewWidget()
        self._preview.setMinimumHeight(120)
        self._preview.pixel_picked.connect(self._on_pixel_picked)
        self._preview.coords_picked.connect(self._on_coords_picked)
        pc_lay.addWidget(self._preview, 1)

        v_split.addWidget(prev_container)

        # ── Inspector section ────────────────────────────────────────
        self._inspector = InspectorWidget()
        self._inspector.block_changed.connect(self._on_block_changed)
        self._inspector.trigger_changed.connect(self._on_trigger_changed)
        self._inspector.pick_region_requested.connect(self._open_region_overlay)
        self._inspector.pick_color_requested.connect(self._on_pick_color)
        self._inspector.pick_coords_requested.connect(self._on_pick_coords)
        self._inspector.pick_screen_point_requested.connect(self._open_point_picker)
        self._inspector.pick_template_requested.connect(self._open_template_overlay)
        self._inspector.pick_pixel_requested.connect(self._open_pixel_picker)
        self._inspector.record_sound_requested.connect(self._on_record_sound)
        self._inspector.test_trigger_requested.connect(self._on_test_trigger)
        v_split.addWidget(self._inspector)

        # Default split: 300px preview, rest for inspector
        v_split.setSizes([280, 480])
        v_split.setStretchFactor(0, 0)
        v_split.setStretchFactor(1, 1)

        lay.addWidget(v_split, 1)
        return w

    def _make_statusbar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #45475a;")
        self._status_text = QLabel("Готов")
        self._status_text.setStyleSheet("color: #585b70; font-size: 11px;")

        sep1 = QLabel("|")
        sep1.setStyleSheet("color: #313244;")

        self._hotkey_lbl = QLabel("F12 = аварийный стоп")
        self._hotkey_lbl.setStyleSheet("color: #89b4fa; font-size: 11px;")

        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #313244;")

        self._log_lbl = QLabel("")
        self._log_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")

        bar.addWidget(self._status_dot)
        bar.addWidget(self._status_text)
        bar.addWidget(sep1)
        bar.addWidget(self._hotkey_lbl)
        bar.addWidget(sep2)
        bar.addWidget(self._log_lbl, 1)

    # ─── Connect signals ────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._trigger_list.add_requested.connect(self._on_add_trigger)
        self._trigger_list.trigger_selected.connect(self._on_trigger_selected)
        self._trigger_list.trigger_deleted.connect(self._on_trigger_deleted)

        self._block_list.add_block_requested.connect(self._on_add_block)
        self._block_list.block_selected.connect(self._on_block_selected)
        self._block_list.block_deleted.connect(self._on_block_deleted)
        self._block_list.block_duplicated.connect(self._on_block_duplicated)
        self._block_list.blocks_reordered.connect(self._on_reorder)

        self._loop_cb.toggled.connect(lambda v: setattr(self._config, "loop", v))
        self._delay_sp.valueChanged.connect(lambda v: setattr(self._config, "loop_delay_ms", v))
        self._iters_sp.valueChanged.connect(lambda v: setattr(self._config, "max_iterations", v))

    # ─── Trigger management ─────────────────────────────────────────────────

    def _on_add_trigger(self) -> None:
        n = len(self._config.triggers) + 1
        t = Trigger(name=f"Триггер {n}")
        self._config.triggers.append(t)
        self._trigger_list.add_trigger(t)
        # Auto-select
        self._trigger_list._on_card_selected(t.id)

    def _on_trigger_selected(self, tid: str) -> None:
        t = self._find_trigger(tid)
        if not t:
            return
        self._inspector.set_triggers(self._config.triggers)
        self._inspector.load_trigger(t)
        # Update preview to show trigger region
        self._preview.set_region(tuple(t.region))
        if t.type == "color_mask":
            self._preview.set_mask_params(t.hsv_lower, t.hsv_upper, show=True)
        else:
            self._preview.clear_mask()
        self._preview_status.setText(f"Область: {t.region[2]}×{t.region[3]} px")

    def _on_trigger_deleted(self, tid: str) -> None:
        self._config.triggers = [t for t in self._config.triggers if t.id != tid]
        self._inspector.set_triggers(self._config.triggers)
        self._inspector.clear_if_trigger(tid)

    def _on_trigger_changed(self, trigger: Trigger) -> None:
        self._trigger_list.update_trigger(trigger)
        # Keep preview in sync
        self._preview.set_region(tuple(trigger.region))
        if trigger.type == "color_mask":
            self._preview.set_mask_params(trigger.hsv_lower, trigger.hsv_upper, show=True)
        else:
            self._preview.clear_mask()
        self._preview_status.setText(f"Область: {trigger.region[2]}×{trigger.region[3]} px")

    # ─── Block management ───────────────────────────────────────────────────

    def _on_add_block(self, btype: str) -> None:
        b = Block(type=btype)
        if btype == "wait":
            b.action = Action(type="wait", ms=500)
        elif btype == "action":
            b.action = Action(type="click_xy", x=0, y=0)
        elif btype == "if_trigger":
            b.action = Action(type="click_on_trigger")
        elif btype == "while_trigger":
            b.action = Action(type="click_on_trigger")
            b.repeat_delay_ms = 200
        elif btype == "wait_trigger":
            b.wait_timeout_ms = 10000
        self._config.blocks.append(b)
        self._block_list.add_block(b)
        self._block_list._list.setCurrentRow(self._block_list._list.count() - 1)

    def _on_block_selected(self, bid: str) -> None:
        b = self._find_block(bid)
        if b:
            self._inspector.set_triggers(self._config.triggers)
            self._inspector.load_block(b)

    def _on_block_deleted(self, bid: str) -> None:
        self._config.blocks = [b for b in self._config.blocks if b.id != bid]
        self._block_list.remove_block(bid)
        self._inspector.clear_if_block(bid)

    def _on_block_duplicated(self, bid: str) -> None:
        b = self._find_block(bid)
        if not b:
            return
        nb = copy.deepcopy(b)
        nb.id = new_id()
        idx = self._config.blocks.index(b)
        self._config.blocks.insert(idx + 1, nb)
        self._block_list.insert_block(nb, idx + 1)
        self._log(f"Блок продублирован: {nb.display_label()}")

    def _on_block_changed(self, block: Block) -> None:
        self._block_list.update_block(block)

    def _on_reorder(self, order: list) -> None:
        id_map = {b.id: b for b in self._config.blocks}
        self._config.blocks = [id_map[bid] for bid in order if bid in id_map]

    # ─── Region overlay ─────────────────────────────────────────────────────

    def _open_region_overlay(self) -> None:
        self._overlay_target = "trigger"
        self._log("Прячу окно… выберите область на экране")
        self.hide()
        QTimer.singleShot(350, self._show_overlay)

    def _open_preview_region_overlay(self) -> None:
        self._overlay_target = "preview"
        self._log("Прячу окно… выделите область для превью (окно игры/программы)")
        self.hide()
        QTimer.singleShot(350, self._show_overlay)

    def _open_template_overlay(self) -> None:
        self._overlay_target = "template"
        self._log("Прячу окно… обведите рамкой картинку-образец")
        self.hide()
        QTimer.singleShot(350, self._show_overlay)

    def _show_overlay(self) -> None:
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()

    def _on_region_done(self, x: int, y: int, w: int, h: int) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        if self._overlay_target == "trigger":
            self._inspector.update_trigger_region(x, y, w, h)
        elif self._overlay_target == "template":
            self._save_template_capture(x, y, w, h)
        else:
            # Standalone preview region — no trigger needed
            self._preview.set_region((x, y, w, h))
            self._preview.clear_mask()
            self._preview_status.setText(f"Превью: {w}×{h} px")
            self._log(f"Область превью установлена: {w}×{h}")

    def _save_template_capture(self, x: int, y: int, w: int, h: int) -> None:
        trigger = self._inspector.current_trigger()
        if trigger is None:
            self._log("Образец: триггер не выбран")
            return
        frame = capture_screen((x, y, w, h))
        if frame is None or frame.size == 0:
            self._log("Образец: не удалось захватить экран")
            return
        try:
            import cv2
            import numpy as np
            tpl_dir = os.path.join(os.path.expanduser("~"), ".botforge", "templates")
            os.makedirs(tpl_dir, exist_ok=True)
            path = os.path.join(tpl_dir, f"{trigger.id}.png")
            ok, buf = cv2.imencode(".png", frame)
            if not ok:
                self._log("Образец: ошибка кодирования PNG")
                return
            buf.tofile(path)  # unicode-safe write (cv2.imwrite fails on non-ASCII paths)
        except Exception as e:
            self._log(f"Образец: ошибка сохранения ({e})")
            return
        self._inspector.set_template_path(path)
        self._log(f"Образец сохранён: {w}×{h} px")

    def _on_overlay_cancelled(self) -> None:
        self.show()
        self.raise_()

    def _open_point_picker(self) -> None:
        self._point_target = "coords"
        self._log("Прячу окно… кликните на нужную точку на экране")
        self.hide()
        QTimer.singleShot(350, self._show_point_picker)

    def _open_pixel_picker(self) -> None:
        self._point_target = "pixel"
        self._log("Прячу окно… кликните на нужный пиксель")
        self.hide()
        QTimer.singleShot(350, self._show_point_picker)

    def _show_point_picker(self) -> None:
        self._point_picker.show()
        self._point_picker.raise_()
        self._point_picker.activateWindow()

    def _on_screen_point_picked(self, x: int, y: int) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        if self._point_target == "pixel":
            frame = capture_screen((x, y, 1, 1))
            if frame is None or frame.size == 0:
                self._log("Не удалось прочитать цвет пикселя")
                return
            b, g, r = (int(v) for v in frame[0, 0][:3])
            self._inspector.update_pixel(x, y, r, g, b)
            self._log(f"Пиксель: ({x}, {y})  RGB({r},{g},{b})")
            self._preview_status.setText(f"Пиксель ({x}, {y}) RGB({r},{g},{b})")
        else:
            self._inspector.on_coords_picked(x, y)
            self._log(f"Координаты захвачены: ({x}, {y})")
            self._preview_status.setText(f"Координаты: ({x}, {y})")
        self._point_target = "coords"

    # ─── Color / Coord pick ─────────────────────────────────────────────────

    def _on_pick_color(self) -> None:
        self._preview.enable_pixel_pick(True)
        self._log("Кликните на нужный цвет в превью")
        self._preview_status.setText("Кликните на цвет в превью...")

    def _on_pixel_picked(self, b: int, g: int, r: int) -> None:
        self._inspector.on_pixel_picked(b, g, r)
        self._preview_status.setText(f"Цвет захвачен: RGB({r},{g},{b})")

    def _on_pick_coords(self) -> None:
        self._preview.enable_coord_pick(True)
        self._log("Кликните на точку в превью для захвата координат →")
        self._preview_status.setText("Кликните на точку в превью...")

    def _on_coords_picked(self, ax: int, ay: int) -> None:
        self._inspector.on_coords_picked(ax, ay)
        self._log(f"Координаты: ({ax}, {ay})")
        self._preview_status.setText(f"Координаты: ({ax}, {ay})")

    # ─── Sound recording ────────────────────────────────────────────────────

    def _on_record_sound(self, seconds: int) -> None:
        trigger = self._inspector.current_trigger()
        if trigger is None:
            return
        self._log(f"⏺ Запись звука {seconds} сек — воспроизведите звук СЕЙЧАС...")
        self._preview_status.setText(f"⏺ Запись {seconds} сек...")
        tid = trigger.id

        def work():
            try:
                from ..core.audio import record_sample, trim_silence, save_wav
                data = record_sample(seconds)
                if data is None or len(data) == 0:
                    self._sound_recorded_sig.emit("")
                    return
                data = trim_silence(data)
                if len(data) < 1600:  # < 0.1 s of actual sound
                    self._sound_recorded_sig.emit("")
                    return
                snd_dir = os.path.join(os.path.expanduser("~"), ".botforge", "sounds")
                os.makedirs(snd_dir, exist_ok=True)
                path = os.path.join(snd_dir, f"{tid}.wav")
                save_wav(path, data)
                self._sound_recorded_sig.emit(path)
            except Exception:
                self._sound_recorded_sig.emit("")

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _on_sound_recorded(self, path: str) -> None:
        if not path:
            self._log("Не удалось записать звук — был ли звук во время записи?")
            self._preview_status.setText("Запись не удалась")
            return
        self._inspector.set_sound_path(path)
        self._log("✔ Звук записан, тишина по краям обрезана")
        self._preview_status.setText("Образец звука сохранён")

    # ─── Trigger testing ────────────────────────────────────────────────────

    def _on_test_trigger(self, trigger) -> None:
        if trigger is None:
            return

        # Sound trigger: listen for a few seconds, no region required
        if trigger.type == "sound":
            self._test_sound_trigger(trigger)
            return

        # Pixel trigger: no region required, checks its own coords
        if trigger.type == "pixel":
            if trigger.pixel_x <= 0 and trigger.pixel_y <= 0:
                self._inspector.show_test_result(False, None, None)
                self._log("Проверка: пиксель не выбран")
                return
            frame = capture_screen((trigger.pixel_x, trigger.pixel_y, 1, 1))
            fired = frame is not None and check_pixel_color(
                frame, trigger.pixel_rgb, trigger.pixel_tolerance)
            cx = trigger.pixel_x - trigger.region[0]
            cy = trigger.pixel_y - trigger.region[1]
            self._finish_test(trigger, fired, cx if fired else None, cy if fired else None)
            return

        if trigger.region[2] <= 0 or trigger.region[3] <= 0:
            self._inspector.show_test_result(False, None, None)
            self._log("Проверка: область триггера не выбрана")
            return
        frame = capture_screen(tuple(trigger.region))
        if frame is None:
            self._inspector.show_test_result(False, None, None)
            self._log("Проверка: не удалось захватить экран")
            return
        fired, cx, cy = False, None, None
        if trigger.type == "color_mask":
            fired, cx, cy, _ = check_color_mask(
                frame, trigger.hsv_lower, trigger.hsv_upper, trigger.min_match_ratio
            )
        elif trigger.type == "template" and trigger.template_path:
            try:
                import cv2
                import numpy as np
                data = np.fromfile(trigger.template_path, dtype=np.uint8)
                tmpl = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if tmpl is not None:
                    fired, cx, cy = check_template(frame, tmpl, trigger.template_threshold)
            except Exception:
                pass
        elif trigger.type == "change":
            # Two captures ~350ms apart: change needs a "before" and "after"
            import time as _time
            self._log("Проверка движения: сравниваю два кадра (350 мс)...")
            _time.sleep(0.35)
            frame2 = capture_screen(tuple(trigger.region))
            fired, cx, cy, _ = check_change(frame2, frame, trigger.min_match_ratio)
        self._finish_test(trigger, fired, cx, cy)

    def _test_sound_trigger(self, trigger) -> None:
        import time as _time
        try:
            from ..core.audio import AudioMonitor, match_audio, load_wav, AUDIO_OK
        except Exception:
            AUDIO_OK = False
        if not AUDIO_OK:
            self._inspector.show_test_result(False, None, None)
            self._log("Проверка: пакет soundcard не установлен")
            return

        template = None
        if trigger.sound_mode == "match":
            if not trigger.sound_path or not os.path.exists(trigger.sound_path):
                self._inspector.show_test_result(False, None, None)
                self._log("Проверка: образец звука не записан")
                return
            template = load_wav(trigger.sound_path)
            if template is None:
                self._inspector.show_test_result(False, None, None)
                self._log("Проверка: не удалось прочитать образец")
                return

        mon = AudioMonitor()
        if not mon.start():
            self._inspector.show_test_result(False, None, None)
            self._log("Проверка: не удалось запустить захват звука")
            return

        self._log("🎧 Слушаю 4 секунды — воспроизведите звук...")
        self._preview_status.setText("🎧 Слушаю 4 сек...")
        fired = False
        deadline = _time.monotonic() + 4.0
        while _time.monotonic() < deadline:
            QApplication.processEvents()
            _time.sleep(0.1)
            try:
                if trigger.sound_mode == "level":
                    if mon.current_level() >= trigger.sound_level:
                        fired = True
                        break
                else:
                    score = match_audio(mon.get_buffer(), template)
                    if score >= trigger.sound_threshold:
                        fired = True
                        break
            except Exception:
                break
        mon.stop()
        self._finish_test(trigger, fired, None, None)

    def _finish_test(self, trigger, fired: bool, cx, cy) -> None:
        self._inspector.show_test_result(fired, cx, cy)
        if fired:
            self._log(f"Проверка: триггер '{trigger.name}' СРАБОТАЛ ({cx},{cy})")
            self._trigger_list.set_active(trigger.id, True)
            QTimer.singleShot(1500, lambda: self._trigger_list.set_active(trigger.id, False))
            # Show the match location on the preview
            if cx is not None and cy is not None and trigger.region[2] > 0:
                self._preview.set_region(tuple(trigger.region))
                if trigger.type == "color_mask":
                    self._preview.set_mask_params(
                        trigger.hsv_lower, trigger.hsv_upper, show=True)
                else:
                    self._preview.clear_mask()
                self._preview.show_match_marker(cx, cy)
                abs_x = trigger.region[0] + cx
                abs_y = trigger.region[1] + cy
                self._preview_status.setText(
                    f"Найдено: ({abs_x}, {abs_y}) на экране")
        else:
            self._log(f"Проверка: триггер '{trigger.name}' не сработал")
            self._preview_status.setText("Совпадение не найдено")

    # ─── Engine ─────────────────────────────────────────────────────────────

    def _act_run(self) -> None:
        if not self._config.blocks:
            QMessageBox.information(self, "Пусто",
                "Сценарий пуст. Добавьте хотя бы один блок.")
            return
        if self._engine and self._engine.isRunning():
            return
        self._engine = BotEngine(self)
        self._engine.set_config(self._config)
        self._engine.set_backend(self._backend_cb.currentData())
        self._engine.block_activated.connect(self._on_block_activated)
        self._engine.block_step.connect(self._block_list.set_step)
        self._engine.iteration_changed.connect(self._block_list.set_iteration)
        self._engine.trigger_fired.connect(self._on_trigger_fired)
        self._engine.trigger_match.connect(self._on_trigger_match)
        self._engine.log_message.connect(self._log)
        self._engine.engine_stopped.connect(self._on_stopped)
        self._engine.start_hotkey()
        self._engine.start()
        self._set_running(True)

    def _act_stop(self) -> None:
        if self._engine:
            self._engine.stop()

    def _on_block_activated(self, bid: str) -> None:
        self._block_list.highlight_block(bid)
        b = self._find_block(bid)
        if b:
            self._log(f"▶  {b.display_label()}")

    def _on_trigger_fired(self, tid: str) -> None:
        self._trigger_list.set_active(tid, True)
        QTimer.singleShot(400, lambda: self._trigger_list.set_active(tid, False))

    def _on_trigger_match(self, tid: str, cx: int, cy: int) -> None:
        # Show marker only if preview is looking at this trigger's region,
        # otherwise the marker position would be meaningless
        t = self._find_trigger(tid)
        if t and self._preview.current_region() == tuple(t.region):
            self._preview.show_match_marker(cx, cy, duration_ms=1500)

    def _on_stopped(self) -> None:
        if self._engine:
            self._engine.stop_hotkey()
        self._block_list.clear_highlights()
        self._trigger_list.clear_active()
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._block_list.set_enabled_add(not running)
        if running:
            self._status_dot.setStyleSheet("color: #a6e3a1;")
            self._status_text.setText("Работает")
            self._status_text.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        else:
            self._status_dot.setStyleSheet("color: #45475a;")
            self._status_text.setText("Готов")
            self._status_text.setStyleSheet("color: #585b70; font-size: 11px;")

    # ─── Recording ──────────────────────────────────────────────────────────

    def _toggle_recording(self) -> None:
        if self._recording:
            self._recording = False
            if self._recorder:
                self._recorder.stop()
                self._recorder = None
            self._rec_btn.setText("⏺ Запись")
            self._rec_btn.setStyleSheet(BTN_REC)
            self._log("Запись остановлена")
        else:
            self._recording = True
            self._rec_btn.setText("⏹ Стоп записи")
            self._rec_btn.setStyleSheet(BTN_REC_ACTIVE)
            self._recorder = Recorder(self._recorded_block_sig.emit)
            self._recorder.start()
            self._log("● Запись... кликайте и нажимайте клавиши")

    def _on_recorded_block(self, block: Block) -> None:
        # Ignore clicks on the BotForge window itself (e.g. the stop button)
        a = block.action
        if a and a.type == "click_xy" and a.x is not None and self.isVisible():
            ratio = self.devicePixelRatio() or 1.0
            geo = self.frameGeometry()
            if geo.contains(int(a.x / ratio), int(a.y / ratio)):
                return
        self._config.blocks.append(block)
        self._block_list.add_block(block)

    # ─── File ops ───────────────────────────────────────────────────────────

    def _act_new(self) -> None:
        if not self._confirm_close():
            return
        self._config = BotConfig()
        self._current_file = None
        self._block_list.clear_all()
        self._trigger_list.clear_all()
        self._loop_cb.setChecked(True)
        self._delay_sp.setValue(50)
        self._iters_sp.setValue(0)
        self._inspector.set_triggers([])
        self._inspector.clear_selection()
        self._preview.set_region(None)
        self._preview.clear_mask()
        self._proj_lbl.setText("Новый бот")
        self.setWindowTitle("BotForge")
        self._log("Новый проект создан")

    def _act_open(self) -> None:
        if not self._confirm_close():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть проект", "",
            "BotForge (*.json);;Все файлы (*)")
        if not path:
            return
        try:
            cfg = load_config(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки", str(e))
            return
        self._load_config(cfg, path)

    def _act_save(self) -> None:
        if not self._current_file:
            path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить проект",
                f"{self._config.name}.json",
                "BotForge (*.json);;Все файлы (*)")
            if not path:
                return
            self._current_file = path
        try:
            save_config(self._config, self._current_file)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return
        fname = os.path.basename(self._current_file)
        self._log(f"Сохранено: {fname}")

    def _load_config(self, cfg: BotConfig, path: str) -> None:
        self._config = cfg
        self._current_file = path
        self._block_list.clear_all()
        self._trigger_list.clear_all()
        self._inspector.clear_selection()
        for t in cfg.triggers:
            self._trigger_list.add_trigger(t)
        for b in cfg.blocks:
            self._block_list.add_block(b)
        self._loop_cb.setChecked(cfg.loop)
        self._delay_sp.setValue(cfg.loop_delay_ms)
        self._iters_sp.setValue(cfg.max_iterations)
        name = os.path.splitext(os.path.basename(path))[0]
        self._proj_lbl.setText(name)
        self.setWindowTitle(f"BotForge — {name}")
        self._inspector.set_triggers(cfg.triggers)
        self._log(f"Открыт: {os.path.basename(path)}")

    def _confirm_close(self) -> bool:
        if not (self._config.blocks or self._config.triggers):
            return True
        r = QMessageBox.question(
            self, "Сохранить проект?",
            "Текущий проект будет закрыт. Сохранить изменения?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        if r == QMessageBox.StandardButton.Save:
            self._act_save()
            return True
        return r == QMessageBox.StandardButton.Discard

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _find_trigger(self, tid: str) -> Optional[Trigger]:
        return next((t for t in self._config.triggers if t.id == tid), None)

    def _find_block(self, bid: str) -> Optional[Block]:
        return next((b for b in self._config.blocks if b.id == bid), None)

    def _log(self, msg: str) -> None:
        self._log_lbl.setText(msg)

    def keyPressEvent(self, event) -> None:
        from PySide6.QtCore import Qt
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if ctrl and key == Qt.Key.Key_S:
            self._act_save()
        elif ctrl and key == Qt.Key.Key_O:
            self._act_open()
        elif ctrl and key == Qt.Key.Key_N:
            self._act_new()
        elif key == Qt.Key.Key_F5:
            self._act_run()
        elif key == Qt.Key.Key_F12:
            self._act_stop()
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._engine and self._engine.isRunning():
            self._engine.stop()
            self._engine.wait(2000)
        if self._recorder:
            self._recorder.stop()
        event.accept()
