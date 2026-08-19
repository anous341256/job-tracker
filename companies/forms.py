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
        exclude = ('user', 'pinned_order', 'archived_at', 'created_at', 'updated_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].required = False
        self.fields['priority'].required = False
        self.fields['status'].initial = self.fields['status'].initial or Company.Status.RESEARCHING
        self.fields['priority'].initial = self.fields['priority'].initial or Company.Priority.MEDIUM


class CompoundJobForm(BootstrapFormMixin, forms.Form):
    title = forms.CharField(label='职位名称', max_length=200, required=False)
    category = forms.ChoiceField(label='职位类别', choices=JobPosition.Category.choices, required=False)
    source_url = forms.URLField(label='职位链接', max_length=1000, required=False)
    location = forms.CharField(label='工作地点', max_length=200, required=False)
    application_deadline = forms.DateField(label='职位截止日期', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    description = forms.CharField(label='职位描述 / JD', required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].initial = JobPosition.Category.TECHNICAL

    def clean(self):
        data = super().clean()
        touched = any(value not in (None, '') for key, value in data.items() if key != 'category')
        if touched and not data.get('title'):
            self.add_error('title', '填写职位信息时，职位名称不能为空。')
        return data


class CompoundScheduleForm(BootstrapFormMixin, forms.Form):
    title = forms.CharField(label='日程标题', max_length=200, required=False)
    event_type = forms.ChoiceField(label='类型', choices=(), required=False)
    starts_at = forms.DateTimeField(label='开始时间', required=False, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    ends_at = forms.DateTimeField(label='结束时间', required=False, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    location = forms.CharField(label='地点', max_length=300, required=False)
    meeting_url = forms.URLField(label='会议链接', max_length=1000, required=False)
    job_index = forms.ChoiceField(label='关联本次新增职位', choices=(), required=False)

    def __init__(self, *args, job_choices=(), **kwargs):
        from core.models import CalendarEvent
        super().__init__(*args, **kwargs)
        self.fields['event_type'].choices = CalendarEvent.Type.choices
        self.fields['event_type'].initial = CalendarEvent.Type.OTHER
        self.fields['job_index'].choices = [('', '不关联职位'), *job_choices]

    def clean(self):
        data = super().clean()
        touched = any(value not in (None, '') for key, value in data.items() if key != 'event_type')
        if touched and not data.get('title'):
            self.add_error('title', '填写日程时，标题不能为空。')
        if touched and not data.get('starts_at'):
            self.add_error('starts_at', '填写日程时，开始时间不能为空。')
        if data.get('starts_at') and data.get('ends_at') and data['ends_at'] <= data['starts_at']:
            self.add_error('ends_at', '结束时间必须晚于开始时间。')
        return data


class CompoundTodoForm(BootstrapFormMixin, forms.Form):
    title = forms.CharField(label='任务标题', max_length=200, required=False)
    priority = forms.ChoiceField(label='优先级', choices=(), required=False)
    due_at = forms.DateTimeField(label='截止时间', required=False, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    notes = forms.CharField(label='说明', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    job_index = forms.ChoiceField(label='关联本次新增职位', choices=(), required=False)

    def __init__(self, *args, job_choices=(), **kwargs):
        from core.models import TodoItem
        super().__init__(*args, **kwargs)
        self.fields['priority'].choices = TodoItem.Priority.choices
        self.fields['priority'].initial = TodoItem.Priority.MEDIUM
        self.fields['job_index'].choices = [('', '不关联职位'), *job_choices]

    def clean(self):
        data = super().clean()
        touched = any(value not in (None, '') for key, value in data.items() if key != 'priority')
        if touched and not data.get('title'):
            self.add_error('title', '填写 To Do 时，任务标题不能为空。')
        return data


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
