from datetime import datetime

from django.utils import timezone

from .models import EmailAccount, SyncedEmail
from .services import _guess_links, cleanup_stored_emails, message_hash, DeletedEmailMarker, queue_auto_schedule_analysis


def register_outlook_account(user, data):
    address = str(data.get('email_address', '')).strip()
    if '@' not in address:
        raise ValueError('Host agent did not return a valid Outlook address.')
    account, _ = EmailAccount.objects.update_or_create(
        user=user, provider=EmailAccount.Provider.OUTLOOK_LOCAL, email_address=address,
        defaults={'scopes': ['local:Mail.Read'], 'status': EmailAccount.Status.ACTIVE, 'error_message': ''},
    )
    return {'account_id': account.pk, 'email_address': account.email_address}


def save_outlook_messages(account, messages):
    if not account or account.provider != EmailAccount.Provider.OUTLOOK_LOCAL:
        raise ValueError('Invalid local Outlook account.')
    created_ids = []
    for item in messages[:100]:
        entry_id = str(item.get('id', ''))
        if not entry_id or DeletedEmailMarker.objects.filter(account=account, message_hash=message_hash(entry_id), expires_at__gt=timezone.now()).exists():
            continue
        received_at = datetime.fromisoformat(str(item['received_at']).replace('Z', '+00:00'))
        if timezone.is_naive(received_at):
            received_at = timezone.make_aware(received_at)
        sender = str(item.get('sender', account.email_address))[:254]
        company, contact, application = _guess_links(account, sender, str(item.get('subject', '')))
        email, created = SyncedEmail.objects.update_or_create(
            account=account, provider_message_id=entry_id,
            defaults={'thread_id': str(item.get('thread_id', ''))[:255], 'direction': SyncedEmail.Direction.INBOUND,
                      'sender': sender if '@' in sender else account.email_address, 'recipients': item.get('recipients', [])[:50],
                      'subject': str(item.get('subject', ''))[:500], 'body_text': str(item.get('body_text', ''))[:50000],
                      'folder_name': str(item.get('folder_name', 'Inbox'))[:255], 'is_read': bool(item.get('is_read')),
                      'has_attachments': bool(item.get('has_attachments')), 'received_at': received_at,
                      'company': company, 'contact': contact, 'application': application},
        )
        if created:
            created_ids.append(email.pk)
    account.last_synced_at = timezone.now()
    account.status = EmailAccount.Status.ACTIVE
    account.error_message = ''
    account.save(update_fields=('last_synced_at', 'status', 'error_message', 'updated_at'))
    cleanup_stored_emails()
    queue_auto_schedule_analysis(account, created_ids)
    return {'imported': len(created_ids)}
