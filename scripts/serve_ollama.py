"""Relay runtime diagnostics without persisting its startup environment dump."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
environment = os.environ.copy()
for name in ('RESEND_API_KEY', 'NEWS_LLM_API_KEY', 'OPENAI_API_KEY', 'GMAIL_CLIENT_ID',
             'GMAIL_CLIENT_SECRET', 'GMAIL_REFRESH_TOKEN', 'NEWS_RECIPIENT', 'NEWS_SENDER'):
    environment.pop(name, None)
process = subprocess.Popen([str(root / '.tools/ollama/bin/ollama'), 'serve'],
                           env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
try:
    for line in process.stdout:
        if 'env=' in line or 'ssh-ed25519' in line: continue
        sys.stdout.write(line)
        sys.stdout.flush()
    raise SystemExit(process.wait())
finally:
    if process.poll() is None: process.terminate()
