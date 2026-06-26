import itertools
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django_select2.forms import Select2Widget

from children.models import ChildProfile
from core.choices import RoleChoices
from expenses.models import Expense, ExpenseCategory
from families.utils import get_family_of_user
from .models import Invitation, ChildSupportAgreement, FamilyMember, SpouseSupportAgreement

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
        fields = ["role", "channel", "email", "phone", "display_name", 'message']
        widgets = {
            "role": forms.Select(attrs={"class": "form-select"}),
        }

    # =========================
    # INIT
    # =========================
    def __init__(self, *args, user_role=None, family=None, inviter=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user_role = user_role
        self.family = family
        self.inviter = inviter

        # ✅ AGGIUNGI CAMPO FAMIGLIA TARGET (per professionisti)
        from families.models import Family
        self.fields['target_family'] = forms.ModelChoiceField(
            queryset=Family.objects.none(),
            required=False,
            label="Seleziona la Famiglia",
            widget=forms.Select(attrs={'class': 'form-select'})
        )

        # Default: tutti i ruoli
        self.fields["role"].choices = RoleChoices.choices



        # ✅ SE L'INVITANTE È UN PROFESSIONISTA, POPOLA IL DROPDOWN FAMIGLIE
        if inviter and hasattr(inviter, 'family_memberships'):
            # Professionisti possono invitare solo per le famiglie a cui sono assegnati
            family_ids = inviter.family_memberships.values_list('family_id', flat=True)
            self.fields['target_family'].queryset = Family.objects.filter(id__in=family_ids)

            # Se è un professionista, rendi obbligatoria la scelta della famiglia
            if user_role in ['lawyer','lawyer_a','lawyer_b','mediator', 'mediator_a', 'mediator_b',
                           'consultant', 'consultant_a', 'consultant_b']:
                self.fields['target_family'].required = False
            else:
                # Genitori: nascondi il campo (la famiglia è implicita)
                self.fields['target_family'].widget = forms.HiddenInput()
                self.fields['target_family'].initial = family.id
        else:
            # Fallback: nascondi il campo
            self.fields['target_family'].widget = forms.HiddenInput()
            self.fields['target_family'].initial = family.id if family else None

        # =========================
        # RUOLI GIÀ OCCUPATI
        # =========================
        if family:
            occupied = set(family.members.values_list("role", flat=True))
        else:
            occupied = set()  # ✅ Set vuoto: nessun ruolo occupato

        # =========================
        # RUOLI CONSENTITI PER INVITANTE
        # =========================
        if user_role in (RoleChoices.PARENT_A, "parent_a"):
            # Genitore A invita: mostra ruoli specifici
            allowed = {
                RoleChoices.PARENT_B,
                RoleChoices.LAWYER_A,
                RoleChoices.MEDIATOR,
                RoleChoices.CONSULTANT,
            }

        elif user_role in (RoleChoices.PARENT_B, "parent_b"):
            # Genitore B invita: mostra ruoli specifici
            allowed = {
                RoleChoices.PARENT_A,
                RoleChoices.LAWYER_B,
                RoleChoices.MEDIATOR,
                RoleChoices.CONSULTANT,
            }

        elif "lawyer" in str(user_role) or "mediator" in str(user_role) or "consultant" in str(user_role):
            # ✅ PROFESSIONISTI: mostrano SOLO ruoli base (senza _a/_b)
            # Il suffisso verrà calcolato automaticamente in base alla famiglia selezionata
            # NON devono vedere "lawyer" perché sono già loro l'avvocato
            allowed = {
                "parent",  # Genitore (base, senza suffisso)
                "mediator",  # Mediatore (base)
                "consultant",  # Consulente (base)
            }

        else:
            # Fallback per altri ruoli
            allowed = {c[0] for c in RoleChoices.choices}

        # =========================
        # FILTRO FINALE
        # =========================
        available_roles = [
            c for c in RoleChoices.choices
            if c[0] in allowed and c[0] not in occupied
        ]

        # ✅ Se l'invitante è un professionista, aggiungi i ruoli base se non ci sono
        if "lawyer" in str(user_role) or "mediator" in str(user_role) or "consultant" in str(user_role):
            # Aggiungi manualmente i ruoli base se mancano
            base_roles = [
                ("parent", "Genitore"),
                ("mediator", "Mediatore"),
                ("consultant", "Consulente"),
            ]
            available_roles = [
                c for c in base_roles
                if c[0] in allowed
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
        target_family = cleaned_data.get("target_family")
        # ✅ NUOVA LOGICA: Gestione target_family in base al ruolo invitato
        if role == 'parent':
            # Se invita un genitore, la famiglia è sempre None (se ne crea una nuova)
            cleaned_data['target_family'] = None
        else:
            # Se invita mediatore o consulente, la famiglia è OBBLIGATORIA
            if not target_family:
                self.add_error("target_family",
                               "⚠️ Devi selezionare una famiglia esistente per invitare un professionista.")

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

        # ✅ Evita inviti duplicati per lo stesso utente in famiglie diverse
        if self.instance.pk is None and email:
            target_user = get_user_model().objects.filter(email=email).first()
            if target_user and FamilyMember.objects.filter(user=target_user, family=self.family).exists():
                self.add_error("email", "Questo utente è già membro di questa famiglia")

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
        })
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

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


from django import forms
from django.core.exceptions import ValidationError


class SpouseSupportForm(forms.Form):
    """Form dedicato per il mantenimento al coniuge con sentenza"""

    # ✅ MANTIENI 'amount' (non 'monthly_amount')
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        label="Importo mensile (€)",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        })
    )

    start_date = forms.DateField(
        label="Data inizio",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )

    end_date = forms.DateField(
        label="Data fine (opzionale)",
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )

    payment_day = forms.IntegerField(
        label="Giorno del mese per pagamento",
        min_value=1,
        max_value=31,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
            'max': '31'
        })
    )

    payer_role = forms.ChoiceField(
        label="Chi versa il mantenimento",
        choices=[
            ('parent_a', 'Genitore A versa a Genitore B'),
            ('parent_b', 'Genitore B versa a Genitore A'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    decree_number = forms.CharField(
        label="Numero sentenza",
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Es: Sentenza n. 123/2026'
        })
    )

    decree_date = forms.DateField(
        label="Data sentenza",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )

    decree_file = forms.FileField(
        label="File sentenza (PDF)",
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if end_date and start_date and end_date < start_date:
            raise ValidationError("La data fine deve essere successiva alla data inizio")

        return cleaned_data


from accounts.models import User


class SpouseSupportAgreementForm(forms.ModelForm):
    """Form per inserimento/modifica mantenimento coniuge"""

    class Meta:
        model = SpouseSupportAgreement
        fields = [
            'decree_number', 'decree_date', 'decree_file',
            'monthly_amount', 'payment_day',
            'start_date', 'end_date', 'beneficiary'
        ]
        widgets = {
            'decree_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'monthly_amount': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'class': 'form-control',
                'placeholder': 'Es: 500.00'
            }),
            'payment_day': forms.NumberInput(attrs={
                'min': '1',
                'max': '31',
                'class': 'form-control',
                'placeholder': 'Es: 5'
            }),
            'beneficiary': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'decree_number': 'Numero sentenza/accordo',
            'decree_date': 'Data sentenza',
            'decree_file': 'File sentenza (PDF)',
            'monthly_amount': 'Importo mensile (€)',
            'payment_day': 'Giorno del mese per il pagamento',
            'start_date': 'Data inizio mantenimento',
            'end_date': 'Data fine mantenimento',
            'beneficiary': 'Ex coniuge beneficiario',
        }
        help_texts = {
            'monthly_amount': 'Importo mensile stabilito dalla sentenza (es: €500)',
            'payment_day': 'Giorno del mese in cui va pagato il mantenimento (1-31)',
            'end_date': 'Obbligatoria per mantenimento coniuge (es: 31/12/2030)',
            'beneficiary': 'Seleziona l\'ex coniuge che riceve il mantenimento',
        }

    def __init__(self, *args, family=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Filtra beneficiari: solo utenti con ruolo spouse nella famiglia
        if family:
            from families.models import FamilyMember
            spouse_members = FamilyMember.objects.filter(
                family=family,
                role='spouse'
            ).select_related('user')

            self.fields['beneficiary'].queryset = User.objects.filter(
                id__in=[m.user_id for m in spouse_members]
            )

        # ✅ end_date è OPZIONALE (rimuovi required=True)
        self.fields['end_date'].required = False

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        # ✅ Validazione: se end_date è inserita, deve essere dopo start_date
        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError("La data fine deve essere successiva alla data inizio")

        return cleaned_data