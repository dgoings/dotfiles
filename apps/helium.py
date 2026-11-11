"""Helium browser (Chromium-based). Mirrors community's Chrome support."""

from talon import Context, Module, actions

mod = Module()
mod.apps.helium = r"""
os: mac
app.bundle: net.imput.helium
"""

ctx = Context()
ctx.matches = r"""
app: helium
"""


@ctx.action_class("user")
class UserActions:
    def tab_close_wrapper():
        actions.sleep("180ms")
        actions.app.tab_close()


@ctx.action_class("browser")
class BrowserActions:
    def show_extensions():
        actions.app.tab_open()
        actions.browser.go("chrome://extensions")
