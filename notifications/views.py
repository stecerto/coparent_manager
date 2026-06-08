# notifications/views.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .models import Notification

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Notification

@login_required
def api_unread_count(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({"count": count})

@login_required
def api_list(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
    data = [{
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "target_url": n.target_url,
        "created_at": n.created_at.strftime("%H:%M")
    } for n in notifs]
    return JsonResponse({"notifications": data})

@login_required
@require_POST
def api_mark_read(request, pk):
    try:
        notif = Notification.objects.get(id=pk, user=request.user)
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        return JsonResponse({"success": True})
    except Notification.DoesNotExist:
        return JsonResponse({"success": False}, status=404)

@login_required
def notifications_page(request):
    """🌐 Pagina HTML per visualizzare le notifiche"""
    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")[:50]
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
@require_POST
def delete_all_notifications(request):
    """Elimina tutte le notifiche dell'utente"""
    deleted_count, _ = Notification.objects.filter(user=request.user).delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            "success": True,
            "deleted_count": deleted_count,
            "message": f"Eliminate {deleted_count} notifiche"
        })

    from django.contrib import messages
    messages.success(request, f"✅ Eliminate {deleted_count} notifiche")
    return redirect('notifications:dashboard')

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

