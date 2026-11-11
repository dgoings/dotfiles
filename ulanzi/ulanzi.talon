# Ulanzi AU05: global controls + defaults for any app without its own file.
#
# Ulanzi Studio setup: ONE preset, no per-app presets. Each control sends:
#   Voice key        ctrl+opt+shift+cmd+V   dictation (Talon sleeps meanwhile)
#   Talon key        ctrl+opt+shift+cmd+T   Talon wake/sleep toggle
#   Key 3            ctrl+opt+shift+cmd+B   "back / cancel"
#   Knob left        ctrl+opt+shift+cmd+J   "move up / previous"
#   Knob right       ctrl+opt+shift+cmd+L   "move down / next"
#   Knob press       ctrl+opt+shift+cmd+K   "confirm"
#
# What B/J/K/L do per app lives in ulanzi_apps.py (defaults in ulanzi.py).
# Every control goes through user.ulanzi_control, which lets listening mode
# (listening/listening.py) take it over first; otherwise it does the above.
# `mode: all` keeps every control working while Talon is asleep or you're
# dictating.
mode: all
-

key(ctrl-alt-shift-cmd-v): user.ulanzi_control("voice")
key(ctrl-alt-shift-cmd-t): user.ulanzi_control("talon")
key(ctrl-alt-shift-cmd-b): user.ulanzi_control("back")
key(ctrl-alt-shift-cmd-j): user.ulanzi_control("knob_left")
key(ctrl-alt-shift-cmd-l): user.ulanzi_control("knob_right")
key(ctrl-alt-shift-cmd-k): user.ulanzi_control("knob_press")

settings():
    # On-screen dot showing Talon's mode: blue command, grey asleep,
    # purple listening, black while the listening voice speaks.
    user.mode_indicator_show = true
    # Middle of the right edge (community's top-center default hides behind
    # the MacBook camera notch).
    user.mode_indicator_x = 1
    user.mode_indicator_y = 0.5
