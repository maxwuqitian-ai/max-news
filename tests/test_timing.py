import pytest

from news_agent.delivery import delivery_key
from news_agent.timing import verify_delivery_time


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
