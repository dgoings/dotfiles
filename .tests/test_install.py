import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("install", REPO / ".listening" / "install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)

HERDR = {"hooks": [{"type": "command", "command": "herdr session-start"}]}


@pytest.fixture
def env(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"SessionStart": [HERDR]}, "env": {"A": "1"}}, indent=2) + "\n")
    return settings, tmp_path / "skills"


def run(env, *extra):
    settings, skills = env
    return install.main(["--settings", str(settings), "--skills-dir", str(skills),
                         "--python", sys.executable, *extra])


def load(settings):
    return json.loads(settings.read_text())


def test_install_adds_hooks_keeps_existing(env):
    assert run(env) == 0
    hooks = load(env[0])["hooks"]
    assert hooks["SessionStart"] == [HERDR]
    for event in ("Stop", "Notification", "UserPromptSubmit"):
        assert len(hooks[event]) == 1
    stop = hooks["Stop"][0]["hooks"][0]
    assert stop == {"type": "command", "async": True, "timeout": 10,
                    "command": f"{sys.executable} {REPO}/.listening/listen.py hook-stop"}
    note = hooks["Notification"][0]
    assert note["matcher"] == "permission_prompt"
    assert note["hooks"][0]["async"] is True
    prompt = hooks["UserPromptSubmit"][0]["hooks"][0]
    assert prompt["timeout"] == 5 and "async" not in prompt


def test_install_idempotent(env):
    run(env)
    first = env[0].read_text()
    run(env)
    assert env[0].read_text() == first


def test_install_backs_up(env):
    original = env[0].read_text()
    run(env)
    baks = list(env[0].parent.glob("settings.json.bak-listening-*"))
    assert len(baks) == 1 and baks[0].read_text() == original


def test_uninstall_removes_only_ours(env):
    original = load(env[0])
    run(env)
    assert run(env, "--uninstall") == 0
    assert load(env[0]) == original
    assert not (env[1] / "listen").exists()
    assert len(list(env[0].parent.glob("settings.json.bak-listening-*"))) >= 1


def test_skill_symlink_created(env):
    run(env)
    link = env[1] / "listen"
    assert link.is_symlink()
    assert link.resolve() == (REPO / ".listening" / "skill" / "listen").resolve()


def test_refuses_old_python(env, tmp_path, capsys):
    fake = tmp_path / "oldpy"
    fake.write_text("#!/bin/sh\necho '(3, 9)'\n")
    fake.chmod(0o755)
    before = env[0].read_text()
    rc = install.main(["--settings", str(env[0]), "--skills-dir", str(env[1]), "--python", str(fake)])
    assert rc == 1
    assert env[0].read_text() == before
    assert "3.10" in capsys.readouterr().err


def test_refuses_foreign_skill_dir(env, capsys):
    (env[1] / "listen").mkdir(parents=True)
    before = env[0].read_text()
    assert run(env) == 1
    assert env[0].read_text() == before
    assert not list(env[0].parent.glob("settings.json.bak-*"))
    assert "listen" in capsys.readouterr().err


@pytest.mark.parametrize("content", ['[1, 2]', '{"hooks": {"Stop": {"a": 1}}}', '{"hooks": []}'])
def test_refuses_odd_settings_shape(env, content, capsys):
    env[0].write_text(content)
    assert run(env) == 1
    assert env[0].read_text() == content
    assert not list(env[0].parent.glob("settings.json.bak-*"))
