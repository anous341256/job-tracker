from django.urls import path
from . import views

app_name = 'core'
urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('calendar/events/', views.calendar_events, name='calendar-events'),
    path('calendar/free-slots/', views.calendar_free_slots, name='calendar-free-slots'),
    path('todos/', views.todos, name='todos'),
    path('calendar/events/new/', views.calendar_event_create, name='calendar-event-create'),
    path('calendar/events/<int:pk>/edit/', views.calendar_event_edit, name='calendar-event-edit'),
    path('todos/new/', views.todo_create, name='todo-create'),
    path('todos/<int:pk>/edit/', views.todo_edit, name='todo-edit'),
    path('todos/<int:pk>/toggle/', views.todo_toggle, name='todo-toggle'),
    path('todos/<int:pk>/delete/', views.todo_delete, name='todo-delete'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/read/', views.notification_read, name='notification-read'),
    path('notifications/read-all/', views.notifications_read_all, name='notifications-read-all'),
]
