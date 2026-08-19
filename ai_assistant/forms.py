import uuid

from django import forms

from applications.models import Application
from companies.models import Company, JobPosition
from productivity.models import Contact, Resume
from .models import AISettings, EmailScheduleCandidate, EmailTodoCandidate


class AISettingsForm(forms.ModelForm):
    openai_api_key = forms.CharField(required=False, label='新的 OpenAI API Key', widget=forms.PasswordInput(render_value=False), help_text='留空表示不修改现有密钥。')
    confirm_sensitive_cloud = forms.BooleanField(required=False, label='我理解简历文本会发送给 OpenAI，并授权后续匹配任务使用云端模型')

    class Meta:
        model = AISettings
        fields = ('default_provider', 'ollama_url', 'ollama_model', 'openai_fast_model', 'openai_quality_model', 'allow_sensitive_cloud', 'email_schedule_auto_enabled', 'email_schedule_auto_limit')
        labels = {
            'default_provider': '默认 Provider', 'ollama_url': 'Ollama 地址', 'ollama_model': '本地模型',
            'openai_fast_model': 'OpenAI 快速模型', 'openai_quality_model': 'OpenAI 质量模型',
            'allow_sensitive_cloud': '允许敏感内容发送到 OpenAI',
            'email_schedule_auto_enabled': '新邮件自动提取日程与 To Do',
            'email_schedule_auto_limit': '每次自动分析邮件上限',
        }

    def clean(self):
        data = super().clean()
        if data.get('allow_sensitive_cloud') and not data.get('confirm_sensitive_cloud') and not self.instance.allow_sensitive_cloud:
            self.add_error('confirm_sensitive_cloud', '首次开启云端敏感内容授权时必须确认。')
        return data


class JDParseForm(forms.Form):
    provider = forms.ChoiceField(choices=AISettings.Provider.choices, label='Provider')
    source_text = forms.CharField(label='招聘 JD', widget=forms.Textarea(attrs={'rows': 18}), max_length=50000)


class JobMatchForm(forms.Form):
    provider = forms.ChoiceField(choices=AISettings.Provider.choices, label='Provider')
    resume = forms.ModelChoiceField(queryset=None, label='简历')
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['resume'].queryset = Resume.objects.filter(user=user, archived_at__isnull=True)


class EmailScheduleReviewForm(forms.ModelForm):
    participants = forms.CharField(required=False, label='参与人（每行一个）', widget=forms.Textarea(attrs={'rows': 2}))
    target = forms.ChoiceField(
        choices=(('calendar', '加入普通日程'), ('interview', '创建面试'), ('todo', '创建 To Do')),
        label='审核通过后执行',
    )
    job_position = forms.ModelChoiceField(queryset=JobPosition.objects.none(), required=False, label='关联职位')

    class Meta:
        model = EmailScheduleCandidate
        fields = ('title', 'event_type', 'starts_at', 'ends_at', 'timezone_name', 'location', 'meeting_url', 'participants', 'summary', 'company', 'job_position', 'application', 'contact')
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'summary': forms.Textarea(attrs={'rows': 3}),
            'participants': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company'].queryset = Company.objects.filter(user=user)
        self.fields['company'].required = True
        self.fields['job_position'].queryset = JobPosition.objects.filter(company__user=user).select_related('company')
        self.fields['application'].queryset = Application.objects.filter(user=user).select_related('job_position__company')
        self.fields['contact'].queryset = Contact.objects.filter(user=user)
        if self.instance.application_id:
            self.fields['job_position'].initial = self.instance.application.job_position_id
        if self.instance.event_type == EmailScheduleCandidate.EventType.INTERVIEW:
            self.fields['target'].initial = 'interview'
        if isinstance(self.initial.get('participants'), list):
            self.initial['participants'] = '\n'.join(self.initial['participants'])
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control' if not isinstance(field.widget, forms.Select) else 'form-select')

    def clean_participants(self):
        value = self.cleaned_data.get('participants', '')
        if isinstance(value, list):
            return value
        return [line.strip() for line in value.replace(',', '\n').splitlines() if line.strip()]

    def clean(self):
        data = super().clean()
        if data.get('target') in {'calendar', 'interview'} and not data.get('starts_at'):
            self.add_error('starts_at', '加入日程前请补充开始时间。')
        company = data.get('company')
        job = data.get('job_position')
        application = data.get('application')
        if job and company and job.company_id != company.id:
            self.add_error('job_position', '关联职位必须属于所选公司。')
        if application and company and application.job_position.company_id != company.id:
            self.add_error('application', '关联投递必须属于所选公司。')
        if application and job and application.job_position_id != job.id:
            self.add_error('application', '关联投递必须属于所选职位。')
        if data.get('target') == 'interview' and not (application or job):
            self.add_error('job_position', '创建面试必须关联职位或已有投递。')
        if data.get('ends_at') and data.get('starts_at') and data['ends_at'] <= data['starts_at']:
            self.add_error('ends_at', '结束时间必须晚于开始时间。')
        return data


class EmailTodoReviewForm(forms.ModelForm):
    class Meta:
        model = EmailTodoCandidate
        fields = (
            'title', 'action_type', 'due_at', 'timezone_name', 'priority',
            'action_url', 'notes', 'company', 'job_position', 'application',
        )
        widgets = {
            'due_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True)
        self.fields['company'].required = True
        self.fields['job_position'].queryset = JobPosition.objects.filter(company__user=user).select_related('company')
        self.fields['application'].queryset = Application.objects.filter(user=user).select_related('job_position__company')
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-select' if isinstance(field.widget, forms.Select) else 'form-control')

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


for form_class in (AISettingsForm, JDParseForm, JobMatchForm):
    old_init = form_class.__init__
    def styled_init(self, *args, _old=old_init, **kwargs):
        _old(self, *args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput): field.widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(field.widget, forms.Select): field.widget.attrs.setdefault('class', 'form-select')
            else: field.widget.attrs.setdefault('class', 'form-control')
    form_class.__init__ = styled_init


class EmailAssistantChatForm(forms.Form):
    content = forms.CharField(
        label='给千问的消息',
        max_length=2000,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': '例如：这是日本时间，结束时间是下午四点。',
        }),
    )
    client_request_id = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields['client_request_id'].initial = uuid.uuid4()


class EmailAssistantCompanyForm(forms.Form):
    company = forms.ModelChoiceField(
        queryset=Company.objects.none(),
        required=False,
        label='关联已有公司',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    new_company_name = forms.CharField(
        required=False,
        max_length=200,
        label='或快速新建公司',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '只需要填写公司名称'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True).order_by('name')

    def clean(self):
        data = super().clean()
        if not data.get('company') and not (data.get('new_company_name') or '').strip():
            raise forms.ValidationError('请选择已有公司，或输入新公司名称。')
        return data
