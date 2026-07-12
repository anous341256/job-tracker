import base64
import hashlib
import json
from datetime import timezone as datetime_timezone
from email.message import EmailMessage

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from productivity.models import Communication, Contact
from .models import EmailAccount, SyncedEmail


def _fernet():
    key = settings.OAUTH_ENCRYPTION_KEY
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_token(value): return _fernet().encrypt(value.encode()).decode() if value else ''
def decrypt_token(value): return _fernet().decrypt(value.encode()).decode() if value else ''


PROVIDERS = {
    'gmail': {
        'authorize': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token': 'https://oauth2.googleapis.com/token',
        'profile': 'https://gmail.googleapis.com/gmail/v1/users/me/profile',
        'scope': 'openid email https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send',
    },
    'outlook': {
        'authorize': f'https://login.microsoftonline.com/{settings.MICROSOFT_TENANT}/oauth2/v2.0/authorize',
        'token': f'https://login.microsoftonline.com/{settings.MICROSOFT_TENANT}/oauth2/v2.0/token',
        'profile': 'https://graph.microsoft.com/v1.0/me',
        'scope': 'openid email offline_access User.Read Mail.Read Mail.Send',
    },
}


def provider_credentials(provider):
    if provider == 'gmail': return settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET
    if provider == 'outlook': return settings.MICROSOFT_CLIENT_ID, settings.MICROSOFT_CLIENT_SECRET
    raise ImproperlyConfigured('不支持的邮箱服务商。')


def refresh_access_token(account):
    if account.token_expires_at and account.token_expires_at > timezone.now() + timezone.timedelta(minutes=2):
        return decrypt_token(account.encrypted_access_token)
    client_id, client_secret = provider_credentials(account.provider)
    response = requests.post(PROVIDERS[account.provider]['token'], data={'client_id': client_id, 'client_secret': client_secret, 'refresh_token': decrypt_token(account.encrypted_refresh_token), 'grant_type': 'refresh_token'}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    account.encrypted_access_token = encrypt_token(payload['access_token'])
    account.token_expires_at = timezone.now() + timezone.timedelta(seconds=payload.get('expires_in', 3600))
    account.save(update_fields=('encrypted_access_token', 'token_expires_at', 'updated_at'))
    return payload['access_token']


def _guess_links(account, sender, subject):
    contact = Contact.objects.filter(user=account.user, email__iexact=sender).select_related('company').first()
    if contact: return contact.company, contact, None
    for application in account.user.applications.select_related('job_position__company'):
        if application.job_position.company.name.lower() in subject.lower():
            return application.job_position.company, None, application
    return None, None, None


def sync_account(account):
    token = refresh_access_token(account)
    headers = {'Authorization': f'Bearer {token}'}
    if account.provider == 'gmail':
        listing = requests.get('https://gmail.googleapis.com/gmail/v1/users/me/messages', headers=headers, params={'maxResults': 50, 'q': 'newer_than:30d'}, timeout=30).json()
        for item in listing.get('messages', []):
            data = requests.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}", headers=headers, params={'format': 'metadata', 'metadataHeaders': ['From', 'To', 'Subject', 'Date']}, timeout=30).json()
            values = {h['name'].lower(): h['value'] for h in data.get('payload', {}).get('headers', [])}
            sender = values.get('from', '')[-254:]
            company, contact, application = _guess_links(account, sender, values.get('subject', ''))
            SyncedEmail.objects.update_or_create(account=account, provider_message_id=item['id'], defaults={'thread_id': data.get('threadId', ''), 'direction': SyncedEmail.Direction.INBOUND, 'sender': sender if '@' in sender else account.email_address, 'recipients': [values.get('to', '')], 'subject': values.get('subject', ''), 'body_text': data.get('snippet', ''), 'received_at': timezone.datetime.fromtimestamp(int(data.get('internalDate', '0')) / 1000, tz=datetime_timezone.utc), 'company': company, 'contact': contact, 'application': application})
    else:
        response = requests.get('https://graph.microsoft.com/v1.0/me/messages', headers=headers, params={'$top': 50, '$select': 'id,conversationId,subject,bodyPreview,from,toRecipients,receivedDateTime'}, timeout=30)
        response.raise_for_status()
        for data in response.json().get('value', []):
            sender = data.get('from', {}).get('emailAddress', {}).get('address', account.email_address)
            company, contact, application = _guess_links(account, sender, data.get('subject', ''))
            SyncedEmail.objects.update_or_create(account=account, provider_message_id=data['id'], defaults={'thread_id': data.get('conversationId', ''), 'direction': SyncedEmail.Direction.INBOUND, 'sender': sender, 'recipients': [x['emailAddress']['address'] for x in data.get('toRecipients', [])], 'subject': data.get('subject', ''), 'body_text': data.get('bodyPreview', ''), 'received_at': timezone.datetime.fromisoformat(data['receivedDateTime'].replace('Z', '+00:00')), 'company': company, 'contact': contact, 'application': application})
    account.last_synced_at = timezone.now(); account.status = EmailAccount.Status.ACTIVE; account.error_message = ''; account.save(update_fields=('last_synced_at', 'status', 'error_message', 'updated_at'))


def send_message(account, *, to, subject, body, application=None):
    token = refresh_access_token(account); headers = {'Authorization': f'Bearer {token}'}
    if account.provider == 'gmail':
        message = EmailMessage(); message['To'] = to; message['From'] = account.email_address; message['Subject'] = subject; message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        response = requests.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', headers={**headers, 'Content-Type': 'application/json'}, json={'raw': raw}, timeout=30)
    else:
        response = requests.post('https://graph.microsoft.com/v1.0/me/sendMail', headers={**headers, 'Content-Type': 'application/json'}, json={'message': {'subject': subject, 'body': {'contentType': 'Text', 'content': body}, 'toRecipients': [{'emailAddress': {'address': to}}]}}, timeout=30)
    response.raise_for_status()
    Communication.objects.create(user=account.user, company=application.job_position.company if application else None, application=application, channel=Communication.Channel.EMAIL, direction=Communication.Direction.OUTBOUND, subject=subject, summary=body, occurred_at=timezone.now())
