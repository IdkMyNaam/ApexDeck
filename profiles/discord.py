"""
profiles/discord.py
Profile 3 - Discord Voice Channel

Uses pypresence.Client (sync) running entirely in a background thread.
All RPC calls happen in that thread — no asyncio conflicts.

Controls:
  OLED button      -> Toggle self-mute
  Roller click     -> Toggle self-deafen
  Scroll up/down   -> Manual scroll / marquee through VC members
"""

import os
import threading
import time
import webbrowser
import http.server
import urllib.parse
import requests as req

import gamesense
from profiles.base import BaseProfile

try:
    from pypresence import Client as DiscordClient
    PYPRESENCE_AVAILABLE = True
except ImportError:
    PYPRESENCE_AVAILABLE = False

MARQUEE_INTERVAL = 0.4
MARQUEE_PAUSE    = 2.0
DM_DISPLAY_SECS  = 4.0
CACHE_FILE       = os.path.join(os.path.dirname(__file__), "..", ".discord_token")


# ── Token cache ───────────────────────────────────────────────────────────────

def _save_token(token):
    try:
        with open(CACHE_FILE, "w") as f:
            f.write(token)
    except Exception:
        pass

def _load_token():
    try:
        with open(CACHE_FILE) as f:
            t = f.read().strip()
            return t if t else None
    except Exception:
        return None

def _clear_token():
    try:
        os.remove(CACHE_FILE)
    except Exception:
        pass


# ── OAuth2 ────────────────────────────────────────────────────────────────────

_auth_code = None

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _auth_code = params["code"][0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
    def log_message(self, *args):
        pass

def _fetch_new_token(client_id, client_secret, redirect_uri):
    global _auth_code
    _auth_code = None
    scopes = "rpc rpc.voice.read rpc.voice.write rpc.notifications.read"
    auth_url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(scopes)}"
    )
    server = http.server.HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    print("[discord] Opening browser for authorization...")
    webbrowser.open(auth_url)
    t.join(timeout=60)
    server.server_close()
    if not _auth_code:
        return None
    try:
        resp = req.post("https://discord.com/api/oauth2/token", data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "grant_type":    "authorization_code",
            "code":          _auth_code,
            "redirect_uri":  redirect_uri,
        })
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if token:
            _save_token(token)
        return token
    except Exception as e:
        print(f"[discord] token exchange failed: {e}")
        return None


# ── Profile ───────────────────────────────────────────────────────────────────

class DiscordProfile(BaseProfile):
    name = "Discord"

    def __init__(self, client_id, client_secret, redirect_uri):
        self._client_id     = client_id
        self._client_secret = client_secret
        self._redirect_uri  = redirect_uri

        self._muted    = False
        self._deafened = False
        self._channel  = None
        self._members  = []

        self._marquee_offset = 0
        self._marquee_dir    = 1
        self._marquee_pause  = 0

        self._showing_status = False
        self._status_timer   = None
        self._lock           = threading.Lock()

        self._running  = False
        self._rpc      = None
        self._thread   = None

        # Actions queued from key presses, consumed in the worker thread
        self._action_queue = []
        self._action_event = threading.Event()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if not PYPRESENCE_AVAILABLE:
            gamesense.show("Discord", "pip install pypresence")
            return
        if not self._client_id or not self._client_secret:
            gamesense.show("Discord", "No credentials")
            return
        self._running = True
        self._gen = getattr(self, "_gen", 0) + 1
        self._thread  = threading.Thread(target=self._worker, args=(self._gen,), daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._action_event.set()  # unblock the wait
        if self._rpc:
            try:
                self._rpc.close()
            except Exception:
                pass
            self._rpc = None

    # ── controls ──────────────────────────────────────────────────────────────

    def on_button_press(self):
        self._enqueue("mute")

    def on_roller_click(self):
        self._enqueue("deafen")

    def on_scroll_up(self):
        with self._lock:
            self._marquee_offset = max(0, self._marquee_offset - 1)
        self._draw_vc()

    def on_scroll_down(self):
        with self._lock:
            members  = list(self._members)
            deafened = self._deafened
            muted    = self._muted
        full  = self._build_members_str(members)
        ind   = "[D] " if deafened else ("[M] " if muted else "")
        width = 20 - len(ind)
        max_o = max(0, len(full) - width)
        with self._lock:
            self._marquee_offset = min(max_o, self._marquee_offset + 1)
        self._draw_vc()

    def _enqueue(self, action):
        with self._lock:
            self._action_queue.append(action)
        self._action_event.set()

    # ── OLED ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_members_str(members):
        return "  ".join(m[:12] for m in members) if members else "Empty"

    def _draw_vc(self):
        with self._lock:
            showing  = self._showing_status
            channel  = self._channel
            members  = list(self._members)
            muted    = self._muted
            deafened = self._deafened
            offset   = self._marquee_offset

        if showing:
            return
        if not channel:
            gamesense.show("Discord", "Not in VC")
            return

        line1      = ("# " + channel)[:20]
        indicators = "[D] " if deafened else ("[M] " if muted else "")
        width      = 20 - len(indicators)
        full       = self._build_members_str(members)

        if len(full) <= width:
            line2 = indicators + full
        else:
            window = full[offset: offset + width].ljust(width)
            if offset + width < len(full):
                window = window[:width - 1] + ">"
            if offset > 0:
                window = "<" + window[1:]
            line2 = indicators + window

        gamesense.show(line1, line2)

    def _show_status_briefly(self, line1, line2, duration=2.5):
        with self._lock:
            self._showing_status = True
            if self._status_timer:
                self._status_timer.cancel()
        gamesense.show(line1, line2)
        def revert():
            with self._lock:
                self._showing_status = False
            self._draw_vc()
        t = threading.Timer(duration, revert)
        with self._lock:
            self._status_timer = t
        t.start()

    def _status_line(self):
        with self._lock:
            if self._deafened: return "[D]"
            if self._muted:    return "[M]"
        return "Active"

    def _tick_marquee(self):
        with self._lock:
            if self._showing_status:
                return
            members  = list(self._members)
            deafened = self._deafened
            muted    = self._muted

        full  = self._build_members_str(members)
        ind   = "[D] " if deafened else ("[M] " if muted else "")
        width = 20 - len(ind)

        if len(full) <= width:
            return

        max_o = len(full) - width

        with self._lock:
            if self._marquee_pause > 0:
                self._marquee_pause -= 1
                return
            self._marquee_offset += self._marquee_dir
            if self._marquee_offset >= max_o:
                self._marquee_offset = max_o
                self._marquee_dir    = -1
                self._marquee_pause  = int(MARQUEE_PAUSE / MARQUEE_INTERVAL)
            elif self._marquee_offset <= 0:
                self._marquee_offset = 0
                self._marquee_dir    = 1
                self._marquee_pause  = int(MARQUEE_PAUSE / MARQUEE_INTERVAL)

        self._draw_vc()

    # ── sync RPC calls (all run inside _worker thread) ────────────────────────

    def _do_mute(self):
        with self._lock:
            new_mute = not self._muted
        try:
            self._rpc.set_voice_settings(mute=new_mute)
            with self._lock:
                self._muted = new_mute
            self._show_status_briefly("Muted" if new_mute else "Unmuted", self._status_line())
            print(f"[discord] mute -> {new_mute}")
        except Exception as e:
            print(f"[discord] mute error: {e}")

    def _do_deafen(self):
        with self._lock:
            new_deaf = not self._deafened
            new_mute = new_deaf or self._muted
        try:
            self._rpc.set_voice_settings(mute=new_mute, deaf=new_deaf)
            with self._lock:
                self._deafened = new_deaf
                self._muted    = new_mute
            self._show_status_briefly(
                "Deafened" if new_deaf else "Undeafened",
                self._status_line()
            )
            print(f"[discord] deafen -> {new_deaf}")
        except Exception as e:
            print(f"[discord] deafen error: {e}")

    def _refresh_vc(self):
        try:
            result = self._rpc.get_selected_voice_channel()
            data = result.get("data") if isinstance(result, dict) else None
            if data:
                members = [
                    vs.get("nick") or vs.get("user", {}).get("username", "?")
                    for vs in data.get("voice_states", [])
                ]
                with self._lock:
                    self._channel        = data.get("name", "Unknown")
                    self._members        = members
                    self._marquee_offset = 0
                    self._marquee_dir    = 1
                    self._marquee_pause  = int(MARQUEE_PAUSE / MARQUEE_INTERVAL)
            else:
                with self._lock:
                    if not self._showing_status:
                        self._channel        = None
                        self._members        = []
                        self._marquee_offset = 0
        except Exception as e:
            print(f"[discord] refresh VC error: {e}")
        self._draw_vc()

    def _refresh_voice_settings(self):
        try:
            result = self._rpc.get_voice_settings()
            data = result.get("data") if isinstance(result, dict) else None
            if data:
                with self._lock:
                    self._muted    = data.get("mute", False)
                    self._deafened = data.get("deaf", False)
        except Exception as e:
            print(f"[discord] refresh voice settings error: {e}")

    def _on_vc_event(self, data):
        self._refresh_vc()

    def _on_notification(self, data):
        try:
            payload = data.get("data", data) if isinstance(data, dict) else {}
            body    = payload.get("body", "")
            title   = payload.get("title", "")
            sender  = title.split("(")[0].strip() or "DM"
            line1   = f"DM: {sender}"[:20]
            line2   = body[:20]
            print(f"[discord] notification from {sender}: {body}")
            self._show_status_briefly(line1, line2, duration=DM_DISPLAY_SECS)
        except Exception as e:
            print(f"[discord] notification error: {e}")

    # ── worker thread ─────────────────────────────────────────────────────────

    def _worker(self, gen):
        # Get token (cached or fresh)
        token = _load_token()
        if not token:
            gamesense.show("Discord", "Authorizing...")
            token = _fetch_new_token(self._client_id, self._client_secret, self._redirect_uri)
        else:
            print("[discord] using cached token")

        if not token:
            gamesense.show("Discord", "Auth failed")
            return

        # Connect
        try:
            self._rpc = DiscordClient(self._client_id)
            self._rpc.start()
        except Exception as e:
            print(f"[discord] connect failed: {e}")
            gamesense.show("Discord", "Open Discord!")
            return

        # Authenticate — if cached token fails, re-auth once
        try:
            self._rpc.authenticate(token)
        except Exception as e:
            print(f"[discord] cached token failed ({e}), re-authorizing...")
            _clear_token()
            token = _fetch_new_token(self._client_id, self._client_secret, self._redirect_uri)
            if not token:
                gamesense.show("Discord", "Auth failed")
                return
            try:
                self._rpc.authenticate(token)
            except Exception as e2:
                print(f"[discord] authenticate failed: {e2}")
                gamesense.show("Discord", "Auth failed")
                return

        print("[discord] connected")
        gamesense.show("Discord", "Connected!")

        # Subscribe to events (sync Client uses regular def handlers)
        try:
            self._rpc.register_event("VOICE_CHANNEL_SELECT", self._on_vc_event)
        except Exception as e:
            print(f"[discord] VC subscribe (non-fatal): {e}")
        try:
            self._rpc.register_event("NOTIFICATION_CREATE", self._on_notification)
        except Exception as e:
            print(f"[discord] notification subscribe (non-fatal): {e}")

        # Initial state
        self._refresh_vc()
        self._refresh_voice_settings()

        last_poll    = time.time()
        last_marquee = time.time()

        while self._running and gen == getattr(self, "_gen", gen):
            now = time.time()

            # Process queued actions (mute/deafen from key presses)
            with self._lock:
                actions = self._action_queue[:]
                self._action_queue.clear()
            for action in actions:
                if action == "mute":
                    self._do_mute()
                elif action == "deafen":
                    self._do_deafen()

            # Marquee tick
            if now - last_marquee >= MARQUEE_INTERVAL:
                self._tick_marquee()
                last_marquee = now

            # Poll every 5s
            if now - last_poll >= 5:
                self._refresh_vc()
                self._refresh_voice_settings()
                last_poll = now

            # Short sleep — keeps loop responsive without hammering CPU
            self._action_event.wait(timeout=0.1)
            self._action_event.clear()
