from django.urls import path
from . import views

app_name = 'companies'
urlpatterns = [
    path('', views.CompanyListView.as_view(), name='list'),
    path('new/', views.CompanyCreateView.as_view(), name='create'),
    path('<int:pk>/', views.CompanyDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.CompanyUpdateView.as_view(), name='edit'),
    path('<int:pk>/archive/', views.CompanyArchiveView.as_view(), name='archive'),
    path('<int:pk>/delete/', views.CompanyDeleteView.as_view(), name='delete'),
    path('<int:pk>/pin/', views.CompanyPinView.as_view(), name='pin'),
    path('reorder-pinned/', views.CompanyReorderPinnedView.as_view(), name='reorder-pinned'),
    path('jobs/', views.JobListView.as_view(), name='job-list'),
    path('jobs/new/', views.JobCreateView.as_view(), name='job-create'),
    path('jobs/<int:pk>/', views.JobDetailView.as_view(), name='job-detail'),
    path('jobs/<int:pk>/edit/', views.JobUpdateView.as_view(), name='job-edit'),
    path('jobs/<int:pk>/delete/', views.JobDeleteView.as_view(), name='job-delete'),
    path('jobs/<int:pk>/pipeline-status/', views.JobPipelineStatusView.as_view(), name='job-pipeline-status'),
]
