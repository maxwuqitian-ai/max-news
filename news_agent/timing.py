"""Read-only proof of a daily send's timing; never initiates delivery."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .delivery import delivery_key


def verify_delivery_time(ledger, recipient, edition_date, config):
    record = ledger.get(delivery_key(recipient, edition_date))
    if not record or record.get('status') != 'sent':
        raise ValueError('No confirmed daily send for this date and recipient')
    sent = datetime.fromisoformat(record['sent_at'])
    if sent.tzinfo is None:
        raise ValueError('Send timestamp must include a timezone')
    zone = ZoneInfo(config['newsletter']['timezone'])
    hour, minute = map(int, config['newsletter']['target_time'].split(':'))
    target = datetime.fromisoformat(edition_date).replace(
        hour=hour, minute=minute, tzinfo=zone)
    delay = sent - target
    if not timedelta(0) <= delay <= timedelta(seconds=60):
        raise ValueError(
            f'Daily send at {sent.astimezone(zone).isoformat()} missed '
            f'{target.isoformat()} (delay {delay.total_seconds():.0f} seconds)')
    return record
