import json
import os
import re
import secrets
import shutil
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .paths import state_dir


@dataclass
class Section:
    title: str
    text: str


@dataclass
class Reply:
    id: str
    session_key: str
    kind: str  # "reply" or "walkthrough"
    title: str | None
    sections: list[Section] = field(default_factory=list)


@dataclass
class SessionState:
    key: str
    unheard: str | None = None
    walkthrough: str | None = None
    walkthrough_pos: int = 0
    blocked: bool = False
    awaiting_response: bool = False
    suppress_next_stop: bool = False
    listening_context: str | None = None


def _unique_name() -> str:
    """Sortable by time, unique across processes."""
    return f"{time.time_ns():020d}-{os.getpid()}-{secrets.token_hex(3)}"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(3)}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _safe_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else state_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    # on/off flag
    def is_on(self) -> bool:
        return (self.root / "on").exists()

    def set_on(self, on: bool) -> None:
        flag = self.root / "on"
        if on:
            _atomic_write(flag, "")
        else:
            flag.unlink(missing_ok=True)

    # replies
    def _reply_dir(self, reply_id: str) -> Path:
        return self.root / "replies" / reply_id

    def create_reply(
        self, session_key: str, kind: str, written: str, title: str | None = None
    ) -> str:
        reply_id = _unique_name()
        folder = self._reply_dir(reply_id)
        _atomic_write(folder / "written.md", written)
        _atomic_write(
            folder / "meta.json",
            json.dumps({"session_key": session_key, "kind": kind, "title": title}),
        )
        return reply_id

    def save_sections(self, reply_id: str, sections: list[Section]) -> None:
        _atomic_write(
            self._reply_dir(reply_id) / "spoken.json",
            json.dumps([asdict(s) for s in sections]),
        )

    def load_reply(self, reply_id: str) -> Reply | None:
        folder = self._reply_dir(reply_id)
        meta = _read_json(folder / "meta.json")
        spoken = _read_json(folder / "spoken.json")
        if not isinstance(meta, dict) or not isinstance(spoken, list):
            return None
        try:
            return Reply(
                id=reply_id,
                session_key=meta["session_key"],
                kind=meta["kind"],
                title=meta.get("title"),
                sections=[Section(s["title"], s["text"]) for s in spoken],
            )
        except (KeyError, TypeError):
            return None

    def prune(self, keep: int = 50) -> None:
        folders = sorted(p for p in (self.root / "replies").glob("*") if p.is_dir())
        for old in folders[: max(0, len(folders) - keep)]:
            shutil.rmtree(old, ignore_errors=True)

    # sessions
    def _session_path(self, key: str) -> Path:
        return self.root / "sessions" / f"{_safe_key(key)}.json"

    def session(self, key: str) -> SessionState:
        data = _read_json(self._session_path(key))
        if not isinstance(data, dict):
            return SessionState(key=key)
        known = {f.name for f in fields(SessionState)}
        data = {k: v for k, v in data.items() if k in known}
        data["key"] = key
        return SessionState(**data)

    def save_session(self, state: SessionState) -> None:
        _atomic_write(self._session_path(state.key), json.dumps(asdict(state)))

    # events
    def push_event(self, type: str, session_key: str, **data) -> None:
        payload = {**data, "type": type, "session_key": session_key}
        _atomic_write(
            self.root / "events" / f"{_unique_name()}.json", json.dumps(payload)
        )

    def pop_events(self) -> list[dict]:
        events = []
        for path in sorted((self.root / "events").glob("*.json")):
            data = _read_json(path)
            try:
                path.unlink()
            except OSError:
                continue  # another consumer took it
            if isinstance(data, dict):
                events.append(data)
        return events

    # saved microphone
    def set_saved_mic(self, name: str | None) -> None:
        path = self.root / "saved_mic"
        if name is None:
            path.unlink(missing_ok=True)
        else:
            _atomic_write(path, name)

    def saved_mic(self) -> str | None:
        try:
            return (self.root / "saved_mic").read_text() or None
        except OSError:
            return None
