import pytest

from news_agent.delivery import delivery_key
from news_agent.timing import verify_delivery_time


@pytest.mark.parametrize('now,expected', [
    ('2026-11-24T12:15:00+00:00', '2026-11-23'),
    ('2026-11-24T13:14:59+00:00', '2026-11-23'),
    ('2026-11-24T13:15:00+00:00', '2026-11-24'),
    ('2026-11-24T22:23:13+00:00', '2026-11-24'),
    ('2026-11-25T06:30:00+00:00', '2026-11-24'),
    ('2026-10-09T12:15:00+00:00', '2026-10-09'),
    ('2026-10-09T13:15:00+00:00', '2026-10-09'),
    ('2026-11-01T12:15:00+00:00', '2026-10-31'),
    ('2026-11-01T13:15:00+00:00', '2026-11-01'),
])
def test_scheduled_audit_checks_latest_completed_morning_even_when_delayed(config, now, expected):
    from datetime import datetime
    from news_agent.timing import latest_due_edition_date
    assert latest_due_edition_date(config, datetime.fromisoformat(now)) == expected


def test_actual_combined_cron_workflow_cannot_silently_skip_missing_mail(config, tmp_path, monkeypatch):
    import base64
    import datetime as datetime_module
    import json
    from pathlib import Path
    import subprocess
    from types import SimpleNamespace
    import yaml
    import news_agent.config

    workflow = yaml.safe_load(Path('.github/workflows/verify-morning-delivery.yml').read_text())
    step = next(s for s in workflow['jobs']['verify']['steps'] if s.get('id') == 'timing')
    script = step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    clock = datetime_module.datetime.fromisoformat('2026-11-24T22:23:13+00:00')

    class Clock(datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.astimezone(tz)

    reads = []
    def read_ledger(*args, **kwargs):
        reads.append(args)
        return SimpleNamespace(stdout=json.dumps({'content': base64.b64encode(b'{}').decode()}))

    monkeypatch.setattr(datetime_module, 'datetime', Clock)
    monkeypatch.setattr(news_agent.config, 'load', lambda _: config)
    monkeypatch.setattr(subprocess, 'run', read_ledger)
    monkeypatch.setenv('EVENT', 'schedule')
    monkeypatch.setenv('SCHEDULE', '15 12,13 * * *')
    monkeypatch.setenv('NEWS_RECIPIENT', 'reader@example.com')
    monkeypatch.setenv('GITHUB_REPOSITORY', 'owner/synthetic')
    monkeypatch.setenv('GITHUB_OUTPUT', str(tmp_path / 'outputs'))
    with pytest.raises(SystemExit, match='No confirmed daily send'):
        exec(compile(script, 'actual-scheduled-audit', 'exec'), {})
    assert len(reads) == 1


@pytest.mark.parametrize('date,sent', [
    ('2026-10-09', '2026-10-09T12:00:00+00:00'),
    ('2026-01-15', '2026-01-15T13:00:59+00:00'),
    ('2026-03-08', '2026-03-08T12:00:00+00:00'),
    ('2026-11-01', '2026-11-01T13:00:00+00:00'),
])
def test_on_time_across_dst(config, date, sent):
    record = {'status': 'sent', 'sent_at': sent}
    ledger = {delivery_key('reader@example.com', date): record}
    assert verify_delivery_time(ledger, 'reader@example.com', date, config) == record


@pytest.mark.parametrize('sent', [
    '2026-10-09T11:59:59+00:00',
    '2026-10-09T12:01:01+00:00',
    '2026-10-09T15:34:40.961603+00:00',
    '2026-10-10T12:00:00+00:00',
    '2026-10-09T08:00:00',
])
def test_early_late_wrong_day_or_unknown_timezone_fails(config, sent):
    ledger = {delivery_key('reader@example.com', '2026-10-09'):
              {'status': 'sent', 'sent_at': sent}}
    with pytest.raises(ValueError):
        verify_delivery_time(ledger, 'reader@example.com', '2026-10-09', config)


@pytest.mark.parametrize('record', [None, {'status': 'pending'}, {'status': 'unknown'}])
def test_missing_or_uncertain_send_cannot_prove_timing(config, record):
    ledger = {delivery_key('reader@example.com', '2026-10-09'): record} if record else {}
    with pytest.raises(ValueError):
        verify_delivery_time(ledger, 'reader@example.com', '2026-10-09', config)
