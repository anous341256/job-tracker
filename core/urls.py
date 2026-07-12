from django.urls import path
from . import views

app_name = 'core'
urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('calendar/events/', views.calendar_events, name='calendar-events'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/read/', views.notification_read, name='notification-read'),
]
