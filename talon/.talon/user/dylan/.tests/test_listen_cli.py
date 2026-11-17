import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / ".venv" / "bin" / "python"
SCRIPT = ROOT / ".listening" / "listen.py"
KEY = "rex:block:t"

PERMISSION = {"notification_type": "permission_prompt", "message": "Claude needs your permission"}


def run(store, *args, stdin="", env_extra=None):
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("REX_BLOCK", "T3CODE_THREAD_ID", "LISTENING_NESTED")}
    env["LISTENING_STATE_DIR"] = str(store.root)
    env["REX_BLOCK"] = "block:t"
    env.update(env_extra or {})
    return subprocess.run(
        [str(PY), str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=env, cwd="/"
    )


def event_types(store):
    return [e["type"] for e in store.pop_events()]


def test_hooks_noop_when_off(store):
    r = run(store, "hook-notify", stdin=json.dumps(PERMISSION))
    assert r.returncode == 0
    assert not (store.root / "events").exists() or not list((store.root / "events").iterdir())
    assert not (store.root / "sessions").exists()


def test_nested_env_noops(store):
    store.set_on(True)
    r = run(store, "hook-notify", stdin=json.dumps(PERMISSION), env_extra={"LISTENING_NESTED": "1"})
    assert r.returncode == 0
    assert store.pop_events() == []


def test_walkthrough_turns_on_and_queues(store):
    r = run(
        store,
        "walkthrough",
        "--title",
        "Design doc",
        stdin=json.dumps({"sections": [{"title": "Intro", "text": "Hi."}]}),
    )
    assert r.returncode == 0, r.stderr
    assert "Walkthrough queued (1 sections)." in r.stdout
    assert store.is_on()
    assert event_types(store) == ["listening_on", "walkthrough_ready"]
    s = store.session(KEY)
    assert s.walkthrough is not None
    assert s.walkthrough_pos == 0
    assert s.suppress_next_stop is True
    reply = store.load_reply(s.walkthrough)
    assert reply.kind == "walkthrough" and reply.title == "Design doc"


def test_walkthrough_bad_json_exits_2(store):
    r = run(store, "walkthrough", "--title", "x", stdin="not json")
    assert r.returncode == 2
    assert r.stderr.strip()
    assert not store.is_on()


def test_prompt_hook_injects_context_once(store):
    store.set_on(True)
    s = store.session(KEY)
    s.listening_context = "Dylan was listening to section 2"
    store.save_session(s)
    payload = json.dumps({"prompt": "what about it?"})
    first = run(store, "hook-prompt", stdin=payload)
    out = json.loads(first.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "section 2" in out["hookSpecificOutput"]["additionalContext"]
    second = run(store, "hook-prompt", stdin=payload)
    assert second.stdout == ""
    assert second.returncode == 0


def test_notify_permission_sets_blocked(store):
    store.set_on(True)
    r = run(store, "hook-notify", stdin=json.dumps(PERMISSION))
    assert r.returncode == 0 and r.stdout == ""
    events = store.pop_events()
    assert len(events) == 1
    assert events[0]["type"] == "needs_you"
    assert events[0]["line"] == "Claude needs you to approve something."
    assert events[0]["session_key"] == KEY
    assert store.session(KEY).blocked is True


def test_notify_plan_and_question_lines(store, tmp_path):
    store.set_on(True)
    plan = {**PERMISSION, "message": "Claude Code needs your approval for the plan"}
    run(store, "hook-notify", stdin=json.dumps(plan))
    assert store.pop_events()[0]["line"] == "Claude has a plan for you to review."

    transcript = tmp_path / "t.jsonl"
    lines = [
        {"type": "api-request-blob", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hm"}, {"type": "tool_use", "name": "AskUserQuestion"}]}},
        {"type": "api-request-blob", "message": {"content": [{"type": "tool_use", "name": "Read"}]}},
    ]
    transcript.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    q = {**PERMISSION, "transcript_path": str(transcript)}
    run(store, "hook-notify", stdin=json.dumps(q))
    assert store.pop_events()[0]["line"] == "Claude has a question for you."


def test_notify_idle_ignored(store):
    store.set_on(True)
    run(store, "hook-notify", stdin=json.dumps({"notification_type": "idle_prompt", "message": "Claude is waiting"}))
    assert store.pop_events() == []


def test_prompt_hook_ignores_task_notifications(store):
    store.set_on(True)
    s = store.session(KEY)
    s.blocked = True
    s.listening_context = "ctx"
    store.save_session(s)
    r = run(store, "hook-prompt", stdin=json.dumps({"prompt": "<task-notification>done</task-notification>"}))
    assert r.stdout == ""
    s = store.session(KEY)
    assert s.blocked is True and s.listening_context == "ctx"


def test_bad_stdin_swallowed(store):
    store.set_on(True)
    for cmd in ("hook-notify", "hook-prompt"):
        r = run(store, cmd, stdin="garbage")
        assert r.returncode == 0 and r.stdout == ""


def test_last_tool_use_name_partial_first_line(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("listen", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = tmp_path / "big.jsonl"
    entry = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "AskUserQuestion"}]}})
    filler = json.dumps({"type": "user", "message": {"content": "x" * 1000}})
    p.write_text((filler + "\n") * 600 + entry + "\n")  # > 256 KB
    assert mod.last_tool_use_name(str(p)) == "AskUserQuestion"
    assert mod.last_tool_use_name(str(tmp_path / "missing")) is None


# ---- Task 5: stop hook and rewrite worker ----

SECTIONS = {"sections": [{"title": "Fake", "text": "Spoken by the fake."}]}
WRITTEN = "## Heading\n\nSome written reply text for the fallback."


@pytest.fixture
def fake_claude(tmp_path):
    path = tmp_path / "fake-claude"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "rec = os.environ.get('FAKE_RECORD')\n"
        "if rec:\n"
        "    json.dump({'argv': sys.argv[1:], 'nested': os.environ.get('LISTENING_NESTED')}, open(rec, 'w'))\n"
        "mode = os.environ.get('FAKE_MODE', 'ok')\n"
        "if mode == 'fail':\n"
        "    sys.exit(1)\n"
        "if mode == 'sleep':\n"
        "    time.sleep(5)\n"
        "if mode == 'garbage':\n"
        "    print('not json')\n"
        "    sys.exit(0)\n"
        "print(json.dumps({'result': json.dumps(" + repr(SECTIONS) + ")}))\n"
    )
    path.chmod(0o755)
    return path


def make_reply(store, written=WRITTEN):
    return store.create_reply(KEY, "reply", written)


def rewrite(store, fake, rid, mode="ok", on=True, **extra):
    if on:
        store.set_on(True)
    env = {"LISTENING_CLAUDE_BIN": str(fake), "FAKE_MODE": mode, **extra}
    return run(store, "rewrite", rid, env_extra=env)


def test_stop_hook_returns_fast(store, fake_claude):
    import time

    store.set_on(True)
    payload = json.dumps({"last_assistant_message": "Hello."})
    t = time.monotonic()
    r = run(
        store,
        "hook-stop",
        stdin=payload,
        env_extra={"LISTENING_CLAUDE_BIN": str(fake_claude), "FAKE_MODE": "sleep"},
    )
    assert r.returncode == 0, r.stderr
    assert time.monotonic() - t < 1
    assert (store.root / "replies").exists() and len(list((store.root / "replies").iterdir())) == 1


def test_rewrite_saves_sections_and_event(store, fake_claude):
    rid = make_reply(store)
    r = rewrite(store, fake_claude, rid)
    assert r.returncode == 0, r.stderr
    reply = store.load_reply(rid)
    assert [(s.title, s.text) for s in reply.sections] == [("Fake", "Spoken by the fake.")]
    assert store.session(KEY).unheard == rid
    events = store.pop_events()
    assert [e["type"] for e in events] == ["reply_ready"]
    assert events[0]["reply_id"] == rid


@pytest.mark.parametrize("mode", ["fail", "garbage"])
def test_rewrite_falls_back_on_failure(store, fake_claude, mode):
    from core.spoken import fallback_sections

    rid = make_reply(store)
    rewrite(store, fake_claude, rid, mode=mode)
    assert store.load_reply(rid).sections == fallback_sections(WRITTEN)
    assert event_types(store) == ["reply_ready"]


def test_rewrite_falls_back_on_timeout(store, fake_claude):
    from core.spoken import fallback_sections

    rid = make_reply(store)
    rewrite(store, fake_claude, rid, mode="sleep", LISTENING_REWRITE_TIMEOUT="1")
    assert store.load_reply(rid).sections == fallback_sections(WRITTEN)
    assert event_types(store) == ["reply_ready"]


def test_rewrite_blank_reply_saves_nothing(store, fake_claude):
    rid = make_reply(store, "   \n")
    rewrite(store, fake_claude, rid, mode="fail")
    assert store.load_reply(rid) is None
    assert store.pop_events() == []


def test_rewrite_passes_no_hooks_and_nested_env(store, fake_claude, tmp_path):
    record = tmp_path / "record.json"
    rid = make_reply(store)
    rewrite(store, fake_claude, rid, FAKE_RECORD=str(record))
    seen = json.loads(record.read_text())
    argv = seen["argv"]
    assert argv[argv.index("--settings") + 1] == '{"disableAllHooks": true}'
    assert argv[argv.index("--model") + 1] == "haiku"
    assert seen["nested"] == "1"
    assert WRITTEN in argv[-1]


def test_stop_suppressed_after_walkthrough(store):
    store.set_on(True)
    state = store.session(KEY)
    state.suppress_next_stop = True
    state.blocked = True
    store.save_session(state)
    r = run(store, "hook-stop", stdin=json.dumps({"last_assistant_message": "Hi"}))
    assert r.returncode == 0
    assert not (store.root / "replies").exists() or not list((store.root / "replies").iterdir())
    after = store.session(KEY)
    assert after.suppress_next_stop is False
    assert after.blocked is False


def test_stop_hook_active_noops(store):
    store.set_on(True)
    r = run(
        store,
        "hook-stop",
        stdin=json.dumps({"stop_hook_active": True, "last_assistant_message": "Hi"}),
    )
    assert r.returncode == 0
    assert not (store.root / "replies").exists() or not list((store.root / "replies").iterdir())


def test_stop_clears_blocked_and_noops_on_empty(store):
    store.set_on(True)
    state = store.session(KEY)
    state.blocked = True
    store.save_session(state)
    run(store, "hook-stop", stdin=json.dumps({"last_assistant_message": "  "}))
    assert store.session(KEY).blocked is False
    assert not (store.root / "replies").exists() or not list((store.root / "replies").iterdir())


# ---- final review fixes ----


def load_listen_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("listen_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_core_exits_0_silently(store, tmp_path):
    lonely = tmp_path / "elsewhere" / ".listening"
    lonely.mkdir(parents=True)
    copy = lonely / "listen.py"
    copy.write_text(SCRIPT.read_text())
    store.set_on(True)
    env = {k: v for k, v in __import__("os").environ.items()
           if k not in ("T3CODE_THREAD_ID", "LISTENING_NESTED")}
    env["LISTENING_STATE_DIR"] = str(store.root)
    for sub in ("hook-prompt", "hook-stop", "hook-notify"):
        r = subprocess.run([str(PY), str(copy), sub], input="{}", capture_output=True,
                           text=True, env=env, cwd="/")
        assert (r.returncode, r.stdout, r.stderr) == (0, "", ""), sub


def test_missing_style_guide_falls_back(store, fake_claude, tmp_path, monkeypatch):
    from core.spoken import fallback_sections

    mod = load_listen_module()
    monkeypatch.setattr(mod, "STYLE_GUIDE", tmp_path / "no-such-style-guide.md")
    monkeypatch.setenv("LISTENING_CLAUDE_BIN", str(fake_claude))
    monkeypatch.delenv("LISTENING_NESTED", raising=False)
    store.set_on(True)
    rid = make_reply(store)
    assert mod.main(["rewrite", rid]) == 0
    assert store.load_reply(rid).sections == fallback_sections(WRITTEN)
    assert store.session(KEY).unheard == rid
    assert event_types(store) == ["reply_ready"]


def test_prompt_hook_pushes_prompt_sent_once(store):
    store.set_on(True)
    r = run(store, "hook-prompt", stdin=json.dumps({"prompt": "typed answer"}))
    assert (r.returncode, r.stdout) == (0, "")
    events = store.pop_events()
    assert [(e["type"], e["session_key"]) for e in events] == [("prompt_sent", KEY)]
    assert isinstance(events[0]["at"], float)


def test_prompt_hook_pushes_prompt_sent_alongside_context(store):
    store.set_on(True)
    s = store.session(KEY)
    s.blocked = True
    s.listening_context = "ctx"
    store.save_session(s)
    r = run(store, "hook-prompt", stdin=json.dumps({"prompt": "answer"}))
    assert "ctx" in r.stdout
    assert event_types(store) == ["prompt_sent"]


def test_prompt_hook_no_prompt_sent_for_task_notification_or_off(store):
    store.set_on(True)
    run(store, "hook-prompt", stdin=json.dumps({"prompt": "<task-notification>x</task-notification>"}))
    assert store.pop_events() == []
    store.set_on(False)
    run(store, "hook-prompt", stdin=json.dumps({"prompt": "typed"}))
    assert store.pop_events() == []


def test_rewrite_after_listening_off_saves_but_does_not_announce(store, fake_claude):
    rid = make_reply(store)
    r = rewrite(store, fake_claude, rid, on=False)
    assert r.returncode == 0
    assert store.load_reply(rid) is not None  # sections saved, harmless
    assert store.session(KEY).unheard is None
    assert not (store.root / "sessions").exists() or not list((store.root / "sessions").iterdir())
    assert store.pop_events() == []
