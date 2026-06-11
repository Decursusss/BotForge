from __future__ import annotations
import time

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    _PAG_OK = True
except ImportError:
    _PAG_OK = False

try:
    import pydirectinput
    pydirectinput.FAILSAFE = False
    _PDI_OK = True
except ImportError:
    _PDI_OK = False


# Key-name aliases → canonical names understood by the backends
_KEY_ALIASES = {
    "win": "winleft", "windows": "winleft", "cmd": "winleft",
    "super": "winleft", "lwin": "winleft", "meta": "winleft",
    "rwin": "winright",
    "control": "ctrl", "ctl": "ctrl",
    "escape": "esc",
    "return": "enter",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup", "pgdn": "pagedown", "pgdown": "pagedown",
    "caps_lock": "capslock",
}

# pydirectinput sends DirectInput scancodes without the extended-key flag,
# so the Windows key is silently ignored by the OS. These keys are sent
# directly via WinAPI keybd_event with virtual-key codes instead.
_VK_FALLBACK = {
    "winleft": 0x5B,
    "winright": 0x5C,
    "apps": 0x5D,
}


def _vk_event(vk: int, up: bool) -> None:
    """Send a key event via WinAPI with the extended-key flag."""
    import ctypes
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    flags = KEYEVENTF_EXTENDEDKEY | (KEYEVENTF_KEYUP if up else 0)
    ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


class InputBackend:
    """Unified input abstraction. backend='pydirectinput' or 'pyautogui'."""

    def __init__(self, backend: str = "pydirectinput"):
        if backend == "pydirectinput" and _PDI_OK:
            self._lib = pydirectinput
            self._mode = "pydirectinput"
        elif _PAG_OK:
            self._lib = pyautogui
            self._mode = "pyautogui"
        else:
            self._lib = None
            self._mode = "none"

    @property
    def mode(self) -> str:
        return self._mode

    @staticmethod
    def _norm_key(key: str) -> str:
        k = (key or "").strip().lower()
        return _KEY_ALIASES.get(k, k)

    def _needs_vk(self, key: str) -> bool:
        """Keys pydirectinput cannot deliver — sent via WinAPI instead."""
        return self._mode == "pydirectinput" and key in _VK_FALLBACK

    def click(self, x: int, y: int, button: str = "left") -> None:
        if self._lib is None:
            return
        try:
            self._lib.click(x, y, button=button)
        except Exception:
            pass

    def move(self, x: int, y: int) -> None:
        if self._lib is None:
            return
        try:
            self._lib.moveTo(x, y)
        except Exception:
            pass

    def press(self, key: str) -> None:
        if self._lib is None or not key:
            return
        key = self._norm_key(key)
        if self._needs_vk(key):
            vk = _VK_FALLBACK[key]
            _vk_event(vk, up=False)
            time.sleep(0.03)
            _vk_event(vk, up=True)
            return
        try:
            self._lib.press(key)
        except Exception:
            pass

    def key_down(self, key: str) -> None:
        if self._lib is None or not key:
            return
        key = self._norm_key(key)
        if self._needs_vk(key):
            _vk_event(_VK_FALLBACK[key], up=False)
            return
        try:
            self._lib.keyDown(key)
        except Exception:
            pass

    def key_up(self, key: str) -> None:
        if self._lib is None or not key:
            return
        key = self._norm_key(key)
        if self._needs_vk(key):
            _vk_event(_VK_FALLBACK[key], up=True)
            return
        try:
            self._lib.keyUp(key)
        except Exception:
            pass

    def hotkey(self, *keys: str) -> None:
        """Press a key combination, e.g. hotkey('ctrl', 'a') for Ctrl+A."""
        if self._lib is None or not keys:
            return
        norm = [self._norm_key(k) for k in keys if k and k.strip()]
        if not norm:
            return
        try:
            if self._mode == "pyautogui":
                pyautogui.hotkey(*norm)
                return
            # pydirectinput has no hotkey() — simulate manually.
            # Route through key_down/key_up so the WinAPI fallback applies
            # to keys pydirectinput can't send (win, apps).
            held = []
            try:
                for k in norm[:-1]:
                    self.key_down(k)
                    held.append(k)
                    time.sleep(0.03)
                self.key_down(norm[-1])
                time.sleep(0.03)
                self.key_up(norm[-1])
            finally:
                for k in reversed(held):
                    self.key_up(k)
                    time.sleep(0.02)
        except Exception:
            pass

    def scroll(self, x: int, y: int, amount: int = 3) -> None:
        if self._lib is None:
            return
        try:
            if self._mode == "pyautogui":
                pyautogui.scroll(amount, x=x, y=y)
            else:
                pydirectinput.scroll(amount)
        except Exception:
            pass

    def mouse_down(self, button: str = "left") -> None:
        if self._lib is None:
            return
        try:
            self._lib.mouseDown(button=button)
        except Exception:
            pass

    def mouse_up(self, button: str = "left") -> None:
        if self._lib is None:
            return
        try:
            self._lib.mouseUp(button=button)
        except Exception:
            pass

    def double_click(self, x: int, y: int, button: str = "left") -> None:
        if self._lib is None:
            return
        try:
            self._lib.click(x, y, button=button)
            time.sleep(0.06)
            self._lib.click(x, y, button=button)
        except Exception:
            pass

    def drag(self, x1: int, y1: int, x2: int, y2: int,
             duration_ms: int = 300, button: str = "left") -> None:
        """Press at (x1,y1), move to (x2,y2) in steps, release."""
        if self._lib is None:
            return
        try:
            self._lib.moveTo(x1, y1)
            time.sleep(0.05)
            self._lib.mouseDown(button=button)
            steps = max(int(duration_ms / 16), 2)
            for i in range(1, steps + 1):
                nx = x1 + (x2 - x1) * i // steps
                ny = y1 + (y2 - y1) * i // steps
                self._lib.moveTo(nx, ny)
                time.sleep(duration_ms / 1000.0 / steps)
            self._lib.mouseUp(button=button)
        except Exception:
            try:
                self._lib.mouseUp(button=button)
            except Exception:
                pass

    def type_text(self, text: str, interval: float = 0.0001) -> None:
        """Type a string. Note: pydirectinput supports latin/digits only."""
        if self._lib is None or not text:
            return
        try:
            self._lib.write(text, interval=interval)
        except Exception:
            # Fallback: char-by-char press
            for ch in text:
                try:
                    self._lib.press(ch)
                    time.sleep(interval)
                except Exception:
                    pass
