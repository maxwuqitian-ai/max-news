import copy
import httpx
import respx
import pytest
from news_agent.editorial import Model, generate, EditorialError
from news_agent.cli import preparation_due, schedule_due
from datetime import datetime


@respx.mock
def test_local_model_needs_no_api_key_and_returns_chinese_json(config, monkeypatch):
    config['model'].update(provider='ollama', api_key_env=None, base_url='http://127.0.0.1:11434', thinking=False)
    monkeypatch.delenv('NEWS_LLM_API_KEY', raising=False)
    route = respx.post('http://127.0.0.1:11434/api/chat').mock(return_value=httpx.Response(200,
        json={'message': {'content': '{"headline":"本地模型中文测试"}'}}))
    model = Model(config['model'])
    try: assert model.ask('test', {'task': 'test'})['headline'] == '本地模型中文测试'
    finally: model.close()
    assert 'authorization' not in route.calls[0].request.headers
    import json
    assert json.loads(route.calls[0].request.content)['think'] is False


@respx.mock
def test_reasoning_output_limit_continues_once_and_preserves_rejection(config):
    import json
    config['model'].update(provider='ollama', api_key_env=None, base_url='http://127.0.0.1:11434', thinking=True)
    route=respx.post('http://127.0.0.1:11434/api/chat').mock(side_effect=[
        httpx.Response(200,json={'done_reason':'length','message':{'thinking':'A number is unsupported.', 'content':'{"approved":'}}),
        httpx.Response(200,json={'message':{'content':'{"approved":false,"issues":["Unsupported number"]}'}})])
    model=Model(config['model'])
    try:
        result=model.ask('Reject unsupported facts.', {'task':'Audit supplied sources'})
    finally: model.close()
    assert result=={'approved':False,'issues':['Unsupported number']}
    assert len(route.calls)==2
    continuation=json.loads(route.calls[1].request.content)
    assert continuation['think'] is False
    assert continuation['messages'][0]['content']=='Reject unsupported facts.'
    assert 'unsupported' in continuation['messages'][-2]['content']


@respx.mock
def test_classification_cache_uses_immutable_source_not_advancing_age(config,tmp_path):
    import json
    from news_agent.selection import classify
    config['model'].update(provider='ollama',api_key_env=None,base_url='http://127.0.0.1:11434',cache_dir=str(tmp_path))
    rating={'category':'economics','genre':'breaking_news','event_key':'synthetic_rate_change',
        'is_conflict':False,'consequence':4,'global_relevance':4}
    route=respx.post('http://127.0.0.1:11434/api/chat').mock(return_value=httpx.Response(200,
        json={'message':{'content':json.dumps({'ratings':{'a0_test':rating}})}}))
    catalog=[{'id':'a0_test','title':'合成测试央行调整利率','publisher':'合成测试媒体',
        'family':'synthetic','published_at':'2026-01-15T11:00:00+00:00','published_age_hours':1}]
    model=Model(config['model'])
    try:
        assert classify(catalog,model,'Classify source data',config)['a0_test']==rating
        catalog[0]['published_age_hours']=2
        assert classify(catalog,model,'Classify source data',config)['a0_test']==rating
        assert len(route.calls)==1
        payload=json.loads(json.loads(route.calls[0].request.content)['messages'][1]['content'])
        assert 'published_age_hours' not in payload['articles'][0]
        assert payload['articles'][0]['published_at']==catalog[0]['published_at']
        catalog[0]['published_at']='2026-01-15T11:30:00+00:00'
        classify(catalog,model,'Classify source data',config)
        assert len(route.calls)==2
    finally: model.close()


@respx.mock
def test_local_schema_constrains_category_names_without_copying_placeholders(config):
    import json
    from news_agent.selection import rating_schema
    config['model'].update(provider='ollama', api_key_env=None, base_url='http://127.0.0.1:11434')
    schema = rating_schema(['a0_title'])
    route = respx.post('http://127.0.0.1:11434/api/chat').mock(return_value=httpx.Response(200,
        json={'message': {'content': '{"events":[]}'}}))
    model = Model(config['model'])
    try: model.ask('test', {'task': 'Select events', 'response_schema': schema})
    finally: model.close()
    request = json.loads(route.calls[0].request.content)
    assert request['format'] == schema
    assert request['format']['properties']['ratings']['properties']['a0_title']['properties']['category']['enum'] == ['politics', 'economics', 'business', 'technology', 'world', 'sports', 'entertainment', 'personal_interest']
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
            if payload['task'].startswith('Rate EVERY'):
                return {'ratings': {a['id']: {'category': edition['stories'][int(a['id'].split('_')[0][1:])]['category'],
                    'genre': 'breaking_news', 'event_key': edition['stories'][int(a['id'].split('_')[0][1:])]['event_key'],
                    'is_conflict': False, 'consequence': 4, 'global_relevance': 4} for a in payload['articles']}}
            if payload['task'].startswith('Audit the selected'):
                return {'checks': {e['event_key']: {'genre': 'breaking_news', 'category': e['category'], 'all_sources_cover_this_event': True,
                    'new_development': True, 'importance_level': 'major_sector', 'duplicate_of': 'none', 'reason': 'Synthetic test assessment'} for e in payload['events']}}
            if payload['task'].startswith('Verify this single story'):
                assert payload['edition_date'] == edition['date']
                assert payload['as_of'] == edition['as_of']
                assert 'story' not in payload
                assert all('evidence' not in a for a in payload['articles'])
                assert payload['published_story']['paragraphs']
                sources = {p['id']: p for p in payload['source_passages']}
                for paragraph in payload['published_story']['paragraphs']:
                    assert 'quote' not in paragraph
                    assert paragraph['citations']
                    for reference in paragraph['citations']:
                        assert sources[reference]['quote']
                        assert sources[reference]['source_id'] == 's0'
                return {'approved': True, 'issues': []}
            if not payload['task'].startswith('Write ONE'): return {'approved': True, 'issues': []}
            story = copy.deepcopy(edition['stories'][self.drafts])
            self.drafts += 1
            story['freshness'].update(article_id='s0', passage_id='p0')
            story['freshness'].pop('quote')
            for claim in story['claims']:
                for ref in claim['evidence']:
                    ref.update(article_id='s0', passage_id='p0'); ref.pop('quote')
            return {'story': story}
        def close(self): pass
    model = FakeModel()
    result = generate(config, articles, edition['date'], model=model, as_of=datetime.fromisoformat(edition['as_of']))
    assert model.calls == 23 and result['editorial_mode'] == 'local_per_story_review'


@pytest.mark.parametrize('start,just_before,target', [
    ('2026-07-15T09:30:00+00:00', '2026-07-15T09:29:00+00:00', '2026-07-15T12:00:00+00:00'),
    ('2026-01-15T10:30:00+00:00', '2026-01-15T10:29:00+00:00', '2026-01-15T13:00:00+00:00')])
def test_preparation_starts_early_but_send_gate_remains_0800(config, start, just_before, target):
    config['newsletter']['delivery_enabled'] = True
    now = datetime.fromisoformat(start)
    assert preparation_due(config, now) and not schedule_due(config, now)
    assert not preparation_due(config, datetime.fromisoformat(just_before))
    assert schedule_due(config, datetime.fromisoformat(target))


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
            if payload['task'].startswith('Rate EVERY'):
                return {'ratings': {a['id']: {'category': edition['stories'][int(a['id'].split('_')[0][1:])]['category'],
                    'genre': 'breaking_news', 'event_key': edition['stories'][int(a['id'].split('_')[0][1:])]['event_key'],
                    'is_conflict': False, 'consequence': 4, 'global_relevance': 4} for a in payload['articles']}}
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


def test_selection_review_cannot_approve_sports_as_company_news(artifacts):
    from news_agent.local_editorial import validate_selection_audit
    event = artifacts[1]['stories'][6]
    check = {'genre': 'breaking_news', 'category': 'sports', 'all_sources_cover_this_event': True, 'new_development': True,
             'importance_level': 'major_sector', 'duplicate_of': 'none', 'reason': 'This concerns a cricket match'}
    with pytest.raises(EditorialError, match='Selection review failed'):
        validate_selection_audit({'checks': {event['event_key']: check}}, [event])


def test_programmatic_selection_groups_duplicates_and_excludes_sports(config):
    from news_agent.selection import select
    catalog = [{'id': f'a{i}', 'title': f'Article {i}', 'family': f'publisher-{i%3}', 'published_age_hours': 1} for i in range(12)]
    categories = ['politics']*3 + ['economics']*3 + ['business']*2 + ['technology']*2 + ['business']*2
    ratings = {a['id']: {'category': categories[i], 'genre': 'breaking_news', 'event_key': f'event_{i}',
               'is_conflict': False, 'consequence': 4, 'global_relevance': 4} for i, a in enumerate(catalog)}
    ratings['a10'].update(event_key='event_6')
    ratings['a11'].update(genre='sports', consequence=5, global_relevance=5)
    events = select(catalog, ratings, config)
    assert len(events) == 10
    assert len({e['event_key'] for e in events}) == 10
    assert 'a11' not in {aid for e in events for aid in e['article_ids']}
    company = next(e for e in events if e['event_key'] == 'event_6')
    assert set(company['article_ids']) == {'a6', 'a10'}


def test_selection_uses_chinese_primary_and_english_corroboration(config):
    from news_agent.selection import select
    catalog = [{'id':f'a{i}','title':f'Article {i}','family':f'publisher-{i}',
                'published_age_hours':2} for i in range(12)]
    categories=['politics']*3+['economics']*3+['business']*2+['technology']*2+['business']*2
    ratings={a['id']:{'category':categories[i],'genre':'breaking_news','event_key':f'event_{i}',
        'is_conflict':False,'consequence':4,'global_relevance':4} for i,a in enumerate(catalog)}
    # An English report is newer, but the published text must remain Chinese.
    catalog[10]['published_age_hours']=1
    ratings['a10']['event_key']='event_6'
    # An English-only event cannot enter this source-preserving edition.
    ratings['a11'].update(consequence=5,global_relevance=5)
    events=select(catalog,ratings,config,eligible_primary={f'a{i}' for i in range(10)})
    assert len(events)==10
    company=next(e for e in events if e['event_key']=='event_6')
    assert company['article_ids']==['a6','a10']
    assert 'a11' not in {aid for e in events for aid in e['article_ids']}


def test_writer_passage_references_resolve_to_original_quotes(artifacts):
    from news_agent.local_editorial import evidence_passages, resolve_story
    articles, edition = artifacts
    source = articles[0]
    passages = {'s0': evidence_passages(source.evidence)}
    story = copy.deepcopy(edition['stories'][0])
    references = [story['freshness']] + [e for c in story['claims'] for e in c['evidence']]
    for ref in references:
        ref.update(article_id='s0', passage_id='p0'); ref.pop('quote')
    story['cross_check']['status'] = 'independent'
    resolved = resolve_story(story, edition['stories'][0], {'s0': source.id}, passages)
    assert resolved['freshness']['quote'] == source.evidence
    assert resolved['cross_check']['status'] == 'single_source'
    story['freshness']['passage_id'] = 'invented'
    with pytest.raises(EditorialError, match='provided passage ID'):
        resolve_story(story, edition['stories'][0], {'s0': source.id}, passages)


def test_company_earnings_and_weather_use_primary_topic():
    from news_agent.selection import primary_category
    assert primary_category('AI chip demand pushes company profits to a record', 'technology') == 'business'
    assert primary_category('Isaias strengthens into the first hurricane', 'economics') == 'world'
    assert primary_category('Industrial profits rise across China', 'economics') == 'economics'


@pytest.mark.parametrize('corrected_review_passes', [True, False])
def test_rejected_story_is_rewritten_and_requires_a_new_review(config, artifacts, corrected_review_passes):
    from news_agent.local_editorial import write_story
    articles, edition = artifacts
    event = edition['stories'][0]
    class RevisingModel:
        drafts = 0
        reviews = 0
        feedback_seen = False
        def ask(self, system, payload):
            if payload['task'].startswith('Write ONE'):
                self.drafts += 1
                if self.drafts == 2:
                    self.feedback_seen = payload['review_issues'] == ['Remove unsupported background']
                story = copy.deepcopy(event)
                for ref in [story['freshness']] + [e for c in story['claims'] for e in c['evidence']]:
                    ref.update(article_id='s0', passage_id='p0'); ref.pop('quote')
                return {'story': story}
            self.reviews += 1
            approved = self.reviews == 2 and corrected_review_passes
            return {'approved': approved, 'issues': [] if approved else ['Remove unsupported background']}
    model = RevisingModel()
    if corrected_review_passes:
        result = write_story(config, articles, edition['date'], model, event, datetime.fromisoformat(edition['as_of']))
        assert result['freshness']['quote'] == articles[0].evidence
    else:
        with pytest.raises(EditorialError, match='failed after revision'):
            write_story(config, articles, edition['date'], model, event, datetime.fromisoformat(edition['as_of']))
    assert model.feedback_seen and model.drafts == model.reviews == 2


@respx.mock
def test_model_checkpoints_require_exact_inputs_and_have_an_expiry(config):
    import json, time
    from pathlib import Path
    config['model'].update(provider='ollama', api_key_env=None)
    route = respx.post('http://127.0.0.1:11434/api/chat').mock(return_value=httpx.Response(200,
        json={'message': {'content': '{"approved":true,"issues":[]}'}}))
    model = Model(config['model'])
    try:
        model.ask('Review', {'task': 'test', 'source': 'Original publisher evidence'})
        model.ask('Review', {'task': 'test', 'source': 'Original publisher evidence'})
        assert route.call_count == 1
        model.ask('Review', {'task': 'test', 'source': 'Changed publisher evidence'})
        model.ask('Changed review rules', {'task': 'test', 'source': 'Original publisher evidence'})
        assert route.call_count == 3
        for p in Path(config['model']['cache_dir']).glob('*.json'):
            entry = json.loads(p.read_text()); entry['created_at'] = time.time()-14401; p.write_text(json.dumps(entry))
        model.ask('Review', {'task': 'test', 'source': 'Original publisher evidence'})
        assert route.call_count == 4
    finally: model.close()


def test_passage_splitting_preserves_abbreviated_subjects():
    from news_agent.local_editorial import evidence_passages
    text = 'Officials made an announcement. U.S. authorities want him kept in Beirut. Additional reporting follows.'
    passages = list(evidence_passages(text).values())
    assert 'U.S. authorities want him kept in Beirut.' in passages
    assert all(p in text for p in passages)


def test_omitting_a_rejected_story_does_not_waive_topic_limits(config):
    from news_agent.local_editorial import balance_verified_stories
    stories = [{'event_key':f'event-{i}', 'category': 'politics' if i < 6 else 'business',
                'is_conflict': False, 'rank_score': 100-i} for i in range(14)]
    balanced = balance_verified_stories(stories, config)
    assert len(balanced) == 13
    assert sum(s['category']=='politics' for s in balanced) <= len(balanced)*.4
    assert 'event-5' not in {s['event_key'] for s in balanced}

def test_rebalance_publisher_excerpts_before_rank_score_exists(config):
    from news_agent.local_editorial import balance_verified_stories
    config['newsletter']['min_stories']=6
    stories=[{'event_key':f'event-{i}','category':'politics' if i<3 else 'business',
        'is_conflict':False,'scores':dict(consequence=1 if i==2 else 4,
            timeliness=4,credibility=4,global_relevance=4)} for i in range(7)]
    result=balance_verified_stories(stories,config)
    assert len(result)==6
    assert 'event-2' not in {s['event_key'] for s in result}
    assert sum(s['category']=='politics' for s in result)<=len(result)*.4


def test_writer_requires_main_claim_support_from_each_provided_report(artifacts):
    from news_agent.local_editorial import evidence_passages, resolve_story, story_schema
    articles, edition = artifacts
    aliases = {'s0':articles[0].id, 's1':articles[1].id}
    passages = {key:evidence_passages(articles[i].evidence) for i,key in enumerate(aliases)}
    event = dict(edition['stories'][0], article_ids=list(aliases.values()))
    story = {'headline':event['headline'], 'freshness': {'article_id':'s0','passage_id':'p0','development':'虚构测试进展'},
             'claims': {kind:{'text':event['claims'][i]['text'],'evidence':{'s0':['p0'],'s1':['p0']}}
                        for i,kind in enumerate(('fact','context'))},
             'cross_check':{'status':'not_independent','note':'仅为合成测试素材。'}}
    result = resolve_story(story,event,aliases,passages)
    assert {r['article_id'] for r in result['claims'][0]['evidence']} == set(aliases.values())
    assert story_schema(aliases,passages)['properties']['story']['properties']['claims']['properties']['fact']['properties']['evidence']['properties']['s1']['minItems'] == 1
    story['claims']['fact']['evidence']['s1'] = []
    with pytest.raises(EditorialError,match='every provided source'):
        resolve_story(story,event,aliases,passages)


@pytest.mark.parametrize('invented', [False, True])
def test_grounded_translation_sees_selected_quotes_only(invented):
    from news_agent.local_editorial import grounded_draft
    passages = {'s0':{'p0':'Officials announced a tax cut.', 'p1':'The law takes effect next month.',
                      'p2':'An unrelated report describes a different event.'}}
    payload = {'edition_date':'2026-10-08','as_of':'2026-10-08T12:00:00+00:00',
               'event':{'event_key':'tax_cut','category':'economics'},
               'articles':[{'id':'s0','publisher':'BBC','passages':passages['s0']}]}
    class FakeModel:
        translations = 0
        def ask(self, system, request):
            if request['task'].startswith('Select evidence'):
                return {'fact':{'s0':['invented' if invented else 'p0']},'context':{'s0':['p1']},
                        'freshness':{'article_id':'s0','passage_id':'p0'},'is_conflict':False,
                        'cross_check':{'status':'single_source','note':'一个报道来源'}}
            self.translations += 1
            assert request['paragraph_evidence'] == {
                'fact':[{'publisher':'BBC','quote':passages['s0']['p0']}],
                'context':[{'publisher':'BBC','quote':passages['s0']['p1']}]}
            assert 'unrelated' not in str(request)
            return {'headline':'税收政策调整','fact':'据BBC报道，当局宣布减税。',
                    'context':'新法下月生效。','development':'当局宣布减税。'}
    model = FakeModel()
    if invented:
        with pytest.raises(EditorialError,match='unavailable passage'):
            grounded_draft(model,payload,{'s0':'actual-id'},passages)
        assert model.translations == 0
    else:
        story = grounded_draft(model,payload,{'s0':'actual-id'},passages)
        assert story['claims']['fact']['evidence'] == {'s0':['p0']}
        assert model.translations == 1
