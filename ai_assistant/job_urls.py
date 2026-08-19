from django.urls import path
from . import views

app_name = 'ai_jobs'
urlpatterns = [
    path('<int:pk>/ai/parse/', views.jd_parse, name='parse'),
    path('<int:pk>/ai/match/', views.job_match, name='match'),
]
