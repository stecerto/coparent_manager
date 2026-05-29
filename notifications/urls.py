from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # 🌐 Pagina HTML completa
    path('dashboard/', views.notifications_page, name='dashboard'),

    # 📡 API per polling badge e frontend
    path('api/unread-count/', views.get_unread_count, name='unread_count'),
    path('api/list/', views.list_notifications, name='api_list'),

    # ✅ Azioni
    path('api/mark-read/<int:notification_id>/', views.mark_as_read, name='mark_as_read'),
    path('api/mark-read-all/', views.mark_as_read_all, name='mark_as_read_all'),
]