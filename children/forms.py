from django import forms
from children.models import ChildProfile


class ChildForm(forms.ModelForm):
    class Meta:
        model = ChildProfile
        fields = [
            "name",
            "surname",
            "birth_date",
            "notes"
        ]

        widgets = {
            "birth_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "notes": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

from django import forms

class ChildSupportForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))