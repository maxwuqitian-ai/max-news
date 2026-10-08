from datetime import datetime, timezone
import copy
import httpx
import pytest
import respx
from news_agent.weather import forecast, line
from news_agent.render import render

URL = 'https://api.open-meteo.com/v1/forecast'


def data():
    return {'current_units': {'temperature_2m': '°C'}, 'current': {'time':'2026-01-15T07:15', 'temperature_2m': -3.4},
            'daily_units': {'temperature_2m_max':'°C', 'temperature_2m_min':'°C', 'precipitation_probability_max':'%'},
            'daily': {'time':['2026-01-15','2026-01-16'], 'temperature_2m_max':[2.5,4.5],
                      'temperature_2m_min':[-6.1,-4.1], 'precipitation_probability_max':[35,55]}}


@respx.mock
def test_weather_celsius_probability_and_html_text_header(config, artifacts):
    route=respx.get(URL).mock(return_value=httpx.Response(200,json=data()))
    weather=forecast(config,datetime(2026,1,15,12,30,tzinfo=timezone.utc))
    assert weather['status']=='ok' and weather['temperature_c']==-3.4
    assert weather['precipitation_probability_percent']==35
    assert route.calls[0].request.url.params['temperature_unit']=='celsius'
    assert route.calls[0].request.url.params['timezone']=='America/New_York'
    _,edition=artifacts
    # Rendering tests need precomputed source metadata, just as production validation produces.
    from news_agent.editorial import validate
    validate(edition,artifacts[0],config,edition['date'])
    edition['weather']=weather
    html,text=render(edition,'简报')
    for output in (html,text):
        assert '-3.4°C' in output and '35%' in output and '汉诺威' in output
        assert '最低 -6.1°C / 最高 2.5°C' in output
        assert output.index('汉诺威') < output.index('政治与国际关系')
        assert 'Open-Meteo' in output
        assert '核实说明' not in output
    assert weather['probability_definition']=='maximum_hourly_precipitation_probability'


@pytest.mark.parametrize('failure',['outage','null_probability','fahrenheit','stale','future','wrong_date','invalid_range'])
@respx.mock
def test_weather_failures_never_invent_values(config,failure):
    d=data()
    if failure=='null_probability': d['daily']['precipitation_probability_max'][0]=None
    elif failure=='fahrenheit': d['current_units']['temperature_2m']='°F'
    elif failure=='stale': d['current']['time']='2026-01-15T01:00'
    elif failure=='future': d['current']['time']='2026-01-15T10:00'
    elif failure=='wrong_date': d['daily']['time']=['2026-01-13','2026-01-14']
    elif failure=='invalid_range': d['daily']['temperature_2m_min'][0]=30
    respx.get(URL).mock(return_value=httpx.Response(403) if failure=='outage' else httpx.Response(200,json=d))
    weather=forecast(config,datetime(2026,1,15,12,30,tzinfo=timezone.utc))
    assert weather['status']=='unavailable'
    assert '暂不可用' in line(weather) and '%' not in line(weather)


@respx.mock
def test_evening_preview_uses_tomorrow_forecast_with_correct_label(config):
    d=data();d['current']['time']='2026-01-15T20:15'
    respx.get(URL).mock(return_value=httpx.Response(200,json=d))
    weather=forecast(config,datetime(2026,1,16,1,30,tzinfo=timezone.utc))
    assert weather['date']=='2026-01-16' and weather['day_label']=='明日'
    assert weather['precipitation_probability_percent']==55


def test_disabled_weather_makes_no_request(config):
    config['weather']['enabled']=False
    assert forecast(config) is None
