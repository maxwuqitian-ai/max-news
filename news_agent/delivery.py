"""Fail-closed delivery ledger: uncertainty is never automatically retried."""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import fcntl
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import httpx

LOG = logging.getLogger(__name__)


class DeliveryError(RuntimeError): pass


def required(name):
    value = os.environ.get(name)
    if not value: raise DeliveryError(f'Missing {name}')
    return value


def address(value):
    # Prevent header injection and accidental multiple recipients.
    if any(c in value for c in '\r\n,;') or '@' not in parseaddr(value)[1]:
        raise DeliveryError('Invalid single email address')
    return value


def atomic_json(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.tmp-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally:
        if os.path.exists(name): os.unlink(name)


@contextmanager
def locked_state(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'delivery.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / 'deliveries.json'
        ledger = json.loads(path.read_text()) if path.exists() else {}
        yield path, ledger


def sync_state():
    # Actions must persist pending state remotely BEFORE calling the mail API.
    # Locally, fsync plus advisory locking provides the same single-machine protection.
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        if os.environ.get('NEWS_DURABLE_STATE') != 'true':
            raise DeliveryError('Actions delivery requires durable state branch initialization')
        subprocess.run(['python', 'scripts/state_branch.py', 'push'], check=True)


def gmail_credentials(client):
    response = client.post('https://oauth2.googleapis.com/token', data={
        'client_id': required('GMAIL_CLIENT_ID'), 'client_secret': required('GMAIL_CLIENT_SECRET'),
        'refresh_token': required('GMAIL_REFRESH_TOKEN'), 'grant_type': 'refresh_token'})
    response.raise_for_status()
    data = response.json()
    scopes = set(data.get('scope', '').split())
    if scopes and scopes != {'https://www.googleapis.com/auth/gmail.send'}:
        raise DeliveryError('Gmail OAuth must use only gmail.send permission')
    return data['access_token']


def delivery_key(recipient, edition_date, test_id=None):
    return ('test:' + test_id if test_id else 'daily:' + edition_date) + ':' + sha256(recipient.casefold().encode()).hexdigest()[:16]


def already_attempted(config, edition_date):
    recipient = address(required(config['newsletter']['recipient_env']))
    with locked_state(config['newsletter']['state_dir']) as (_, ledger):
        return ledger.get(delivery_key(recipient, edition_date))


def deliver(config, html, text, edition_date, *, test_id=None, client=None):
    recipient = address(required(config['newsletter']['recipient_env']))
    provider = config['email']['provider']
    subject = config['newsletter']['subject'] + ' · ' + edition_date
    if test_id:
        if not all(c.isalnum() or c in '-_' for c in test_id) or len(test_id) > 80:
            raise DeliveryError('test-id must contain 1–80 letters, numbers, hyphens or underscores')
        subject = '[测试] ' + subject
    elif not config['newsletter']['delivery_enabled']:
        raise DeliveryError('Recurring delivery disabled; first review a sample and run send-test')
    # Same daily identity across providers prevents a provider switch from duplicating the edition.
    key = delivery_key(recipient, edition_date, test_id)
    owns = client is None
    client = client or httpx.Client(timeout=45)
    try:
        with locked_state(config['newsletter']['state_dir']) as (path, ledger):
            existing = ledger.get(key)
            if existing:
                if existing['status'] == 'sent':
                    LOG.info('Duplicate delivery skipped key=%s', key)
                    return {'status': 'duplicate', 'key': key}
                raise DeliveryError(f'Delivery {key} is pending/uncertain; reconcile before another attempt')
            # Validate credentials and refresh Gmail access BEFORE reserving the email.
            if provider == 'resend':
                api_key = required(config['email']['resend_api_key_env'])
                sender = address(required(config['email']['sender_env']))
                url = 'https://api.resend.com/emails'
                headers = {'Authorization': 'Bearer ' + api_key,
                           'Idempotency-Key': sha256(key.encode()).hexdigest()}
                payload = {'from': sender, 'to': [recipient], 'subject': subject, 'html': html, 'text': text}
            elif provider == 'gmail':
                token = gmail_credentials(client)
                message = EmailMessage()
                message['To'] = recipient
                message['Subject'] = subject
                message['Message-ID'] = f'<{sha256(key.encode()).hexdigest()}@global-daily-news.local>'
                message.set_content(text)
                message.add_alternative(html, subtype='html')
                url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
                headers = {'Authorization': 'Bearer ' + token}
                payload = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
            else: raise DeliveryError('Unsupported email provider')
            ledger[key] = {'status': 'pending', 'provider': provider, 'date': edition_date,
                           'attempted_at': datetime.now(timezone.utc).isoformat()}
            atomic_json(path, ledger)
            sync_state()  # If this fails, abort before sending.
            try:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                message_id = response.json().get('id')
                if not message_id: raise DeliveryError('Mail API response lacks message ID')
            except (httpx.HTTPError, ValueError, DeliveryError) as exc:
                ledger[key]['status'] = 'uncertain'
                ledger[key]['error_type'] = type(exc).__name__
                atomic_json(path, ledger)
                sync_state()
                raise DeliveryError('Mail API failed or result is uncertain; automatic resend blocked') from exc
            ledger[key].update(status='sent', message_id=message_id,
                               sent_at=datetime.now(timezone.utc).isoformat())
            atomic_json(path, ledger)
            sync_state()  # A failure leaves remote pending, preventing duplicate delivery.
            LOG.info('Mail accepted provider=%s message_id=%s key=%s', provider, message_id, key)
            return {'status': 'sent', 'message_id': message_id, 'key': key}
    finally:
        if owns: client.close()
