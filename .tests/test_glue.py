"""listening/listening.py (the Talon glue), loaded against a stub `talon` module.

Nothing here speaks, plays a sound, or touches the real mic or Talon modes:
subprocess, focus lookup and every talon action are fakes that only record.
"""

import importlib.util
import sys
import time
import types
from pathlib import Path

import pytest

from core.store import Section

REPO = Path(__file__).resolve().parent.parent
KEY = "tty:/dev/ttys003"
OTHER = "tty:/dev/ttys004"
MIC = "Built-in Mic"


class FakeProc:
    pid = 4242

    def poll(self):
        return None  # still speaking

    def terminate(self):
        pass


def fake_talon(log):
    talon = types.ModuleType("talon")

    class Module:
        def mode(self, *a, **k):
            pass

        def setting(self, *a, **k):
            pass

        def action_class(self, cls):
            return cls

    settings_values = {
        "user.listening_engine": "say",
        "user.listening_voice": "Samantha",
        "user.listening_rate": 190,
    }
    talon.Module = Module
    talon.actions = types.SimpleNamespace(
        user=types.SimpleNamespace(ulanzi_key=lambda keys: log.append(("key", keys))),
        sound=types.SimpleNamespace(
            active_microphone=lambda: log.mic,
            set_microphone=lambda name: (log.append(("mic", name)), setattr(log, "mic", name)),
        ),
        mode=types.SimpleNamespace(
            enable=lambda m: log.append(("enable", m)),
            disable=lambda m: log.append(("disable", m)),
        ),
    )
    talon.app = types.SimpleNamespace(register=lambda *a: None, notify=lambda *a: None)
    talon.cron = types.SimpleNamespace(interval=lambda *a: None)
    talon.scope = types.SimpleNamespace(get=lambda name: set())
    talon.settings = types.SimpleNamespace(get=lambda name: settings_values[name])
    talon.ui = types.SimpleNamespace()
    return talon


class Log(list):
    mic = MIC

    def keys(self):
        return [v for k, v in self if k == "key"]

    def mics(self):
        return [v for k, v in self if k == "mic"]


@pytest.fixture
def glue(store, monkeypatch):
    log = Log()
    monkeypatch.setitem(sys.modules, "talon", fake_talon(log))
    pkg = types.ModuleType("lglue")
    pkg.__path__ = [str(REPO / "listening")]
    monkeypatch.setitem(sys.modules, "lglue", pkg)
    spec = importlib.util.spec_from_file_location("lglue.listening", REPO / "listening" / "listening.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lglue.listening"] = mod
    try:
        spec.loader.exec_module(mod)
        monkeypatch.setattr(mod, "_lookup_focus", lambda: KEY)
        monkeypatch.setattr(mod, "_in_claude_terminal", lambda: True)
        monkeypatch.setattr(
            mod,
            "subprocess",
            types.SimpleNamespace(
                Popen=lambda *a, **k: FakeProc(),
                run=lambda *a, **k: types.SimpleNamespace(stdout=""),
                DEVNULL=-3,
            ),
        )
        mod.log = log
        mod._turn_on()
        yield mod
    finally:
        for name in [n for n in sys.modules if n == "lglue" or n.startswith("lglue.")]:
            del sys.modules[name]


def add_unheard(store, key, texts):
    rid = store.create_reply(key, "reply", "written")
    store.save_sections(rid, [Section(f"Part {i + 1}", t) for i, t in enumerate(texts)])
    state = store.session(key)
    state.unheard = rid
    store.save_session(state)
    return rid


def prompt_sent(store, key, at=None):
    store.push_event("prompt_sent", key, at=time.time() if at is None else at)


# --- item 3: a response sent by keyboard wakes Talon up -------------------------


def test_keyboard_send_finishes_respond_without_space(glue, store):
    glue.Actions.listening_respond()
    assert glue._responding and glue.log.keys() == ["space"]
    assert glue.log.mic == "None"
    prompt_sent(store, KEY)
    glue._tick()
    assert glue._responding is False
    assert glue.player.phase == "idle"
    assert glue.log.keys() == ["space"]  # no second Space
    assert glue.log.mic == MIC  # Talon hears again


def test_keyboard_send_plays_awaited_answer_that_already_arrived(glue, store):
    glue.Actions.listening_respond()
    add_unheard(store, KEY, ["answer"])
    prompt_sent(store, KEY)
    glue._tick()
    assert glue._responding is False
    assert glue.player.phase == "speaking"


def test_voice_key_second_press_still_sends_and_later_prompt_sent_is_a_noop(glue, store):
    assert glue.Actions.listening_intercept("voice") is True
    assert glue.Actions.listening_intercept("voice") is True
    assert glue.log.keys() == ["space", "space"]
    assert glue._responding is False
    mics = list(glue.log.mics())
    prompt_sent(store, KEY)
    glue._tick()
    assert glue.log.keys() == ["space", "space"]
    assert glue.log.mics() == mics


def test_prompt_sent_for_another_session_or_from_before_is_ignored(glue, store):
    glue.Actions.listening_respond()
    prompt_sent(store, OTHER)
    prompt_sent(store, KEY, at=time.time() - 60)  # typed before the respond started
    glue._tick()
    assert glue._responding is True
    assert glue.log.mic == "None"


# --- item 4: "listening off" mid-respond stops /voice ---------------------------


def test_listening_off_mid_respond_presses_space(glue):
    glue.Actions.listening_respond()
    glue.Actions.listening_off()
    assert glue.log.keys() == ["space", "space"]
    assert glue._responding is False and glue._on is False
    assert glue.log.mic == MIC


def test_listening_off_when_not_responding_presses_nothing(glue):
    glue.Actions.listening_off()
    assert glue.log.keys() == []


# --- item 5: an exception after claiming a control never falls through -----------


def boom(*a, **k):
    raise RuntimeError("boom")


def test_intercept_exception_after_claim_returns_true(glue, store, monkeypatch):
    add_unheard(store, KEY, ["one"])
    monkeypatch.setattr(glue.player, "go_ahead", boom)
    assert glue.Actions.listening_intercept("knob_press") is True


def test_intercept_exception_in_talon_or_voice_branch_returns_true(glue, monkeypatch):
    monkeypatch.setattr(glue, "_start_respond", boom)
    assert glue.Actions.listening_intercept("voice") is True
    monkeypatch.setattr(glue, "_listening_off", boom)
    assert glue.Actions.listening_intercept("talon") is True


def test_intercept_exception_before_claim_returns_false(glue, monkeypatch):
    monkeypatch.setattr(glue.player, "has_something", boom)
    assert glue.Actions.listening_intercept("knob_press") is False


# --- item 9: speech that fails to start never leaves Talon deaf -------------------


def test_speak_failure_finishes_section_and_restores_mic(glue, store, monkeypatch):
    add_unheard(store, KEY, ["one", "two"])
    monkeypatch.setattr(glue, "_say_command", boom)
    glue.Actions.listening_go_ahead()
    assert glue.log.mic == "None"
    assert isinstance(glue._say, glue._FailedSay)
    glue._tick()
    assert glue.player.phase == "waiting"
    assert glue.log.mic == MIC
