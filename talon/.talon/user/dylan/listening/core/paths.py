import os
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "talon-listening"


def state_dir() -> Path:
    path = Path(os.environ.get("LISTENING_STATE_DIR") or DEFAULT_STATE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path
