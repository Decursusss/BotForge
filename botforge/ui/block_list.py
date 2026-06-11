from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QAbstractItemView, QListWidget, QListWidgetItem,
    QFrame, QSizePolicy, QMenu
)
from PySide6.QtCore import Signal, Qt, QSize, QPoint
from PySide6.QtGui import QFont, QColor, QKeySequence

from ..core.models import Block

BLOCK_ICONS = {
    "wait":          "⏱",
    "action":        "▶",
    "if_trigger":    "⚡",
    "wait_trigger":  "⏳",
    "while_trigger": "🔁",
}
BLOCK_COLORS = {
    "wait":          "#2d4a6a",
    "action":        "#1e3a5e",
    "if_trigger":    "#3a2a5e",
    "wait_trigger":  "#1a3a2a",
    "while_trigger": "#3a2a1a",
}

BLOCK_LIST_STYLE = """
QListWidget {
    background: #181825;
    border: none;
    outline: none;
}
QListWidget::item {
    background: #1e2030;
    border: 1px solid #313244;
    border-radius: 6px;
    margin: 2px 4px;
    padding: 8px 10px;
    color: #cdd6f4;
    font-size: 12px;
}
QListWidget::item:selected {
    background: #1e3050;
    border: 1px solid #89b4fa;
    color: #cdd6f4;
}
QListWidget::item:hover:!selected {
    background: #252535;
    border: 1px solid #45475a;
}
"""

ADD_BTN_STYLE = """
QPushButton {
    background: #1e2030;
    color: #a6adc8;
    border: 1px solid #313244;
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 11px;
}
QPushButton:hover {
    background: #252540;
    color: #cdd6f4;
    border-color: #585b70;
}
"""

DEL_BTN_STYLE = """
QPushButton {
    background: #3a1a1a;
    color: #f38ba8;
    border: 1px solid #5a2a2a;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 11px;
}
QPushButton:hover {
    background: #5a2a2a;
    color: #ff9cad;
}
QPushButton:disabled {
    color: #45475a; border-color: #313244; background: #1e2030;
}
"""

ACTIVE_ITEM_BG = "#1a3a1a"
ACTIVE_ITEM_BORDER = "#a6e3a1"


class BlockListWidget(QWidget):
    block_selected   = Signal(str)
    block_deleted    = Signal(str)
    block_duplicated = Signal(str)
    blocks_reordered = Signal(list)
    add_block_requested = Signal(str)  # block_type

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Header ───────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background: #181825;")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(8, 8, 8, 8)
        hl.setSpacing(6)

        title_row = QHBoxLayout()
        title = QLabel("СЦЕНАРИЙ")
        title.setStyleSheet("color: #585b70; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        self._step_lbl = QLabel("")
        self._step_lbl.setStyleSheet(
            "color: #a6e3a1; font-size: 11px; font-weight: bold; padding: 2px 6px;"
            " background: #1a3a1a; border-radius: 4px;"
        )
        self._step_lbl.hide()
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self._step_lbl)
        hl.addLayout(title_row)

        # Add block buttons — row 1
        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(4)
        self._add_btns = {}
        for btype, icon, label in [
            ("action",        "▶",  "Действие"),
            ("if_trigger",    "⚡", "ЕСЛИ триггер"),
            ("while_trigger", "🔁", "ПОКА триггер"),
        ]:
            btn = QPushButton(f"{icon} {label}")
            btn.setStyleSheet(ADD_BTN_STYLE)
            btn.setToolTip(self._add_tooltip(btype))
            btn.clicked.connect(lambda checked=False, t=btype: self.add_block_requested.emit(t))
            btn_row1.addWidget(btn)
            self._add_btns[btype] = btn
        hl.addLayout(btn_row1)

        # Add block buttons — row 2
        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(4)
        for btype, icon, label in [
            ("wait_trigger", "⏳", "Ждать триггер"),
            ("wait",         "⏱", "Ожидание"),
        ]:
            btn = QPushButton(f"{icon} {label}")
            btn.setStyleSheet(ADD_BTN_STYLE)
            btn.setToolTip(self._add_tooltip(btype))
            btn.clicked.connect(lambda checked=False, t=btype: self.add_block_requested.emit(t))
            btn_row2.addWidget(btn)
            self._add_btns[btype] = btn
        hl.addLayout(btn_row2)

        layout.addWidget(header)

        # ── List ─────────────────────────────────────────────────────────
        self._list = QListWidget()
        self._list.setStyleSheet(BLOCK_LIST_STYLE)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setSpacing(0)
        self._list.setUniformItemSizes(False)
        self._list.currentItemChanged.connect(self._on_selection)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._list)

        # ── Footer ───────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet("background: #181825; border-top: 1px solid #313244;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(8, 6, 8, 6)
        fl.setSpacing(8)

        self._count_lbl = QLabel("0 блоков")
        self._count_lbl.setStyleSheet("color: #585b70; font-size: 10px;")
        fl.addWidget(self._count_lbl)
        fl.addStretch()

        hint = QLabel("ПКМ / Del — удалить   •   Drag — переместить")
        hint.setStyleSheet("color: #45475a; font-size: 10px;")
        fl.addWidget(hint)

        # Delete button
        self._del_btn = QPushButton("✕  Удалить")
        self._del_btn.setStyleSheet(DEL_BTN_STYLE)
        self._del_btn.setToolTip("Удалить выбранный блок (Delete)")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._delete_selected)
        fl.addWidget(self._del_btn)

        layout.addWidget(footer)

        self._blocks: dict[str, Block] = {}
        self._highlighted_id: Optional[str] = None
        self._iteration = 1

    # ── Public API ────────────────────────────────────────────────────────

    @staticmethod
    def _add_tooltip(btype: str) -> str:
        tips = {
            "action":        "Добавить действие: клик, клавиша, движение мыши...",
            "if_trigger":    "ЕСЛИ триггер активен → выполнить действие (одна проверка)",
            "while_trigger": "ПОКА триггер активен → повторять действие (цикл while)",
            "wait_trigger":  "Ждать пока триггер не сработает, затем продолжить сценарий",
            "wait":          "Добавить паузу (ожидание N миллисекунд)",
        }
        return tips.get(btype, "")

    def _make_item_text(self, block: Block, index: int) -> str:
        icon = BLOCK_ICONS.get(block.type, "●")
        label = block.display_label()
        return f"{index + 1:>2}  {icon}  {label}"

    def add_block(self, block: Block) -> None:
        self._blocks[block.id] = block
        item = QListWidgetItem(self._make_item_text(block, self._list.count()))
        item.setData(Qt.ItemDataRole.UserRole, block.id)
        item.setSizeHint(QSize(-1, 44))
        self._list.addItem(item)
        self._update_count()

    def remove_block(self, block_id: str) -> None:
        self._blocks.pop(block_id, None)
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == block_id:
                self._list.takeItem(i)
                break
        self._renumber()
        self._update_count()

    def update_block(self, block: Block) -> None:
        self._blocks[block.id] = block
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == block.id:
                item.setText(self._make_item_text(block, i))
                break

    def highlight_block(self, block_id: str) -> None:
        self._highlighted_id = block_id
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                bid = item.data(Qt.ItemDataRole.UserRole)
                if bid == block_id:
                    item.setBackground(QColor("#1a3a1a"))
                    item.setForeground(QColor("#a6e3a1"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    self._list.scrollToItem(item)
                else:
                    item.setBackground(QColor())
                    item.setForeground(QColor("#cdd6f4"))
                    font = item.font()
                    font.setBold(False)
                    item.setFont(font)

    def set_step(self, step: int, total: int) -> None:
        prefix = f"Итерация {self._iteration}  ·  " if self._iteration > 1 else ""
        self._step_lbl.setText(f"▶  {prefix}Шаг {step} / {total}")
        self._step_lbl.show()

    def set_iteration(self, n: int) -> None:
        self._iteration = n

    def insert_block(self, block: Block, row: int) -> None:
        self._blocks[block.id] = block
        item = QListWidgetItem(self._make_item_text(block, row))
        item.setData(Qt.ItemDataRole.UserRole, block.id)
        item.setSizeHint(QSize(-1, 44))
        self._list.insertItem(row, item)
        self._renumber()
        self._update_count()
        self._list.setCurrentRow(row)

    def clear_highlights(self) -> None:
        self._highlighted_id = None
        self._iteration = 1
        self._step_lbl.hide()
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                item.setBackground(QColor())
                item.setForeground(QColor("#cdd6f4"))
                font = item.font()
                font.setBold(False)
                item.setFont(font)

    def clear_all(self) -> None:
        self._list.clear()
        self._blocks.clear()
        self._update_count()
        self._del_btn.setEnabled(False)

    def get_ordered_ids(self) -> list:
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
            if self._list.item(i)
        ]

    def set_enabled_add(self, enabled: bool) -> None:
        for btn in self._add_btns.values():
            btn.setEnabled(enabled)
        self._del_btn.setEnabled(enabled and self._list.currentItem() is not None)

    # ── Deletion ──────────────────────────────────────────────────────────

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        bid = item.data(Qt.ItemDataRole.UserRole)
        self.block_deleted.emit(bid)

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #45475a; }
        """)
        bid = item.data(Qt.ItemDataRole.UserRole)
        dup_action = menu.addAction("⧉  Дублировать")
        dup_action.triggered.connect(lambda: self.block_duplicated.emit(bid))
        del_action = menu.addAction("✕  Удалить блок")
        del_action.triggered.connect(lambda: self.block_deleted.emit(bid))
        menu.exec(self._list.mapToGlobal(pos))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_selected()
        else:
            super().keyPressEvent(event)

    # ── Internal ──────────────────────────────────────────────────────────

    def _on_selection(self, current, previous) -> None:
        has_sel = current is not None
        self._del_btn.setEnabled(has_sel)
        if current:
            bid = current.data(Qt.ItemDataRole.UserRole)
            self.block_selected.emit(bid)

    def _on_rows_moved(self, *args) -> None:
        self._renumber()
        self.blocks_reordered.emit(self.get_ordered_ids())

    def _renumber(self) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item:
                bid = item.data(Qt.ItemDataRole.UserRole)
                if bid in self._blocks:
                    item.setText(self._make_item_text(self._blocks[bid], i))

    def _update_count(self) -> None:
        n = self._list.count()
        self._count_lbl.setText(
            f"{n} {'блок' if n == 1 else 'блока' if 2 <= n <= 4 else 'блоков'}"
        )
