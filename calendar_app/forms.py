from django import forms

from models import CalendarEvent


class EventForm(forms.ModelForm):

    class Meta:
        model = CalendarEvent
        fields = [
            "title",
            "description",
            "event_type",
            "amount",
            "start_time",
            "end_time",
            "children"
        ]