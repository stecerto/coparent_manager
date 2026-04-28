from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from calendar_app.models import CalendarEvent
from calendar_app.services.calendar_service import create_event, update_event
from families.utils import get_family_of_user


@login_required
def delete_event_view(request, event_id):
    event = get_object_or_404(
        CalendarEvent,
        id=event_id
    )

    if event.family.members.filter(
        user=request.user
    ).exists():
        event.delete()

    return redirect("families:family_calendar")

@login_required
def event_form_view(request, event_id=None):
    family = get_family_of_user(request.user)

    event = None
    is_edit = False
    # ➕ dati da calendario
    start = request.GET.get("start")
    end = request.GET.get("end")

    if event_id:
        event = get_object_or_404(CalendarEvent, id=event_id, family=family)
        is_edit = True

    if request.method == "POST":

        child_ids = request.POST.getlist("children")
        children = family.children.filter(id__in=child_ids)

        if is_edit:
            update_event(event, request.user, {
                "title": request.POST.get("title"),
                "description": request.POST.get("description"),
                "start_time": request.POST.get("start_time"),
                "end_time": request.POST.get("end_time"),
                "children": children
            })
        else:
            create_event(
                family=family,
                title=request.POST.get("title"),
                description=request.POST.get("description"),
                start_time=request.POST.get("start_time"),
                end_time=request.POST.get("end_time"),
                created_by=request.user,
                children=children
            )

        return redirect("calendar:calendar_view")

    return render(request, "calendar_app/event_form.html", {
        "event": event,
        "is_edit": is_edit,
        "family": family,
        "start": start,
        "end": end
    })


