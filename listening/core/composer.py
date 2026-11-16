"""When a dictated T3 Code response has landed in the message box.

T3 Code's own dictation puts the text in the message box some time after the
recording is stopped (it transcribes, then tidies the text up), and doesn't
send it. The Talon glue reads the message box every so often and asks this
whether it's time to press Enter.
"""

from typing import Optional

SETTLE = 0.7  # seconds the new text must stay unchanged before it's sent
GIVE_UP_AFTER = 30.0  # seconds; after that the text is left unsent


class SendWatch:
    def __init__(self, at_stop: Optional[str], now: float):
        """`at_stop` is the message box text when the recording was stopped
        (None if it couldn't be read)."""
        self._at_stop = (at_stop or "").strip()
        self._started = now
        self._candidate: Optional[str] = None
        self._since = now

    def poll(self, text: Optional[str], now: float) -> str:
        """"send", "wait" or "give_up", given the message box text right now
        (None if it can't be read)."""
        current = (text or "").strip()
        if text is not None and current and current != self._at_stop:
            if current != self._candidate:
                self._candidate, self._since = current, now
            elif now - self._since >= SETTLE:
                return "send"
        else:
            self._candidate = None
        if now - self._started > GIVE_UP_AFTER:
            return "give_up"
        return "wait"
