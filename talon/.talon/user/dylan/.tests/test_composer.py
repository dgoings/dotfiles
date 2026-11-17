from core.composer import GIVE_UP_AFTER, SETTLE, SendWatch


def test_sends_once_new_text_has_settled():
    watch = SendWatch("\n", 0.0)
    assert watch.poll("\n", 1.0) == "wait"
    assert watch.poll("hello there", 4.0) == "wait"
    assert watch.poll("hello there", 4.0 + SETTLE - 0.1) == "wait"
    assert watch.poll("hello there", 4.0 + SETTLE) == "send"


def test_text_from_before_the_stop_is_never_sent():
    watch = SendWatch("draft", 0.0)
    assert watch.poll("draft\n", 5.0) == "wait"
    assert watch.poll("draft", GIVE_UP_AFTER + 1) == "give_up"


def test_a_change_restarts_the_settle_time():
    watch = SendWatch(None, 0.0)
    assert watch.poll("raw text", 1.0) == "wait"
    assert watch.poll("Raw text.", 1.0 + SETTLE) == "wait"
    assert watch.poll("Raw text.", 1.0 + 2 * SETTLE) == "send"


def test_unreadable_or_emptied_box_waits_then_gives_up():
    watch = SendWatch("", 0.0)
    assert watch.poll("hello", 1.0) == "wait"
    assert watch.poll(None, 1.5) == "wait"
    assert watch.poll("hello", 2.0) == "wait"  # settle starts over
    assert watch.poll("", 3.0) == "wait"
    assert watch.poll(None, GIVE_UP_AFTER + 0.1) == "give_up"
