from pathlib import Path
from zoneinfo import ZoneInfo
import yaml


def load(path: str) -> dict:
    config = yaml.safe_load(Path(path).read_text())
    n = config['newsletter']
    ZoneInfo(n['timezone'])
    if not 6 <= n['min_stories'] <= n['max_stories'] <= 15:
        raise ValueError('Configure between 6 and 15 substantial stories')
    if not 1 <= n['lookback_hours'] <= 72 or n['max_candidates'] < n['min_stories']:
        raise ValueError('Invalid collection limits')
    if n['lookback_hours'] > 24:
        raise ValueError('Fresh daily news must use at most a 24-hour lookback')
    if not 0 < n.get('max_edition_age_hours', 4) <= 4:
        raise ValueError('An edition cannot be sent more than four hours after collection')
    editorial = config['editorial']
    order = editorial.get('section_order', ['politics', 'economics', 'business', 'technology'])
    if len(order) != 4 or set(order) != {'politics', 'economics', 'business', 'technology'}:
        raise ValueError('Section order must contain all four sections exactly once')
    if not 0 < editorial.get('politics_world_max_share', .4) <= 1:
        raise ValueError('Invalid politics/world share')
    weather = config.get('weather', {})
    if weather.get('enabled'):
        if not -90 <= weather['latitude'] <= 90 or not -180 <= weather['longitude'] <= 180:
            raise ValueError('Invalid weather location coordinates')
    return config
