from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    url = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=('user', 'is_read', 'created_at'), name='notif_user_unread_idx')]


class Reminder(models.Model):
    class Kind(models.TextChoices):
        DEADLINE = 'deadline', '职位截止'
        INTERVIEW = 'interview', '面试'
        FOLLOW_UP = 'follow_up', '投递跟进'

    class Status(models.TextChoices):
        PENDING = 'pending', '等待发送'
        SENT = 'sent', '已发送'
        FAILED = 'failed', '发送失败'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reminders')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    object_key = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    message = models.TextField()
    url = models.CharField(max_length=500, blank=True)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('user', 'kind', 'object_key', 'scheduled_at'), name='unique_scheduled_reminder')]
        indexes = [models.Index(fields=('status', 'scheduled_at'), name='reminder_due_idx')]
