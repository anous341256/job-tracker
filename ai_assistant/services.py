import hashlib
import re
import uuid
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .crypto import decrypt_api_key
from .models import (
    AIMatchAnalysis,
    AISettings,
    AITask,
    EmailAssistantMessage,
    EmailAssistantThread,
    EmailScheduleCandidate,
    EmailTodoCandidate,
)
from .prompts import (
    PROMPT_VERSION,
    build_email_assistant_prompt,
    build_email_schedule_prompt,
    build_jd_prompt,
    build_match_prompt,
)
from .providers import OllamaProvider, OpenAIProvider
from .schemas import EmailAssistantResult, EmailScheduleResult, JDParseResult, JobMatchResult


ACTIVE_STATUSES = (AITask.Status.PENDING, AITask.Status.WAITING_HOST, AITask.Status.RUNNING)


def user_ai_settings(user):
    settings_obj, _ = AISettings.objects.get_or_create(user=user)
    return settings_obj


def select_model(settings_obj, task_type, provider):
    if provider == AISettings.Provider.OLLAMA:
        return settings_obj.ollama_model
    return settings_obj.openai_fast_model if task_type in (AITask.Type.JD_PARSE, AITask.Type.EMAIL_SCHEDULE) else settings_obj.openai_quality_model


def get_or_create_email_thread(*, user, email):
    if email.account.user_id != user.id:
        raise ValueError('不能访问其他用户的邮件。')
    thread, _ = EmailAssistantThread.objects.get_or_create(user=user, email=email)
    return thread


def create_ai_task(*, user, task_type, job, provider, source_text='', resume=None):
    settings_obj = user_ai_settings(user)
    if provider == AISettings.Provider.OPENAI:
        if not settings_obj.encrypted_openai_api_key or not settings_obj.openai_key_verified:
            raise ValueError('请先在 AI 设置中保存并验证 OpenAI API Key。')
        if task_type == AITask.Type.JOB_MATCH and not settings_obj.allow_sensitive_cloud:
            raise ValueError('请先授权简历内容发送到 OpenAI，或改用本地 Ollama。')
    fingerprint_source = f'{task_type}|{job.pk}|{resume.pk if resume else ""}|{source_text}'
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
    with transaction.atomic():
        existing = AITask.objects.select_for_update().filter(
            user=user, task_type=task_type, job=job, resume=resume, status__in=ACTIVE_STATUSES,
        ).first()
        if existing:
            return existing, False
        task = AITask.objects.create(
            user=user,
            task_type=task_type,
            provider=provider,
            model=select_model(settings_obj, task_type, provider),
            job=job,
            resume=resume,
            input_fingerprint=fingerprint,
            prompt_version=PROMPT_VERSION,
            input_payload={'source_text': source_text} if task_type == AITask.Type.JD_PARSE else {},
            sensitive_cloud_consent=provider == AISettings.Provider.OPENAI and settings_obj.allow_sensitive_cloud,
        )
    from .tasks import execute_ai_task
    execute_ai_task.delay(str(task.pk))
    return task, True


def create_email_schedule_task(*, user, email, provider=None):
    if email.account.user_id != user.id:
        raise ValueError('不能分析其他用户的邮件。')
    settings_obj = user_ai_settings(user)
    provider = provider or settings_obj.default_provider
    if provider == AISettings.Provider.OPENAI:
        if not settings_obj.encrypted_openai_api_key or not settings_obj.openai_key_verified:
            raise ValueError('请先在 AI 设置中保存并验证 OpenAI API Key。')
        if not settings_obj.allow_sensitive_cloud:
            raise ValueError('邮件可能包含敏感信息，请先授权云端分析，或改用本地 Ollama。')
    source = f'{email.provider_message_id}|{email.subject}|{email.body_text[:50000]}'
    fingerprint = hashlib.sha256(f'{AITask.Type.EMAIL_SCHEDULE}|{source}'.encode()).hexdigest()
    with transaction.atomic():
        thread = get_or_create_email_thread(user=user, email=email)
        existing = AITask.objects.select_for_update().filter(
            user=user, task_type=AITask.Type.EMAIL_SCHEDULE, email=email, status__in=ACTIVE_STATUSES,
        ).first()
        if existing:
            return existing, False
        task = AITask.objects.create(
            user=user,
            task_type=AITask.Type.EMAIL_SCHEDULE,
            provider=provider,
            model=select_model(settings_obj, AITask.Type.EMAIL_SCHEDULE, provider),
            email=email,
            email_thread=thread,
            input_fingerprint=fingerprint,
            prompt_version=PROMPT_VERSION,
            sensitive_cloud_consent=provider == AISettings.Provider.OPENAI and settings_obj.allow_sensitive_cloud,
        )
    from .tasks import execute_ai_task
    execute_ai_task.delay(str(task.pk))
    return task, True


def create_email_chat_task(*, user, email, content, client_request_id):
    """Persist the user's turn before queueing local Qwen, with retry idempotency."""
    content = str(content or '').strip()
    if not content:
        raise ValueError('请输入要对千问说的话。')
    if len(content) > 2000:
        raise ValueError('单条消息最多 2000 个字符。')
    try:
        request_uuid = uuid.UUID(str(client_request_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError('请求标识无效，请刷新页面后重试。') from exc
    settings_obj = user_ai_settings(user)
    try:
        with transaction.atomic():
            thread = get_or_create_email_thread(user=user, email=email)
            thread = EmailAssistantThread.objects.select_for_update().get(pk=thread.pk, user=user)
            existing_message = EmailAssistantMessage.objects.select_related('task').filter(
                thread=thread, client_request_id=request_uuid,
            ).first()
            if existing_message:
                return existing_message.task, False
            active = AITask.objects.select_for_update().filter(
                user=user, email_thread=thread, task_type=AITask.Type.EMAIL_CHAT, status__in=ACTIVE_STATUSES,
            ).first()
            if active:
                raise ValueError('千问正在处理上一条消息，请稍候。')
            fingerprint = hashlib.sha256(f'{thread.pk}|{request_uuid}|{content}'.encode()).hexdigest()
            task = AITask.objects.create(
                user=user,
                task_type=AITask.Type.EMAIL_CHAT,
                provider=AISettings.Provider.OLLAMA,
                model=settings_obj.ollama_model or 'qwen3:8b',
                email=email,
                email_thread=thread,
                input_fingerprint=fingerprint,
                prompt_version=PROMPT_VERSION,
            )
            message = EmailAssistantMessage.objects.create(
                thread=thread,
                role=EmailAssistantMessage.Role.USER,
                content=content,
                task=task,
                client_request_id=request_uuid,
            )
            task.input_payload = {'message_id': message.pk}
            task.save(update_fields=('input_payload',))
            thread.status = EmailAssistantThread.Status.IN_REVIEW
            thread.resolution = ''
            thread.reviewed_at = None
            thread.save(update_fields=('status', 'resolution', 'reviewed_at', 'last_activity_at'))
    except IntegrityError:
        existing_message = EmailAssistantMessage.objects.select_related('task').filter(
            thread__user=user,
            client_request_id=request_uuid,
        ).first()
        if existing_message:
            return existing_message.task, False
        raise
    from .tasks import execute_ai_task
    execute_ai_task.delay(str(task.pk))
    return task, True


def provider_for(task):
    settings_obj = user_ai_settings(task.user)
    if task.provider == AISettings.Provider.OLLAMA:
        return OllamaProvider(settings_obj.ollama_url)
    return OpenAIProvider(decrypt_api_key(settings_obj.encrypted_openai_api_key))


def host_agent_ollama_request(task):
    """Build transient invocation data. Full prompts are never stored in commands."""
    if task.task_type == AITask.Type.JD_PARSE:
        prompt, schema = build_jd_prompt(task.input_payload.get('source_text', '')), JDParseResult
    elif task.task_type == AITask.Type.JOB_MATCH:
        prompt, schema = match_prompt(task), JobMatchResult
    elif task.task_type == AITask.Type.EMAIL_CHAT:
        prompt, schema = email_assistant_prompt(task), EmailAssistantResult
    else:
        prompt, schema = email_schedule_prompt(task), EmailScheduleResult
    system_prompt = __import__('ai_assistant.prompts', fromlist=['SYSTEM_PROMPT']).SYSTEM_PROMPT
    return {
        'task_id': str(task.pk),
        'model': task.model,
        'prompt': prompt,
        'schema': schema.model_json_schema(),
        'system_prompt': system_prompt,
    }


def extract_resume_text(resume):
    path = Path(resume.file.path)
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
    elif suffix == '.docx':
        from docx import Document
        text = '\n'.join(paragraph.text for paragraph in Document(str(path)).paragraphs)
    elif suffix == '.doc':
        raise ValueError('旧版 .doc 暂不支持，请转换为 PDF 或 DOCX。')
    else:
        raise ValueError('该简历格式暂不支持 AI 分析。')
    text = text.strip()
    if not text:
        raise ValueError('无法从简历中提取文字。')
    return text[:40000]


def redact_contact_details(text):
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[EMAIL REDACTED]', text)
    return re.sub(r'(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)', '[PHONE REDACTED]', text)


def match_prompt(task):
    resume_text = extract_resume_text(task.resume)
    if task.provider == AISettings.Provider.OPENAI:
        resume_text = redact_contact_details(resume_text)
    job = task.job
    job_data = {
        'title': job.title,
        'company': job.company.name,
        'description': job.description,
        'requirements': job.requirements,
        'benefits': job.benefits,
        'metadata': job.ai_metadata,
    }
    profile = getattr(task.user, 'profile', None)
    profile_data = {'target_role': getattr(profile, 'target_role', ''), 'location': getattr(profile, 'location', '')}
    return build_match_prompt(job_data=job_data, profile_data=profile_data, resume_text=resume_text)


def _email_body_for_prompt(body):
    body = body or ''
    if len(body) <= 20000:
        return body
    return f'{body[:12000]}\n\n[中间内容已省略]\n\n{body[-8000:]}'


def _email_prompt_data(email):
    application = email.application if email.application_id else None
    return {
        'subject': email.subject,
        'sender': email.sender,
        'recipients': email.recipients,
        'received_at': email.received_at.isoformat(),
        'body_text': _email_body_for_prompt(email.body_text),
        'linked_company': getattr(email.company, 'name', ''),
        'linked_job': application.job_position.title if application else '',
        'linked_application': str(application) if application else '',
        'linked_contact': str(email.contact) if email.contact_id else '',
    }


def email_schedule_prompt(task):
    profile = getattr(task.user, 'profile', None)
    return build_email_schedule_prompt(
        email_data=_email_prompt_data(task.email),
        user_timezone=getattr(profile, 'timezone', 'Asia/Tokyo'),
    )


def email_assistant_prompt(task):
    profile = getattr(task.user, 'profile', None)
    messages = list(task.email_thread.messages.order_by('-created_at', '-pk').values('role', 'content')[:20])
    messages.reverse()
    conversation = [{'role': item['role'], 'content': item['content'][:2000]} for item in messages]
    schedule_candidates = list(
        EmailScheduleCandidate.objects.filter(
            email=task.email,
            status__in=(EmailScheduleCandidate.Status.PENDING, EmailScheduleCandidate.Status.NEEDS_INFO),
        ).order_by('created_at').values(
            'title', 'event_type', 'starts_at', 'ends_at', 'timezone_name',
            'location', 'meeting_url', 'missing_fields', 'confidence',
        )
    )
    for item in schedule_candidates:
        for field in ('starts_at', 'ends_at'):
            if item[field]:
                item[field] = item[field].isoformat()
    todo_candidates = list(
        EmailTodoCandidate.objects.filter(
            email=task.email,
            status__in=(EmailTodoCandidate.Status.PENDING, EmailTodoCandidate.Status.NEEDS_INFO),
        ).order_by('created_at').values(
            'title', 'action_type', 'due_at', 'timezone_name', 'priority',
            'action_url', 'missing_fields', 'confidence',
        )
    )
    for item in todo_candidates:
        if item['due_at']:
            item['due_at'] = item['due_at'].isoformat()
    return build_email_assistant_prompt(
        email_data=_email_prompt_data(task.email),
        user_timezone=getattr(profile, 'timezone', 'Asia/Tokyo'),
        conversation=conversation,
        current_candidates={
            'schedule_candidates': schedule_candidates,
            'todo_candidates': todo_candidates,
        },
    )


def run_task(task):
    provider = provider_for(task)
    if task.task_type == AITask.Type.JD_PARSE:
        return provider.generate(model=task.model, prompt=build_jd_prompt(task.input_payload.get('source_text', '')), schema=JDParseResult)
    if task.task_type == AITask.Type.EMAIL_SCHEDULE:
        return provider.generate(model=task.model, prompt=email_schedule_prompt(task), schema=EmailScheduleResult)
    if task.task_type == AITask.Type.EMAIL_CHAT:
        return provider.generate(model=task.model, prompt=email_assistant_prompt(task), schema=EmailAssistantResult)
    return provider.generate(model=task.model, prompt=match_prompt(task), schema=JobMatchResult)


def save_match_analysis(task):
    AIMatchAnalysis.objects.create(
        task=task,
        user=task.user,
        job=task.job,
        resume=task.resume,
        score=task.result['score'],
        summary=task.result['summary'],
        details=task.result,
    )


@transaction.atomic
def save_email_schedule_candidates(task):
    thread = task.email_thread or get_or_create_email_thread(user=task.user, email=task.email)
    if EmailAssistantMessage.objects.filter(task=task, role=EmailAssistantMessage.Role.ASSISTANT).exists():
        return
    assessment = task.result.get('assessment', 'needs_info')
    fallback = {
        'action_found': '我从邮件中找到了可能的日程或待办，请核对下面的候选卡片。',
        'schedule_found': '我从邮件中找到了可能的日程，请核对下面的候选卡片。',
        'no_action': '我没有在这封邮件中找到明确的日程或待办。请人工确认后再标记完成。',
        'no_schedule': '我没有在这封邮件中找到明确的日程或待办。请人工确认后再标记完成。',
        'needs_info': '邮件中可能有行动事项，但信息还不完整。你可以在对话中补充。',
    }.get(assessment, '请核对下面的候选卡片。')
    assistant_message = EmailAssistantMessage.objects.create(
        thread=thread,
        role=EmailAssistantMessage.Role.ASSISTANT,
        content=(task.result.get('assistant_reply') or fallback)[:3000],
        task=task,
        structured_data={'assessment': assessment},
    )
    EmailScheduleCandidate.objects.filter(
        email=task.email,
        status__in=(EmailScheduleCandidate.Status.PENDING, EmailScheduleCandidate.Status.NEEDS_INFO),
    ).update(status=EmailScheduleCandidate.Status.SUPERSEDED, reviewed_at=timezone.now())
    EmailTodoCandidate.objects.filter(
        email=task.email,
        status__in=(EmailTodoCandidate.Status.PENDING, EmailTodoCandidate.Status.NEEDS_INFO),
    ).update(status=EmailTodoCandidate.Status.SUPERSEDED, reviewed_at=timezone.now())
    schedule_version = EmailScheduleCandidate.objects.filter(email=task.email).aggregate(value=Max('version'))['value'] or 0
    todo_version = EmailTodoCandidate.objects.filter(email=task.email).aggregate(value=Max('version'))['value'] or 0
    version = max(schedule_version, todo_version) + 1
    schedule_items = task.result.get('schedule_candidates') or task.result.get('candidates', [])
    for item in schedule_items:
        missing = item.get('missing_fields', [])
        EmailScheduleCandidate.objects.create(
            user=task.user,
            email=task.email,
            task=task,
            source_message=assistant_message,
            version=version,
            status=EmailScheduleCandidate.Status.PENDING if item.get('starts_at') else EmailScheduleCandidate.Status.NEEDS_INFO,
            title=item['title'][:200],
            event_type=item.get('event_type', 'other'),
            starts_at=item.get('starts_at'),
            ends_at=item.get('ends_at'),
            timezone_name=item.get('timezone_name') or 'Asia/Tokyo',
            location=item.get('location') or '',
            meeting_url=item.get('meeting_url') or '',
            participants=item.get('participants') or [],
            summary=item.get('summary') or '',
            evidence=item.get('evidence', '')[:2000],
            missing_fields=missing,
            confidence=item.get('confidence', 0),
            company=task.email.company,
            application=task.email.application,
            contact=task.email.contact,
        )
    application = task.email.application if task.email.application_id else None
    for item in task.result.get('todo_candidates', []):
        missing = item.get('missing_fields', [])
        due_at = item.get('due_at')
        if isinstance(due_at, str):
            due_at = parse_datetime(due_at)
        if due_at and timezone.is_naive(due_at):
            try:
                due_at = timezone.make_aware(due_at, ZoneInfo(item.get('timezone_name') or 'Asia/Tokyo'))
            except ZoneInfoNotFoundError:
                due_at = timezone.make_aware(due_at, ZoneInfo('Asia/Tokyo'))
        if item.get('is_urgent'):
            priority = 'high'
        elif item.get('is_optional'):
            priority = 'low'
        elif due_at and due_at <= timezone.now() + timedelta(hours=72):
            priority = 'high'
        else:
            priority = 'medium'
        essential_missing = [field for field in missing if field not in {'due_at', 'timezone_name'}]
        EmailTodoCandidate.objects.create(
            user=task.user,
            email=task.email,
            task=task,
            source_message=assistant_message,
            version=version,
            status=EmailTodoCandidate.Status.NEEDS_INFO if essential_missing else EmailTodoCandidate.Status.PENDING,
            title=item['title'][:200],
            action_type=item.get('action_type', 'other'),
            due_at=due_at,
            timezone_name=item.get('timezone_name') or 'Asia/Tokyo',
            priority=priority,
            action_url=item.get('action_url') or '',
            notes=item.get('notes') or '',
            evidence=item.get('evidence', '')[:2000],
            missing_fields=missing,
            confidence=item.get('confidence', 0),
            company=task.email.company,
            job_position=application.job_position if application else None,
            application=application,
        )
    thread.status = EmailAssistantThread.Status.IN_REVIEW
    thread.resolution = ''
    thread.reviewed_at = None
    thread.save(update_fields=('status', 'resolution', 'reviewed_at', 'last_activity_at'))
