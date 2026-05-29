# expenses/forms.py
import itertools

from django import forms
from django_select2.forms import Select2Widget

from expenses.models import Expense, ExpenseCategory
from children.models import ChildProfile
from families.utils import get_family_of_user


from django import forms
from .models import ExpenseCategory


class ExpenseCategoryForm(forms.ModelForm):

    class Meta:
        model = ExpenseCategory

        fields = [
            "group",
            "display_name",
            "color",
            "is_active"
        ]

        widgets = {
            "color": forms.TextInput(
                attrs={"type": "color"}
            )
        }

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "child",
            "expense_type",
            "amount",
            "description",
            "expense_date",
            "status"
        ]
        labels = {
            "child": "Figlio",
            "expense_type": "Categoria spesa",
            "amount": "Importo",
            "description": "Descrizione",
            "expense_date": "Data",
            "status": "Stato"
        }
        widgets = {
            'expense_type': Select2Widget(attrs={'data-placeholder': 'Cerca categoria...'}),  # 🔄 Combobox
            'expense_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'child': forms.Select(attrs={'class': 'form-select'})
        }

    def __init__(self, *args, **kwargs):
        # ✅ 1. Estrai custom kwargs PRIMA di chiamare super()
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # ✅ 2. Sicurezza: parte vuoto
        self.fields["child"].queryset = ChildProfile.objects.none()
        self.fields["child"].empty_label = "Seleziona figlio"

        # ✅ 3. Se c'è un user, carica i figli della sua famiglia
        if user:
            family = get_family_of_user(user)  # ⚠️ Assicurati che sia importato in forms.py
            if family:
                self.fields["child"].queryset = family.children.filter(is_active=True)

        # ✅ 4. Categorie raggruppate (logica originale, mantenuta)
        categories = ExpenseCategory.objects.filter(
            is_active=True,
            valid_to__isnull=True,
            group__is_active=True
        ).select_related("group").order_by(
            "group__label",
            "display_name"
        )

        grouped_choices = []

        for group, cats in itertools.groupby(categories, key=lambda c: c.group.label):
            grouped_choices.append((
                group,
                [(c.id, c.display_name) for c in cats]
            ))

        self.fields["expense_type"].choices = grouped_choices
        self.fields["expense_type"].empty_label = "Seleziona categoria"

        expense_type = forms.ModelChoiceField(
            queryset=ExpenseCategory.objects.filter(is_active=True),
            required=True ) # 🔥 OBBLIGATORIO


class ExpenseFilterForm(forms.Form):

    child = forms.ModelChoiceField(
        queryset=ChildProfile.objects.none(),
        required=False,
        label="Figlio",
        empty_label="Tutti i figli"
    )
    status = forms.ChoiceField(  # 🔥 NUOVO
        choices=[("", "Tutti")] + Expense.STATUS_CHOICES,
        required=False,
        label="Stato"
    )

    expense_type = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.all().order_by("display_name"),
        required=False, empty_label="Tutte le categorie",
        label="Categoria",
        widget=forms.Select(attrs={'class': 'form-control'})

    )

    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="Da"
    )

    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label="A"
    )

    def __init__(self, *args, family=None, **kwargs):
        super().__init__(*args, **kwargs)

        if family:
            self.fields["child"].queryset = family.children.filter(is_active=True)

            # 🎨 styling
            for field in self.fields.values():
                field.widget.attrs.update({"class": "form-control"})
        else:
            self.fields["child"].queryset = ChildProfile.objects.all()  # fallback




