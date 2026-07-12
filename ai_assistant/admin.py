from django.contrib import admin
from .models import AIMatchAnalysis, AISettings, AITask


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'default_provider', 'openai_key_verified', 'allow_sensitive_cloud')
    exclude = ('encrypted_openai_api_key',)


@admin.register(AITask)
class AITaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'task_type', 'provider', 'model', 'status', 'created_at')
    readonly_fields = ('input_payload', 'result', 'error_message')


admin.site.register(AIMatchAnalysis)
