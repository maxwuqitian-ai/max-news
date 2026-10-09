import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from news_agent.editorial import Model
from news_agent.selection import classify


@respx.mock
def test_retry_classifies_only_new_articles_even_when_aliases_move(config, tmp_path):
    config['model'].update(provider='ollama', api_key_env=None,
        base_url='http://127.0.0.1:11434', cache_dir=str(tmp_path))
    rating = dict(category='economics', genre='breaking_news',
        event_key='test_rate_decision', is_conflict=False, consequence=4, global_relevance=4)

    def reply(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        return httpx.Response(200, json={'message': {'content': json.dumps(
            {'ratings': {a['id']: rating for a in payload['articles']}})}})

    route = respx.post('http://127.0.0.1:11434/api/chat').mock(side_effect=reply)
    old = dict(id='a0_old', source_id='publisher-url-hash', title='合成央行利率决定',
        published_at='2026-10-09T09:00:00+00:00', published_age_hours=1,
        publisher='Synthetic', family='Synthetic', excerpt='Synthetic evidence, not news.')
    model = Model(config['model'])
    try:
        classify([old], model, 'Classify only supplied reporting', config)
        moved = dict(old, id='a1_old', published_age_hours=2)
        new = dict(old, id='a0_new', source_id='new-url-hash', title='另一合成央行决定')
        result = classify([new, moved], model, 'Classify only supplied reporting', config)
        assert set(result) == {'a0_new', 'a1_old'}
        payload = json.loads(json.loads(route.calls[-1].request.content)['messages'][1]['content'])
        assert [a['id'] for a in payload['articles']] == ['a0_new']
        assert payload['known_events'] == {'test_rate_decision': moved['title']}
        assert len(route.calls) == 2
        # Changed reporting must invalidate the old assessment, despite the URL.
        moved['excerpt'] = 'The publisher corrected the earlier evidence.'
        classify([moved], model, 'Classify only supplied reporting', config)
        assert len(route.calls) == 3
        # Neither a changed model nor changed classification policy can inherit it.
        config['model']['name'] = 'different-model'
        classify([moved], model, 'Classify only supplied reporting', config)
        classify([moved], model, 'Changed classification policy', config)
        assert len(route.calls) == 5
    finally:
        model.close()


@respx.mock
@pytest.mark.parametrize('damage', ['expired', 'invalid'])
def test_expired_or_invalid_assessment_is_recomputed(config, tmp_path, damage):
    import time
    config['model'].update(provider='ollama', api_key_env=None,
        base_url='http://127.0.0.1:11434', cache_dir=str(tmp_path))
    rating = dict(category='business', genre='breaking_news', event_key='synthetic_acquisition',
        is_conflict=False, consequence=4, global_relevance=4)
    route = respx.post('http://127.0.0.1:11434/api/chat').mock(return_value=httpx.Response(
        200, json={'message': {'content': json.dumps({'ratings': {'a0': rating}})}}))
    model = Model(config['model'])
    article = dict(id='a0', title='合成并购测试', published_at='2026-10-09T09:00:00+00:00',
        published_age_hours=1)
    try:
        classify([article], model, 'Source-only classification', config)
        path = next(tmp_path.glob('rating-*.json'))
        entry = json.loads(path.read_text())
        if damage == 'expired':
            entry['created_at'] = time.time() - 20000
        else:
            entry['rating']['consequence'] = 'unverified'
        path.write_text(json.dumps(entry))
        for cached_response in tmp_path.glob('[a-f0-9]*.json'):
            cached_response.unlink()
        classify([article], model, 'Source-only classification', config)
        assert len(route.calls) == 2
    finally:
        model.close()


def test_ready_edition_wakes_at_target_without_thirty_second_overshoot(config, monkeypatch):
    from news_agent import cli
    clock = [datetime(2026, 10, 10, 11, 59, 50, tzinfo=timezone.utc)]
    sleeps = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz or timezone.utc)

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += timedelta(seconds=seconds)

    config['newsletter']['delivery_enabled'] = True
    monkeypatch.setattr(cli, 'datetime', Clock)
    monkeypatch.setattr(cli.time, 'sleep', sleep)
    cli.wait_for_send_window(config)
    assert sleeps == [10]
    assert clock[0] == datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize('second_approved', [True, False])
def test_targeted_final_omission_requires_all_gates_and_a_new_review(config, artifacts, second_approved):
    from news_agent.local_editorial import finish_review, FinalReviewError
    articles, edition = artifacts
    config['newsletter']['min_stories'] = 8
    from news_agent.editorial import validate
    validate(edition, articles, config, edition['date'])

    class Reviewer:
        calls = 0
        def ask(self, system, payload):
            self.calls += 1
            if self.calls == 1:
                return {'approved': False, 'issues': ['synthetic-6: unsupported company claim']}
            assert len(payload['stories']) == 9
            assert 'synthetic-6' not in {s['event_key'] for s in payload['stories']}
            return {'approved': second_approved, 'issues': [] if second_approved else
                ['synthetic-5: another unsupported claim']}

    model = Reviewer()
    if second_approved:
        review = finish_review(edition, articles, config, model,
            datetime.fromisoformat(edition['as_of']), True)
        assert review == {'approved': True, 'issues': []}
    else:
        with pytest.raises(FinalReviewError):
            finish_review(edition, articles, config, model,
                datetime.fromisoformat(edition['as_of']), True)
    assert model.calls == 2


def test_final_repair_cannot_override_minimum_count(config, artifacts):
    from news_agent.local_editorial import finish_review
    from news_agent.editorial import EditorialError
    articles, edition = artifacts
    from news_agent.editorial import validate
    validate(edition, articles, config, edition['date'])

    class Reviewer:
        calls = 0
        def ask(self, system, payload):
            self.calls += 1
            return {'approved': False, 'issues': ['synthetic-6: unsupported claim']}

    model = Reviewer()
    with pytest.raises(EditorialError, match='10'):
        finish_review(edition, articles, config, model, datetime.fromisoformat(edition['as_of']), True)
    assert model.calls == 1
    assert len(edition['stories']) == 10


@respx.mock
def test_report_comparison_reuses_unchanged_evidence_but_rejects_a_new_conflict(config, tmp_path):
    import copy
    from news_agent.collect import Article
    from news_agent.editorial import EditorialError
    from news_agent.publisher_excerpt import compile_story, check_reports
    title = '合成测试银行调整利率'
    excerpt = '这是虚构的合成测试素材，银行宣布将利率上调0.25个百分点，所有数字仅为测试使用。'
    primary = Article('main', title, 'https://synthetic.example/main', '合成媒体', 'synthetic',
        '2026-01-15T11:00:00+00:00', title + '. ' + excerpt,
        '2026-01-15T12:00:00+00:00', 'rss', publisher_excerpt=excerpt)
    secondary = copy.deepcopy(primary)
    secondary.id = 'second'
    secondary.publisher = '另一合成媒体'
    secondary.family = 'other-synthetic'
    secondary.url = 'https://other-synthetic.example/second'
    event = dict(event_key='synthetic_rate_change', category='economics', is_conflict=False,
        article_ids=['main', 'second'], scores=dict(consequence=4, timeliness=4,
        credibility=4, global_relevance=4))
    story = compile_story(event, [primary, secondary])
    config['model'].update(provider='ollama', api_key_env=None,
        base_url='http://127.0.0.1:11434', cache_dir=str(tmp_path))

    def reply(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        consistent = not any('0.50' in report['excerpt'] for report in payload['reports'])
        return httpx.Response(200, json={'message': {'content': json.dumps(
            {'consistent': consistent, 'issues': [] if consistent else ['Conflicting rate figures']})}})

    route = respx.post('http://127.0.0.1:11434/api/chat').mock(side_effect=reply)
    model = Model(config['model'])
    try:
        for hour in (12, 13):
            check_reports(story, [primary, secondary], model, '2026-01-15',
                datetime(2026, 1, 15, hour, tzinfo=timezone.utc))
        assert len(route.calls) == 1
        secondary.publisher_excerpt = excerpt.replace('0.25', '0.50')
        secondary.evidence = title + '. ' + secondary.publisher_excerpt
        for hour in (13, 14):
            with pytest.raises(EditorialError, match='Conflicting rate figures'):
                check_reports(story, [primary, secondary], model, '2026-01-15',
                    datetime(2026, 1, 15, hour, tzinfo=timezone.utc))
        assert len(route.calls) == 2
    finally:
        model.close()


def test_early_preparation_excludes_sources_expiring_just_after_send_target(config, monkeypatch):
    from news_agent import cli
    from news_agent.collect import Article
    from news_agent.editorial import EditorialError
    now = datetime(2026, 10, 10, 8, 40, tzinfo=timezone.utc)  # 04:40 New York

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz or timezone.utc)

    articles = [Article(key, '合成时效测试', 'https://synthetic.example/' + key,
        'Synthetic', 'synthetic', published, 'Synthetic evidence, not news.',
        now.isoformat(), 'rss') for key, published in [
            ('expires_0820', '2026-10-09T12:20:00+00:00'),
            ('fresh_at_0845', '2026-10-09T12:50:00+00:00')]]
    captured = []

    def stop_before_writing(config, selected, edition_date, as_of):
        captured.extend(a.id for a in selected)
        raise EditorialError('Synthetic collection test stops before writing or mailing')

    config['newsletter']['delivery_enabled'] = True
    monkeypatch.setattr(cli, 'datetime', Clock)
    monkeypatch.setattr(cli.configuration, 'load', lambda _: config)
    monkeypatch.setattr(cli, 'already_attempted', lambda *_: None)
    monkeypatch.setattr(cli, 'collect', lambda *_: (articles, []))
    monkeypatch.setattr(cli, 'generate', stop_before_writing)
    assert cli.main(['run']) == 1
    assert captured == ['fresh_at_0845']
