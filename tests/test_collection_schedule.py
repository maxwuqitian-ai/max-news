from datetime import datetime, timezone
import httpx
import pytest
import respx
from news_agent.cli import schedule_due
from news_agent.collect import allowed, canonical_url, collect, preliminary_groups, Article


@pytest.mark.parametrize('when,expected', [
    ('2026-01-15T12:59:00+00:00', False), ('2026-01-15T13:00:00+00:00', True),
    ('2026-07-15T11:59:00+00:00', False), ('2026-07-15T12:00:00+00:00', True),
    ('2026-03-08T12:00:00+00:00', True), ('2026-11-01T13:00:00+00:00', True),
    ('2026-07-15T16:00:00+00:00', False)])
def test_dst_and_late_runner_window(config, when, expected):
    config['newsletter']['delivery_enabled'] = True
    assert schedule_due(config, datetime.fromisoformat(when)) is expected


def test_disabled_schedule_is_noop(config):
    assert not schedule_due(config, datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc))


def test_url_normalization_and_domain_safety():
    assert canonical_url('https://bbc.com/news/a?utm_source=x&id=2#fragment') == 'https://bbc.com/news/a?id=2'
    assert allowed('https://www.bbc.com/a', ['bbc.com'])
    assert not allowed('https://bbc.com.evil.example/a', ['bbc.com'])
    with pytest.raises(ValueError): canonical_url('http://bbc.com/a')
    with pytest.raises(ValueError): canonical_url('https://user:password@bbc.com/a')


@respx.mock
def test_feed_date_filter_and_canonical_dedup(config):
    config['sources'] = [{'name': 'Test', 'family': 'Test', 'url': 'https://feed.example/rss', 'domains': ['publisher.example']}]
    config['gdelt']['enabled'] = False
    description = 'Synthetic feed evidence for an imaginary event used only for testing collection and normalization. ' * 2
    entries = ''.join(f'<item><title>Fixture {i}</title><link>{url}</link><pubDate>{date}</pubDate><description>{description}</description></item>' for i, (url, date) in enumerate([
        ('https://publisher.example/a?utm_source=x', 'Thu, 15 Jan 2026 11:00:00 GMT'),
        ('https://publisher.example/a', 'Thu, 15 Jan 2026 11:00:00 GMT'),
        ('https://publisher.example/stale', 'Thu, 01 Jan 2026 11:00:00 GMT'),
        ('https://publisher.example/future', 'Thu, 16 Jan 2026 11:00:00 GMT'),
        ('https://evil.example/not-a-publisher', 'Thu, 15 Jan 2026 11:00:00 GMT')]))
    respx.get('https://feed.example/rss').mock(return_value=httpx.Response(200, text=f'<rss version="2.0"><channel>{entries}</channel></rss>'))
    respx.get('https://publisher.example/a').mock(return_value=httpx.Response(403))
    with httpx.Client() as client:
        articles, failures = collect(config, datetime(2026,1,15,12,tzinfo=timezone.utc), client)
    assert len(articles) == 1 and articles[0].url == 'https://publisher.example/a'
    assert not failures


@respx.mock
def test_unavailable_feed_is_reported(config):
    config['sources'] = [{'name': 'Unavailable', 'url': 'https://feed.example/rss'}]
    config['gdelt']['enabled'] = False
    respx.get('https://feed.example/rss').mock(return_value=httpx.Response(403))
    with httpx.Client() as client: articles, failures = collect(config, client=client)
    assert not articles and failures[0]['source'] == 'Unavailable'


@respx.mock
def test_gdelt_without_publisher_date_is_excluded(config):
    config['sources'] = []
    config['gdelt']['publishers'] = {'publisher.example': {'name': 'Test', 'family': 'Test'}}
    respx.get(config['gdelt']['url']).mock(return_value=httpx.Response(200, json={'articles': [
        {'url': 'https://publisher.example/a', 'title': 'Synthetic GDELT test', 'seendate': '20260115T110000Z'}]}))
    respx.get('https://publisher.example/a').mock(return_value=httpx.Response(200, text='<p>' + 'Synthetic article evidence. '*30 + '</p>'))
    with httpx.Client() as client:
        articles, _ = collect(config, datetime(2026,1,15,12,tzinfo=timezone.utc), client)
    assert articles == []


@respx.mock
def test_cross_domain_page_redirect_is_rejected(config):
    from news_agent.collect import page_evidence
    respx.get('https://publisher.example/a').mock(return_value=httpx.Response(302, headers={'location': 'https://evil.example/a'}))
    with httpx.Client() as client, pytest.raises(ValueError, match='outside publisher'):
        page_evidence(client, 'https://publisher.example/a', ['publisher.example'])


def test_lexical_event_groups(artifacts):
    articles, _ = artifacts
    assert len(preliminary_groups(articles[:1])) == 1
    articles[1].title = articles[0].title
    assert preliminary_groups(articles[:2]) == [[articles[0].id, articles[1].id]]
