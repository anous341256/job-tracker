from django import forms

from productivity.models import Resume
from .models import AISettings


class AISettingsForm(forms.ModelForm):
    openai_api_key = forms.CharField(required=False, label='新的 OpenAI API Key', widget=forms.PasswordInput(render_value=False), help_text='留空表示不修改现有密钥。')
    confirm_sensitive_cloud = forms.BooleanField(required=False, label='我理解简历文本会发送给 OpenAI，并授权后续匹配任务使用云端模型')

    class Meta:
        model = AISettings
        fields = ('default_provider', 'ollama_url', 'ollama_model', 'openai_fast_model', 'openai_quality_model', 'allow_sensitive_cloud')
        labels = {'default_provider': '默认 Provider', 'ollama_url': 'Ollama 地址', 'ollama_model': '本地模型', 'openai_fast_model': 'OpenAI 快速模型', 'openai_quality_model': 'OpenAI 质量模型', 'allow_sensitive_cloud': '允许敏感内容发送到 OpenAI'}

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


for form_class in (AISettingsForm, JDParseForm, JobMatchForm):
    old_init = form_class.__init__
    def styled_init(self, *args, _old=old_init, **kwargs):
        _old(self, *args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput): field.widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(field.widget, forms.Select): field.widget.attrs.setdefault('class', 'form-select')
            else: field.widget.attrs.setdefault('class', 'form-control')
    form_class.__init__ = styled_init
