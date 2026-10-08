"""Synthetic source fixtures; never use these as a real briefing."""
import copy
from datetime import datetime
import pytest
from news_agent.collect import Article
from news_agent.editorial import EditorialError,validate
from news_agent.publisher_excerpt import compile_story,short_excerpt,verify_story,eligible
from news_agent.render import render

def fixture():
    title='合成測試銀行宣布調升利率'
    text='這是虛構測試：國民銀行調高基準利率0.25個百分點，以回應通脹上升。新利率下月生效，銀行表示將根據物價數據評估後續政策。'
    article=Article('test-source',title,'https://publisher.example/test','合成測試媒體','synthetic',
        '2026-01-15T11:00:00+00:00',title+'. '+text,'2026-01-15T12:00:00+00:00','rss',publisher_excerpt=text)
    event={'event_key':'synthetic-rate-change','category':'economics','is_conflict':False,'article_ids':[article.id],
           'scores':{'consequence':4,'timeliness':4,'credibility':4,'global_relevance':4}}
    return article,event

def test_publisher_truncation_keeps_only_complete_sentences():
    with pytest.raises(EditorialError,match='complete publisher sentence'):
        short_excerpt('三星传出调降产量，主因是手机事业的成本压 […]',180)
    assert short_excerpt('合成测试：三星表示计划降低手机产量。尚未披露完整的成本压 […]',180)=='合成测试：三星表示计划降低手机产量。'

def test_incomplete_source_prefix_cannot_pass_delivery_verification():
    from news_agent.publisher_excerpt import simplified
    article,event=fixture();story=compile_story(event,[article])
    quote=article.publisher_excerpt[:20]
    story['claims'][1]['evidence'][0]['quote']=quote
    story['claims'][1]['text']=simplified(f'据{article.publisher}报道：'+quote)
    with pytest.raises(EditorialError,match='complete publisher sentence'):
        verify_story(story,[article])

def test_source_preserving_briefing_has_simplified_chinese_and_verbatim_provenance(config):
    article,event=fixture();story=compile_story(event,[article])
    config['editorial']['mode']='publisher_chinese_excerpt'
    config['newsletter'].update(min_stories=1,max_stories=1)
    edition={'date':'2026-01-15','as_of':'2026-01-15T12:00:00+00:00','stories':[story]}
    validate(edition,[article],config,edition['date'],enforce_balance=False)
    assert '調升' not in story['headline'] and '调升' in story['headline']
    assert '0.25' in story['claims'][1]['text']
    assert story['claims'][1]['evidence'][0]['quote'] in article.evidence
    html,text=render(edition,'测试')
    assert html.count(story['headline'])==1 and text.count(story['headline'])==1

@pytest.mark.parametrize('change',[('0.25','0.50'),('国民银行','国家银行')])
def test_altered_figures_and_names_are_rejected_before_delivery(change):
    article,event=fixture();story=compile_story(event,[article])
    story['claims'][1]['text']=story['claims'][1]['text'].replace(*change)
    with pytest.raises(EditorialError,match='rewritten'):verify_story(story,[article])

def test_short_excerpt_never_cuts_a_decimal_as_a_sentence_boundary():
    source='这是合成测试，银行将利率上调0.25个百分点。下一句说明其他背景。'
    assert short_excerpt(source,len(source)-8)=='这是合成测试，银行将利率上调0.25个百分点。'

def test_opinion_paths_are_excluded_even_when_discovered_outside_rss():
    article,_=fixture();assert eligible(article)
    article.url='https://publisher.example/opinion/policy'
    assert not eligible(article)
    article.url='https://publisher.example/%E4%B8%93%E6%A0%8F%E6%A3%80%E7%B4%A2/policy'
    assert not eligible(article)
