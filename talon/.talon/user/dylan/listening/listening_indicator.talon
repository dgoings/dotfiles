# Make listening mode visible in the community mode indicator.
# In listening mode, command/dictation/sleep are all off, so the indicator
# uses its "other" color; while the voice speaks, the mic is "None" and it
# uses its "mute" color (black by default).
mode: user.listening
-
settings():
    user.mode_indicator_color_other = "9b59b6"
