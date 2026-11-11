import json

from core.focus import focused_session_key

GHOSTTY = "com.mitchellh.ghostty"
REX = "com.superlogical.rex"
REX_CLI = "/Applications/Rex Beta.app/Contents/Helpers/Rex Server.rex/Contents/MacOS/rex"
OSA = [
    "osascript",
    "-e",
    'tell application "Ghostty" to get tty of focused terminal of selected tab of front window',
]

S1 = "session:01a1ad96-09d6-7bdf-92c6-66d909ead96e"
S2 = "session:01a1cadd-0ece-7c63-a047-d2b281b4b154"


def client_ls(*session_ids):
    # Trimmed from real `rex client ls --json` output.
    return json.dumps({"clients": [
        {"client_id": "client:a", "info": {"kind": "app", "platform": "macos",
         "name": "Rex Beta", "label": "Dylan MBP"},
         "connection_state": "connected", "session_ids": list(session_ids)},
        {"client_id": "client:b", "principal": {"kind": "peer"},
         "connection_state": "connected"},
        {"client_id": "client:c", "info": {"kind": "cli", "name": "rex"},
         "connection_state": "connected"},
    ]})


def inspect(label, block):
    # Trimmed from real `rex session inspect S --json` output.
    return json.dumps({
        "session_id": "session:x", "label": label,
        "active_window_id": "window:2",
        "windows": [
            {"window_id": "window:1", "label": "Window 1", "focused_block_id": "block:other"},
            {"window_id": "window:2", "label": "Window 2", "focused_block_id": block},
        ],
    })


def fake(table):
    def run(args):
        key = tuple(args)
        if key not in table:
            raise RuntimeError(f"unexpected {args}")
        v = table[key]
        if isinstance(v, Exception):
            raise v
        return v
    return run


def test_ghostty_tty():
    run = fake({tuple(OSA): "/dev/ttys003\n"})
    assert focused_session_key(GHOSTTY, "", run) == "tty:/dev/ttys003"


def test_ghostty_bad_output_none():
    assert focused_session_key(GHOSTTY, "", fake({tuple(OSA): ""})) is None
    assert focused_session_key(GHOSTTY, "", fake({tuple(OSA): "missing value"})) is None


def test_rex_single_session():
    run = fake({
        (REX_CLI, "client", "ls", "--json"): client_ls(S1),
        (REX_CLI, "session", "inspect", S1, "--json"): inspect("a", "block:abc"),
    })
    assert focused_session_key(REX, "whatever", run) == "rex:block:abc"


def test_rex_two_sessions_picks_title_match():
    run = fake({
        (REX_CLI, "client", "ls", "--json"): client_ls(S1, S2),
        (REX_CLI, "session", "inspect", S1, "--json"): inspect("alpha", "block:1"),
        (REX_CLI, "session", "inspect", S2, "--json"): inspect("ds9-replan-scope", "block:2"),
    })
    assert focused_session_key(REX, "claude - ds9-replan-scope", run) == "rex:block:2"


def test_rex_two_sessions_no_match_none():
    run = fake({
        (REX_CLI, "client", "ls", "--json"): client_ls(S1, S2),
        (REX_CLI, "session", "inspect", S1, "--json"): inspect("alpha", "block:1"),
        (REX_CLI, "session", "inspect", S2, "--json"): inspect("beta", "block:2"),
    })
    assert focused_session_key(REX, "claude - gamma", run) is None


def test_rex_no_focused_block_none():
    run = fake({
        (REX_CLI, "client", "ls", "--json"): client_ls(S1),
        (REX_CLI, "session", "inspect", S1, "--json"):
            json.dumps({"label": "a", "active_window_id": "window:9", "windows": []}),
    })
    assert focused_session_key(REX, "x", run) is None


def test_failure_returns_none():
    def boom(args):
        raise TimeoutError("slow")
    assert focused_session_key(GHOSTTY, "", boom) is None
    assert focused_session_key(REX, "t", boom) is None


def test_garbage_json_returns_none():
    run = fake({(REX_CLI, "client", "ls", "--json"): "not json"})
    assert focused_session_key(REX, "t", run) is None


def test_unknown_app_none():
    assert focused_session_key("com.apple.Safari", "t", fake({})) is None
