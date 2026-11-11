from core.player import Chime, Deafen, Listen, Player, Speak, StopSpeech
from core.store import Section

KEY = "tty:/dev/ttys003"
OTHER = "tty:/dev/ttys004"
CANT_TELL = "I can't tell which Claude session is in front."


def make_reply(store, key, texts, kind="reply", title=None):
    rid = store.create_reply(key, kind, "written", title)
    store.save_sections(rid, [Section(f"Part {i + 1}", t) for i, t in enumerate(texts)])
    return rid


def add_unheard(store, key, texts):
    rid = make_reply(store, key, texts)
    state = store.session(key)
    state.unheard = rid
    store.save_session(state)
    return rid


def add_walkthrough(store, key, texts, pos=0, title="the design doc"):
    rid = make_reply(store, key, texts, kind="walkthrough", title=title)
    state = store.session(key)
    state.walkthrough = rid
    state.walkthrough_pos = pos
    store.save_session(state)
    return rid


def ready(key, rid="x"):
    return {"type": "reply_ready", "session_key": key, "reply_id": rid}


def play(text):
    return [Deafen(), Speak(text)]


# --- brief tests -------------------------------------------------------------


def test_go_ahead_plays_first_section_then_waits(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    assert p.go_ahead(KEY) == play("one")
    assert p.phase == "speaking"
    assert p.section_finished() == [Listen()]
    assert p.phase == "waiting"


def test_continue_repeat_back_skip(store):
    add_unheard(store, KEY, ["one", "two", "three", "four"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    assert p.continue_() == play("two")
    p.section_finished()
    assert p.repeat() == play("two")
    p.section_finished()
    assert p.back() == play("one")
    p.section_finished()
    assert p.skip() == [StopSpeech(), Deafen(), Speak("two")]


def test_last_section_adds_thats_everything(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    assert p.continue_() == play("two That's everything.")
    assert p.section_finished() == [Listen()]
    assert p.phase == "idle"


def test_nothing_new(store):
    assert Player(store).go_ahead(KEY) == [Speak("Nothing new here.")]


def test_no_focus_says_cant_tell(store):
    add_unheard(store, KEY, ["one"])
    p = Player(store)
    assert p.go_ahead(None) == [Speak(CANT_TELL)]
    assert p.phase == "idle"


def test_unheard_beats_walkthrough_then_walkthrough_resumes(store):
    add_walkthrough(store, KEY, ["w1", "w2", "w3"], pos=1)
    add_unheard(store, KEY, ["answer"])
    p = Player(store)
    assert p.go_ahead(KEY) == play("answer")
    assert store.session(KEY).unheard is None
    assert p.section_finished() == play("Back to the walkthrough. w2")
    assert store.session(KEY).walkthrough_pos == 2
    assert p.section_finished() == [Listen()]
    assert p.continue_() == play("w3 That's everything.")
    assert p.section_finished() == [Listen()]
    state = store.session(KEY)
    assert (state.walkthrough, state.walkthrough_pos) == (None, 0)


def test_respond_sets_context_and_awaits(store):
    add_unheard(store, KEY, ["one", "two", "three"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    p.continue_()
    assert p.respond_started(KEY) == [StopSpeech(), Deafen()]
    assert p.phase == "responding"
    state = store.session(KEY)
    assert state.awaiting_response is True
    assert state.listening_context == (
        "Dylan was listening to section 2 of 3, titled 'Part 2', "
        "of the reply, when he responded."
    )
    assert p.respond_finished(KEY) == [Listen()]
    assert p.phase == "idle"


def test_awaited_answer_autoplays(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.respond_started(KEY)
    p.respond_finished(KEY)
    rid = add_unheard(store, KEY, ["the answer"])
    assert p.handle_event(ready(KEY, rid), KEY) == [
        Chime("done", False),
        Deafen(),
        Speak("the answer That's everything."),
    ]
    assert store.session(KEY).awaiting_response is False


def test_reply_while_speaking_only_chimes(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    state = store.session(KEY)
    state.awaiting_response = True
    store.save_session(state)
    rid = add_unheard(store, KEY, ["new"])
    assert p.handle_event(ready(KEY, rid), KEY) == [Chime("done", False)]
    assert p.phase == "speaking"


def test_background_reply_soft_chime(store):
    rid = add_unheard(store, OTHER, ["one"])
    p = Player(store)
    assert p.handle_event(ready(OTHER, rid), KEY) == [Chime("done", True)]
    assert p.handle_event(ready(OTHER, rid), None) == [Chime("done", True)]


def test_needs_you_focused_speaks_line(store):
    line = "Claude needs you to approve something."
    event = {"type": "needs_you", "session_key": KEY, "line": line}
    p = Player(store)
    assert p.handle_event(event, KEY) == [
        Chime("needs_you", False),
        Deafen(),
        Speak(line),
    ]
    assert Player(store).handle_event(event, OTHER) == [Chime("needs_you", True)]


def test_reset_stops_and_clears(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.reset() == [StopSpeech()]
    assert p.phase == "idle"
    assert (p.key, p.reply_id, p.index, p.last_played) == (None, None, 0, None)
    assert p.go_ahead(KEY) == [Speak("Nothing new here.")]


def test_blocked_session_has_nothing(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    assert p.has_something(KEY) is True
    p.go_ahead(KEY)
    state = store.session(KEY)
    state.blocked = True
    store.save_session(state)
    assert p.has_something(KEY) is False


# --- rulings -----------------------------------------------------------------


def test_stop_keeps_position_for_go_ahead(store):
    add_unheard(store, KEY, ["one", "two", "three"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    assert p.stop() == [StopSpeech(), Listen()]
    assert p.phase == "idle"
    assert p.go_ahead(KEY) == play("two")


def test_unheard_replaces_paused_position(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.stop()
    add_unheard(store, KEY, ["fresh"])
    assert p.go_ahead(KEY) == play("fresh That's everything.")


def test_go_ahead_while_waiting_continues(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    add_unheard(store, KEY, ["newer"])  # waiting between sections: go ahead = continue
    assert p.go_ahead(KEY) == play("two That's everything.")


def test_go_ahead_resumes_walkthrough_at_saved_pos(store):
    add_walkthrough(store, KEY, ["w1", "w2", "w3"], pos=1)
    p = Player(store)
    assert p.go_ahead(KEY) == play("w2")
    assert store.session(KEY).walkthrough_pos == 2


def test_continue_with_nothing_does_nothing(store):
    p = Player(store)
    assert p.continue_() == []
    assert p.repeat() == []
    assert p.back() == []
    assert p.skip() == []


def test_back_stays_at_first_section(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    assert p.back() == play("one")


def test_repeat_while_speaking_stops_first(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.repeat() == [StopSpeech(), Deafen(), Speak("one")]


def test_skip_past_last_section_finishes(store):
    add_unheard(store, KEY, ["one"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.skip() == [StopSpeech(), Listen()]
    assert p.phase == "idle"
    assert p.repeat() == []


def test_skip_past_reply_returns_to_walkthrough(store):
    add_walkthrough(store, KEY, ["w1", "w2"], pos=1)
    add_unheard(store, KEY, ["answer"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.skip() == [
        StopSpeech(),
        Deafen(),
        Speak("Back to the walkthrough. w2 That's everything."),
    ]


def test_needs_you_notice_restores_prior_phase(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    event = {"type": "needs_you", "session_key": KEY, "line": "Claude has a question for you."}
    p.handle_event(event, KEY)
    assert p.phase == "speaking"
    assert p.section_finished() == [Listen()]
    assert p.phase == "waiting"
    assert p.continue_() == play("two That's everything.")


def test_needs_you_while_speaking_only_chimes(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    event = {"type": "needs_you", "session_key": KEY, "line": "Claude has a question for you."}
    assert p.handle_event(event, KEY) == [Chime("needs_you", False)]


def test_respond_mid_walkthrough_context_and_resume(store):
    add_walkthrough(store, KEY, ["w1", "w2", "w3"], title="the design doc")
    p = Player(store)
    p.go_ahead(KEY)
    p.respond_started(KEY)
    assert store.session(KEY).listening_context == (
        "Dylan was listening to section 1 of 3, titled 'Part 1', "
        "of the walkthrough 'the design doc', when he responded."
    )
    p.respond_finished(KEY)
    rid = add_unheard(store, KEY, ["answer"])
    assert p.handle_event(ready(KEY, rid), KEY) == [
        Chime("done", False),
        Deafen(),
        Speak("answer"),
    ]
    assert p.section_finished() == play("Back to the walkthrough. w2")


def test_untitled_walkthrough_and_section(store):
    rid = store.create_reply(KEY, "walkthrough", "written", None)
    store.save_sections(rid, [Section("", "w1")])
    state = store.session(KEY)
    state.walkthrough = rid
    store.save_session(state)
    p = Player(store)
    p.go_ahead(KEY)
    p.respond_started(KEY)
    assert store.session(KEY).listening_context == (
        "Dylan was listening to section 1 of 1, titled 'untitled', "
        "of the walkthrough 'untitled', when he responded."
    )


def test_respond_without_reply_only_awaits(store):
    p = Player(store)
    assert p.respond_started(KEY) == [StopSpeech(), Deafen()]
    assert p.phase == "responding"
    state = store.session(KEY)
    assert state.awaiting_response is True
    assert state.listening_context is None


def test_reply_while_responding_only_chimes(store):
    p = Player(store)
    p.respond_started(KEY)
    rid = add_unheard(store, KEY, ["answer"])
    assert p.handle_event(ready(KEY, rid), KEY) == [Chime("done", False)]
    assert p.phase == "responding"


def test_respond_finished_plays_answer_that_arrived_during_dictation(store):
    p = Player(store)
    p.respond_started(KEY)
    rid = add_unheard(store, KEY, ["answer"])
    p.handle_event(ready(KEY, rid), KEY)
    assert p.respond_finished(KEY) == [
        Listen(),
        Deafen(),
        Speak("answer That's everything."),
    ]
    assert store.session(KEY).awaiting_response is False


def test_focused_reply_not_awaited_only_chimes(store):
    rid = add_unheard(store, KEY, ["one"])
    p = Player(store)
    assert p.handle_event(ready(KEY, rid), KEY) == [Chime("done", False)]
    assert p.phase == "idle"


def test_awaited_answer_plays_after_current_section(store):
    # Review Focus 5: the awaited answer arrives mid-section; it plays once that ends.
    add_walkthrough(store, KEY, ["w1", "w2", "w3"])
    p = Player(store)
    p.go_ahead(KEY)
    p.respond_started(KEY)
    p.respond_finished(KEY)
    assert p.go_ahead(KEY) == play("w2")
    rid = add_unheard(store, KEY, ["answer"])
    assert p.handle_event(ready(KEY, rid), KEY) == [Chime("done", False)]
    assert p.section_finished() == play("answer")
    assert p.section_finished() == play("Back to the walkthrough. w3 That's everything.")


def test_walkthrough_ready(store):
    add_unheard(store, KEY, ["old one", "old two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()  # waiting on the old reply; the new walkthrough wins
    rid = add_walkthrough(store, KEY, ["w1", "w2"])
    event = {"type": "walkthrough_ready", "session_key": KEY, "reply_id": rid}
    assert p.handle_event(event, KEY) == play("w1")
    assert Player(store).handle_event(event, OTHER) == [Chime("done", True)]


def test_listening_on_and_off_events(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    assert p.handle_event({"type": "listening_on", "session_key": ""}, KEY) == [Listen()]
    p.go_ahead(KEY)
    assert p.handle_event({"type": "listening_off", "session_key": ""}, KEY) == [StopSpeech()]
    assert p.phase == "idle"
    assert p.handle_event({"type": "bogus", "session_key": KEY}, KEY) == []


def test_has_something_by_phase_and_store(store):
    p = Player(store)
    assert p.has_something(KEY) is False
    assert p.has_something(None) is False
    add_walkthrough(store, KEY, ["w1"])
    assert p.has_something(KEY) is True
    p.respond_started(KEY)
    assert p.has_something(None) is True


def test_finished_walkthrough_is_not_something(store):
    add_walkthrough(store, KEY, ["w1"], pos=1)  # last section already started
    p = Player(store)
    assert p.has_something(KEY) is False
    assert p.go_ahead(KEY) == [Speak("Nothing new here.")]
    assert store.session(KEY).walkthrough is None


def test_finishing_old_walkthrough_keeps_newer_one(store):
    add_walkthrough(store, KEY, ["a1"])
    p = Player(store)
    p.go_ahead(KEY)
    newer = add_walkthrough(store, KEY, ["b1"])
    event = {"type": "walkthrough_ready", "session_key": KEY, "reply_id": newer}
    assert p.handle_event(event, KEY) == [Chime("done", False)]
    assert p.section_finished() == [Listen()]
    assert store.session(KEY).walkthrough == newer
    assert p.go_ahead(KEY) == play("b1 That's everything.")


# --- fix round 1 -------------------------------------------------------------


def test_waiting_and_paused_count_only_for_their_own_session(store):
    add_unheard(store, KEY, ["one", "two", "three"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.has_something(OTHER) is True  # speaking: key 3 stops it anywhere
    p.section_finished()
    assert (p.has_something(KEY), p.has_something(OTHER)) == (True, False)
    p.stop()
    assert (p.has_something(KEY), p.has_something(OTHER)) == (True, False)


def test_respond_goes_to_focused_session(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.stop()
    assert p.respond_started(OTHER) == [StopSpeech(), Deafen()]
    other = store.session(OTHER)
    assert (other.awaiting_response, other.listening_context) == (True, None)
    key = store.session(KEY)
    assert (key.awaiting_response, key.listening_context) == (False, None)
    add_unheard(store, OTHER, ["answer"])  # arrives while he's still dictating
    assert p.respond_finished(OTHER) == [Listen(), Deafen(), Speak("answer That's everything.")]


def test_go_ahead_taking_unheard_clears_awaiting(store):
    state = store.session(KEY)
    state.awaiting_response = True
    store.save_session(state)
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    assert store.session(KEY).awaiting_response is False


def test_focused_walkthrough_ready_clears_awaiting(store):
    p = Player(store)
    p.respond_started(KEY)
    p.respond_finished(KEY)
    rid = add_walkthrough(store, KEY, ["w1", "w2"])
    event = {"type": "walkthrough_ready", "session_key": KEY, "reply_id": rid}
    assert p.handle_event(event, KEY) == play("w1")
    assert store.session(KEY).awaiting_response is False


def test_reset_clears_awaiting_for_current_and_focused(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.respond_started(KEY)
    for key in (KEY, OTHER):
        state = store.session(key)
        state.awaiting_response = True
        store.save_session(state)
    assert p.handle_event({"type": "listening_off", "session_key": ""}, OTHER) == [StopSpeech()]
    assert store.session(KEY).awaiting_response is False
    assert store.session(OTHER).awaiting_response is False
    rid = add_unheard(store, KEY, ["later"])
    assert p.handle_event(ready(KEY, rid), KEY) == [Chime("done", False)]


def test_stop_mid_section_replays_it(store):
    add_walkthrough(store, KEY, ["w1", "w2", "w3"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    p.continue_()  # w2 starts: walkthrough_pos 2
    assert p.stop() == [StopSpeech(), Listen()]
    assert store.session(KEY).walkthrough_pos == 1
    assert p.go_ahead(KEY) == play("w2")
    p.stop()
    assert Player(store).go_ahead(KEY) == play("w2")  # from the store, too


def test_stop_while_responding_does_nothing(store):
    p = Player(store)
    p.respond_started(KEY)
    assert p.stop() == []
    assert p.phase == "responding"


# --- spoken controls vs. the tab in front --------------------------------------


def waiting_on_section_two(store):
    """Section 1 of KEY's reply played; now paused between sections."""
    add_unheard(store, KEY, ["one", "two", "three"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    return p


def test_continue_with_no_focus_keeps_current_session(store):
    p = waiting_on_section_two(store)  # then he switched to Slack
    assert p.continue_(None) == play("two")


def test_continue_in_same_tab_plays_next(store):
    p = waiting_on_section_two(store)
    assert p.continue_(KEY) == play("two")


def test_continue_in_other_claude_tab_plays_that_tab(store):
    p = waiting_on_section_two(store)
    add_unheard(store, OTHER, ["other one"])
    assert p.continue_(OTHER) == play("other one That's everything.")
    assert p.key == OTHER


def test_continue_with_no_focus_resumes_paused_session(store):
    p = waiting_on_section_two(store)
    p.stop()
    assert p.continue_(None) == play("two")


def test_continue_with_no_session_goes_ahead_in_focused_tab(store):
    add_unheard(store, KEY, ["fresh"])
    assert Player(store).continue_(KEY) == play("fresh That's everything.")


def test_continue_with_no_session_and_no_focus_does_nothing(store):
    assert Player(store).continue_(None) == []


def test_repeat_with_no_focus_repeats_current(store):
    p = waiting_on_section_two(store)
    assert p.repeat(None) == play("one")


def test_repeat_in_other_claude_tab_does_nothing(store):
    p = waiting_on_section_two(store)
    assert p.repeat(OTHER) == []
    assert p.back(OTHER) == []
    assert p.skip(OTHER) == []
    assert p.phase == "waiting"


def test_back_and_skip_with_no_focus_act_on_current(store):
    p = waiting_on_section_two(store)
    p.continue_(None)
    p.section_finished()
    assert p.back(None) == play("one")
    p.section_finished()
    assert p.skip(None) == [StopSpeech(), Deafen(), Speak("two")]


def test_knob_while_speaking_acts_whichever_tab_is_in_front(store):
    p = waiting_on_section_two(store)
    p.continue_(KEY)  # section 2 speaking
    assert p.skip(OTHER) == [StopSpeech(), Deafen(), Speak("three That's everything.")]


# --- next_text (what to render ahead) ----------------------------------------


def spoken(effects):
    [text] = [e.text for e in effects if isinstance(e, Speak)]
    return text


def test_next_text_mid_reply(store):
    add_unheard(store, KEY, ["one", "two", "three"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.next_text() == "two"
    assert p.next_text() == "two"  # pure: asking twice changes nothing
    assert (p.phase, p.index, p.last_played) == ("speaking", 1, 0)
    p.section_finished()
    assert p.continue_() == play("two")


def test_next_text_last_section_is_none(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()
    p.continue_()
    assert p.next_text() is None
    assert p.section_finished() == [Listen()]
    assert p.next_text() is None  # idle


def test_next_text_includes_back_to_walkthrough_prefix(store):
    add_walkthrough(store, KEY, ["w1", "w2", "w3"], pos=1)
    add_unheard(store, KEY, ["answer"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.next_text() == "Back to the walkthrough. w2"
    assert store.session(KEY).walkthrough_pos == 1  # pure
    assert spoken(p.section_finished()) == "Back to the walkthrough. w2"


def test_next_text_includes_thats_everything_suffix(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.next_text() == "two That's everything."
    p.section_finished()
    assert spoken(p.continue_()) == "two That's everything."


def test_next_text_resuming_last_walkthrough_section(store):
    add_walkthrough(store, KEY, ["w1", "w2"], pos=1)
    add_unheard(store, KEY, ["answer"])
    p = Player(store)
    p.go_ahead(KEY)
    assert p.next_text() == "Back to the walkthrough. w2 That's everything."
    assert spoken(p.section_finished()) == "Back to the walkthrough. w2 That's everything."


def test_next_text_awaited_answer(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    state = store.session(KEY)
    state.awaiting_response = True
    store.save_session(state)
    add_unheard(store, KEY, ["the answer"])
    assert p.next_text() == "the answer That's everything."
    assert store.session(KEY).awaiting_response is True  # pure
    assert spoken(p.section_finished()) == "the answer That's everything."


def test_next_text_none_while_notice(store):
    add_unheard(store, KEY, ["one", "two"])
    p = Player(store)
    p.go_ahead(KEY)
    p.section_finished()  # waiting on section two
    assert p.next_text() is None  # not speaking
    event = {"type": "needs_you", "session_key": KEY, "line": "Claude has a question for you."}
    p.handle_event(event, KEY)
    assert p.phase == "speaking"
    assert p.next_text() is None
