from django import forms

from core.form_widgets import apply_date_picker_widgets

from .models import Company, JobPosition


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_date_picker_widgets(self.fields)
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
        widgets = {
            'application_deadline': forms.DateInput(attrs={'type': 'date'}),
            'published_at': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 5}),
            'requirements': forms.Textarea(attrs={'rows': 5}),
            'benefits': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['company'].queryset = Company.objects.filter(user=user, archived_at__isnull=True)
        self.fields['category_other'].widget.attrs.update({
            'placeholder': '例如：研究职、事务职',
            'data-other-category': 'true',
        })

    def clean(self):
        cleaned = super().clean()
        company = cleaned.get('company')
        source_url = cleaned.get('source_url')
        title = cleaned.get('title')
        category = cleaned.get('category')
        category_other = (cleaned.get('category_other') or '').strip()
        if category == JobPosition.Category.OTHER and not category_other:
            self.add_error('category_other', '选择“其他”时，请填写职位类别。')
        elif category != JobPosition.Category.OTHER:
            cleaned['category_other'] = ''
        if company and title and source_url:
            duplicate = JobPosition.objects.filter(company=company, title__iexact=title, source_url=source_url)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error('source_url', '相同公司、职位名称和链接的职位已存在。')
        return cleaned
