import hashlib
import re
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from .crypto import decrypt_api_key
from .models import AIMatchAnalysis, AISettings, AITask
from .providers import OllamaProvider, OpenAIProvider
from .prompts import PROMPT_VERSION, build_jd_prompt, build_match_prompt
from .schemas import JDParseResult, JobMatchResult


ACTIVE_STATUSES = (AITask.Status.PENDING, AITask.Status.RUNNING)


def user_ai_settings(user):
    settings_obj, _ = AISettings.objects.get_or_create(user=user)
    return settings_obj


def select_model(settings_obj, task_type, provider):
    if provider == AISettings.Provider.OLLAMA: return settings_obj.ollama_model
    return settings_obj.openai_fast_model if task_type == AITask.Type.JD_PARSE else settings_obj.openai_quality_model


def create_ai_task(*, user, task_type, job, provider, source_text='', resume=None):
    settings_obj = user_ai_settings(user)
    if provider == AISettings.Provider.OPENAI:
        if not settings_obj.encrypted_openai_api_key or not settings_obj.openai_key_verified:
            raise ValueError('请先在 AI 设置中保存并验证 OpenAI API Key。')
        if task_type == AITask.Type.JOB_MATCH and not settings_obj.allow_sensitive_cloud:
            raise ValueError('请先在 AI 设置中授权简历内容发送到 OpenAI，或改用本地 Ollama。')
    fingerprint_source = f'{task_type}|{job.pk}|{resume.pk if resume else ""}|{source_text}'
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()
    with transaction.atomic():
        existing = AITask.objects.select_for_update().filter(user=user, task_type=task_type, job=job, resume=resume, status__in=ACTIVE_STATUSES).first()
        if existing: return existing, False
        task = AITask.objects.create(user=user, task_type=task_type, provider=provider, model=select_model(settings_obj, task_type, provider), job=job, resume=resume, input_fingerprint=fingerprint, prompt_version=PROMPT_VERSION, input_payload={'source_text': source_text} if task_type == AITask.Type.JD_PARSE else {}, sensitive_cloud_consent=provider == AISettings.Provider.OPENAI and settings_obj.allow_sensitive_cloud)
    from .tasks import execute_ai_task
    execute_ai_task.delay(str(task.pk))
    return task, True


def provider_for(task):
    settings_obj = user_ai_settings(task.user)
    if task.provider == AISettings.Provider.OLLAMA: return OllamaProvider(settings_obj.ollama_url)
    return OpenAIProvider(decrypt_api_key(settings_obj.encrypted_openai_api_key))


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
        raise ValueError('旧版 .doc 暂不支持 AI 解析，请转换为 PDF 或 DOCX。')
    else:
        raise ValueError('该简历格式暂不支持 AI 解析。')
    text = text.strip()
    if not text: raise ValueError('无法从简历中提取文字。')
    return text[:40000]


def redact_contact_details(text):
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[EMAIL REDACTED]', text)
    return re.sub(r'(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)', '[PHONE REDACTED]', text)


def match_prompt(task):
    resume_text = extract_resume_text(task.resume)
    if task.provider == AISettings.Provider.OPENAI: resume_text = redact_contact_details(resume_text)
    job = task.job
    job_data = {'title': job.title, 'company': job.company.name, 'description': job.description, 'requirements': job.requirements, 'benefits': job.benefits, 'metadata': job.ai_metadata}
    profile = getattr(task.user, 'profile', None)
    profile_data = {'target_role': getattr(profile, 'target_role', ''), 'location': getattr(profile, 'location', '')}
    return build_match_prompt(job_data=job_data, profile_data=profile_data, resume_text=resume_text)


def run_task(task):
    provider = provider_for(task)
    if task.task_type == AITask.Type.JD_PARSE:
        return provider.generate(model=task.model, prompt=build_jd_prompt(task.input_payload.get('source_text', '')), schema=JDParseResult)
    return provider.generate(model=task.model, prompt=match_prompt(task), schema=JobMatchResult)


def save_match_analysis(task):
    AIMatchAnalysis.objects.create(task=task, user=task.user, job=task.job, resume=task.resume, score=task.result['score'], summary=task.result['summary'], details=task.result)
