# calendar_app/views.py
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime as django_parse_datetime
from django.views.decorators.http import require_POST
from django.urls import reverse
from families.utils import get_family_of_user
from .models import CalendarEvent
from .services.calendar_service import create_event, update_event, get_family_events


def _parse_local_dt(dt_str):
    """Helper sicuro per datetime-local con timezone"""
    if not dt_str: return None
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


@login_required
def family_calendar_view(request):
    family = get_family_of_user(request.user, request=request)
    if not family:
        return render(request, "calendar_app/no_family.html")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        event_type = request.POST.get("event_type", "other")

        start_time = _parse_local_dt(request.POST.get("start_time"))
        end_time = _parse_local_dt(request.POST.get("end_time"))

        children = family.children.filter(id__in=request.POST.getlist("children")) if request.POST.getlist(
            "children") else []

        if not title or not start_time or not end_time:
            return render(request, "calendar_app/calendar_view.html", {
                "events": get_family_events(family), "family": family,
                "event_types": CalendarEvent.EVENT_TYPES,
                "error": "Compila titolo, date e categoria."
            })

        event_id = request.POST.get("event_id")
        if event_id:
            event = get_object_or_404(CalendarEvent, pk=event_id, family=family)
            update_event(event, request.user, {
                "title": title, "description": description, "event_type": event_type,
                "start_time": start_time, "end_time": end_time, "children": children,
            })
        else:
            create_event(family=family, title=title, start_time=start_time, end_time=end_time,
                         created_by=request.user, description=description, event_type=event_type, children=children)
        return redirect("calendar:calendar_view")

    return render(request, "calendar_app/calendar_view.html", {
        "events": get_family_events(family), "family": family,
        "event_types": CalendarEvent.EVENT_TYPES,
    })


@login_required
def events_json(request):
    family = get_family_of_user(request.user, request=request)
    if not family: return JsonResponse([], safe=False)

    queryset = CalendarEvent.objects.filter(family=family, is_active=True).select_related(
        "created_by").prefetch_related("children")

    start, end = request.GET.get("start"), request.GET.get("end")
    if start and end:
        s_dt, e_dt = django_parse_datetime(start), django_parse_datetime(end)
        if s_dt and e_dt:
            queryset = queryset.filter(start_time__gte=s_dt, end_time__lte=e_dt)

    data = []
    for ev in queryset:
        kids = [c.name for c in ev.children.all()]
        data.append({
            "id": ev.id, "title": f"{ev.title} {'👶' + ', '.join(kids) if kids else ''}",
            "start": ev.start_time.isoformat(), "end": ev.end_time.isoformat(),
            "event_type": ev.event_type,
            "extendedProps": {"event_type": ev.event_type, "children": kids, "description": ev.description},
            "backgroundColor": _get_event_color(ev.event_type), "borderColor": _get_event_color(ev.event_type),
        })
    return JsonResponse(data, safe=False)


@login_required
@require_POST
def update_event_ajax(request, event_id):
    try:
        ev = get_object_or_404(CalendarEvent, pk=event_id, family=get_family_of_user(request.user, request=request))
        start = _parse_local_dt(request.POST.get("start_time"))
        end = _parse_local_dt(request.POST.get("end_time"))
        if start: ev.start_time = start
        if end: ev.end_time = end
        if request.POST.get("title"): ev.title = request.POST["title"].strip()
        ev.save()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def delete_event_view(request, event_id):
    ev = get_object_or_404(CalendarEvent, pk=event_id, family=get_family_of_user(request.user, request=request))
    ev.is_active = False
    ev.archived_at = timezone.now()
    ev.archived_by = request.user
    ev.save()
    return redirect("calendar:calendar_view")


@login_required
def event_form_view(request, event_id=None):
    family = get_family_of_user(request.user, request=request)
    if not family: return render(request, "calendar_app/no_family.html")

    event = get_object_or_404(CalendarEvent, pk=event_id, family=family) if event_id else None
    is_edit = bool(event)
    # ✅ GENERA BREADCRUMBS COMPATIBILI CON IL TUO BASE.HTML
    breadcrumbs = [
        {"name": "Home", "url": reverse("home")},
        # ⚠️ Adatta se il tuo dashboard ha un nome diverso
        {"name": "Calendario", "url": reverse("calendar:calendar_view")},
        {"name": "Modifica evento" if is_edit else "Crea evento", "url": None}
        # url=None → base.html lo renderà attivo/non cliccabile
    ]
    if request.method == "POST":
        children = family.children.filter(id__in=request.POST.getlist("children")) if request.POST.getlist(
            "children") else []
        data = {
            "title": request.POST.get("title"), "description": request.POST.get("description"),
            "start_time": _parse_local_dt(request.POST.get("start_time")),
            "end_time": _parse_local_dt(request.POST.get("end_time")),
            "event_type": request.POST.get("event_type", "other"),
            "children": children
        }
        if event:
            update_event(event, request.user, data)
        else:
            create_event(family=family, created_by=request.user, **data)
        return redirect("calendar:calendar_view")



    return render(request, "calendar_app/event_form.html", {
        "event": event, "is_edit": bool(event), "family": family,
        "start": request.GET.get("start", ""), "end": request.GET.get("end", ""),
        "event_types": CalendarEvent.EVENT_TYPES, "breadcrumbs": breadcrumbs,
    })


def _get_event_color(event_type):
    return {
        "custody": "#6f42c1", "school": "#0d6efd", "medical": "#198754",
        "expense": "#ffc107", "legal": "#dc3545", "other": "#6c757d"
    }.get(event_type, "#6c757d")