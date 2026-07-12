from django import forms

class ComposeEmailForm(forms.Form):
    account = forms.ModelChoiceField(queryset=None)
    to = forms.EmailField()
    subject = forms.CharField(max_length=300)
    body = forms.CharField(widget=forms.Textarea)
    application_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    def __init__(self, *args, user=None, **kwargs):
        from .models import EmailAccount
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = EmailAccount.objects.filter(user=user, status=EmailAccount.Status.ACTIVE)
        for field in self.fields.values(): field.widget.attrs.setdefault('class', 'form-control')


class EmailLinkForm(forms.Form):
    company = forms.ModelChoiceField(queryset=None, required=False)
    application = forms.ModelChoiceField(queryset=None, required=False)
    contact = forms.ModelChoiceField(queryset=None, required=False)
    def __init__(self, *args, user=None, **kwargs):
        from companies.models import Company
        from applications.models import Application
        from productivity.models import Contact
        super().__init__(*args, **kwargs)
        self.fields['company'].queryset = Company.objects.filter(user=user)
        self.fields['application'].queryset = Application.objects.filter(user=user)
        self.fields['contact'].queryset = Contact.objects.filter(user=user)
        for field in self.fields.values(): field.widget.attrs['class'] = 'form-select'
