"""Durable Actions ledger on a dedicated branch, without changing the application checkout."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.news-state'
BRANCH = 'news-agent-state'


def git(*args, check=True, capture=True, cwd=None):
    return subprocess.run(['git', *args], cwd=cwd or STATE, check=check,
                          capture_output=capture, text=True)


def initialize():
    if STATE.exists(): raise RuntimeError('Refusing to overwrite an existing state checkout')
    STATE.mkdir()
    git('init', '--quiet')
    # Use platform/Actions Git authentication as configured; never extract credential values.
    remote = git('remote', 'get-url', 'origin', cwd=ROOT).stdout.strip()
    git('remote', 'add', 'origin', remote)
    # Actions checkout persists a scoped extraheader in local Git config; include that config
    # for authenticated operations without printing or copying its secret value.
    git('config', 'include.path', str(ROOT / '.git' / 'config'))
    git('config', 'user.name', 'news-agent[bot]')
    git('config', 'user.email', 'news-agent@users.noreply.github.com')
    refs = git('ls-remote', '--exit-code', 'origin', 'refs/heads/' + BRANCH, check=False)
    if refs.returncode == 0:
        git('fetch', '--depth=1', 'origin', BRANCH)
        git('checkout', '-B', BRANCH, 'FETCH_HEAD')
    elif refs.returncode == 2:  # confirmed absent branch, NOT an authentication/network failure
        git('checkout', '--orphan', BRANCH)
        (STATE / 'deliveries.json').write_text('{}\n')
        git('add', 'deliveries.json')
        git('commit', '-m', 'Initialize delivery ledger')
        git('push', 'origin', f'HEAD:refs/heads/{BRANCH}')
    else:
        raise RuntimeError('Cannot read remote delivery ledger; refusing a blank state')
    path = STATE / 'deliveries.json'
    data = json.loads(path.read_text())
    if not isinstance(data, dict): raise RuntimeError('Invalid remote ledger')
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a') as f: f.write('NEWS_DURABLE_STATE=true\n')


def push():
    git('add', 'deliveries.json')
    if git('diff', '--cached', '--quiet', check=False).returncode == 0: return
    git('commit', '-m', 'Record newsletter delivery state')
    # Never force-push: a concurrent change must abort before an email can be sent.
    git('push', 'origin', f'HEAD:refs/heads/{BRANCH}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'push'])
    args = parser.parse_args()
    try: initialize() if args.action == 'init' else push()
    except Exception:
        # Git diagnostics may contain remote credentials; suppress captured stderr.
        raise SystemExit('Durable ledger operation failed; no automatic email retry is permitted')
