from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView

from .forms import CommunicationForm, ContactForm, DocumentForm, ResumeForm, TagForm
from .models import Communication, Contact, Document, Resume, Tag


class OwnedListView(LoginRequiredMixin, ListView):
    paginate_by = 20
    template_name = 'productivity/list.html'
    def get_queryset(self): return self.model.objects.filter(user=self.request.user).order_by('-pk')


class OwnedCreateView(LoginRequiredMixin, CreateView):
    template_name = 'generic/form.html'
    success_url = reverse_lazy('core:dashboard')
    def get_form_kwargs(self): return {**super().get_form_kwargs(), 'user': self.request.user}
    def form_valid(self, form): form.instance.user = self.request.user; return super().form_valid(form)


class ContactList(OwnedListView): model = Contact
class ContactCreate(OwnedCreateView): form_class = ContactForm
class ResumeList(OwnedListView): model = Resume
class ResumeCreate(OwnedCreateView): form_class = ResumeForm
class DocumentList(OwnedListView): model = Document
class DocumentCreate(OwnedCreateView): form_class = DocumentForm
class CommunicationList(OwnedListView): model = Communication
class CommunicationCreate(OwnedCreateView): form_class = CommunicationForm
class TagList(OwnedListView): model = Tag
class TagCreate(OwnedCreateView): form_class = TagForm


def document_download(request, pk):
    if not request.user.is_authenticated: raise Http404
    document = Document.objects.filter(pk=pk, user=request.user).first()
    if not document: raise Http404
    return FileResponse(document.file.open('rb'), as_attachment=True, filename=document.original_name)

# Create your views here.
