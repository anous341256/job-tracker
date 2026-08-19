from django import forms

from core.form_widgets import apply_date_picker_widgets
from applications.models import Application
from companies.models import Company, JobPosition
from .models import CalendarEvent, TodoItem


class TodoItemForm(forms.ModelForm):
    class Meta:
        model = TodoItem
        fields = ('company', 'job_position', 'application', 'title', 'status', 'priority', 'due_at', 'source_url', 'notes')
        widgets = {
            'due_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, user=None, company=None, job_position=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True)
            self.fields['job_position'].queryset = JobPosition.objects.filter(company__user=user)
            self.fields['application'].queryset = Application.objects.filter(user=user)
        if company:
            self.fields['company'].initial = company
        if job_position:
            self.fields['job_position'].initial = job_position
        apply_date_picker_widgets(self.fields)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        data = super().clean()
        company = data.get('company')
        job = data.get('job_position')
        application = data.get('application')
        if company and self.user and company.user_id != self.user.id:
            self.add_error('company', '无权使用该公司。')
        if job and company and job.company_id != company.id:
            self.add_error('job_position', '关联职位必须属于所选公司。')
        if application and company and application.job_position.company_id != company.id:
            self.add_error('application', '关联投递必须属于所选公司。')
        if application and job and application.job_position_id != job.id:
            self.add_error('application', '关联投递必须属于所选职位。')
        return data


class CalendarEventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = ('company', 'job_position', 'title', 'event_type', 'starts_at', 'ends_at', 'location', 'meeting_url', 'notes')
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, company=None, job_position=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True)
            self.fields['job_position'].queryset = JobPosition.objects.filter(company__user=user)
        if company:
            self.fields['company'].initial = company
        if job_position:
            self.fields['job_position'].initial = job_position
        apply_date_picker_widgets(self.fields)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        data = super().clean()
        company = data.get('company')
        job = data.get('job_position')
        if company and self.user and company.user_id != self.user.id:
            self.add_error('company', '无权使用该公司。')
        if job and company and job.company_id != company.id:
            self.add_error('job_position', '关联职位必须属于所选公司。')
        if data.get('starts_at') and data.get('ends_at') and data['ends_at'] <= data['starts_at']:
            self.add_error('ends_at', '结束时间必须晚于开始时间。')
        return data
