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


def test_local_pipeline_reviews_every_story_and_final_edition(config, artifacts):
    articles, edition = artifacts
    config['model']['provider'] = 'ollama'
    events = [{k: s[k] for k in ('event_key', 'category', 'article_ids', 'scores')} for s in edition['stories']]
    class FakeModel:
        calls = 0
        def ask(self, system, payload):
            self.calls += 1
            if self.calls == 1: return {'events': events}
            if self.calls == 22 or self.calls % 2 == 1: return {'approved': True, 'issues': []}
            return {'story': copy.deepcopy(edition['stories'][(self.calls - 2)//2])}
        def close(self): pass
    model = FakeModel()
    result = generate(config, articles, edition['date'], model=model, as_of=datetime.fromisoformat(edition['as_of']))
    assert model.calls == 22 and result['editorial_mode'] == 'local_per_story_review'


def test_preparation_starts_early_but_send_gate_remains_0800(config):
    config['newsletter']['delivery_enabled'] = True
    now = datetime.fromisoformat('2026-07-15T10:45:00+00:00')
    assert preparation_due(config, now) and not schedule_due(config, now)
    assert not preparation_due(config, datetime.fromisoformat('2026-07-15T10:44:00+00:00'))


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
