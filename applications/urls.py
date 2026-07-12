from django.urls import path
from . import views

app_name = 'applications'
urlpatterns = [
    path('', views.ApplicationListView.as_view(), name='list'),
    path('board/', views.ApplicationBoardView.as_view(), name='board'),
    path('new/', views.ApplicationCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ApplicationDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.ApplicationUpdateView.as_view(), name='edit'),
    path('<int:pk>/status/', views.ApplicationStatusView.as_view(), name='status'),
    path('<int:pk>/archive/', views.ApplicationArchiveView.as_view(), name='archive'),
    path('<int:application_pk>/interviews/new/', views.InterviewCreateView.as_view(), name='interview-create'),
    path('interviews/<int:pk>/edit/', views.InterviewUpdateView.as_view(), name='interview-edit'),
]
