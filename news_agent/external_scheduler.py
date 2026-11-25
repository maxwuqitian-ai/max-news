"""Provision two private cron-job.org HTTP triggers; never send mail itself."""
import argparse
import json
import os
import re
from zoneinfo import ZoneInfo

import httpx

from .config import load

GITHUB_API = 'https://api.github.com'
CRON_API = 'https://api.cron-job.org'


class SchedulerError(RuntimeError):
    pass


def build_jobs(repository, config, token='<private GitHub Actions token>'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository):
        raise SchedulerError('Invalid GitHub repository name')
    settings = config['newsletter']
    zone = settings['timezone']
    ZoneInfo(zone)
    hour, minute = map(int, settings['target_time'].split(':'))
    target = hour * 60 + minute
    preparation = settings.get('preparation_minutes', 75)
    if not (0 <= hour < 24 and 0 <= minute < 60 and 0 < preparation <= target and target + 15 < 1440):
        raise SchedulerError('Configure a same-day morning preparation window and audit deadline')
    first = target - preparation + min(7, preparation - 1)
    ticks = list(range(first, target, 60))
    ref = config.get('scheduler', {}).get('ref', 'main')
    if not isinstance(ref, str) or not ref.strip():
        raise SchedulerError('Configure a nonempty scheduler ref')

    def job(kind, workflow, hours, minutes, inputs):
        return {
            'title': f'max-news:{repository}:{kind}',
            'url': f'{GITHUB_API}/repos/{repository}/actions/workflows/{workflow}/dispatches',
            'enabled': bool(settings['delivery_enabled']), 'saveResponses': False,
            'requestMethod': 1,  # Official API enum: POST.
            'schedule': {'timezone': zone, 'expiresAt': 0, 'hours': hours, 'minutes': minutes,
                         'mdays': [-1], 'months': [-1], 'wdays': [-1]},
            'notification': {'onFailure': True, 'onFailureCount': 1, 'onSuccess': False,
                             'onDisable': True},
            'extendedData': {
                'headers': {'Authorization': 'Bearer ' + token,
                            'Accept': 'application/vnd.github+json',
                            'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'},
                'body': json.dumps({'ref': ref, 'inputs': inputs}, separators=(',', ':'))},
        }

    return [
        job('prepare', 'daily-news.yml', sorted({t // 60 for t in ticks}),
            sorted({t % 60 for t in ticks}), {'mode': 'daily'}),
        job('audit', 'verify-morning-delivery.yml', [(target + 15) // 60],
            [(target + 15) % 60], {}),
    ]


def request(client, method, url, key, *, body=None, provider):
    try:
        response = client.request(method, url, headers={
            'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
            'Accept': 'application/vnd.github+json' if provider == 'GitHub' else 'application/json',
            'User-Agent': 'max-news-scheduler/1.0'}, json=body)
    except httpx.HTTPError as exc:
        # Never print API response bodies, private headers, or exception URLs.
        suffix = ' Check existing managed jobs before applying again; a write may have succeeded.' if method in ('PUT', 'PATCH') else ''
        raise SchedulerError(provider + ' request failed.' + suffix) from None
    if not 200 <= response.status_code < 300:
        raise SchedulerError(f'{provider} rejected {method}: HTTP {response.status_code}; response omitted')
    if response.status_code == 204 or not response.content:
        return {}
    try:
        result = response.json()
        if not isinstance(result, dict): raise ValueError()
        return result
    except ValueError:
        raise SchedulerError(provider + ' returned invalid JSON; response omitted') from None


def matching_job(jobs, wanted):
    matches = [job for job in jobs if job.get('title') == wanted['title']]
    if len(matches) > 1:
        raise SchedulerError('Duplicate managed job titles; reconcile them in cron-job.org before applying')
    if matches and matches[0].get('url') != wanted['url']:
        raise SchedulerError('Managed job title belongs to a different URL; refusing to overwrite')
    return matches[0] if matches else None


def assert_job(actual, expected):
    for field in ('title', 'url', 'enabled', 'requestMethod', 'saveResponses', 'schedule'):
        if actual.get(field) != expected[field]:
            raise SchedulerError('Managed job readback mismatch in ' + field)
    for field, value in expected['notification'].items():
        if actual.get('notification', {}).get(field) != value:
            raise SchedulerError('Managed job notification readback mismatch')
    headers = {k.lower(): v for k, v in actual.get('extendedData', {}).get('headers', {}).items()}
    if any(headers.get(k.lower()) != v for k, v in expected['extendedData']['headers'].items()):
        raise SchedulerError('Managed private request header readback mismatch; values omitted')
    try:
        if json.loads(actual['extendedData']['body']) != json.loads(expected['extendedData']['body']):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise SchedulerError('Managed dispatch body readback mismatch; values omitted') from None


def configure(client, repository, config, cron_key, dispatch_token, *, apply=False):
    jobs = build_jobs(repository, config, dispatch_token)
    for workflow in ('daily-news.yml', 'verify-morning-delivery.yml'):
        result = request(client, 'GET', f'{GITHUB_API}/repos/{repository}/actions/workflows/{workflow}',
                         dispatch_token, provider='GitHub')
        if result.get('state') != 'active':
            raise SchedulerError('Required GitHub workflow is not active: ' + workflow)
    if apply:
        # Tests Actions write access with a mode that cannot generate or send.
        request(client, 'POST', jobs[0]['url'], dispatch_token, provider='GitHub',
                body={'ref': config.get('scheduler', {}).get('ref', 'main'), 'inputs': {'mode': 'check'}})
    listing = request(client, 'GET', CRON_API + '/jobs', cron_key, provider='cron-job.org')
    if listing.get('someFailed') is not False or not isinstance(listing.get('jobs'), list):
        raise SchedulerError('Incomplete scheduler job listing; refusing writes or readiness claim')
    existing = listing['jobs']
    # Preflight every title before writing either job.
    matches = [matching_job(existing, wanted) for wanted in jobs]
    summary = []
    for wanted, matched in zip(jobs, matches):
        if matched:
            job_id = matched.get('jobId')
            if type(job_id) is not int or job_id <= 0:
                raise SchedulerError('Invalid managed job ID')
            if apply:
                request(client, 'PATCH', f'{CRON_API}/jobs/{job_id}', cron_key,
                        body={'job': wanted}, provider='cron-job.org')
        elif apply:
            created = request(client, 'PUT', CRON_API + '/jobs', cron_key,
                              body={'job': wanted}, provider='cron-job.org')
            job_id = created.get('jobId')
            if type(job_id) is not int or job_id <= 0:
                raise SchedulerError('Creation response lacks job ID; reconcile scheduler before reapplying')
        else:
            raise SchedulerError('Managed job is missing; run apply after reviewing the plan')
        detail = request(client, 'GET', f'{CRON_API}/jobs/{job_id}', cron_key, provider='cron-job.org')
        assert_job(detail.get('job', {}), wanted)
        summary.append({'job_id': job_id, 'title': wanted['title'], 'enabled': wanted['enabled'],
                        'timezone': wanted['schedule']['timezone'], 'hours': wanted['schedule']['hours'],
                        'minutes': wanted['schedule']['minutes']})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'apply', 'verify'], default='plan', nargs='?')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', 'maxwuqitian-ai/max-news'))
    args = parser.parse_args(argv)
    try:
        config = load(args.config)
        if args.action == 'plan':
            # No credentials or HTTP requests are needed to inspect the plan.
            print(json.dumps({'action': 'plan', 'applied': False,
                'jobs': build_jobs(args.repository, config)}, ensure_ascii=False, indent=2))
            return 0
        missing = [name for name in ('CRONJOB_API_KEY', 'NEWS_DISPATCH_TOKEN') if not os.environ.get(name)]
        if missing:
            raise SchedulerError('Missing GitHub Repository secrets: ' + ', '.join(missing))
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            summary = configure(client, args.repository, config, os.environ['CRONJOB_API_KEY'],
                os.environ['NEWS_DISPATCH_TOKEN'], apply=args.action == 'apply')
        print(json.dumps({'verified_jobs': summary, 'email_sent': False}, ensure_ascii=False, indent=2))
        return 0
    except SchedulerError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print('Scheduler setup failed type=' + type(exc).__name__ + '; details omitted')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
