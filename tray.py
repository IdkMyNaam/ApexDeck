"""
tray.py
Launches main.py as a hidden background process and shows a system tray icon.
Put a shortcut to THIS file in your startup folder instead of main.py.

Requirements:
    pip install pystray pillow
"""

import sys
import os
import subprocess
import threading
import signal

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    # If pystray/pillow not installed, just run main.py directly visible
    os.execv(sys.executable, [sys.executable, os.path.join(os.path.dirname(__file__), "main.py")])
    sys.exit()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN     = os.path.join(BASE_DIR, "main.py")

# Use pythonw.exe to run main.py with no console window
PYTHONW  = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.exists(PYTHONW):
    PYTHONW = sys.executable  # fallback to regular python

process = None


def create_icon_image():
    """Draw a simple 'A5' icon in SteelSeries orange."""
    size  = 64
    img   = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(img)
    # Background circle
    draw.ellipse([2, 2, size - 2, size - 2], fill=(255, 100, 0, 255))
    # Text
    draw.text((10, 16), "A5", fill=(255, 255, 255, 255))
    return img


def start_main():
    global process
    process = subprocess.Popen(
        [PYTHONW, MAIN],
        cwd=BASE_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    print(f"[tray] started main.py (pid {process.pid})")


def stop(icon, item=None):
    global process
    if process and process.poll() is None:
        print(f"[tray] stopping main.py (pid {process.pid})")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    icon.stop()
    sys.exit(0)


def restart(icon, item):
    global process
    if process and process.poll() is None:
        process.kill()
        process.wait()
    start_main()


def main():
    start_main()

    icon = pystray.Icon(
        name  = "ApexDeck",
        icon  = create_icon_image(),
        title = "ApexDeck",
        menu  = pystray.Menu(
            pystray.MenuItem("ApexDeck", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Restart", restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", stop),
        )
    )

    # Monitor the main process in background — restart if it crashes
    def watchdog():
        while True:
            if process and process.poll() is not None:
                print("[tray] main.py exited unexpectedly, restarting...")
                start_main()
            threading.Event().wait(5)

    threading.Thread(target=watchdog, daemon=True).start()

    icon.run()


if __name__ == "__main__":
    main()
