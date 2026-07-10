"""
profiles/spotify.py
Profile 1 — Spotify now playing, volume control, mute, play/pause/skip/back.

Controls:
  Roller scroll up/down  → Spotify volume +/- step
  Roller click           → Mute / unmute
  OLED button x1         → Play / pause
  OLED button x2         → Next track
  OLED button x3         → Previous track
"""

import threading
import time

import gamesense
from profiles.base import BaseProfile


def _volume_bar(pct: int) -> str:
    filled = round(pct / 10)
    return "█" * filled + "░" * (10 - filled)


class SpotifyProfile(BaseProfile):
    name = "Spotify"

    def __init__(self, sp, config: dict):
        """
        sp     — an authenticated spotipy.Spotify instance
        config — the 'settings' dict from config.json
        """
        self._sp = sp
        self._volume_step = config.get("volume_step", 5)
        self._display_secs = config.get("volume_display_seconds", 3)
        self._poll_interval = config.get("poll_interval", 2.0)
        self._press_window = config.get("multi_press_window_ms", 500) / 1000.0

        self._state = {
            "artist":          "",
            "track":           "",
            "volume":          50,
            "muted":           False,
            "vol_before_mute": 50,
            "showing_temp":    False,
            "temp_timer":      None,
        }
        self._lock = threading.Lock()

        self._poll_thread = None
        self._running = False

        # Multi-press tracking for OLED button
        self._press_count = 0
        self._press_timer = None
        self._press_lock = threading.Lock()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._gen = getattr(self, "_gen", 0) + 1
        self._poll_thread = threading.Thread(target=self._poll_loop, args=(self._gen,), daemon=True)
        self._poll_thread.start()

    def stop(self):
        self._running = False
        # Clear any pending multi-press timer so it doesn't fire after switching profiles
        with self._press_lock:
            if self._press_timer:
                self._press_timer.cancel()
                self._press_timer = None
            self._press_count = 0
        with self._lock:
            if self._state["temp_timer"]:
                self._state["temp_timer"].cancel()

    # ── controls ──────────────────────────────────────────────────────────────

    def on_scroll_up(self):
        with self._lock:
            new_vol = self._state["volume"] + self._volume_step
        threading.Thread(target=self._set_volume, args=(new_vol,), daemon=True).start()
        threading.Thread(target=self._show_volume, daemon=True).start()

    def on_scroll_down(self):
        with self._lock:
            new_vol = self._state["volume"] - self._volume_step
        threading.Thread(target=self._set_volume, args=(new_vol,), daemon=True).start()
        threading.Thread(target=self._show_volume, daemon=True).start()

    def on_roller_click(self):
        threading.Thread(target=self._toggle_mute, daemon=True).start()

    def on_button_press(self):
        with self._press_lock:
            self._press_count += 1
            if self._press_timer:
                self._press_timer.cancel()

            def fire():
                with self._press_lock:
                    count = self._press_count
                    self._press_count = 0
                    self._press_timer = None
                threading.Thread(target=self._handle_presses, args=(count,), daemon=True).start()

            t = threading.Timer(self._press_window, fire)
            self._press_timer = t
            t.start()

    # ── internal ──────────────────────────────────────────────────────────────

    def _get_device_id(self):
        try:
            for d in self._sp.devices().get("devices", []):
                if d.get("is_active"):
                    return d["id"]
            devs = self._sp.devices().get("devices", [])
            return devs[0]["id"] if devs else None
        except Exception:
            return None

    def _set_volume(self, vol: int):
        vol = max(0, min(100, vol))
        try:
            self._sp.volume(vol, device_id=self._get_device_id())
            with self._lock:
                self._state["volume"] = vol
                self._state["muted"]  = (vol == 0)
            print(f"[spotify] volume → {vol}%")
        except Exception as e:
            print(f"[spotify] volume error: {e}")

    def _show_volume(self):
        with self._lock:
            vol = self._state["volume"]
            self._state["showing_temp"] = True
            if self._state["temp_timer"]:
                self._state["temp_timer"].cancel()
        gamesense.show(f"Volume  {vol}%", _volume_bar(vol))

        def revert():
            with self._lock:
                self._state["showing_temp"] = False
                artist = self._state["artist"]
                track  = self._state["track"]
            gamesense.show(artist, track)

        t = threading.Timer(self._display_secs, revert)
        with self._lock:
            self._state["temp_timer"] = t
        t.start()

    def _toggle_mute(self):
        with self._lock:
            muted = self._state["muted"]
            vol   = self._state["volume"]
            saved = self._state["vol_before_mute"]

        if muted:
            restore = saved if saved > 0 else 30
            self._set_volume(restore)
            with self._lock:
                self._state["muted"] = False
            self._show_volume()
        else:
            with self._lock:
                self._state["vol_before_mute"] = vol
            self._set_volume(0)
            with self._lock:
                self._state["muted"] = True
                if self._state["temp_timer"]:
                    self._state["temp_timer"].cancel()
                self._state["showing_temp"] = True
            gamesense.show("Muted", "Click to unmute")

            def revert():
                with self._lock:
                    self._state["showing_temp"] = False
                    artist = self._state["artist"]
                    track  = self._state["track"]
                gamesense.show(artist, track)

            t = threading.Timer(3, revert)
            with self._lock:
                self._state["temp_timer"] = t
            t.start()

    def _handle_presses(self, count: int):
        try:
            if count == 1:
                pb = self._sp.current_playback()
                if pb and pb.get("is_playing"):
                    self._sp.pause_playback()
                    gamesense.show("Paused", "")
                else:
                    self._sp.start_playback()
                    gamesense.show("Playing", "")
                print("[spotify] play/pause")
            elif count == 2:
                self._sp.next_track()
                gamesense.show("Next track >>", "")
                print("[spotify] next track")
            elif count >= 3:
                self._sp.previous_track()
                gamesense.show("<< Prev track", "")
                print("[spotify] previous track")
        except Exception as e:
            print(f"[spotify] button error (count={count}): {e}")

        def revert():
            with self._lock:
                self._state["showing_temp"] = False
                artist = self._state["artist"]
                track  = self._state["track"]
            gamesense.show(artist, track)

        threading.Timer(2, revert).start()

    def _poll_loop(self, gen):
        while self._running and gen == getattr(self, "_gen", gen):
            try:
                pb = self._sp.current_playback()
                if pb and pb.get("item"):
                    artist = pb["item"]["artists"][0]["name"]
                    track  = pb["item"]["name"]
                    vol    = pb.get("device", {}).get("volume_percent", self._state["volume"])
                    with self._lock:
                        self._state["artist"] = artist
                        self._state["track"]  = track
                        self._state["volume"] = vol
                        self._state["muted"]  = (vol == 0)
                        showing = self._state["showing_temp"]
                    if not showing:
                        gamesense.show(artist, track)
                else:
                    with self._lock:
                        showing = self._state["showing_temp"]
                    if not showing:
                        gamesense.show("Spotify", "Not playing")
            except Exception as e:
                print(f"[spotify] poll error: {e}")
            time.sleep(self._poll_interval)
