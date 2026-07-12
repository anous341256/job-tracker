from django.urls import path
from . import views

app_name = 'productivity'
urlpatterns = [
    path('contacts/', views.ContactList.as_view(), name='contacts'), path('contacts/new/', views.ContactCreate.as_view(), name='contact-create'),
    path('resumes/', views.ResumeList.as_view(), name='resumes'), path('resumes/new/', views.ResumeCreate.as_view(), name='resume-create'),
    path('documents/', views.DocumentList.as_view(), name='documents'), path('documents/new/', views.DocumentCreate.as_view(), name='document-create'), path('documents/<int:pk>/download/', views.document_download, name='document-download'),
    path('communications/', views.CommunicationList.as_view(), name='communications'), path('communications/new/', views.CommunicationCreate.as_view(), name='communication-create'),
    path('tags/', views.TagList.as_view(), name='tags'), path('tags/new/', views.TagCreate.as_view(), name='tag-create'),
]
