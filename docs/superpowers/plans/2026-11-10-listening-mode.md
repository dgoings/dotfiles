# Listening Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While listening mode is on, Claude Code replies in Ghostty/Rex get a spoken, sectioned version Dylan can play, pause and answer by voice or Ulanzi knob. On request, documents can be walked through the same way.

**Architecture:** Claude Code hooks (Stop, Notification, UserPromptSubmit) call a stdlib-only Python CLI (`.listening/listen.py`). It writes reply bundles and events to a state folder, and a detached worker has Claude Haiku rewrite replies into spoken sections. Talon polls that folder. A pure-Python player state machine (`listening/core/player.py`) decides what to do, and thin Talon glue (`listening/listening.py`) carries it out: macOS `say`, `afplay` chimes, the microphone switched to "None" while speaking, and a `user.listening` mode with a small command set. The Ulanzi controls go through one dispatcher, so listening mode can take them over only when there's something to hear.

**Tech Stack:** Talon (Python 3.14, `talon` API), Homebrew `python3` 3.15 stdlib for hooks/CLI, pytest in `dylan/.venv`, macOS `say`/`afplay`/`osascript`, Rex CLI, Claude Code CLI 2.1.322.

**Spec:** `docs/2026-11-10-listening-mode-design.md` (read it first; this plan argues from it).

## Global Constraints

- All code in the `dylan` repo (`~/.talon/user/dylan`). Don't edit `community/` or `rango-talon/`.
- Talon loads every `.py` under `~/.talon/user` **except dot-folders** (verified). Talon-loaded code goes in `listening/`. Hook/CLI scripts, tests and the venv go in `.listening/`, `.tests/` and `.venv/`.
- `listening/core/` must be stdlib-only, with no `talon` import and no side effects at import time. Talon loads it, the CLI imports it, pytest tests it. Use relative imports inside `core`.
- State folder: `~/.local/state/talon-listening/`, overridable with the env var `LISTENING_STATE_DIR` (tests always set it).
- Hooks must exit fast, and must do nothing and write nothing when listening mode is off. Any error inside a hook is swallowed with exit 0. A broken listening mode must never break a Claude session.
- Nested Haiku call: `claude --settings '{"disableAllHooks": true}' -p --model haiku --tools "" --no-session-persistence --max-turns 1 --output-format json <prompt>`, run with env `LISTENING_NESTED=1`. Every hook exits immediately when `LISTENING_NESTED` is set. Don't use `--bare`: it needs `ANTHROPIC_API_KEY`, and Dylan uses subscription login.
- Session keys: `"tty:/dev/ttysNNN"` (Ghostty) or `"rex:<REX_BLOCK value>"` (Rex).
- Bundle IDs: Ghostty `com.mitchellh.ghostty`, Rex `com.superlogical.rex`. Rex CLI: `/Applications/Rex Beta.app/Contents/Helpers/Rex Server.rex/Contents/MacOS/rex` (not on PATH).
- Ulanzi hyper keys (ctrl+alt+shift+cmd + V/T/B/J/L/K) and the 80ms `RELEASE_DELAY` in `ulanzi/ulanzi.py` are kept as they are.
- Voice preference order: `Zoe (Premium)`, `Ava (Premium)`, `Evan (Premium)`, then `Samantha`. Overridable with Talon setting `user.listening_voice`. Rate: `user.listening_rate`, default 190 words/min.
- Chimes: `done` = `/System/Library/Sounds/Glass.aiff`, `needs_you` = `/System/Library/Sounds/Submarine.aiff`. Focused session plays at volume 1.0, background at 0.25 (`afplay -v`).
- Exact spoken copy: no new content → "Nothing new here." End of everything → "That's everything." Resuming a walkthrough after an answer → "Back to the walkthrough." Can't tell the session → "I can't tell which Claude session is in front." Needs-you lines: permission → "Claude needs you to approve something." Question → "Claude has a question for you." Plan → "Claude has a plan for you to review."
- Settings edits to `~/.claude/settings.json` are additive (existing SessionStart hooks for herdr and Rex stay), back up first, and need Dylan's go-ahead at execution time.
- Commit after each task. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The Haiku call fails, times out (>90s) or returns non-JSON:** the reply still gets spoken sections from the plain-text fallback, and the chime still plays. Test in Task 5.
2. **Focus detection fails** (osascript denied, Rex CLI missing or slow, title doesn't match): treated as "not focused". Soft chime, no autoplay, and "go ahead" says the can't-tell line instead of playing the wrong session. Tests in Tasks 6 and 7.
3. **Talon reloads or restarts while the mic is switched to "None"** (saving a file mid-playback): on load, the glue restores the saved microphone, so Talon is never left deaf. Test in Task 2 (store marker) and the manual check in Task 8.
4. **"listening off" (or the Talon key) mid-speech or mid-dictation:** speech stops, the mic is restored, command mode returns, and no later events autoplay. Tests in Task 7, manual check in Task 8.
5. **A reply arrives while another section is speaking:** nothing interrupts; it chimes, and it plays only on "go ahead" (or automatically after the current one finishes, if it's the awaited answer). Test in Task 7.

---

### Task 1: Probe what hooks actually see

Three facts the docs don't confirm, which later tasks depend on: do hooks inherit `REX_BLOCK` and does the process tree have the terminal's tty; does `REX_BLOCK` look the same as Rex's `focused_block_id`; and which `notification_type` fires for a permission prompt, an AskUserQuestion menu, and plan approval (ExitPlanMode).

**Files:**
- Create (temporary, deleted at the end of the task): `.listening/probe_hook.sh`
- Modify (temporary): `~/.claude/settings.json`
- Modify: `docs/2026-11-10-listening-mode-design.md` (append a "Findings" section)

- [ ] **Step 1:** Write `probe_hook.sh`. It appends one line per call to `~/.local/state/talon-listening/probe.log`: the hook event name, stdin JSON, `REX_BLOCK`, `REX_SESSION`, `ps -o tty= -p $$`, and the `tty` of each parent PID up to PID 1.
- [ ] **Step 2:** Back up `~/.claude/settings.json` to `settings.json.bak-listening-probe`. With Dylan's OK, add the probe for `Stop`, `Notification` (no matcher) and `UserPromptSubmit`.
- [ ] **Step 3:** Ask Dylan to start a fresh `claude` session in **Ghostty** and one in **Rex**, and in each to: get one normal reply, trigger a permission prompt (e.g. ask it to run `touch /tmp/x` in default permission mode), answer an AskUserQuestion (ask it to "ask me a multiple choice question"), and get a plan approval (`/plan`, then ask for a trivial plan).
- [ ] **Step 4:** Read `probe.log`. Record in the design doc's new "Findings" section:
  - whether `REX_BLOCK` is present;
  - the first ancestor with a real tty, and whether it equals Ghostty's `focused terminal` tty;
  - for the Rex session, whether `REX_BLOCK` equals the `focused_block_id` from `rex session inspect "$REX_SESSION" --json`;
  - the `notification_type` (or absence of one) for each of the three blocked cases.
- [ ] **Step 5:** Restore `settings.json` from the backup, then delete `probe_hook.sh` and `probe.log`. Verify `diff ~/.claude/settings.json ~/.claude/settings.json.bak-listening-probe` prints nothing.
- [ ] **Step 6:** Commit the Findings: `docs: record hook probe findings for listening mode`.

If a blocked case fires no Notification at all, note it. Task 4 covers only the cases that do, and the setup notes in Task 9 say which ones don't.

### Task 2: Scaffolding and the state store

**Files:**
- Create: `.gitignore` additions (`.venv/`, `.pytest_cache/`), `.tests/conftest.py`, `.tests/test_store.py`
- Create: `listening/core/__init__.py` (empty), `listening/core/paths.py`, `listening/core/store.py`

**Interfaces:**
- Produces (`core/paths.py`): `state_dir() -> Path` (env `LISTENING_STATE_DIR` or the default; creates it).
- Produces (`core/store.py`):
  - `@dataclass Section(title: str, text: str)`
  - `@dataclass Reply(id: str, session_key: str, kind: str, title: str | None, sections: list[Section])`. `kind` is `"reply"` or `"walkthrough"`.
  - `@dataclass SessionState(key: str, unheard: str | None = None, walkthrough: str | None = None, walkthrough_pos: int = 0, blocked: bool = False, awaiting_response: bool = False, suppress_next_stop: bool = False, listening_context: str | None = None)`
  - `class Store(root: Path)` with:
    - `is_on() -> bool` and `set_on(on: bool) -> None`;
    - `create_reply(session_key: str, kind: str, written: str, title: str | None = None) -> str` (id sortable by time) and `save_sections(reply_id: str, sections: list[Section]) -> None`;
    - `load_reply(reply_id: str) -> Reply | None` (None when the folder is missing or has no sections yet);
    - `session(key: str) -> SessionState` and `save_session(state: SessionState) -> None`;
    - `push_event(type: str, session_key: str, **data) -> None` and `pop_events() -> list[dict]` (oldest first, removes what it returns; each dict has `type`, `session_key` and data);
    - `set_saved_mic(name: str | None) -> None` and `saved_mic() -> str | None`;
    - `prune(keep: int = 50) -> None` (oldest reply folders removed).
- Layout: `on` (flag file), `replies/<id>/{written.md, spoken.json, meta.json}`, `sessions/<sanitized key>.json`, `events/<time>-<n>.json`, `saved_mic`. Writes are atomic (write a temp file, then `os.replace`).

- [ ] **Step 1:** Create the venv and install pytest: `python3 -m venv .venv && .venv/bin/pip install pytest`. Add `.venv/` and `.pytest_cache/` to `.gitignore`.
- [ ] **Step 2:** `.tests/conftest.py` puts `listening/` on `sys.path` (so `import core.store` works). It also provides a `store` fixture: `Store(tmp_path)`, with `LISTENING_STATE_DIR` set to `tmp_path` via `monkeypatch`.
- [ ] **Step 3: Write failing tests** in `.tests/test_store.py`:
  - `test_flag_defaults_off_and_toggles`: `is_on()` is False; after `set_on(True)` it's True.
  - `test_reply_round_trip`: `create_reply("tty:/dev/ttys003", "reply", "hi")`, then `save_sections(id, [Section("A", "one")])`, then `load_reply(id)` equals `Reply(id, "tty:/dev/ttys003", "reply", None, [Section("A", "one")])`.
  - `test_load_reply_without_sections_is_none`.
  - `test_session_defaults_and_persist`: `session("rex:block:1").unheard is None`; after saving it with `unheard="x"`, a new `Store` on the same root reads `"x"`.
  - `test_events_fifo_and_consumed`: push `a` then `b`; `pop_events()` returns types `["a", "b"]`, and a second pop returns `[]`.
  - `test_prune_keeps_newest`: create 3 replies, `prune(keep=2)`; the oldest id loads as None.
  - `test_saved_mic_round_trip`: `set_saved_mic("AU05")`, then `saved_mic() == "AU05"`; `set_saved_mic(None)`, then `saved_mic() is None`.
- [ ] **Step 4:** Run `.venv/bin/pytest .tests/test_store.py -q`. Expected: FAIL (module missing).
- [ ] **Step 5:** Implement `paths.py` and `store.py`.
- [ ] **Step 6:** Run `.venv/bin/pytest .tests -q`. Expected: all pass. Check `~/.talon/talon.log` shows `[+] user/dylan/listening/core/store.py` with no error after it.
- [ ] **Step 7:** Commit: `feat(listening): state store`.

### Task 3: Session key, spoken parsing and the style guide

**Files:**
- Create: `listening/core/session.py`, `listening/core/spoken.py`, `listening/style_guide.md`
- Test: `.tests/test_session.py`, `.tests/test_spoken.py`

**Interfaces:**
- Produces (`core/session.py`): `own_session_key(env: Mapping[str, str], tty_of: Callable[[int], str], parent_of: Callable[[int], int], pid: int) -> str | None`. If `REX_BLOCK` is in env, returns `"rex:" + value`. Otherwise it walks from `pid` up through parents to PID 1, and the **topmost** (last seen) `tty_of(p)` that isn't `"??"` or empty gives `"tty:/dev/" + tty` (Task 1 finding: sessions under Claude's background helper have an inner pty below the tab's real tty). Returns None if no tty is found. Stop if a parent lookup fails or loops. Also `default_tty_of(pid)` and `default_parent_of(pid)`, both using `ps -o tty=` and `ps -o ppid=`.
- Produces (`core/spoken.py`):
  - `class SpokenFormatError(ValueError)`;
  - `parse_sections(raw: str) -> list[Section]`. It accepts `{"sections": [{"title", "text"}...]}`, optionally inside ```` ```json ```` fences or with prose around the JSON object. It raises `SpokenFormatError` when there's no valid object, the list is empty, or a text is empty.
  - `fallback_sections(written: str) -> list[Section]`. Splits on markdown headings, otherwise on blank-line paragraphs, and merges pieces under ~60 words with the next one. It strips markdown syntax (`#`, `*`, `` ` ``, `|`, link URLs), and replaces each fenced code block with "There's a code block here; it's on screen." Title is the heading text or `""`.
- Produces: `listening/style_guide.md`, the rules from spec piece 6 written as instructions to a model. It covers review mode for walkthroughs (all substance) and update mode for replies (outcome first). It also pins the exact output format above and the 20–45 second section target (~60–120 words).

- [ ] **Step 1: Write failing tests:**
  - `test_rex_env_wins`: env `{"REX_BLOCK": "block:9"}` gives `"rex:block:9"`.
  - `test_walks_to_first_real_tty`: ttys `{50: "??", 40: "??", 30: "ttys003"}`, parents `50→40→30→1`, pid 50 gives `"tty:/dev/ttys003"`.
  - `test_topmost_tty_wins`: ttys `{50: "??", 40: "ttys004", 30: "??", 20: "ttys002", 10: "??"}`, parents `50→40→30→20→10→1`, pid 50 gives `"tty:/dev/ttys002"`.
  - `test_no_tty_returns_none`.
  - `test_parse_plain_json`, `test_parse_fenced_json_with_prose`: both give `[Section("Browser", "I fixed it.")]`.
  - `test_parse_rejects_empty_list` and `test_parse_rejects_garbage`: both raise `SpokenFormatError`.
  - `test_fallback_splits_on_headings`: `"## One\nAlpha text.\n## Two\nBeta text."` gives titles `["One", "Two"]`. (Pad each body past 60 words in the test so they don't merge.)
  - `test_fallback_strips_markdown_and_code`: the output text contains no `` ` `` `|` `*` `#`, and contains "it's on screen".
- [ ] **Step 2:** Run `.venv/bin/pytest .tests/test_session.py .tests/test_spoken.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `session.py` and `spoken.py`, and write `style_guide.md`.
- [ ] **Step 4:** Run all tests. Expected: pass.
- [ ] **Step 5:** Commit: `feat(listening): session keys, spoken parsing, style guide`.

### Task 4: CLI basics (on/off, walkthrough, prompt hook, notification hook)

**Files:**
- Create: `.listening/listen.py` (`argparse`; adds `../listening` to `sys.path`; imports `core.*`)
- Test: `.tests/test_listen_cli.py` (runs the script with `subprocess` using `.venv/bin/python`, with `LISTENING_STATE_DIR=tmp_path` and stdin JSON)

**Interfaces:**
- Consumes: `Store`, `own_session_key`, `parse_sections` (Tasks 2–3).
- Produces (subcommands; all exit 0 on any internal error, and all exit immediately when `LISTENING_NESTED` is set):
  - `listen.py on` / `listen.py off`: set the flag, and push event `listening_on` / `listening_off` (session key `""`).
  - `listen.py walkthrough --title TEXT`, with sections JSON on stdin: sets the flag on and creates a reply with kind `walkthrough`. The session's `walkthrough` is set to the new id, `walkthrough_pos` to 0, and `suppress_next_stop` to True. Pushes `listening_on` if the flag was off, then `walkthrough_ready`. Prints `Walkthrough queued (N sections).` On invalid JSON it exits 2 with the parse error on stderr. This is the one non-zero exit, so the skill can fix its JSON.
  - `listen.py hook-prompt` (UserPromptSubmit): when on, and the prompt doesn't start with `<task-notification>` (a background agent's result, not Dylan; such prompts do nothing), it clears `blocked`. If `listening_context` is set, it prints `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": <context>}}` and clears the context.
  - `listen.py hook-notify` (Notification): when on, it picks a needs-you line with `blocked_line(payload: dict, last_tool: str | None) -> str | None` (pure, in `listen.py`), using the Global Constraints copy. Task 1 found all three cases arrive as `notification_type == "permission_prompt"`: a `message` containing `"approval for the plan"` → the plan line; otherwise `last_tool == "AskUserQuestion"` → the question line; otherwise → the permission line. Any other type (e.g. `idle_prompt`) → None. `last_tool` comes from `last_tool_use_name(transcript_path) -> str | None`, which reads only the last 256 KB of the JSONL transcript and returns the `name` of the last `tool_use` block in an `assistant` entry's `message.content`, or None on any error. On a match it sets `blocked=True` and pushes `needs_you` with `line=...`.
- The session key for every hook comes from `own_session_key(os.environ, default_tty_of, default_parent_of, os.getpid())`. With no key, the hook does nothing.

- [ ] **Step 1: Write failing tests:**
  - `test_hooks_noop_when_off`: with the flag off, `hook-notify` with a permission payload leaves `events/` empty and creates no `sessions/` folder.
  - `test_nested_env_noops`: with the flag on and `LISTENING_NESTED=1`, `hook-notify` pushes nothing.
  - `test_walkthrough_turns_on_and_queues`: flag off; stdin `{"sections":[{"title":"Intro","text":"Hi."}]}`, `--title "Design doc"`. Afterwards `is_on()`, events are `["listening_on", "walkthrough_ready"]`, and the session has `walkthrough` set and `suppress_next_stop` True. (Set `REX_BLOCK=block:t` in the test env for a stable key.)
  - `test_walkthrough_bad_json_exits_2`.
  - `test_prompt_hook_injects_context_once`: the session has `listening_context="Dylan was listening to section 2"`. The first run prints JSON whose `additionalContext` contains it; the second run prints nothing.
  - `test_notify_permission_sets_blocked`: `{"notification_type": "permission_prompt", "message": "Claude needs your permission"}`; the event has `line == "Claude needs you to approve something."`.
  - `test_notify_plan_and_question_lines`: the plan message `"Claude Code needs your approval for the plan"` gives `"Claude has a plan for you to review."`; a permission payload whose `transcript_path` is a tmp JSONL ending in an assistant `tool_use` named `AskUserQuestion` gives `"Claude has a question for you."`.
  - `test_notify_idle_ignored`: `notification_type: "idle_prompt"` pushes nothing.
  - `test_prompt_hook_ignores_task_notifications`: `blocked=True` and `listening_context` set; a prompt starting with `<task-notification>` leaves both unchanged and prints nothing.
- [ ] **Step 2:** Run `.venv/bin/pytest .tests/test_listen_cli.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement those subcommands in `listen.py`.
- [ ] **Step 4:** Run all tests. Expected: pass.
- [ ] **Step 5:** Commit: `feat(listening): CLI on/off, walkthrough, prompt and notification hooks`.

### Task 5: Stop hook and the Haiku rewrite worker

**Files:**
- Modify: `.listening/listen.py`
- Test: `.tests/test_listen_cli.py` (a fake `claude` script on PATH, chosen with `LISTENING_CLAUDE_BIN`)

**Interfaces:**
- Produces:
  - `listen.py hook-stop`, with Stop JSON on stdin. It returns immediately if off, nested, or `stop_hook_active` is true. Otherwise it clears `blocked`. If `suppress_next_stop` is set, it clears that and stops there. Otherwise it creates a `reply` from `last_assistant_message` (an empty or missing message means do nothing). Then it starts `listen.py rewrite <id>` fully detached (`subprocess.Popen(..., start_new_session=True, stdin/stdout/stderr=DEVNULL)`) and exits.
  - `listen.py rewrite REPLY_ID`. It runs the nested Haiku command from Global Constraints. The prompt is `style_guide.md`, then a line saying this is update mode, then the written reply. It uses `LISTENING_CLAUDE_BIN` or `claude`, with timeout 90s. It reads `.result` from the JSON output, then `parse_sections`. On any failure it uses `fallback_sections(written)`. Then `save_sections`, set the session's `unheard` to the id, push `reply_ready` with `reply_id`, and `prune()`.

- [ ] **Step 1: Write failing tests** (the fake `claude` prints `{"result": "<sections json>"}`; a variant exits 1; another sleeps past a test timeout, made shorter with env `LISTENING_REWRITE_TIMEOUT=1`):
  - `test_stop_hook_returns_fast`: when on, `hook-stop` finishes in under 1s, even with a fake `claude` that sleeps 5s.
  - `test_rewrite_saves_sections_and_event`: run `rewrite` directly (not detached). The reply loads with the fake's sections; the session's `unheard == id`; the events are `["reply_ready"]`.
  - `test_rewrite_falls_back_on_failure` and `test_rewrite_falls_back_on_timeout`: sections equal `fallback_sections(written)`, and `reply_ready` is still pushed.
  - `test_rewrite_passes_no_hooks_and_nested_env`: the fake records its argv and env. It sees `--settings` `{"disableAllHooks": true}`, `--model haiku`, and `LISTENING_NESTED=1`.
  - `test_stop_suppressed_after_walkthrough`: with `suppress_next_stop` True, `hook-stop` creates no reply and clears the flag.
  - `test_stop_hook_active_noops`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `hook-stop` and `rewrite`.
- [ ] **Step 4:** Run all tests. Expected: pass.
- [ ] **Step 5:** Commit: `feat(listening): stop hook and Haiku rewrite worker`.

### Task 6: Focused session detection

**Files:**
- Create: `listening/core/focus.py`
- Test: `.tests/test_focus.py`

**Interfaces:**
- Produces: `focused_session_key(front_bundle: str, window_title: str, run: Callable[[list[str]], str]) -> str | None`. `run` returns stdout, or raises on failure or timeout. Any exception leads to a None result.
  - Ghostty: `run(["osascript", "-e", 'tell application "Ghostty" to get tty of focused terminal of selected tab of front window'])`, then `"tty:" + stripped output`.
  - Rex: first `rex client ls --json`, taking the `session_ids` of clients whose `info.kind == "app"`. If there's more than one, pick the session whose label (from `rex session inspect S --json` `.label`) satisfies `window_title.endswith(" - " + label)`. Then take `focused_block_id` from the window whose `window_id == active_window_id` and return `"rex:" + id`. Adjust the prefix to the Task 1 findings so it equals the hook's key.
  - Other bundles: None.
- Produces: `default_run(args) -> str`, a subprocess call with a 2s timeout and `check=True`.

- [ ] **Step 1: Write failing tests** with a fake `run` keyed by argv:
  - `test_ghostty_tty`: osascript returns `"/dev/ttys003\n"`, giving `"tty:/dev/ttys003"`.
  - `test_rex_single_session`: canned `client ls` and `session inspect` JSON (shaped like the real output recorded in the spec) give `"rex:block:abc"`.
  - `test_rex_two_sessions_picks_title_match`.
  - `test_failure_returns_none`: `run` raises, giving None.
  - `test_unknown_app_none`.
- [ ] **Step 2:** Run `.venv/bin/pytest .tests/test_focus.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `focus.py`.
- [ ] **Step 4:** Run all tests. Expected: pass. Then, in a Talon REPL with this Ghostty tab focused, `focused_session_key("com.mitchellh.ghostty", "", default_run)` prints this session's tty.
- [ ] **Step 5:** Commit: `feat(listening): focused session detection for Ghostty and Rex`.

### Task 7: Player state machine

**Files:**
- Create: `listening/core/player.py`
- Test: `.tests/test_player.py`

**Interfaces:**
- Consumes: `Store`, `Reply`, `SessionState`.
- Produces effects, as dataclasses: `Speak(text: str)`, `StopSpeech()`, `Chime(kind: str, soft: bool)` (`kind` is `"done"` or `"needs_you"`), `Listen()` (mic back on, listening command set), `Deafen()`.
- Produces `class Player(store: Store)`:
  - state `phase` is `"idle"`, `"speaking"`, `"waiting"` or `"responding"`;
  - `key: str | None`, `reply_id: str | None`, `index: int` (next section to play), `last_played: int | None`.
  - Methods, each returning `list[Effect]`:
    - `go_ahead(focused_key: str | None)`, `continue_()`, `repeat()`, `back()`, `skip()`, `stop()`, `section_finished()`;
    - `respond_started()`, `respond_finished()`;
    - `handle_event(event: dict, focused_key: str | None)`, `reset()` (listening off: `[StopSpeech()]` and everything cleared).
  - `has_something(focused_key: str | None) -> bool`.
- Rules (from the spec, plus the calls made there):
  - **Playing a section** returns `[Deafen(), Speak(text)]`, where text is the section text plus `" That's everything."` if it's the last section of the last thing to play.
  - **`go_ahead`:**
    - with no focused key, `[Speak(can't-tell line)]`;
    - if paused on the same key, it resumes `index`;
    - otherwise the session's `unheard` (cleared once taken) wins over its `walkthrough` (resumed at `walkthrough_pos`);
    - otherwise `[Speak("Nothing new here.")]`.
  - **`section_finished`:**
    - if there are more sections, `phase = "waiting"` and `[Listen()]`;
    - if a reply finishes and the session has a walkthrough, it plays `"Back to the walkthrough. "` plus the next walkthrough section;
    - each walkthrough advance saves `walkthrough_pos`, and the end of a walkthrough clears it.
  - **`repeat`** replays `last_played`. **`back`** plays `last_played - 1` (at least 0). **`skip`** gives `[StopSpeech()]` and plays the next section.
  - **`stop`** gives `[StopSpeech(), Listen()]`, with `phase = "idle"`, keeping the position for `go_ahead`.
  - **`respond_started`** gives `[StopSpeech(), Deafen()]`, with `phase = "responding"`. It sets `awaiting_response = True` and `listening_context = "Dylan was listening to section {n} of {total}, titled '{title}', of {the reply|the walkthrough '{title}'}, when he responded."` on the current session.
  - **`respond_finished`** gives `[Listen()]` and `phase = "idle"`.
  - **`handle_event`:**
    - `reply_ready`: focused and `awaiting_response` and not speaking means clear awaiting, then `[Chime("done", False)]` and `go_ahead`. Focused otherwise means `[Chime("done", False)]`. Not focused means `[Chime("done", True)]`.
    - `needs_you`: `[Chime("needs_you", soft=not focused)]`, plus `[Deafen(), Speak(line)]` if focused and not speaking.
    - `walkthrough_ready`: focused means `go_ahead`; otherwise a soft done chime.
    - `listening_on`: `[Listen()]`. `listening_off`: `reset()`.
  - **`has_something`** is True when phase is speaking, waiting or responding, or the focused session has `unheard` or `walkthrough`, unless that session's `blocked` is True.

- [ ] **Step 1: Write failing tests** using a real `Store(tmp_path)` with replies built from `create_reply` and `save_sections`:
  - `test_go_ahead_plays_first_section_then_waits`: effects are `[Deafen(), Speak("one")]`; after `section_finished()`, `[Listen()]` and phase `"waiting"`.
  - `test_continue_repeat_back_skip` (one assertion per control on the expected `Speak` text).
  - `test_last_section_adds_thats_everything`.
  - `test_nothing_new` and `test_no_focus_says_cant_tell`.
  - `test_unheard_beats_walkthrough_then_walkthrough_resumes`: the reply's last section finishes, then `Speak("Back to the walkthrough. <next>")` plays at the saved `walkthrough_pos`.
  - `test_respond_sets_context_and_awaits` and `test_awaited_answer_autoplays`.
  - `test_reply_while_speaking_only_chimes` (Review Focus 5): while speaking, `reply_ready` for the focused key gives exactly `[Chime("done", False)]`.
  - `test_background_reply_soft_chime` and `test_needs_you_focused_speaks_line`.
  - `test_reset_stops_and_clears` (Review Focus 4): mid-speech `reset()` gives `[StopSpeech()]`, then phase `"idle"`, and a later `go_ahead` doesn't resume.
  - `test_blocked_session_has_nothing`.
- [ ] **Step 2:** Run `.venv/bin/pytest .tests/test_player.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `player.py`.
- [ ] **Step 4:** Run all tests. Expected: pass.
- [ ] **Step 5:** Commit: `feat(listening): playback state machine`.

### Task 8: Talon glue, commands and the Ulanzi dispatcher

**Files:**
- Create: `listening/listening.py`, `listening/listening.talon`, `listening/listening_on.talon`
- Modify: `ulanzi/ulanzi.py` (add `ulanzi_control`), `ulanzi/ulanzi.talon` (the six hotkeys call `user.ulanzi_control("<name>")`)

**Interfaces:**
- Consumes: `Store`, `Player`, `focused_session_key`/`default_run`, effects (Tasks 2–7).
- Produces (Talon module `listening.py`):
  - `mod.mode("listening")`, giving `user.listening`;
  - settings `user.listening_voice: str = ""` and `user.listening_rate: int = 190`;
  - actions: `listening_on()`, `listening_off()`, `listening_go_ahead()`, `listening_continue()`, `listening_repeat()`, `listening_back()`, `listening_skip()`, `listening_stop()`, `listening_respond()`, and `listening_intercept(control: str) -> bool`.
- Produces (`ulanzi.py`): `ulanzi_control(name: str)`, where `name` is one of `voice`, `talon`, `back`, `knob_left`, `knob_right` or `knob_press`. It returns early if `actions.user.listening_intercept(name)` is True, and otherwise calls today's action for that control.
- Effect execution:
  - **`Deafen`:** if the mic isn't already "None", save `actions.sound.active_microphone()` with `store.set_saved_mic`, then `actions.sound.set_microphone("None")`.
  - **`Listen`:** restore the saved mic and clear it, then disable `command`, `dictation` and `sleep`, and enable `user.listening`.
  - **`Speak`:** stop any current speech, then `subprocess.Popen(["say", "-v", voice, "-r", str(rate), text])`, keeping the process. The voice is the setting, or the first installed voice from the Global Constraints list (checked once with `say -v '?'`).
  - **`StopSpeech`:** terminate the process.
  - **`Chime`:** `afplay -v 1.0|0.25 <sound>`.
- `cron.interval("300ms", tick)` runs at all times. Listening mode can be turned on from Claude's side by a walkthrough request, so the tick has to catch that.
  - **While off:** it only looks for a `listening_on` event. On finding one, it turns listening on in Talon and handles the rest of that batch. Other events are dropped, since hooks don't write any while off.
  - **While on:** if the `say` process exited and the phase is speaking, it calls `section_finished()`. Then it handles `store.pop_events()` with the current focused key (`ui.active_app().bundle` and `ui.active_window().title`), including an external `listening_off`.
- At module load, if `store.saved_mic()` is set, restore it and clear it (Review Focus 3).
- **`listening_off`:** `player.reset()` effects, mic restored, `user.listening` disabled, `actions.user.talon_mode()`, `store.set_on(False)`.
- **`listening_intercept`** returns False when listening is off. When on:
  - `talon`: `listening_off()`, True.
  - `voice`, in a Claude terminal (Ghostty/Rex): the first press calls `listening_respond()`; the press that ends dictation presses `space` after the release delay and calls `respond_finished`. Both return True. In other apps it returns False, so Superwhisper behaves as before.
  - `knob_press`, `back`, `knob_left`, `knob_right`: only if `player.has_something(focused)`. They map to `go_ahead`/`continue`, `stop`, `repeat`/`back` (if phase is waiting, `repeat`; if speaking, `back`) and `skip` respectively, returning True. Otherwise False.
- **`listening_respond`:** `respond_started()` effects, then press `space` (Claude's `/voice tap`).
- `listening.talon` (`mode: user.listening`), every command anchored `^...$`: `go ahead`, `continue`, `repeat`, `respond`, `stop`, `tab next` → `app.tab_next()`, `tab last` → `app.tab_previous()`, `listening off`.
- `listening_on.talon` (no mode header, so command mode): `listening on: user.listening_on()`.

- [ ] **Step 1:** Implement the files above. Check `~/.talon/talon.log` shows all of them loaded, with no traceback.
- [ ] **Step 2:** In a Talon REPL, confirm `user.listening` exists in `registry.modes` (or that `actions.mode.enable("user.listening")` works) and that the Ulanzi hotkeys resolve to `user.ulanzi_control`.
- [ ] **Step 3: Manual checks with Dylan** (no Claude needed). Create a two-section reply for this Ghostty tab with `listen.py walkthrough` and check:
  - it chimes and starts speaking;
  - the mic shows "None" while speaking;
  - after section 1, "continue" works and the knob press works;
  - key 3 stops mid-sentence;
  - the Talon key leaves listening mode and restores the mic and command mode.
- [ ] **Step 4: Review Focus 3, manually.** Mid-speech, re-save `listening.py` (forcing a reload). Afterwards, `actions.sound.active_microphone()` is `AU05` again.
- [ ] **Step 5:** Check the Ulanzi behavior with listening off is unchanged: knob in Ghostty and Helium, voice key in Ghostty and Claude Desktop.
- [ ] **Step 6:** Commit: `feat(listening): Talon playback, commands, and Ulanzi remote`.

### Task 9: Skill, hook install and setup notes

**Files:**
- Create: `.listening/skill/listen/SKILL.md`, `.listening/install.py`, `listening/README.md`
- Test: `.tests/test_install.py`

**Interfaces:**
- Produces `install.py [--settings PATH] [--skills-dir PATH] [--uninstall]`, with defaults `~/.claude/settings.json` and `~/.claude/skills`. It:
  - backs up the settings file to `settings.json.bak-listening-<timestamp>`;
  - adds hooks idempotently, identified by the command containing `/.listening/listen.py`: `Stop` (async, `<python> <repo>/.listening/listen.py hook-stop`), `Notification` (async; matcher = the `|`-joined types from `NEEDS_YOU`), and `UserPromptSubmit` (sync, timeout 5). `<python>` is the absolute path of the interpreter running `install.py`.
  - symlinks `<skills-dir>/listen` to `.listening/skill/listen`.
  - `--uninstall` removes only those hooks and the link.
- `SKILL.md`:
  - frontmatter `name: listen`, plus a `description` that triggers on "walk me through", "talk me through", "read me" and "listen to" for a document or content.
  - Body: read `~/.talon/user/dylan/listening/style_guide.md`; write sections in review mode (all the substance) to a temp JSON file; run `<python> ~/.talon/user/dylan/.listening/listen.py walkthrough --title "<title>" < file`; on exit 2, fix the JSON and retry; reply in one short line ("Starting the walkthrough of <title>.").

- [ ] **Step 1: Write failing tests** against tmp files:
  - `test_install_adds_hooks_keeps_existing`: a settings file with the herdr SessionStart hook keeps it, and gains exactly one Stop, one Notification and one UserPromptSubmit entry.
  - `test_install_idempotent`: running twice gives the same file.
  - `test_install_backs_up`.
  - `test_uninstall_removes_only_ours`.
  - `test_skill_symlink_created`.
- [ ] **Step 2:** Run `.venv/bin/pytest .tests/test_install.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement `install.py`, then write `SKILL.md` and `README.md`. The README covers:
  - how to turn listening mode on and off;
  - the commands and Ulanzi table;
  - downloading a Premium voice;
  - which blocked cases do or don't chime (from Task 1);
  - `install.py --uninstall`.
- [ ] **Step 4:** Run all tests. Expected: pass.
- [ ] **Step 5:** With Dylan's go-ahead, run `/opt/homebrew/bin/python3 .listening/install.py`. Check that `python3 -m json.tool ~/.claude/settings.json` parses and that `ls -l ~/.claude/skills/listen` points into the repo.
- [ ] **Step 6:** Commit: `feat(listening): walkthrough skill, hook installer, setup notes`.

### Task 10: End-to-end check with Dylan

No new files unless something fails. Fix failures in the task that owns the code, with a test first.

- [ ] **Step 1: Crossword run, Ghostty.**
  - Say "listening on" and ask Claude a question.
  - After it finishes: a clear chime within ~15s. "go ahead" reads section 1 and the mic is "None"; "continue" reads the next one; the last section ends with "That's everything."
- [ ] **Step 2: Background tab.** Start a task in a second Ghostty tab and switch away. It gives a soft chime. Switch back with "tab next", and "go ahead" plays it.
- [ ] **Step 3: Respond.** Mid-reply, press the voice key, speak, then press it again (it sends). Claude's answer chimes and plays on its own. Claude's answer should show it knew which section you were on.
- [ ] **Step 4: Walkthrough.** With listening off, ask "walk me through docs/2026-11-10-listening-mode-design.md". Listening turns on and it starts playing. Respond mid-walkthrough: the answer plays, then "Back to the walkthrough." and the next section.
- [ ] **Step 5: Needs you.** Trigger a permission prompt. It gives a needs-you chime and the spoken line. The knob moves through the prompt's options as usual, and the knob press approves.
- [ ] **Step 6: Rex.** Repeat Step 1 in Rex.
- [ ] **Step 7: Off means off.** Say "listening off". A normal Claude reply gives no chime and nothing is written to `events/`. The Ulanzi behaves as before.
- [ ] **Step 8:** Commit any fixes. Update the spec's Status line to `implemented`.
