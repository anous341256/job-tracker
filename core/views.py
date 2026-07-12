from collections import Counter
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from applications.models import Application, ApplicationStatusLog, Interview
from companies.models import JobPosition
from .models import Notification


@login_required
def dashboard(request):
    applications = Application.objects.filter(user=request.user)
    today = timezone.localdate()
    source_counts = list(applications.values('source').annotate(total=Count('id')).order_by('source'))
    monthly_counter = Counter(timezone.localtime(value).strftime('%Y-%m') for value in applications.values_list('created_at', flat=True))
    progressed = applications.exclude(status__in=[Application.Status.PREPARING, Application.Status.APPLIED]).count()
    offers = applications.filter(status__in=[Application.Status.OFFER, Application.Status.ACCEPTED]).count()
    stage_durations = []
    for app in applications.prefetch_related('status_logs'):
        logs = list(app.status_logs.order_by('changed_at'))
        stage_durations.extend((b.changed_at - a.changed_at).total_seconds() / 86400 for a, b in zip(logs, logs[1:]))
    context = {
        'application_count': applications.count(),
        'status_counts': applications.values('status').annotate(total=Count('id')).order_by('status'),
        'upcoming_interviews': Interview.objects.filter(application__user=request.user, status=Interview.Status.SCHEDULED, scheduled_at__gte=timezone.now()).select_related('application__job_position__company')[:5],
        'deadlines': JobPosition.objects.filter(company__user=request.user, application_deadline__range=(today, today + timedelta(days=14))).select_related('company')[:5],
        'follow_ups': applications.filter(next_action_date__lte=today, archived_at__isnull=True).exclude(status__in=[Application.Status.ACCEPTED, Application.Status.REJECTED, Application.Status.WITHDRAWN, Application.Status.CLOSED])[:5],
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
        'interview_conversion': round(progressed * 100 / applications.count(), 1) if applications.exists() else 0,
        'offer_conversion': round(offers * 100 / applications.count(), 1) if applications.exists() else 0,
        'average_stage_days': round(sum(stage_durations) / len(stage_durations), 1) if stage_durations else 0,
        'source_chart': {'labels': [dict(Application.Source.choices).get(x['source'], x['source']) for x in source_counts], 'values': [x['total'] for x in source_counts]},
        'monthly_chart': {'labels': sorted(monthly_counter), 'values': [monthly_counter[key] for key in sorted(monthly_counter)]},
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def calendar_events(request):
    start = parse_datetime(request.GET.get('start', ''))
    end = parse_datetime(request.GET.get('end', ''))
    if not start or not end:
        start, end = timezone.now() - timedelta(days=31), timezone.now() + timedelta(days=62)
    events = []
    interviews = Interview.objects.filter(application__user=request.user, scheduled_at__gte=start, scheduled_at__lt=end).exclude(status=Interview.Status.CANCELLED)
    for interview in interviews:
        events.append({'title': f'面试：{interview.title}', 'start': interview.scheduled_at.isoformat(), 'end': (interview.scheduled_at + timedelta(minutes=interview.duration_minutes or 60)).isoformat(), 'url': f'/applications/{interview.application_id}/', 'color': '#24456d'})
    for job in JobPosition.objects.filter(company__user=request.user, application_deadline__gte=start.date(), application_deadline__lt=end.date()).select_related('company'):
        events.append({'title': f'截止：{job.company.name} {job.title}', 'start': job.application_deadline.isoformat(), 'url': f'/jobs/{job.pk}/', 'color': '#a04444'})
    for app in Application.objects.filter(user=request.user, next_action_date__gte=start.date(), next_action_date__lt=end.date(), archived_at__isnull=True).select_related('job_position__company'):
        events.append({'title': f'跟进：{app.job_position.company.name} {app.job_position.title}', 'start': app.next_action_date.isoformat(), 'url': f'/applications/{app.pk}/', 'color': '#88733c'})
    return JsonResponse(events, safe=False)


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
