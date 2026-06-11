from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid


def new_id() -> str:
    return str(uuid.uuid4())[:8]


_new_id = new_id  # backward-compat alias


@dataclass
class Action:
    type: str = "wait"
    # click_xy | double_click | click_on_trigger | drag | key_press | key_hold
    # text_type | wait | random_wait | move_mouse | scroll
    x: Optional[int] = None
    y: Optional[int] = None
    x2: Optional[int] = None        # drag: end point
    y2: Optional[int] = None
    trigger_id: Optional[str] = None
    key: str = ""
    text: str = ""                  # text_type
    ms: int = 500                   # wait / drag duration / random_wait min
    ms_max: int = 1500              # random_wait max
    hold_ms: int = 1000             # key_hold duration
    button: str = "left"            # left | right | middle
    scroll_amount: int = 3
    offset_px: int = 0              # random click offset (humanization)


@dataclass
class Trigger:
    id: str = field(default_factory=new_id)
    name: str = "Триггер"
    type: str = "color_mask"        # color_mask | template | pixel | change | sound
    region: list = field(default_factory=lambda: [0, 0, 0, 0])
    hsv_lower: list = field(default_factory=lambda: [0, 100, 100])
    hsv_upper: list = field(default_factory=lambda: [10, 255, 255])
    min_match_ratio: float = 0.05   # color_mask: color share; change: changed-pixel share
    template_path: Optional[str] = None
    template_threshold: float = 0.8
    # pixel trigger:
    pixel_x: int = 0
    pixel_y: int = 0
    pixel_rgb: list = field(default_factory=lambda: [255, 0, 0])  # R, G, B
    pixel_tolerance: int = 10
    # sound trigger:
    sound_path: Optional[str] = None
    sound_mode: str = "match"       # match (sample) | level (volume)
    sound_threshold: float = 0.60   # match similarity 0..1
    sound_level: float = 0.10       # RMS level 0..1 for level mode


@dataclass
class Block:
    id: str = field(default_factory=new_id)
    type: str = "action"            # action | if_trigger | wait | wait_trigger | while_trigger
    label: str = ""
    action: Optional[Action] = None
    actions: list = field(default_factory=list)  # if/while: sequential actions
    trigger_id: Optional[str] = None
    wait_timeout_ms: int = 10000    # wait_trigger: 0 = infinite
    # while_trigger:
    repeat_delay_ms: int = 200      # pause between loop iterations
    max_repeats: int = 0            # 0 = infinite (until trigger state changes)
    invert: bool = False            # False = while active, True = while NOT active

    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.type == "wait" and self.action:
            return f"Ожидание {self.action.ms} мс"
        if self.type == "action" and self.action:
            a = self.action
            t = a.type
            if t == "click_xy":
                extra = f" ±{a.offset_px}px" if a.offset_px else ""
                return f"Клик ({a.x}, {a.y}){extra}"
            if t == "double_click":
                return f"Двойной клик ({a.x}, {a.y})"
            if t == "click_on_trigger":
                return "Клик по триггеру"
            if t == "drag":
                return f"Драг ({a.x},{a.y}) → ({a.x2},{a.y2})"
            if t == "key_press":
                return f"Клавиша [{a.key}]"
            if t == "key_hold":
                return f"Зажать [{a.key}] {a.hold_ms} мс"
            if t == "mouse_hold":
                return f"Зажать {a.button}-клик {a.hold_ms} мс ({a.x}, {a.y})"
            if t == "text_type":
                txt = a.text if len(a.text) <= 18 else a.text[:18] + "…"
                return f"Текст: {txt}"
            if t == "move_mouse":
                return f"Мышь → ({a.x}, {a.y})"
            if t == "scroll":
                return f"Скролл {a.scroll_amount}"
            if t == "wait":
                return f"Пауза {a.ms} мс"
            if t == "random_wait":
                return f"Пауза {a.ms}–{a.ms_max} мс (случайно)"
            if t == "beep":
                names = {"beep": "Сигнал", "alarm": "Тревога ×3", "system": "Системный"}
                return f"Звук: {names.get(a.text, 'Сигнал')}"
            if t == "stop_bot":
                return "СТОП — остановить бота"
            if t == "restart_scenario":
                return "Сценарий заново (с шага 1)"
        if self.type == "if_trigger":
            return f"ЕСЛИ триггер → {self._actions_word()}"
        if self.type == "wait_trigger":
            sec = self.wait_timeout_ms // 1000
            limit = f"таймаут {sec}с" if self.wait_timeout_ms > 0 else "∞"
            return f"Ждать триггер ({limit})"
        if self.type == "while_trigger":
            cond = "ПОКА НЕТ триггера" if self.invert else "ПОКА триггер"
            limit = f" (макс {self.max_repeats}×)" if self.max_repeats > 0 else ""
            return f"{cond} → {self._actions_word()}{limit}"
        return "Блок"

    def _actions_word(self) -> str:
        n = len(self.actions) if self.actions else (1 if self.action else 0)
        if n <= 1:
            return "действие"
        if 2 <= n <= 4:
            return f"{n} действия"
        return f"{n} действий"


@dataclass
class BotConfig:
    name: str = "Новый бот"
    loop: bool = True
    loop_delay_ms: int = 50
    max_iterations: int = 0         # 0 = infinite
    triggers: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
