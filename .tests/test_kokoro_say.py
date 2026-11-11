"""kokoro_say.py, run for real with the TTS venv's Python (renders with the real
models). Skipped when the venv or the models aren't set up."""

import json
import os
import subprocess
from pathlib import Path

import pytest

TTS = Path(__file__).resolve().parent.parent / ".listening" / "tts"
PYTHON = TTS / "venv" / "bin" / "python"
SCRIPT = TTS / "kokoro_say.py"
MODELS = Path(
    os.environ.get("LISTENING_KOKORO_MODELS")
    or Path.home() / ".local/share/talon-listening/kokoro"
)

if not PYTHON.exists():
    pytest.skip("TTS venv not set up (.listening/tts/setup.sh)", allow_module_level=True)

needs_models = pytest.mark.skipif(
    not (MODELS / "kokoro-v1.0.onnx").exists(), reason="Kokoro models not downloaded"
)


def run(tmp_path, *args, models=None):
    env = dict(os.environ, LISTENING_TTS_CACHE=str(tmp_path / "cache"))
    if models is not None:
        env["LISTENING_KOKORO_MODELS"] = str(models)
    result = subprocess.run(
        [str(PYTHON), str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return result


def dry_play(tmp_path, text, *extra, models=None):
    result = run(tmp_path, "--dry-run", *extra, "--play", text, models=models)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def wavs(tmp_path):
    return sorted((tmp_path / "cache").glob("*.wav"))


@needs_models
def test_dry_run_play_renders_then_execs_afplay(tmp_path):
    argv = dry_play(tmp_path, "Hello there.")
    [wav] = wavs(tmp_path)
    assert argv == ["afplay", str(wav)]
    assert wav.stat().st_size > 1000


@needs_models
def test_second_play_uses_cache(tmp_path):
    first = dry_play(tmp_path, "Hello again.")
    [wav] = wavs(tmp_path)
    mtime = wav.stat().st_mtime_ns
    assert dry_play(tmp_path, "Hello again.") == first
    assert wav.stat().st_mtime_ns == mtime
    assert wavs(tmp_path) == [wav]


def test_missing_models_falls_back_to_say(tmp_path):
    empty = tmp_path / "no-models"
    empty.mkdir()
    argv = dry_play(
        tmp_path,
        "Hello there.",
        "--fallback-voice",
        "Zoe (Premium)",
        "--rate",
        "190",
        models=empty,
    )
    assert argv == ["say", "-v", "Zoe (Premium)", "-r", "190", "Hello there."]
    assert wavs(tmp_path) == []
    assert "missing model file" in (tmp_path / "cache" / "last-error.txt").read_text()


def test_bad_arguments_in_play_mode_still_speak(tmp_path):
    result = run(tmp_path, "--dry-run", "--play", "--speed", "fast", "Hello there.")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0] == "say"


@needs_models
def test_render_only_writes_cache_file(tmp_path):
    result = run(tmp_path, "--render-only", "Rendered ahead.")
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    [wav] = wavs(tmp_path)
    # The play that follows finds it and doesn't render again.
    mtime = wav.stat().st_mtime_ns
    assert dry_play(tmp_path, "Rendered ahead.") == ["afplay", str(wav)]
    assert wav.stat().st_mtime_ns == mtime


def test_render_only_fails_without_models(tmp_path):
    empty = tmp_path / "no-models"
    empty.mkdir()
    result = run(tmp_path, "--render-only", "Hello there.", models=empty)
    assert result.returncode != 0
    assert wavs(tmp_path) == []


@needs_models
def test_cache_pruned_to_200(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    for i in range(205):
        old = cache / f"old{i:03d}.wav"
        old.write_bytes(b"x")
        os.utime(old, (1_000_000 + i, 1_000_000 + i))
    result = run(tmp_path, "--render-only", "Newest one.")
    assert result.returncode == 0, result.stderr
    remaining = wavs(tmp_path)
    assert len(remaining) == 200
    names = {p.name for p in remaining}
    assert "old000.wav" not in names and "old005.wav" not in names
    assert "old006.wav" in names and "old204.wav" in names
    assert any(not n.startswith("old") for n in names)
