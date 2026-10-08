"""Publisher timestamps and evidence for a genuinely new daily development."""
from datetime import datetime, timedelta, timezone


def timestamp(value):
    if not isinstance(value, str): raise ValueError('Missing publisher timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None: raise ValueError('Timestamp must include a timezone')
    return parsed.astimezone(timezone.utc)


def is_fresh(article, as_of, hours):
    try:
        published = timestamp(article.published)
        return as_of - timedelta(hours=hours) <= published <= as_of
    except ValueError:
        return False


def verify_send_freshness(edition, articles, config, now=None):
    now = now or datetime.now(timezone.utc)
    by_id = {a.id: a for a in articles}
    collected = timestamp(edition.get('as_of'))
    if collected > now or now - collected > timedelta(hours=config['newsletter'].get('max_edition_age_hours', 4)):
        raise ValueError('Edition is too old to send; collect and review a fresh edition')
    for story in edition['stories']:
        aid = story['freshness']['article_id']
        if not is_fresh(by_id[aid], now, config['newsletter']['lookback_hours']):
            raise ValueError('A story aged outside the fresh-news window before delivery')
