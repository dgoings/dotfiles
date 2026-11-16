"""Voice toggle for Rango. Starts off; "rango on" / "rango off" flip it.

Off means two things: the user.rango_disabled tag silences every Rango
voice command, and the extension's hints are hidden in the browser.
"""

from talon import Context, Module, actions

mod = Module()
ctx = Context()

# Off at startup: Rango's commands stay inactive until "rango on".
ctx.tags = ["user.rango_disabled"]


@mod.action_class
class Actions:
    def rango_on():
        """Enable Rango's voice commands and show its hints"""
        ctx.tags = []
        actions.user.rango_enable_hints("global")
        actions.app.notify("Rango on")

    def rango_off():
        """Disable Rango's voice commands and hide its hints"""
        actions.user.rango_disable_hints("global")
        ctx.tags = ["user.rango_disabled"]
        actions.app.notify("Rango off")
