import copy
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import yaml

from news_agent.external_scheduler import build_jobs, configure, main, SchedulerError


class Service:
    def __init__(self):
        self.jobs = {}
        self.calls = []
        self.incomplete = False
        self.lose_create_response = False
        self.wrong_readback = False

    def handle(self, request):
        method, path = request.method, request.url.path
        self.calls.append((method, str(request.url)))
        if request.url.host == 'api.github.com':
            assert request.headers['Authorization'] == 'Bearer synthetic-github-token'
            if method == 'GET': return httpx.Response(200, json={'state': 'active'})
            assert method == 'POST'
            assert json.loads(request.content)['inputs'] == {'mode': 'check'}
            return httpx.Response(204)
        assert request.url.host == 'api.cron-job.org'
        assert request.headers['Authorization'] == 'Bearer synthetic-cron-key'
        if path == '/jobs' and method == 'GET':
            return httpx.Response(200, json={'jobs': list(self.jobs.values()), 'someFailed': self.incomplete})
        if method == 'PUT':
            job_id = max(self.jobs, default=0) + 1
            self.jobs[job_id] = dict(json.loads(request.content)['job'], jobId=job_id)
            if self.lose_create_response:
                self.lose_create_response = False
                raise httpx.ReadTimeout('Synthetic lost response', request=request)
            return httpx.Response(200, json={'jobId': job_id})
        job_id = int(path.rsplit('/', 1)[1])
        if method == 'PATCH':
            self.jobs[job_id].update(json.loads(request.content)['job'])
            return httpx.Response(200, json={})
        job = copy.deepcopy(self.jobs[job_id])
        if self.wrong_readback: job['schedule']['timezone'] = 'UTC'
        return httpx.Response(200, json={'job': job})


def setup(client, config, apply=True):
    return configure(client, 'owner/news', config, 'synthetic-cron-key',
                     'synthetic-github-token', apply=apply)


def test_plan_never_uses_credentials_or_network(config, monkeypatch, capsys):
    monkeypatch.setenv('CRONJOB_API_KEY', 'never-print-this-cron-key')
    monkeypatch.setenv('NEWS_DISPATCH_TOKEN', 'never-print-this-dispatch-key')
    monkeypatch.setattr('news_agent.external_scheduler.load', lambda _: config)
    monkeypatch.setattr(httpx, 'Client', lambda **_: pytest.fail('Plan accessed network'))
    assert main(['plan', '--repository', 'owner/news']) == 0
    text = capsys.readouterr().out
    assert 'never-print-this' not in text
    assert json.loads(text)['applied'] is False
    jobs = json.loads(text)['jobs']
    assert jobs[0]['schedule']['hours'] == [4, 5, 6, 7]
    assert jobs[0]['schedule']['minutes'] == [37]
    assert jobs[1]['schedule']['hours'] == [8]
    assert jobs[1]['schedule']['minutes'] == [15]
    assert all(job['schedule']['timezone'] == 'America/New_York' for job in jobs)


def test_apply_and_verify_reconcile_existing_jobs_without_duplicates(config):
    service = Service()
    with httpx.Client(transport=httpx.MockTransport(service.handle)) as client:
        first = setup(client, config)
        second = setup(client, config)
        before = len(service.calls)
        verified = setup(client, config, apply=False)
    assert first == second == verified
    assert len(service.jobs) == 2
    assert sum(method == 'PUT' for method, _ in service.calls) == 2
    assert sum(method == 'PATCH' for method, _ in service.calls) == 2
    assert all(method == 'GET' for method, _ in service.calls[before:])


def test_incomplete_listing_cannot_create_or_claim_readiness(config):
    service = Service(); service.incomplete = True
    with httpx.Client(transport=httpx.MockTransport(service.handle)) as client:
        with pytest.raises(SchedulerError, match='Incomplete'):
            setup(client, config)
    assert service.jobs == {}


def test_uncertain_create_is_not_blindly_retried_and_next_apply_reconciles(config):
    service = Service(); service.lose_create_response = True
    with httpx.Client(transport=httpx.MockTransport(service.handle)) as client:
        with pytest.raises(SchedulerError, match='write may have succeeded'):
            setup(client, config)
        assert len(service.jobs) == 1
        assert sum(method == 'PUT' for method, _ in service.calls) == 1
        setup(client, config)
    assert len(service.jobs) == 2
    assert sum(method == 'PUT' for method, _ in service.calls) == 2


@pytest.mark.parametrize('conflict', ['duplicate', 'different_url'])
def test_conflicting_managed_jobs_are_never_overwritten(config, conflict):
    service = Service()
    wanted = build_jobs('owner/news', config)[0]
    service.jobs[1] = dict(wanted, jobId=1)
    if conflict == 'duplicate': service.jobs[2] = dict(wanted, jobId=2)
    else: service.jobs[1]['url'] = 'https://unrelated.example/keep'
    with httpx.Client(transport=httpx.MockTransport(service.handle)) as client:
        with pytest.raises(SchedulerError): setup(client, config)
    assert not any(method in ('PATCH', 'PUT') for method, _ in service.calls)


def test_readback_detects_wrong_timezone(config):
    service = Service(); service.wrong_readback = True
    with httpx.Client(transport=httpx.MockTransport(service.handle)) as client:
        with pytest.raises(SchedulerError, match='readback mismatch'):
            setup(client, config)


def test_api_error_never_exposes_private_response_or_credentials(config):
    def reject(request):
        return httpx.Response(401, json={'detail': 'synthetic-github-token synthetic-cron-key'})
    with httpx.Client(transport=httpx.MockTransport(reject)) as client:
        with pytest.raises(SchedulerError) as exc: setup(client, config)
    assert 'HTTP 401' in str(exc.value)
    assert 'synthetic-github-token' not in str(exc.value)
    assert 'synthetic-cron-key' not in str(exc.value)


@pytest.mark.parametrize('manual_mode,preparation,enabled', [
    ('check', True, False), ('check', False, False), ('preview', False, True),
    ('send-test', False, True), ('daily', True, True), ('daily', False, False)])
def test_actual_workflow_healthcheck_can_never_generate_or_send(config, monkeypatch, tmp_path,
                                                              manual_mode, preparation, enabled):
    import news_agent.config
    import news_agent.cli
    workflow = yaml.safe_load(Path('.github/workflows/daily-news.yml').read_text())
    steps = workflow['jobs']['briefing']['steps']
    gate = next(step for step in steps if step.get('id') == 'gate')
    script = gate['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    monkeypatch.setattr(news_agent.config, 'load', lambda _: config)
    monkeypatch.setattr(news_agent.cli, 'preparation_due', lambda _: preparation)
    monkeypatch.setenv('EVENT', 'workflow_dispatch')
    monkeypatch.setenv('MODE', manual_mode)
    monkeypatch.setenv('SOURCE_RUN_ID', '')
    output = tmp_path / 'gate'
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    exec(compile(script, 'actual-daily-workflow-gate', 'exec'), {})
    assert f'enabled={str(enabled).lower()}\n' in output.read_text()


@pytest.mark.parametrize('month,utc_hour', [(1, 9), (7, 8)])
def test_external_local_ticks_match_preparation_window_in_both_offsets(config, month, utc_hour):
    from zoneinfo import ZoneInfo
    from news_agent.cli import preparation_due
    config['newsletter']['delivery_enabled'] = True
    job = build_jobs('owner/news', config)[0]
    local = datetime(2026, month, 15, job['schedule']['hours'][0], job['schedule']['minutes'][0],
                     tzinfo=ZoneInfo(job['schedule']['timezone']))
    assert local.astimezone(ZoneInfo('UTC')).hour == utc_hour
    assert preparation_due(config, local)
