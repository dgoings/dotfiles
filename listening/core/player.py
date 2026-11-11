"""Playback state machine for listening mode.

Pure logic: each control or store event returns a list of effects for the Talon
glue to carry out. Session state is re-read from the store on every call (hooks
write it concurrently) and saved straight after each change.
"""

from dataclasses import dataclass

from .store import Reply, SessionState, Store

CANT_TELL = "I can't tell which Claude session is in front."
NOTHING_NEW = "Nothing new here."
EVERYTHING = " That's everything."
BACK_TO_WALKTHROUGH = "Back to the walkthrough. "


@dataclass(frozen=True)
class Speak:
    text: str


@dataclass(frozen=True)
class StopSpeech:
    pass


@dataclass(frozen=True)
class Chime:
    kind: str  # "done" or "needs_you"
    soft: bool


@dataclass(frozen=True)
class Listen:
    """Mic back on, listening command set active."""


@dataclass(frozen=True)
class Deafen:
    pass


Effect = Speak | StopSpeech | Chime | Listen | Deafen


class Player:
    def __init__(self, store: Store):
        self.store = store
        self.phase = "idle"  # "idle", "speaking", "waiting" or "responding"
        self.key: str | None = None
        self.reply_id: str | None = None
        self.index = 0  # next section to play
        self.last_played: int | None = None
        self._notice = False  # speaking a needs-you line, not a section
        self._phase_before_notice = "idle"

    # --- controls ------------------------------------------------------------

    def go_ahead(self, focused_key: str | None) -> list[Effect]:
        if self.phase in ("speaking", "responding"):
            return []
        if focused_key is None:
            return [Speak(CANT_TELL)]
        if self.phase == "waiting" and self.key == focused_key:
            return self.continue_()
        state = self.store.session(focused_key)
        if state.unheard:
            reply_id, state.unheard = state.unheard, None
            state.awaiting_response = False  # whatever he was waiting for is here
            self.store.save_session(state)
            if self.store.load_reply(reply_id) is not None:
                return self._start(focused_key, reply_id, 0)
        if self._paused_on(focused_key):
            return self._play(self.index)
        walkthrough = self._walkthrough_left(state)
        if walkthrough is not None:
            return self._start(focused_key, walkthrough.id, state.walkthrough_pos)
        if state.walkthrough:
            self._clear_walkthrough(state)
        return [Speak(NOTHING_NEW)]

    def continue_(self) -> list[Effect]:
        if self.phase == "waiting" or (
            self.phase == "idle" and self.key and self._paused_on(self.key)
        ):
            return self._play(self.index)
        return []

    def repeat(self) -> list[Effect]:
        if self.last_played is None or self.phase == "responding":
            return []
        return self._interrupt() + self._play(self.last_played)

    def back(self) -> list[Effect]:
        if self.last_played is None or self.phase == "responding":
            return []
        return self._interrupt() + self._play(max(self.last_played - 1, 0))

    def skip(self) -> list[Effect]:
        if self.last_played is None or self.phase == "responding":
            return []
        return [StopSpeech()] + self._play(self.index)

    def stop(self) -> list[Effect]:
        if self.phase == "responding":
            return []  # waking Talon mid-dictation would hear the dictation
        if self.phase == "speaking" and not self._notice:
            self._rewind_to_interrupted()
        self.phase = "idle"
        self._notice = False
        return [StopSpeech(), Listen()]

    def section_finished(self) -> list[Effect]:
        if self.phase != "speaking":
            return []
        if self._notice:
            self._notice = False
            self.phase = self._phase_before_notice
            return [Listen()]
        awaited = self._take_awaited(self.key)
        if awaited is not None:
            return awaited
        reply = self._reply()
        if reply is not None and self.index < len(reply.sections):
            self.phase = "waiting"
            return [Listen()]
        return self._finish_item(reply)

    def respond_started(self, focused_key: str | None = None) -> list[Effect]:
        key = focused_key or self.key
        if key is not None:
            state = self.store.session(key)
            state.awaiting_response = True
            if focused_key is None or focused_key == self.key:
                context = self._listening_context()
                if context is not None:
                    state.listening_context = context
            self.store.save_session(state)
        self.phase = "responding"
        self._notice = False
        return [StopSpeech(), Deafen()]

    def respond_finished(self, focused_key: str | None = None) -> list[Effect]:
        self.phase = "idle"
        return [Listen()] + (self._take_awaited(focused_key or self.key) or [])

    def reset(self, focused_key: str | None = None) -> list[Effect]:
        """Listening off: stop speech and forget the position. The store keeps
        unheard replies and walkthroughs for next time, but nothing stays awaited,
        so no later reply autoplays."""
        for key in {self.key, focused_key} - {None}:
            self._clear_awaiting(key)
        self.phase = "idle"
        self._clear_position()
        return [StopSpeech()]

    # --- events --------------------------------------------------------------

    def handle_event(self, event: dict, focused_key: str | None) -> list[Effect]:
        kind = event.get("type")
        key = event.get("session_key")
        focused = focused_key is not None and key == focused_key
        busy = self.phase in ("speaking", "responding")
        if kind == "reply_ready":
            if not focused:
                return [Chime("done", True)]
            awaited = None if busy else self._take_awaited(key)
            return [Chime("done", False)] + (awaited or [])
        if kind == "needs_you":
            effects: list[Effect] = [Chime("needs_you", not focused)]
            line = event.get("line")
            if focused and not busy and line:
                effects += self._speak_notice(line)
            return effects
        if kind == "walkthrough_ready":
            if not focused or busy:
                return [Chime("done", not focused)]
            if self.key == key:  # a new walkthrough replaces what was paused here
                self.phase = "idle"
                self._clear_position()
            self._clear_awaiting(key)
            return self.go_ahead(key)
        if kind == "listening_on":
            return [Listen()]
        if kind == "listening_off":
            return self.reset(focused_key)
        return []

    def has_something(self, focused_key: str | None) -> bool:
        state = self.store.session(focused_key) if focused_key else None
        if state is not None and state.blocked:
            return False  # the knob keeps its normal meaning for the prompt
        if self.phase in ("speaking", "responding"):
            return True  # key 3 must stop the voice whichever tab is in front
        if state is None:
            return False
        if self.key == focused_key and (
            self.phase == "waiting" or self._paused_on(focused_key)
        ):
            return True
        return bool(state.unheard) or self._walkthrough_left(state) is not None

    # --- helpers -------------------------------------------------------------

    def _start(self, key: str, reply_id: str, index: int) -> list[Effect]:
        self.key, self.reply_id = key, reply_id
        return self._play(index)

    def _play(self, index: int, prefix: str = "") -> list[Effect]:
        """Play section `index` of the current item, or finish it if past the end."""
        reply = self._reply()
        if reply is None or not 0 <= index < len(reply.sections):
            return self._finish_item(reply)
        text = prefix + reply.sections[index].text
        if index == len(reply.sections) - 1 and self._nothing_follows(reply):
            text += EVERYTHING
        if reply.kind == "walkthrough":
            state = self.store.session(reply.session_key)
            if state.walkthrough == reply.id:
                state.walkthrough_pos = index + 1
                self.store.save_session(state)
        self.phase = "speaking"
        self._notice = False
        self.index, self.last_played = index + 1, index
        return [Deafen(), Speak(text)]

    def _finish_item(self, reply: Reply | None) -> list[Effect]:
        """The current item has no sections left: return to the walkthrough after a
        reply, otherwise end playback."""
        state = self.store.session(self.key) if self.key else None
        if state is not None:
            walkthrough = self._walkthrough_left(state)
            if walkthrough is not None and (reply is None or reply.kind == "reply"):
                self.reply_id = walkthrough.id
                return self._play(state.walkthrough_pos, BACK_TO_WALKTHROUGH)
            if state.walkthrough and (walkthrough is None or state.walkthrough == reply.id):
                self._clear_walkthrough(state)  # finished or stale; a newer one stays
        self.phase = "idle"
        self._clear_position()
        return [Listen()]

    def _take_awaited(self, key: str | None) -> list[Effect] | None:
        """Play the answer Dylan is waiting for, if it has arrived."""
        if key is None:
            return None
        state = self.store.session(key)
        if not (state.awaiting_response and state.unheard):
            return None
        if self.store.load_reply(state.unheard) is None:
            return None
        state.awaiting_response = False
        self.store.save_session(state)
        self.phase = "idle"
        return self.go_ahead(key)

    def _speak_notice(self, line: str) -> list[Effect]:
        if not self._notice:
            self._phase_before_notice = self.phase
        self._notice = True
        self.phase = "speaking"
        return [Deafen(), Speak(line)]

    def _rewind_to_interrupted(self) -> None:
        """Stopped mid-section: make that section the next one to play."""
        if self.last_played is None:
            return
        self.index = self.last_played
        reply = self._reply()
        if reply is not None and reply.kind == "walkthrough":
            state = self.store.session(reply.session_key)
            if state.walkthrough == reply.id:
                state.walkthrough_pos = self.last_played
                self.store.save_session(state)

    def _clear_awaiting(self, key: str) -> None:
        state = self.store.session(key)
        if state.awaiting_response:
            state.awaiting_response = False
            self.store.save_session(state)

    def _interrupt(self) -> list[Effect]:
        return [StopSpeech()] if self.phase == "speaking" else []

    def _listening_context(self) -> str | None:
        reply = self._reply()
        if reply is None or self.last_played is None:
            return None
        if not 0 <= self.last_played < len(reply.sections):
            return None
        section = reply.sections[self.last_played]
        if reply.kind == "walkthrough":
            item = f"the walkthrough '{reply.title or 'untitled'}'"
        else:
            item = "the reply"
        return (
            f"Dylan was listening to section {self.last_played + 1} of "
            f"{len(reply.sections)}, titled '{section.title or 'untitled'}', "
            f"of {item}, when he responded."
        )

    def _reply(self) -> Reply | None:
        return self.store.load_reply(self.reply_id) if self.reply_id else None

    def _paused_on(self, key: str) -> bool:
        if self.phase != "idle" or self.key != key:
            return False
        reply = self._reply()
        return reply is not None and self.index < len(reply.sections)

    def _nothing_follows(self, reply: Reply) -> bool:
        if reply.kind == "walkthrough":
            return True
        return self._walkthrough_left(self.store.session(reply.session_key)) is None

    def _walkthrough_left(self, state: SessionState) -> Reply | None:
        """The session's walkthrough, if it still has sections to play."""
        if not state.walkthrough:
            return None
        walkthrough = self.store.load_reply(state.walkthrough)
        if walkthrough is None or state.walkthrough_pos >= len(walkthrough.sections):
            return None
        return walkthrough

    def _clear_walkthrough(self, state: SessionState) -> None:
        state.walkthrough, state.walkthrough_pos = None, 0
        self.store.save_session(state)

    def _clear_position(self) -> None:
        self.key = self.reply_id = self.last_played = None
        self.index = 0
        self._notice = False
