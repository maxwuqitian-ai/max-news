"""Synthetic fixtures only. These are NOT a real-news sample."""
import copy
from datetime import datetime, timezone
import pytest
from news_agent.config import load
from news_agent.collect import Article


@pytest.fixture
def config(tmp_path):
    c = load('config.yaml')
    c['model']['provider'] = 'openai'
    c['model']['api_key_env'] = 'NEWS_LLM_API_KEY'
    c['newsletter']['state_dir'] = str(tmp_path / 'state')
    c['newsletter']['output_dir'] = str(tmp_path / 'output')
    return c


@pytest.fixture
def artifacts():
    articles, stories = [], []
    quote = 'This is synthetic test evidence that describes an explicitly fictional event for unit testing.'
    for i in range(10):
        aid = f'article-{i}'
        articles.append(Article(aid, f'SYNTHETIC event {i}', f'https://publisher.example/story/{i}',
            f'Test publisher {i % 3}', f'family-{i % 3}', '2026-01-15T11:00:00+00:00', quote,
            '2026-01-15T12:00:00+00:00', 'rss'))
        stories.append({'event_key': f'synthetic-{i}', 'category': ['politics', 'politics', 'politics', 'economics', 'economics', 'economics', 'business', 'business', 'technology', 'technology'][i], 'is_conflict': False,
            'freshness': {'development': '这是一项新的虚构测试进展', 'article_id': aid, 'quote': quote}, 'headline': f'测试虚构新闻标题{i}',
            'article_ids': [aid], 'scores': {'consequence': 4, 'timeliness': 4, 'credibility': 3, 'global_relevance': 4},
            'claims': [{'kind': kind, 'text': ('这是一段明确标注为虚构的测试内容，仅用于验证软件功能，不是新闻，也不应用于任何实际简报。' * 2),
                        'evidence': [{'article_id': aid, 'quote': quote}]} for kind in ('fact', 'context')],
            'cross_check': {'status': 'single_source', 'note': '仅为虚构测试素材，尚无独立报道核实。'}})
    return articles, {'date': '2026-01-15', 'as_of': '2026-01-15T12:00:00+00:00', 'stories': stories}
