from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CommunicationForm, ContactForm, DocumentForm, ResumeForm, TagForm
from .models import Communication, Contact, Document, Resume, Tag


class OwnedListView(LoginRequiredMixin, ListView):
    paginate_by = 20
    template_name = 'productivity/list.html'
    page_title = '资料'
    create_url_name = None
    def get_queryset(self): return self.model.objects.filter(user=self.request.user).order_by('-pk')
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'page_title': self.page_title, 'create_url_name': self.create_url_name, 'model_name': self.model._meta.model_name}


class OwnedCreateView(LoginRequiredMixin, CreateView):
    template_name = 'generic/form.html'
    success_url = reverse_lazy('core:dashboard')
    def get_form_kwargs(self): return {**super().get_form_kwargs(), 'user': self.request.user}
    def form_valid(self, form): form.instance.user = self.request.user; return super().form_valid(form)


class OwnedDetailView(LoginRequiredMixin, DetailView):
    template_name = 'productivity/detail.html'
    edit_url_name = None
    def get_queryset(self): return self.model.objects.filter(user=self.request.user)
    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'model_name': self.model._meta.model_name, 'edit_url_name': self.edit_url_name}


class OwnedUpdateView(LoginRequiredMixin, UpdateView):
    template_name = 'generic/form.html'
    detail_url_name = None
    form_title = '编辑资料'
    def get_queryset(self): return self.model.objects.filter(user=self.request.user)
    def get_form_kwargs(self): return {**super().get_form_kwargs(), 'user': self.request.user}
    def get_success_url(self): return reverse(self.detail_url_name, args=[self.object.pk])
    def get_context_data(self, **kwargs): return {**super().get_context_data(**kwargs), 'form_title': self.form_title}


class ContactList(OwnedListView): model = Contact; page_title = '联系人'; create_url_name = 'productivity:contact-create'
class ContactCreate(OwnedCreateView): form_class = ContactForm; success_url = reverse_lazy('productivity:contacts')
class ContactDetail(OwnedDetailView): model = Contact; edit_url_name = 'productivity:contact-edit'
class ContactUpdate(OwnedUpdateView): model = Contact; form_class = ContactForm; detail_url_name = 'productivity:contact-detail'; form_title = '编辑联系人'
class ResumeList(OwnedListView): model = Resume; page_title = '简历'; create_url_name = 'productivity:resume-create'
class ResumeCreate(OwnedCreateView): form_class = ResumeForm; success_url = reverse_lazy('productivity:resumes')
class ResumeDetail(OwnedDetailView): model = Resume; edit_url_name = 'productivity:resume-edit'
class ResumeUpdate(OwnedUpdateView): model = Resume; form_class = ResumeForm; detail_url_name = 'productivity:resume-detail'; form_title = '编辑简历'
class DocumentList(OwnedListView): model = Document; page_title = '附件'; create_url_name = 'productivity:document-create'
class DocumentCreate(OwnedCreateView): form_class = DocumentForm; success_url = reverse_lazy('productivity:documents')
class DocumentDetail(OwnedDetailView): model = Document; edit_url_name = 'productivity:document-edit'
class DocumentUpdate(OwnedUpdateView): model = Document; form_class = DocumentForm; detail_url_name = 'productivity:document-detail'; form_title = '编辑附件'
class CommunicationList(OwnedListView): model = Communication; page_title = '沟通记录'; create_url_name = 'productivity:communication-create'
class CommunicationCreate(OwnedCreateView): form_class = CommunicationForm; success_url = reverse_lazy('productivity:communications')
class CommunicationDetail(OwnedDetailView): model = Communication; edit_url_name = 'productivity:communication-edit'
class CommunicationUpdate(OwnedUpdateView): model = Communication; form_class = CommunicationForm; detail_url_name = 'productivity:communication-detail'; form_title = '编辑沟通记录'
class TagList(OwnedListView): model = Tag; page_title = '标签'; create_url_name = 'productivity:tag-create'
class TagCreate(OwnedCreateView): form_class = TagForm; success_url = reverse_lazy('productivity:tags')
class TagDetail(OwnedDetailView): model = Tag; edit_url_name = 'productivity:tag-edit'
class TagUpdate(OwnedUpdateView): model = Tag; form_class = TagForm; detail_url_name = 'productivity:tag-detail'; form_title = '编辑标签'


def document_download(request, pk):
    if not request.user.is_authenticated: raise Http404
    document = Document.objects.filter(pk=pk, user=request.user).first()
    if not document: raise Http404
    return FileResponse(document.file.open('rb'), as_attachment=True, filename=document.original_name)


def resume_download(request, pk):
    if not request.user.is_authenticated: raise Http404
    resume = Resume.objects.filter(pk=pk, user=request.user).first()
    if not resume: raise Http404
    return FileResponse(resume.file.open('rb'), as_attachment=False, filename=resume.file.name.rsplit('/', 1)[-1])

# Create your views here.
