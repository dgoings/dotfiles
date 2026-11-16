from core.session import own_session_key


def _chain(ttys, parents):
    return (lambda p: ttys.get(p, "??")), (lambda p: parents.get(p, 0))


def test_rex_env_wins():
    assert own_session_key({"REX_BLOCK": "block:9"}, lambda p: "", lambda p: 0, 5) == "rex:block:9"


def test_walks_to_first_real_tty():
    t, p = _chain({50: "??", 40: "??", 30: "ttys003"}, {50: 40, 40: 30, 30: 1})
    assert own_session_key({}, t, p, 50) == "tty:/dev/ttys003"


def test_topmost_tty_wins():
    t, p = _chain(
        {50: "??", 40: "ttys004", 30: "??", 20: "ttys002", 10: "??"},
        {50: 40, 40: 30, 30: 20, 20: 10, 10: 1},
    )
    assert own_session_key({}, t, p, 50) == "tty:/dev/ttys002"


def test_no_tty_returns_none():
    t, p = _chain({50: "??", 40: "??"}, {50: 40, 40: 1})
    assert own_session_key({}, t, p, 50) is None


def test_loop_stops():
    t, p = _chain({50: "ttys001", 40: "??"}, {50: 40, 40: 50})
    assert own_session_key({}, t, p, 50) == "tty:/dev/ttys001"


def test_parent_failure_keeps_found():
    def parent(p):
        raise RuntimeError("boom")

    assert own_session_key({}, lambda p: "ttys007", parent, 50) == "tty:/dev/ttys007"
    assert own_session_key({}, lambda p: "ttys007", lambda p: 0, 50) == "tty:/dev/ttys007"


def test_t3_thread_env_wins_over_rex_and_tty():
    t, p = _chain({50: "ttys003"}, {50: 1})
    env = {"T3CODE_THREAD_ID": "dd7c8f3b-1577-4a1a-ad89-fcb1f0faa080", "REX_BLOCK": "block:9"}
    assert own_session_key(env, t, p, 50) == "t3:dd7c8f3b-1577-4a1a-ad89-fcb1f0faa080"
