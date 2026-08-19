from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET

from applications.models import Application, Interview
from applications.services import ENDED_OUTCOMES, PIPELINE_STAGES
from companies.models import JobPosition
from companies.models import Company
from .forms import CalendarEventForm, TodoItemForm
from .models import CalendarEvent, Notification, TodoItem
from .services import (
    build_company_cards,
    create_scheduled_action,
    event_color,
    timed_busy_intervals,
    user_calendar_timezone,
    workday_free_slots,
)


def _safe_redirect(request, default):
    target = request.POST.get('next') or request.GET.get('next')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(default)


@login_required
def dashboard(request):
    return render(request, 'core/dashboard.html', {
        'company_cards': build_company_cards(request.user),
        'pipeline_stages': PIPELINE_STAGES,
        'ended_outcomes': ENDED_OUTCOMES,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
        'open_todo_count': TodoItem.objects.filter(user=request.user).exclude(status=TodoItem.Status.DONE).count(),
        'now': timezone.now(),
    })


@login_required
def calendar_events(request):
    start = parse_datetime(request.GET.get('start', ''))
    end = parse_datetime(request.GET.get('end', ''))
    if not start or not end:
        start, end = timezone.now() - timedelta(days=31), timezone.now() + timedelta(days=62)

    events = []
    for interval in timed_busy_intervals(request.user, start, end):
        events.append({
            'title': interval.title,
            'start': interval.starts_at.isoformat(),
            'end': interval.ends_at.isoformat(),
            'url': interval.url,
            'color': interval.color,
            'extendedProps': {
                'kind': interval.kind,
                'duration': f'{interval.duration_minutes} 分钟',
            },
        })

    jobs = JobPosition.objects.filter(
        company__user=request.user,
        application_deadline__gte=start.date(),
        application_deadline__lt=end.date(),
    ).select_related('company')
    for job in jobs:
        events.append({
            'title': f'截止：{job.company.name} {job.title}',
            'start': job.application_deadline.isoformat(),
            'allDay': True,
            'url': f'/jobs/{job.pk}/',
            'color': '#d94d43',
            'extendedProps': {'kind': 'deadline'},
        })

    follow_ups = Application.objects.filter(
        user=request.user,
        next_action_date__gte=start.date(),
        next_action_date__lt=end.date(),
        archived_at__isnull=True,
    ).select_related('job_position__company')
    for app in follow_ups:
        events.append({
            'title': f'跟进：{app.job_position.company.name} {app.job_position.title}',
            'start': app.next_action_date.isoformat(),
            'allDay': True,
            'url': f'/applications/{app.pk}/',
            'color': '#c58b25',
            'extendedProps': {'kind': 'followup'},
        })

    todos = TodoItem.objects.filter(
        user=request.user,
        due_at__gte=start,
        due_at__lt=end,
    ).exclude(status=TodoItem.Status.DONE)
    for todo in todos:
        events.append({
            'title': f'To Do：{todo.title}',
            'start': todo.due_at.isoformat(),
            'end': (todo.due_at + timedelta(minutes=30)).isoformat(),
            'url': f'/todos/{todo.pk}/edit/',
            'color': '#6f7b8f',
            'extendedProps': {'kind': 'todo', 'duration': '30 分钟'},
        })
    return JsonResponse(events, safe=False)


def _duration_label(minutes):
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f'{hours}小时{remainder}分钟'
    if hours:
        return f'{hours}小时'
    return f'{remainder}分钟'


@require_GET
@login_required
def calendar_free_slots(request):
    local_tz = user_calendar_timezone(request.user)
    start = parse_datetime(request.GET.get('start', ''))
    end = parse_datetime(request.GET.get('end', ''))
    if not start or not end:
        return JsonResponse({'error': 'start 和 end 必须是 ISO-8601 日期时间。'}, status=400)
    if timezone.is_naive(start):
        start = timezone.make_aware(start, local_tz)
    if timezone.is_naive(end):
        end = timezone.make_aware(end, local_tz)
    if end <= start:
        return JsonResponse({'error': 'end 必须晚于 start。'}, status=400)
    if end - start > timedelta(days=62):
        return JsonResponse({'error': '查询范围不能超过62天。'}, status=400)

    weekday_labels = ('月', '火', '水', '木', '金', '土', '日')
    events = []
    for slot_start, slot_end in workday_free_slots(request.user, start, end):
        minutes = int((slot_end - slot_start).total_seconds() / 60)
        duration = _duration_label(minutes)
        date_label = f'{slot_start.year}年{slot_start.month}月{slot_start.day}日（{weekday_labels[slot_start.weekday()]}）'
        time_label = f'{slot_start:%H:%M}–{slot_end:%H:%M}'
        copy_text = f'{date_label} {time_label}'
        events.append({
            'title': f'空闲 {duration}',
            'start': slot_start.isoformat(),
            'end': slot_end.isoformat(),
            'display': 'background',
            'groupId': 'free-slot',
            'backgroundColor': '#dff3e6',
            'borderColor': '#79b88f',
            'textColor': '#22643a',
            'editable': False,
            'classNames': ['free-slot-event'],
            'extendedProps': {
                'kind': 'free_slot',
                'minutes': minutes,
                'duration': duration,
                'dateLabel': date_label,
                'timeLabel': time_label,
                'copyText': copy_text,
            },
        })
    return JsonResponse(events, safe=False)


@login_required
def todos(request):
    items = TodoItem.objects.filter(user=request.user).select_related('company', 'job_position', 'application', 'source_email')
    status = request.GET.get('status', '').strip()
    q = request.GET.get('q', '').strip()
    if status:
        items = items.filter(status=status)
    if q:
        items = items.filter(Q(title__icontains=q) | Q(notes__icontains=q))
    company_id = request.GET.get('company', '').strip()
    if company_id.isdigit():
        items = items.filter(company_id=company_id)
    page_obj = Paginator(items, 20).get_page(request.GET.get('page'))
    counts = {
        key: TodoItem.objects.filter(user=request.user, status=key).count()
        for key, _ in TodoItem.Status.choices
    }
    return render(request, 'core/todos.html', {
        'items': page_obj.object_list,
        'page_obj': page_obj,
        'is_paginated': page_obj.paginator.num_pages > 1,
        'status': status,
        'q': q,
        'counts': counts,
        'status_choices': TodoItem.Status.choices,
        'companies': Company.objects.filter(user=request.user, archived_at__isnull=True).order_by('name'),
        'company_id': company_id,
    })


@login_required
def todo_create(request):
    company = Company.objects.filter(pk=request.GET.get('company'), user=request.user).first()
    job = JobPosition.objects.filter(pk=request.GET.get('job'), company__user=request.user).select_related('company').first()
    if job and not company:
        company = job.company
    if job and company and job.company_id != company.id:
        job = None
    form = TodoItemForm(request.POST or None, user=request.user, company=company, job_position=job)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.user = request.user
        item.save()
        return _safe_redirect(request, 'core:dashboard')
    return render(request, 'generic/form.html', {
        'form': form, 'form_title': '新增 To Do', 'next_url': request.GET.get('next', ''),
    })


@login_required
def todo_edit(request, pk):
    item = get_object_or_404(TodoItem, pk=pk, user=request.user)
    form = TodoItemForm(request.POST or None, instance=item, user=request.user)
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        if updated.status == TodoItem.Status.DONE and not updated.completed_at:
            updated.completed_at = timezone.now()
        if updated.status != TodoItem.Status.DONE:
            updated.completed_at = None
        updated.save()
        return _safe_redirect(request, 'core:todos')
    return render(request, 'generic/form.html', {
        'form': form, 'form_title': '编辑 To Do', 'next_url': request.GET.get('next', ''),
    })


@login_required
def calendar_event_create(request):
    company = Company.objects.filter(pk=request.GET.get('company'), user=request.user).first()
    job = JobPosition.objects.filter(pk=request.GET.get('job'), company__user=request.user).select_related('company').first()
    if job and not company:
        company = job.company
    if job and company and job.company_id != company.id:
        job = None
    form = CalendarEventForm(request.POST or None, user=request.user, company=company, job_position=job)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        create_scheduled_action(
            user=request.user,
            company=data['company'],
            job_position=data.get('job_position'),
            title=data['title'],
            event_type=data['event_type'],
            starts_at=data['starts_at'],
            ends_at=data.get('ends_at'),
            location=data.get('location') or '',
            meeting_url=data.get('meeting_url') or '',
            notes=data.get('notes') or '',
        )
        return _safe_redirect(request, 'core:dashboard')
    return render(request, 'generic/form.html', {
        'form': form,
        'form_title': '新增日程',
        'form_intro': '选择“面试”并关联职位时，系统会自动创建或推进该职位的求职记录。',
        'next_url': request.GET.get('next', ''),
    })


@login_required
def calendar_event_edit(request, pk):
    event = get_object_or_404(CalendarEvent, pk=pk, user=request.user)
    form = CalendarEventForm(request.POST or None, instance=event, user=request.user)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        if data['event_type'] == CalendarEvent.Type.INTERVIEW and data.get('job_position'):
            with transaction.atomic():
                create_scheduled_action(
                    user=request.user,
                    company=data['company'],
                    job_position=data['job_position'],
                    title=data['title'],
                    event_type=data['event_type'],
                    starts_at=data['starts_at'],
                    ends_at=data.get('ends_at'),
                    location=data.get('location') or '',
                    meeting_url=data.get('meeting_url') or '',
                    notes=data.get('notes') or '',
                    participants=event.participants,
                    source_email=event.source_email,
                    contact=event.contact,
                )
                event.delete()
        else:
            updated = form.save(commit=False)
            updated.user = request.user
            updated.save()
        return _safe_redirect(request, 'calendar')
    return render(request, 'generic/form.html', {
        'form': form, 'form_title': '编辑日程', 'next_url': request.GET.get('next', ''),
    })


@login_required
def todo_toggle(request, pk):
    item = get_object_or_404(TodoItem, pk=pk, user=request.user)
    if request.method == 'POST':
        if item.status == TodoItem.Status.DONE:
            item.reopen()
        else:
            item.mark_done()
        if request.headers.get('HX-Request'):
            return render(request, 'core/_todo_mini_row.html', {
                'todo': item,
                'card_company_id': request.POST.get('card_company_id') or item.company_id,
                'now': timezone.now(),
            })
    return _safe_redirect(request, 'core:todos')


@login_required
def todo_delete(request, pk):
    item = get_object_or_404(TodoItem, pk=pk, user=request.user)
    if request.method == 'POST':
        item.delete()
        return redirect('core:todos')
    return render(request, 'generic/confirm_delete.html', {
        'object': item,
        'kind': ' To Do',
        'cancel_url': '/todos/',
    })


@login_required
def notifications(request):
    return render(request, 'core/notifications.html', {'notifications': Notification.objects.filter(user=request.user)[:100]})


@login_required
def notification_read(request, pk):
    if request.method == 'POST':
        item = get_object_or_404(Notification, pk=pk, user=request.user)
        item.is_read = True
        item.save(update_fields=('is_read',))
    return redirect('core:notifications')


@login_required
def notifications_read_all(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('core:notifications')
