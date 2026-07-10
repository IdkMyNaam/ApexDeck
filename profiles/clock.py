"""
profiles/clock.py
Profile 2 — Clock display with date.

Shows:
  Line 1 — current time  (HH:MM:SS)
  Line 2 — current date  (Mon DD MMM)

Controls in this profile:
  Roller scroll  → nothing (could add brightness/contrast later)
  Roller click   → toggle between 12h and 24h format
  OLED button    → nothing
"""

import threading
import time
from datetime import datetime

import gamesense
from profiles.base import BaseProfile


class ClockProfile(BaseProfile):
    name = "Clock"

    def __init__(self):
        self._running = False
        self._thread = None
        self._24h = True   # toggle with roller click

    def start(self):
        self._running = True
        self._gen = getattr(self, "_gen", 0) + 1
        self._thread = threading.Thread(target=self._tick, args=(self._gen,), daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def on_roller_click(self):
        self._24h = not self._24h
        fmt = "24h" if self._24h else "12h"
        print(f"[clock] switched to {fmt} format")

    def _tick(self, gen):
        while self._running and gen == getattr(self, "_gen", gen):
            now = datetime.now()
            if self._24h:
                time_str = now.strftime("%H:%M:%S")
            else:
                time_str = now.strftime("%I:%M:%S %p").lstrip("0")
            date_str = now.strftime("%a %d %b")   # e.g. "Sat 23 May"
            gamesense.show(time_str, date_str)
            time.sleep(1)
