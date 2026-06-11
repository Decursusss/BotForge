from __future__ import annotations
import time
import random
import threading
from typing import Optional, List, Dict

from PySide6.QtCore import QThread, Signal

from .models import BotConfig, Block, Trigger, Action
from .capture import capture_screen
from .vision import check_color_mask, check_template, check_pixel_color, check_change
from .input_backend import InputBackend

try:
    from pynput import keyboard as pynput_kb
    _PYNPUT_OK = True
except ImportError:
    _PYNPUT_OK = False

try:
    import cv2
    import numpy as np
    _CV2_OK = True
except ImportError:
    _CV2_OK = False


class BotEngine(QThread):
    block_activated   = Signal(str)         # block id
    block_step        = Signal(int, int)    # current step (1-based), total steps
    iteration_changed = Signal(int)         # loop iteration number (1-based)
    trigger_fired     = Signal(str)         # trigger id
    trigger_match     = Signal(str, int, int)  # trigger id, cx, cy (region-relative)
    log_message       = Signal(str)
    engine_stopped    = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: Optional[BotConfig] = None
        self._running = False
        self._restart = False
        self._input = InputBackend()
        self._hotkey_listener = None
        self._trigger_cache: Dict[str, bool] = {}
        self._template_cache: Dict[str, Optional[object]] = {}
        self._prev_frames: Dict[str, object] = {}  # change-trigger: previous frame
        self._sound_cache: Dict[str, Optional[object]] = {}
        self._audio_monitor = None

    def set_config(self, config: BotConfig) -> None:
        self._config = config
        self._template_cache.clear()
        self._prev_frames.clear()
        self._sound_cache.clear()

    def set_backend(self, backend: str) -> None:
        self._input = InputBackend(backend)

    def start_hotkey(self) -> None:
        if not _PYNPUT_OK:
            return
        try:
            self._hotkey_listener = pynput_kb.GlobalHotKeys({
                "<f12>": self._emergency_stop
            })
            self._hotkey_listener.start()
        except Exception as e:
            self.log_message.emit(f"Хоткей F12 не зарегистрирован: {e}")

    def stop_hotkey(self) -> None:
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

    def _emergency_stop(self) -> None:
        self.log_message.emit("F12: аварийная остановка")
        self.stop()

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        if self._config is None:
            self.log_message.emit("Ошибка: конфигурация не задана")
            self.engine_stopped.emit()
            return

        self._running = True
        config = self._config
        self.log_message.emit(f"Запуск: {config.name}")

        # Sound triggers need a live system-audio monitor
        self._audio_monitor = None
        if any(t.type == "sound" for t in config.triggers):
            try:
                from .audio import AudioMonitor, AUDIO_OK
                if AUDIO_OK:
                    mon = AudioMonitor()
                    if mon.start():
                        self._audio_monitor = mon
                        self.log_message.emit("Аудио-мониторинг запущен")
                    else:
                        self.log_message.emit(
                            "⚠ Не удалось запустить захват звука — звуковые триггеры неактивны")
                else:
                    self.log_message.emit(
                        "⚠ Пакет soundcard не установлен (pip install soundcard)")
            except Exception as e:
                self.log_message.emit(f"⚠ Аудио-мониторинг: {e}")

        iteration = 0
        while self._running:
            iteration += 1
            if config.max_iterations > 0 and iteration > config.max_iterations:
                self.log_message.emit(f"Достигнут лимит повторов ({config.max_iterations})")
                break
            self.iteration_changed.emit(iteration)
            if iteration > 1:
                self.log_message.emit(f"--- Итерация {iteration} ---")

            self._restart = False
            total = len(config.blocks)
            for step, block in enumerate(config.blocks, 1):
                if not self._running or self._restart:
                    break
                self.block_activated.emit(block.id)
                self.block_step.emit(step, total)
                self._execute_block(block, config)

            if self._restart:
                continue  # restart_scenario: jump back to step 1

            if not config.loop:
                break

            if self._running and config.loop_delay_ms > 0:
                self._sleep_ms(config.loop_delay_ms)

        if self._audio_monitor is not None:
            self._audio_monitor.stop()
            self._audio_monitor = None

        self.log_message.emit("Остановлено.")
        self.engine_stopped.emit()

    def _execute_block(self, block: Block, config: BotConfig) -> None:
        if block.type == "wait":
            ms = block.action.ms if block.action else 500
            self.log_message.emit(f"Ожидание {ms} мс")
            self._sleep_ms(ms)

        elif block.type == "action":
            if block.action:
                self._execute_action(block.action, config)

        elif block.type == "wait_trigger":
            self._execute_wait_trigger(block, config)

        elif block.type == "while_trigger":
            self._execute_while_trigger(block, config)

        elif block.type == "if_trigger":
            trigger = self._find_trigger(block.trigger_id, config)
            if trigger is None:
                return
            fired, cx, cy = self._check_trigger(trigger)
            if fired:
                self.trigger_fired.emit(trigger.id)
                if cx is not None and cy is not None:
                    self.trigger_match.emit(trigger.id, cx, cy)
                self.log_message.emit(f"Триггер '{trigger.name}' сработал → ({cx},{cy})")
                self._run_trigger_actions(block, trigger, cx, cy, config)

    @staticmethod
    def _actions_of(block: Block) -> list:
        """Action chain of a block: new-style list or legacy single action."""
        if block.actions:
            return block.actions
        return [block.action] if block.action else []

    def _run_trigger_actions(self, block: Block, trigger: Trigger,
                             cx, cy, config: BotConfig) -> None:
        """Execute the block's action chain sequentially."""
        for action in self._actions_of(block):
            if not self._running or self._restart:
                return
            if action.type == "click_on_trigger" and cx is not None and cy is not None:
                abs_x = trigger.region[0] + cx
                abs_y = trigger.region[1] + cy
                self.log_message.emit(f"Клик по триггеру ({abs_x},{abs_y})")
                self._input.click(abs_x, abs_y, action.button)
            else:
                self._execute_action(action, config)

    def _execute_wait_trigger(self, block: Block, config: BotConfig) -> None:
        trigger = self._find_trigger(block.trigger_id, config)
        if trigger is None:
            self.log_message.emit("Блок 'Ждать триггер': триггер не выбран, пропуск")
            return

        timeout_ms = block.wait_timeout_ms
        deadline = time.monotonic() + timeout_ms / 1000.0 if timeout_ms > 0 else None
        self.log_message.emit(
            f"Ожидаю триггер '{trigger.name}'"
            + (f" (таймаут {timeout_ms} мс)" if timeout_ms > 0 else " (∞)")
        )

        while self._running:
            fired, cx, cy = self._check_trigger(trigger)
            if fired:
                self.trigger_fired.emit(trigger.id)
                if cx is not None and cy is not None:
                    self.trigger_match.emit(trigger.id, cx, cy)
                self.log_message.emit(f"Триггер '{trigger.name}' сработал! Продолжаю.")
                return
            if deadline is not None and time.monotonic() >= deadline:
                self.log_message.emit(f"Таймаут ожидания '{trigger.name}'. Продолжаю.")
                return
            self._sleep_ms(100)

    def _execute_while_trigger(self, block: Block, config: BotConfig) -> None:
        trigger = self._find_trigger(block.trigger_id, config)
        if trigger is None:
            self.log_message.emit("Блок 'ПОКА триггер': триггер не выбран, пропуск")
            return

        cond_name = "НЕ активен" if block.invert else "активен"
        self.log_message.emit(
            f"Цикл: пока '{trigger.name}' {cond_name}"
            + (f", макс {block.max_repeats} повторов" if block.max_repeats > 0 else "")
        )

        count = 0
        while self._running:
            fired, cx, cy = self._check_trigger(trigger)
            condition = (not fired) if block.invert else fired
            if not condition:
                self.log_message.emit(f"Цикл завершён: условие больше не выполняется ({count}×)")
                return
            if fired:
                self.trigger_fired.emit(trigger.id)
                if cx is not None and cy is not None:
                    self.trigger_match.emit(trigger.id, cx, cy)

            self._run_trigger_actions(block, trigger, cx, cy, config)

            count += 1
            if self._restart:
                return  # restart_scenario fired inside the loop body
            if block.max_repeats > 0 and count >= block.max_repeats:
                self.log_message.emit(f"Цикл завершён: лимит {block.max_repeats} повторов")
                return
            self._sleep_ms(max(block.repeat_delay_ms, 20))

    def _execute_action(self, action: Action, config: BotConfig) -> None:
        t = action.type
        if t == "click_xy":
            x, y = action.x or 0, action.y or 0
            if action.offset_px > 0:
                x += random.randint(-action.offset_px, action.offset_px)
                y += random.randint(-action.offset_px, action.offset_px)
            self.log_message.emit(f"Клик ({x},{y}) [{action.button}]")
            self._input.click(x, y, action.button)
        elif t == "double_click":
            x, y = action.x or 0, action.y or 0
            if action.offset_px > 0:
                x += random.randint(-action.offset_px, action.offset_px)
                y += random.randint(-action.offset_px, action.offset_px)
            self.log_message.emit(f"Двойной клик ({x},{y})")
            self._input.double_click(x, y, action.button)
        elif t == "drag":
            self.log_message.emit(
                f"Драг ({action.x},{action.y}) → ({action.x2},{action.y2})"
            )
            self._input.drag(
                action.x or 0, action.y or 0,
                action.x2 or 0, action.y2 or 0,
                max(action.ms or 300, 50), action.button,
            )
        elif t == "key_hold":
            key = (action.key or "").strip()
            if key:
                self.log_message.emit(f"Зажимаю [{key}] на {action.hold_ms} мс")
                self._input.key_down(key)
                self._sleep_ms(action.hold_ms)
                self._input.key_up(key)
        elif t == "mouse_hold":
            x, y = action.x or 0, action.y or 0
            self.log_message.emit(
                f"Зажимаю {action.button} кнопку мыши на {action.hold_ms} мс ({x},{y})")
            self._input.move(x, y)
            self._input.mouse_down(action.button)
            self._sleep_ms(action.hold_ms)
            self._input.mouse_up(action.button)  # released even after F12 stop
        elif t == "text_type":
            if action.text:
                self.log_message.emit(f"Ввожу текст ({len(action.text)} симв.)")
                self._input.type_text(action.text)
        elif t == "random_wait":
            lo = max(action.ms or 0, 0)
            hi = max(action.ms_max or 0, lo)
            ms = random.randint(lo, hi)
            self.log_message.emit(f"Случайная пауза {ms} мс")
            self._sleep_ms(ms)
        elif t == "click_on_trigger":
            trigger = self._find_trigger(action.trigger_id, config)
            if trigger:
                fired, cx, cy = self._check_trigger(trigger)
                if fired and cx is not None:
                    ax = trigger.region[0] + cx
                    ay = trigger.region[1] + cy
                    self.log_message.emit(f"Клик по триггеру ({ax},{ay})")
                    self._input.click(ax, ay, action.button)
        elif t == "key_press":
            key_str = (action.key or "").strip()
            parts = [k.strip() for k in key_str.split("+") if k.strip()]
            if len(parts) > 1:
                self.log_message.emit(f"Хоткей [{'+'.join(parts)}]")
                self._input.hotkey(*parts)
            elif parts:
                self.log_message.emit(f"Клавиша [{parts[0]}]")
                self._input.press(parts[0])
        elif t == "wait":
            self.log_message.emit(f"Ожидание {action.ms} мс")
            self._sleep_ms(action.ms or 0)
        elif t == "move_mouse":
            self.log_message.emit(f"Мышь → ({action.x},{action.y})")
            self._input.move(action.x or 0, action.y or 0)
        elif t == "scroll":
            self.log_message.emit(f"Скролл {action.scroll_amount}")
            self._input.scroll(action.x or 0, action.y or 0, action.scroll_amount)
        elif t == "beep":
            self.log_message.emit("Звуковой сигнал")
            self._play_sound(action.text or "beep", action.ms or 300)
        elif t == "stop_bot":
            self.log_message.emit("Действие СТОП: останавливаю бота")
            self._running = False
        elif t == "restart_scenario":
            self.log_message.emit("Действие: начинаю сценарий заново")
            self._restart = True

    def _play_sound(self, kind: str, duration_ms: int) -> None:
        try:
            import winsound
            if kind == "system":
                winsound.MessageBeep()
            elif kind == "alarm":
                for _ in range(3):
                    winsound.Beep(1500, 200)
                    time.sleep(0.08)
            else:
                winsound.Beep(1000, max(min(duration_ms, 5000), 50))
        except Exception:
            pass

    def _check_trigger(self, trigger: Trigger):
        # Sound trigger: checked against the live audio monitor, no screen capture
        if trigger.type == "sound":
            mon = self._audio_monitor
            if mon is None:
                return False, None, None
            try:
                if trigger.sound_mode == "level":
                    fired = mon.current_level() >= trigger.sound_level
                else:
                    template = self._load_sound(trigger)
                    if template is None:
                        return False, None, None
                    from .audio import match_audio
                    score = match_audio(mon.get_buffer(), template)
                    fired = score >= trigger.sound_threshold
            except Exception:
                return False, None, None
            if fired:
                mon.clear()  # cooldown: same sound must not re-fire from the buffer
                return True, None, None
            return False, None, None

        # Pixel trigger: 1×1 capture at its own coords, region not used for check
        if trigger.type == "pixel":
            frame = capture_screen((trigger.pixel_x, trigger.pixel_y, 1, 1))
            if frame is None:
                return False, None, None
            fired = check_pixel_color(frame, trigger.pixel_rgb, trigger.pixel_tolerance)
            if fired:
                # region-relative center so click_on_trigger hits the pixel
                cx = trigger.pixel_x - trigger.region[0]
                cy = trigger.pixel_y - trigger.region[1]
                return True, cx, cy
            return False, None, None

        frame = capture_screen(tuple(trigger.region))
        if frame is None:
            return False, None, None

        if trigger.type == "color_mask":
            fired, cx, cy, _ = check_color_mask(
                frame, trigger.hsv_lower, trigger.hsv_upper, trigger.min_match_ratio
            )
            return fired, cx, cy
        elif trigger.type == "template":
            template = self._load_template(trigger)
            if template is None:
                return False, None, None
            fired, cx, cy = check_template(frame, template, trigger.template_threshold)
            return fired, cx, cy
        elif trigger.type == "change":
            prev = self._prev_frames.get(trigger.id)
            self._prev_frames[trigger.id] = frame
            fired, cx, cy, _ = check_change(frame, prev, trigger.min_match_ratio)
            return fired, cx, cy

        return False, None, None

    def _load_sound(self, trigger: Trigger):
        if trigger.id in self._sound_cache:
            return self._sound_cache[trigger.id]
        tpl = None
        if trigger.sound_path:
            try:
                from .audio import load_wav
                tpl = load_wav(trigger.sound_path)
            except Exception:
                tpl = None
        self._sound_cache[trigger.id] = tpl
        return tpl

    def _load_template(self, trigger: Trigger):
        if trigger.id in self._template_cache:
            return self._template_cache[trigger.id]
        if not _CV2_OK or not trigger.template_path:
            self._template_cache[trigger.id] = None
            return None
        try:
            # np.fromfile + imdecode: works with non-ASCII paths unlike cv2.imread
            data = np.fromfile(trigger.template_path, dtype=np.uint8)
            tmpl = cv2.imdecode(data, cv2.IMREAD_COLOR)
            self._template_cache[trigger.id] = tmpl
            return tmpl
        except Exception:
            self._template_cache[trigger.id] = None
            return None

    def _find_trigger(self, trigger_id: Optional[str], config: BotConfig) -> Optional[Trigger]:
        if not trigger_id:
            return None
        for t in config.triggers:
            if t.id == trigger_id:
                return t
        return None

    def _sleep_ms(self, ms: int) -> None:
        end = time.monotonic() + ms / 1000.0
        while self._running and time.monotonic() < end:
            time.sleep(0.01)
