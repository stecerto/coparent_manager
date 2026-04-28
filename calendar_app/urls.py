from django.urls import path

from .views.events import event_form_view, delete_event_view
from .views.calendar import  family_calendar_view #, update_event_ajax, delete_event_view, calendar_events_json

app_name = "calendar"
urlpatterns = [
    path("", family_calendar_view, name="calendar_view"),
    #path("events-json/", calendar_events_json, name="events_json"),
    path("event/create/", event_form_view, name="event_create"),
    path("event/<int:event_id>/edit/", event_form_view, name="event_edit"),
    path("event/<int:event_id>/delete/", delete_event_view, name="event_delete"),
]