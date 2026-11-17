#!/bin/sh
# Sets up the Kokoro voice for listening mode. Safe to run again: it only
# creates or fetches what's missing.
#
#   .listening/tts/setup.sh [--from DIR]
#
# Creates .listening/tts/venv (Python 3.14: kokoro-onnx has no onnxruntime
# wheels for 3.15), installs kokoro-onnx and soundfile, and puts the two model
# files in the models folder (~/.local/share/talon-listening/kokoro, or
# $LISTENING_KOKORO_MODELS). With --from DIR, model files are copied from DIR
# instead of downloaded.
#
# Kokoro also needs Homebrew's espeak-ng (brew install espeak-ng).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
VENV="$HERE/venv"
PYTHON314=/opt/homebrew/opt/python@3.14/bin/python3.14
MODELS="${LISTENING_KOKORO_MODELS:-$HOME/.local/share/talon-listening/kokoro}"
RELEASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
FROM=""

if [ "${1:-}" = "--from" ]; then
    FROM="${2:?--from needs a folder}"
fi

if [ ! -x "$PYTHON314" ]; then
    echo "Python 3.14 not found at $PYTHON314 (brew install python@3.14)" >&2
    exit 1
fi
if [ ! -e /opt/homebrew/lib/libespeak-ng.dylib ]; then
    echo "warning: Homebrew espeak-ng is missing (brew install espeak-ng); Kokoro will fall back to the Mac voice" >&2
fi

if [ ! -x "$VENV/bin/python" ]; then
    echo "creating $VENV"
    "$PYTHON314" -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c "import kokoro_onnx, soundfile" 2>/dev/null; then
    echo "installing kokoro-onnx and soundfile"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet kokoro-onnx soundfile
fi

mkdir -p "$MODELS"
for name in kokoro-v1.0.onnx voices-v1.0.bin; do
    if [ -s "$MODELS/$name" ]; then
        continue
    fi
    tmp="$MODELS/.$name.partial"
    if [ -n "$FROM" ] && [ -s "$FROM/$name" ]; then
        echo "copying $name from $FROM"
        cp "$FROM/$name" "$tmp"
    else
        echo "downloading $name"
        curl -fL --progress-bar -o "$tmp" "$RELEASE/$name"
    fi
    mv "$tmp" "$MODELS/$name"
done

echo "Kokoro voice ready (models in $MODELS)"
