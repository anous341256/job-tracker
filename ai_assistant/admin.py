from django.contrib import admin
from .models import (
    AIMatchAnalysis,
    AISettings,
    AITask,
    EmailAssistantMessage,
    EmailAssistantThread,
    EmailScheduleCandidate,
    EmailTodoCandidate,
)


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'default_provider', 'openai_key_verified', 'allow_sensitive_cloud')
    exclude = ('encrypted_openai_api_key',)


@admin.register(AITask)
class AITaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'task_type', 'provider', 'model', 'status', 'created_at')
    readonly_fields = ('input_payload', 'result', 'error_message')


admin.site.register(AIMatchAnalysis)


@admin.register(EmailAssistantThread)
class EmailAssistantThreadAdmin(admin.ModelAdmin):
    list_display = ('email', 'user', 'status', 'resolution', 'last_activity_at')
    list_filter = ('status', 'resolution')
    search_fields = ('email__subject', 'email__sender', 'user__username')


@admin.register(EmailAssistantMessage)
class EmailAssistantMessageAdmin(admin.ModelAdmin):
    list_display = ('thread', 'role', 'task', 'created_at')
    list_filter = ('role',)
    search_fields = ('thread__email__subject',)
    readonly_fields = ('content', 'structured_data', 'client_request_id')


@admin.register(EmailScheduleCandidate)
class EmailScheduleCandidateAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'event_type', 'starts_at', 'version')
    list_filter = ('status', 'event_type')
    search_fields = ('title', 'email__subject', 'user__username')


@admin.register(EmailTodoCandidate)
class EmailTodoCandidateAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'action_type', 'due_at', 'priority', 'version')
    list_filter = ('status', 'action_type', 'priority')
    search_fields = ('title', 'email__subject', 'user__username')
