"""Per-app behavior for the Ulanzi key 3 and knob.

Each Context below overrides the default actions in ulanzi.py for one group
of apps. An app-specific override always beats the default. To add an app,
copy a block and change the app.bundle lines. (Find an app's bundle ID with
`osascript -e 'id of app "AppName"'`.)
"""

from talon import Context, actions, ui

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


# T3 Code: the knob switches threads (T3's thread.previous / thread.next
# shortcuts, see ~/.t3/userdata/keybindings.json). T3 stops at either end of
# the list, so from the first or last thread in the sidebar the knob wraps
# around by pressing the row at the other end. Press and key 3 keep the
# defaults (Enter sends, Escape cancels). In listening mode the knob and voice
# key work as in the terminals (see listening/README.md).
T3_THREAD_ROW_CLASS = "group/sidebar-row"
T3_MAX_NODES = 3000

t3code = Context()
t3code.matches = r"""
mode: all
app.bundle: com.t3tools.t3code
"""


def _t3_thread_rows():
    """The thread rows showing in T3's sidebar, top to bottom, and the index
    of the open thread's row (None if it isn't among them)."""
    rows, current = [], None
    try:
        queue = [ui.active_window().element]
        for _ in range(T3_MAX_NODES):
            if not queue:
                break
            el = queue.pop(0)
            try:
                if el.get("AXRole") == "AXButton" and T3_THREAD_ROW_CLASS in (
                    el.get("AXDOMClassList") or []
                ):
                    if el.get("AXARIACurrent") == "page":
                        current = len(rows)
                    rows.append(el)
                    continue
                queue.extend(el.children)
            except Exception:
                continue
    except Exception as e:
        print(f"ulanzi: couldn't read T3's thread list: {e!r}")
    return rows, current


def _t3_switch_thread(step: int):
    """Go to the previous (-1) or next (+1) thread, wrapping at the ends."""
    rows, current = _t3_thread_rows()
    if current is not None and len(rows) > 1:
        wrap_to = None
        if step < 0 and current == 0:
            wrap_to = rows[-1]
        elif step > 0 and current == len(rows) - 1:
            wrap_to = rows[0]
        if wrap_to is not None:
            try:
                wrap_to.perform("AXPress")
                return
            except Exception as e:
                print(f"ulanzi: couldn't wrap around T3's thread list: {e!r}")
    actions.user.ulanzi_key("cmd-shift-[" if step < 0 else "cmd-shift-]")


@t3code.action_class("user")
class T3CodeActions:
    def ulanzi_knob_left():
        _t3_switch_thread(-1)

    def ulanzi_knob_right():
        _t3_switch_thread(1)


# Claude Desktop uses the defaults (knob scrolls the conversation under the
# mouse, press sends, key 3 is Escape). Add a Context here to customize it.
