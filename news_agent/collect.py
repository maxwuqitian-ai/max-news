from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from hashlib import sha256
from html.parser import HTMLParser
import logging
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import feedparser
import httpx
from .net import get
from .freshness import timestamp, is_fresh

LOG = logging.getLogger(__name__)


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer'): self.skip += 1
        elif tag in ('p', 'br', 'h1', 'h2', 'li'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer') and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def clean(value: str) -> str:
    parser = TextParser()
    parser.feed(value)
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise ValueError('Only public HTTPS publisher URLs are accepted')
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(('utm_', 'fbclid', 'gclid'))]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path, urlencode(query), ''))


def allowed(url: str, domains: list[str]) -> bool:
    host = urlsplit(url).hostname or ''
    return any(host == d or host.endswith('.' + d) for d in domains)


@dataclass
class Article:
    id: str
    title: str
    url: str
    publisher: str
    family: str
    published: str | None
    evidence: str
    retrieved: str
    method: str
    discovered: str | None = None
    def to_dict(self): return asdict(self)


def make_article(title, url, publisher, family, published, evidence, now, method):
    url = canonical_url(url)
    return Article(sha256(url.encode()).hexdigest()[:16], clean(title), url, publisher, family,
                   published.isoformat() if published else None, clean(evidence)[:6000], now.isoformat(), method)


def in_window(published: datetime, now: datetime, hours: int) -> bool:
    return now - timedelta(hours=hours) <= published <= now


class PublicationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.published = None
        self.ld = False
        self.ld_parts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and (attrs.get('property') or attrs.get('name', '')).lower() in ('article:published_time', 'datepublished'):
            try: self.published = timestamp(attrs.get('content'))
            except ValueError: pass
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.ld = True
            self.ld_parts = []
    def handle_data(self, data):
        if self.ld: self.ld_parts.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.ld:
            self.ld = False
            try:
                def visit(obj):
                    if isinstance(obj, list):
                        for child in obj: visit(child)
                    if isinstance(obj, dict):
                        kinds = obj.get('@type', [])
                        if isinstance(kinds, str): kinds = [kinds]
                        if set(kinds) & {'NewsArticle', 'Article', 'ReportageNewsArticle'} and obj.get('datePublished'):
                            self.published = timestamp(obj['datePublished'])
                        if '@graph' in obj: visit(obj['@graph'])
                visit(json.loads(''.join(self.ld_parts)))
            except (ValueError, TypeError): pass


def publisher_page(client, url, domains):
    # Follow only allowlisted publisher redirects; do not follow arbitrary feed URLs.
    for _ in range(5):
        if not allowed(url, domains): raise ValueError('Redirect outside publisher domains')
        response = get(client, url, follow_redirects=False, attempts=1, timeout=8)
        if response.is_redirect:
            from urllib.parse import urljoin
            url = canonical_url(urljoin(url, response.headers['location']))
            continue
        metadata = PublicationParser()
        metadata.feed(response.text)
        return clean(response.text), metadata.published
    raise ValueError('Too many redirects')


def page_evidence(client, url, domains):
    return publisher_page(client, url, domains)[0]


def collect(config, now=None, client=None):
    now = now or datetime.now(timezone.utc)
    articles, failures = {}, []
    hours = config['newsletter']['lookback_hours']
    owns = client is None
    client = client or httpx.Client(timeout=25, headers={'User-Agent': 'GlobalDailyNews/0.1 (personal RSS briefing)'})
    try:
        for source in config['sources']:
            try:
                feed = feedparser.parse(get(client, source['url'], follow_redirects=True).content)
                if feed.bozo and not feed.entries: raise ValueError('Invalid feed')
                for entry in feed.entries[:config['newsletter'].get('max_per_feed', 25)]:
                    stamp = entry.get('published_parsed')
                    if not stamp: continue  # Never invent a publisher timestamp.
                    published = datetime(*stamp[:6], tzinfo=timezone.utc)
                    if not in_window(published, now, hours): continue
                    try:
                        url = canonical_url(entry.get('link', ''))
                        if not allowed(url, source['domains']): continue
                        body = ' '.join(c.get('value', '') for c in entry.get('content', [])) or entry.get('summary', '')
                        evidence = entry.get('title', '') + '. ' + body
                        article = make_article(entry.get('title', ''), url, source['name'], source['family'], published, evidence, now, 'rss')
                        if len(article.evidence) >= 100: articles[url] = article
                    except ValueError: continue
                LOG.info('Collected RSS source=%s cumulative=%d', source['name'], len(articles))
            except (httpx.HTTPError, ValueError) as exc:
                failures.append({'source': source['name'], 'error': type(exc).__name__})
                LOG.warning('RSS unavailable source=%s error=%s', source['name'], type(exc).__name__)
        gdelt = config['gdelt']
        if gdelt['enabled']:
            try:
                # Query time is anchored to the actual collection window, including historical manual dates.
                response = get(client, gdelt['url'], params={
                    'query': gdelt['query'], 'mode': 'artlist', 'format': 'json',
                    'maxrecords': gdelt['max_records'], 'sort': 'datedesc',
                    'startdatetime': (now-timedelta(hours=hours)).strftime('%Y%m%d%H%M%S'),
                    'enddatetime': now.strftime('%Y%m%d%H%M%S')})
                for item in response.json().get('articles', []):
                    try:
                        url = canonical_url(item['url'])
                        if url in articles: continue
                        domain = next((d for d in gdelt['publishers'] if allowed(url, [d])), None)
                        if not domain: continue
                        # GDELT seendate is discovery time, NOT publication time. Keep it explicitly identified.
                        seen = datetime.strptime(item['seendate'], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
                        if not in_window(seen, now, hours): continue
                        body = ''  # Full publisher evidence is fetched in the bounded enrichment phase.
                        p = gdelt['publishers'][domain]
                        article = make_article(item['title'], url, p['name'], p['family'], None,
                                               item['title'] + '. ' + body, now, 'gdelt_discovery_time')
                        article.discovered = seen.isoformat()
                        articles[url] = article
                    except (httpx.HTTPError, ValueError, KeyError): continue
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                failures.append({'source': 'GDELT', 'error': type(exc).__name__})
                LOG.warning('GDELT unavailable error=%s', type(exc).__name__)
    except BaseException:
        if owns: client.close()
        raise
    # Keep representation across sources without country quotas; editorial ranking follows.
    ordered = sorted(articles.values(), key=lambda a: a.published or a.discovered or '', reverse=True)
    buckets = {}
    for article in ordered: buckets.setdefault(article.family, []).append(article)
    balanced = []
    while any(buckets.values()) and len(balanced) < config['newsletter']['max_candidates']:
        for bucket in buckets.values():
            if bucket and len(balanced) < config['newsletter']['max_candidates']: balanced.append(bucket.pop(0))
    domains = list({d for source in config['sources'] for d in source.get('domains', [])} | set(gdelt['publishers']))
    def enrich(article):
        try:
            if len(article.evidence) < 1200 or article.method == 'gdelt_discovery_time':
                body, published = publisher_page(client, article.url, domains)
                if article.published is None and published:
                    article.published = published.isoformat()
                if len(body) >= 300: article.evidence = (article.evidence + ' ' + body)[:6000]
        except (httpx.HTTPError, ValueError): pass
        return article
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            enriched = list(pool.map(enrich, balanced))
        return [a for a in enriched if is_fresh(a, now, hours) and len(a.evidence) >= (300 if a.method == 'gdelt_discovery_time' else 100)], failures
    finally:
        if owns: client.close()


def preliminary_groups(articles):
    """Conservative lexical grouping, refined across languages by the editorial model."""
    groups = []
    for article in articles:
        normalized = re.sub(r'[^\w\s]', '', article.title.casefold())
        group = next((g for g in groups if SequenceMatcher(None, normalized, g['key']).ratio() >= .82), None)
        if group: group['article_ids'].append(article.id)
        else: groups.append({'key': normalized, 'article_ids': [article.id]})
    return [g['article_ids'] for g in groups]
