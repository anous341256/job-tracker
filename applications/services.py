from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from companies.models import JobPosition

from .models import Application, ApplicationStatusLog

TERMINAL_STATUSES = {
    Application.Status.OFFER,
    Application.Status.ACCEPTED,
    Application.Status.REJECTED,
    Application.Status.WITHDRAWN,
    Application.Status.GHOSTED,
    Application.Status.CLOSED,
}

PIPELINE_STAGES = (
    ('unapplied', '未投递'),
    ('researching', '调查中（说明会等）'),
    ('applied', '已投递（ES）'),
    ('interviewing', '面试中'),
    ('ended', '已结束'),
)
PIPELINE_STAGE_LABELS = dict(PIPELINE_STAGES)
PIPELINE_STAGE_RANK = {value: index for index, (value, _) in enumerate(PIPELINE_STAGES)}
ENDED_OUTCOMES = (
    (Application.Status.OFFER, '内定待决定'),
    (Application.Status.ACCEPTED, '决定入社'),
    (Application.Status.REJECTED, '未通过'),
    (Application.Status.WITHDRAWN, '主动辞退'),
    (Application.Status.GHOSTED, '长期无回复'),
    (Application.Status.CLOSED, '其他结束'),
)
ENDED_OUTCOME_LABELS = dict(ENDED_OUTCOMES)


def pipeline_stage(application):
    if not application:
        return 'unapplied'
    if application.status == Application.Status.PREPARING:
        return 'researching'
    if application.status in {
        Application.Status.APPLIED,
        Application.Status.SCREENING,
        Application.Status.ASSESSMENT,
    }:
        return 'applied'
    if application.status == Application.Status.INTERVIEWING:
        return 'interviewing'
    return 'ended'


def latest_application_for_job(job, *, lock=False):
    queryset = Application.objects.filter(user=job.company.user, job_position=job).order_by('-created_at', '-pk')
    if lock:
        queryset = queryset.select_for_update()
    return queryset.first()


def _model_status_for_stage(stage, outcome=''):
    if stage == 'researching':
        return Application.Status.PREPARING
    if stage == 'applied':
        return Application.Status.APPLIED
    if stage == 'interviewing':
        return Application.Status.INTERVIEWING
    if stage == 'ended' and outcome in ENDED_OUTCOME_LABELS:
        return outcome
    raise ValidationError('请选择有效的求职阶段和结束结果。')


@transaction.atomic
def change_job_pipeline(*, job, user, stage, outcome='', note='', backward_confirmed=False):
    """Create or update the latest application behind a five-stage job control."""
    locked_job = JobPosition.objects.select_for_update().select_related('company').get(pk=job.pk)
    if locked_job.company.user_id != user.id:
        raise ValidationError('不能修改其他用户的职位。')
    if stage not in PIPELINE_STAGE_LABELS:
        raise ValidationError('无效的求职阶段。')

    application = latest_application_for_job(locked_job, lock=True)
    current_stage = pipeline_stage(application)
    if stage == 'unapplied':
        if application:
            raise ValidationError('已有历史记录的职位不能删除回未投递；请结束当前流程。')
        return None

    target_status = _model_status_for_stage(stage, outcome)
    if application and PIPELINE_STAGE_RANK[stage] < PIPELINE_STAGE_RANK[current_stage] and not backward_confirmed:
        raise ValidationError('向前一阶段调整需要确认。')

    # A finished historical attempt is immutable. Starting another active stage
    # creates a new attempt and keeps the old timeline intact.
    if application and current_stage == 'ended' and stage != 'ended':
        application = None

    if application is None:
        application = Application.objects.create(
            user=user,
            job_position=locked_job,
            status=target_status,
            applied_at=timezone.localdate() if stage in {'applied', 'interviewing'} else None,
            priority=locked_job.company.priority,
        )
        ApplicationStatusLog.objects.create(
            application=application,
            to_status=target_status,
            changed_by=user,
            note=note,
        )
        return application

    changed = change_status(
        application=application,
        status=target_status,
        user=user,
        note=note,
    )
    if stage in {'applied', 'interviewing'} and not changed.applied_at:
        changed.applied_at = timezone.localdate()
        changed.save(update_fields=('applied_at', 'updated_at'))
    return changed


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
