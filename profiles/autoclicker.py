"""
profiles/autoclicker.py
Profile 5 - Autoclicker

OLED button   -> Start / stop clicking
Roller click  -> Toggle mode: Click <-> Hold
Scroll up     -> Increase interval (ms)
Scroll down   -> Decrease interval (ms)

Modes:
  Click : left click, wait <interval> ms, repeat
  Hold  : press down, wait <interval> ms, release, short gap, repeat

Interval steps scale with the value:
  <= 50ms   : +/- 5ms
  <= 200ms  : +/- 10ms
  <= 1000ms : +/- 50ms
  above     : +/- 100ms

Requires: pip install pynput   (only the mouse part is used)
"""

import threading
import time

import gamesense
from profiles.base import BaseProfile

try:
    from pynput.mouse import Controller as MouseController, Button
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

MIN_MS   = 10
MAX_MS   = 10000
HOLD_GAP = 0.05   # seconds between hold cycles (release -> next press)


class AutoClickerProfile(BaseProfile):
    name = "AutoClicker"

    def __init__(self):
        self._interval_ms = 100
        self._hold_mode   = False
        self._active      = False
        self._running     = False
        self._gen         = 0     # kills stale click threads
        self._lock        = threading.Lock()
        self._mouse       = MouseController() if PYNPUT_AVAILABLE else None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        if not PYNPUT_AVAILABLE:
            gamesense.show("AutoClicker", "pip install pynput")
            return
        self._draw()

    def stop(self):
        self._running = False
        self._set_active(False)
        # Defensive: never leave the mouse button stuck down
        if self._mouse:
            try:
                self._mouse.release(Button.left)
            except Exception:
                pass

    # ── controls ──────────────────────────────────────────────────────────────

    def on_button_press(self):
        if not PYNPUT_AVAILABLE:
            return
        with self._lock:
            new_state = not self._active
        self._set_active(new_state)
        self._draw()

    def on_roller_click(self):
        with self._lock:
            self._hold_mode = not self._hold_mode
        self._draw()

    def on_scroll_up(self):
        with self._lock:
            self._interval_ms = min(MAX_MS, self._interval_ms + self._step())
        self._draw()

    def on_scroll_down(self):
        with self._lock:
            self._interval_ms = max(MIN_MS, self._interval_ms - self._step())
        self._draw()

    # ── internals ─────────────────────────────────────────────────────────────

    def _step(self) -> int:
        ms = self._interval_ms
        if ms <= 50:   return 5
        if ms <= 200:  return 10
        if ms <= 1000: return 50
        return 100

    def _set_active(self, active: bool):
        with self._lock:
            if active == self._active:
                return
            self._active = active
            if active:
                self._gen += 1
                gen = self._gen
                threading.Thread(target=self._click_loop, args=(gen,), daemon=True).start()
                print("[autoclicker] started")
            else:
                print("[autoclicker] stopped")

    def _click_loop(self, gen: int):
        while True:
            with self._lock:
                if not self._active or gen != self._gen or not self._running:
                    return
                interval = self._interval_ms / 1000.0
                hold     = self._hold_mode
            try:
                if hold:
                    self._mouse.press(Button.left)
                    time.sleep(interval)
                    self._mouse.release(Button.left)
                    time.sleep(HOLD_GAP)
                else:
                    self._mouse.click(Button.left)
                    time.sleep(interval)
            except Exception as e:
                print(f"[autoclicker] error: {e}")
                self._set_active(False)
                return

    def _draw(self):
        with self._lock:
            state = "ON" if self._active else "OFF"
            mode  = "Hold" if self._hold_mode else "Click"
            ms    = self._interval_ms
        gamesense.show(f"AutoClk {state} {mode}"[:20], f"{ms}ms")
