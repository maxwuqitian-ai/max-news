#!/usr/bin/env bash
set -euo pipefail
# Official release digest from GitHub's expanded asset metadata for v0.40.1.
# Install only inside the workspace; no sudo, trust bypasses, or shell-piped installers.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
ollama_root="${NEWS_OLLAMA_ROOT:-$repo_root/.tools/ollama}"
if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then
  echo 'This pinned installer supports Linux x86_64; use the official Ollama installer on other systems.' >&2
  exit 1
fi
version=0.40.1
digest=a7aebbe3dd76ccf1351a56a3e57218ad4863cb5f9a9938c58de87a37555e355d
if [ -x "$ollama_root/bin/ollama" ] && "$ollama_root/bin/ollama" --version 2>&1 | grep -q "$version"; then
  exit 0
fi
mkdir -p "$ollama_root"
archive="$ollama_root/ollama-linux-amd64.tar.zst"
if [ ! -f "$archive" ]; then
  curl --fail --location --retry 2 --connect-timeout 20 \
    "https://github.com/ollama/ollama/releases/download/v$version/ollama-linux-amd64.tar.zst" \
    --output "$archive.part"
  mv "$archive.part" "$archive"
fi
printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status
# A verified official archive is extracted only after digest validation.
tar --zstd -xf "$archive" -C "$ollama_root"
rm "$archive"
