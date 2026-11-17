# Listening mode: the only commands Talon hears between spoken sections.
# Every rule is anchored (silence before and after) so chatter can't trigger it.
mode: user.listening
-
^go ahead$: user.listening_go_ahead()
^continue$: user.listening_continue()
^repeat$: user.listening_repeat()
^respond$: user.listening_respond()
^stop$: user.listening_stop()
^tab next$: app.tab_next()
^tab last$: app.tab_previous()
^listening off$: user.listening_off()
