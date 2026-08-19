from django.urls import path
from . import assistant_views, views

app_name = 'ai_assistant'
urlpatterns = [
    path('mail-assistant/', assistant_views.mail_assistant, name='mail-assistant'),
    path('mail-assistant/emails/<int:pk>/', assistant_views.mail_assistant_email, name='mail-assistant-email'),
    path('mail-assistant/emails/<int:pk>/chat/', assistant_views.mail_assistant_chat, name='mail-assistant-chat'),
    path('mail-assistant/emails/<int:pk>/company/', assistant_views.mail_assistant_company, name='mail-assistant-company'),
    path('mail-assistant/emails/<int:pk>/complete/', assistant_views.mail_assistant_complete, name='mail-assistant-complete'),
    path('mail-assistant/emails/<int:pk>/reopen/', assistant_views.mail_assistant_reopen, name='mail-assistant-reopen'),
    path('mail-assistant/emails/<int:pk>/clear/', assistant_views.mail_assistant_clear, name='mail-assistant-clear'),
    path('mail-assistant/candidates/<int:pk>/approve/', assistant_views.mail_assistant_candidate_approve, name='mail-assistant-candidate-approve'),
    path('mail-assistant/candidates/<int:pk>/reject/', assistant_views.mail_assistant_candidate_reject, name='mail-assistant-candidate-reject'),
    path('mail-assistant/todos/<int:pk>/approve/', assistant_views.mail_assistant_todo_approve, name='mail-assistant-todo-approve'),
    path('mail-assistant/todos/<int:pk>/reject/', assistant_views.mail_assistant_todo_reject, name='mail-assistant-todo-reject'),
    path('settings/', views.ai_settings, name='settings'),
    path('settings/delete-key/', views.delete_openai_key, name='delete-key'),
    path('tasks/<uuid:pk>/', views.task_detail, name='task-detail'),
    path('tasks/<uuid:pk>/apply/', views.apply_jd_result, name='task-apply'),
    path('tasks/<uuid:pk>/delete/', views.delete_task, name='task-delete'),
    path('email-schedules/', views.email_schedules, name='email-schedules'),
    path('email-schedules/<int:pk>/review/', views.email_schedule_review, name='email-schedule-review'),
    path('email-schedules/<int:pk>/reject/', views.email_schedule_reject, name='email-schedule-reject'),
]
