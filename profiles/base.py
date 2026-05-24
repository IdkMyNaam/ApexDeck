"""
profiles/base.py
Base class for all profiles. Every profile must inherit this and implement
the methods below.
"""


class BaseProfile:
    # Display name shown in the profile switcher on the OLED
    name: str = "Unnamed Profile"

    def start(self):
        """Called when this profile becomes active. Start any threads/polling here."""
        pass

    def stop(self):
        """Called when switching away from this profile. Clean up threads here."""
        pass

    def on_scroll_up(self):
        """Roller scrolled up."""
        pass

    def on_scroll_down(self):
        """Roller scrolled down."""
        pass

    def on_roller_click(self):
        """Roller button clicked (single press)."""
        pass

    def on_button_press(self):
        """
        OLED button pressed (short press).
        Multi-press logic (double/triple) is handled inside each profile
        using the press counter below if needed.
        """
        pass

    def update_oled(self):
        """
        Called by the main loop to refresh the OLED.
        Profiles that poll data (e.g. Spotify, clock) push their own
        updates internally, but this can be used as a fallback tick.
        """
        pass
