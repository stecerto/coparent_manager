# notifications/views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notifications_page(request):
    """🌐 Pagina HTML per visualizzare le notifiche"""
    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")[:50]
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
def get_unread_count(request):
    """📡 API: Conta notifiche non lette (per il badge)"""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({"unread_count": count})


@login_required
@require_POST
def mark_as_read(request, notification_id=None):
    """✅ API: Segna come letta una specifica notifica"""
    Notification.objects.filter(id=notification_id, user=request.user).update(is_read=True)
    return JsonResponse({"success": True})


@login_required
@require_POST
def mark_as_read_all(request):
    """✅ API: Segna TUTTE le notifiche come lette"""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"success": True, "marked_all": True})


@login_required
def list_notifications(request):
    """📋 API: Lista notifiche recenti (per frontend/polling)"""
    limit = int(request.GET.get("limit", 10))
    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")[:limit]

    data = [{
        "id": n.id,
        "type": n.notification_type,
        "title": n.title,
        "message": n.message[:100] + ("..." if len(n.message) > 100 else ""),
        "url": n.target_url or "#",
        "is_read": n.is_read,
        "created_at": n.created_at.strftime("%H:%M %d/%m"),
    } for n in notifications]

    return JsonResponse({"notifications": data})

