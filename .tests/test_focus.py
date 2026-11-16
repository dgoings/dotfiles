import json

from core.focus import focused_session_key, t3_key

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


# --- T3 Code -------------------------------------------------------------------

T3 = "com.t3tools.t3code"
ENV = "0d222d51-200a-45cc-91a7-a33bd7fdbc9d"
THREAD = "1aa5ff5d-6693-4fa5-9d3e-61c2205d1681"
T3_URL = f"t3code://app/#/{ENV}/{THREAD}"  # real page address of an open thread


def test_t3_thread_from_page_address():
    assert focused_session_key(T3, "T3 Code (Beta)", fake({}), lambda: T3_URL) == "t3:" + THREAD
    assert t3_key(T3_URL + "?panel=diff") == "t3:" + THREAD
    assert t3_key(T3_URL + "/files") == "t3:" + THREAD


def test_t3_pages_that_are_not_a_thread_none():
    for url in (None, "", "t3code://app/#/", "t3code://app/#/settings", f"t3code://app/#/{ENV}",
                f"t3code://app/#/{ENV}/draft", f"https://example.com/#/{ENV}/{THREAD}"):
        assert t3_key(url) is None


def test_t3_without_reader_or_failing_reader_none():
    def boom():
        raise RuntimeError("no window")
    assert focused_session_key(T3, "t", fake({})) is None
    assert focused_session_key(T3, "t", fake({}), boom) is None
