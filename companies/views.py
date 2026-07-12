from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect
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
        return qs


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


class JobUpdateView(JobCreateView, UpdateView):
    model = JobPosition
    def get_queryset(self):
        return JobPosition.objects.filter(company__user=self.request.user)
