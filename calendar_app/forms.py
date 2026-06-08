# calendar_app/forms.py
from django import forms
from .models import CalendarEvent
from expenses.models import ExpenseCategory


class EventForm(forms.ModelForm):
    # ✅ Campo amount separato (non nel modello CalendarEvent)
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
        help_text="Importo se l'evento genera una spesa"
    )

    class Meta:
        model = CalendarEvent
        fields = [
            "title",
            "description",
            "event_type",
            "expense_category",  # ✅ Usa categoria spese
            "start_time",
            "end_time",
            "children"
        ]
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtra categorie per famiglia
        if self.instance and self.instance.family:
            self.fields['expense_category'].queryset = ExpenseCategory.objects.filter(
                family=self.instance.family,
                is_active=True
            )

        # Se stiamo modificando un evento esistente con spesa, precompila amount
        if self.instance and self.instance.linked_expense:
            self.fields['amount'].initial = self.instance.linked_expense.amount