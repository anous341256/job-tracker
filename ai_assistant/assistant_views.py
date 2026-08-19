from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from companies.models import Company
from core.models import CalendarEvent, TodoItem
from mailboxes.models import SyncedEmail

from .forms import EmailAssistantChatForm, EmailAssistantCompanyForm, EmailScheduleReviewForm, EmailTodoReviewForm
from .models import AITask, EmailAssistantThread, EmailScheduleCandidate, EmailTodoCandidate
from .services import create_email_chat_task, get_or_create_email_thread


UNRESOLVED = (EmailScheduleCandidate.Status.PENDING, EmailScheduleCandidate.Status.NEEDS_INFO)
ACTIVE_TASKS = (AITask.Status.PENDING, AITask.Status.WAITING_HOST, AITask.Status.RUNNING)


def _owned_email(user, pk):
    return get_object_or_404(
        SyncedEmail.objects.select_related('account', 'company', 'application__job_position', 'contact'),
        pk=pk,
        account__user=user,
    )


def _email_queue(user, query='', review_filter='pending'):
    emails = SyncedEmail.objects.filter(account__user=user).select_related('company', 'assistant_thread')
    if query:
        emails = emails.filter(Q(subject__icontains=query) | Q(sender__icontains=query) | Q(body_text__icontains=query))
    if review_filter == 'completed':
        emails = emails.filter(assistant_thread__status=EmailAssistantThread.Status.REVIEWED)
    elif review_filter == 'needs_info':
        emails = emails.filter(
            Q(schedule_candidates__status=EmailScheduleCandidate.Status.NEEDS_INFO)
            | Q(todo_candidates__status=EmailTodoCandidate.Status.NEEDS_INFO)
        )
    elif review_filter == 'candidate':
        emails = emails.filter(
            Q(schedule_candidates__status=EmailScheduleCandidate.Status.PENDING)
            | Q(todo_candidates__status=EmailTodoCandidate.Status.PENDING)
        )
    else:
        emails = emails.exclude(assistant_thread__status=EmailAssistantThread.Status.REVIEWED)
    return emails.distinct().order_by('-received_at')[:100]


def _candidate_forms(email, user):
    candidates = list(
        EmailScheduleCandidate.objects.filter(email=email)
        .exclude(status=EmailScheduleCandidate.Status.SUPERSEDED)
        .select_related('company', 'application__job_position', 'contact', 'source_message')
        .order_by('-version', 'created_at')
    )
    for candidate in candidates:
        candidate.workbench_form = EmailScheduleReviewForm(instance=candidate, user=user)
    return candidates


def _todo_candidate_forms(email, user):
    candidates = list(
        EmailTodoCandidate.objects.filter(email=email)
        .exclude(status=EmailTodoCandidate.Status.SUPERSEDED)
        .select_related('company', 'job_position', 'application__job_position', 'source_message')
        .order_by('-version', 'created_at')
    )
    for candidate in candidates:
        candidate.workbench_form = EmailTodoReviewForm(instance=candidate, user=user)
    return candidates


def _detail_context(request, email, *, candidate_form=None, todo_candidate_form=None):
    thread = get_or_create_email_thread(user=request.user, email=email)
    candidates = _candidate_forms(email, request.user)
    todo_candidates = _todo_candidate_forms(email, request.user)
    if candidate_form is not None:
        for candidate in candidates:
            if candidate.pk == candidate_form.instance.pk:
                candidate.workbench_form = candidate_form
    if todo_candidate_form is not None:
        for candidate in todo_candidates:
            if candidate.pk == todo_candidate_form.instance.pk:
                candidate.workbench_form = todo_candidate_form
    active_task = thread.ai_tasks.filter(status__in=ACTIVE_TASKS).order_by('-created_at').first()
    failed_task = thread.ai_tasks.filter(status=AITask.Status.FAILED).order_by('-created_at').first()
    return {
        'selected_email': email,
        'assistant_thread': thread,
        'assistant_messages': thread.messages.select_related('task').order_by('created_at', 'pk')[:100],
        'candidates': candidates,
        'todo_candidates': todo_candidates,
        'active_task': active_task,
        'failed_task': failed_task,
        'chat_form': EmailAssistantChatForm(),
        'company_form': EmailAssistantCompanyForm(user=request.user, initial={'company': email.company_id}),
        'has_unresolved': (
            any(item.status in UNRESOLVED for item in candidates)
            or any(item.status in UNRESOLVED for item in todo_candidates)
        ),
        'has_approved': (
            any(item.status == EmailScheduleCandidate.Status.APPROVED for item in candidates)
            or any(item.status == EmailTodoCandidate.Status.APPROVED for item in todo_candidates)
        ),
    }


def _render_detail(request, email, *, candidate_form=None, todo_candidate_form=None, status=200):
    return render(
        request,
        'ai_assistant/_mail_assistant_detail.html',
        _detail_context(request, email, candidate_form=candidate_form, todo_candidate_form=todo_candidate_form),
        status=status,
    )


@login_required
def mail_assistant(request):
    query = request.GET.get('q', '').strip()
    review_filter = request.GET.get('status', 'pending').strip()
    if review_filter not in {'pending', 'needs_info', 'candidate', 'completed'}:
        review_filter = 'pending'
    queue = list(_email_queue(request.user, query, review_filter))
    selected = None
    selected_id = request.GET.get('email', '').strip()
    if selected_id.isdigit():
        selected = _owned_email(request.user, selected_id)
    elif queue:
        selected = _owned_email(request.user, queue[0].pk)
    context = {
        'email_queue': queue,
        'query': query,
        'review_filter': review_filter,
        'selected_email': selected,
    }
    if selected:
        context.update(_detail_context(request, selected))
    return render(request, 'ai_assistant/mail_assistant.html', context)


@require_GET
@login_required
def mail_assistant_email(request, pk):
    return _render_detail(request, _owned_email(request.user, pk))


@require_POST
@login_required
def mail_assistant_chat(request, pk):
    email = _owned_email(request.user, pk)
    thread = get_or_create_email_thread(user=request.user, email=email)
    if thread.status == EmailAssistantThread.Status.REVIEWED:
        messages.error(request, '这封邮件已经完成检查，如需继续对话请先重新打开。')
        return _render_detail(request, email, status=409) if request.headers.get('HX-Request') else redirect('ai_assistant:mail-assistant')
    form = EmailAssistantChatForm(request.POST)
    if not form.is_valid():
        messages.error(request, '消息未发送，请检查输入内容。')
        return _render_detail(request, email, status=400) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')
    try:
        create_email_chat_task(
            user=request.user,
            email=email,
            content=form.cleaned_data['content'],
            client_request_id=form.cleaned_data['client_request_id'],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return _render_detail(request, email, status=409) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')
    return _render_detail(request, email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')


@require_POST
@login_required
def mail_assistant_company(request, pk):
    email = _owned_email(request.user, pk)
    form = EmailAssistantCompanyForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, '请选择公司，或输入要新建的公司名称。')
        return _render_detail(request, email, status=400) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')
    with transaction.atomic():
        company = form.cleaned_data.get('company')
        new_name = (form.cleaned_data.get('new_company_name') or '').strip()
        if not company:
            company = Company.objects.filter(user=request.user, name__iexact=new_name).first()
            if not company:
                company = Company.objects.create(user=request.user, name=new_name)
        email.company = company
        if email.application_id and email.application.job_position.company_id != company.id:
            email.application = None
        if email.contact_id and email.contact.company_id != company.id:
            email.contact = None
        email.save(update_fields=('company', 'application', 'contact'))
        pending = EmailScheduleCandidate.objects.filter(email=email, status__in=UNRESOLVED)
        pending.update(company=company, application=None, contact=None)
        pending_todos = EmailTodoCandidate.objects.filter(email=email, status__in=UNRESOLVED)
        pending_todos.update(company=company, job_position=None, application=None)
    messages.success(request, f'邮件已关联到 {company.name}。')
    return _render_detail(request, email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')


@require_POST
@login_required
def mail_assistant_complete(request, pk):
    email = _owned_email(request.user, pk)
    thread = get_or_create_email_thread(user=request.user, email=email)
    with transaction.atomic():
        thread = EmailAssistantThread.objects.select_for_update().get(pk=thread.pk, user=request.user)
        if (
            EmailScheduleCandidate.objects.filter(email=email, status__in=UNRESOLVED).exists()
            or EmailTodoCandidate.objects.filter(email=email, status__in=UNRESOLVED).exists()
        ):
            messages.error(request, '请先批准或忽略所有待审核候选。')
            return _render_detail(request, email, status=409) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')
        has_approved = (
            EmailScheduleCandidate.objects.filter(email=email, status=EmailScheduleCandidate.Status.APPROVED).exists()
            or EmailTodoCandidate.objects.filter(email=email, status=EmailTodoCandidate.Status.APPROVED).exists()
        )
        thread.status = EmailAssistantThread.Status.REVIEWED
        thread.resolution = EmailAssistantThread.Resolution.WITH_SCHEDULE if has_approved else EmailAssistantThread.Resolution.NO_SCHEDULE
        thread.reviewed_at = timezone.now()
        thread.save(update_fields=('status', 'resolution', 'reviewed_at', 'last_activity_at'))
    messages.success(request, '这封邮件的行动事项检查已完成。')
    if request.headers.get('HX-Request'):
        next_email = _email_queue(request.user, review_filter='pending').first()
        if next_email:
            return _render_detail(request, _owned_email(request.user, next_email.pk))
        return render(request, 'ai_assistant/_mail_assistant_empty.html')
    return redirect('ai_assistant:mail-assistant')


@require_POST
@login_required
def mail_assistant_reopen(request, pk):
    email = _owned_email(request.user, pk)
    thread = get_or_create_email_thread(user=request.user, email=email)
    thread.status = EmailAssistantThread.Status.IN_REVIEW
    thread.resolution = ''
    thread.reviewed_at = None
    thread.save(update_fields=('status', 'resolution', 'reviewed_at', 'last_activity_at'))
    messages.success(request, '邮件已重新打开，可以继续与千问确认。')
    return _render_detail(request, email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')


@require_POST
@login_required
def mail_assistant_clear(request, pk):
    email = _owned_email(request.user, pk)
    thread = get_or_create_email_thread(user=request.user, email=email)
    if thread.ai_tasks.filter(status__in=ACTIVE_TASKS).exists():
        messages.error(request, '千问仍在处理消息，完成后才能清空对话。')
        return _render_detail(request, email, status=409) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')
    thread.messages.all().delete()
    messages.success(request, '对话记录已清空；邮件、候选、正式日程和 To Do 没有删除。')
    return _render_detail(request, email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={email.pk}')


def _apply_candidate(candidate, form, user):
    updated = candidate
    for field in (
        'title', 'event_type', 'starts_at', 'ends_at', 'timezone_name',
        'location', 'meeting_url', 'participants', 'summary', 'company',
        'application', 'contact',
    ):
        setattr(updated, field, form.cleaned_data.get(field))
    target = form.cleaned_data['target']
    if target == 'interview':
        from core.services import create_scheduled_action
        application = updated.application
        job = form.cleaned_data.get('job_position') or (application.job_position if application else None)
        obj = create_scheduled_action(
            user=user,
            company=updated.company,
            job_position=job,
            application=application,
            title=updated.title,
            event_type=CalendarEvent.Type.INTERVIEW,
            starts_at=updated.starts_at,
            ends_at=updated.ends_at,
            meeting_url=updated.meeting_url,
            location=updated.location,
            participants=updated.participants,
            notes=updated.summary,
            source_email=updated.email,
            contact=updated.contact,
        )
        object_type = 'interview'
    elif target == 'todo':
        obj = TodoItem.objects.create(
            user=user,
            company=updated.company,
            job_position=form.cleaned_data.get('job_position'),
            application=updated.application,
            title=updated.title,
            due_at=updated.starts_at,
            notes=updated.summary,
            source_email=updated.email,
            source_url=updated.meeting_url,
        )
        object_type = 'todo'
    else:
        calendar_type = updated.event_type if updated.event_type in CalendarEvent.Type.values else CalendarEvent.Type.OTHER
        obj = CalendarEvent.objects.create(
            user=user,
            title=updated.title,
            event_type=calendar_type,
            starts_at=updated.starts_at,
            ends_at=updated.ends_at,
            location=updated.location,
            meeting_url=updated.meeting_url,
            participants=updated.participants,
            notes=updated.summary,
            source_email=updated.email,
            company=updated.company,
            job_position=form.cleaned_data.get('job_position'),
            application=updated.application,
            contact=updated.contact,
        )
        object_type = 'calendar_event'
    updated.status = EmailScheduleCandidate.Status.APPROVED
    updated.created_object_type = object_type
    updated.created_object_id = obj.pk
    updated.reviewed_at = timezone.now()
    updated.save()
    return obj


@require_POST
@login_required
def mail_assistant_candidate_approve(request, pk):
    candidate = get_object_or_404(
        EmailScheduleCandidate.objects.select_related('email__account', 'application__job_position'),
        pk=pk,
        user=request.user,
        email__account__user=request.user,
    )
    if candidate.status not in UNRESOLVED:
        messages.info(request, '这个候选已经处理过。')
        return _render_detail(request, candidate.email)
    form = EmailScheduleReviewForm(request.POST, instance=candidate, user=request.user)
    if not form.is_valid():
        return _render_detail(request, candidate.email, candidate_form=form, status=400)
    with transaction.atomic():
        locked = EmailScheduleCandidate.objects.select_for_update().get(pk=candidate.pk, user=request.user)
        if locked.status not in UNRESOLVED:
            messages.info(request, '这个候选已经处理过。')
        else:
            form.instance = locked
            _apply_candidate(locked, form, request.user)
            messages.success(request, '候选已经加入日程。')
    return _render_detail(request, candidate.email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={candidate.email_id}')


@require_POST
@login_required
def mail_assistant_candidate_reject(request, pk):
    candidate = get_object_or_404(EmailScheduleCandidate, pk=pk, user=request.user, email__account__user=request.user)
    if candidate.status in UNRESOLVED:
        candidate.status = EmailScheduleCandidate.Status.REJECTED
        candidate.reviewed_at = timezone.now()
        candidate.save(update_fields=('status', 'reviewed_at'))
        messages.success(request, '候选已忽略。')
    return _render_detail(request, candidate.email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={candidate.email_id}')


@require_POST
@login_required
def mail_assistant_todo_approve(request, pk):
    candidate = get_object_or_404(
        EmailTodoCandidate.objects.select_related('email__account', 'application__job_position'),
        pk=pk,
        user=request.user,
        email__account__user=request.user,
    )
    if candidate.status not in UNRESOLVED:
        messages.info(request, '这个 To Do 候选已经处理过。')
        return _render_detail(request, candidate.email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={candidate.email_id}')
    form = EmailTodoReviewForm(request.POST, instance=candidate, user=request.user)
    if not form.is_valid():
        return _render_detail(request, candidate.email, todo_candidate_form=form, status=400)
    with transaction.atomic():
        locked = EmailTodoCandidate.objects.select_for_update().get(pk=candidate.pk, user=request.user)
        if locked.status not in UNRESOLVED:
            messages.info(request, '这个 To Do 候选已经处理过。')
        else:
            cleaned = form.cleaned_data
            todo = TodoItem.objects.create(
                user=request.user,
                company=cleaned['company'],
                job_position=cleaned.get('job_position'),
                application=cleaned.get('application'),
                title=cleaned['title'],
                priority=cleaned['priority'],
                due_at=cleaned.get('due_at'),
                notes=cleaned.get('notes') or '',
                source_email=locked.email,
                source_url=cleaned.get('action_url') or '',
            )
            for field in (
                'title', 'action_type', 'due_at', 'timezone_name', 'priority',
                'action_url', 'notes', 'company', 'job_position', 'application',
            ):
                setattr(locked, field, cleaned.get(field))
            locked.status = EmailTodoCandidate.Status.APPROVED
            locked.created_object_id = todo.pk
            locked.reviewed_at = timezone.now()
            locked.save()
            messages.success(request, '候选已经创建为 To Do。')
    return _render_detail(request, candidate.email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={candidate.email_id}')


@require_POST
@login_required
def mail_assistant_todo_reject(request, pk):
    candidate = get_object_or_404(
        EmailTodoCandidate,
        pk=pk,
        user=request.user,
        email__account__user=request.user,
    )
    if candidate.status in UNRESOLVED:
        candidate.status = EmailTodoCandidate.Status.REJECTED
        candidate.reviewed_at = timezone.now()
        candidate.save(update_fields=('status', 'reviewed_at'))
        messages.success(request, 'To Do 候选已忽略。')
    return _render_detail(request, candidate.email) if request.headers.get('HX-Request') else redirect(f'{reverse("ai_assistant:mail-assistant")}?email={candidate.email_id}')
