from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from applications.models import Application, Interview
from companies.models import JobPosition
from .models import Notification


@login_required
def dashboard(request):
    applications = Application.objects.filter(user=request.user)
    today = timezone.localdate()
    source_counts = list(applications.values('source').annotate(total=Count('id')).order_by('source'))
    monthly_counts = list(applications.annotate(month=TruncMonth('created_at')).values('month').annotate(total=Count('id')).order_by('month'))
    progressed = applications.exclude(status__in=[Application.Status.PREPARING, Application.Status.APPLIED]).count()
    offers = applications.filter(status__in=[Application.Status.OFFER, Application.Status.ACCEPTED]).count()
    total = applications.count()
    context = {
        'application_count': total,
        'status_counts': applications.values('status').annotate(total=Count('id')).order_by('status'),
        'upcoming_interviews': Interview.objects.filter(application__user=request.user, scheduled_at__gte=timezone.now()).select_related('application__job_position__company')[:5],
        'deadlines': JobPosition.objects.filter(company__user=request.user, application_deadline__gte=today, application_deadline__lte=today + timedelta(days=14)).select_related('company')[:5],
        'follow_ups': applications.filter(next_action_date__lte=today).exclude(status__in=['accepted', 'rejected', 'withdrawn', 'closed'])[:5],
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
        'interview_conversion': round(progressed * 100 / total, 1) if total else 0,
        'offer_conversion': round(offers * 100 / total, 1) if total else 0,
        'source_chart': {'labels': [dict(Application.Source.choices).get(x['source'], x['source']) for x in source_counts], 'values': [x['total'] for x in source_counts]},
        'monthly_chart': {'labels': [x['month'].strftime('%Y-%m') for x in monthly_counts], 'values': [x['total'] for x in monthly_counts]},
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def calendar_events(request):
    events = []
    for interview in Interview.objects.filter(application__user=request.user):
        events.append({'title': f'面试：{interview.title}', 'start': interview.scheduled_at.isoformat(), 'url': f'/applications/{interview.application_id}/'})
    for job in JobPosition.objects.filter(company__user=request.user, application_deadline__isnull=False):
        events.append({'title': f'截止：{job.company.name} {job.title}', 'start': job.application_deadline.isoformat(), 'url': f'/jobs/{job.pk}/'})
    return JsonResponse(events, safe=False)


@login_required
def notifications(request):
    return render(request, 'core/notifications.html', {'notifications': Notification.objects.filter(user=request.user)})


@login_required
def notification_read(request, pk):
    if request.method == 'POST':
        item = get_object_or_404(Notification, pk=pk, user=request.user)
        item.is_read = True
        item.save(update_fields=('is_read',))
    return redirect('core:notifications')

# Create your views here.
