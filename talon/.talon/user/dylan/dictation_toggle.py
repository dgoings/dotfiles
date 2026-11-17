from talon import noise, actions

HOTKEY = "ctrl-alt-shift-z"
recording = False

def on_pop(active):
    global recording
    print(f"pop heard, recording={recording}")
    if recording:
        actions.key(HOTKEY)          # stop Superwhisper
        actions.speech.enable()      # wake Talon
    else:
        actions.speech.disable()     # sleep Talon so it ignores dictation
        actions.key(HOTKEY)          # start Superwhisper
    recording = not recording

# noise.register("pop", on_pop)
