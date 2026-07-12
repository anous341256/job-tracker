from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
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
        return qs


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
    def get_queryset(self): return Interview.objects.filter(application__user=self.request.user).select_related('application__job_position__company')


class InterviewCreateView(LoginRequiredMixin, CreateView):
    form_class = InterviewForm
    template_name = 'generic/form.html'
    def dispatch(self, request, *args, **kwargs):
        self.application = Application.objects.filter(pk=kwargs['application_pk'], user=request.user).first()
        if not self.application: raise Http404
        return super().dispatch(request, *args, **kwargs)
    def form_valid(self, form): form.instance.application = self.application; return super().form_valid(form)
    def get_success_url(self): return reverse_lazy('applications:detail', kwargs={'pk': self.application.pk})


class InterviewUpdateView(LoginRequiredMixin, UpdateView):
    model = Interview
    form_class = InterviewForm
    template_name = 'generic/form.html'
    def get_queryset(self): return Interview.objects.filter(application__user=self.request.user)
    def get_success_url(self): return reverse_lazy('applications:detail', kwargs={'pk': self.object.application_id})
