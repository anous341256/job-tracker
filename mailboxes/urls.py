from django.urls import path
from . import views

app_name = 'mailboxes'
urlpatterns = [
    path('accounts/', views.accounts, name='accounts'), path('connect/<str:provider>/', views.connect, name='connect'), path('callback/<str:provider>/', views.callback, name='callback'),
    path('accounts/<int:pk>/disconnect/', views.disconnect, name='disconnect'), path('accounts/<int:pk>/sync/', views.sync, name='sync'),
    path('messages/', views.messages_list, name='messages'), path('messages/<int:pk>/link/', views.link_message, name='link-message'), path('compose/', views.compose, name='compose'),
]
