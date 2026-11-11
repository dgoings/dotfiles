---
name: listen
description: Speak a document or other content aloud as a walkthrough through Talon listening mode. Use when the user says "walk me through", "talk me through", "read me" or "listen to" a document, plan, design, diff or other content.
---

# Listen: spoken walkthrough

1. Read `~/.talon/user/dylan/listening/style_guide.md` and follow it. This is review mode: cover all of the substance, in the original's order.
2. Write the sections as JSON, exactly `{"sections": [{"title": "...", "text": "..."}]}`, to a fresh temp file: `f=$(mktemp)`.
3. Run `/opt/homebrew/bin/python3 ~/.talon/user/dylan/.listening/listen.py walkthrough --title "<title>" < "$f"`, then delete the file with `rm -f "$f"`.
4. If it exits 2, the JSON was invalid: fix it per the error message and retry.
5. If stderr says "I can't tell which Claude session this is.", tell the user in one line that the walkthrough couldn't start because the session couldn't be identified.
6. Otherwise reply in one short line: "Starting the walkthrough of <title>." Nothing more; the walkthrough is spoken, so don't repeat the content.

This also turns listening mode on if it was off.
