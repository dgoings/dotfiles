---
name: listen
description: Speak a document or other content aloud as a walkthrough through Talon listening mode. Use when the user says "walk me through", "talk me through", "read me" or "listen to" a document, plan, design, diff or other content.
---

# Listen: spoken walkthrough

1. Read `~/.talon/user/dylan/listening/style_guide.md` and follow it. This is review mode: cover all of the substance, in the original's order.
2. Do steps 2 to 4 in ONE Bash call (shell variables don't survive between calls). Create a temp file with `mktemp`, write the sections JSON into it with a quoted heredoc, run listen.py with the file as stdin, and delete the file only if it exits 0:

   ```
   f=$(mktemp)
   cat > "$f" <<'JSON'
   {"sections": [{"title": "...", "text": "..."}]}
   JSON
   /opt/homebrew/bin/python3 ~/.talon/user/dylan/.listening/listen.py walkthrough --title "<title>" < "$f" && rm -f "$f" || echo "kept: $f"
   ```

3. If it exits 2, the JSON was invalid and the file is kept (its path is printed). Fix the JSON by rewriting the file at that literal path, then rerun just the listen.py line with `< <that path>`, deleting the file on exit 0.
4. If stderr says "I can't tell which Claude session this is.", tell the user in one line that the walkthrough couldn't start because the session couldn't be identified.
5. Otherwise reply in one short line: "Starting the walkthrough of <title>." Nothing more; the walkthrough is spoken, so don't repeat the content.

This also turns listening mode on if it was off.
