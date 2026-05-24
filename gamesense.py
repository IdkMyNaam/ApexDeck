"""
gamesense.py
All communication with the SteelSeries GameSense API.
"""

import json
import os
import requests

CORE_PROPS_PATH = os.path.join(
    os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
    "SteelSeries", "SteelSeries Engine 3", "coreProps.json"
)

GAME = "APEXSPOTIFY"


def _get_address() -> str:
    try:
        with open(CORE_PROPS_PATH) as f:
            data = json.load(f)
        addr = data.get("address", "127.0.0.1:54235")
        print(f"[gamesense] address: {addr}")
        return addr
    except Exception as e:
        print(f"[gamesense] coreProps error ({e}), using default")
        return "127.0.0.1:54235"


_base = f"http://{_get_address()}"


def post(endpoint: str, payload: dict):
    try:
        r = requests.post(f"{_base}/{endpoint}", json=payload, timeout=2)
        return r
    except Exception as e:
        print(f"[gamesense] {endpoint} failed: {e}")
        return None


def register():
    """Register the game and bind the OLED screen event."""
    post("remove_game", {"game": GAME})

    r = post("game_metadata", {
        "game": GAME,
        "game_display_name": "Apex Spotify",
        "developer": "you",
        "deinitialize_timer_length_ms": 60000
    })
    print(f"[gamesense] register → {r.status_code if r else 'failed'}")

    r = post("bind_game_event", {
        "game": GAME,
        "event": "SHOW",
        "value_optional": True,
        "data_fields": [
            {"context-frame-key": "line1", "label": "Line 1"},
            {"context-frame-key": "line2", "label": "Line 2"}
        ],
        "handlers": [{
            "device-type": "screened-128x40",
            "zone": "one",
            "mode": "screen",
            "datas": [{
                "lines": [
                    {"has-text": True, "context-frame-key": "line1"},
                    {"has-text": True, "context-frame-key": "line2"}
                ]
            }]
        }]
    })
    print(f"[gamesense] bind → {r.status_code if r else 'failed'}")


def show(line1: str, line2: str):
    """Display two lines of text on the OLED."""
    post("game_event", {
        "game": GAME,
        "event": "SHOW",
        "data": {
            "value": 1,
            "frame": {
                "line1": line1[:20],
                "line2": line2[:20]
            }
        }
    })


def heartbeat():
    """Send a heartbeat so GameSense doesn't go idle."""
    post("game_heartbeat", {"game": GAME})


def unregister():
    post("remove_game", {"game": GAME})
