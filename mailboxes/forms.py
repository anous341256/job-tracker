from django import forms

from applications.models import Application
from companies.models import Company
from productivity.models import Contact
from .models import EmailAccount


class ComposeEmailForm(forms.Form):
    account = forms.ModelChoiceField(queryset=None, label='邮箱账户')
    to = forms.EmailField(label='收件人')
    subject = forms.CharField(max_length=300, label='主题')
    body = forms.CharField(widget=forms.Textarea, label='正文')
    application_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = EmailAccount.objects.filter(user=user, status=EmailAccount.Status.ACTIVE).exclude(provider=EmailAccount.Provider.OUTLOOK_LOCAL)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class EmailLinkForm(forms.Form):
    company = forms.ModelChoiceField(queryset=None, required=False, label='公司')
    application = forms.ModelChoiceField(queryset=None, required=False, label='投递')
    contact = forms.ModelChoiceField(queryset=None, required=False, label='联系人')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True)
        self.fields['application'].queryset = Application.objects.filter(user=user, archived_at__isnull=True)
        self.fields['contact'].queryset = Contact.objects.filter(user=user)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select'


class QuickCompanyLinkForm(forms.Form):
    company = forms.ModelChoiceField(queryset=None, required=False, label='关联公司')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True).order_by('name')
        self.fields['company'].widget.attrs['class'] = 'form-select form-select-sm'


class OutlookFolderForm(forms.ModelForm):
    class Meta:
        model = EmailAccount
        fields = ('sync_folder',)
        labels = {'sync_folder': '同步文件夹'}
        help_texts = {'sync_folder': '使用 Inbox，或填写收件箱下的文件夹名称。'}
        widgets = {'sync_folder': forms.TextInput(attrs={'class': 'form-control form-control-sm'})}
