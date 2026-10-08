from datetime import datetime
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo
from .weather import line as weather_line
from jinja2 import Environment, BaseLoader, select_autoescape

LABELS = {'politics': '政治与国际关系', 'economics': '经济与市场', 'business': '公司与商业', 'technology': '科技与AI'}
ORDER = ['politics', 'economics', 'business', 'technology']

TEMPLATE = '''<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ subject }}</title>
<style>body{margin:0;background:#f2f4f7;color:#182433;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}.wrap{max-width:720px;margin:auto;background:white;padding:28px}h1{font-size:26px}h2{font-size:21px;color:#175d9b;margin-top:30px}h3{font-size:18px;line-height:1.5}p{font-size:16px;line-height:1.9}a{color:#175d9b;overflow-wrap:anywhere}.meta{color:#596575;font-size:13px}.story{border-top:1px solid #dde3eb;padding:12px 0}@media(max-width:600px){.wrap{padding:16px}h1{font-size:23px}}</style></head>
<body><div class="wrap" style="max-width:720px;margin:auto;background:#fff;padding:24px"><h1>{{ subject }}</h1>
{% if weather %}<p style="font-size:15px;line-height:1.6;background:#eef5fc;padding:12px">{{ weather }}</p>{% if weather_source %}<p class="meta"><a href="{{ weather_source }}">Open-Meteo</a></p>{% endif %}{% endif %}
<p class="meta">{{ edition.date }}{% if test or edition.sample_note %} · 晨间样刊{% endif %} · {{ edition.stories|length }} 条重要新闻 · 约 {{ minutes }} 分钟阅读</p>
<p class="meta">新闻截止时间：{{ as_of }}（纽约时间）</p>

{% for section in sections %}<h2>{{ section.label }} · {{ section.stories|length }} 条</h2>
{% for story in section.stories %}<section class="story" style="border-top:1px solid #dde3eb;padding:12px 0"><h3>{{ story.number }}. {{ story.headline }}</h3>
{% for claim in story.claims if claim.placement != 'headline' %}<p style="font-size:16px;line-height:1.9">{{ claim.text }}</p>{% endfor %}
<p class="meta">原始报道：{% for source in story.sources %}<a href="{{ source.url }}">{{ source.name }}</a>{% if not loop.last %} · {% endif %}{% endfor %}</p></section>{% endfor %}{% endfor %}
</div></body></html>'''



def ordered_stories(stories, section_order=None):
    """Keep ranking within sections while matching the email's presentation order."""
    positions={category:i for i,category in enumerate(section_order or ORDER)}
    return sorted(stories,key=lambda story:positions['politics' if story['category']=='world' else story['category']])


def local_time(value):
    if not value: return '发表时间未核实，仅作背景'
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M')


def render(edition, subject, test=False, section_order=None):
    urls = {s['id']: s['url'] for story in edition['stories'] for s in story['sources']}
    order = section_order or ORDER
    sections = []
    number = 0
    for category in order:
        stories = []
        for story in edition['stories']:
            group = 'politics' if story['category'] == 'world' else story['category']
            if group != category: continue
            number += 1
            sources = [dict(s, published_label=local_time(s.get('time'))) for s in story['sources']]
            stories.append(dict(story, number=number, sources=sources))
        if stories: sections.append({'label': LABELS[category], 'stories': stories})
    as_of = local_time(edition.get('as_of'))
    minutes = max(1, math.ceil(sum(len(re.findall(r'[\u4e00-\u9fff]', c['text'])) for s in edition['stories'] for c in s['claims']) / 300))
    weather = edition.get('weather')
    weather_text = weather_line(weather)
    weather_source = weather.get('source_url') if weather and weather.get('status') == 'ok' else None
    weather_time = local_time(weather.get('current_time')) if weather_source else None
    weather_time_label = '天气对应时间' if weather and weather.get('data_mode') == 'retrospective_model' else '天气更新'
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(default=True))
    html = env.from_string(TEMPLATE).render(edition=edition, subject=subject, article_urls=urls,
                                         test=test, sections=sections, as_of=as_of, minutes=minutes, weather=weather_text, weather_source=weather_source, weather_time=weather_time, weather_time_label=weather_time_label)
    lines = [subject, f"{edition['date']} · {len(edition['stories'])} 条重要新闻 · 约{minutes}分钟阅读",
             f'新闻截止时间：{as_of}（纽约时间）', '']
    if weather_text:
        lines[1:1] = [weather_text] + ([f'Open-Meteo {weather_source}'] if weather_source else [])
    if test or edition.get('sample_note'): lines[1:1] = ['晨间样刊']
    for section in sections:
        lines += [f"【{section['label']}】", '']
        for story in section['stories']:
            lines += [f"{story['number']}. {story['headline']}"]
            lines += [c['text'] for c in story['claims'] if c.get('placement') != 'headline']
            lines += [f"来源：{s['name']} {s['url']}" for s in story['sources']]
            lines += ['']
    return html, '\n'.join(lines)


def write(edition, subject, directory, test=False, section_order=None):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    html, text = render(edition, subject, test, section_order)
    (root / 'briefing.html').write_text(html, encoding='utf-8')
    (root / 'briefing.txt').write_text(text, encoding='utf-8')
    return html, text
