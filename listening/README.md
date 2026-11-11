# Listening mode

Claude Code replies are rewritten for the ear and spoken through Talon, so you can listen away from the screen. Design: `docs/2026-11-10-listening-mode-design.md`. Style guide for the spoken text: `listening/style_guide.md`.

## Turn it on and off

- Say "listening on" (or ask for a walkthrough, which turns it on by itself).
- Say "listening off", or press the Talon key, to leave. Speech stops, the mic is restored and normal command mode returns.

## Install the Claude Code hooks and skill

    /opt/homebrew/bin/python3 ~/.talon/user/dylan/.listening/install.py

This backs up `~/.claude/settings.json` (to `settings.json.bak-listening-<timestamp>`), adds a Stop, a Notification (`permission_prompt`) and a UserPromptSubmit hook, and links `~/.claude/skills/listen` to `.listening/skill/listen`. It only adds; existing hooks stay. Running it again changes nothing. Running sessions pick the hooks up without a restart.

Options: `--settings PATH`, `--skills-dir PATH`, `--python PATH` (default `/opt/homebrew/bin/python3`, written verbatim into the hook commands; must be Python 3.10 or newer). SKILL.md uses `/opt/homebrew/bin/python3`, so a different `--python` also needs that line edited. It refuses to replace a `listen` skill folder that isn't its own link.

Remove everything it added (hooks and link only, with another backup):

    /opt/homebrew/bin/python3 ~/.talon/user/dylan/.listening/install.py --uninstall

## Commands while listening mode is on

Only these are heard between spoken sections, and each must be said alone:

| Say | Does |
|---|---|
| go ahead | play the focused session's newest unheard reply, or resume |
| continue | next section |
| repeat | this section again |
| respond | start dictating to Claude |
| stop | stop playback; the rest is kept |
| tab next / tab last | switch terminal tabs |
| listening off | leave listening mode |

Saying "respond" starts dictation. End it with the voice-key shortcut (not plain Space), so Talon un-mutes. With Claude Code's `/voice tap`, that second press also sends.

## Ulanzi AU05 as a remote

The knob (turn and press) and key 3 act as a remote only while the focused session has something to hear (playing, paused, or an unheard reply or walkthrough waiting) and isn't blocked; otherwise they keep their normal per-app meanings. While listening mode is on, the Talon key always leaves listening mode, and the voice key always starts or ends a response in a Claude terminal (Ghostty or Rex).

| Control | Does | Shortcut |
|---|---|---|
| Knob press | go ahead / continue | ctrl+opt+shift+cmd+K |
| Key 3 | stop (works mid-sentence) | ctrl+opt+shift+cmd+B |
| Knob left | repeat, or back a section | ctrl+opt+shift+cmd+J |
| Knob right | skip to next section | ctrl+opt+shift+cmd+L |
| Voice key | respond: start dictation; press again to stop | ctrl+opt+shift+cmd+V |
| Talon key | leave listening mode | ctrl+opt+shift+cmd+T |

Each control is just a hyper-key keyboard shortcut (ctrl+opt+shift+cmd plus V, T, B, J, L or K), so you can press the same shortcuts on a keyboard without the device.

## Blocked sessions

When a session is blocked on you (tool permission, multiple-choice question, plan approval), you get a "needs you" chime and a short spoken line. All three come from the Notification hook, which fires only if the prompt is still unanswered after about 6 seconds. Answering faster means no chime. Answer on screen, with the knob or keyboard.

## Walkthroughs

Ask Claude to "walk me through", "talk me through", "read me" or "listen to" a document. The `listen` skill writes a sectioned spoken version and queues it; a reply you ask for mid-walkthrough plays first, then the walkthrough resumes.

## Voice

Built-in Mac voice. Preference order: Zoe (Premium), Ava (Premium), Evan (Premium), then Samantha. To get a Premium voice: System Settings, Accessibility, Spoken Content, System Voice, Manage Voices, then download one (e.g. Zoe) with the Premium variant. Override with the Talon setting `user.listening_voice`; speed is `user.listening_rate` (default 190 words per minute).
