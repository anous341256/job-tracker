from django.urls import path
from . import views

app_name = 'mailboxes'
urlpatterns = [
    path('connect/local-outlook/', views.connect_local_outlook, name='connect-local-outlook'),
    path('accounts/', views.accounts, name='accounts'), path('connect/<str:provider>/', views.connect, name='connect'), path('callback/<str:provider>/', views.callback, name='callback'),
    path('accounts/<int:pk>/disconnect/', views.disconnect, name='disconnect'), path('accounts/<int:pk>/sync/', views.sync, name='sync'),
    path('accounts/<int:pk>/folder/', views.update_folder, name='update-folder'),
    path('messages/', views.messages_list, name='messages'),
    path('messages/<int:pk>/', views.message_detail, name='message-detail'),
    path('messages/<int:pk>/link/', views.link_message, name='link-message'),
    path('messages/<int:pk>/quick-link/', views.quick_link_company, name='quick-link-company'),
    path('messages/<int:pk>/delete/', views.delete_message, name='message-delete'),
    path('messages/<int:pk>/attachments/<int:index>/import/', views.import_attachment, name='attachment-import'),
    path('messages/bulk-delete/', views.bulk_delete_messages, name='messages-bulk-delete'),
    path('compose/', views.compose, name='compose'),
]
