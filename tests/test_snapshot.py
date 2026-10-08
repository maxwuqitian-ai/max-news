"""Repair retries preserve real cutoff timestamps and fail on stale evidence."""
from datetime import datetime
import json
import pytest
from news_agent.cli import read_snapshot
from news_agent.editorial import EditorialError


def snapshot(root, artifacts, as_of):
    (root / 'collection-report.json').write_text(json.dumps({'retrieved_at':as_of}))
    (root / 'articles.json').write_text(json.dumps([a.to_dict() for a in artifacts[0]]))


def test_recent_snapshot_retains_original_cutoff_and_reporting(config, artifacts, tmp_path):
    as_of='2026-01-15T12:00:00+00:00'
    snapshot(tmp_path,artifacts,as_of)
    articles,cutoff=read_snapshot(tmp_path,config,datetime.fromisoformat('2026-01-15T13:00:00+00:00'))
    assert cutoff.isoformat()==as_of
    assert [a.to_dict() for a in articles]==[a.to_dict() for a in artifacts[0]]


@pytest.mark.parametrize(('as_of','now'),[
    ('2026-01-15T08:59:00+00:00','2026-01-15T13:00:00+00:00'),
    ('2026-01-15T13:01:00+00:00','2026-01-15T13:00:00+00:00'),
    ('2026-10-09T03:30:00+00:00','2026-10-09T05:30:00+00:00'),
])
def test_snapshot_rejects_expired_future_or_previous_new_york_day(config, artifacts, tmp_path, as_of, now):
    snapshot(tmp_path,artifacts,as_of)
    with pytest.raises(EditorialError,match='freshness window'):
        read_snapshot(tmp_path,config,datetime.fromisoformat(now))
