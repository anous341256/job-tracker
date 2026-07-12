from django.urls import path
from . import views

app_name = 'productivity'
urlpatterns = [
    path('contacts/', views.ContactList.as_view(), name='contacts'), path('contacts/new/', views.ContactCreate.as_view(), name='contact-create'), path('contacts/<int:pk>/', views.ContactDetail.as_view(), name='contact-detail'), path('contacts/<int:pk>/edit/', views.ContactUpdate.as_view(), name='contact-edit'),
    path('resumes/', views.ResumeList.as_view(), name='resumes'), path('resumes/new/', views.ResumeCreate.as_view(), name='resume-create'), path('resumes/<int:pk>/', views.ResumeDetail.as_view(), name='resume-detail'), path('resumes/<int:pk>/edit/', views.ResumeUpdate.as_view(), name='resume-edit'), path('resumes/<int:pk>/file/', views.resume_download, name='resume-download'),
    path('documents/', views.DocumentList.as_view(), name='documents'), path('documents/new/', views.DocumentCreate.as_view(), name='document-create'), path('documents/<int:pk>/', views.DocumentDetail.as_view(), name='document-detail'), path('documents/<int:pk>/edit/', views.DocumentUpdate.as_view(), name='document-edit'), path('documents/<int:pk>/download/', views.document_download, name='document-download'),
    path('communications/', views.CommunicationList.as_view(), name='communications'), path('communications/new/', views.CommunicationCreate.as_view(), name='communication-create'), path('communications/<int:pk>/', views.CommunicationDetail.as_view(), name='communication-detail'), path('communications/<int:pk>/edit/', views.CommunicationUpdate.as_view(), name='communication-edit'),
    path('tags/', views.TagList.as_view(), name='tags'), path('tags/new/', views.TagCreate.as_view(), name='tag-create'), path('tags/<int:pk>/', views.TagDetail.as_view(), name='tag-detail'), path('tags/<int:pk>/edit/', views.TagUpdate.as_view(), name='tag-edit'),
]
