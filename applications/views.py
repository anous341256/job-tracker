from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View
from django.utils import timezone

from .forms import ApplicationForm, InterviewForm
from .models import Application, Interview
from .services import change_status, create_application


class ApplicationListView(LoginRequiredMixin, ListView):
    model = Application
    paginate_by = 20
    template_name = 'applications/application_list.html'
    def get_queryset(self):
        qs = Application.objects.filter(user=self.request.user).select_related('job_position__company')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(job_position__title__icontains=q) | Q(job_position__company__name__icontains=q))
        for key in ('status', 'source', 'priority'):
            if value := self.request.GET.get(key): qs = qs.filter(**{key: value})
        if company := self.request.GET.get('company'): qs = qs.filter(job_position__company_id=company)
        if date_from := self.request.GET.get('date_from'): qs = qs.filter(applied_at__gte=date_from)
        if date_to := self.request.GET.get('date_to'): qs = qs.filter(applied_at__lte=date_to)
        return qs
    def get_context_data(self, **kwargs):
        from companies.models import Company
        return {**super().get_context_data(**kwargs), 'statuses': Application.Status.choices, 'sources': Application.Source.choices, 'priorities': Company.Priority.choices, 'companies': Company.objects.filter(user=self.request.user, archived_at__isnull=True).order_by('name')}


class ApplicationBoardView(ApplicationListView):
    template_name = 'applications/board.html'
    paginate_by = None
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        apps = list(context['object_list'])
        context['columns'] = [(value, label, [a for a in apps if a.status == value]) for value, label in Application.Status.choices]
        return context


class ApplicationDetailView(LoginRequiredMixin, DetailView):
    model = Application
    template_name = 'applications/application_detail.html'
    def get_queryset(self):
        return Application.objects.filter(user=self.request.user).select_related('job_position__company', 'resume').prefetch_related('status_logs', 'interviews')


class ApplicationCreateView(LoginRequiredMixin, CreateView):
    form_class = ApplicationForm
    template_name = 'generic/form.html'
    def get_form_kwargs(self): return {**super().get_form_kwargs(), 'user': self.request.user}
    def get_initial(self):
        initial = super().get_initial()
        job_id = self.request.GET.get('job')
        if job_id and self.request.user.companies.filter(job_positions__pk=job_id).exists():
            initial['job_position'] = job_id
        return initial
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'form_title': '新建投递', 'form_intro': '记录投递日期、来源和下一步行动，状态变化会单独保留历史。'}
    def form_valid(self, form):
        try: self.object = create_application(user=self.request.user, form=form)
        except ValidationError as exc:
            form.add_error(None, exc)
            return self.form_invalid(form)
        return redirect('applications:detail', pk=self.object.pk)


class ApplicationUpdateView(LoginRequiredMixin, UpdateView):
    model = Application
    form_class = ApplicationForm
    template_name = 'generic/form.html'
    def get_queryset(self): return Application.objects.filter(user=self.request.user)
    def get_form_kwargs(self): return {**super().get_form_kwargs(), 'user': self.request.user}
    def get_success_url(self): return reverse_lazy('applications:detail', kwargs={'pk': self.object.pk})


class ApplicationStatusView(LoginRequiredMixin, View):
    def post(self, request, pk):
        application = Application.objects.filter(pk=pk, user=request.user).first()
        if not application: raise Http404
        try: change_status(application=application, status=request.POST.get('status', ''), user=request.user, note=request.POST.get('note', ''))
        except ValidationError as exc: return render(request, 'generic/error_fragment.html', {'error': exc}, status=400)
        if request.headers.get('HX-Request'): return render(request, 'applications/_card.html', {'application': Application.objects.get(pk=pk)})
        return redirect('applications:detail', pk=pk)


class ApplicationArchiveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        application = Application.objects.filter(pk=pk, user=request.user).first()
        if not application: raise Http404
        application.archived_at = None if application.archived_at else timezone.now()
        application.save(update_fields=('archived_at', 'updated_at'))
        return redirect('applications:detail', pk=pk)


class InterviewListView(LoginRequiredMixin, ListView):
    model = Interview
    template_name = 'applications/interview_list.html'
    paginate_by = 20
    def get_queryset(self):
        qs = Interview.objects.filter(application__user=self.request.user).select_related('application__job_position__company')
        if status := self.request.GET.get('status'): qs = qs.filter(status=status)
        return qs
    def get_context_data(self, **kwargs): return {**super().get_context_data(**kwargs), 'statuses': Interview.Status.choices}


class ApplicationDeleteView(LoginRequiredMixin, View):
    def dispatch(self, request, pk, *args, **kwargs):
        self.object = Application.objects.filter(pk=pk, user=request.user).first()
        if not self.object: raise Http404
        return super().dispatch(request, pk, *args, **kwargs)
    def get(self, request, pk): return render(request, 'generic/confirm_delete.html', {'object': self.object, 'cancel_url': reverse_lazy('applications:detail', kwargs={'pk': pk}), 'archive_url': reverse_lazy('applications:archive', kwargs={'pk': pk}), 'kind': '投递'})
    def post(self, request, pk):
        if self.object.status_logs.exists() or self.object.interviews.exists() or self.object.synced_emails.exists() or self.object.communications.exists() or self.object.documents.exists():
            messages.error(request, '该投递已有状态历史、面试、邮件或附件，不能删除，请改用归档。')
            return redirect('applications:detail', pk=pk)
        self.object.delete(); messages.success(request, '投递已删除。'); return redirect('applications:list')


class InterviewCreateView(LoginRequiredMixin, CreateView):
    form_class = InterviewForm
    template_name = 'generic/form.html'
    def dispatch(self, request, *args, **kwargs):
        self.application = Application.objects.filter(pk=kwargs['application_pk'], user=request.user).first()
        if not self.application: raise Http404
        return super().dispatch(request, *args, **kwargs)
    def form_valid(self, form): form.instance.application = self.application; return super().form_valid(form)
    def get_success_url(self): return reverse_lazy('applications:detail', kwargs={'pk': self.application.pk})
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'form_title': '添加面试', 'form_intro': f'{self.application.job_position.company} · {self.application.job_position.title}'}


class InterviewUpdateView(LoginRequiredMixin, UpdateView):
    model = Interview
    form_class = InterviewForm
    template_name = 'generic/form.html'
    def get_queryset(self): return Interview.objects.filter(application__user=self.request.user)
    def get_success_url(self): return reverse_lazy('applications:detail', kwargs={'pk': self.object.application_id})
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'form_title': '修改面试', 'form_intro': '可以修改时间、面试状态、结果和复盘记录。'}


class InterviewStatusView(LoginRequiredMixin, View):
    def post(self, request, pk):
        interview = Interview.objects.filter(pk=pk, application__user=request.user).first()
        if not interview:
            raise Http404
        status = request.POST.get('status')
        result = request.POST.get('result')
        changed_fields = []
        if status in Interview.Status.values and status != interview.status:
            interview.status = status
            changed_fields.append('status')
        if result in Interview.Result.values and result != interview.result:
            interview.result = result
            changed_fields.append('result')
        if changed_fields:
            changed_fields.append('updated_at')
            interview.save(update_fields=changed_fields)
        return redirect(request.POST.get('next') or 'interviews')
