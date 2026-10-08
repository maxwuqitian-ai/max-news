"""Free Open-Meteo forecasts; show failures rather than invent weather."""
from datetime import datetime, timedelta, timezone
import logging
import math
from zoneinfo import ZoneInfo
import httpx
from .net import get

LOG = logging.getLogger(__name__)


def number(value, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('Invalid weather value')
    return value


def forecast(config, now=None, client=None):
    settings = config.get('weather', {})
    if not settings.get('enabled', False): return None
    now = now or datetime.now(timezone.utc)
    tz = config['newsletter']['timezone']
    local = now.astimezone(ZoneInfo(tz))
    owns = client is None
    client = client or httpx.Client(timeout=15)
    try:
        response = get(client, settings['url'], attempts=2, params={
            'latitude': settings['latitude'], 'longitude': settings['longitude'],
            'current': 'temperature_2m',
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
            'temperature_unit': 'celsius', 'timezone': tz, 'forecast_days': 2})
        data = response.json()
        if data['current_units']['temperature_2m'] != '°C': raise ValueError('Weather must use Celsius')
        if data['daily_units']['precipitation_probability_max'] != '%': raise ValueError('Expected probability percent')
        if any(data['daily_units'][k] != '°C' for k in ('temperature_2m_max', 'temperature_2m_min')):
            raise ValueError('Daily temperatures must use Celsius')
        # Open-Meteo returns local ISO times without offsets; attach the requested IANA timezone.
        current_time = datetime.fromisoformat(data['current']['time'])
        if current_time.tzinfo is None: current_time = current_time.replace(tzinfo=ZoneInfo(tz))
        if not timedelta(0) <= now - current_time.astimezone(timezone.utc) <= timedelta(hours=2):
            raise ValueError('Stale or future weather observation')
        # An evening sample shows tomorrow's daytime range/probability instead of an almost-ended day.
        day = local.date() + timedelta(days=local.hour >= settings.get('next_day_after_hour', 18))
        index = data['daily']['time'].index(day.isoformat())
        low = number(data['daily']['temperature_2m_min'][index], -100, 65)
        high = number(data['daily']['temperature_2m_max'][index], -100, 65)
        if low > high: raise ValueError('Invalid daily temperature range')
        chance = number(data['daily']['precipitation_probability_max'][index], 0, 100)
        return {'status': 'ok', 'location': settings['location'], 'date': day.isoformat(),
                'day_label': '明日' if day != local.date() else '今日',
                'temperature_c': round(number(data['current']['temperature_2m'], -100, 65), 1),
                'low_c': round(low, 1), 'high_c': round(high, 1), 'precipitation_probability_percent': round(chance),
                'current_time': current_time.isoformat(), 'retrieved_at': now.isoformat(),
                'source': 'Open-Meteo', 'source_url': 'https://open-meteo.com/',
                'probability_definition': 'maximum_hourly_precipitation_probability'}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        LOG.warning('Weather unavailable error=%s', type(exc).__name__)
        return {'status': 'unavailable', 'location': settings['location'], 'retrieved_at': now.isoformat()}
    finally:
        if owns: client.close()


def line(weather):
    if not weather: return None
    if weather['status'] != 'ok': return f"{weather['location']}｜天气暂不可用"
    if weather.get('data_mode') == 'retrospective_model':
        return (f"{weather['location']}｜07:00 {weather['temperature_c']:g}°C（模型）｜"
                f"当日降雨/雪概率 {weather['precipitation_probability_percent']}%"
                '（最高小时值，模型）')
    return (f"{weather['location']}｜当前 {weather['temperature_c']:g}°C｜{weather['day_label']} "
            f"最低 {weather['low_c']:g}°C / 最高 {weather['high_c']:g}°C｜降雨/雪概率 "
            f"{weather['precipitation_probability_percent']}%（最高小时值）")
