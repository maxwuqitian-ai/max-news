import importlib.util
import json
from pathlib import Path
import subprocess


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def test_remote_ledger_survives_new_machine_and_records_pending_before_send(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('state_branch', 'scripts/state_branch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    remote = tmp_path / 'remote.git'
    remote.mkdir()
    run('git', 'init', '--bare', cwd=remote)
    root = tmp_path / 'application'
    root.mkdir()
    run('git', 'init', cwd=root)
    run('git', 'remote', 'add', 'origin', str(remote), cwd=root)
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setattr(module, 'STATE', root / '.news-state')
    module.initialize()
    pending = {'daily:test': {'status': 'pending'}}
    (module.STATE / 'deliveries.json').write_text(json.dumps(pending))
    module.push()
    second = tmp_path / 'second-machine'
    second.mkdir()
    run('git', 'init', cwd=second)
    run('git', 'remote', 'add', 'origin', str(remote), cwd=second)
    monkeypatch.setattr(module, 'ROOT', second)
    monkeypatch.setattr(module, 'STATE', second / '.news-state')
    module.initialize()
    assert json.loads((module.STATE / 'deliveries.json').read_text()) == pending
