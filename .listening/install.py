#!/usr/bin/env python3
"""Install (or remove) listening mode's Claude Code hooks and the `listen` skill.

    install.py [--settings PATH] [--skills-dir PATH] [--python PATH] [--uninstall]

Only touches hook entries whose command contains `/.listening/listen.py`, and the
`<skills-dir>/listen` symlink when it points at this repo's skill.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LISTEN = REPO / ".listening" / "listen.py"
SKILL_SRC = REPO / ".listening" / "skill" / "listen"
MARKER = "/.listening/listen.py"
MIN_PYTHON = (3, 10)
HOMEBREW_PYTHON = "/opt/homebrew/bin/python3"


def default_python() -> str:
    return HOMEBREW_PYTHON if os.path.exists(HOMEBREW_PYTHON) else sys.executable


def python_ok(python: str) -> bool:
    try:
        out = subprocess.run([python, "-c", "import sys; print(sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=15).stdout
        nums = tuple(int(n) for n in out.strip().strip("()").split(","))
        return nums >= MIN_PYTHON
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def our_entries(python: str) -> dict:
    def cmd(sub: str) -> str:
        return f"{python} {LISTEN} {sub}"

    return {
        "Stop": {"hooks": [{"type": "command", "command": cmd("hook-stop"),
                            "async": True, "timeout": 10}]},
        "Notification": {"matcher": "permission_prompt",
                         "hooks": [{"type": "command", "command": cmd("hook-notify"),
                                    "async": True, "timeout": 10}]},
        "UserPromptSubmit": {"hooks": [{"type": "command", "command": cmd("hook-prompt"),
                                        "timeout": 5}]},
    }


def is_ours(hook: dict) -> bool:
    return MARKER in str(hook.get("command", ""))


def group_has_ours(group) -> bool:
    return isinstance(group, dict) and any(
        isinstance(h, dict) and is_ours(h) for h in group.get("hooks", []))


def add_hooks(settings: dict, python: str) -> None:
    hooks = settings.setdefault("hooks", {})
    for event, group in our_entries(python).items():
        groups = hooks.setdefault(event, [])
        if not any(group_has_ours(g) for g in groups):
            groups.append(group)


def remove_hooks(settings: dict) -> None:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for g in groups:
            if group_has_ours(g):
                rest = [h for h in g["hooks"] if not (isinstance(h, dict) and is_ours(h))]
                if not rest:
                    continue
                g = {**g, "hooks": rest}
            kept.append(g)
        if kept:
            hooks[event] = kept
        elif len(kept) != len(groups):
            del hooks[event]
    if not hooks:
        del settings["hooks"]


def is_our_link(link: Path) -> bool:
    return link.is_symlink() and link.resolve() == SKILL_SRC.resolve()


def shape_problem(settings) -> str:
    if not isinstance(settings, dict):
        return "settings JSON is not an object"
    hooks = settings.get("hooks")
    if hooks is None:
        return ""
    if not isinstance(hooks, dict):
        return "\"hooks\" is not an object"
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            return f"hooks.{event} is not a list"
    return ""


def write_settings(path: Path, settings: dict) -> None:
    tmp = path.with_name(path.name + ".tmp-listening")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="install.py")
    p.add_argument("--settings", default="~/.claude/settings.json")
    p.add_argument("--skills-dir", default="~/.claude/skills")
    p.add_argument("--python", default=None,
                   help="interpreter written into the hook commands")
    p.add_argument("--uninstall", action="store_true")
    args = p.parse_args(argv)

    settings_path = Path(args.settings).expanduser()
    link = Path(args.skills_dir).expanduser() / "listen"
    python = args.python or default_python()

    if not args.uninstall and not python_ok(python):
        print(f"{python} is missing or older than Python 3.10; "
              "pass --python with a newer interpreter.", file=sys.stderr)
        return 1
    if link.exists() or link.is_symlink():
        if not is_our_link(link):
            if not args.uninstall:
                print(f"{link} already exists and is not the listening skill link; "
                      "not changing anything.", file=sys.stderr)
                return 1

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except ValueError as e:
            print(f"{settings_path} is not valid JSON ({e}); not changing anything.",
                  file=sys.stderr)
            return 1
        problem = shape_problem(settings)
        if problem:
            print(f"{settings_path}: {problem}; not changing anything.", file=sys.stderr)
            return 1
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = settings_path.with_name(f"{settings_path.name}.bak-listening-{stamp}")
        n = 1
        while backup.exists():
            n += 1
            backup = settings_path.with_name(f"{settings_path.name}.bak-listening-{stamp}-{n}")
        backup.write_text(settings_path.read_text())
        print(f"Backed up settings to {backup}")
    else:
        settings = {}

    if args.uninstall:
        remove_hooks(settings)
        if settings_path.exists():
            write_settings(settings_path, settings)
        if is_our_link(link):
            link.unlink()
        print("Removed listening hooks and skill link.")
        return 0

    add_hooks(settings, python)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    write_settings(settings_path, settings)
    if not is_our_link(link):
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(SKILL_SRC)
    print(f"Installed listening hooks (python: {python}) and skill link {link}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
