from decimal import Decimal

from django import forms

from core.choices import RoleChoices
from expenses.models import Expense
from .models import Invitation, ChildSupportAgreement

from django import forms
from .models import Invitation

# families/forms.py
from django import forms
from core.choices import RoleChoices  # ✅ Import centralizzato
from .models import Invitation


class InvitationForm(forms.ModelForm):
    """
    Form per invitare membri nella famiglia.
    Responsabilità: validazione + UI (NO business logic complessa).
    """

    display_name = forms.CharField(
        required=False,
        label="Nome del destinatario (opzionale)",
        widget=forms.TextInput(attrs={
            "placeholder": "Es. Mario Rossi, Avv. Bianchi...",
            "class": "form-control"
        })
    )

    channel = forms.ChoiceField(
        choices=Invitation.CHANNEL_CHOICES,
        label="Metodo di invito",
        widget=forms.RadioSelect(attrs={"class": "form-check-input"})
    )

    email = forms.EmailField(
        required=False,
        label="Email",
        widget=forms.EmailInput(attrs={
            "placeholder": "nome@esempio.com",
            "class": "form-control"
        })
    )

    phone = forms.CharField(
        required=False,
        label="Telefono (con prefisso)",
        widget=forms.TextInput(attrs={
            "placeholder": "+39 333 1234567",
            "class": "form-control"
        })
    )

    class Meta:
        model = Invitation
        fields = ["role", "channel", "email", "phone", "display_name"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-select"}),
        }

    # =========================
    # INIT
    # =========================
    def __init__(self, *args, user_role=None, family=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user_role = user_role
        self.family = family

        # Default: tutti i ruoli
        self.fields["role"].choices = RoleChoices.choices

        if not family or not user_role:
            return

        # =========================
        # RUOLI GIÀ OCCUPATI
        # =========================
        occupied = set(family.members.values_list("role", flat=True))

        # =========================
        # RUOLI CONSENTITI PER INVITANTE
        # =========================
        if user_role in (RoleChoices.PARENT_A, "parent_a"):
            allowed = {
                RoleChoices.PARENT_B,
                RoleChoices.LAWYER_A,
                RoleChoices.MEDIATOR,
                RoleChoices.CONSULTANT,
            }

        elif user_role in (RoleChoices.PARENT_B, "parent_b"):
            allowed = {
                RoleChoices.PARENT_A,
                RoleChoices.LAWYER_B,
                RoleChoices.MEDIATOR,
                RoleChoices.CONSULTANT,
            }

        elif "lawyer" in str(user_role):
            allowed = {
                RoleChoices.LAWYER_A,
                RoleChoices.LAWYER_B,
                RoleChoices.MEDIATOR,
                RoleChoices.CONSULTANT,
            }

        else:
            allowed = {c[0] for c in RoleChoices.choices}

        # =========================
        # FILTRO FINALE
        # =========================
        available_roles = [
            c for c in RoleChoices.choices
            if c[0] in allowed and c[0] not in occupied
        ]

        self.fields["role"].choices = available_roles

        # =========================
        # CASO NESSUN RUOLO DISPONIBILE
        # =========================
        if not available_roles:
            self.fields["role"].disabled = True
            self.fields["role"].help_text = (
                "Tutti i ruoli sono già assegnati in questa famiglia."
            )

        # =========================
        # UX: se 1 solo ruolo → hidden
        # =========================
        if len(available_roles) == 1:
            self.fields["role"].widget = forms.HiddenInput()

    # =========================
    # CLEAN
    # =========================
    def clean(self):
        cleaned_data = super().clean()

        channel = cleaned_data.get("channel")
        email = cleaned_data.get("email")
        phone = cleaned_data.get("phone")
        role = cleaned_data.get("role")

        if not channel:
            self.add_error("channel", "Seleziona un metodo di invito")

        if channel == "email" and not email:
            self.add_error("email", "Email obbligatoria")

        if channel == "whatsapp" and not phone:
            self.add_error("phone", "Telefono obbligatorio")

        # validazione ruolo
        available_values = {c[0] for c in self.fields["role"].choices}
        if role and role not in available_values:
            self.add_error("role", "Ruolo non disponibile per questa famiglia")

        # duplicati invito
        if self.instance.pk is None and email:
            if Invitation.objects.filter(
                family=self.family,
                email=email,
                status="pending"
            ).exists():
                self.add_error("email", "Invito già esistente")

        return cleaned_data

    # =========================
    # SAVE
    # =========================
    def save(self, commit=True, family=None, sender=None):
        invitation = super().save(commit=False)

        if family:
            invitation.family = family

        if sender:
            invitation.invited_by = sender

        if not invitation.expire_at:
            from django.utils import timezone
            from datetime import timedelta
            invitation.expire_at = timezone.now() + timedelta(days=7)

        if commit:
            invitation.save()

        return invitation


# expenses/forms.py
class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense

        fields = [
            "child", "expense_type", "amount", "description",
            "expense_date", "status"  # ✅ AGGIUNGI QUESTO se vuoi modificarlo via form
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
            "expense_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0", "class": "form-control"}),
        }
        # Se vuoi renderlo readonly in certi casi:
        # readonly_fields = ["status"]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Esempio: rendi status readonly se già approvato
        if self.instance and self.instance.pk:
            if self.instance.status in ("accepted", "paid"):
                self.fields["status"].disabled = True
                self.fields["status"].widget.attrs["readonly"] = True


class ChildSupportAgreementForm(forms.ModelForm):
    class Meta:
        model = ChildSupportAgreement
        # ⚠️ SOLO campi del modello. MAI 'DELETE', 'id' o campi calcolati
        fields = [
            'decree_number', 'decree_date', 'decree_file', 'monthly_amount',
            'split_pct_parent_a', 'payment_day', 'start_date', 'end_date', 'children'
        ]
        widgets = {
            'decree_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'children': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'split_pct_parent_a': forms.NumberInput(
                attrs={'step': '0.01', 'min': '0', 'max': '100', 'class': 'form-control'}
            )
        }

    def clean_split_pct_parent_a(self):
        """Validazione aggiuntiva se necessaria"""
        value = self.cleaned_data.get('split_pct_parent_a')
        if value is not None and (value < 0 or value > 100):
            raise forms.ValidationError("La percentuale deve essere tra 0 e 100.")
        return value