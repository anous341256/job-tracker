import base64
import hashlib
import json
import re
import sys
import mimetypes
import tempfile
from pathlib import Path
from datetime import timezone as datetime_timezone
from email.message import EmailMessage

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files import File
from django.utils import timezone

from productivity.models import Communication, Contact
from productivity.models import Document
from .models import DeletedEmailMarker, EmailAccount, SyncedEmail


def _looks_like_schedule_email(email):
    """Cheap pre-filter for mail worth sending to the schedule extractor.

    This only avoids sending unrelated newsletters to the local model. The
    model remains responsible for deciding whether a real event exists.
    """
    value = f'{email.subject}\n{email.body_text[:8000]}'.casefold()
    signals = (
        'interview', 'meeting', 'appointment', 'schedule', 'calendar',
        'webinar', 'briefing', 'assessment', 'test center', 'deadline',
        'due date', 'teams.microsoft.com', 'zoom.us',
        '面试', '面談', '会议', '會議', '日程', '预约', '預約', '说明会', '說明會',
        '笔试', '筆試', '测评', '測評', '适性検査', '適性検査', '截止', '提交期限',
        '面接', '面談', '面会', '会議', '候補日', '予約', '説明会', 'セミナー',
        'ウェビナー', '筆記試験', '試験', '締切', '提出期限', '受検',
        'カジュアル面談', 'ミーティング',
        'resume', 'curriculum vitae', 'cv upload', 'upload your cv',
        'submit', 'submission', 'upload', 'complete the form', 'fill out',
        'reply by', 'respond by', 'action required', 'aptitude test',
        '简历', '履历', '履歷', '提交', '上传', '上傳', '填写', '填寫',
        '请回复', '請回覆', '适性检查', '適性檢查', '测验', '測驗',
        '履歴書', 'エントリーシート', '提出', 'アップロード', '入力してください',
        'ご返信', '返信期限', '受検してください', '受験してください', '対応期限',
    )
    if any(signal.casefold() in value for signal in signals):
        return True
    # Some recruiters write only a terse date/time without words such as
    # “interview”. Require both a date-like and a time-like token to keep the
    # automatic pre-filter conservative.
    date_like = re.search(
        r'(?:20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{1,2}月\d{1,2}日|'
        r'\b(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?\b|'
        r'(?:明天|后天|下周[一二三四五六日天]|tomorrow|next\s+(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?))',
        value,
        re.IGNORECASE,
    )
    time_like = re.search(r'(?:\b(?:[01]?\d|2[0-3]):[0-5]\d\b|(?:上午|下午|午前|午後)\s*\d{1,2}(?:[:点時]\d{1,2})?)', value)
    return bool(date_like and time_like)


def queue_auto_schedule_analysis(account, email_ids):
    """Queue only new, likely-relevant local copies; never blocks a mail sync."""
    if not email_ids:
        return
    try:
        from ai_assistant.models import AISettings
        from ai_assistant.services import create_email_schedule_task
        settings_obj, _ = AISettings.objects.get_or_create(user=account.user)
        if not settings_obj.email_schedule_auto_enabled:
            return
        emails = SyncedEmail.objects.filter(pk__in=email_ids, account=account).order_by('-received_at')[:settings_obj.email_schedule_auto_limit]
        for email in emails:
            if _looks_like_schedule_email(email):
                # Mail Assistant v1 is deliberately local-only. Email content
                # never falls through to a cloud provider during auto analysis.
                create_email_schedule_task(user=account.user, email=email, provider=AISettings.Provider.OLLAMA)
    except Exception:
        # Sync is the primary operation. Configuration/model errors must not fail it.
        return


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


def message_hash(provider_message_id):
    return hashlib.sha256(provider_message_id.encode('utf-8')).hexdigest()


def mark_and_delete_email(email):
    DeletedEmailMarker.objects.update_or_create(
        account=email.account,
        message_hash=message_hash(email.provider_message_id),
        defaults={'expires_at': timezone.now() + timezone.timedelta(days=45)},
    )
    email.delete()


def cleanup_stored_emails():
    """Bound local storage while preserving all manually linked messages."""
    now = timezone.now()
    DeletedEmailMarker.objects.filter(expires_at__lte=now).delete()
    unlinked = SyncedEmail.objects.filter(company__isnull=True, application__isnull=True, contact__isnull=True)
    unlinked.filter(received_at__lt=now - timezone.timedelta(days=180)).delete()
    for account_id in EmailAccount.objects.values_list('id', flat=True):
        excess_ids = list(
            unlinked.filter(account_id=account_id).order_by('-received_at').values_list('id', flat=True)[1000:]
        )
        if excess_ids:
            SyncedEmail.objects.filter(id__in=excess_ids).delete()


def sync_account(account):
    if account.provider == EmailAccount.Provider.OUTLOOK_LOCAL:
        return sync_local_outlook(account)
    new_ids = []
    token = refresh_access_token(account)
    headers = {'Authorization': f'Bearer {token}'}
    if account.provider == 'gmail':
        listing = requests.get('https://gmail.googleapis.com/gmail/v1/users/me/messages', headers=headers, params={'maxResults': 50, 'q': 'newer_than:30d'}, timeout=30).json()
        for item in listing.get('messages', []):
            data = requests.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}", headers=headers, params={'format': 'metadata', 'metadataHeaders': ['From', 'To', 'Subject', 'Date']}, timeout=30).json()
            values = {h['name'].lower(): h['value'] for h in data.get('payload', {}).get('headers', [])}
            sender = values.get('from', '')[-254:]
            company, contact, application = _guess_links(account, sender, values.get('subject', ''))
            email, created = SyncedEmail.objects.update_or_create(account=account, provider_message_id=item['id'], defaults={'thread_id': data.get('threadId', ''), 'direction': SyncedEmail.Direction.INBOUND, 'sender': sender if '@' in sender else account.email_address, 'recipients': [values.get('to', '')], 'subject': values.get('subject', ''), 'body_text': data.get('snippet', ''), 'received_at': timezone.datetime.fromtimestamp(int(data.get('internalDate', '0')) / 1000, tz=datetime_timezone.utc), 'company': company, 'contact': contact, 'application': application})
            if created: new_ids.append(email.pk)
    else:
        response = requests.get('https://graph.microsoft.com/v1.0/me/messages', headers=headers, params={'$top': 50, '$select': 'id,conversationId,subject,bodyPreview,from,toRecipients,receivedDateTime'}, timeout=30)
        response.raise_for_status()
        for data in response.json().get('value', []):
            sender = data.get('from', {}).get('emailAddress', {}).get('address', account.email_address)
            company, contact, application = _guess_links(account, sender, data.get('subject', ''))
            email, created = SyncedEmail.objects.update_or_create(account=account, provider_message_id=data['id'], defaults={'thread_id': data.get('conversationId', ''), 'direction': SyncedEmail.Direction.INBOUND, 'sender': sender, 'recipients': [x['emailAddress']['address'] for x in data.get('toRecipients', [])], 'subject': data.get('subject', ''), 'body_text': data.get('bodyPreview', ''), 'received_at': timezone.datetime.fromisoformat(data['receivedDateTime'].replace('Z', '+00:00')), 'company': company, 'contact': contact, 'application': application})
            if created: new_ids.append(email.pk)
    account.last_synced_at = timezone.now(); account.status = EmailAccount.Status.ACTIVE; account.error_message = ''; account.save(update_fields=('last_synced_at', 'status', 'error_message', 'updated_at'))
    cleanup_stored_emails()
    queue_auto_schedule_analysis(account, new_ids)


def _local_outlook_namespace():
    if sys.platform != 'win32':
        raise RuntimeError('本机 Outlook 同步仅支持 Windows。')
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError('缺少 pywin32，无法连接本机 Outlook。') from exc
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch('Outlook.Application')
    return pythoncom, outlook.GetNamespace('MAPI')


def local_outlook_identity():
    """获取默认 SMTP 地址，不读取任何邮件内容。"""
    pythoncom, namespace = _local_outlook_namespace()
    try:
        for local_account in namespace.Accounts:
            address = str(getattr(local_account, 'SmtpAddress', '') or '').strip()
            if '@' in address:
                return address
        return 'local-outlook@localhost'
    finally:
        pythoncom.CoUninitialize()


def _outlook_sender_address(item, fallback):
    address = str(getattr(item, 'SenderEmailAddress', '') or '').strip()
    if getattr(item, 'SenderEmailType', '') == 'EX':
        try:
            exchange_user = item.Sender.GetExchangeUser()
            address = str(exchange_user.PrimarySmtpAddress or address)
        except Exception:
            pass
    return address if '@' in address else fallback


def sync_local_outlook(account, *, limit=50, days=30):
    """只读同步经典 Outlook 的近期邮件，不修改邮箱中的任何对象。"""
    pythoncom, namespace = _local_outlook_namespace()
    imported = 0
    new_ids = []
    cutoff = timezone.now() - timezone.timedelta(days=days)
    try:
        folder = namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
        if account.sync_folder and account.sync_folder.lower() != 'inbox':
            try:
                folder = folder.Folders.Item(account.sync_folder)
            except Exception as exc:
                raise RuntimeError(f'找不到 Outlook 文件夹：{account.sync_folder}') from exc
        items = folder.Items
        items.Sort('[ReceivedTime]', True)
        scanned = 0
        for item in items:
            if scanned >= 250 or imported >= limit:
                break
            scanned += 1
            if getattr(item, 'Class', None) != 43:  # 43 = olMail
                continue
            received_at = getattr(item, 'ReceivedTime', None)
            if not received_at:
                continue
            if timezone.is_naive(received_at):
                received_at = timezone.make_aware(received_at)
            if received_at < cutoff:
                break
            entry_id = str(item.EntryID)
            if DeletedEmailMarker.objects.filter(account=account, message_hash=message_hash(entry_id), expires_at__gt=timezone.now()).exists():
                continue
            sender = _outlook_sender_address(item, account.email_address)
            subject = str(getattr(item, 'Subject', '') or '')[:500]
            company, contact, application = _guess_links(account, sender, subject)
            recipients = []
            try:
                recipients = [str(r.Address) for r in item.Recipients if getattr(r, 'Address', None)]
            except Exception:
                pass
            _, created = SyncedEmail.objects.update_or_create(
                account=account,
                provider_message_id=entry_id,
                defaults={
                    'thread_id': str(getattr(item, 'ConversationID', '') or ''),
                    'direction': SyncedEmail.Direction.INBOUND,
                    'sender': sender,
                    'recipients': recipients,
                    'subject': subject,
                    # Outlook Body is plain text. Keep a generous cap so the
                    # built-in reader is useful without storing unbounded data.
                    'body_text': str(getattr(item, 'Body', '') or '')[:50000],
                    'folder_name': account.sync_folder or 'Inbox',
                    'is_read': not bool(getattr(item, 'UnRead', False)),
                    'has_attachments': bool(getattr(getattr(item, 'Attachments', None), 'Count', 0)),
                    'received_at': received_at,
                    'company': company,
                    'contact': contact,
                    'application': application,
                },
            )
            imported += int(created)
            if created:
                new_ids.append(email.pk)
        account.last_synced_at = timezone.now()
        account.status = EmailAccount.Status.ACTIVE
        account.error_message = ''
        account.sync_cursor = timezone.now().isoformat()
        account.save(update_fields=('last_synced_at', 'status', 'error_message', 'sync_cursor', 'updated_at'))
        cleanup_stored_emails()
        queue_auto_schedule_analysis(account, new_ids)
        return imported
    finally:
        pythoncom.CoUninitialize()


def list_local_attachments(email):
    if email.account.provider != EmailAccount.Provider.OUTLOOK_LOCAL:
        return []
    pythoncom, namespace = _local_outlook_namespace()
    try:
        item = namespace.GetItemFromID(email.provider_message_id)
        return [{'index': index, 'name': str(item.Attachments.Item(index).FileName), 'size': int(item.Attachments.Item(index).Size or 0)} for index in range(1, item.Attachments.Count + 1)]
    finally:
        pythoncom.CoUninitialize()


def import_local_attachment(email, index):
    allowed = {'.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg', '.txt'}
    pythoncom, namespace = _local_outlook_namespace()
    try:
        item = namespace.GetItemFromID(email.provider_message_id)
        if index < 1 or index > item.Attachments.Count:
            raise RuntimeError('附件不存在。')
        attachment = item.Attachments.Item(index)
        name = Path(str(attachment.FileName)).name
        if Path(name).suffix.lower() not in allowed:
            raise RuntimeError('该附件类型不允许导入资料库。')
        if int(attachment.Size or 0) > 10 * 1024 * 1024:
            raise RuntimeError('附件不能超过 10 MB。')
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / name
            attachment.SaveAsFile(str(temp_path))
            with temp_path.open('rb') as stream:
                document = Document(
                    user=email.account.user,
                    company=email.company,
                    application=email.application,
                    document_type=Document.Type.OTHER,
                    original_name=name,
                    mime_type=mimetypes.guess_type(name)[0] or 'application/octet-stream',
                    description=f'从邮件“{email.subject}”导入',
                )
                document.file.save(name, File(stream), save=True)
                return document
    finally:
        pythoncom.CoUninitialize()


def send_message(account, *, to, subject, body, application=None):
    if account.provider == EmailAccount.Provider.OUTLOOK_LOCAL:
        raise RuntimeError('本机 Outlook 连接为只读模式，不能发送邮件。')
    token = refresh_access_token(account); headers = {'Authorization': f'Bearer {token}'}
    if account.provider == 'gmail':
        message = EmailMessage(); message['To'] = to; message['From'] = account.email_address; message['Subject'] = subject; message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        response = requests.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', headers={**headers, 'Content-Type': 'application/json'}, json={'raw': raw}, timeout=30)
    else:
        response = requests.post('https://graph.microsoft.com/v1.0/me/sendMail', headers={**headers, 'Content-Type': 'application/json'}, json={'message': {'subject': subject, 'body': {'contentType': 'Text', 'content': body}, 'toRecipients': [{'emailAddress': {'address': to}}]}}, timeout=30)
    response.raise_for_status()
    Communication.objects.create(user=account.user, company=application.job_position.company if application else None, application=application, channel=Communication.Channel.EMAIL, direction=Communication.Direction.OUTBOUND, subject=subject, summary=body, occurred_at=timezone.now())
