from datetime import datetime, time, timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone

from accounts.models import Profile
from applications.models import Application, Interview
from companies.models import JobPosition
from .models import HostAgentCommand, Notification, Reminder


def _local_morning(day):
    return timezone.make_aware(datetime.combine(day, time(9)))


def _replace_pending_reminder(user, kind, object_key, scheduled_at, title, message, url):
    Reminder.objects.filter(user=user, kind=kind, object_key=object_key, status=Reminder.Status.PENDING).exclude(scheduled_at=scheduled_at).delete()
    Reminder.objects.get_or_create(
        user=user, kind=kind, object_key=object_key, scheduled_at=scheduled_at,
        defaults={'title': title, 'message': message, 'url': url},
    )


@shared_task
def build_reminders():
    now = timezone.now()
    today = timezone.localdate()
    jobs = JobPosition.objects.filter(application_deadline__range=(today, today + timedelta(days=8))).select_related('company__user')
    for job in jobs:
        for days in (7, 3, 1):
            scheduled = _local_morning(job.application_deadline - timedelta(days=days))
            if scheduled >= now - timedelta(hours=1):
                _replace_pending_reminder(job.company.user, Reminder.Kind.DEADLINE, f'job:{job.pk}:{days}d', scheduled, '职位即将截止', f'{job.company.name} 的 {job.title} 将在 {days} 天后截止。', f'/jobs/{job.pk}/')

    active_interviews = Interview.objects.filter(status=Interview.Status.SCHEDULED, scheduled_at__range=(now, now + timedelta(days=8))).select_related('application__user')
    active_ids = set(active_interviews.values_list('id', flat=True))
    Reminder.objects.filter(kind=Reminder.Kind.INTERVIEW, status=Reminder.Status.PENDING, object_key__startswith='interview:').exclude(object_key__regex=rf'^interview:({"|".join(map(str, active_ids))}):' if active_ids else r'^$').delete()
    for interview in active_interviews:
        for hours in (24, 1):
            scheduled = interview.scheduled_at - timedelta(hours=hours)
            if scheduled >= now - timedelta(hours=1):
                _replace_pending_reminder(interview.application.user, Reminder.Kind.INTERVIEW, f'interview:{interview.pk}:{hours}h', scheduled, '面试提醒', f'{interview.title} 将在 {hours} 小时后开始。', f'/applications/{interview.application_id}/')

    applications = Application.objects.filter(next_action_date__range=(today, today + timedelta(days=8)), archived_at__isnull=True).select_related('user')
    for application in applications:
        scheduled = _local_morning(application.next_action_date)
        _replace_pending_reminder(application.user, Reminder.Kind.FOLLOW_UP, f'application:{application.pk}', scheduled, '投递跟进提醒', application.next_action or str(application), f'/applications/{application.pk}/')


@shared_task
def send_due_reminders():
    due_ids = list(Reminder.objects.filter(status=Reminder.Status.PENDING, scheduled_at__lte=timezone.now()).values_list('id', flat=True))
    for reminder_id in due_ids:
        with transaction.atomic():
            reminder = Reminder.objects.select_for_update().select_related('user').filter(pk=reminder_id, status=Reminder.Status.PENDING).first()
            if not reminder:
                continue
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


@shared_task
def expire_host_agent_commands():
    cutoff = timezone.now() - timedelta(minutes=30)
    commands = HostAgentCommand.objects.filter(
        status__in=(HostAgentCommand.Status.QUEUED, HostAgentCommand.Status.RUNNING),
        created_at__lt=cutoff,
    ).select_related('ai_task')
    for command in commands:
        command.status = HostAgentCommand.Status.EXPIRED
        command.completed_at = timezone.now()
        command.error_message = '本机代理在 30 分钟内未完成该任务。'
        command.save(update_fields=('status', 'completed_at', 'error_message'))
        if command.ai_task_id:
            command.ai_task.status = 'failed'
            command.ai_task.error_type = 'HostAgentTimeout'
            command.ai_task.error_message = command.error_message
            command.ai_task.finished_at = timezone.now()
            command.ai_task.save(update_fields=('status', 'error_type', 'error_message', 'finished_at'))


@shared_task
def queue_periodic_outlook_syncs():
    """Queue bounded Outlook pages; the Windows agent remains the only COM reader."""
    if not settings.HOST_AGENT_ENABLED or settings.HOST_AGENT_AUTO_SYNC_MINUTES <= 0:
        return 0
    from mailboxes.models import EmailAccount

    now = timezone.now()
    due_before = now - timedelta(minutes=settings.HOST_AGENT_AUTO_SYNC_MINUTES)
    accounts = EmailAccount.objects.filter(
        provider=EmailAccount.Provider.OUTLOOK_LOCAL,
        status=EmailAccount.Status.ACTIVE,
    ).filter(
        models.Q(last_synced_at__isnull=True) | models.Q(last_synced_at__lte=due_before)
    ).select_related('user')
    queued = 0
    for account in accounts:
        active = HostAgentCommand.objects.filter(
            email_account=account,
            command_type=HostAgentCommand.Type.OUTLOOK_SYNC,
            status__in=(HostAgentCommand.Status.QUEUED, HostAgentCommand.Status.RUNNING),
        ).exists()
        if active:
            continue
        payload = {'limit': 100, 'days': 30, 'folder': account.sync_folder}
        if account.last_synced_at:
            payload['since'] = (account.last_synced_at - timedelta(minutes=10)).isoformat()
        HostAgentCommand.objects.create(
            user=account.user,
            email_account=account,
            command_type=HostAgentCommand.Type.OUTLOOK_SYNC,
            payload=payload,
        )
        queued += 1
    return queued
