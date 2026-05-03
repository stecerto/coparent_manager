# expenses/forms.py
from django import forms

from expenses.models import Expense, ExpenseCategory
from children.models import ChildProfile
from families.utils import get_family_of_user


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "child",
            "expense_type",
            "amount",
            "description",
            "expense_date",
        ]
        widgets = {
            "expense_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # 🔥 sicurezza: nessun figlio di default
        self.fields["child"].queryset = ChildProfile.objects.none()

        # 🔥 expense_type come dropdown reale dal DB
        self.fields["expense_type"].queryset = ExpenseCategory.objects.all()
        self.fields["expense_type"].empty_label = "Seleziona categoria"

        if user:
            family = get_family_of_user(user)

            if family:
                self.fields["child"].queryset = (
                    family.children.filter(is_active=True)
                )
            else:
                self.fields["child"].queryset = (
                    ChildProfile.objects.none()
                )
                # 🔥 UX migliore
        self.fields["child"].empty_label = "Seleziona figlio"



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
        queryset=ExpenseCategory.objects.all(),
        required=False,
        label="Categoria",
        empty_label="Tutte"
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




