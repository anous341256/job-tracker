from django.contrib import admin

from .models import EmailAccount, SyncedEmail

@admin.register(EmailAccount)
class EmailAccountAdmin(admin.ModelAdmin):
    list_display = ('email_address', 'provider', 'status', 'last_synced_at')
    exclude = ('encrypted_access_token', 'encrypted_refresh_token')

@admin.register(SyncedEmail)
class SyncedEmailAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender', 'account', 'received_at')
