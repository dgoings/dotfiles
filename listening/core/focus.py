"""Which Claude session is in the frontmost terminal tab.

Returns the same key the hooks compute for their own session:
"tty:/dev/ttysNNN" (Ghostty) or "rex:<REX_BLOCK>" (Rex).
"""

import json
import subprocess
from typing import Callable, Optional

GHOSTTY_BUNDLE = "com.mitchellh.ghostty"
REX_BUNDLE = "com.superlogical.rex"
REX_CLI = "/Applications/Rex Beta.app/Contents/Helpers/Rex Server.rex/Contents/MacOS/rex"
_GHOSTTY_SCRIPT = (
    'tell application "Ghostty" to get tty of focused terminal of selected tab of front window'
)


def default_run(args: list) -> str:
    """Run a command and return stdout. Raises on failure or after 2s."""
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=2, check=True
    )
    return result.stdout


def _ghostty_key(run: Callable) -> Optional[str]:
    out = run(["osascript", "-e", _GHOSTTY_SCRIPT]).strip()
    if not out.startswith("/dev/"):
        return None
    return "tty:" + out


def _rex_key(window_title: str, run: Callable) -> Optional[str]:
    clients = json.loads(run([REX_CLI, "client", "ls", "--json"])).get("clients", [])
    session_ids = []
    for client in clients:
        if (client.get("info") or {}).get("kind") != "app":
            continue
        for sid in client.get("session_ids") or []:
            if sid not in session_ids:
                session_ids.append(sid)
    if not session_ids:
        return None

    def inspect(sid):
        return json.loads(run([REX_CLI, "session", "inspect", sid, "--json"]))

    if len(session_ids) == 1:
        session = inspect(session_ids[0])
    else:
        session = None
        for sid in session_ids:
            candidate = inspect(sid)
            label = candidate.get("label")
            if label and window_title.endswith(" - " + label):
                session = candidate
                break
        if session is None:
            return None

    active = session.get("active_window_id")
    for window in session.get("windows") or []:
        if window.get("window_id") == active:
            block = window.get("focused_block_id")
            return "rex:" + block if block else None
    return None


def focused_session_key(
    front_bundle: str, window_title: str, run: Callable
) -> Optional[str]:
    try:
        if front_bundle == GHOSTTY_BUNDLE:
            return _ghostty_key(run)
        if front_bundle == REX_BUNDLE:
            return _rex_key(window_title or "", run)
    except Exception:
        return None
    return None
