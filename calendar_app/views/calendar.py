from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import models
from django.shortcuts import render, redirect

from calendar_app.services.calendar_service import (
    create_event,
    get_family_events
)
from families.models import Family
from families.utils import get_family_of_user


@login_required
def family_calendar_view(request):
    family = get_family_of_user(request.user)

    if not family:
        return render(
            request,
            "calendar_app/no_family.html"
        )

    if request.method == "POST":
        title = request.POST.get("title")
        start_time = request.POST.get("start_time")
        end_time= request.POST.get("end_time")
        description = request.POST.get("description")
        event_type = request.POST.get("event_type", "other")

        child_ids = request.POST.getlist("children")

        children = family.children.filter(
            id__in=child_ids,
            is_active=True
        )

        create_event(
            family=family,
            title=title,
            start_time=start_time,
            end_time=end_time,
            created_by=request.user,
            description=description,
            event_type=event_type,
            children=children,
        )

        return redirect("calendar:calendar_view")

    events = get_family_events(family)

    return render(
        request,
        "calendar_app/calendar.html",
        {
            "events": events,
            "family": family
        }
    )


'''
@login_required
def calendar_events_json(request):
    family = get_family_of_user(request.user)

    if not family:
        return JsonResponse([], safe=False)

    events = get_family_events(family)

    data = []
    for event in events:
        data.append({
            "id": event.id,
            "title": event.title,
            "start": event.start_time.isoformat(),
            "end": event.end_time.isoformat(),
            "extendedProps": {
                "description": event.description,
                "children": list(event.children.values_list("id", flat=True))
            }
        })
    return JsonResponse(data, safe=False)

@require_POST
@login_required
def update_event_ajax(request, event_id):
    family = get_family_of_user(request.user)

    event = CalendarEvent.objects.get(id=event_id, family=family)

    child_ids = request.POST.getlist("children")
    children = family.children.filter(id__in=child_ids)

    new_event = update_event(event, request.user, {
        "title": request.POST.get("title"),
        "description": request.POST.get("description"),
        "start_time": request.POST.get("start_time"),
        "end_time": request.POST.get("end_time"),
        "children": children
    })

    return JsonResponse({"status": "ok", "id": new_event.id})


@require_POST
@login_required
def delete_event_view(request, event_id):
    family = get_family_of_user(request.user)

    event = get_object_or_404(
        CalendarEvent,
        id=event_id,
        family=family
    )

    event.delete()

    return redirect("calendar:calendar_view")
'''