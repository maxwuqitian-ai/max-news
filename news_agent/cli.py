import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo
from . import config as configuration
from .collect import Article, collect
from .delivery import atomic_json, deliver, already_attempted, DeliveryError
from .editorial import EditorialError, generate, validate
from .render import write
from .freshness import verify_send_freshness, is_fresh
from .weather import forecast

LOG = logging.getLogger(__name__)

def expected_send_time(config, now):
    local = now.astimezone(ZoneInfo(config['newsletter']['timezone']))
    hour, minute = map(int, config['newsletter']['target_time'].split(':'))
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return max(now, target.astimezone(timezone.utc))


def schedule_due(config, now=None):
    n = config['newsletter']
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(n['timezone']))
    hour, minute = map(int, n['target_time'].split(':'))
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Send at the configured local target; allow delayed runners within four hours.
    return n['delivery_enabled'] and target <= local < target + timedelta(hours=4)


def preparation_due(config, now=None):
    n = config['newsletter']
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(n['timezone']))
    hour, minute = map(int, n['target_time'].split(':'))
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return n['delivery_enabled'] and target - timedelta(minutes=n.get('preparation_minutes', 75)) <= local < target + timedelta(hours=4)


def wait_for_send_window(config):
    while not schedule_due(config):
        if not preparation_due(config):
            raise DeliveryError('Preparation finished outside the valid send window')
        time.sleep(30)


def read_artifacts(root, config, expected_date):
    articles = [Article(**a) for a in json.loads((root / 'articles.json').read_text())]
    edition = json.loads((root / 'edition.json').read_text())
    if edition.get('review') != {'approved': True, 'issues': []}:
        raise EditorialError('Only an editorially reviewed edition can be sent')
    return validate(edition, articles, config, expected_date)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Source-grounded Chinese daily news briefing')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('command', choices=['collect', 'preview', 'send-test', 'run', 'due'])
    parser.add_argument('--test-id', help='Unique manual test identity; reuse prevents duplicate tests')
    args = parser.parse_args(argv)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    try:
        config = configuration.load(args.config)
        now = datetime.now(timezone.utc)
        edition_date = now.astimezone(ZoneInfo(config['newsletter']['timezone'])).date().isoformat()
        if args.command == 'due':
            print('true' if schedule_due(config, now) else 'false')
            return 0
        if args.command == 'run' and not preparation_due(config, now):
            LOG.info('Outside delivery window or delivery disabled; no email sent')
            return 0
        if args.command == 'run':
            previous = already_attempted(config, edition_date)
            if previous:
                if previous['status'] != 'sent':
                    raise DeliveryError('Previous daily send is uncertain; manual reconciliation required')
                LOG.info('Daily edition already sent; skipping collection and model calls')
                return 0
        root = Path(config['newsletter']['output_dir'])
        root.mkdir(parents=True, exist_ok=True)
        if args.command == 'send-test':
            if not args.test_id: parser.error('send-test requires --test-id')
            edition = read_artifacts(root, config, edition_date)
        else:
            articles, failures = collect(config, now)
            if args.command in ('run','preview'):
                # Preparing early must not admit reports that will be stale at
                # the intended delivery time. Sending still checks actual time.
                cutoff = max(expected_send_time(config, now) if args.command == 'run' else now,
                             now + timedelta(minutes=config['newsletter'].get('freshness_buffer_minutes',0)))
                articles = [a for a in articles if is_fresh(a, cutoff, config['newsletter']['lookback_hours'])]
            atomic_json(root / 'articles.json', [a.to_dict() for a in articles])
            atomic_json(root / 'collection-report.json', {'retrieved_at': now.isoformat(), 'count': len(articles), 'failures': failures})
            LOG.info('Collection completed articles=%d unavailable_sources=%d', len(articles), len(failures))
            if args.command == 'collect':
                return 0 if articles else 1
            edition = generate(config, articles, edition_date, as_of=now)
            atomic_json(root / 'edition.json', edition)
        if args.command == 'run':
            LOG.info('Edition ready; waiting for the local send window if necessary')
            wait_for_send_window(config)
        # Refresh weather after any scheduled wait, so the header reflects send time.
        edition['weather'] = forecast(config)
        atomic_json(root / 'edition.json', edition)
        html, text = write(edition, config['newsletter']['subject'], root, test=args.command != 'run', section_order=config['editorial']['section_order'])
        if args.command in ('send-test', 'run'):
            if args.command == 'send-test':
                articles = [Article(**a) for a in json.loads((root / 'articles.json').read_text())]
            verify_send_freshness(edition, articles, config)
            deliver(config, html, text, edition_date, test_id=args.test_id if args.command == 'send-test' else None)
        return 0
    except Exception as exc:
        # Response bodies, request headers and credential values must never enter logs.
        LOG.error('Operation failed type=%s', type(exc).__name__)
        if isinstance(exc, (EditorialError, DeliveryError, FileNotFoundError, ValueError)):
            LOG.error('%s', str(exc))
        return 1


if __name__ == '__main__': sys.exit(main())
