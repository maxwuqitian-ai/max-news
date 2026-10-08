"""Classify small source batches; let Python own identity, grouping and ranking."""
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from math import floor
from .editorial import EditorialError

LOG = logging.getLogger(__name__)
NEWS_CATEGORIES = ['politics', 'economics', 'business', 'technology', 'world']
CATEGORIES = NEWS_CATEGORIES + ['sports', 'entertainment', 'personal_interest']
GENRES = ['breaking_news', 'explainer', 'recap', 'opinion', 'profile']

def primary_category(title, predicted):
    """Resolve unambiguous primary events, rather than secondary AI/weather effects."""
    text = title.casefold()
    if (re.search(r'武器|[导導][弹彈]|[飞飛][弹彈]|\b(?:missile|weapon)\b',text)
            and re.search(r'[试試]射|\btests?\b',text)):
        return 'politics'
    if (re.search(r'[欧歐]股|股市|\b(?:stock markets?|wall street|european stocks)\b',text)
            and re.search(r'收黑|[开開]低|走低|下跌|\b(?:falls?|drops?|slumps?|lower)\b',text)):
        return 'economics'
    if re.search(r'\b(profits?|earnings|acquisition|buyout|merger)\b', text) and not re.search(r'\b(industrial|economy-wide|sector-wide)\b', text):
        return 'business'
    if re.search(r'\b(hurricane|typhoon|earthquake|tsunami)\b', text) and re.search(r'\b(strengthens|forms|hits|strikes|landfall)\b', text):
        return 'world'
    return predicted



def conflict_theme(title):
    """Count military, attack and ceasefire reporting toward the conflict limit."""
    text = title.casefold()
    weapons = (re.search(r'武器|[导導][弹彈]|[飞飛][弹彈]|\b(?:missiles?|weapons?)\b', text)
               and re.search(r'[试試]射|\btests?\b', text))
    naval = (re.search(r'[舰艦]船|[军軍][舰艦]|海[军軍]|\b(?:naval|navy|warships?)\b', text)
             and re.search(r'南海|[紧緊][张張]|[对對]峙|\b(?:tensions?|confrontation|south china sea)\b', text))
    direct_war = re.search(r'停火|停[战戰]|[战戰]事|[战戰]火|[战戰][场場]|前[线線]|空[袭襲]|[炮砲][击擊]|[轰轟]炸|\b(?:ceasefires?|shelling|bombardment|airstrikes?)\b', text)
    conflict_context = re.search(r'伊朗|以色列|加[沙薩]|[乌烏]克[兰蘭]|[军軍][队隊]|[军軍]方|美[军軍]|\b(?:iran|israel|gaza|ukraine|russia|army|military)\b', text)
    attack = re.search(r'攻[击擊]|[袭襲][击擊]|[开開][战戰]|[进進]攻|\b(?:attacks?|strikes?)\b|(?<!trade )\bwar\b', text)
    return bool(weapons or naval or direct_war or (conflict_context and attack))


def oil_market_event(article,timezone):
    """Consolidate the same day's regional stock declines linked to rising oil."""
    title=article['title'].casefold();text=title+' '+article.get('excerpt','').casefold()
    if not article.get('published_at') or primary_category(title,'unknown')!='economics':
        return None
    if not re.search(r'油[价價](?:今天|今日)?(?:大|急|暴|[飙飆])?(?:升|[涨漲])|(?:rising|surging|higher)\s+(?:crude\s+)?oil|oil(?:\s+prices?)?\s+(?:rises?|rose|jumps?|surges?)',text):
        return None
    day=datetime.fromisoformat(article['published_at'].replace('Z','+00:00')).astimezone(ZoneInfo(timezone)).date()
    return 'global_markets_rising_oil_'+day.isoformat().replace('-','_')

def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}

def rating_schema(ids):
    rating = obj({'category': {'type': 'string', 'enum': CATEGORIES},
        'genre': {'type': 'string', 'enum': GENRES},
        'event_key': {'type': 'string'}, 'is_conflict': {'type': 'boolean'},
        'consequence': {'type': 'integer', 'minimum': 0, 'maximum': 5},
        'global_relevance': {'type': 'integer', 'minimum': 0, 'maximum': 5}})
    return obj({'ratings': obj({aid: rating for aid in ids})})

def classify(catalog, model, system, config):
    ratings = {}
    size = config['model'].get('selection_batch_size', 20)
    if not 1 <= size <= 30: raise EditorialError('Selection batch size must be 1–30')
    for start in range(0, len(catalog), size):
        batch = catalog[start:start + size]
        ids = {a['id'] for a in batch}
        payload = {
            'task': 'Rate EVERY supplied article separately. Do not select a newsletter yet. '
                    'Return ratings keyed by the exact article IDs, exactly once each. '
                    'Category describes the topic; genre describes new reporting versus explanation, commentary or profiles. '
                    'Sports news belongs to category sports, even when it is breaking_news. Entertainment belongs to entertainment. '
                    'Company acquisitions/earnings/operations are business; government/diplomatic/legal policy actions are politics; '
                    'economic data, financial markets and trade are economics. A cricket fixture is sports, not business. '
                    'Rate consequence and global_relevance 0–5: 0–2 is minor/local/personal-interest; 3–5 is consequential. '
                    'Use a concise lowercase English event_key for the concrete development. '
                    'Reports of the SAME event must use the SAME key, including existing keys below. '
                    'Different countries/entities/actions must not share a key. is_conflict is true for armed-conflict reporting.',
            # Genre/event identity/impact depend on original reporting. Recency
            # is recalculated by select(), and freshness checked before delivery.
            # An advancing clock must not invalidate unchanged source ratings.
            'articles': [{k:v for k,v in article.items() if k!='published_age_hours'} for article in batch],
            'category_definitions': {'politics': 'government, elections, diplomacy, national laws and government policy',
                'economics': 'macroeconomic data, financial markets, trade and economy-wide conditions',
                'business': 'company transactions, acquisitions, earnings, competition and operations',
                'technology': 'computing, AI, products and significant research breakthroughs',
                'world': 'major public health, disasters and other consequential non-political events',
                'sports': 'fixtures, athletes, competitions and retirements',
                'entertainment': 'actors, films, celebrity events and entertainment features',
                'personal_interest': 'minor local cases, human-interest features, lifestyle and travel'},
            'genre_definitions': {'breaking_news': 'FACTUAL REPORT of a substantive NEW development, announcement, decision, transaction, data release or verified change; this is the eligible news genre',
                'explainer': 'background/how/why analysis without a substantive new development',
                'recap': 'retelling or rounding up previously reported developments',
                'opinion': 'commentary, reviews, letters and author opinions',
                'profile': 'background about a person, place, lifestyle or ongoing topic without a substantive new development'},
            'impact_scale': {'0': 'irrelevant', '1': 'minor or personal-interest', '2': 'limited/local consequence',
                '3': 'significant regional or sector consequence', '4': 'major national/international consequence',
                '5': 'exceptional global consequence'},
            'known_events': {r['event_key']: next(a['title'] for a in catalog if a['id'] == aid)
                             for aid, r in ratings.items()},
            'response_schema': rating_schema([a['id'] for a in batch])}
        LOG.info('Classifying source batch=%d articles=%d', start // size + 1, len(batch))
        for attempt in range(2):
            result = model.ask(system, payload).get('ratings', {})
            try:
                if not isinstance(result, dict) or set(result) != ids:
                    raise EditorialError('Rate every supplied source ID exactly once; do not invent or omit IDs')
                for aid, r in result.items():
                    if isinstance(r, dict) and r.get('genre') in ('sports', 'entertainment', 'personal_interest'):
                        # Interpret legacy assessments using orthogonal topic/genre axes.
                        r['category'], r['genre'] = r['genre'], 'breaking_news'
                    if isinstance(r, dict) and isinstance(r.get('event_key'), str):
                        # An internal grouping label is case/space insensitive;
                        # normalize syntax without changing any source identity.
                        r['event_key'] = re.sub(r'[^a-z0-9_-]+', '_', r['event_key'].casefold()).strip('_')
                    if (not isinstance(r, dict) or r.get('category') not in CATEGORIES or r.get('genre') not in GENRES
                            or type(r.get('is_conflict')) is not bool or not isinstance(r.get('event_key'), str)
                            or not re.fullmatch(r'[a-z0-9_-]{3,100}', r['event_key'])
                            or any(type(r.get(k)) is not int or not 0 <= r[k] <= 5 for k in ('consequence', 'global_relevance'))):
                        raise EditorialError(f'Invalid source assessment for {aid}')
                for article in batch:
                    r = result[article['id']]
                    r['category'] = primary_category(article['title'], r['category'])
                ratings.update(result)
                break
            except EditorialError as exc:
                if attempt: raise
                payload['validation_error'] = str(exc)
    return ratings

def select(catalog, ratings, config, *, excluded=frozenset(),eligible_primary=None):
    policy, n = config['editorial'], config['newsletter']
    groups = {}
    for article in catalog:
        aid = article['id']; r = ratings[aid]
        if aid in excluded or r['category'] not in NEWS_CATEGORIES or r['genre'] != 'breaking_news':
            continue
        r=dict(r,category=primary_category(article['title'],r['category']),
               is_conflict=r['is_conflict'] or conflict_theme(article['title']))
        key=oil_market_event(article,n['timezone']) or r['event_key']
        group = groups.setdefault(key, [])
        group.append((article, r))
    candidates = []
    for key, reports in groups.items():
        if (max(r['consequence'] for _, r in reports) < policy.get('minimum_consequence', 3)
                or max(r['global_relevance'] for _, r in reports) < policy.get('minimum_global_relevance', 3)):
            continue
        reports.sort(key=lambda ar: ar[0]['published_age_hours'])
        primaries=[ar for ar in reports if eligible_primary is None or ar[0]['id'] in eligible_primary]
        if not primaries: continue
        primary, rating = primaries[0]
        scores = {'consequence': max(r['consequence'] for _, r in reports),
                  'timeliness': round(max(0, 5 * (1 - primary['published_age_hours'] / 24)), 2),
                  'credibility': 5 if primary.get('family') in ('BBC', 'AP', 'Reuters', 'NPR') else 4, 'global_relevance': max(r['global_relevance'] for _, r in reports)}
        chosen = [primary]
        families = {primary.get('family')}
        for a, _ in reports:
            if a.get('family') not in families:
                chosen.append(a); families.add(a.get('family'))
                if len(chosen) == 3: break
        candidates.append({'event_key': key, 'category': rating['category'],
                           'article_ids': [a['id'] for a in chosen], 'scores': scores,
                           'is_conflict': any(r['is_conflict'] for _, r in reports)})
    candidates.sort(key=lambda e: sum(e['scores'][k] * w for k, w in
        [('consequence', .4), ('timeliness', .2), ('credibility', .2), ('global_relevance', .2)]), reverse=True)
    for count in range(n['max_stories'], n['min_stories'] - 1, -1):
        selected, counts, conflicts = [], {}, 0
        for event in candidates:
            section = 'politics' if event['category'] == 'world' else event['category']
            cap = {'politics': floor(count * policy.get('politics_world_max_share', 1)),
                   'technology': floor(count * policy.get('technology_max_share', 1))}.get(section, count)
            if counts.get(section, 0) >= cap: continue
            if event['is_conflict'] and conflicts >= floor(count * policy.get('conflict_max_share', 1)): continue
            selected.append(event); counts[section] = counts.get(section, 0) + 1
            conflicts += event['is_conflict']
            if len(selected) == count: break
        if len(selected) == count and len(counts) >= policy.get('minimum_sections', 3):
            return selected
    raise EditorialError('Insufficient distinct consequential fresh events with the required topic variety')
