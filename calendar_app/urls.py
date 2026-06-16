# calendar_app/urls.py
from django.urls import path
#from .views.events import events_json,event_form_view, delete_event_view, update_event_ajax  # ✅ Aggiungi update_event_ajax
from . import views

app_name = "calendar"

urlpatterns = [
    # 🗓️ Vista principale calendario
    path("", views.family_calendar_view, name="calendar_view"),  # ✅ Nome coerente con template

    # 📡 API JSON per FullCalendar
    path("events-json/", views.events_json, name="events_json"),

    # ➕ Creazione evento (form classico)
    path("event/create/", views.event_form_view, name="event_create"),

    # ✏️ Modifica evento (form classico)
    path("event/<int:event_id>/edit/", views.event_form_view, name="event_edit"),

    # 🔁 Aggiornamento AJAX (drag&drop / resize) - ✅ NUOVO
    path("event/<int:event_id>/update/", views.update_event_ajax, name="event_update"),

    # 🗑️ Eliminazione evento
    path("event/<int:event_id>/delete/", views.delete_event_view, name="event_delete"),
    # 📋 Lista eventi
    path('events/', views.events_list_view, name='events_list'),
    # 👁️ ✅ NUOVO: Dettaglio evento (aggiungi questa riga)
    path('event/<int:event_id>/detail/', views.event_detail_view, name='event_detail'),
]