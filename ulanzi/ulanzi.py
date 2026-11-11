"""Ulanzi AU05 keypad support.

Ulanzi Studio uses a single preset in which every control sends a fixed
"hyper" shortcut (ctrl+alt+shift+cmd + a letter). Talon decides what each
shortcut does based on the frontmost app: ulanzi.talon holds the global
controls and defaults, and apps/*.talon override them per app.
"""

import subprocess

from talon import Module, actions, app, cron, ui

mod = Module()

# Apps where the voice key drives Claude Code's `/voice tap` (Space toggles it).
CLAUDE_CODE_TERMINALS = {"com.superlogical.rex", "com.mitchellh.ghostty"}

# Superwhisper's record toggle shortcut (set in Superwhisper's settings).
# Only sent while Superwhisper is running: otherwise the focused app gets it,
# and a terminal reads it as ctrl+Z (suspending Claude Code).
SUPERWHISPER_HOTKEY = "ctrl-alt-shift-z"
SUPERWHISPER_PROCESS = "superwhisper"

# The keypad is still holding ctrl/alt/shift/cmd when Talon sees the shortcut.
# Wait for it to let go so those modifiers don't get added to what we send
# (e.g. Up turning into cmd+Up, or scrolling turning into ctrl+scroll zoom).
RELEASE_DELAY = "80ms"

# Each dictation tool has its own on/off state, and the voice key always
# toggles the tool for the frontmost app: in Rex/Ghostty that's Claude Code's
# /voice, even if Superwhisper is running or mid-recording.
DICTATION_KEYS = {"claude": "space", "superwhisper": SUPERWHISPER_HOTKEY}
_dictating = set()  # tools currently recording
_talon_was_awake = False  # Talon's state before the first tool started


def _after_release(fn):
    cron.after(RELEASE_DELAY, fn)


def _superwhisper_running() -> bool:
    # Superwhisper is a menu-bar-only app, which Talon's ui.apps() doesn't
    # list, so check for the process instead.
    result = subprocess.run(["pgrep", "-x", SUPERWHISPER_PROCESS], capture_output=True)
    return result.returncode == 0


@mod.action_class
class Actions:
    def ulanzi_sleep():
        """Put Talon to sleep (same as the "sleep all" voice command)"""
        actions.user.switcher_hide_running()
        actions.user.history_disable()
        actions.user.homophones_hide()
        actions.user.help_hide()
        actions.user.mouse_sleep()
        actions.speech.disable()

    def ulanzi_wake():
        """Wake Talon into command mode (like "welcome back", minus the history panel)"""
        actions.user.deep_sleep_disable()
        actions.user.mouse_wake()
        actions.user.talon_mode()

    def ulanzi_toggle():
        """Toggle Talon between awake and asleep"""
        if actions.speech.enabled():
            actions.user.ulanzi_sleep()
        else:
            actions.user.ulanzi_wake()

    def ulanzi_key(keys: str):
        """Press keys once the keypad has released its modifiers"""
        _after_release(lambda: actions.key(keys))

    def ulanzi_scroll(lines: int):
        """Scroll under the mouse (positive = down) once modifiers are released"""
        _after_release(lambda: actions.mouse_scroll(lines, by_lines=True))

    # Per-app controls. These are the defaults for apps not listed in
    # ulanzi_apps.py, which overrides them per app.
    def ulanzi_back():
        """Key 3: back / cancel"""
        actions.user.ulanzi_key("escape")

    def ulanzi_knob_left():
        """Knob left: up / previous"""
        actions.user.ulanzi_scroll(-3)

    def ulanzi_knob_right():
        """Knob right: down / next"""
        actions.user.ulanzi_scroll(3)

    def ulanzi_knob_press():
        """Knob press: confirm"""
        actions.user.ulanzi_key("enter")

    def ulanzi_dictation_toggle():
        """Start/stop dictation: Claude Code /voice in terminals, Superwhisper elsewhere.

        Talon sleeps while you dictate so it doesn't act on your speech, then
        returns to whatever state it was in before.
        """
        global _talon_was_awake
        if ui.active_app().bundle in CLAUDE_CODE_TERMINALS:
            tool = "claude"
        else:
            tool = "superwhisper"
        sw_running = tool != "superwhisper" or _superwhisper_running()

        if tool in _dictating:
            _dictating.discard(tool)
            if sw_running:
                actions.user.ulanzi_key(DICTATION_KEYS[tool])
            if not _dictating and _talon_was_awake:
                actions.speech.enable()
            return

        if not sw_running:
            app.notify("Ulanzi voice key", "Superwhisper isn't running")
            return
        if not _dictating:
            _talon_was_awake = actions.speech.enabled()
        _dictating.add(tool)
        actions.speech.disable()
        actions.user.ulanzi_key(DICTATION_KEYS[tool])
