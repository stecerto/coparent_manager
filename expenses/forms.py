# expenses/forms.py
import itertools
from django import forms
from django_select2.forms import Select2Widget
from children.models import ChildProfile
from expenses.models import Expense, ExpenseCategory
from families.utils import get_family_of_user


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
        ]
        labels = {
            "child": "Figlio",
            "expense_type": "Categoria spesa",
            "amount": "Importo",
            "description": "Descrizione",
            "expense_date": "Data",
        }
        widgets = {
            'expense_type': Select2Widget(attrs={'data-placeholder': 'Cerca categoria...'}),
            'expense_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'child': forms.Select(attrs={'class': 'form-select'})
        }

    # ✅ NUOVO: Checkbox per spesa coniuge
    is_for_spouse = forms.BooleanField(
        required=False,
        label="Spesa per coniuge (mantenimento attivo)",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'id_is_for_spouse'
        }),
        help_text="Seleziona se questa spesa è relativa al mantenimento del coniuge"
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # ✅ Sicurezza: parte vuoto
        self.fields["child"].queryset = ChildProfile.objects.none()
        self.fields["child"].empty_label = "Seleziona figlio"

        # ✅ Verifica se c'è mantenimento coniuge attivo
        has_spouse_support = False
        if user:
            family = get_family_of_user(user)
            if family:
                self.fields["child"].queryset = family.children.filter(is_active=True)

                # ✅ Controlla mantenimento coniuge
                from children.models import ChildSupport
                from datetime import date
                from django.db.models import Q

                today = date.today()
                spouse_support = ChildSupport.objects.filter(
                    family=family,
                    support_type='spouse',
                    is_active=True,
                    start_date__lte=today
                ).filter(
                    Q(end_date__isnull=True) | Q(end_date__gte=today)
                ).first()

                has_spouse_support = spouse_support is not None

        # ✅ Se non c'è mantenimento coniuge, nascondi il checkbox
        if not has_spouse_support:
            self.fields['is_for_spouse'].widget = forms.HiddenInput()
            self.fields['is_for_spouse'].required = False

        # ✅ Categorie raggruppate
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

        if 'status' in self.fields:
            del self.fields['status']

    expense_type = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.filter(is_active=True),
        required=True
    )


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
        else:
            self.fields["child"].queryset = ChildProfile.objects.all()  # fallback

        # 🎨 styling
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})





