from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Application user model.

    Keep authentication data here. Job-seeking profile data belongs in a
    separate profile model when that feature is introduced.
    """

    def __str__(self):
        return self.get_full_name() or self.username


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile'
    )
    display_name = models.CharField('显示名称', max_length=100, blank=True)
    location = models.CharField('所在地', max_length=200, blank=True)
    timezone = models.CharField('时区', max_length=64, default='Asia/Tokyo')
    target_role = models.CharField('目标职位', max_length=200, blank=True)
    default_currency = models.CharField('默认币种', max_length=3, default='JPY')
    email_reminders = models.BooleanField('接收邮件提醒', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or str(self.user)
