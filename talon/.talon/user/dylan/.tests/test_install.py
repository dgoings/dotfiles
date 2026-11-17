import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("install", REPO / ".listening" / "install.py")
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)

HERDR = {"hooks": [{"type": "command", "command": "herdr session-start"}]}


@pytest.fixture(autouse=True)
def fake_home(tmp_path_factory, monkeypatch):
    """An empty home folder, so nothing depends on this Mac's ~/.talon or on
    the interpreter living under the real home."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    return home


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


def expected_command(sub, python=sys.executable, listen=f"{REPO}/.listening/listen.py"):
    return f"/bin/sh -c '\"{python}\" \"{listen}\" {sub} 2>/dev/null; exit 0'"


def test_install_adds_hooks_keeps_existing(env):
    assert run(env) == 0
    hooks = load(env[0])["hooks"]
    assert hooks["SessionStart"] == [HERDR]
    for event in ("Stop", "Notification", "UserPromptSubmit"):
        assert len(hooks[event]) == 1
    stop = hooks["Stop"][0]["hooks"][0]
    assert stop == {"type": "command", "async": True, "timeout": 10,
                    "command": expected_command("hook-stop")}
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


# ---- final review: hooks never block or error a prompt ----


def test_hook_commands_are_wrapped_to_exit_0():
    entries = install.our_entries(sys.executable)
    subs = {"Stop": "hook-stop", "Notification": "hook-notify", "UserPromptSubmit": "hook-prompt"}
    for event, sub in subs.items():
        command = entries[event]["hooks"][0]["command"]
        assert command == expected_command(sub)
        assert install.MARKER in command


def test_rerun_replaces_old_format_entry(env):
    old = {"hooks": [{"type": "command", "async": True, "timeout": 10,
                      "command": f"{sys.executable} {REPO}/.listening/listen.py hook-stop"}]}
    env[0].write_text(json.dumps({"hooks": {"SessionStart": [HERDR], "Stop": [old]}}))
    assert run(env) == 0
    hooks = load(env[0])["hooks"]
    assert hooks["SessionStart"] == [HERDR]
    for event in ("Stop", "Notification", "UserPromptSubmit"):
        assert len(hooks[event]) == 1
        assert len(hooks[event][0]["hooks"]) == 1
    assert hooks["Stop"][0]["hooks"][0]["command"] == expected_command("hook-stop")


def test_rerun_keeps_foreign_hook_sharing_our_group(env):
    mixed = {"hooks": [{"type": "command", "command": "other-tool stop"},
                       {"type": "command", "command": f"python3 {REPO}/.listening/listen.py hook-stop"}]}
    env[0].write_text(json.dumps({"hooks": {"Stop": [mixed]}}))
    assert run(env) == 0
    stop = load(env[0])["hooks"]["Stop"]
    commands = [h["command"] for g in stop for h in g["hooks"]]
    assert commands == ["other-tool stop", expected_command("hook-stop")]


def test_command_with_missing_listen_py_exits_0(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "LISTEN", tmp_path / "gone" / ".listening" / "listen.py")
    for event in ("Stop", "Notification", "UserPromptSubmit"):
        command = install.our_entries(sys.executable)[event]["hooks"][0]["command"]
        r = subprocess.run(command, shell=True, input="{}", capture_output=True, text=True)
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_command_quotes_odd_paths(tmp_path, monkeypatch):
    odd = tmp_path / "it's a \"dir\" $HOME `x`" / ".listening"
    odd.mkdir(parents=True)
    script = odd / "listen.py"
    script.write_text("import sys; print(sys.argv[1:])\n")
    monkeypatch.setattr(install, "LISTEN", script)
    command = install.our_entries(sys.executable)["Stop"]["hooks"][0]["command"]
    assert install.MARKER in command
    r = subprocess.run(command, shell=True, capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (0, "['hook-stop']\n")


# ---- portable paths: "$HOME/...", through ~/.talon/user ----


def test_shell_path_writes_home_as_variable(fake_home):
    assert install.shell_path(fake_home / "a b" / "x.py") == '"$HOME/a b/x.py"'
    assert install.shell_path(fake_home / "it's $x") == '"$HOME/it\'s \\$x"'
    assert install.shell_path("/opt/homebrew/bin/python3") == '"/opt/homebrew/bin/python3"'


def test_hooks_reach_listen_through_talon_user(fake_home, tmp_path, monkeypatch):
    # The folder lives elsewhere (the dotfiles checkout) and is linked into
    # ~/.talon/user, as stow does.
    repo = tmp_path / "dotfiles" / "dylan"
    (repo / ".listening").mkdir(parents=True)
    script = repo / ".listening" / "listen.py"
    script.write_text("import sys; print(sys.argv[1:])\n")
    (fake_home / ".talon" / "user").mkdir(parents=True)
    (fake_home / ".talon" / "user" / "dylan").symlink_to(repo)
    monkeypatch.setattr(install, "REPO", repo.resolve())
    monkeypatch.setattr(install, "LISTEN", script.resolve())

    command = install.our_entries(sys.executable)["Stop"]["hooks"][0]["command"]
    assert '"$HOME/.talon/user/dylan/.listening/listen.py" hook-stop' in command
    assert str(repo) not in command and install.MARKER in command
    r = subprocess.run(command, shell=True, capture_output=True, text=True)
    assert (r.returncode, r.stdout) == (0, "['hook-stop']\n")


def test_skill_link_goes_through_talon_user(env, fake_home):
    (fake_home / ".talon" / "user").mkdir(parents=True)
    (fake_home / ".talon" / "user" / "dylan").symlink_to(install.REPO)
    assert run(env) == 0
    link = env[1] / "listen"
    assert link.readlink() == fake_home / ".talon/user/dylan/.listening/skill/listen"
    assert install.is_our_link(link)
