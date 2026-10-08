#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_MODELS="$repo_root/.models"
export OLLAMA_CONTEXT_LENGTH=32768
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
mkdir -p output .models "$HOME/.ollama"
if ! curl --silent --fail --noproxy 127.0.0.1 http://127.0.0.1:11434/api/version >/dev/null; then
  nohup python3 scripts/serve_ollama.py > output/ollama.log 2>&1 < /dev/null &
  printf '%s\n' "$!" > output/ollama.pid
fi
for attempt in $(seq 1 30); do
  if curl --silent --fail --noproxy 127.0.0.1 http://127.0.0.1:11434/api/version >/dev/null; then
    exit 0
  fi
  sleep 1
done
echo 'Ollama failed to become ready; inspect output/ollama.log' >&2
exit 1
