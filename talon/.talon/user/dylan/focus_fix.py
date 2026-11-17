"""Stop a misheard "focus <app>" from opening Mission Control.

Community's bare `focus` command opens Mission Control. When Talon doesn't
recognize the app name you said, it matches that bare command instead.
Show a notification so you know to try again.
"""

from talon import Context, app

ctx = Context()


@ctx.action_class("user")
class UserActions:
    def switcher_menu():
        app.notify("Talon", "Didn't catch which app to focus. Try again.")
