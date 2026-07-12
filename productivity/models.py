from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from applications.models import Application
from companies.models import Company, JobPosition


def validate_file_size(value):
    if value.size > 10 * 1024 * 1024:
        raise ValidationError('文件不能超过 10 MB。')


class Contact(models.Model):
    class Type(models.TextChoices):
        HR = 'hr', 'HR'
        RECRUITER = 'recruiter', '猎头'
        REFERRER = 'referrer', '内推人'
        INTERVIEWER = 'interviewer', '面试官'
        MANAGER = 'manager', '负责人'
        OTHER = 'other', '其他'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contacts')
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='contacts')
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=150, blank=True)
    contact_type = models.CharField(max_length=20, choices=Type.choices, default=Type.OTHER)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    linkedin_url = models.URLField(max_length=500, blank=True)
    last_contact_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.company})'


class Resume(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=20, default='zh-hans')
    target_role = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to='resumes/%Y/%m/', validators=[FileExtensionValidator(['pdf', 'doc', 'docx']), validate_file_size])
    is_default = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} {self.version}'.strip()


class Document(models.Model):
    class Type(models.TextChoices):
        COVER_LETTER = 'cover_letter', '求职信'
        OFFER = 'offer', 'Offer'
        JOB_DESCRIPTION = 'job_description', 'JD 资料'
        INTERVIEW = 'interview', '面试资料'
        OTHER = 'other', '其他'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='documents')
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    application = models.ForeignKey(Application, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    document_type = models.CharField(max_length=20, choices=Type.choices, default=Type.OTHER)
    file = models.FileField(upload_to='documents/%Y/%m/', validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'txt']), validate_file_size])
    original_name = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file:
            self.original_name = self.original_name or Path(self.file.name).name
            self.size = self.file.size
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_name or Path(self.file.name).name


class Communication(models.Model):
    class Channel(models.TextChoices):
        EMAIL = 'email', '邮件'
        PHONE = 'phone', '电话'
        WECHAT = 'wechat', '微信'
        LINKEDIN = 'linkedin', 'LinkedIn'
        MEETING = 'meeting', '会议'
        OTHER = 'other', '其他'

    class Direction(models.TextChoices):
        INBOUND = 'inbound', '收到'
        OUTBOUND = 'outbound', '发出'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='communications')
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='communications')
    application = models.ForeignKey(Application, on_delete=models.SET_NULL, null=True, blank=True, related_name='communications')
    contact = models.ForeignKey(Contact, on_delete=models.SET_NULL, null=True, blank=True, related_name='communications')
    channel = models.CharField(max_length=20, choices=Channel.choices)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    subject = models.CharField(max_length=300, blank=True)
    summary = models.TextField(blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-occurred_at',)

    def __str__(self):
        return self.subject or f'{self.get_channel_display()} · {self.occurred_at:%Y-%m-%d}'


class Tag(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#6c757d')
    companies = models.ManyToManyField(Company, blank=True, related_name='tags')
    job_positions = models.ManyToManyField(JobPosition, blank=True, related_name='tags')
    applications = models.ManyToManyField(Application, blank=True, related_name='tags')

    class Meta:
        constraints = [models.UniqueConstraint(fields=('user', 'name'), name='unique_tag_per_user')]

    def __str__(self):
        return self.name
