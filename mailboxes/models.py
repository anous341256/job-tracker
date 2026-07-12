from django.conf import settings
from django.db import models

from applications.models import Application
from companies.models import Company
from productivity.models import Contact


class EmailAccount(models.Model):
    class Provider(models.TextChoices):
        GMAIL = 'gmail', 'Gmail'
        OUTLOOK = 'outlook', 'Outlook'
        OUTLOOK_LOCAL = 'outlook_local', '本机 Outlook（只读）'

    class Status(models.TextChoices):
        ACTIVE = 'active', '已连接'
        EXPIRED = 'expired', '授权过期'
        DISCONNECTED = 'disconnected', '已断开'
        ERROR = 'error', '同步错误'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_accounts')
    provider = models.CharField(max_length=20, choices=Provider.choices)
    email_address = models.EmailField()
    encrypted_access_token = models.TextField(blank=True)
    encrypted_refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list)
    sync_cursor = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    error_message = models.TextField(blank=True)
    sync_folder = models.CharField(max_length=255, default='Inbox')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('user', 'provider', 'email_address'), name='unique_user_email_provider')]


class SyncedEmail(models.Model):
    class Direction(models.TextChoices):
        INBOUND = 'inbound', '收到'
        OUTBOUND = 'outbound', '发出'

    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='messages')
    provider_message_id = models.CharField(max_length=255)
    thread_id = models.CharField(max_length=255, blank=True)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    sender = models.EmailField()
    recipients = models.JSONField(default=list)
    subject = models.CharField(max_length=500, blank=True)
    body_text = models.TextField(blank=True)
    folder_name = models.CharField(max_length=255, default='Inbox')
    is_read = models.BooleanField(default=False)
    has_attachments = models.BooleanField(default=False)
    received_at = models.DateTimeField()
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='synced_emails')
    application = models.ForeignKey(Application, on_delete=models.SET_NULL, null=True, blank=True, related_name='synced_emails')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='synced_emails')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('account', 'provider_message_id'), name='unique_provider_message')]
        ordering = ('-received_at',)


class DeletedEmailMarker(models.Model):
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='deleted_markers')
    message_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('account', 'message_hash'), name='unique_deleted_email_marker')]
        indexes = [models.Index(fields=('expires_at',), name='deleted_email_expiry_idx')]
