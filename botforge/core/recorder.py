from __future__ import annotations
import time
from typing import Callable, List

from .models import Block, Action

try:
    from pynput import mouse, keyboard
    _PYNPUT_OK = True
except ImportError:
    _PYNPUT_OK = False


class Recorder:
    """Records mouse clicks and key presses into Block objects."""

    def __init__(self, on_block: Callable[[Block], None]):
        self._on_block = on_block
        self._active = False
        self._mouse_listener = None
        self._keyboard_listener = None
        self._last_time = 0.0

    def start(self) -> None:
        if not _PYNPUT_OK or self._active:
            return
        self._active = True
        self._last_time = time.time()

        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._keyboard_listener = keyboard.Listener(on_press=self._on_key)
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def stop(self) -> None:
        self._active = False
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

    def _emit_wait(self) -> None:
        now = time.time()
        elapsed_ms = int((now - self._last_time) * 1000)
        self._last_time = now
        if elapsed_ms > 100:
            b = Block(type="wait", action=Action(type="wait", ms=elapsed_ms))
            b.label = f"Ожидание {elapsed_ms} мс"
            self._on_block(b)

    def _on_click(self, x, y, button, pressed) -> None:
        if not self._active or not pressed:
            return
        self._emit_wait()
        btn = "left" if str(button).endswith("left") else "right"
        action = Action(type="click_xy", x=x, y=y, button=btn)
        b = Block(type="action", action=action)
        b.label = f"Клик {btn} ({x},{y})"
        self._on_block(b)

    def _on_key(self, key) -> None:
        if not self._active:
            return
        try:
            key_name = key.char if hasattr(key, "char") and key.char else key.name
        except AttributeError:
            return
        if key_name is None:
            return
        self._emit_wait()
        action = Action(type="key_press", key=key_name)
        b = Block(type="action", action=action)
        b.label = f"Клавиша [{key_name}]"
        self._on_block(b)
