from datetime import datetime, time, timedelta

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from accounts.models import Profile
from applications.models import Application, Interview
from companies.models import JobPosition
from .models import Notification, Reminder


def _create_reminder(user, kind, object_key, scheduled_at, title, message, url):
    Reminder.objects.get_or_create(user=user, kind=kind, object_key=object_key, scheduled_at=scheduled_at, defaults={'title': title, 'message': message, 'url': url})


@shared_task
def build_reminders():
    today = timezone.localdate()
    for job in JobPosition.objects.filter(application_deadline__range=(today, today + timedelta(days=7))).select_related('company__user'):
        days = (job.application_deadline - today).days
        if days in (1, 3, 7):
            scheduled = timezone.make_aware(datetime.combine(today, time(9)))
            _create_reminder(job.company.user, Reminder.Kind.DEADLINE, f'job:{job.pk}:{days}', scheduled, '职位即将截止', f'{job.company.name} 的 {job.title} 将在 {days} 天后截止。', f'/jobs/{job.pk}/')
    now = timezone.now()
    for interview in Interview.objects.filter(scheduled_at__range=(now, now + timedelta(hours=24))).select_related('application__user'):
        hours = round((interview.scheduled_at - now).total_seconds() / 3600)
        if hours in (1, 24):
            _create_reminder(interview.application.user, Reminder.Kind.INTERVIEW, f'interview:{interview.pk}:{hours}', now, '面试提醒', interview.title, f'/applications/{interview.application_id}/')
    for app in Application.objects.filter(next_action_date=today).select_related('user'):
        scheduled = timezone.make_aware(datetime.combine(today, time(9)))
        _create_reminder(app.user, Reminder.Kind.FOLLOW_UP, f'application:{app.pk}', scheduled, '今日需要跟进', app.next_action or str(app), f'/applications/{app.pk}/')


@shared_task
def send_due_reminders():
    for reminder in Reminder.objects.filter(status=Reminder.Status.PENDING, scheduled_at__lte=timezone.now()).select_related('user'):
        try:
            Notification.objects.create(user=reminder.user, title=reminder.title, message=reminder.message, url=reminder.url)
            profile = Profile.objects.filter(user=reminder.user).first()
            if reminder.user.email and (not profile or profile.email_reminders):
                send_mail(reminder.title, reminder.message, None, [reminder.user.email])
            reminder.status = Reminder.Status.SENT
            reminder.sent_at = timezone.now()
            reminder.failure_reason = ''
        except Exception as exc:
            reminder.status = Reminder.Status.FAILED
            reminder.failure_reason = str(exc)[:1000]
        reminder.save(update_fields=('status', 'sent_at', 'failure_reason'))
