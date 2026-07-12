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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AITask(models.Model):
    class Type(models.TextChoices):
        JD_PARSE = 'jd_parse', 'JD 结构化解析'
        JOB_MATCH = 'job_match', '简历职位匹配'

    class Status(models.TextChoices):
        PENDING = 'pending', '等待处理'
        RUNNING = 'running', '处理中'
        SUCCEEDED = 'succeeded', '已完成'
        FAILED = 'failed', '失败'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_tasks')
    task_type = models.CharField(max_length=20, choices=Type.choices)
    provider = models.CharField(max_length=20, choices=AISettings.Provider.choices)
    model = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    job = models.ForeignKey('companies.JobPosition', on_delete=models.CASCADE, related_name='ai_tasks')
    resume = models.ForeignKey('productivity.Resume', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_tasks')
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
        indexes = [models.Index(fields=('user', 'status', 'created_at'), name='ai_task_user_status_idx'), models.Index(fields=('job', 'task_type', 'created_at'), name='ai_task_job_type_idx')]


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
