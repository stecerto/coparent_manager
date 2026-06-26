from django.urls import path
from . import views
app_name = "chat"
urlpatterns = [
    path("", views.family_chat_view, name="chat_home"),
    path("message/<int:pk>/delete/", views.delete_message_view, name="delete_message"),
    path("history/<int:pk>/", views.message_history_view, name="message_history"),
    path("api/send-rejection/", views.send_rejection_message, name="send_rejection_message"),
    path("export-pdf/", views.chat_export_pdf, name="chat_export_pdf"),
    path("history-view/", views.chat_history_view, name="chat_history"),
    # ✅ Chat per avvocati con selezione famiglia
    path('lawyer/family/<int:family_id>/', views.family_chat_view, name='chat_family'),

    # ✅ Chat privata avvocato-assistito
    path('lawyer/family/<int:family_id>/private/<int:user_id>/', views.family_chat_view, name='chat_private'),
    path('professional/', views.professional_chat_view, name='professional_chat'),
    path('professional/attachment/<int:attachment_id>/preview/', views.preview_professional_attachment,
    name='preview_professional_attachment'
),
    path('professional/attachment/<int:attachment_id>/download/', views.download_professional_attachment,
    name='download_professional_attachment'),
]