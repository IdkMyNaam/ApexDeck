"""
main.py
Entry point. Manages the key hook, profile switcher, and heartbeat.

Hold the ROLLER CLICK for 2 seconds → profile switcher appears on OLED
  Scroll up/down to move through profiles
  Press OLED button to confirm selection
  Hold roller click 2 seconds again to cancel
"""

import json
import os
import signal
import sys
import threading
import time

import keyboard
import spotipy
from spotipy.oauth2 import SpotifyOAuth

import gamesense
from profiles.spotify import SpotifyProfile
from profiles.clock import ClockProfile
from profiles.discord import DiscordProfile
from profiles.slots import SlotsProfile

# ── Scan codes (confirmed from keydetect) ─────────────────────────────────────
SC_VOL_UP    = -175
SC_VOL_DOWN  = -174
SC_VOL_MUTE  = -173
SC_PLAY_PAUSE = -179
HANDLED_SC = {SC_VOL_UP, SC_VOL_DOWN, SC_VOL_MUTE, SC_PLAY_PAUSE}

# ── Load config ───────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_active_profile(index: int):
    cfg = load_config()
    cfg["active_profile"] = index
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)

# ── Profile switcher state ────────────────────────────────────────────────────
AUTO_SELECT_SECONDS = 1.5    # seconds of no scrolling before auto-confirming

switcher = {
    "active":     False,   # are we in the switcher UI right now?
    "cursor":     0,       # which profile is highlighted
    "auto_timer": None,    # fires after idle to auto-confirm
}
switcher_lock = threading.Lock()

# ── Hold detection for OLED button ───────────────────────────────────────────
hold = {
    "press_time": None,      # when the button was pressed down
    "hold_timer": None,      # fires after hold_duration to enter switcher
    "held":       False,     # did we already trigger the hold action?
}
hold_lock = threading.Lock()

# ── Globals filled in main() ──────────────────────────────────────────────────
profiles     = []
active_index = 0
cfg_settings = {}


def current_profile():
    return profiles[active_index]


# ── Profile switcher UI ───────────────────────────────────────────────────────

def enter_switcher():
    with switcher_lock:
        switcher["active"] = True
        switcher["cursor"] = active_index
        switcher["auto_timer"] = None
    current_profile().stop()
    _draw_switcher()
    _reset_auto_select()
    print("[switcher] opened")

def exit_switcher(confirm: bool):
    global active_index
    with switcher_lock:
        if switcher["auto_timer"]:
            switcher["auto_timer"].cancel()
            switcher["auto_timer"] = None
        switcher["active"] = False
        selected = switcher["cursor"]

    if confirm:
        active_index = selected
        save_active_profile(active_index)
        print(f"[switcher] switched to profile {active_index}: {profiles[active_index].name}")

    profiles[active_index].start()
    print(f"[switcher] closed, running: {profiles[active_index].name}")

def _draw_switcher():
    with switcher_lock:
        cursor = switcher["cursor"]
    total   = len(profiles)
    name    = profiles[cursor].name
    counter = f"{cursor + 1}/{total}"
    gamesense.show(f"> {name}", counter)


def _reset_auto_select():
    """Restart the idle timer. Called every time the cursor moves."""
    with switcher_lock:
        if switcher["auto_timer"]:
            switcher["auto_timer"].cancel()
        t = threading.Timer(AUTO_SELECT_SECONDS, lambda: exit_switcher(confirm=True))
        switcher["auto_timer"] = t
        t.start()


# ── Key hook ──────────────────────────────────────────────────────────────────

def on_key_event(e):
    sc = e.scan_code
    if sc not in HANDLED_SC:
        return True   # pass all other keys through

    # Always suppress our keys regardless of mode
    if e.event_type == keyboard.KEY_UP:
        if sc == SC_VOL_MUTE:
            with switcher_lock:
                in_sw = switcher["active"]
            if not in_sw:
                _on_mute_release_normal()
        return False

    if e.event_type != keyboard.KEY_DOWN:
        return False

    with switcher_lock:
        in_switcher = switcher["active"]

    if in_switcher:
        # In switcher: scroll moves cursor, OLED button confirms, roller hold cancels
        if sc == SC_VOL_UP:
            with switcher_lock:
                switcher["cursor"] = (switcher["cursor"] - 1) % len(profiles)
            _draw_switcher()
            _reset_auto_select()
        elif sc == SC_VOL_DOWN:
            with switcher_lock:
                switcher["cursor"] = (switcher["cursor"] + 1) % len(profiles)
            _draw_switcher()
            _reset_auto_select()
        elif sc == SC_VOL_MUTE:
            # Roller short-click → confirm immediately
            exit_switcher(confirm=True)
        elif sc == SC_PLAY_PAUSE:
            # OLED button → confirm immediately
            exit_switcher(confirm=True)
    else:
        # Normal mode — route to the active profile
        if sc == SC_VOL_UP:
            threading.Thread(target=current_profile().on_scroll_up, daemon=True).start()
        elif sc == SC_VOL_DOWN:
            threading.Thread(target=current_profile().on_scroll_down, daemon=True).start()
        elif sc == SC_VOL_MUTE:
            _on_mute_down_normal()
        elif sc == SC_PLAY_PAUSE:
            threading.Thread(target=current_profile().on_button_press, daemon=True).start()

    return False


def _on_mute_down_normal():
    """Roller click in normal mode: short press = mute, hold 2s = open switcher."""
    hold_dur = cfg_settings.get("hold_duration_seconds", 2.0)
    with hold_lock:
        hold["held"] = False
        if hold["hold_timer"]:
            hold["hold_timer"].cancel()

        def trigger_hold():
            with hold_lock:
                hold["held"] = True
            enter_switcher()

        t = threading.Timer(hold_dur, trigger_hold)
        hold["hold_timer"] = t
        t.start()


def _on_mute_release_normal():
    """Roller released in normal mode: short press = mute."""
    with hold_lock:
        if hold["hold_timer"]:
            hold["hold_timer"].cancel()
            hold["hold_timer"] = None
        was_held = hold["held"]
        hold["held"] = False

    if not was_held:
        threading.Thread(target=current_profile().on_roller_click, daemon=True).start()


def _on_mute_down_switcher():
    """Roller click inside switcher: hold to cancel."""
    hold_dur = cfg_settings.get("hold_duration_seconds", 2.0)
    with hold_lock:
        hold["held"] = False
        if hold["hold_timer"]:
            hold["hold_timer"].cancel()

        def trigger_cancel():
            with hold_lock:
                hold["held"] = True
            exit_switcher(confirm=False)

        t = threading.Timer(hold_dur, trigger_cancel)
        hold["hold_timer"] = t
        t.start()


def _on_mute_release_switcher():
    """Roller released inside switcher without holding → do nothing (not a cancel)."""
    with hold_lock:
        if hold["hold_timer"]:
            hold["hold_timer"].cancel()
            hold["hold_timer"] = None
        hold["held"] = False


# ── Heartbeat ────────────────────────────────────────────────────────────────

def heartbeat_loop():
    while True:
        gamesense.heartbeat()
        time.sleep(10)


# ── Shutdown ──────────────────────────────────────────────────────────────────

def shutdown(sig=None, frame=None):
    print("\n[*] Shutting down...")
    try:
        current_profile().stop()
    except Exception:
        pass
    gamesense.show("Apex Profiles", "Stopped")
    gamesense.unregister()
    sys.exit(0)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global profiles, active_index, cfg_settings

    cfg = load_config()
    cfg_settings  = cfg.get("settings", {})
    spotify_cfg   = cfg.get("spotify", {})
    discord_cfg   = cfg.get("discord", {})
    active_index  = cfg.get("active_profile", 0)

    if spotify_cfg.get("client_id") == "YOUR_SPOTIFY_CLIENT_ID_HERE":
        print("Please fill in your Spotify credentials in config.json")
        sys.exit(1)

    # Build Spotify client
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=spotify_cfg["client_id"],
        client_secret=spotify_cfg["client_secret"],
        redirect_uri=spotify_cfg["redirect_uri"],
        scope="user-read-playback-state user-modify-playback-state",
        open_browser=True,
        cache_path=os.path.join(os.path.dirname(__file__), ".spotify_cache")
    ))

    # Register all profiles here — add more to this list to add more profiles
    profiles = [
        SpotifyProfile(sp, cfg_settings),
        ClockProfile(),
        DiscordProfile(
            discord_cfg.get("client_id", ""),
            discord_cfg.get("client_secret", ""),
            discord_cfg.get("redirect_uri", "http://127.0.0.1:8888/callback"),
        ),
        SlotsProfile(),
    ]

    active_index = min(active_index, len(profiles) - 1)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("[*] Registering with SteelSeries GG...")
    gamesense.register()
    gamesense.show("Apex Profiles", "Starting...")

    print("[*] Connecting to Spotify...")
    try:
        sp.current_playback()
    except Exception as e:
        print(f"Spotify auth error: {e}")
        sys.exit(1)

    print(f"[*] Starting profile: {profiles[active_index].name}")
    profiles[active_index].start()

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    keyboard.hook(on_key_event, suppress=True)

    print("[*] Running. Press Ctrl+C to quit.")
    print(f"    Active profile: {profiles[active_index].name}")
    print(f"    Hold ROLLER CLICK {cfg_settings.get('hold_duration_seconds', 2.0)}s to switch profiles")
    print(f"    Profiles: {', '.join(p.name for p in profiles)}")

    keyboard.wait()


if __name__ == "__main__":
    main()
