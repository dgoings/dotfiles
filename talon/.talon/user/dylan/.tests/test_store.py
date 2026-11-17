from core.store import Reply, Section, Store


def test_flag_defaults_off_and_toggles(store):
    assert store.is_on() is False
    store.set_on(True)
    assert store.is_on() is True
    store.set_on(False)
    assert store.is_on() is False


def test_reply_round_trip(store):
    rid = store.create_reply("tty:/dev/ttys003", "reply", "hi")
    store.save_sections(rid, [Section("A", "one")])
    assert store.load_reply(rid) == Reply(
        rid, "tty:/dev/ttys003", "reply", None, [Section("A", "one")]
    )


def test_load_reply_without_sections_is_none(store):
    rid = store.create_reply("tty:/dev/ttys003", "reply", "hi")
    assert store.load_reply(rid) is None
    assert store.load_reply("missing") is None


def test_session_defaults_and_persist(store, tmp_path):
    assert store.session("rex:block:1").unheard is None
    state = store.session("rex:block:1")
    state.unheard = "x"
    store.save_session(state)
    assert Store(tmp_path).session("rex:block:1").unheard == "x"


def test_events_fifo_and_consumed(store):
    store.push_event("a", "tty:/dev/ttys003", n=1)
    store.push_event("b", "tty:/dev/ttys003")
    events = store.pop_events()
    assert [e["type"] for e in events] == ["a", "b"]
    assert events[0]["session_key"] == "tty:/dev/ttys003"
    assert events[0]["n"] == 1
    assert store.pop_events() == []


def test_pop_events_skips_corrupt_files(store):
    store.push_event("a", "k")
    (store.root / "events" / "00000000000000000000-0-bad.json").write_text("{nope")
    assert [e["type"] for e in store.pop_events()] == ["a"]
    assert store.pop_events() == []


def test_prune_keeps_newest(store):
    ids = [store.create_reply("k", "reply", str(i)) for i in range(3)]
    for rid in ids:
        store.save_sections(rid, [Section("A", "x")])
    store.prune(keep=2)
    assert store.load_reply(ids[0]) is None
    assert store.load_reply(ids[1]) is not None
    assert store.load_reply(ids[2]) is not None


def test_saved_mic_round_trip(store):
    assert store.saved_mic() is None
    store.set_saved_mic("AU05")
    assert store.saved_mic() == "AU05"
    store.set_saved_mic(None)
    assert store.saved_mic() is None


def test_session_key_with_slashes_round_trips(store):
    state = store.session("tty:/dev/ttys003")
    state.blocked = True
    store.save_session(state)
    again = store.session("tty:/dev/ttys003")
    assert again.key == "tty:/dev/ttys003" and again.blocked is True


def test_load_written(store):
    rid = store.create_reply("rex:block:x", "reply", "hello there")
    assert store.load_written(rid) == ("rex:block:x", "hello there")
    assert store.load_written("nope") is None


def test_clear_awaiting_all(store):
    keys = ["tty:/dev/ttys003", "rex:block:1", "tty:/dev/ttys009"]
    for key, awaiting in zip(keys, (True, True, False)):
        state = store.session(key)
        state.awaiting_response = awaiting
        state.unheard = f"r-{key}"
        store.save_session(state)
    (store.root / "sessions" / "junk.json").write_text("not json")
    store.clear_awaiting_all()
    for key in keys:
        state = store.session(key)
        assert state.awaiting_response is False
        assert state.unheard == f"r-{key}"  # nothing else changes


def test_clear_awaiting_all_without_sessions(store):
    store.clear_awaiting_all()  # no sessions folder yet: nothing to do
