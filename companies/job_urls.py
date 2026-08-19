from django.urls import path
from . import views

app_name = 'jobs'
urlpatterns = [
    path('', views.JobListView.as_view(), name='list'),
    path('new/', views.JobCreateView.as_view(), name='create'),
    path('<int:pk>/', views.JobDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.JobUpdateView.as_view(), name='edit'),
    path('<int:pk>/pipeline-status/', views.JobPipelineStatusView.as_view(), name='pipeline-status'),
]
