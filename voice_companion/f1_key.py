"""F1 on every screen (Will, November 6, 2026).

- F1 once goes to the main menu.
- F1 twice quickly opens help for the screen you are on. On the main menu that is the
  user guide.
- Control+F1 opens Favorite apps.

One press waits a moment to see whether a second press follows, so a double press never
leaves the screen first. The window sends 'F1' for one press and 'Double:F1' for two.
"""
import time

# How long to wait for a second press, in seconds. F12 twice uses about the same time.
DOUBLE_PRESS_SECONDS = 0.4
SINGLE = 'F1'
DOUBLE = 'Double:F1'
FAVORITES = 'Ctrl+F1'


class F1Presses:
    """Tells one F1 press from two. press() returns 'Double:F1' at once for a second press,
    or None for a first press; due() returns 'F1' once the wait for a second press is over."""

    def __init__(self, clock=time.monotonic, wait=DOUBLE_PRESS_SECONDS):
        self.clock = clock
        self.wait = wait
        self.first = None

    def press(self):
        now = self.clock()
        if self.first is not None and now - self.first <= self.wait:
            self.first = None
            return DOUBLE
        self.first = now
        return None

    def due(self):
        if self.first is not None and self.clock() - self.first > self.wait:
            self.first = None
            return SINGLE
        return None

    def pending(self):
        return self.first is not None
