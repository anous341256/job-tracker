from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Application, ApplicationStatusLog

TERMINAL_STATUSES = {Application.Status.ACCEPTED, Application.Status.REJECTED, Application.Status.WITHDRAWN, Application.Status.CLOSED}


@transaction.atomic
def create_application(*, user, form):
    job = form.cleaned_data['job_position']
    if Application.objects.filter(user=user, job_position=job).exclude(status__in=TERMINAL_STATUSES).exists():
        raise ValidationError('该职位已经存在进行中的投递。')
    application = form.save(commit=False)
    application.user = user
    application.save()
    form.save_m2m()
    ApplicationStatusLog.objects.create(application=application, to_status=application.status, changed_by=user)
    return application


@transaction.atomic
def change_status(*, application, status, user, note=''):
    locked = Application.objects.select_for_update().get(pk=application.pk)
    if status not in Application.Status.values:
        raise ValidationError('无效状态。')
    old_status = locked.status
    if old_status != status:
        locked.status = status
        locked.save(update_fields=('status', 'updated_at'))
        ApplicationStatusLog.objects.create(application=locked, from_status=old_status, to_status=status, changed_by=user, note=note)
    return locked
