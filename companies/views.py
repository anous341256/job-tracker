from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.forms import formset_factory
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from core.models import CalendarEvent, TodoItem
from core.services import create_scheduled_action
from .forms import CompanyForm, CompoundJobForm, CompoundScheduleForm, CompoundTodoForm, JobPositionForm
from .models import Company, JobPosition
from applications.services import (
    ENDED_OUTCOMES,
    PIPELINE_STAGES,
    change_job_pipeline,
    latest_application_for_job,
    pipeline_stage,
)


class OwnedQuerysetMixin(LoginRequiredMixin):
    owner_path = 'user'

    def get_queryset(self):
        return super().get_queryset().filter(**{self.owner_path: self.request.user})


class CompanyListView(OwnedQuerysetMixin, ListView):
    model = Company
    paginate_by = 20
    template_name = 'companies/company_list.html'

    def get_queryset(self):
        qs = super().get_queryset().annotate(job_count=Count('job_positions')).order_by('-updated_at', 'name')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(industry__icontains=q) | Q(location__icontains=q))
        for key in ('status', 'priority', 'industry'):
            if value := self.request.GET.get(key):
                qs = qs.filter(**{key: value})
        return qs
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'statuses': Company.Status.choices, 'priorities': Company.Priority.choices, 'industries': Company.objects.filter(user=self.request.user).exclude(industry='').values_list('industry', flat=True).distinct().order_by('industry')}


class CompanyDetailView(OwnedQuerysetMixin, DetailView):
    model = Company
    template_name = 'companies/company_detail.html'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('job_positions', 'calendar_events', 'todo_items')


class CompanyCreateView(LoginRequiredMixin, View):
    template_name = 'companies/company_compound_form.html'
    JobFormSet = formset_factory(CompoundJobForm, extra=1, can_delete=True)
    ScheduleFormSet = formset_factory(CompoundScheduleForm, extra=1, can_delete=True)
    TodoFormSet = formset_factory(CompoundTodoForm, extra=1, can_delete=True)

    def _job_choices(self, request):
        if request.method != 'POST':
            return []
        try:
            total = min(int(request.POST.get('jobs-TOTAL_FORMS', 0)), 25)
        except (TypeError, ValueError):
            total = 0
        return [
            (str(index), request.POST.get(f'jobs-{index}-title', '').strip() or f'职位 {index + 1}')
            for index in range(total)
            if request.POST.get(f'jobs-{index}-title', '').strip()
        ]

    def _forms(self, request):
        data = request.POST or None
        job_choices = self._job_choices(request)
        return (
            CompanyForm(data),
            self.JobFormSet(data, prefix='jobs'),
            self.ScheduleFormSet(data, prefix='schedules', form_kwargs={'job_choices': job_choices}),
            self.TodoFormSet(data, prefix='todos', form_kwargs={'job_choices': job_choices}),
        )

    def get(self, request):
        return render(request, self.template_name, self._context(*self._forms(request)))

    def post(self, request):
        company_form, job_forms, schedule_forms, todo_forms = self._forms(request)
        valid = all((company_form.is_valid(), job_forms.is_valid(), schedule_forms.is_valid(), todo_forms.is_valid()))
        if not valid:
            return render(request, self.template_name, self._context(company_form, job_forms, schedule_forms, todo_forms))
        with transaction.atomic():
            company = company_form.save(commit=False)
            company.user = request.user
            company.status = company.status or Company.Status.RESEARCHING
            company.priority = company.priority or Company.Priority.MEDIUM
            company.save()
            created_jobs = {}
            for index, form in enumerate(job_forms.forms):
                if form.cleaned_data.get('DELETE') or not form.cleaned_data.get('title'):
                    continue
                data = form.cleaned_data
                created_jobs[str(index)] = JobPosition.objects.create(
                    company=company,
                    title=data['title'],
                    category=data.get('category') or JobPosition.Category.TECHNICAL,
                    source_url=data.get('source_url') or '',
                    location=data.get('location') or '',
                    application_deadline=data.get('application_deadline'),
                    description=data.get('description') or '',
                )
            for form in schedule_forms.forms:
                if form.cleaned_data.get('DELETE') or not form.cleaned_data.get('title'):
                    continue
                data = form.cleaned_data
                create_scheduled_action(
                    user=request.user,
                    company=company,
                    job_position=created_jobs.get(data.get('job_index')),
                    title=data['title'],
                    event_type=data.get('event_type') or CalendarEvent.Type.OTHER,
                    starts_at=data['starts_at'],
                    ends_at=data.get('ends_at'),
                    location=data.get('location') or '',
                    meeting_url=data.get('meeting_url') or '',
                )
            for form in todo_forms.forms:
                if form.cleaned_data.get('DELETE') or not form.cleaned_data.get('title'):
                    continue
                data = form.cleaned_data
                TodoItem.objects.create(
                    user=request.user,
                    company=company,
                    job_position=created_jobs.get(data.get('job_index')),
                    title=data['title'],
                    priority=data.get('priority') or TodoItem.Priority.MEDIUM,
                    due_at=data.get('due_at'),
                    notes=data.get('notes') or '',
                )
        messages.success(request, f'已创建 {company.name}，相关职位、日程和 To Do 已一并保存。')
        return redirect(f'/dashboard/#company-{company.pk}')

    def _context(self, company_form, job_forms, schedule_forms, todo_forms):
        return {
            'company_form': company_form,
            'job_forms': job_forms,
            'schedule_forms': schedule_forms,
            'todo_forms': todo_forms,
        }


class CompanyUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Company
    form_class = CompanyForm
    template_name = 'generic/form.html'
    success_url = reverse_lazy('companies:list')


class CompanyArchiveView(OwnedQuerysetMixin, View):
    model = Company

    def post(self, request, pk):
        company = Company.objects.filter(pk=pk, user=request.user).first()
        if not company:
            raise Http404
        company.archived_at = None if company.archived_at else timezone.now()
        company.status = Company.Status.ARCHIVED if company.archived_at else Company.Status.RESEARCHING
        if company.archived_at:
            company.pinned_order = None
        company.save(update_fields=('archived_at', 'status', 'pinned_order', 'updated_at'))
        messages.success(request, '公司归档状态已更新。')
        return redirect('companies:detail', pk=pk)


class JobListView(LoginRequiredMixin, ListView):
    model = JobPosition
    paginate_by = 20
    template_name = 'companies/job_list.html'

    def get_queryset(self):
        qs = JobPosition.objects.filter(company__user=self.request.user).select_related('company')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(company__name__icontains=q) | Q(location__icontains=q))
        for key in ('company', 'status', 'work_mode'):
            if value := self.request.GET.get(key):
                qs = qs.filter(**{f'{key}_id' if key == 'company' else key: value})
        deadline = self.request.GET.get('deadline')
        today = timezone.localdate()
        if deadline == 'upcoming': qs = qs.filter(application_deadline__gte=today)
        elif deadline == 'overdue': qs = qs.filter(application_deadline__lt=today)
        elif deadline == 'none': qs = qs.filter(application_deadline__isnull=True)
        return qs
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'companies': Company.objects.filter(user=self.request.user, archived_at__isnull=True).order_by('name'), 'statuses': JobPosition.Status.choices, 'work_modes': JobPosition.WorkMode.choices}


class CompanyDeleteView(LoginRequiredMixin, View):
    def dispatch(self, request, pk, *args, **kwargs):
        self.object = Company.objects.filter(pk=pk, user=request.user).first()
        if not self.object: raise Http404
        return super().dispatch(request, pk, *args, **kwargs)
    def get(self, request, pk): return render(request, 'generic/confirm_delete.html', {'object': self.object, 'cancel_url': reverse_lazy('companies:detail', kwargs={'pk': pk}), 'archive_url': reverse_lazy('companies:archive', kwargs={'pk': pk}), 'kind': '公司'})
    def post(self, request, pk):
        has_related = (
            self.object.job_positions.exists() or self.object.contacts.exists()
            or self.object.synced_emails.exists() or self.object.communications.exists()
            or self.object.documents.exists() or self.object.calendar_events.exists()
            or self.object.todo_items.exists()
        )
        if has_related:
            messages.error(request, '该公司已有职位、联系人、邮件或其他业务数据，不能删除，请改用归档。')
            return redirect('companies:detail', pk=pk)
        self.object.delete(); messages.success(request, '公司已删除。'); return redirect('companies:list')


class JobDeleteView(LoginRequiredMixin, View):
    def dispatch(self, request, pk, *args, **kwargs):
        self.object = JobPosition.objects.filter(pk=pk, company__user=request.user).first()
        if not self.object: raise Http404
        return super().dispatch(request, pk, *args, **kwargs)
    def get(self, request, pk): return render(request, 'generic/confirm_delete.html', {'object': self.object, 'cancel_url': reverse_lazy('companies:job-detail', kwargs={'pk': pk}), 'kind': '职位'})
    def post(self, request, pk):
        has_related = (
            self.object.applications.exists()
            or self.object.todo_items.exists()
            or self.object.calendar_events.exists()
            or self.object.ai_tasks.exists()
            or self.object.ai_match_analyses.exists()
        )
        if has_related:
            messages.error(request, '该职位已有投递、日程、To Do 或 AI 分析记录，不能删除；请将职位状态改为已关闭。')
            return redirect('companies:job-detail', pk=pk)
        self.object.delete(); messages.success(request, '职位已删除。'); return redirect('companies:job-list')


class JobDetailView(LoginRequiredMixin, DetailView):
    model = JobPosition
    template_name = 'companies/job_detail.html'
    def get_queryset(self):
        return JobPosition.objects.filter(company__user=self.request.user).select_related('company')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        application = latest_application_for_job(self.object)
        self.object.pipeline_application = application
        self.object.pipeline_stage = pipeline_stage(application)
        self.object.pipeline_stage_label = dict(PIPELINE_STAGES)[self.object.pipeline_stage]
        self.object.pipeline_outcome_label = application.get_status_display() if application and self.object.pipeline_stage == 'ended' else ''
        context.update({'pipeline_stages': PIPELINE_STAGES, 'ended_outcomes': ENDED_OUTCOMES})
        return context


class JobCreateView(LoginRequiredMixin, CreateView):
    form_class = JobPositionForm
    template_name = 'generic/form.html'
    success_url = reverse_lazy('companies:job-list')
    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'user': self.request.user}

    def get_initial(self):
        initial = super().get_initial()
        company_id = self.request.GET.get('company')
        if company_id and Company.objects.filter(pk=company_id, user=self.request.user).exists():
            initial['company'] = company_id
        return initial

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'form_title': '添加职位', 'form_intro': '先填写公司、职位名称和职位类别，其余信息可以稍后补充。'}


class JobUpdateView(JobCreateView, UpdateView):
    model = JobPosition
    def get_queryset(self):
        return JobPosition.objects.filter(company__user=self.request.user)
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'form_title': '编辑职位'}


class JobPipelineStatusView(LoginRequiredMixin, View):
    def post(self, request, pk):
        job = JobPosition.objects.filter(pk=pk, company__user=request.user).select_related('company').first()
        if not job:
            raise Http404
        try:
            application = change_job_pipeline(
                job=job,
                user=request.user,
                stage=request.POST.get('stage', ''),
                outcome=request.POST.get('outcome', ''),
                note=request.POST.get('note', '').strip(),
                backward_confirmed=request.POST.get('backward_confirmed') == 'yes',
            )
        except Exception as exc:
            if request.headers.get('HX-Request'):
                return render(request, 'generic/error_fragment.html', {'error': exc}, status=400)
            messages.error(request, str(exc))
            return redirect('core:dashboard')
        job.pipeline_application = application
        job.pipeline_stage = pipeline_stage(application)
        job.pipeline_stage_label = dict(PIPELINE_STAGES)[job.pipeline_stage]
        job.pipeline_outcome_label = application.get_status_display() if application and job.pipeline_stage == 'ended' else ''
        if request.headers.get('HX-Request'):
            return render(request, 'core/_job_pipeline_row.html', {
                'job': job,
                'pipeline_stages': PIPELINE_STAGES,
                'ended_outcomes': ENDED_OUTCOMES,
            })
        return redirect('core:dashboard')


class CompanyPinView(LoginRequiredMixin, View):
    def post(self, request, pk):
        company = Company.objects.filter(pk=pk, user=request.user, archived_at__isnull=True).first()
        if not company:
            raise Http404
        if company.pinned_order is None:
            maximum = Company.objects.filter(
                user=request.user, archived_at__isnull=True, pinned_order__isnull=False,
            ).order_by('-pinned_order').values_list('pinned_order', flat=True).first()
            company.pinned_order = (maximum or 0) + 1
        else:
            company.pinned_order = None
        company.save(update_fields=('pinned_order', 'updated_at'))
        return redirect('core:dashboard')


class CompanyReorderPinnedView(LoginRequiredMixin, View):
    def post(self, request):
        raw_ids = request.POST.getlist('company_ids')
        try:
            ids = [int(value) for value in raw_ids]
        except (TypeError, ValueError):
            return JsonResponse({'error': '排序数据无效。'}, status=400)
        owned_ids = set(Company.objects.filter(
            user=request.user, archived_at__isnull=True, pinned_order__isnull=False, pk__in=ids,
        ).values_list('pk', flat=True))
        if len(ids) != len(set(ids)) or owned_ids != set(ids):
            return JsonResponse({'error': '只能调整自己的置顶公司。'}, status=400)
        with transaction.atomic():
            for order, company_id in enumerate(ids, start=1):
                Company.objects.filter(pk=company_id, user=request.user).update(pinned_order=order)
        return HttpResponse(status=204)
