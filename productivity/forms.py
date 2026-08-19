from django import forms
from core.form_widgets import apply_date_picker_widgets
from .models import Communication, Contact, Document, Resume, Tag


class UserOwnedForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_date_picker_widgets(self.fields)
        self.user = user
        for field in self.fields.values(): field.widget.attrs.setdefault('class', 'form-control')
        for name in ('company', 'application', 'contact'):
            if name in self.fields and user:
                lookup = {'company': 'user', 'application': 'user', 'contact': 'user'}[name]
                self.fields[name].queryset = self.fields[name].queryset.filter(**{lookup: user})


class ContactForm(UserOwnedForm):
    class Meta: model = Contact; exclude = ('user', 'created_at', 'updated_at')
class ResumeForm(UserOwnedForm):
    class Meta: model = Resume; exclude = ('user', 'archived_at', 'created_at', 'updated_at')
class DocumentForm(UserOwnedForm):
    class Meta: model = Document; exclude = ('user', 'original_name', 'mime_type', 'size', 'created_at')
    def clean_file(self):
        file = self.cleaned_data['file']
        allowed = {'application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'image/png', 'image/jpeg', 'text/plain'}
        if getattr(file, 'content_type', '') not in allowed: raise forms.ValidationError('不支持的文件类型。')
        return file
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.mime_type = getattr(self.cleaned_data.get('file'), 'content_type', '')
        if commit: instance.save()
        return instance
class CommunicationForm(UserOwnedForm):
    class Meta: model = Communication; exclude = ('user', 'created_at'); widgets = {'occurred_at': forms.DateTimeInput(attrs={'type': 'datetime-local'})}
class TagForm(UserOwnedForm):
    class Meta: model = Tag; exclude = ('user',)
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if user:
            self.fields['companies'].queryset = self.fields['companies'].queryset.filter(user=user)
            self.fields['job_positions'].queryset = self.fields['job_positions'].queryset.filter(company__user=user)
            self.fields['applications'].queryset = self.fields['applications'].queryset.filter(user=user)
