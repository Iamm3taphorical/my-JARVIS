#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-venv}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
PIPER_VOICE="${PIPER_VOICE:-en_US-lessac-medium}"
VOICE_DIR="$ROOT_DIR/voices"
VOICE_MODEL="$VOICE_DIR/${PIPER_VOICE}.onnx"
VOICE_CONFIG="$VOICE_MODEL.json"
VOICE_BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"

log() {
  printf '[setup] %s\n' "$1"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    return 1
  fi
}

install_apt_deps() {
  if need_cmd apt-get; then
    log "Installing system audio dependencies with apt."
    sudo apt-get update
    sudo apt-get install -y ffmpeg alsa-utils python3-venv python3-pip curl
  else
    log "apt-get not available; skipping system package installation."
  fi
}

create_venv() {
  log "Creating Python virtual environment at $VENV_DIR."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip wheel setuptools
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
}

ensure_voice() {
  mkdir -p "$VOICE_DIR"
  if [[ -f "$VOICE_MODEL" && -f "$VOICE_CONFIG" ]]; then
    log "Piper voice already exists: $VOICE_MODEL"
    return
  fi

  log "Downloading Piper voice: $PIPER_VOICE"
  curl -L "${VOICE_BASE_URL}/${PIPER_VOICE}.onnx" -o "$VOICE_MODEL"
  curl -L "${VOICE_BASE_URL}/${PIPER_VOICE}.onnx.json" -o "$VOICE_CONFIG"
}

ensure_ollama_model() {
  if ! need_cmd ollama; then
    log "Ollama was not found on PATH. Install Ollama first from https://ollama.com/download/linux"
    return 1
  fi

  if ! ollama list >/dev/null 2>&1; then
    log "Ollama is installed but not responding. Start it in another terminal with: ollama serve"
    return 1
  fi

  if ollama list | awk '{print $1}' | grep -Fxq "$OLLAMA_MODEL"; then
    log "Ollama model already exists: $OLLAMA_MODEL"
  else
    log "Pulling Ollama model: $OLLAMA_MODEL"
    ollama pull "$OLLAMA_MODEL"
  fi
}

warm_whisper() {
  log "Checking faster-whisper model availability. This may download the first time."
  "$VENV_DIR/bin/python" - <<'PY'
import json

from faster_whisper import WhisperModel

with open("config.json", "r", encoding="utf-8") as handle:
    stt_config = json.load(handle)["stt"]

model_size = stt_config.get("model_size", "small")
device = stt_config.get("device", "cpu")
compute_type = stt_config.get("compute_type", "int8")

WhisperModel(model_size, device=device, compute_type=compute_type)
print(f"faster-whisper {model_size} is ready")
PY
}

verify() {
  log "Running JARVIS startup checks."
  "$VENV_DIR/bin/python" main.py --check --text
}

build_frontend() {
  if ! need_cmd npm; then
    log "npm was not found; skipping GUI frontend setup."
    return
  fi

  log "Installing GUI frontend dependencies."
  npm install
  log "Building GUI frontend."
  npm run build
}

install_apt_deps
create_venv
ensure_voice
ensure_ollama_model
warm_whisper
build_frontend
verify

log "Setup complete. Run: source $VENV_DIR/bin/activate && python main.py"
