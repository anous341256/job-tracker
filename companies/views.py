from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from .forms import CompanyForm, JobPositionForm
from .models import Company, JobPosition


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


class CompanyCreateView(LoginRequiredMixin, CreateView):
    form_class = CompanyForm
    template_name = 'generic/form.html'
    success_url = reverse_lazy('companies:list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


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
        company.save(update_fields=('archived_at', 'status', 'updated_at'))
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
        has_related = self.object.job_positions.exists() or self.object.contacts.exists() or self.object.synced_emails.exists() or self.object.communications.exists() or self.object.documents.exists()
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
        if self.object.applications.exists():
            messages.error(request, '该职位已有投递记录，不能删除；请将职位状态改为已关闭。')
            return redirect('companies:job-detail', pk=pk)
        self.object.delete(); messages.success(request, '职位已删除。'); return redirect('companies:job-list')


class JobDetailView(LoginRequiredMixin, DetailView):
    model = JobPosition
    template_name = 'companies/job_detail.html'
    def get_queryset(self):
        return JobPosition.objects.filter(company__user=self.request.user).select_related('company')


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
