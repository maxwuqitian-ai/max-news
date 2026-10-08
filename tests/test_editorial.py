import copy
import pytest
from news_agent.editorial import EditorialError, generate, validate
from news_agent.render import render


def test_validates_citations_and_renders_both_formats(config, artifacts):
    articles, edition = artifacts
    result = validate(edition, articles, config, edition['date'])
    html, text = render(result, '全球每日新闻', test=True)
    assert 'lang="zh-Hans"' in html and 'viewport' in html
    assert html.count('<section') == 10 and '晨间样刊' in text
    for a in articles:
        assert a.url in html and a.url in text
    assert '<script>' not in html


@pytest.mark.parametrize('mutation', ['fabricated_quote', 'unknown_source', 'duplicate_event', 'duplicate_article',
    'too_few', 'too_many', 'bad_date', 'english', 'false_independence', 'uncited', 'technology_overflow', 'bad_score'])
def test_rejects_invalid_editions(config, artifacts, mutation):
    articles, edition = artifacts
    s = edition['stories'][0]
    if mutation == 'fabricated_quote': s['claims'][0]['evidence'][0]['quote'] = 'A made-up quote that was never in the source.'
    elif mutation == 'unknown_source': s['article_ids'] = ['invented']
    elif mutation == 'duplicate_event': edition['stories'][1]['event_key'] = s['event_key']
    elif mutation == 'duplicate_article': edition['stories'][1]['article_ids'] = s['article_ids']
    elif mutation == 'too_few': edition['stories'].pop()
    elif mutation == 'too_many': edition['stories'] *= 2
    elif mutation == 'bad_date': edition['date'] = '2025-01-15'
    elif mutation == 'english': s['headline'] = 'English only'
    elif mutation == 'false_independence': s['cross_check']['status'] = 'independent'
    elif mutation == 'uncited': s['claims'][0]['evidence'] = []
    elif mutation == 'technology_overflow':
        for item in edition['stories'][:6]: item['category'] = 'technology'
    elif mutation == 'bad_score': s['scores']['credibility'] = 6
    with pytest.raises(EditorialError): validate(edition, articles, config, '2026-01-15')


def test_separate_review_can_reject_unsupported_copy(config, artifacts):
    articles, edition = artifacts
    class FakeModel:
        calls = 0
        def ask(self, system, payload):
            self.calls += 1
            return edition if self.calls == 1 else {'approved': False, 'issues': ['Unsupported translation']}
        def close(self): pass
    with pytest.raises(EditorialError, match='verification failed'):
        generate(config, articles, edition['date'], model=FakeModel(), as_of=__import__('datetime').datetime.fromisoformat(edition['as_of']))


def test_successful_generation_requires_review(config, artifacts):
    articles, edition = artifacts
    class FakeModel:
        calls = 0
        def ask(self, system, payload):
            self.calls += 1
            return edition if self.calls == 1 else {'approved': True, 'issues': []}
        def close(self): pass
    result = generate(config, articles, edition['date'], model=FakeModel(), as_of=__import__('datetime').datetime.fromisoformat(edition['as_of']))
    assert result['review']['approved'] is True


def test_renderer_escapes_source_and_generated_html(config, artifacts):
    articles, edition = artifacts
    validate(edition, articles, config, edition['date'])
    edition['stories'][0]['headline'] += '<script>alert(1)</script>'
    html, _ = render(edition, '测试')
    assert '<script>' not in html and '&lt;script&gt;' in html
