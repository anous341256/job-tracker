from django.contrib import admin

from .models import Notification, Reminder

admin.site.register(Notification)
admin.site.register(Reminder)
