from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from applications.models import Interview
from companies.models import JobPosition
from core.models import CalendarEvent, TodoItem
from core.models import HostAgentHeartbeat
from .crypto import encrypt_api_key
from .forms import AISettingsForm, EmailScheduleReviewForm, JDParseForm, JobMatchForm
from .models import AISettings, AITask, EmailScheduleCandidate
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
    return render(request, 'ai_assistant/settings.html', {'form': form, 'settings_obj': instance, 'ollama_ok': ollama_ok, 'host_agent': HostAgentHeartbeat.objects.order_by('-last_seen_at').first()})


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


@login_required
def email_schedules(request):
    candidates = EmailScheduleCandidate.objects.filter(user=request.user).select_related('email', 'company', 'application__job_position__company')
    status = request.GET.get('status', '').strip()
    company = request.GET.get('company', '').strip()
    if status:
        candidates = candidates.filter(status=status)
    if company.isdigit():
        candidates = candidates.filter(company_id=company)
    return render(request, 'ai_assistant/email_schedule_list.html', {
        'candidates': candidates[:100],
        'status_choices': EmailScheduleCandidate.Status.choices,
        'companies': request.user.companies.order_by('name'),
        'status': status,
        'company_id': company,
    })


@login_required
def email_schedule_review(request, pk):
    candidate = get_object_or_404(
        EmailScheduleCandidate.objects.select_related('email', 'task', 'company', 'application', 'contact'),
        pk=pk, user=request.user,
    )
    if candidate.status in (EmailScheduleCandidate.Status.APPROVED, EmailScheduleCandidate.Status.REJECTED):
        messages.info(request, '该候选已经处理完成。')
        return redirect('ai_assistant:email-schedules')
    form = EmailScheduleReviewForm(request.POST or None, instance=candidate, user=request.user)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            candidate = EmailScheduleCandidate.objects.select_for_update().get(pk=candidate.pk, user=request.user)
            if candidate.status in (EmailScheduleCandidate.Status.APPROVED, EmailScheduleCandidate.Status.REJECTED):
                messages.info(request, '该候选已被处理。')
                return redirect('ai_assistant:email-schedules')
            updated = form.save(commit=False)
            target = form.cleaned_data['target']
            if target == 'interview':
                from core.services import create_scheduled_action
                job = form.cleaned_data.get('job_position') or updated.application.job_position
                obj = create_scheduled_action(
                    user=request.user, company=updated.company, job_position=job,
                    application=updated.application, title=updated.title,
                    event_type=CalendarEvent.Type.INTERVIEW, starts_at=updated.starts_at,
                    ends_at=updated.ends_at, meeting_url=updated.meeting_url,
                    location=updated.location, participants=updated.participants,
                    notes=updated.summary, source_email=updated.email, contact=updated.contact,
                )
                object_type = 'interview'
            elif target == 'todo':
                obj = TodoItem.objects.create(
                    user=request.user, company=updated.company,
                    job_position=form.cleaned_data.get('job_position'), application=updated.application,
                    title=updated.title, due_at=updated.starts_at, notes=updated.summary,
                    source_email=updated.email, source_url=updated.meeting_url,
                )
                object_type = 'todo'
            else:
                calendar_type = updated.event_type if updated.event_type in CalendarEvent.Type.values else CalendarEvent.Type.OTHER
                obj = CalendarEvent.objects.create(
                    user=request.user, title=updated.title, event_type=calendar_type,
                    starts_at=updated.starts_at, ends_at=updated.ends_at, location=updated.location,
                    meeting_url=updated.meeting_url, participants=updated.participants, notes=updated.summary,
                    source_email=updated.email, company=updated.company,
                    job_position=form.cleaned_data.get('job_position'), application=updated.application, contact=updated.contact,
                )
                object_type = 'calendar_event'
            updated.status = EmailScheduleCandidate.Status.APPROVED
            updated.created_object_type = object_type
            updated.created_object_id = obj.pk
            updated.reviewed_at = timezone.now()
            updated.save()
        messages.success(request, '已根据审核内容创建记录。')
        return redirect('calendar') if target != 'todo' else redirect('core:todos')
    return render(request, 'ai_assistant/email_schedule_review.html', {'candidate': candidate, 'form': form})


@login_required
def email_schedule_reject(request, pk):
    candidate = get_object_or_404(EmailScheduleCandidate, pk=pk, user=request.user)
    if request.method == 'POST' and candidate.status not in (EmailScheduleCandidate.Status.APPROVED, EmailScheduleCandidate.Status.REJECTED):
        candidate.status = EmailScheduleCandidate.Status.REJECTED
        candidate.reviewed_at = timezone.now()
        candidate.save(update_fields=('status', 'reviewed_at'))
        messages.success(request, '已忽略该 AI 建议。')
    return redirect('ai_assistant:email-schedules')
