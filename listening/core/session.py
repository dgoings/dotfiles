import subprocess
from collections.abc import Callable, Mapping

_MAX_DEPTH = 64


def own_session_key(
    env: Mapping[str, str],
    tty_of: Callable[[int], str],
    parent_of: Callable[[int], int],
    pid: int,
) -> str | None:
    """Identify the terminal tab a process belongs to.

    Rex sessions use REX_BLOCK. Otherwise walk up the process tree and use the
    topmost real tty (sessions under Claude's background helper have an inner
    pty below the tab's real tty).
    """
    block = env.get("REX_BLOCK")
    if block:
        return "rex:" + block

    found = ""
    seen: set[int] = set()
    p = pid
    while p > 1 and p not in seen and len(seen) < _MAX_DEPTH:
        seen.add(p)
        try:
            tty = (tty_of(p) or "").strip()
        except Exception:
            break
        if tty and tty != "??":
            found = tty
        try:
            nxt = parent_of(p)
        except Exception:
            break
        if not nxt or nxt <= 0:
            break
        p = nxt
    return "tty:/dev/" + found if found else None


def _ps(field: str, pid: int) -> str:
    try:
        out = subprocess.run(
            ["ps", "-o", field + "=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def default_tty_of(pid: int) -> str:
    return _ps("tty", pid)


def default_parent_of(pid: int) -> int:
    try:
        return int(_ps("ppid", pid))
    except ValueError:
        return 0
