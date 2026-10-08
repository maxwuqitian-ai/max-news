import base64
import json
from email import message_from_bytes
import httpx
import pytest
import respx
from news_agent.delivery import deliver, DeliveryError


@pytest.fixture
def credentials(monkeypatch):
    for key, value in {'NEWS_RECIPIENT': 'reader@example.org', 'NEWS_SENDER': 'news@example.org',
                       'RESEND_API_KEY': 'synthetic-test-key', 'GMAIL_CLIENT_ID': 'test-id',
                       'GMAIL_CLIENT_SECRET': 'test-secret', 'GMAIL_REFRESH_TOKEN': 'test-refresh'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)


@respx.mock
def test_resend_manual_and_duplicate_prevention(config, credentials):
    route = respx.post('https://api.resend.com/emails').mock(return_value=httpx.Response(200, json={'id': 'mail-123'}))
    with httpx.Client() as client:
        first = deliver(config, '<p>测试</p>', '测试', '2026-01-15', test_id='test-one', client=client)
        second = deliver(config, '<p>测试</p>', '测试', '2026-01-15', test_id='test-one', client=client)
    assert first['status'] == 'sent' and second['status'] == 'duplicate'
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.headers['Idempotency-Key']
    assert json.loads(request.content)['text'] == '测试'


@respx.mock
def test_timeout_blocks_automatic_resend(config, credentials):
    route = respx.post('https://api.resend.com/emails').mock(side_effect=httpx.ReadTimeout('uncertain'))
    with httpx.Client() as client:
        with pytest.raises(DeliveryError, match='uncertain'):
            deliver(config, 'html', 'text', '2026-01-15', test_id='timeout', client=client)
        with pytest.raises(DeliveryError, match='reconcile'):
            deliver(config, 'html', 'text', '2026-01-15', test_id='timeout', client=client)
    assert route.call_count == 1


@respx.mock
def test_disabled_daily_delivery(config, credentials):
    config['newsletter']['delivery_enabled'] = False
    route = respx.post('https://api.resend.com/emails').mock(return_value=httpx.Response(200, json={'id': 'must-not-send'}))
    with pytest.raises(DeliveryError, match='disabled'):
        deliver(config, 'html', 'text', '2026-01-15')
    assert route.call_count == 0


@respx.mock
def test_durable_state_must_save_before_send(config, credentials, monkeypatch):
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.delenv('NEWS_DURABLE_STATE', raising=False)
    route = respx.post('https://api.resend.com/emails').mock(return_value=httpx.Response(200, json={'id': 'bad'}))
    with pytest.raises(DeliveryError, match='durable'):
        deliver(config, 'html', 'text', '2026-01-15', test_id='remote-pending')
    assert route.call_count == 0


@respx.mock
def test_gmail_multipart_and_minimum_scope(config, credentials):
    config['email']['provider'] = 'gmail'
    respx.post('https://oauth2.googleapis.com/token').mock(return_value=httpx.Response(200,
        json={'access_token': 'test-access', 'scope': 'https://www.googleapis.com/auth/gmail.send'}))
    route = respx.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send').mock(
        return_value=httpx.Response(200, json={'id': 'gmail-123'}))
    deliver(config, '<p>中文</p>', '中文', '2026-01-15', test_id='gmail')
    raw = json.loads(route.calls[0].request.content)['raw']
    message = message_from_bytes(base64.urlsafe_b64decode(raw))
    assert message.is_multipart()
    assert {p.get_content_type() for p in message.get_payload()} == {'text/plain', 'text/html'}


@respx.mock
def test_gmail_rejects_broader_permissions(config, credentials):
    config['email']['provider'] = 'gmail'
    respx.post('https://oauth2.googleapis.com/token').mock(return_value=httpx.Response(200,
        json={'access_token': 'test', 'scope': 'https://mail.google.com/'}))
    with pytest.raises(DeliveryError, match='gmail.send'):
        deliver(config, 'html', 'text', '2026-01-15', test_id='too-broad')


@respx.mock
def test_next_day_event_coverage_is_allowed(config, credentials):
    config['newsletter']['delivery_enabled'] = True
    route = respx.post('https://api.resend.com/emails').mock(return_value=httpx.Response(200, json={'id': 'mail'}))
    deliver(config, 'same ongoing event', 'text', '2026-01-15')
    deliver(config, 'same ongoing event', 'text', '2026-01-16')
    assert route.call_count == 2


@respx.mock
def test_provider_switch_does_not_duplicate_daily_email(config, credentials):
    config['newsletter']['delivery_enabled'] = True
    route = respx.post('https://api.resend.com/emails').mock(return_value=httpx.Response(200, json={'id': 'mail'}))
    deliver(config, 'html', 'text', '2026-01-15')
    config['email']['provider'] = 'gmail'
    result = deliver(config, 'html', 'text', '2026-01-15')
    assert result['status'] == 'duplicate' and route.call_count == 1
