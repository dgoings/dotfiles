"""Spoken app names for community's app switcher ("focus <app>").

These work like lines in community's app_name_overrides.mac.csv: an app named
here is only reachable by the spoken forms given for it, and community's
generated forms for it are dropped (so "code" can't also mean "T3 Code").
They live here so the community checkout stays untouched.

Community reads only its own CSV, so this wraps its update_running_list() to
merge these in each time it rebuilds the list of running apps. If community
renames that function or its `overrides` dict, the names here stop working
and the Talon log says so.
"""

import sys

from talon import app

# spoken form -> the app's exact name (as in the menu bar)
APP_NAMES = {
    "ghostty": "Ghostty",
    "ghost": "Ghostty",
    "code": "Code",
    "vs code": "Code",
    "tee three": "T3 Code (Beta)",
    "t three code": "T3 Code (Beta)",
}

SWITCHER = "user.community.core.app_switcher.app_switcher"


def _install():
    switcher = sys.modules.get(SWITCHER)
    if switcher is None or not hasattr(switcher, "update_running_list"):
        print(f"app_names: {SWITCHER} not found; extra app names are off")
        return
    # Unwrap a previous install so reloading this file doesn't stack wrappers.
    original = getattr(
        switcher.update_running_list, "__wrapped__", switcher.update_running_list
    )

    def update_running_list():
        # Community lowercases both sides of its CSV; match that.
        switcher.overrides.update(
            {spoken.lower(): name.lower() for spoken, name in APP_NAMES.items()}
        )
        original()

    update_running_list.__wrapped__ = original
    switcher.update_running_list = update_running_list
    update_running_list()


app.register("ready", _install)
