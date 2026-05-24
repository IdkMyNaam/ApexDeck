"""
profiles/slots.py
Profile 4 - Slot Machine

OLED button / Roller click -> Spin
Scroll up                  -> Increase bet
Scroll down                -> Decrease bet

Coins are saved to .slots_save and passively generated over time.
If you run out you have to wait for passive income to build back up.
"""

import threading
import time
import random
import json
import os

import gamesense
from profiles.base import BaseProfile

SYMBOLS    = ["NIG", "7", "$", "BAR", "***", "o"]
PAYOUTS    = {"NIG":1000, "7": 100, "$": 20, "BAR": 10, "***": 5, "o": 3}
PAYOUT_2   = 1
WEIGHTS    = [2, 5, 15, 20, 25, 35]
BET_OPTIONS       = [1, 5, 10, 25, 50, 100, "ALL"]
STARTING_COINS    = 100
PASSIVE_INCOME    = 5      # coins per interval
PASSIVE_INTERVAL  = 30     # seconds between passive income ticks
MAX_COINS         = 99999
SPIN_TICK         = 0.08
SPIN_FRAMES       = 12
REEL_STOP         = 4

SAVE_FILE = os.path.join(os.path.dirname(__file__), "..", ".slots_save")


def _load_save():
    try:
        with open(SAVE_FILE) as f:
            data = json.load(f)
        coins = int(data.get("coins", STARTING_COINS))
        # Calculate offline passive income based on time away
        last_seen = float(data.get("last_seen", time.time()))
        elapsed   = time.time() - last_seen
        ticks     = int(elapsed // PASSIVE_INTERVAL)
        coins     = min(MAX_COINS, coins + ticks * PASSIVE_INCOME)
        return coins
    except Exception:
        return STARTING_COINS

def _save(coins):
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump({"coins": coins, "last_seen": time.time()}, f)
    except Exception:
        pass


class SlotsProfile(BaseProfile):
    name = "Slots"

    def __init__(self):
        self._coins    = _load_save()
        self._bet_idx  = 1
        self._reels    = ["7", "$", "BAR"]
        self._spinning = False
        self._running  = False
        self._lock     = threading.Lock()
        self._passive_thread = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._passive_thread = threading.Thread(target=self._passive_loop, daemon=True)
        self._passive_thread.start()
        self._draw_idle()

    def stop(self):
        self._running = False
        with self._lock:
            _save(self._coins)

    # ── controls ──────────────────────────────────────────────────────────────

    def on_button_press(self):
        self._try_spin()

    def on_roller_click(self):
        self._try_spin()

    def on_scroll_up(self):
        with self._lock:
            if self._spinning:
                return
            self._bet_idx = min(len(BET_OPTIONS) - 1, self._bet_idx + 1)
        self._draw_idle()

    def on_scroll_down(self):
        with self._lock:
            if self._spinning:
                return
            self._bet_idx = max(0, self._bet_idx - 1)
        self._draw_idle()

    # ── OLED ──────────────────────────────────────────────────────────────────

    def _reel_str(self, reels):
        def pad(s): return s.center(3)
        return f"{pad(reels[0])}|{pad(reels[1])}|{pad(reels[2])}"

    def _draw_idle(self):
        with self._lock:
            coins  = self._coins
            bet    = BET_OPTIONS[self._bet_idx]
            reels  = list(self._reels)
            broke  = coins < BET_OPTIONS[0]

        line1 = self._reel_str(reels)
        if broke:
            line2 = f"Wait {PASSIVE_INTERVAL}s +{PASSIVE_INCOME}"
        elif bet == "ALL":
            line2 = f"C:{coins} B:ALL"
        else:
            line2 = f"C:{coins} B:{bet}"
        gamesense.show(line1, line2)

    # ── passive income loop ───────────────────────────────────────────────────

    def _passive_loop(self):
        while self._running:
            time.sleep(PASSIVE_INTERVAL)
            if not self._running:
                break
            with self._lock:
                self._coins = min(MAX_COINS, self._coins + PASSIVE_INCOME)
                coins = self._coins
                spinning = self._spinning
                _save(coins)
            print(f"[slots] passive income +{PASSIVE_INCOME} → {coins} coins")
            if not spinning:
                self._draw_idle()

    # ── spin ──────────────────────────────────────────────────────────────────

    def _try_spin(self):
        with self._lock:
            if self._spinning:
                return
            coins  = self._coins
            bet_opt = BET_OPTIONS[self._bet_idx]

            # Resolve ALL IN
            if bet_opt == "ALL":
                bet = coins
            else:
                bet = bet_opt

            if coins < 1:
                gamesense.show("Need coins!", f"+{PASSIVE_INCOME}/{PASSIVE_INTERVAL}s")
                return
            if bet_opt != "ALL" and coins < bet:
                # Clamp bet to what they can afford
                while self._bet_idx > 0 and BET_OPTIONS[self._bet_idx] != "ALL" and BET_OPTIONS[self._bet_idx] > coins:
                    self._bet_idx -= 1
                bet = BET_OPTIONS[self._bet_idx]
                if bet == "ALL":
                    bet = coins

            self._coins   -= bet
            self._spinning = True

        threading.Thread(target=self._spin_animation, args=(bet,), daemon=True).start()

    def _spin_animation(self, bet):
        final   = random.choices(SYMBOLS, weights=WEIGHTS, k=3)
        stopped = [False, False, False]
        display = list(self._reels)

        for frame in range(SPIN_FRAMES + REEL_STOP * 2 + 1):
            if frame >= SPIN_FRAMES:
                reel_idx = (frame - SPIN_FRAMES) // REEL_STOP
                for i in range(min(reel_idx + 1, 3)):
                    stopped[i] = True
            for i in range(3):
                display[i] = final[i] if stopped[i] else random.choice(SYMBOLS)
            line2 = "Spinning..." if any(not s for s in stopped) else "..."
            gamesense.show(self._reel_str(display), line2)
            time.sleep(SPIN_TICK)

        payout, label = self._calc_payout(final, bet)

        with self._lock:
            self._coins   += payout
            self._reels    = final
            coins          = self._coins
            self._spinning = False
            _save(coins)

        line1 = self._reel_str(final)
        net   = payout - bet if payout > 0 else -bet
        sign  = "+" if net >= 0 else ""

        if label == "JACKPOT": line2 = f"JACKPOT!+{payout}"[:20]
        elif label == "WIN3":  line2 = f"WIN! +{payout}"
        elif label == "WIN2":  line2 = f"Nice! +{payout}"
        else:                  line2 = f"Lose  {sign}{net}"

        gamesense.show(line1, line2)
        time.sleep(2.5)

        # Check if broke
        with self._lock:
            coins   = self._coins
            broke   = coins < BET_OPTIONS[0]

        if broke:
            gamesense.show("Broke!", f"+{PASSIVE_INCOME}/{PASSIVE_INTERVAL}s")
            time.sleep(2)

        self._draw_idle()

    def _calc_payout(self, reels, bet):
        a, b, c = reels
        if a == b == c == "7":
            return bet * PAYOUTS["7"], "JACKPOT"
        if a == b == c:
            return bet * PAYOUTS.get(a, 2), "WIN3"
        if a == b or b == c or a == c:
            return bet * PAYOUT_2, "WIN2"
        return 0, "LOSE"
