"""Per-app behavior for the Ulanzi key 3 and knob.

Each Context below overrides the default actions in ulanzi.py for one group
of apps. An app-specific override always beats the default. To add an app,
copy a block and change the app.bundle lines. (Find an app's bundle ID with
`osascript -e 'id of app "AppName"'`.)
"""

from talon import Context, actions

# Rex + Ghostty, mostly for Claude Code: the knob moves through Claude's
# menus and prompt history, press picks, key 3 interrupts or dismisses.
terminals = Context()
terminals.matches = r"""
mode: all
app.bundle: com.superlogical.rex
app.bundle: com.mitchellh.ghostty
"""


@terminals.action_class("user")
class TerminalActions:
    def ulanzi_back():
        actions.user.ulanzi_key("escape")

    def ulanzi_knob_left():
        actions.user.ulanzi_key("up")

    def ulanzi_knob_right():
        actions.user.ulanzi_key("down")

    def ulanzi_knob_press():
        actions.user.ulanzi_key("enter")


# Helium + Chrome: the knob switches tabs, key 3 goes back.
browsers = Context()
browsers.matches = r"""
mode: all
app.bundle: net.imput.helium
app.bundle: com.google.Chrome
"""


@browsers.action_class("user")
class BrowserActions:
    def ulanzi_back():
        actions.user.ulanzi_key("cmd-[")

    def ulanzi_knob_left():
        actions.user.ulanzi_key("cmd-alt-left")

    def ulanzi_knob_right():
        actions.user.ulanzi_key("cmd-alt-right")

    def ulanzi_knob_press():
        actions.user.ulanzi_key("enter")


# Slack: the knob walks unread conversations, key 3 goes back, press sends.
slack = Context()
slack.matches = r"""
mode: all
app.bundle: com.tinyspeck.slackmacgap
"""


@slack.action_class("user")
class SlackActions:
    def ulanzi_back():
        actions.user.ulanzi_key("cmd-[")

    def ulanzi_knob_left():
        actions.user.ulanzi_key("alt-shift-up")

    def ulanzi_knob_right():
        actions.user.ulanzi_key("alt-shift-down")

    def ulanzi_knob_press():
        actions.user.ulanzi_key("enter")


# Claude Desktop + T3 Code use the defaults (knob scrolls the conversation,
# press sends, key 3 is Escape), since neither has keyboard shortcuts for
# switching sessions. Add a Context here to customize them.
