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
    Form per invitare nuovi membri nella famiglia.
    Filtra automaticamente i ruoli disponibili e gestisce validazione canale.
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
            "class": "form-control",
            "pattern": r"^\+?[0-9\s\-\(\)]+$"
        })
    )

    class Meta:
        model = Invitation
        fields = ["role", "channel", "email", "phone", "display_name"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user_role=None, family=None, **kwargs):
        """
        Inizializza il form filtrando i ruoli disponibili.
        """
        # Estrai parametri custom PRIMA di super()
        if 'user_role' in kwargs:
            user_role = kwargs.pop('user_role')
        if 'family' in kwargs:
            family = kwargs.pop('family')

        super().__init__(*args, **kwargs)

        # 🔹 STEP 1: Carica tutti i ruoli come fallback
        all_roles = RoleChoices.all_roles()
        self.fields["role"].choices = all_roles

        # 🔹 STEP 2: Se abbiamo la famiglia, calcola i ruoli DISPONIBILI
        if family:
            # ✅ Calcola ruoli occupati (una sola volta)
            occupied = set(family.members.values_list('role', flat=True)) | set(
                family.invitations.filter(status='pending').values_list('role', flat=True)
            )

            # 🔹 STEP 3: Filtra in base a chi sta invitando (usa RoleChoices, non vecchi constant)
            if user_role in (RoleChoices.PARENT_A, "parent_a"):
                allowed = {RoleChoices.PARENT_B, RoleChoices.LAWYER_A, RoleChoices.LAWYER_B,
                           RoleChoices.MEDIATOR, RoleChoices.CONSULTANT}
            elif user_role in (RoleChoices.PARENT_B, "parent_b"):
                allowed = {RoleChoices.PARENT_A, RoleChoices.LAWYER_A, RoleChoices.LAWYER_B,
                           RoleChoices.MEDIATOR, RoleChoices.CONSULTANT}
            elif user_role in (RoleChoices.LAWYER_A, "lawyer_a", RoleChoices.LAWYER_B, "lawyer_b"):
                allowed = {RoleChoices.LAWYER_A, RoleChoices.LAWYER_B,
                           RoleChoices.MEDIATOR, RoleChoices.CONSULTANT}
            else:
                # Mediator/consultant: possono invitare tutti i ruoli
                allowed = {c[0] for c in RoleChoices.choices}

            # 🔹 STEP 4: Rimuovi ruoli già occupati e applica permessi
            available_roles = [c for c in RoleChoices.choices if c[0] in (allowed - occupied)]

            if available_roles:
                self.fields["role"].choices = available_roles

                # 🔹 STEP 5: Auto-seleziona il ruolo "complementare" se logico
                available_values = {c[0] for c in available_roles}  # ✅ Estrai solo i valori stringa

                if user_role in (RoleChoices.PARENT_A, "parent_a") and RoleChoices.PARENT_B in available_values:
                    self.fields["role"].initial = RoleChoices.PARENT_B
                elif user_role in (RoleChoices.PARENT_B, "parent_b") and RoleChoices.PARENT_A in available_values:
                    self.fields["role"].initial = RoleChoices.PARENT_A
                elif user_role in (RoleChoices.LAWYER_A, "lawyer_a") and RoleChoices.LAWYER_B in available_values:
                    self.fields["role"].initial = RoleChoices.LAWYER_B
                elif user_role in (RoleChoices.LAWYER_B, "lawyer_b") and RoleChoices.LAWYER_A in available_values:
                    self.fields["role"].initial = RoleChoices.LAWYER_A
                else:
                    # Fallback: primo ruolo disponibile
                    self.fields["role"].initial = available_roles[0][0]
            else:
                # Nessun ruolo disponibile → disabilita il campo
                self.fields["role"].disabled = True
                self.fields["role"].help_text = "Tutti i ruoli sono già assegnati in questa famiglia."

        # 🔹 STEP 6: Se c'è SOLO un ruolo disponibile, nascondilo (UX pulita)
        if len(self.fields["role"].choices) == 1:
            self.fields["role"].widget = forms.HiddenInput()
            role_value, role_label = self.fields["role"].choices[0]
            self.fields["role"].help_text = f"Ruolo assegnato automaticamente: {role_label}"

        # 🔹 STEP 7: Gestione visibilità email/phone in base al canale
        self._toggle_channel_fields()

    def _toggle_channel_fields(self):
        """Mostra/nasconde email o phone in base al canale selezionato"""
        # ✅ Controlla prima initial (GET), poi data (POST)
        channel = self.initial.get("channel") or self.data.get("channel") or "email"

        if channel == "email":
            self.fields["email"].required = True
            self.fields["phone"].required = False
            self.fields["phone"].widget.attrs.update({"disabled": "disabled", "class": "form-control text-muted"})
        elif channel == "whatsapp":
            self.fields["email"].required = False
            self.fields["phone"].required = True
            self.fields["email"].widget.attrs.update({"disabled": "disabled", "class": "form-control text-muted"})

        # Aggiungi attributi data- per JS dinamico (opzionale)
        self.fields["channel"].widget.attrs.update({
            "data-toggle-email": "true",
            "data-email-field": "id_email",
            "data-phone-field": "id_phone"
        })

    def clean(self):
        """Validazione incrociata canale → contatto"""
        cleaned_data = super().clean()
        channel = cleaned_data.get("channel")
        email = cleaned_data.get("email")
        phone = cleaned_data.get("phone")
        role = cleaned_data.get("role")

        # 🔹 Validazione canale obbligatorio
        if not channel:
            self.add_error("channel", "Seleziona un metodo di invito")

        # 🔹 Validazione contatto in base al canale
        if channel == "email" and not email:
            self.add_error("email", "L'email è obbligatoria per gli inviti via email")
        elif channel == "whatsapp" and not phone:
            self.add_error("phone", "Il telefono è obbligatorio per gli inviti via WhatsApp")

        # 🔹 Validazione ruolo (se campo visibile)
        if role:
            available_values = {c[0] for c in self.fields["role"].choices}
            if role not in available_values:
                self.add_error("role", "Ruolo non disponibile per questa famiglia")

        # 🔹 Validazione duplicato invito pendente (extra sicurezza)
        if self.instance.pk is None and email and channel == "email":
            if Invitation.objects.filter(
                    family=getattr(self.instance, 'family', None),
                    email=email,
                    status="pending"
            ).exists():
                self.add_error("email", "Esiste già un invito pendente per questa email")

        return cleaned_data

    def save(self, commit=True, family=None, sender=None, **kwargs):
        """
        Override di save() per impostare automaticamente family e invited_by.
        """
        invitation = super().save(commit=False)

        # ✅ Usa i parametri espliciti se forniti, altrimenti fallback su instance
        if family:
            invitation.family = family
        if sender:
            invitation.invited_by = sender

        # Auto-expire a 7 giorni se non impostato
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