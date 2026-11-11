"""Listening mode, Talon side: speaks Claude Code replies a section at a time.

Thin glue around core/player.py. The player decides what happens; this file
carries out its effects (say, afplay, mic switching, Talon modes), polls the
event folder the hooks write to, and routes the listening commands and the
Ulanzi remote to the player.

Talon "hears nothing" while the voice speaks by switching its microphone to
"None". The real mic name is saved in the state folder first, so a reload or
restart mid-speech can put it back (see _recover_after_load).
"""

import os
import re
import signal
import subprocess
import threading

from talon import Module, actions, app, cron, scope, settings, ui

from .core.focus import GHOSTTY_BUNDLE, REX_BUNDLE, default_run, focused_session_key
from .core.player import Chime, Deafen, Listen, Player, Speak, StopSpeech
from .core.store import Store

mod = Module()
mod.mode("listening", "Listening mode: only the listening commands are active")
mod.setting(
    "listening_voice",
    type=str,
    default="",
    desc="macOS voice for listening mode (empty: best installed voice)",
)
mod.setting(
    "listening_rate",
    type=int,
    default=190,
    desc="Listening mode speaking rate, in words per minute",
)

VOICES = ["Zoe (Premium)", "Ava (Premium)", "Evan (Premium)", "Samantha"]
FALLBACK_VOICE = "Samantha"
CHIMES = {
    "done": "/System/Library/Sounds/Glass.aiff",
    "needs_you": "/System/Library/Sounds/Submarine.aiff",
}
CLAUDE_TERMINALS = {GHOSTTY_BUNDLE, REX_BUNDLE}
NO_MIC = "None"

store = Store()
player = Player(store)

# Hotkeys and the cron tick may run on different threads; the player is not
# thread-safe, so every entry point that touches it holds this lock.
_lock = threading.RLock()
_on = False  # Talon is in listening mode
_responding = False  # Claude's /voice is recording an answer (voice key / "respond")
_say = None  # running `say` process
_say_generation = 0  # generation the running `say` belongs to
_generation = 0  # bumped whenever we kill speech, so a killed `say` never counts as finished
_default_voice = None  # picked lazily from `say -v ?`
_SAY_PID = store.root / "say.pid"  # lets a reloaded module silence an orphaned `say`


def _log(message: str) -> None:
    print(f"listening: {message}")


# --- focus -----------------------------------------------------------------


class _Focus:
    """The focused session key, looked up at most once per tick or handler.

    The lookup can take seconds (osascript / Rex CLI), so it only runs when
    something actually needs it, and never for apps other than Ghostty/Rex.
    """

    def __init__(self):
        self._looked_up = False
        self._key = None

    def __call__(self):
        if not self._looked_up:
            self._looked_up = True
            self._key = _lookup_focus()
        return self._key


def _lookup_focus():
    try:
        bundle = ui.active_app().bundle
        if bundle not in CLAUDE_TERMINALS:
            return None
        title = ui.active_window().title
    except Exception as e:
        _log(f"focus lookup failed: {e!r}")
        return None
    return focused_session_key(bundle, title, default_run)


def _in_claude_terminal() -> bool:
    try:
        return ui.active_app().bundle in CLAUDE_TERMINALS
    except Exception:
        return False


# --- effects ---------------------------------------------------------------


def _run(effects) -> None:
    for effect in effects:
        try:
            _execute(effect)
        except Exception as e:
            _log(f"effect {effect!r} failed: {e!r}")


def _execute(effect) -> None:
    if isinstance(effect, Deafen):
        _deafen()
    elif isinstance(effect, Listen):
        _listen()
    elif isinstance(effect, Speak):
        _speak(effect.text)
    elif isinstance(effect, StopSpeech):
        _stop_speech()
    elif isinstance(effect, Chime):
        _chime(effect.kind, effect.soft)


def _deafen() -> None:
    current = actions.sound.active_microphone()
    if current != NO_MIC:
        store.set_saved_mic(current)
        actions.sound.set_microphone(NO_MIC)


def _restore_mic() -> None:
    saved = store.saved_mic()
    if saved:
        actions.sound.set_microphone(saved)
        store.set_saved_mic(None)


def _enter_listening_modes() -> None:
    actions.mode.disable("command")
    actions.mode.disable("dictation")
    actions.mode.disable("sleep")
    actions.mode.enable("user.listening")


def _leave_listening_modes() -> None:
    actions.mode.disable("user.listening")
    # Back to regular command mode. (community's user.talon_mode() only calls
    # speech.enable(), which doesn't re-enable command mode and, when Talon
    # isn't asleep, just shows "Talon is already awake".)
    actions.mode.disable("sleep")
    actions.mode.disable("dictation")
    actions.mode.enable("command")


def _listen() -> None:
    _restore_mic()
    _enter_listening_modes()


def _voice() -> str:
    chosen = settings.get("user.listening_voice")
    if chosen:
        return chosen
    global _default_voice
    if _default_voice is None:
        _default_voice = _pick_voice()
    return _default_voice


def _pick_voice() -> str:
    try:
        out = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception as e:
        _log(f"listing voices failed: {e!r}")
        return FALLBACK_VOICE
    # Lines look like "Zoe (Premium)       en_US    # Hello! ..." or
    # "Samantha (English (US)) en_US    # ...".
    installed = []
    for line in out.splitlines():
        match = re.match(r"^(.+?)\s+[a-z]{2,3}_[A-Za-z0-9]+\s+#", line)
        if match:
            installed.append(match.group(1))
    for voice in VOICES:
        if any(name == voice or name.startswith(voice + " (") for name in installed):
            return voice
    return FALLBACK_VOICE


class _FailedSay:
    """Stands in for a `say` that couldn't start, so the next tick treats the
    section as finished and Talon wakes up instead of staying deaf."""

    pid = None

    def poll(self):
        return 1

    def terminate(self):
        pass


def _speak(text: str) -> None:
    global _say, _say_generation
    _stop_speech()
    _say_generation = _generation
    try:
        _say = subprocess.Popen(
            ["say", "-v", _voice(), "-r", str(settings.get("user.listening_rate")), text],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        _log(f"say failed to start: {e!r}")
        _say = _FailedSay()
        return
    try:
        _SAY_PID.write_text(str(_say.pid))
    except OSError:
        pass


def _stop_speech() -> None:
    global _say, _generation
    _generation += 1
    process, _say = _say, None
    if process is not None and process.poll() is None:
        process.terminate()
    _SAY_PID.unlink(missing_ok=True)


def _chime(kind: str, soft: bool) -> None:
    sound = CHIMES.get(kind)
    if sound:
        subprocess.Popen(
            ["afplay", "-v", "0.25" if soft else "1.0", sound],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


# --- polling ---------------------------------------------------------------


def _tick() -> None:
    try:
        with _lock:
            _tick_body()
    except Exception as e:
        _log(f"tick failed: {e!r}")


def _tick_body() -> None:
    global _say
    if _on and _say is not None and _say.poll() is not None:
        # Only a `say` that ran to its end finishes a section; one we killed
        # has already been replaced (or its generation bumped).
        finished_generation, _say = _say_generation, None
        _SAY_PID.unlink(missing_ok=True)
        if finished_generation == _generation and player.phase == "speaking":
            _run(player.section_finished())

    events = store.pop_events()
    if not events:
        return
    if not _on:
        # Hooks write nothing while listening is off, except the walkthrough
        # CLI, which turns listening on first. Anything before that is stale.
        starts = [i for i, e in enumerate(events) if e.get("type") == "listening_on"]
        if not starts:
            return
        _turn_on()
        events = events[starts[0] + 1 :]

    focused = _Focus()
    for event in events:
        if not _on:
            break  # a listening_off earlier in this batch ended it
        kind = event.get("type")
        if kind == "listening_on":
            continue  # already on; a Listen now could wake the mic mid-speech
        if kind == "listening_off":
            _listening_off(focused)
            break
        _run(player.handle_event(event, focused()))


def _turn_on() -> None:
    global _on
    store.set_on(True)
    _on = True
    _run([Listen()])


def _listening_off(focused: _Focus) -> None:
    global _on, _responding
    _on = False
    _responding = False
    _run([StopSpeech()])  # silence first; the focus lookup can take a moment
    for step in (_restore_mic, _leave_listening_modes, lambda: store.set_on(False)):
        try:
            step()
        except Exception as e:
            _log(f"listening off step failed: {e!r}")
    _run(player.reset(focused()))


# --- control helpers ---------------------------------------------------------


def _start_respond(focused_key) -> None:
    global _responding
    _responding = True
    _run(player.respond_started(focused_key))
    actions.user.ulanzi_key("space")  # Claude Code's /voice tap


def _finish_respond(focused_key) -> None:
    global _responding
    _responding = False
    actions.user.ulanzi_key("space")  # stops /voice tap and sends
    _run(player.respond_finished(focused_key))


def _intercept(control: str) -> bool:
    if control == "talon":
        _listening_off(_Focus())
        return True
    if control == "voice":
        if not _in_claude_terminal():
            return False  # Superwhisper behaves as before
        focused = _Focus()
        if _responding:
            _finish_respond(focused())
        else:
            _start_respond(focused())
        return True
    if control not in ("knob_press", "back", "knob_left", "knob_right"):
        return False
    focused = _Focus()
    key = focused()
    if not player.has_something(key):
        return False  # normal per-app meaning
    if control == "knob_press":
        _run(player.go_ahead(key))
    elif control == "back":
        _run(player.stop())
    elif control == "knob_right":
        _run(player.skip(key))
    elif player.phase == "speaking":
        _run(player.back(key))
    else:
        _run(player.repeat(key))
    return True


# --- load-time recovery ------------------------------------------------------


def _kill_orphaned_say() -> None:
    """A reload loses the previous module's `say` process; silence it."""
    try:
        pid = int(_SAY_PID.read_text().strip())
    except (OSError, ValueError):
        return
    _SAY_PID.unlink(missing_ok=True)
    try:
        comm = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        if os.path.basename(comm) == "say":
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        _log(f"stopping old say failed: {e!r}")


def _recover_after_load() -> None:
    """Review Focus 3: never leave Talon deaf after a reload or restart.

    A Talon restart (or this file reloading) is a fresh start: listening mode
    does NOT resume on its own, even if the store flag was on. The flag is
    turned off, stale events are dropped, and Dylan says "listening on" again.
    """
    with _lock:
        saved_mic, was_on = store.saved_mic(), store.is_on()
        for step in (
            _kill_orphaned_say,
            _restore_mic,
            store.pop_events,
            lambda: store.set_on(False),
        ):
            try:
                step()
            except Exception as e:
                _log(f"recovery step failed: {e!r}")
        in_mode = False
        try:
            in_mode = "user.listening" in scope.get("mode")
            if in_mode:
                _leave_listening_modes()
        except Exception as e:
            _log(f"leaving listening mode after reload failed: {e!r}")
        _log(
            f"loaded (restored mic: {saved_mic or 'no'}, flag was on: {was_on}, "
            f"was in listening mode: {in_mode})"
        )


app.register("ready", _recover_after_load)
cron.interval("300ms", _tick)


# --- actions -----------------------------------------------------------------


@mod.action_class
class Actions:
    def listening_on():
        """Turn listening mode on: Claude replies get spoken"""
        with _lock:
            if _on and player.phase in ("speaking", "responding"):
                return
            _turn_on()

    def listening_off():
        """Leave listening mode and return to command mode"""
        with _lock:
            _listening_off(_Focus())

    def listening_go_ahead():
        """Play the focused session's newest unheard reply, or resume"""
        with _lock:
            _run(player.go_ahead(_Focus()()))

    def listening_continue():
        """Play the next section"""
        with _lock:
            _run(player.continue_(_Focus()()))

    def listening_repeat():
        """Play this section again"""
        with _lock:
            _run(player.repeat(_Focus()()))

    def listening_back():
        """Go back a section"""
        with _lock:
            _run(player.back(_Focus()()))

    def listening_skip():
        """Skip to the next section"""
        with _lock:
            _run(player.skip(_Focus()()))

    def listening_stop():
        """Stop playback; the rest stays available"""
        with _lock:
            _run(player.stop())

    def listening_respond():
        """Start dictating an answer to Claude; the voice key stops and sends"""
        with _lock:
            if not _in_claude_terminal():
                app.notify("Listening mode", "Respond works in a Claude terminal tab")
                return
            if _responding:
                return
            _start_respond(_Focus()())

    def listening_intercept(control: str) -> bool:
        """True if listening mode handled this Ulanzi control"""
        if not _on:
            return False
        try:
            with _lock:
                return _intercept(control)
        except Exception as e:
            _log(f"intercepting {control} failed: {e!r}")
            return False
