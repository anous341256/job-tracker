import uuid

from django.conf import settings
from django.db import models


class AISettings(models.Model):
    class Provider(models.TextChoices):
        OLLAMA = 'ollama', '本地 Ollama'
        OPENAI = 'openai', 'OpenAI API'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_settings')
    default_provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.OLLAMA)
    ollama_url = models.URLField(default='http://127.0.0.1:11434')
    ollama_model = models.CharField(max_length=100, default='qwen3:8b')
    encrypted_openai_api_key = models.TextField(blank=True)
    openai_key_suffix = models.CharField(max_length=4, blank=True)
    openai_key_verified = models.BooleanField(default=False)
    allow_sensitive_cloud = models.BooleanField(default=False)
    openai_fast_model = models.CharField(max_length=100, default='gpt-5.6-luna')
    openai_quality_model = models.CharField(max_length=100, default='gpt-5.6-terra')
    email_schedule_auto_enabled = models.BooleanField(default=False)
    email_schedule_auto_limit = models.PositiveSmallIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class EmailAssistantThread(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待检查'
        IN_REVIEW = 'in_review', '检查中'
        REVIEWED = 'reviewed', '已完成'

    class Resolution(models.TextChoices):
        WITH_SCHEDULE = 'with_schedule', '发现行动事项并已处理'
        NO_SCHEDULE = 'no_schedule', '确认没有行动事项'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_assistant_threads')
    email = models.OneToOneField('mailboxes.SyncedEmail', on_delete=models.CASCADE, related_name='assistant_thread')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    resolution = models.CharField(max_length=20, choices=Resolution.choices, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-last_activity_at',)
        indexes = [models.Index(fields=('user', 'status', 'last_activity_at'), name='email_asst_review_idx')]

    def __str__(self):
        return self.email.subject or f'Email {self.email_id}'


class AITask(models.Model):
    class Type(models.TextChoices):
        JD_PARSE = 'jd_parse', 'JD 结构化解析'
        JOB_MATCH = 'job_match', '简历职位匹配'
        EMAIL_SCHEDULE = 'email_schedule', '邮件日程提取'
        EMAIL_CHAT = 'email_chat', '邮件助手对话'

    class Status(models.TextChoices):
        PENDING = 'pending', '等待处理'
        WAITING_HOST = 'waiting_host', '等待本机代理'
        RUNNING = 'running', '处理中'
        SUCCEEDED = 'succeeded', '已完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_tasks')
    task_type = models.CharField(max_length=20, choices=Type.choices)
    provider = models.CharField(max_length=20, choices=AISettings.Provider.choices)
    model = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    job = models.ForeignKey('companies.JobPosition', on_delete=models.CASCADE, related_name='ai_tasks', null=True, blank=True)
    resume = models.ForeignKey('productivity.Resume', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_tasks')
    email = models.ForeignKey('mailboxes.SyncedEmail', on_delete=models.CASCADE, null=True, blank=True, related_name='ai_tasks')
    email_thread = models.ForeignKey(EmailAssistantThread, on_delete=models.CASCADE, null=True, blank=True, related_name='ai_tasks')
    input_fingerprint = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=30, default='v1')
    input_payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict, blank=True)
    error_type = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    sensitive_cloud_consent = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('user', 'status', 'created_at'), name='ai_task_user_status_idx'),
            models.Index(fields=('job', 'task_type', 'created_at'), name='ai_task_job_type_idx'),
            models.Index(fields=('email', 'task_type', 'created_at'), name='ai_task_email_type_idx'),
        ]


class EmailAssistantMessage(models.Model):
    class Role(models.TextChoices):
        USER = 'user', '用户'
        ASSISTANT = 'assistant', '千问'

    thread = models.ForeignKey(EmailAssistantThread, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    task = models.ForeignKey(AITask, on_delete=models.SET_NULL, null=True, blank=True, related_name='assistant_messages')
    client_request_id = models.UUIDField(null=True, blank=True, unique=True)
    structured_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at', 'pk')
        indexes = [models.Index(fields=('thread', 'created_at'), name='email_asst_msg_idx')]

    def __str__(self):
        return f'{self.get_role_display()}: {self.content[:40]}'


class AIMatchAnalysis(models.Model):
    task = models.OneToOneField(AITask, on_delete=models.CASCADE, related_name='match_analysis')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_match_analyses')
    job = models.ForeignKey('companies.JobPosition', on_delete=models.CASCADE, related_name='ai_match_analyses')
    resume = models.ForeignKey('productivity.Resume', on_delete=models.CASCADE, related_name='ai_match_analyses')
    score = models.PositiveSmallIntegerField()
    summary = models.TextField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)


class EmailScheduleCandidate(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        NEEDS_INFO = 'needs_info', '需要补充'
        APPROVED = 'approved', '已加入日程'
        REJECTED = 'rejected', '已忽略'
        SUPERSEDED = 'superseded', '已被新建议替代'

    class EventType(models.TextChoices):
        INTERVIEW = 'interview', '面试'
        CALL = 'call', '电话/视频沟通'
        ASSESSMENT = 'assessment', '笔试/测评'
        BRIEFING = 'briefing', '说明会'
        FOLLOW_UP = 'follow_up', '跟进事项'
        OTHER = 'other', '其他'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_schedule_candidates')
    email = models.ForeignKey('mailboxes.SyncedEmail', on_delete=models.CASCADE, related_name='schedule_candidates')
    task = models.ForeignKey(AITask, on_delete=models.CASCADE, related_name='schedule_candidates')
    source_message = models.ForeignKey(EmailAssistantMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedule_candidates')
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    title = models.CharField(max_length=200)
    event_type = models.CharField(max_length=20, choices=EventType.choices, default=EventType.OTHER)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    timezone_name = models.CharField(max_length=64, default='Asia/Tokyo')
    location = models.CharField(max_length=300, blank=True)
    meeting_url = models.URLField(max_length=1000, blank=True)
    participants = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)
    evidence = models.TextField(blank=True)
    missing_fields = models.JSONField(default=list, blank=True)
    confidence = models.FloatField(default=0)
    company = models.ForeignKey('companies.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='email_schedule_candidates')
    application = models.ForeignKey('applications.Application', on_delete=models.SET_NULL, null=True, blank=True, related_name='email_schedule_candidates')
    contact = models.ForeignKey('productivity.Contact', on_delete=models.SET_NULL, null=True, blank=True, related_name='email_schedule_candidates')
    created_object_type = models.CharField(max_length=30, blank=True)
    created_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=('user', 'status', 'starts_at'), name='email_schedule_review_idx')]

    def __str__(self):
        return self.title


class EmailTodoCandidate(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        NEEDS_INFO = 'needs_info', '需要补充'
        APPROVED = 'approved', '已创建 To Do'
        REJECTED = 'rejected', '已忽略'
        SUPERSEDED = 'superseded', '已被新建议替代'

    class ActionType(models.TextChoices):
        RESUME_SUBMIT = 'resume_submit', '提交简历'
        DOCUMENT_SUBMIT = 'document_submit', '提交材料'
        ASSESSMENT = 'assessment', '完成适性检查/笔试'
        FORM_FILL = 'form_fill', '填写表单'
        EMAIL_REPLY = 'email_reply', '回复邮件'
        SCHEDULE_BOOKING = 'schedule_booking', '预约时间'
        FOLLOW_UP = 'follow_up', '跟进'
        OTHER = 'other', '其他'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_todo_candidates')
    email = models.ForeignKey('mailboxes.SyncedEmail', on_delete=models.CASCADE, related_name='todo_candidates')
    task = models.ForeignKey(AITask, on_delete=models.CASCADE, related_name='todo_candidates')
    source_message = models.ForeignKey(EmailAssistantMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name='todo_candidates')
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    title = models.CharField(max_length=200)
    action_type = models.CharField(max_length=30, choices=ActionType.choices, default=ActionType.OTHER)
    due_at = models.DateTimeField(null=True, blank=True)
    timezone_name = models.CharField(max_length=64, default='Asia/Tokyo')
    priority = models.CharField(max_length=10, choices=(('low', '低'), ('medium', '中'), ('high', '高')), default='medium')
    action_url = models.URLField(max_length=1000, blank=True)
    notes = models.TextField(blank=True)
    evidence = models.TextField(blank=True)
    missing_fields = models.JSONField(default=list, blank=True)
    confidence = models.FloatField(default=0)
    company = models.ForeignKey('companies.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='email_todo_candidates')
    job_position = models.ForeignKey('companies.JobPosition', on_delete=models.SET_NULL, null=True, blank=True, related_name='email_todo_candidates')
    application = models.ForeignKey('applications.Application', on_delete=models.SET_NULL, null=True, blank=True, related_name='email_todo_candidates')
    created_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=('user', 'status', 'due_at'), name='email_todo_review_idx')]

    def __str__(self):
        return self.title
