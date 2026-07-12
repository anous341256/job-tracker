from django.urls import path
from . import views

app_name = 'ai_assistant'
urlpatterns = [
    path('settings/', views.ai_settings, name='settings'),
    path('settings/delete-key/', views.delete_openai_key, name='delete-key'),
    path('tasks/<uuid:pk>/', views.task_detail, name='task-detail'),
    path('tasks/<uuid:pk>/apply/', views.apply_jd_result, name='task-apply'),
    path('tasks/<uuid:pk>/delete/', views.delete_task, name='task-delete'),
]
