#!/opt/homebrew/bin/python3
"""Listening mode CLI: called by Claude Code hooks and the walkthrough skill.

Hooks never print anything except the documented hook-prompt JSON, and never
fail: any internal error is swallowed and the exit code is 0. The one
deliberate non-zero exit is `walkthrough` with invalid sections JSON (exit 2).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "listening"))

from core.session import default_parent_of, default_tty_of, own_session_key  # noqa: E402
from core.spoken import SpokenFormatError, fallback_sections, parse_sections  # noqa: E402
from core.store import Store  # noqa: E402

TAIL_BYTES = 256 * 1024
STYLE_GUIDE = Path(__file__).resolve().parent.parent / "listening" / "style_guide.md"
DEFAULT_REWRITE_TIMEOUT = 90.0

LINE_PERMISSION = "Claude needs you to approve something."
LINE_QUESTION = "Claude has a question for you."
LINE_PLAN = "Claude has a plan for you to review."


def session_key() -> str | None:
    return own_session_key(os.environ, default_tty_of, default_parent_of, os.getpid())


def read_payload() -> dict:
    data = json.loads(sys.stdin.read())
    return data if isinstance(data, dict) else {}


def last_tool_use_name(transcript_path: str | None) -> str | None:
    """Name of the last tool_use block in an assistant entry, or None."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            tail = f.read()
        last = None
        for raw in tail.splitlines():
            try:
                entry = json.loads(raw)  # first line may be cut off; skip it
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "assistant":
                continue
            content = (entry.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    last = block.get("name")
        return last if isinstance(last, str) else None
    except Exception:
        return None


def blocked_line(payload: dict, last_tool: str | None) -> str | None:
    if payload.get("notification_type") != "permission_prompt":
        return None
    if "approval for the plan" in str(payload.get("message", "")):
        return LINE_PLAN
    if last_tool == "AskUserQuestion":
        return LINE_QUESTION
    return LINE_PERMISSION


def cmd_on(args) -> None:
    store = Store()
    store.set_on(True)
    store.push_event("listening_on", "")


def cmd_off(args) -> None:
    store = Store()
    store.set_on(False)
    store.push_event("listening_off", "")


def cmd_walkthrough(args) -> int:
    try:
        sections = parse_sections(sys.stdin.read())
    except SpokenFormatError as e:
        print(f"Invalid sections JSON: {e}", file=sys.stderr)
        return 2
    key = session_key()
    if not key:
        print("I can't tell which Claude session this is.", file=sys.stderr)
        return 0
    store = Store()
    was_on = store.is_on()
    store.set_on(True)
    written = "\n\n".join(f"## {s.title}\n\n{s.text}" if s.title else s.text for s in sections)
    reply_id = store.create_reply(key, "walkthrough", written, args.title)
    store.save_sections(reply_id, sections)
    state = store.session(key)
    state.walkthrough = reply_id
    state.walkthrough_pos = 0
    state.suppress_next_stop = True
    store.save_session(state)
    if not was_on:
        store.push_event("listening_on", "")
    store.push_event("walkthrough_ready", key, reply_id=reply_id)
    print(f"Walkthrough queued ({len(sections)} sections).")
    return 0


def cmd_hook_prompt(args) -> None:
    store = Store()
    if not store.is_on():
        return
    key = session_key()
    if not key:
        return
    payload = read_payload()
    if str(payload.get("prompt", "")).startswith("<task-notification>"):
        return
    state = store.session(key)
    context = state.listening_context
    if not state.blocked and not context:
        return
    state.blocked = False
    state.listening_context = None
    store.save_session(state)
    if context:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    }
                }
            )
        )


def cmd_hook_notify(args) -> None:
    store = Store()
    if not store.is_on():
        return
    key = session_key()
    if not key:
        return
    payload = read_payload()
    line = blocked_line(payload, last_tool_use_name(payload.get("transcript_path")))
    if line is None:
        return
    state = store.session(key)
    state.blocked = True
    store.save_session(state)
    store.push_event("needs_you", key, line=line)


def cmd_hook_stop(args) -> None:
    store = Store()
    if not store.is_on():
        return
    payload = read_payload()
    if payload.get("stop_hook_active"):
        return
    key = session_key()
    if not key:
        return
    state = store.session(key)
    suppressed = state.suppress_next_stop
    if state.blocked or suppressed:
        state.blocked = False
        state.suppress_next_stop = False
        store.save_session(state)
    if suppressed:
        return
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return
    reply_id = store.create_reply(key, "reply", message)
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "rewrite", reply_id],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def claude_binary() -> str:
    return (
        os.environ.get("LISTENING_CLAUDE_BIN")
        or shutil.which("claude")
        or str(Path.home() / ".local" / "bin" / "claude")
    )


def rewrite_timeout() -> float:
    try:
        return float(os.environ.get("LISTENING_REWRITE_TIMEOUT", DEFAULT_REWRITE_TIMEOUT))
    except ValueError:
        return DEFAULT_REWRITE_TIMEOUT


def haiku_sections(store: Store, written: str):
    """Sections from the nested Haiku call, or None on any failure."""
    prompt = (
        STYLE_GUIDE.read_text()
        + "\n\nThis is update mode: rewrite the following reply for listening.\n\n"
        + written
    )
    try:
        done = subprocess.run(
            [
                claude_binary(),
                "--settings",
                '{"disableAllHooks": true}',
                "-p",
                "--model",
                "haiku",
                "--tools",
                "",
                "--no-session-persistence",
                "--max-turns",
                "1",
                "--output-format",
                "json",
                prompt,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=rewrite_timeout(),
            cwd=store.root,
            env={**os.environ, "LISTENING_NESTED": "1"},
        )
        if done.returncode != 0:
            return None
        out = json.loads(done.stdout)
        if not isinstance(out, dict) or out.get("is_error") is True:
            return None
        result = out.get("result")
        if not isinstance(result, str):
            return None
        return parse_sections(result)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None  # includes timeout, bad JSON and SpokenFormatError


def cmd_rewrite(args) -> None:
    store = Store()
    loaded = store.load_written(args.reply_id)
    if loaded is None:
        return
    key, written = loaded
    sections = haiku_sections(store, written) or fallback_sections(written)
    if not sections:
        return
    store.save_sections(args.reply_id, sections)
    state = store.session(key)
    state.unheard = args.reply_id
    store.save_session(state)
    store.push_event("reply_ready", key, reply_id=args.reply_id)
    store.prune()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="listen.py")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("on").set_defaults(func=cmd_on)
    sub.add_parser("off").set_defaults(func=cmd_off)
    w = sub.add_parser("walkthrough")
    w.add_argument("--title", default=None)
    w.set_defaults(func=cmd_walkthrough)
    sub.add_parser("hook-prompt").set_defaults(func=cmd_hook_prompt)
    sub.add_parser("hook-notify").set_defaults(func=cmd_hook_notify)
    sub.add_parser("hook-stop").set_defaults(func=cmd_hook_stop)
    r = sub.add_parser("rewrite")
    r.add_argument("reply_id")
    r.set_defaults(func=cmd_rewrite)
    return parser


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("LISTENING_NESTED"):
        return 0
    try:
        args = build_parser().parse_args(argv)
    except SystemExit:
        return 0  # a bad invocation must never break a Claude session
    try:
        return args.func(args) or 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
