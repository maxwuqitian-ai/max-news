import copy
import httpx
import respx
import pytest
from news_agent.editorial import Model, generate, EditorialError
from news_agent.cli import preparation_due, schedule_due
from datetime import datetime


@respx.mock
def test_local_model_needs_no_api_key_and_returns_chinese_json(config, monkeypatch):
    config['model'].update(provider='ollama', api_key_env=None, base_url='http://127.0.0.1:11434')
    monkeypatch.delenv('NEWS_LLM_API_KEY', raising=False)
    route = respx.post('http://127.0.0.1:11434/api/chat').mock(return_value=httpx.Response(200,
        json={'message': {'content': '{"headline":"本地模型中文测试"}'}}))
    model = Model(config['model'])
    try: assert model.ask('test', {'task': 'test'})['headline'] == '本地模型中文测试'
    finally: model.close()
    assert 'authorization' not in route.calls[0].request.headers


@respx.mock
def test_local_schema_constrains_category_names_without_copying_placeholders(config):
    import json
    from news_agent.local_editorial import selection_schema
    config['model'].update(provider='ollama', api_key_env=None, base_url='http://127.0.0.1:11434')
    schema = selection_schema({'a0': 'original-id'}, 10, 15)
    route = respx.post('http://127.0.0.1:11434/api/chat').mock(return_value=httpx.Response(200,
        json={'message': {'content': '{"events":[]}'}}))
    model = Model(config['model'])
    try: model.ask('test', {'task': 'Select events', 'response_schema': schema})
    finally: model.close()
    request = json.loads(route.calls[0].request.content)
    assert request['format'] == schema
    assert request['format']['properties']['events']['items']['properties']['category']['enum'] == ['politics', 'economics', 'business', 'technology', 'world']
    assert 'response_schema' not in request['messages'][1]['content']


def test_local_pipeline_reviews_every_story_and_final_edition(config, artifacts):
    articles, edition = artifacts
    config['model']['provider'] = 'ollama'
    events = [dict({k: s[k] for k in ('event_key', 'category', 'scores')}, article_ids=[f'a{i}']) for i, s in enumerate(edition['stories'])]
    class FakeModel:
        calls = 0
        drafts = 0
        def ask(self, system, payload):
            self.calls += 1
            if payload['task'].startswith('Group reporting'):
                return {'events': [dict(e, article_ids=[payload['articles'][i]['id']]) for i, e in enumerate(events)]}
            if not payload['task'].startswith('Write ONE'): return {'approved': True, 'issues': []}
            story = copy.deepcopy(edition['stories'][self.drafts])
            self.drafts += 1
            story['freshness']['article_id'] = 's0'
            for claim in story['claims']:
                for ref in claim['evidence']: ref['article_id'] = 's0'
            return {'story': story}
        def close(self): pass
    model = FakeModel()
    result = generate(config, articles, edition['date'], model=model, as_of=datetime.fromisoformat(edition['as_of']))
    assert model.calls == 23 and result['editorial_mode'] == 'local_per_story_review'


def test_preparation_starts_early_but_send_gate_remains_0800(config):
    config['newsletter']['delivery_enabled'] = True
    now = datetime.fromisoformat('2026-07-15T10:00:00+00:00')
    assert preparation_due(config, now) and not schedule_due(config, now)
    assert not preparation_due(config, datetime.fromisoformat('2026-07-15T09:59:00+00:00'))


def test_static_real_sample_has_matching_citations_and_original_urls(config):
    import json
    from pathlib import Path
    from news_agent.collect import Article
    from news_agent.editorial import validate
    articles = [Article(**a) for a in json.loads(Path('samples/evidence.json').read_text())]
    edition = json.loads(Path('samples/edition.json').read_text())
    validate(edition, articles, config, edition['date'])
    assert len(edition['stories']) == 12
    assert len(articles) == 13
    assert edition['editorial_mode'] == 'manually_curated_source_audit'
    assert len({a.url for a in articles}) == 13


def test_local_rejects_mismatched_selection_before_writing(config, artifacts):
    articles, edition = artifacts
    config['model']['provider'] = 'ollama'
    events = [dict({k: s[k] for k in ('event_key', 'category', 'scores')}, article_ids=[f'a{i}']) for i, s in enumerate(edition['stories'])]
    class ModelRejectingSelection:
        drafts = 0
        def ask(self, system, payload):
            if payload['task'].startswith('Group reporting'):
                return {'events': [dict(e, article_ids=[payload['articles'][i]['id']]) for i, e in enumerate(events)]}
            if payload['task'].startswith('Write ONE'): self.drafts += 1
            return {'approved': False, 'issues': ['Event key does not match the actual source title']}
        def close(self): pass
    model = ModelRejectingSelection()
    with pytest.raises(EditorialError, match='Selection review failed'):
        generate(config, articles, edition['date'], model=model, as_of=datetime.fromisoformat(edition['as_of']))
    assert model.drafts == 0


def test_local_rejects_invented_evidence_reference(artifacts):
    from news_agent.local_editorial import resolve_story
    _, edition = artifacts
    story = copy.deepcopy(edition['stories'][0])
    story['freshness']['article_id'] = 'invented'
    with pytest.raises(EditorialError, match='provided short source IDs'):
        resolve_story(story, story, {'s0': 'article-0'})


def test_early_collection_uses_target_time_to_exclude_reports_stale_at_delivery(config, artifacts):
    from dataclasses import replace
    from news_agent.cli import expected_send_time
    from news_agent.freshness import is_fresh
    now = datetime.fromisoformat('2026-01-15T11:00:00+00:00')  # 06:00 New York
    target = expected_send_time(config, now)
    assert target == datetime.fromisoformat('2026-01-15T13:00:00+00:00')
    article = replace(artifacts[0][0], published='2026-01-14T12:00:00+00:00')
    assert is_fresh(article, now, 24)
    assert not is_fresh(article, target, 24)
    late = datetime.fromisoformat('2026-01-15T14:00:00+00:00')
    assert expected_send_time(config, late) == late
