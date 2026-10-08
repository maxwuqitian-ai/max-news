import copy
from datetime import datetime, timedelta, timezone
import httpx
import pytest
import respx
from news_agent.collect import collect
from news_agent.editorial import validate, EditorialError
from news_agent.freshness import timestamp, verify_send_freshness
from news_agent.render import render


@pytest.mark.parametrize('failure', ['stale', 'future', 'unknown_date', 'no_timezone', 'no_new_development', 'made_up_update'])
def test_rejects_unproven_freshness(config, artifacts, failure):
    articles, edition = artifacts
    a = articles[0]
    if failure == 'stale': a.published = '2026-01-14T11:59:59+00:00'
    elif failure == 'future': a.published = '2026-01-15T12:00:01+00:00'
    elif failure == 'unknown_date': a.published = None
    elif failure == 'no_timezone': a.published = '2026-01-15T11:00:00'
    elif failure == 'no_new_development': edition['stories'][0]['freshness']['development'] = ''
    elif failure == 'made_up_update': edition['stories'][0]['freshness']['quote'] = 'This invented new development does not exist in any supplied publisher evidence.'
    with pytest.raises(EditorialError): validate(edition, articles, config, edition['date'])


def test_politics_cannot_crowd_out_economics_companies_and_technology(config, artifacts):
    articles, edition = artifacts
    for s in edition['stories']: s['category'] = 'politics'
    with pytest.raises(EditorialError, match='coverage'): validate(edition, articles, config, edition['date'])


def test_even_with_section_minima_politics_cannot_dominate(config, artifacts):
    articles, edition = artifacts
    categories = ['politics']*5 + ['economics']*2 + ['business']*2 + ['technology']
    for s, c in zip(edition['stories'], categories): s['category'] = c
    with pytest.raises(EditorialError, match='dominates'): validate(edition, articles, config, edition['date'])


def test_conflicts_are_capped_across_categories(config, artifacts):
    articles, edition = artifacts
    for s in edition['stories'][:3]: s['is_conflict'] = True
    with pytest.raises(EditorialError, match='conflict'): validate(edition, articles, config, edition['date'])


def test_delivery_rechecks_age_after_a_delayed_run(config, artifacts):
    articles, edition = artifacts
    validate(edition, articles, config, edition['date'])
    verify_send_freshness(edition, articles, config, datetime.fromisoformat('2026-01-15T13:00:00+00:00'))
    with pytest.raises(ValueError, match='too old'):
        verify_send_freshness(edition, articles, config, datetime.fromisoformat('2026-01-15T17:00:00+00:00'))
    articles[0].published = '2026-01-14T12:30:00+00:00'
    with pytest.raises(ValueError, match='aged'):
        verify_send_freshness(edition, articles, config, datetime.fromisoformat('2026-01-15T13:00:00+00:00'))


def test_html_and_text_have_matching_sections_and_visible_cutoff(config, artifacts):
    articles, edition = artifacts
    validate(edition, articles, config, edition['date'])
    html, text = render(edition, '测试新闻')
    labels = ['政治与国际关系', '经济与市场', '公司与商业', '科技与AI']
    for output in (html, text):
        positions = [output.index(label) for label in labels]
        assert positions == sorted(positions)
        assert '新闻截止时间' in output and '2026-01-15 07:00' in output
    assert html.count('<section') == 10


@respx.mock
def test_gdelt_requires_and_verifies_publisher_publication_metadata(config):
    config['sources'] = []
    config['gdelt']['publishers'] = {'publisher.example': {'name': 'Fixture', 'family': 'Fixture'}}
    respx.get(config['gdelt']['url']).mock(return_value=httpx.Response(200, json={'articles': [
        {'url': f'https://publisher.example/{key}', 'title': key, 'seendate': '20260115T110000Z'} for key in ('fresh', 'old')]}))
    for key, stamp in [('fresh', '2026-01-15T10:00:00Z'), ('old', '2025-12-01T10:00:00Z')]:
        respx.get(f'https://publisher.example/{key}').mock(return_value=httpx.Response(200,
            text=f'<meta property="article:published_time" content="{stamp}"><p>' + 'Synthetic test article. '*25 + '</p>'))
    with httpx.Client() as client:
        articles, _ = collect(config, datetime(2026,1,15,12,tzinfo=timezone.utc), client)
    assert len(articles) == 1 and articles[0].title == 'fresh'
    assert articles[0].published == '2026-01-15T10:00:00+00:00'


def test_jsonld_uses_article_publication_not_modification_time():
    from news_agent.collect import PublicationParser
    p = PublicationParser()
    p.feed('<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-01-01T11:00:00Z","dateModified":"2026-01-15T11:00:00Z"}</script>')
    assert p.published == datetime(2026,1,1,11,tzinfo=timezone.utc)


@respx.mock
def test_rss_update_cannot_override_stale_publisher_publication(config):
    config['sources'] = [{'name': 'Fixture', 'family': 'Fixture', 'url': 'https://feed.example/rss', 'domains': ['publisher.example']}]
    config['gdelt']['enabled'] = False
    # A long RSS body must not bypass verification of the original timestamp.
    body = 'Synthetic source evidence for testing publication metadata. ' * 30
    feed = ('<rss version="2.0"><channel><item><title>Updated old article</title>'
            '<link>https://publisher.example/old</link><pubDate>Thu, 15 Jan 2026 11:00:00 GMT</pubDate>'
            f'<description>{body}</description></item></channel></rss>')
    respx.get('https://feed.example/rss').mock(return_value=httpx.Response(200, text=feed))
    respx.get('https://publisher.example/old').mock(return_value=httpx.Response(200,
        text='<meta property="article:published_time" content="2026-01-01T11:00:00Z"><p>' + body + '</p>'))
    with httpx.Client() as client:
        articles, _ = collect(config, datetime(2026, 1, 15, 12, tzinfo=timezone.utc), client)
    assert articles == []
