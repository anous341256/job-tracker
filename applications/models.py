from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from companies.models import Company, JobPosition


class Application(models.Model):
    class Status(models.TextChoices):
        PREPARING = 'preparing', _('准备材料')
        APPLIED = 'applied', _('已投递')
        SCREENING = 'screening', _('简历筛选')
        ASSESSMENT = 'assessment', _('笔试或测评')
        INTERVIEWING = 'interviewing', _('面试中')
        OFFER = 'offer', _('已收到 Offer')
        ACCEPTED = 'accepted', _('已接受 Offer')
        REJECTED = 'rejected', _('被拒绝')
        WITHDRAWN = 'withdrawn', _('主动撤回')
        GHOSTED = 'ghosted', _('长期未回复')
        CLOSED = 'closed', _('流程结束')

    class Source(models.TextChoices):
        COMPANY_WEBSITE = 'company_website', _('公司官网')
        JOB_BOARD = 'job_board', _('招聘平台')
        REFERRAL = 'referral', _('内推')
        RECRUITER = 'recruiter', _('猎头或招聘人员')
        CAMPUS = 'campus', _('校园招聘')
        SOCIAL_MEDIA = 'social_media', _('社交媒体')
        OTHER = 'other', _('其他')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='applications',
        verbose_name=_('用户'),
    )
    job_position = models.ForeignKey(
        JobPosition,
        on_delete=models.PROTECT,
        related_name='applications',
        verbose_name=_('职位'),
    )
    status = models.CharField(
        _('状态'), max_length=20, choices=Status.choices, default=Status.PREPARING
    )
    applied_at = models.DateField(_('投递日期'), null=True, blank=True)
    source = models.CharField(
        _('投递来源'), max_length=20, choices=Source.choices, default=Source.OTHER
    )
    source_detail = models.CharField(_('来源说明'), max_length=200, blank=True)
    priority = models.CharField(
        _('优先级'), max_length=10, choices=Company.Priority.choices,
        default=Company.Priority.MEDIUM,
    )
    next_action = models.CharField(_('下一步行动'), max_length=300, blank=True)
    next_action_date = models.DateField(_('下次跟进日期'), null=True, blank=True)
    last_contact_at = models.DateField(_('最近联系日期'), null=True, blank=True)
    expected_salary = models.DecimalField(
        _('期望薪资'), max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    expected_salary_currency = models.CharField(_('期望薪资币种'), max_length=3, default='JPY')
    resume = models.ForeignKey(
        'productivity.Resume', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='applications', verbose_name=_('使用的简历'),
    )
    archived_at = models.DateTimeField(_('归档时间'), null=True, blank=True)
    notes = models.TextField(_('备注'), blank=True)
    withdrawn_reason = models.TextField(_('撤回原因'), blank=True)
    rejection_reason = models.TextField(_('被拒原因'), blank=True)
    created_at = models.DateTimeField(_('创建时间'), auto_now_add=True)
    updated_at = models.DateTimeField(_('更新时间'), auto_now=True)

    class Meta:
        verbose_name = _('投递')
        verbose_name_plural = _('投递')
        ordering = ('-updated_at',)
        indexes = [
            models.Index(fields=('user', 'status'), name='app_user_status_idx'),
            models.Index(fields=('user', 'next_action_date'), name='app_user_next_action_idx'),
            models.Index(fields=('job_position',), name='app_job_position_idx'),
        ]

    def __str__(self):
        return f'{self.job_position} - {self.get_status_display()}'

    def clean(self):
        super().clean()
        terminal = {
            self.Status.OFFER, self.Status.ACCEPTED, self.Status.REJECTED,
            self.Status.WITHDRAWN, self.Status.GHOSTED, self.Status.CLOSED,
        }
        if self.user_id and self.job_position_id and self.status not in terminal:
            duplicate = Application.objects.filter(user_id=self.user_id, job_position_id=self.job_position_id).exclude(status__in=terminal)
            if self.pk: duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists(): raise ValidationError('该职位已经存在进行中的投递。')


class ApplicationStatusLog(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='status_logs',
        verbose_name=_('投递'),
    )
    from_status = models.CharField(
        _('原状态'), max_length=20, choices=Application.Status.choices, blank=True
    )
    to_status = models.CharField(
        _('新状态'), max_length=20, choices=Application.Status.choices
    )
    changed_at = models.DateTimeField(_('变更时间'), auto_now_add=True)
    note = models.TextField(_('说明'), blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='application_status_changes',
        verbose_name=_('操作用户'),
    )

    class Meta:
        verbose_name = _('投递状态记录')
        verbose_name_plural = _('投递状态记录')
        ordering = ('-changed_at', '-pk')
        indexes = [
            models.Index(fields=('application', 'changed_at'), name='app_status_timeline_idx'),
        ]

    def __str__(self):
        return f'{self.application}: {self.from_status or "开始"} -> {self.to_status}'


class Interview(models.Model):
    class Type(models.TextChoices):
        PHONE = 'phone', _('电话面试')
        VIDEO = 'video', _('视频面试')
        ONSITE = 'onsite', _('现场面试')
        TECHNICAL = 'technical', _('技术面试')
        BEHAVIORAL = 'behavioral', _('行为面试')
        HR = 'hr', _('HR 面试')
        CASE_STUDY = 'case_study', _('案例分析')
        OTHER = 'other', _('其他')

    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', _('已安排')
        COMPLETED = 'completed', _('已完成')
        CANCELLED = 'cancelled', _('已取消')
        RESCHEDULED = 'rescheduled', _('已改期')
        NO_SHOW = 'no_show', _('未出席')

    class Result(models.TextChoices):
        PENDING = 'pending', _('等待结果')
        PASSED = 'passed', _('通过')
        FAILED = 'failed', _('未通过')
        UNKNOWN = 'unknown', _('未知')

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='interviews',
        verbose_name=_('投递'),
    )
    round_number = models.PositiveSmallIntegerField(
        _('面试轮次'), validators=[MinValueValidator(1)]
    )
    title = models.CharField(_('面试名称'), max_length=200)
    interview_type = models.CharField(
        _('面试类型'), max_length=20, choices=Type.choices, default=Type.VIDEO
    )
    status = models.CharField(
        _('状态'), max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )
    scheduled_at = models.DateTimeField(_('面试时间'))
    duration_minutes = models.PositiveIntegerField(
        _('预计时长（分钟）'), null=True, blank=True, validators=[MinValueValidator(1)]
    )
    meeting_url = models.URLField(_('会议链接'), max_length=1000, blank=True)
    location = models.CharField(_('面试地点'), max_length=300, blank=True)
    interviewer_names = models.CharField(_('面试官'), max_length=500, blank=True)
    preparation_notes = models.TextField(_('准备笔记'), blank=True)
    questions = models.TextField(_('面试问题'), blank=True)
    reflection = models.TextField(_('面试复盘'), blank=True)
    result = models.CharField(
        _('结果'), max_length=10, choices=Result.choices, default=Result.PENDING
    )
    created_at = models.DateTimeField(_('创建时间'), auto_now_add=True)
    updated_at = models.DateTimeField(_('更新时间'), auto_now=True)

    class Meta:
        verbose_name = _('面试')
        verbose_name_plural = _('面试')
        ordering = ('scheduled_at', 'round_number')
        constraints = [
            models.UniqueConstraint(
                fields=('application', 'round_number'), name='unique_interview_round_per_application'
            ),
        ]
        indexes = [
            models.Index(fields=('status', 'scheduled_at'), name='interview_schedule_idx'),
        ]

    def __str__(self):
        return f'{self.application.job_position.title} - 第 {self.round_number} 轮'
