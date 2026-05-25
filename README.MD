# ApexDeck

A Python app that controls the SteelSeries Apex 5 OLED screen and roller, with swappable profiles.

## Profiles

**Spotify** — shows now playing artist and track name. Scroll to change Spotify volume (not Windows volume), roller click to mute/unmute, OLED button for play/pause, double press to skip, triple press to go back.

**Clock** — shows current time and date. Roller click toggles between 24h and 12h format.

**Discord** — shows your current voice channel and who's in it. Members list auto-scrolls (marquee) if too many to fit. OLED button to mute/unmute, roller click to deafen/undeafen, scroll to manually browse members. DM notifications flash on screen for 4 seconds.

**Slots** — a slot machine. Scroll to change bet, OLED button or roller click to spin. Coins are saved between sessions and passively regenerate over time. If you go broke you have to wait for passive income to build back up.

## Requirements

- Windows (SteelSeries GG must be running)
- Python 3.10+
- SteelSeries Apex 5 keyboard
- Spotify

## Setup

**1. Install dependencies**
```
pip install spotipy requests keyboard pypresence
```

**2. Copy config**

Copy `config.json.example` to `config.json` and fill in your credentials.

**3. Set up Spotify**
- Go to https://developer.spotify.com/dashboard → **Create App**
- Set Redirect URI to: `http://127.0.0.1:8888/callback`
- Copy your **Client ID** and **Client Secret** into `config.json`
- First run opens a browser for login — automatic after that

**4. Set up Discord**
- Go to https://discord.com/developers/applications → **New Application**
- Under **OAuth2** → add Redirect URI: `http://127.0.0.1:8888/callback`
- Copy **Client ID** and **Client Secret** into `config.json`
- First run opens a browser for login — token is cached after that, no re-auth needed

**5. Run**
```
python main.py
```

**6. Optional: run on Windows startup**

Press `Win+R`, type `shell:startup`, drop a shortcut to `main.py` there.

## Controls

### Global

| Input | Action |
|---|---|
| Roller click (hold 2s) | Open profile switcher |

### Profile switcher

| Input | Action |
|---|---|
| Scroll up / down | Move between profiles |
| Roller click or OLED button | Confirm selection |
| Auto-selects after 1.5s of no scrolling | |

### Spotify profile

| Input | Action |
|---|---|
| Scroll up / down | Volume +/- 5% (Spotify only, not Windows) |
| Roller click | Mute / unmute |
| OLED button ×1 | Play / pause |
| OLED button ×2 | Next track |
| OLED button ×3 | Previous track |

### Clock profile

| Input | Action |
|---|---|
| Roller click | Toggle 12h / 24h format |

### Discord profile

| Input | Action |
|---|---|
| OLED button | Mute / unmute |
| Roller click | Deafen / undeafen |
| Scroll up / down | Browse members list |

### Slots profile

| Input | Action |
|---|---|
| OLED button or roller click | Spin |
| Scroll up | Increase bet |
| Scroll down | Decrease bet |

Bet options: 1 → 5 → 10 → 25 → 50 → 100 → ALL IN

| Result | Payout |
|---|---|
| Three 7s | 100× bet (jackpot) |
| Three $ | 20× bet |
| Three BAR | 10× bet |
| Three *** | 5× bet |
| Three o | 3× bet |
| Any pair | 1× bet (break even) |

Coins save between sessions. Passive income: +2 coins every 30 seconds while the app is running. Offline income is calculated when you relaunch.

## Project structure

```
ApexDeck/
├── main.py                # entry point, key hook, profile switcher
├── gamesense.py           # SteelSeries GameSense OLED API wrapper
├── config.json            # your credentials and settings (gitignored)
├── config.json.example    # template to copy from
├── profiles/
│   ├── base.py            # base class all profiles inherit
│   ├── spotify.py         # Spotify now playing + volume control
│   ├── clock.py           # clock and date display
│   ├── discord.py         # Discord voice channel + DM notifications
│   └── slots.py           # slot machine
└── README.md
```

## Settings (config.json)

| Key | Default | Description |
|---|---|---|
| `volume_step` | 5 | % change per scroll tick (Spotify) |
| `volume_display_seconds` | 3 | How long volume bar stays on OLED |
| `poll_interval` | 2.0 | Seconds between Spotify API polls |
| `multi_press_window_ms` | 500 | Window to register double/triple press |
| `hold_duration_seconds` | 2.0 | Seconds to hold roller for profile switcher |

## Adding a new profile

1. Create `profiles/yourprofile.py` and inherit from `BaseProfile`
2. Implement whichever methods you need (`on_button_press`, `on_scroll_up`, etc.)
3. Import and add it to the `profiles` list in `main.py`

```python
from profiles.yourprofile import YourProfile

profiles = [
    SpotifyProfile(sp, cfg_settings),
    ClockProfile(),
    DiscordProfile(...),
    SlotsProfile(),
    YourProfile(),   # <- add here
]
```

### BaseProfile methods

| Method | Trigger |
|---|---|
| `start()` | Profile becomes active |
| `stop()` | Profile is switched away from |
| `on_button_press()` | OLED button pressed |
| `on_roller_click()` | Roller clicked (short press) |
| `on_scroll_up()` | Roller scrolled up |
| `on_scroll_down()` | Roller scrolled down |

## Customising the slot machine

At the top of `profiles/slots.py`:

```python
SYMBOLS  = ["7", "$", "BAR", "***", "o"]   # max 3 chars each
PAYOUTS  = {"7": 100, "$": 20, ...}         # 3-of-a-kind multiplier per symbol
WEIGHTS  = [5, 15, 20, 25, 35]             # spawn chance (lower = rarer)
PAYOUT_2 = 1                               # multiplier for any pair

PASSIVE_INCOME   = 2    # coins earned per tick
PASSIVE_INTERVAL = 30   # seconds between ticks
```

`SYMBOLS`, `PAYOUTS`, and `WEIGHTS` must always have the same number of entries.
