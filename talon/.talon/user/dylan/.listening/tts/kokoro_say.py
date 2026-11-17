"""Speak (or pre-render) one line of listening-mode speech with Kokoro.

Runs in .listening/tts/venv (Python 3.14), not in Talon.

    kokoro_say.py [--voice V] [--speed S] [--fallback-voice NAME] [--rate WPM]
                  [--dry-run] (--play | --render-only) [--] TEXT

--play renders TEXT (or finds it in the cache) and then becomes `afplay` with
os.execvp, so the PID Talon started is the speech: killing it stops speech
while rendering or while playing. If anything about Kokoro fails, it becomes
`say` with the Mac voice instead, so --play always speaks.

--render-only puts TEXT in the cache and exits (non-zero on failure). Talon
uses it to render the next section while this one plays.

--dry-run prints the argv --play would exec, as JSON, instead of exec'ing it.

Rendered audio is cached as <cache>/<sha256 of "voice|speed|text">.wav, newest
200 kept. Cache: ~/.cache/talon-listening/tts ($LISTENING_TTS_CACHE). Models:
~/.local/share/talon-listening/kokoro ($LISTENING_KOKORO_MODELS).
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

MODEL = "kokoro-v1.0.onnx"
VOICES = "voices-v1.0.bin"
# The eSpeak bundled with espeakng_loader ignores its data path; Homebrew's works.
ESPEAK_LIB = "/opt/homebrew/lib/libespeak-ng.dylib"
ESPEAK_DATA = "/opt/homebrew/share/espeak-ng-data"
KEEP = 200
STALE_TEMP_SECONDS = 3600
DEFAULT_FALLBACK_VOICE = "Samantha"
DEFAULT_RATE = 190


def models_dir() -> Path:
    env = os.environ.get("LISTENING_KOKORO_MODELS")
    return Path(env) if env else Path.home() / ".local/share/talon-listening/kokoro"


def cache_dir() -> Path:
    env = os.environ.get("LISTENING_TTS_CACHE")
    return Path(env) if env else Path.home() / ".cache/talon-listening/tts"


def cache_path(voice: str, speed: float, text: str) -> Path:
    digest = hashlib.sha256(f"{voice}|{speed}|{text}".encode()).hexdigest()
    return cache_dir() / f"{digest}.wav"


def lang_for(voice: str) -> str:
    return "en-gb" if voice[:2] in ("bf", "bm") else "en-us"


def render(path: Path, voice: str, speed: float, text: str) -> None:
    """Render `text` to `path`, atomically: a half-written file never exists
    under the final name. Raises on any failure."""
    models = models_dir()
    for name in (MODEL, VOICES):
        if not (models / name).is_file():
            raise FileNotFoundError(f"missing model file {models / name}")
    if not Path(ESPEAK_LIB).exists():
        raise FileNotFoundError(f"missing {ESPEAK_LIB} (brew install espeak-ng)")

    import soundfile
    from kokoro_onnx import Kokoro
    from kokoro_onnx.config import EspeakConfig

    kokoro = Kokoro(
        str(models / MODEL),
        str(models / VOICES),
        espeak_config=EspeakConfig(lib_path=ESPEAK_LIB, data_path=ESPEAK_DATA),
    )
    samples, rate = kokoro.create(text, voice=voice, speed=speed, lang=lang_for(voice))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".wav.tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            soundfile.write(f, samples, rate, format="WAV")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    prune(path.parent)


def prune(folder: Path) -> None:
    """Keep the newest KEEP renders; drop temp files a killed render left."""
    entries = []
    now = time.time()
    for entry in os.scandir(folder):
        try:
            mtime = entry.stat().st_mtime
            if entry.name.endswith(".wav.tmp"):
                if now - mtime > STALE_TEMP_SECONDS:
                    os.unlink(entry.path)
            elif entry.name.endswith(".wav"):
                entries.append((mtime, entry.path))
        except OSError:
            pass
    entries.sort(reverse=True)
    for _, old in entries[KEEP:]:
        try:
            os.unlink(old)
        except OSError:
            pass


def ensure_rendered(voice: str, speed: float, text: str) -> Path:
    path = cache_path(voice, speed, text)
    if not path.is_file():
        render(path, voice, speed, text)
    return path


def note_error(message: str) -> None:
    """Talon discards our stderr, so keep the last failure where it can be found."""
    print(f"kokoro_say: {message}", file=sys.stderr)
    try:
        cache_dir().mkdir(parents=True, exist_ok=True)
        (cache_dir() / "last-error.txt").write_text(f"{time.ctime()}: {message}\n")
    except OSError:
        pass


def become(argv: list[str], dry_run: bool) -> None:
    """Exec `argv` (or print it, for --dry-run). Returns only if exec failed."""
    if dry_run:
        print(json.dumps(argv))
        sys.exit(0)
    os.execvp(argv[0], argv)


def say_argv(fallback_voice: str, rate: int, text: str) -> list[str]:
    return ["say", "-v", fallback_voice, "-r", str(rate), text]


def parse(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Listening-mode speech with Kokoro")
    parser.add_argument("--voice", default="bf_isabella")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--fallback-voice", default=DEFAULT_FALLBACK_VOICE)
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE)
    parser.add_argument("--dry-run", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--play", action="store_true")
    mode.add_argument("--render-only", action="store_true")
    parser.add_argument("text")
    return parser.parse_args(args)


def main(args: list[str]) -> int:
    try:
        opts = parse(args)
    except SystemExit:
        if "--play" not in args or not args:
            raise
        # Still speak: the text is the last argument.
        become(say_argv(DEFAULT_FALLBACK_VOICE, DEFAULT_RATE, args[-1]), "--dry-run" in args)
        return 1

    if opts.render_only:
        try:
            ensure_rendered(opts.voice, opts.speed, opts.text)
        except Exception as e:
            note_error(f"render failed: {e!r}")
            return 1
        return 0

    try:
        path = ensure_rendered(opts.voice, opts.speed, opts.text)
        become(["afplay", str(path)], opts.dry_run)
    except Exception as e:
        note_error(f"fell back to say: {e!r}")
    try:
        become(say_argv(opts.fallback_voice, opts.rate, opts.text), opts.dry_run)
    except OSError as e:
        note_error(f"say failed too: {e!r}")
    return 1  # neither afplay nor say could start


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
