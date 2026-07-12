from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _


class Company(models.Model):
    class Status(models.TextChoices):
        RESEARCHING = 'researching', _('调研中')
        WATCHING = 'watching', _('持续关注')
        TARGET = 'target', _('目标公司')
        ACTIVE = 'active', _('正在接触')
        PAUSED = 'paused', _('暂停关注')
        REJECTED = 'rejected', _('暂不考虑')
        ARCHIVED = 'archived', _('已归档')

    class Priority(models.TextChoices):
        LOW = 'low', _('低')
        MEDIUM = 'medium', _('中')
        HIGH = 'high', _('高')
        DREAM = 'dream', _('梦想公司')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='companies',
        verbose_name=_('用户'),
    )
    name = models.CharField(_('公司名称'), max_length=200)
    status = models.CharField(
        _('状态'), max_length=20, choices=Status.choices, default=Status.RESEARCHING
    )
    website_url = models.URLField(_('公司官网'), max_length=500, blank=True)
    careers_url = models.URLField(_('招聘官网'), max_length=500, blank=True)
    industry = models.CharField(_('行业'), max_length=100, blank=True)
    location = models.CharField(_('所在地'), max_length=200, blank=True)
    company_size = models.CharField(_('公司规模'), max_length=100, blank=True)
    priority = models.CharField(
        _('优先级'), max_length=10, choices=Priority.choices, default=Priority.MEDIUM
    )
    notes = models.TextField(_('备注'), blank=True)
    archived_at = models.DateTimeField(_('归档时间'), null=True, blank=True)
    created_at = models.DateTimeField(_('创建时间'), auto_now_add=True)
    updated_at = models.DateTimeField(_('更新时间'), auto_now=True)

    class Meta:
        verbose_name = _('公司')
        verbose_name_plural = _('公司')
        ordering = ('-updated_at', 'name')
        constraints = [
            models.UniqueConstraint(fields=('user', 'name'), name='unique_company_name_per_user'),
        ]
        indexes = [
            models.Index(fields=('user', 'status'), name='company_user_status_idx'),
            models.Index(fields=('user', 'priority'), name='company_user_priority_idx'),
        ]

    def __str__(self):
        return self.name


class JobPosition(models.Model):
    class Category(models.TextChoices):
        TECHNICAL = 'technical', _('技术职')
        GENERAL = 'general', _('综合职')
        CONSULTING = 'consulting', _('咨询职')
        SALES = 'sales', _('营业职')
        PLANNING = 'planning', _('企划／运营职')
        DESIGN = 'design', _('设计职')
        OTHER = 'other', _('其他')

    class Status(models.TextChoices):
        DRAFT = 'draft', _('待整理')
        OPEN = 'open', _('招聘中')
        CLOSED = 'closed', _('已关闭')
        EXPIRED = 'expired', _('已过期')
        FILLED = 'filled', _('已招满')
        UNKNOWN = 'unknown', _('未知')

    class WorkMode(models.TextChoices):
        ONSITE = 'onsite', _('现场办公')
        HYBRID = 'hybrid', _('混合办公')
        REMOTE = 'remote', _('远程办公')
        UNKNOWN = 'unknown', _('未说明')

    class EmploymentType(models.TextChoices):
        FULL_TIME = 'full_time', _('全职')
        PART_TIME = 'part_time', _('兼职')
        CONTRACT = 'contract', _('合同工')
        INTERNSHIP = 'internship', _('实习')
        TEMPORARY = 'temporary', _('临时')
        OTHER = 'other', _('其他')

    class SalaryPeriod(models.TextChoices):
        HOURLY = 'hourly', _('时薪')
        MONTHLY = 'monthly', _('月薪')
        YEARLY = 'yearly', _('年薪')

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name='job_positions',
        verbose_name=_('公司'),
    )
    title = models.CharField(_('职位名称'), max_length=200)
    category = models.CharField(
        _('职位类别'), max_length=20, choices=Category.choices, default=Category.TECHNICAL
    )
    category_other = models.CharField(
        _('其他职位类别'), max_length=100, blank=True,
        help_text=_('选择“其他”时填写。'),
    )
    department = models.CharField(_('部门'), max_length=150, blank=True)
    status = models.CharField(
        _('状态'), max_length=10, choices=Status.choices, default=Status.OPEN
    )
    description = models.TextField(_('职位描述'), blank=True)
    requirements = models.TextField(_('任职要求'), blank=True)
    benefits = models.TextField(_('福利待遇'), blank=True)
    source_url = models.URLField(_('职位链接'), max_length=1000, blank=True)
    application_deadline = models.DateField(_('投递截止日期'), null=True, blank=True)
    published_at = models.DateField(_('发布日期'), null=True, blank=True)
    location = models.CharField(_('工作地点'), max_length=200, blank=True)
    work_mode = models.CharField(
        _('办公方式'), max_length=10, choices=WorkMode.choices, default=WorkMode.UNKNOWN
    )
    employment_type = models.CharField(
        _('雇佣类型'), max_length=20, choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    salary_min = models.DecimalField(
        _('最低薪资'), max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    salary_max = models.DecimalField(
        _('最高薪资'), max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    salary_currency = models.CharField(_('薪资币种'), max_length=3, default='JPY')
    salary_period = models.CharField(
        _('薪资周期'), max_length=10, choices=SalaryPeriod.choices,
        default=SalaryPeriod.YEARLY,
    )
    notes = models.TextField(_('备注'), blank=True)
    ai_metadata = models.JSONField(_('AI 结构化元数据'), default=dict, blank=True)
    created_at = models.DateTimeField(_('创建时间'), auto_now_add=True)
    updated_at = models.DateTimeField(_('更新时间'), auto_now=True)

    class Meta:
        verbose_name = _('职位')
        verbose_name_plural = _('职位')
        ordering = ('application_deadline', '-updated_at')
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(salary_min__isnull=True)
                    | Q(salary_max__isnull=True)
                    | Q(salary_min__lte=F('salary_max'))
                ),
                name='job_salary_min_lte_max',
            ),
        ]
        indexes = [
            models.Index(fields=('company', 'status'), name='job_company_status_idx'),
            models.Index(fields=('application_deadline',), name='job_deadline_idx'),
        ]

    def __str__(self):
        return f'{self.company.name} - {self.title}'
