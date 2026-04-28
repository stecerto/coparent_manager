from django import forms
from .models import Document


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    widget = MultiFileInput

    def clean(self, data, initial=None):
        if not data:
            return []

        if not isinstance(data, (list, tuple)):
            data = [data]

        return data


class DocumentUploadForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        required=False,
        help_text="Se vuoto, verrà usato il nome originale del file"
    )

    files = MultiFileField()

    category = forms.ChoiceField(
        choices=Document.CATEGORY_CHOICES
    )

    scope = forms.ChoiceField(
        choices=Document.SCOPE_CHOICES
    )

    reference_year = forms.IntegerField(
        required=False
    )