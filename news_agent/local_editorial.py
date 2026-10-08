"""Bounded-context editing for a CPU-hosted Chinese-capable local model."""
import copy
import logging
from .editorial import EditorialError, SYSTEM, validate
from .freshness import timestamp

LOG = logging.getLogger(__name__)

STORY_SCHEMA = {
    'event_key': 'same event_key as requested', 'headline': '中立的简体中文标题',
    'category': 'same requested category', 'is_conflict': False,
    'freshness': {'development': '具体的新进展，非旧事重述', 'article_id': 'fresh report ID',
                  'quote': 'exact passage documenting the new development'}, 'article_ids': ['exact requested article IDs'],
    'scores': {'consequence': 4, 'timeliness': 4, 'credibility': 4, 'global_relevance': 4},
    'claims': [{'kind': 'fact', 'text': '用1至2句短句说明主要事实，约40至80个汉字',
                'evidence': [{'article_id': 'exact provided ID', 'quote': 'exact unmodified supporting passage >=15 characters'}]},
               {'kind': 'context', 'text': '用1句短句补充必要背景，约30至60个汉字',
                'evidence': [{'article_id': 'exact provided ID', 'quote': 'exact supporting passage'}]}],
    'cross_check': {'status': 'independent or single_source or not_independent',
                    'note': '中文简短说明核实情况'}}


def generate_local(config, articles, date, model, as_of):
    n = config['newsletter']
    by_id = {a.id: a for a in articles}
    catalog = []
    for article in articles:
        # Ranking needs the lead and relative age; writing/review retain full
        # publication metadata and evidence. Avoid repeating every RSS headline.
        lead = article.evidence
        if lead.startswith(article.title):
            lead = lead[len(article.title):].lstrip('. ')
        catalog.append({'id': article.id, 'title': article.title, 'publisher': article.publisher,
                        'published_age_hours': round((as_of - timestamp(article.published)).total_seconds() / 3600, 2),
                        'excerpt': lead[:config['model'].get('ranking_excerpt_characters', 180)]})
    ranked = model.ask(SYSTEM, {
        'task': 'Group reporting of the same event across languages and select 10–15 highest-impact distinct events. '
                'Do not write summaries yet. Vary category counts with important developments each day, without fixed category quotas; economics and companies must get substantive coverage. '
                'Reject recaps, explainers and old events; include only concrete new developments. Keep a varied mix and avoid technology or conflict dominating. Select no trivial sports, entertainment or personal-interest items. '
                'All IDs must exist. Every ID can occur in only one event. Choose up to 3 useful original reports/event.',
        'preferences': config['editorial'], 'date': date, 'as_of': as_of.isoformat(), 'articles': catalog,
        'schema': {'events': [{'event_key': 'short unique event key', 'category': 'politics/economics/business/technology/world',
                              'article_ids': ['existing IDs'],
                              'scores': {'consequence': 5, 'timeliness': 5, 'credibility': 5, 'global_relevance': 5}}]}})
    events = ranked.get('events', [])
    if not n['min_stories'] <= len(events) <= n['max_stories']:
        raise EditorialError('Local model did not select 10–15 distinct events')
    used = set()
    for event in events:
        ids = event.get('article_ids', [])
        if not 1 <= len(ids) <= 3 or not set(ids) <= by_id.keys() or used.intersection(ids):
            raise EditorialError('Invalid or overlapping local-model event groups')
        used.update(ids)
    edition = {'date': date, 'as_of': as_of.isoformat(), 'stories': []}
    for index, event in enumerate(events, 1):
        LOG.info('Local editorial story=%d/%d event=%s', index, len(events), event.get('event_key'))
        evidence = [by_id[aid].to_dict() for aid in event['article_ids']]
        payload = {'task': 'Write ONE concise Chinese story with 2–3 grounded paragraphs. '
                           'Use approximately 120–220 Chinese characters total, with substantive details and essential context. Omit filler and process commentary. Do not invent background. '
                           'Keep event_key, category, article_ids and scores exactly as given. '
                           'Quotes must be copied exactly from evidence, not translated. Return {"story": {...}}.',
                   'event': event, 'articles': evidence, 'schema': {'story': STORY_SCHEMA}}
        story = None
        single = copy.deepcopy(config)
        single['newsletter'].update(min_stories=1, max_stories=1)
        # One supported repair attempt for malformed structure/quotes, using precise validation evidence.
        for attempt in range(2):
            candidate = model.ask(SYSTEM, payload).get('story', {})
            try:
                if any(candidate.get(k) != event.get(k) for k in ('event_key', 'category', 'article_ids', 'scores')):
                    raise EditorialError('Story must preserve the requested event metadata')
                validate({'date': date, 'as_of': as_of.isoformat(), 'stories': [candidate]}, articles, single, date, enforce_balance=False)
                story = candidate
                break
            except EditorialError as exc:
                if attempt == 1: raise
                payload['validation_error'] = str(exc)
                payload['previous_story'] = candidate
        review = model.ask(SYSTEM, {
            'task': 'Verify this single story against provided source evidence. Check EVERY Chinese assertion, '
                    'dates/numbers, neutral political language, source independence, headline entailment, '
                    'adequate background, Simplified Chinese quality, and a concrete new development during the freshness window. '
                    'No claim may rest on navigation or unrelated recommended links. '
                    'Return {"approved": true/false, "issues": [specific problems]}. Fail closed.',
            'story': story, 'articles': evidence})
        if review.get('approved') is not True or review.get('issues') != []:
            raise EditorialError(f"Local editorial verification failed for {event.get('event_key')}")
        edition['stories'].append(story)
    validate(edition, articles, config, date)
    review = model.ask(SYSTEM, {
        'task': 'Final edition audit: are all events distinct and globally consequential? '
                'Check that multiple descriptions of one event were merged, politics/economics/acquisitions '
                'and technology/business all receive substantive coverage; war/politics does not dominate, '
                'and Chinese reads naturally. Return {"approved": true/false, "issues": [...]}.',
        'preferences': config['editorial'],
        'stories': [{'event_key': s['event_key'], 'headline': s['headline'], 'category': s['category'],
                     'paragraphs': [c['text'] for c in s['claims']]} for s in edition['stories']]})
    if review.get('approved') is not True or review.get('issues') != []:
        raise EditorialError('Local final edition review failed')
    edition.update(review=review, model=config['model']['name'], editorial_mode='local_per_story_review')
    return edition
