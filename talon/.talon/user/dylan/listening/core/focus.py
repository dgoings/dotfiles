"""Which Claude session is in the frontmost terminal tab or T3 Code thread.

Returns the same key the hooks compute for their own session:
"tty:/dev/ttysNNN" (Ghostty), "rex:<REX_BLOCK>" (Rex) or "t3:<thread id>"
(T3 Code).
"""

import json
import re
import subprocess
from typing import Callable, Optional

GHOSTTY_BUNDLE = "com.mitchellh.ghostty"
REX_BUNDLE = "com.superlogical.rex"
REX_CLI = "/Applications/Rex Beta.app/Contents/Helpers/Rex Server.rex/Contents/MacOS/rex"
T3_BUNDLE = "com.t3tools.t3code"
# The T3 Code window's page address while a thread is open:
# t3code://app/#/<environment id>/<thread id>. Other pages (settings, a new
# unsent thread) don't match.
_UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
_T3_THREAD_URL = re.compile(rf"^t3code://app/#/{_UUID}/({_UUID})(?:[/?].*)?$")
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


def t3_key(url: Optional[str]) -> Optional[str]:
    """The session key for the thread a T3 Code page address shows, if any."""
    match = _T3_THREAD_URL.match(url or "")
    return "t3:" + match.group(1).lower() if match else None


def focused_session_key(
    front_bundle: str,
    window_title: str,
    run: Callable,
    t3_url: Optional[Callable[[], Optional[str]]] = None,
) -> Optional[str]:
    """`t3_url` returns the front T3 Code window's page address (the Talon
    glue reads it through accessibility)."""
    try:
        if front_bundle == GHOSTTY_BUNDLE:
            return _ghostty_key(run)
        if front_bundle == REX_BUNDLE:
            return _rex_key(window_title or "", run)
        if front_bundle == T3_BUNDLE and t3_url is not None:
            return t3_key(t3_url())
    except Exception:
        return None
    return None
