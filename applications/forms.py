from django import forms
from core.form_widgets import apply_date_picker_widgets
from .models import Application, Interview


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        exclude = ('user', 'status', 'archived_at', 'created_at', 'updated_at')
        widgets = {
            'applied_at': forms.DateInput(attrs={'type': 'date'}),
            'next_action_date': forms.DateInput(attrs={'type': 'date'}),
            'last_contact_at': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
            'withdrawn_reason': forms.Textarea(attrs={'rows': 3}),
            'rejection_reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_date_picker_widgets(self.fields)
        self.user = user
        if user:
            self.fields['job_position'].queryset = self.fields['job_position'].queryset.filter(company__user=user)
            self.fields['resume'].queryset = self.fields['resume'].queryset.filter(user=user, archived_at__isnull=True)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        exclude = ('application', 'created_at', 'updated_at')
        widgets = {'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_date_picker_widgets(self.fields)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
