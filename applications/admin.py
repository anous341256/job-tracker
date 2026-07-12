from django.contrib import admin

from .models import Application, ApplicationStatusLog, Interview


class ApplicationStatusLogInline(admin.TabularInline):
    model = ApplicationStatusLog
    extra = 0
    readonly_fields = ('changed_at',)


class InterviewInline(admin.TabularInline):
    model = Interview
    extra = 0


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('job_position', 'user', 'status', 'priority', 'applied_at', 'next_action_date')
    list_filter = ('status', 'priority', 'source')
    search_fields = ('job_position__title', 'job_position__company__name', 'user__username')
    autocomplete_fields = ('user', 'job_position')
    inlines = (ApplicationStatusLogInline, InterviewInline)


@admin.register(ApplicationStatusLog)
class ApplicationStatusLogAdmin(admin.ModelAdmin):
    list_display = ('application', 'from_status', 'to_status', 'changed_at', 'changed_by')
    list_filter = ('to_status', 'changed_at')
    autocomplete_fields = ('application', 'changed_by')


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ('title', 'application', 'round_number', 'scheduled_at', 'status', 'result')
    list_filter = ('status', 'result', 'interview_type')
    search_fields = ('title', 'application__job_position__title', 'interviewer_names')
    autocomplete_fields = ('application',)
