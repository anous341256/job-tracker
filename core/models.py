from django.conf import settings
from django.db import models
from django.utils import timezone


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


class TodoItem(models.Model):
    class Status(models.TextChoices):
        TODO = 'todo', '未开始'
        IN_PROGRESS = 'in_progress', '进行中'
        DONE = 'done', '已完成'
        BLOCKED = 'blocked', '受阻'

    class Priority(models.TextChoices):
        LOW = 'low', '低'
        MEDIUM = 'medium', '中'
        HIGH = 'high', '高'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='todo_items')
    company = models.ForeignKey(
        'companies.Company', on_delete=models.PROTECT, related_name='todo_items',
        verbose_name='公司',
    )
    job_position = models.ForeignKey(
        'companies.JobPosition', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='todo_items', verbose_name='关联职位',
    )
    application = models.ForeignKey(
        'applications.Application', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='todo_items', verbose_name='关联投递',
    )
    title = models.CharField('任务标题', max_length=200)
    status = models.CharField('状态', max_length=20, choices=Status.choices, default=Status.TODO)
    priority = models.CharField('优先级', max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    due_at = models.DateTimeField('截止时间', null=True, blank=True)
    notes = models.TextField('说明', blank=True)
    source_email = models.ForeignKey(
        'mailboxes.SyncedEmail', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='todo_items', verbose_name='来源邮件',
    )
    source_url = models.URLField('操作链接', max_length=1000, blank=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ('status', 'due_at', '-updated_at')
        indexes = [
            models.Index(fields=('user', 'status', 'due_at'), name='todo_user_status_due_idx'),
        ]

    def __str__(self):
        return self.title

    def mark_done(self):
        self.status = self.Status.DONE
        self.completed_at = timezone.now()
        self.save(update_fields=('status', 'completed_at', 'updated_at'))

    def reopen(self):
        self.status = self.Status.TODO
        self.completed_at = None
        self.save(update_fields=('status', 'completed_at', 'updated_at'))


class CalendarEvent(models.Model):
    class Type(models.TextChoices):
        CALL = 'call', '电话/视频沟通'
        ASSESSMENT = 'assessment', '笔试/测评'
        BRIEFING = 'briefing', '说明会'
        ES_DEADLINE = 'es_deadline', 'ES 截止'
        INTERVIEW = 'interview', '面试'
        OTHER = 'other', '其他日程'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='calendar_events')
    title = models.CharField(max_length=200)
    event_type = models.CharField(max_length=20, choices=Type.choices, default=Type.OTHER)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=300, blank=True)
    meeting_url = models.URLField(max_length=1000, blank=True)
    participants = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    source_email = models.ForeignKey('mailboxes.SyncedEmail', on_delete=models.SET_NULL, null=True, blank=True, related_name='calendar_events')
    company = models.ForeignKey('companies.Company', on_delete=models.PROTECT, related_name='calendar_events')
    job_position = models.ForeignKey(
        'companies.JobPosition', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='calendar_events',
    )
    application = models.ForeignKey('applications.Application', on_delete=models.SET_NULL, null=True, blank=True, related_name='calendar_events')
    contact = models.ForeignKey('productivity.Contact', on_delete=models.SET_NULL, null=True, blank=True, related_name='calendar_events')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('starts_at',)
        indexes = [models.Index(fields=('user', 'starts_at'), name='calendar_user_starts_idx')]

    def __str__(self):
        return self.title


class HostAgentHeartbeat(models.Model):
    agent_id = models.CharField(max_length=100, unique=True, default='windows-local')
    version = models.CharField(max_length=30, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    outlook_available = models.BooleanField(default=False)
    ollama_available = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)


class HostAgentCommand(models.Model):
    class Type(models.TextChoices):
        OUTLOOK_CONNECT = 'outlook_connect', 'Outlook 连接'
        OUTLOOK_SYNC = 'outlook_sync', 'Outlook 同步'
        OLLAMA = 'ollama', '本地 Ollama 推理'

    class Status(models.TextChoices):
        QUEUED = 'queued', '等待本机代理'
        RUNNING = 'running', '本机代理处理中'
        SUCCEEDED = 'succeeded', '已完成'
        FAILED = 'failed', '失败'
        EXPIRED = 'expired', '已过期'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='host_agent_commands')
    command_type = models.CharField(max_length=30, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    email_account = models.ForeignKey('mailboxes.EmailAccount', on_delete=models.CASCADE, null=True, blank=True, related_name='host_agent_commands')
    ai_task = models.OneToOneField('ai_assistant.AITask', on_delete=models.CASCADE, null=True, blank=True, related_name='host_agent_command')
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('created_at',)
        indexes = [models.Index(fields=('status', 'created_at'), name='host_agent_queue_idx')]
