"""Bounded-context editing for a CPU-hosted Chinese-capable local model."""
import copy
import logging
from .editorial import EditorialError, SYSTEM, validate
from .freshness import timestamp

LOG = logging.getLogger(__name__)

STORY_SCHEMA = {
    'headline': '中立的简体中文标题',
    'is_conflict': 'JSON boolean; true for armed-conflict reporting',
    'freshness': {'development': '具体的新进展，非旧事重述', 'article_id': 'fresh report ID',
                  'quote': 'exact passage documenting the new development'},
    'claims': [{'kind': 'fact', 'text': '说明主要事实、关键数字和必要归属，约70至130个汉字',
                'evidence': [{'article_id': 'exact provided ID', 'quote': 'exact unmodified supporting passage >=15 characters'}]},
               {'kind': 'context', 'text': '补充相关背景、各方回应或下一步安排，约50至90个汉字',
                'evidence': [{'article_id': 'exact provided ID', 'quote': 'exact supporting passage'}]}],
    'cross_check': {'status': 'independent or single_source or not_independent',
                    'note': '中文简短说明核实情况'}}


def decode_selection(events, aliases, config):
    n, policy = config['newsletter'], config['editorial']
    if not isinstance(events, list) or not n['min_stories'] <= len(events) <= n['max_stories']:
        raise EditorialError('Select the configured number of distinct substantial events')
    used, keys, counts, decoded = set(), set(), {}, []
    dimensions = {'consequence', 'timeliness', 'credibility', 'global_relevance'}
    for event in events:
        if not isinstance(event, dict):
            raise EditorialError('Each selected event must be an object')
        ids = event.get('article_ids', [])
        if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or any(not isinstance(aid, str) for aid in ids) or len(set(ids)) != len(ids) or not set(ids) <= aliases.keys() or used.intersection(ids):
            raise EditorialError('Use only supplied short IDs, each in exactly one event')
        used.update(ids)
        key, category = event.get('event_key'), event.get('category')
        if not isinstance(key, str) or not key or key in keys:
            raise EditorialError('Use unique event keys')
        keys.add(key)
        if category not in {'politics', 'economics', 'business', 'technology', 'world'}:
            raise EditorialError('Use the supplied category names')
        section = 'politics' if category == 'world' else category
        counts[section] = counts.get(section, 0) + 1
        scores = event.get('scores', {})
        if not isinstance(scores, dict) or set(scores) != dimensions or any(type(v) not in (int, float) or not 0 <= v <= 5 for v in scores.values()):
            raise EditorialError('Provide all four ranking scores between zero and five')
        decoded.append(dict(event, article_ids=[aliases[aid] for aid in ids]))
    if len(counts) < policy.get('minimum_sections', 3):
        raise EditorialError('Select a varied edition across at least three sections')
    if counts.get('politics', 0) > len(events) * policy.get('politics_world_max_share', 1):
        raise EditorialError('Too many political/world events; include consequential economics and companies')
    if counts.get('technology', 0) > len(events) * policy.get('technology_max_share', 1):
        raise EditorialError('Too many technology events')
    return decoded


def resolve_story(candidate, event, aliases):
    # Ranking metadata is owned by Python. The writer supplies prose and
    # evidence references, using short per-story source IDs to avoid copy errors.
    if not isinstance(candidate, dict):
        raise EditorialError('Story must be an object')
    candidate = copy.deepcopy(candidate)
    for name in ('event_key', 'category', 'article_ids', 'scores'):
        candidate[name] = copy.deepcopy(event[name])
    references = [candidate.get('freshness', {})]
    if not isinstance(candidate.get('claims', []), list):
        raise EditorialError('Claims must be a list')
    for claim in candidate.get('claims', []):
        if not isinstance(claim, dict) or not isinstance(claim.get('evidence', []), list):
            raise EditorialError('Each claim must have an evidence list')
        references.extend(claim.get('evidence', []))
    for reference in references:
        if not isinstance(reference, dict):
            raise EditorialError('Evidence references must be objects')
        aid = reference.get('article_id')
        if aid not in aliases:
            raise EditorialError('Evidence must cite one of the provided short source IDs')
        reference['article_id'] = aliases[aid]
    return candidate


def generate_local(config, articles, date, model, as_of):
    n = config['newsletter']
    by_id = {a.id: a for a in articles}
    catalog, aliases = [], {}
    for article in articles:
        # Ranking needs the lead and relative age; writing/review retain full
        # publication metadata and evidence. Avoid repeating every RSS headline.
        lead = article.evidence
        if lead.startswith(article.title):
            lead = lead[len(article.title):].lstrip('. ')
        aid = f'a{len(catalog)}'
        aliases[aid] = article.id
        catalog.append({'id': aid, 'title': article.title, 'publisher': article.publisher,
                        'published_age_hours': round((as_of - timestamp(article.published)).total_seconds() / 3600, 2),
                        'excerpt': lead[:config['model'].get('ranking_excerpt_characters', 180)]})
    ranking_payload = {
        'task': 'Group reporting of the same event across languages and select 10–15 highest-impact distinct events. '
                'Do not write summaries yet. Vary category counts with important developments each day, without fixed category quotas; economics and companies must get substantive coverage. '
                'Reject recaps, explainers and old events; include only concrete new developments. Keep a varied mix and avoid technology or conflict dominating. Select no trivial sports, entertainment or personal-interest items. '
                'All short IDs must exist. Never associate an event with an unrelated title. Every ID can occur in only one event. '
                'Business means company transactions, earnings and operations; economics means macroeconomics, markets and trade. '
                'Do not label public health or human-interest features as business. Choose up to 3 useful original reports/event.',
        'preferences': config['editorial'], 'date': date, 'as_of': as_of.isoformat(), 'articles': catalog,
        'schema': {'events': [{'event_key': 'short unique event key', 'category': 'politics/economics/business/technology/world',
                              'article_ids': ['existing short IDs'],
                              'scores': {'consequence': 5, 'timeliness': 5, 'credibility': 5, 'global_relevance': 5}}]}}
    for attempt in range(2):
        ranked = model.ask(SYSTEM, ranking_payload)
        try:
            events = decode_selection(ranked.get('events', []), aliases, config)
            audit = model.ask(SYSTEM, {
                'task': 'Audit the selected events BEFORE writing. Each event must contain only coverage of the SAME event, '
                        'and its event key and category must match its actual source titles. Reject unrelated merged articles, '
                        'misclassified categories, minor human-interest stories, explainers, recaps and duplicate events. '
                        'Require substantive new developments and global importance. Return {"approved": true/false, "issues": [...]}.',
                'events': [dict(event, sources=[{'title': by_id[aid].title, 'publisher': by_id[aid].publisher,
                                                'lead': by_id[aid].evidence[:600]} for aid in event['article_ids']]) for event in events],
                'preferences': config['editorial']})
            if audit.get('approved') is not True or audit.get('issues') != []:
                raise EditorialError('Selection review failed: ' + str(audit.get('issues', [])))
            break
        except EditorialError as exc:
            if attempt == 1: raise
            ranking_payload['validation_error'] = str(exc)
            ranking_payload['previous_selection'] = ranked
    edition = {'date': date, 'as_of': as_of.isoformat(), 'stories': []}
    for index, event in enumerate(events, 1):
        LOG.info('Local editorial story=%d/%d event=%s', index, len(events), event.get('event_key'))
        evidence = [by_id[aid].to_dict() for aid in event['article_ids']]
        source_aliases = {f's{i}': aid for i, aid in enumerate(event['article_ids'])}
        writing_evidence = [dict(by_id[aid].to_dict(), id=alias) for alias, aid in source_aliases.items()]
        payload = {'task': 'Write ONE concise Chinese story with 2–3 grounded paragraphs. '
                           'Use approximately 120–220 Chinese characters total, with substantive details and essential context. Omit filler and process commentary. Do not invent background. '
                           'Use only the supplied short source IDs in all citations. Set is_conflict true for armed conflict. '
                           'Quotes must be copied exactly from evidence, not translated. Return {"story": {...}}.',
                   'event': {'event_key': event['event_key'], 'category': event['category']},
                   'articles': writing_evidence, 'schema': {'story': STORY_SCHEMA}}
        story = None
        single = copy.deepcopy(config)
        single['newsletter'].update(min_stories=1, max_stories=1)
        # One supported repair attempt for malformed structure/quotes, using precise validation evidence.
        for attempt in range(2):
            raw_candidate = model.ask(SYSTEM, payload).get('story', {})
            try:
                candidate = resolve_story(raw_candidate, event, source_aliases)
                validate({'date': date, 'as_of': as_of.isoformat(), 'stories': [candidate]}, articles, single, date, enforce_balance=False)
                story = candidate
                break
            except EditorialError as exc:
                if attempt == 1: raise
                payload['validation_error'] = str(exc)
                payload['previous_story'] = raw_candidate
        review = model.ask(SYSTEM, {
            'task': 'Verify this single story against provided source evidence. Check EVERY Chinese assertion, '
                    'dates/numbers, neutral political language, source independence, headline entailment, '
                    'adequate background, Simplified Chinese quality, and a concrete new development during the freshness window. '
                    'Verify the category, armed-conflict flag, and that all sources cover the same event. '
                    'No claim may rest on navigation or unrelated recommended links. '
                    'Return {"approved": true/false, "issues": [specific problems]}. Fail closed.',
            'story': story, 'articles': evidence})
        if review.get('approved') is not True or review.get('issues') != []:
            raise EditorialError(f"Local editorial verification failed for {event.get('event_key')}: {review.get('issues', [])}")
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
