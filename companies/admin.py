from django.contrib import admin

from .models import Company, JobPosition


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'status', 'priority', 'industry', 'updated_at')
    list_filter = ('status', 'priority', 'industry')
    search_fields = ('name', 'industry', 'location')
    autocomplete_fields = ('user',)


@admin.register(JobPosition)
class JobPositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'status', 'location', 'application_deadline')
    list_filter = ('status', 'work_mode', 'employment_type')
    search_fields = ('title', 'company__name', 'department', 'location')
    autocomplete_fields = ('company',)
