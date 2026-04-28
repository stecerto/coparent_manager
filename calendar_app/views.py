from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from expenses.models import Expense
from families.utils import get_family_of_user
from services.calendar_service import create_event, get_family_events


@login_required
def family_calendar_view(request):
    family = get_family_of_user(request.user)
    if not family:
        return render(request, "calendar_app/no_family.html")

    if request.method == "POST":
        title = request.POST.get("title")
        start_time = request.POST.get("start_time")
        end_time = request.POST.get("end_time")
        description = request.POST.get("description")
        create_event(family, title, start_time, end_time, request.user, description)
        return redirect("calendar:calendar_app")

    events = get_family_events(family)
    return render(request, "calendar_app/calendar_app.html", {"events": events, "family": family})


