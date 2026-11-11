# Listening Mode: hearing Claude's replies instead of reading them

Date: 2026-11-10
Status: implemented (2026-11-11)

## Why

Dylan drives his Mac by voice (Talon, plus a Ulanzi AU05 keypad with a mic,
3 keys and a knob) and talks to Claude Code by voice. The loop breaks on the
way back: Claude's answer is a wall of text that needs eyes on the screen.

The motivating moment: Dylan hands Claude a task, then does a crossword while
it works. He wants to hear when the result is ready, say "go ahead", and have
it talked through one topic at a time, pausing after each so he can continue,
hear it again, or respond, all without looking at or touching the computer.

He also wants to digest longer things the same way, for example a design doc
that's waiting for his review, without reading it.

## Goals

- **Listening mode**, switched on and off by Dylan. When it's off, nothing
  about Claude or Talon changes.
- While it's on, every finished Claude Code reply gets a **spoken version**:
  rewritten to be heard, not read aloud as written, and split into sections
  by topic (decided by an LLM, not by length).
- A **chime** when a reply is ready. The focused tab's session gets a clear
  chime; a background tab's session gets a softer one.
- **Playback controls**: go ahead, continue, repeat, respond, stop, by voice
  or by Ulanzi button.
- **Walkthroughs on request**: Dylan can ask Claude to talk him through a
  document (or other content). It plays section by section with the same
  controls. If he responds partway through, Claude's answer is played, and
  then the walkthrough carries on from where it stopped.
- **Only the focused session talks.** Background sessions prepare their spoken
  version and wait. When Dylan switches to that tab, "go ahead" plays it.
- The written reply stays exactly as it is today. The spoken version is an
  extra format made from it.

## Non-goals (for now)

- Diagrams or other visual formats. They come next, so each reply's formats
  are stored together and a diagram can be added to that bundle later (see
  Storage).
- Cloud voices (ElevenLabs, OpenAI). We start with the built-in Mac voice.
- Claude Desktop and T3 Code. They don't run Claude Code hooks, so this only
  covers Claude Code in **Ghostty** and **Rex**.
- A Ulanzi button for turning listening mode on and off (voice command for now).
- A nicer Talon command for switching tabs (beyond what's in the listening
  command set below).

**Voice (update).** The built-in Mac voice was replaced by local Kokoro
(`bf_isabella`), with the Mac voice as a fallback when Kokoro isn't set up or
fails (Task 11). Cloud voices are still a non-goal.

## Anti-goals (failure even if it technically works)

- **Talon acting on the Mac voice.** If the voice comes out of speakers and
  Talon hears "continue" or "stop" inside a reply, the loop is broken. Talon
  must be deaf while the voice is speaking.
- **Background chatter triggering real commands** while Dylan is away from the
  screen (crossword, a conversation in the room).
- **Reading text as written**: markdown symbols, table cells, full file paths,
  code character by character, bullet-point fragments.
- **Slowing down or interrupting Claude's work.** Producing the spoken version
  must not hold up the session.
- **Unfocused sessions speaking**, or two sessions talking over each other.
- **Changing anything when listening mode is off.**

## How it feels (the crossword walkthrough)

1. Dylan says **"listening on"**. Talon switches to the small listening command
   set (below) and stays that way until he says "listening off".
2. He asks Claude for something in a Ghostty or Rex tab, then turns to his
   crossword.
3. Claude finishes. The written reply appears as usual. In the background, the
   reply is rewritten into spoken sections. When that's ready: a clear chime.
4. Dylan says **"go ahead"** (or presses the knob). Talon goes deaf, and the
   Mac voice reads section 1, for example: "I fixed all three issues. First,
   browser commands in Helium..." It ends by inviting him to continue or
   respond.
5. When the voice stops, Talon wakes into the listening command set.
   - **"continue"** reads the next section.
   - **"repeat"** reads this section again.
   - **"respond"** starts dictation to Claude, the same as the Ulanzi voice key.
   - **"stop"** ends playback. What's left of the reply stays available.
6. After the last section, the voice says that's everything.

**Walkthrough:** Dylan asks, for example, "walk me through the design doc".
Claude writes a spoken version of the document itself, using the same style
rules, and it plays section by section. Because he's reviewing it, it covers
all of the substance, not just a summary, and each pause asks whether he has
thoughts. If he responds, Claude's answer plays as soon as it's ready (he's
waiting for it, so no "go ahead" is needed). Then the walkthrough resumes at the
next section.

## What Dylan decided

- Listening mode only when switched on; written replies unchanged.
- An LLM chunks by meaning and rewrites for the ear (a "skill" for how to talk,
  not just text-to-speech).
- Talon voice commands for the controls (no round trip to Claude for "go
  ahead" or "continue").
- Built-in Mac voice to start.
- Only the focused session plays. Background sessions get a softer chime, and
  Dylan switches tabs himself.
- Walkthroughs on request (e.g. design docs). Responding mid-walkthrough plays
  Claude's answer, then the walkthrough continues.
- Talon is asleep while the voice speaks. After each section it wakes into a
  small command set on its own, accepting only a few responses.
- The Ulanzi works as a remote in listening mode, so he can respond without
  speaking.
- Audio first; diagrams are a later project.
- Code lives in the `dylan` Talon repo.
- **Responding works like today**: start dictation, then press the voice key
  again to stop. With Claude Code's `/voice tap`, that second press also sends.
  Nothing is sent just because he went quiet; he pauses to think.
- **Blocked sessions** (permission prompts, multiple-choice questions, plan
  approvals): he gets a distinct "needs you" chime and a short spoken line,
  then handles it on screen with the remote or keyboard. No voice-driven menu
  navigation. The goal is to not be stuck at the keyboard, not to never touch it.

## Calls made by the designer (Claude), for Dylan to check

- Asking for a walkthrough while listening mode is off **turns listening mode
  on**, since the request itself shows he wants to listen.
- Ending a spoken "respond" uses the voice key (Talon is asleep during
  dictation, so it can't hear a "done" word).
- The knob only acts as a remote while there's something to hear. Otherwise it
  keeps its normal per-app behavior, so he can pick menu options (see piece 3).
- "tab next" / "tab last" are in the listening command set.
- The Talon key leaves listening mode.
- The Haiku rewrite runs via `claude -p --model haiku`.

## Pieces and how they fit

### 1. Listening mode state (Talon)

A flag that's on or off, set by "listening on" and "listening off". While it's
on, Talon is in one of two states:

- **Speaking**: the Mac voice is talking. Talon hears nothing. Only the Ulanzi
  controls work.
- **Waiting**: a small Talon mode with only the listening commands active.
  Dylan's regular commands are off, so chatter can't trigger them.

"listening off" ends playback, leaves the small mode, and returns Talon to
regular command mode.

*Builder: a custom Talon mode (e.g. `user.listening`) is the natural fit. Make
sure regular command-mode files don't match in it.*

### 2. The listening command set

Active only while listening mode is on and the voice isn't speaking:

| Say | Does |
|---|---|
| go ahead | play the focused session's newest unheard reply, or resume |
| continue | next section |
| repeat | this section again |
| respond | start dictating to Claude (same as the Ulanzi voice key); press the voice key to stop and send |
| stop | stop playback; keep the rest for later |
| tab next / tab last | switch terminal tabs (my call: Dylan's regular tab commands are off in this mode) |
| listening off | leave listening mode |

Commands should be fully anchored (silence before and after) to reduce false
triggers, the same way community anchors its wake commands.

### 3. Ulanzi as a remote (listening mode only)

| Control | Does |
|---|---|
| Knob press | go ahead / continue |
| Key 3 | stop (works mid-sentence) |
| Knob left | repeat, or back a section |
| Knob right | skip to the next section |
| Voice key | respond: start dictation; press again to stop and send |
| Talon key | my call: leaves listening mode and returns to command mode |

**When the knob and key 3 act as a remote** (my call): only while the focused
session has something to hear. That means playing, paused between sections, or an
unheard reply or unfinished walkthrough waiting. At all other times they keep
their normal per-app meanings, so in a terminal the knob still moves through
Claude's menus and presses Enter. If the focused session is blocked
(piece 4b), normal meanings take over even if something is unheard, so he
can answer the prompt with the knob.

These must work while the voice is speaking (Talon asleep), and the remote
meanings must override the per-app button meanings in
`ulanzi/ulanzi_apps.py` when they apply. The current Ulanzi setup sends hyper shortcuts that Talon catches in every
mode (`mode: all`), and per-app behavior is done with Context overrides of
`user.ulanzi_*` actions. Listening mode needs to win over those, for example
by checking the flag inside the actions or with a more specific context.

### 4. Spoken replies (Claude Code hook)

A Claude Code **Stop** hook, configured globally in `~/.claude/settings.json`,
runs when a session finishes a reply:

1. If listening mode is off, exit immediately.
2. Start a background job and return right away, so the session is never held
   up.
3. The job takes the final assistant message and has **Claude Haiku** rewrite it
   (my call: via `claude -p --model haiku`, so no separate API key) into spoken
   sections, following the shared style guide (piece 6).
4. It saves the result for that session (see Storage), then plays the clear
   chime if that session is the focused one, or the soft chime if it isn't.

If the turn was one that started a walkthrough, the hook shouldn't also produce
a spoken reply that competes with it (my call; the builder picks the mechanism).

The `claude -p` call must not set off the global Stop hook itself, for example by
using an environment variable the hook checks, or by running with no hooks.

When Dylan responds mid-reply or mid-walkthrough, Claude should know which
section he was hearing. The builder decides how, for example by adding a short
note to the prompt before sending it, or by having the session read the
playback position.

### 4b. Blocked sessions ("needs you")

When a session stops to wait on Dylan mid-task, with a permission prompt, a
multiple-choice question or a plan approval, and listening mode is on:

- play a distinct "needs you" chime (different from the done chimes), focused
  or soft depending on focus as with replies;
- if it's the focused session, say one short line, such as "Claude needs you to
  approve something" or "Claude has a question for you";
- nothing more. Dylan answers on screen with the knob (its normal terminal
  meaning) or the keyboard.

*Builder: Claude Code's Notification hook is the likely trigger. Check which
of these three cases it covers and how to tell them apart, and fill any gaps.*

### 5. Walkthroughs (Claude Code skill)

A user-level Claude Code skill (e.g. `listen` or `walk-me-through`). Dylan asks in
plain words, and the skill tells the main session to:

- write a spoken version of the requested content, in sections, following the
  style guide, covering all of the substance when it's for review;
- hand it to playback (a small helper command the skill calls), marked as a
  walkthrough so it can be resumed after a mid-walkthrough reply.

Playback order for a session: a reply that arrives during a walkthrough plays
first, and then the walkthrough resumes at its next section.

If listening mode is off when he asks, the walkthrough turns it on (my call).
So the helper must be able to switch Talon's listening mode, not just queue
audio.

The skill's source lives in the `dylan` repo and is linked into
`~/.claude/skills/`.

### 6. Spoken style guide (shared)

A single document both the Haiku rewrite and the walkthrough skill follow. It
covers:

- Split by topic, each section short enough to hold in your head (roughly
  20 to 45 seconds when spoken; the builder tunes this).
- Lead with the outcome, then the details.
- Talk like a colleague giving an update: short sentences, no markdown, no
  tables read cell by cell, no bullet fragments.
- File paths, code and commands get described ("the Helium settings file in
  your Talon folder"), not spelled out, unless the exact text matters.
- Mention when something is waiting for Dylan's decision.
- End each section with a short handoff ("Want me to keep going?"); the last
  one says that's everything.

### 7. Which session is focused

The hook (deciding which chime) and "go ahead" (deciding what to play) both need
to know which session is in front:

- **Ghostty** (1.4, AppleScript): `focused terminal of selected tab of front
  window` has a `tty` property, which matches the Claude process's tty exactly
  (verified: `/dev/ttys003` on both sides).
- **Rex**: each Claude session has `REX_SESSION` and `REX_BLOCK` in its
  environment. `rex session inspect SESSION --json` gives `active_window_id`,
  plus each window's `focused_block_id`. The Rex window title, which Talon can
  read, ends with the session's label (e.g. `... - ds9-replan-scope`). The CLI
  binary is at `/Applications/Rex Beta.app/Contents/Helpers/Rex
  Server.rex/Contents/MacOS/rex` (not on PATH). The Rex docs warn that an app
  being attached to a session doesn't prove it's the one showing, so combine
  the title with the focused block.
- In either case, the terminal app also has to be the frontmost app.

Sessions are identified by tty for Ghostty and by `REX_BLOCK` for Rex.

### 8. Playback (Talon)

Talon plays sections with macOS `say`, so stopping kills the process. It tracks
the current section per session, puts Talon to sleep before speaking, and moves
into the waiting state afterwards. The voice and speaking rate are settings.
There are no Premium voices installed right now; the setup notes should tell
Dylan to download one (System Settings > Accessibility > Spoken Content >
System voice > Manage Voices, e.g. "Zoe (Premium)" or "Ava (Premium)"). Use
it when present, and fall back to a standard voice.

Chimes: built-in macOS sounds, one clear and one soft (builder's choice).

## Storage

A state folder outside the repo (builder's choice of location, e.g.
`~/.local/state/listening/`) holds:

- the on/off flag;
- one folder **per reply**, holding the written text and the spoken sections
  (e.g. `written.md`, `spoken.json`). That's where a future `diagram` file
  will go;
- per session: newest unheard reply, active walkthrough and current position.

Keep only recent replies; the builder decides how many.

## Constraints

- macOS, Talon (community + rango-talon + the `dylan` repo), Claude Code CLI in
  Ghostty 1.4 and Rex Beta.
- Don't edit `community/` or `rango-talon/` for this. Everything goes in `dylan/`
  (repo) and `~/.claude/` (hook config, linked skill).
- Fits the existing Ulanzi code in `dylan/ulanzi/` (hyper shortcuts, a release
  delay before emitting keys, and `ulanzi_dictation_toggle`, which presses
  Space for Claude's `/voice tap` in terminals and sleeps Talon while
  dictating).
- The hook must return fast and fail silently. A broken listening mode must
  never break a Claude session.

## Left to the builder

- File layout inside `dylan/`, helper script language, IPC between hook,
  helper and Talon (files on disk are fine).
- Exact Talon mode/tag mechanics, provided the behavior above holds.
- Section length tuning, chime sounds, how many replies to keep.
- How the hook gets the final message (hook input vs. reading the transcript).
- How "respond" mid-playback interacts with `ulanzi_dictation_toggle`'s
  sleep/wake bookkeeping, provided Talon ends up back in the waiting state
  after dictation. (Check that the second voice key press really does send in
  `/voice tap` mode; Dylan reports that it does.)

## Later

- Diagrams as another format in the reply bundle, shown in a browser while the
  voice talks through them.
- A cloud voice.
- A Ulanzi gesture for listening on/off.

## Findings (hook probe, 2026-11-11)

Probed with a temporary logging hook on Stop, Notification and
UserPromptSubmit, in a fresh Claude Code 2.1.322 session in Ghostty and one in
Rex, plus Dylan's other running sessions.

- **Hooks reach running sessions.** A change to `~/.claude/settings.json` takes
  effect in sessions that are already open, so no restart is needed.
- **Rex:** hooks inherit `REX_BLOCK` and `REX_SESSION` (and
  `TERM_PROGRAM=rex`). `REX_BLOCK` (e.g. `block:01a1cadd-…`) equals the
  `focused_block_id` from `rex session inspect "$REX_SESSION" --json` while
  that tab is in front. The Rex session's process tree also has a tty
  (`ttys007`), but `REX_BLOCK` is the key.
- **Ghostty:** hooks don't get `REX_*`. The hook itself runs with no tty, so
  the walk up the parents decides. For a plain session, the first tty found
  (`claude` → `fish` → `login`, all `ttys006`) matches Ghostty's
  `focused terminal` tty. **But** a session started from Claude Code's
  background helper runs under `claude bg-spare` (its own pty, `ttys004`) →
  `claude bg-pty-host` (no tty) → the tab's `claude` (`ttys002`). The first tty
  is wrong there. **Rule: use the topmost tty in the chain**, the last one seen
  before reaching PID 1 or the terminal app.
- **Blocked sessions:** all three cases fire `Notification` with
  `notification_type: "permission_prompt"`, about **6 seconds** after the
  prompt appears. If Dylan answers within those 6 seconds, nothing fires. That
  suits us: no chime for something he's already handling.
  - Plan approval (ExitPlanMode): message `"Claude Code needs your approval for
    the plan"`.
  - Tool permission (Bash in default mode): message `"Claude needs your
    permission"`.
  - Multiple-choice (AskUserQuestion): **the same message as a tool
    permission.** It's told apart by the last `tool_use` in the transcript
    (`transcript_path` in the payload): `AskUserQuestion` means a question.
  - In auto mode, plain commands never prompt, so tool-permission notifications
    are rare for Dylan.
- **Notifications to ignore:** `idle_prompt` ("Claude is waiting for your
  input") fires about 45–60 s after every finished reply.
- **UserPromptSubmit isn't always Dylan.** When a background agent finishes,
  its result arrives as a prompt that starts with `<task-notification>`. Those
  prompts must not count as Dylan answering (no clearing `blocked`, no
  consuming `listening_context`).
- **Stop can fire before the work is done.** A turn that only starts a
  background agent ends with a Stop ("I've started an Explore agent…"), and
  another Stop follows when the result is in. Both are real written replies,
  so both get spoken; the first one is just short.
- `Stop` stdin carries `last_assistant_message` and `stop_hook_active`, as
  documented. Notification stdin has `message`, `notification_type`,
  `session_id` and `transcript_path`, but no `title`.
