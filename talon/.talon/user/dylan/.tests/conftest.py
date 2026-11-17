import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "listening"))

from core.store import Store  # noqa: E402


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LISTENING_STATE_DIR", str(tmp_path))
    return Store(tmp_path)
