from django import forms

from .models import Company, JobPosition


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class CompanyForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Company
        exclude = ('user', 'archived_at', 'created_at', 'updated_at')


class JobPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = JobPosition
        exclude = ('created_at', 'updated_at')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True)

    def clean(self):
        cleaned = super().clean()
        company = cleaned.get('company')
        source_url = cleaned.get('source_url')
        title = cleaned.get('title')
        if company and title and source_url:
            duplicate = JobPosition.objects.filter(company=company, title__iexact=title, source_url=source_url)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error('source_url', '相同公司、职位名称和链接的职位已存在。')
        return cleaned
