from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from companies.models import JobPosition
from .crypto import encrypt_api_key
from .forms import AISettingsForm, JDParseForm, JobMatchForm
from .models import AISettings, AITask
from .providers import verify_openai_key
from .services import create_ai_task, user_ai_settings


@login_required
def ai_settings(request):
    instance = user_ai_settings(request.user)
    form = AISettingsForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        api_key = form.cleaned_data.get('openai_api_key', '').strip()
        if api_key:
            if not verify_openai_key(api_key):
                form.add_error('openai_api_key', '密钥验证失败，请检查 API Key 和访问权限。')
            else:
                try:
                    encrypted = encrypt_api_key(api_key)
                except ImproperlyConfigured as exc:
                    form.add_error('openai_api_key', str(exc))
                else:
                    obj = form.save(commit=False); obj.encrypted_openai_api_key = encrypted; obj.openai_key_suffix = api_key[-4:]; obj.openai_key_verified = True; obj.save(); messages.success(request, 'AI 设置和 OpenAI API Key 已安全保存。'); return redirect('ai_assistant:settings')
        else:
            form.save(); messages.success(request, 'AI 设置已更新。'); return redirect('ai_assistant:settings')
    ollama_ok = False
    try:
        import requests
        ollama_ok = requests.get(f'{instance.ollama_url.rstrip("/")}/api/tags', timeout=2).ok
    except Exception: pass
    return render(request, 'ai_assistant/settings.html', {'form': form, 'settings_obj': instance, 'ollama_ok': ollama_ok})


@login_required
def delete_openai_key(request):
    if request.method == 'POST':
        obj = user_ai_settings(request.user); obj.encrypted_openai_api_key = ''; obj.openai_key_suffix = ''; obj.openai_key_verified = False; obj.allow_sensitive_cloud = False; obj.save(update_fields=('encrypted_openai_api_key', 'openai_key_suffix', 'openai_key_verified', 'allow_sensitive_cloud', 'updated_at')); messages.success(request, 'OpenAI API Key 已删除。')
    return redirect('ai_assistant:settings')


def _owned_job(user, pk): return get_object_or_404(JobPosition.objects.select_related('company'), pk=pk, company__user=user)


@login_required
def jd_parse(request, pk):
    job = _owned_job(request.user, pk); ai_config = user_ai_settings(request.user)
    initial = {'provider': ai_config.default_provider, 'source_text': '\n\n'.join(filter(None, [job.description, job.requirements, job.benefits]))}
    form = JDParseForm(request.POST or None, initial=initial if request.method == 'GET' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            task, created = create_ai_task(user=request.user, task_type=AITask.Type.JD_PARSE, job=job, provider=form.cleaned_data['provider'], source_text=form.cleaned_data['source_text'])
            if not created: messages.info(request, '相同职位已有解析任务正在运行。')
            return redirect('ai_assistant:task-detail', pk=task.pk)
        except ValueError as exc: form.add_error(None, str(exc))
    return render(request, 'ai_assistant/task_form.html', {'form': form, 'title': 'AI 解析 JD', 'job': job})


@login_required
def job_match(request, pk):
    job = _owned_job(request.user, pk); ai_config = user_ai_settings(request.user)
    form = JobMatchForm(request.POST or None, user=request.user, initial={'provider': ai_config.default_provider})
    if request.method == 'POST' and form.is_valid():
        try:
            task, created = create_ai_task(user=request.user, task_type=AITask.Type.JOB_MATCH, job=job, resume=form.cleaned_data['resume'], provider=form.cleaned_data['provider'])
            if not created: messages.info(request, '相同职位和简历已有匹配任务正在运行。')
            return redirect('ai_assistant:task-detail', pk=task.pk)
        except ValueError as exc: form.add_error(None, str(exc))
    return render(request, 'ai_assistant/task_form.html', {'form': form, 'title': 'AI 职位匹配', 'job': job})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(AITask.objects.select_related('job__company', 'resume'), pk=pk, user=request.user)
    rates = django_settings.AI_MODEL_PRICES.get(task.model, {})
    cost = (task.input_tokens * rates.get('input', 0) + task.output_tokens * rates.get('output', 0)) / 1_000_000
    template = 'ai_assistant/_task_status.html' if request.headers.get('HX-Request') else 'ai_assistant/task_detail.html'
    return render(request, template, {'task': task, 'estimated_cost': cost})


JOB_FIELDS = {'title', 'category', 'category_other', 'department', 'location', 'work_mode', 'employment_type', 'salary_min', 'salary_max', 'salary_currency', 'salary_period', 'application_deadline', 'description', 'requirements', 'benefits'}
META_FIELDS = {'skills', 'experience_requirements', 'education_requirements', 'language_requirements', 'preferred_qualifications', 'confidence', 'unknown_fields'}


@login_required
def apply_jd_result(request, pk):
    task = get_object_or_404(AITask.objects.select_related('job__company'), pk=pk, user=request.user, task_type=AITask.Type.JD_PARSE, status=AITask.Status.SUCCEEDED)
    if request.method == 'POST':
        selected = set(request.POST.getlist('fields'))
        with transaction.atomic():
            job = JobPosition.objects.select_for_update().get(pk=task.job_id, company__user=request.user)
            changed = []
            for field in selected & JOB_FIELDS:
                value = task.result.get(field)
                if value not in (None, ''):
                    if field in {'salary_min', 'salary_max'}: value = Decimal(str(value))
                    setattr(job, field, value); changed.append(field)
            metadata = dict(job.ai_metadata)
            for field in selected & META_FIELDS: metadata[field] = task.result.get(field, [])
            if selected & META_FIELDS: job.ai_metadata = metadata; changed.append('ai_metadata')
            try: job.full_clean()
            except ValidationError as exc: messages.error(request, f'无法应用结果：{exc}'); return redirect('ai_assistant:task-detail', pk=pk)
            if changed: job.save(update_fields=changed + ['updated_at'])
        messages.success(request, f'已将 {len(changed)} 项 AI 建议应用到职位。')
        return redirect('companies:job-detail', pk=task.job_id)
    return redirect('ai_assistant:task-detail', pk=pk)


@login_required
def delete_task(request, pk):
    task = get_object_or_404(AITask, pk=pk, user=request.user)
    job_id = task.job_id
    if request.method == 'POST' and task.status not in (AITask.Status.PENDING, AITask.Status.RUNNING): task.delete(); messages.success(request, 'AI 分析记录已删除。')
    return redirect('companies:job-detail', pk=job_id)
