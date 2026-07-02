# accounts/forms.py
# accounts/forms.py
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from core.choices import RoleChoices

User = get_user_model()

# =========================
# 🔹 REGISTRAZIONE
# =========================
class RegisterForm(UserCreationForm):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Conferma Password"}))

    # ✅ AGGIORNATO: Tutti i ruoli della pagina prezzi
    role = forms.ChoiceField(
        choices=[
            (RoleChoices.PARENT, "👨‍👩‍👧 Genitore"),
            (RoleChoices.LAWYER, "⚖️ Avvocato"),
            (RoleChoices.MEDIATOR, "🤝 Mediatore"),
            (RoleChoices.CONSULTANT, "📊 Consulente"),
        ],
        widget=forms.Select(attrs={"class": "form-select"})
    )

    # ✅ NUOVO: Campo piano (pre-compilato dalla URL, modificabile dall'utente)
    plan = forms.ChoiceField(
        choices=[
            ("starter", "Starter "),
            ("pro", "Pro (Piano consigliato)"),
            ("enterprise", "Enterprise (Personalizzato)"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password1', 'password2']
        labels = {
            'first_name': 'Nome',
            'last_name': 'Cognome',
            'email': 'Email',
            'password1': 'Password',
            'password2': 'Conferma Password',
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ✅ Placeholder in italiano
        self.fields['first_name'].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Nome",
            "autofocus": True  #inizia da questo campo
        })
        self.fields['last_name'].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Cognome"
        })
        self.fields['email'].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Email"
        })

        for field_name, field in self.fields.items():
            # ✅ Aggiungi 'plan' alle eccezioni per non sovrascrivere la classe form-select
            if field_name not in ('password1', 'password2', 'role', 'plan', 'first_name', 'last_name', 'email'):
                field.widget.attrs.update({"class": "form-control"})

        email_from_invite = self.initial.get("email")

        if email_from_invite:
            self.fields["email"].initial = email_from_invite

            self.fields["email"].widget.attrs.update({
                "readonly": True,
                "class": "form-control bg-light",
            })

            self.fields["email"].required = True

            self.fields["email"].help_text = (
                "Email precompilata dall'invito (non modificabile)"
            )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Esiste già un account con questa email.")
        return email

    def generate_username(self, email):
        base_username = email.split('@')[0]
        base_username = re.sub(r'[^\w.@+-]', '', base_username)
        if not base_username:
            base_username = "utente"
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.username = self.generate_username(self.cleaned_data["email"])
        if commit:
            user.save()
            # ✅ Il ruolo viene salvato qui. Il piano lo gestisce la view per flessibilità.
            UserProfile.objects.create(user=user, role=self.cleaned_data["role"])
        return user


# =========================
# 🔹 PRIMO LOGIN / AGGIORNAMENTO USER
# =========================
class FirstLoginForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['last_name', 'first_name', 'email']

class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["last_name", "first_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 🔒 Blocca i dati anagrafici DOPO la prima registrazione
        if self.instance.pk:
            for field in ["last_name", "first_name", "email"]:
                self.fields[field].widget.attrs['readonly'] = False
                self.fields[field].help_text = "Non modificabile"


from django import forms
from django_select2.forms import Select2Widget
from accounts.models import UserProfile
import logging

logger = logging.getLogger(__name__)

# accounts/forms.py - MODIFICA il widget in UserProfileForm

from django_select2.forms import Select2Widget


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'address',
            'birth_date',
            'birth_place',
            'birth_place_code',
            'gender',
            'phone',
            'firm_name',
            'partita_iva'
        ]
        labels = {
            'birth_place': 'Luogo di nascita',
            'birth_date': 'Data di nascita',
            'birth_place_code': 'Comune di nascita',
            'gender': 'Sesso',
            'phone': 'Telefono',
            'firm_name': 'Nome studio/ditta',
            'partita_iva': 'Partita IVA',
            'address': 'Indirizzo',
        }
        widgets = {
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Indirizzo completo'}),
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'birth_place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Luogo di nascita'}),
            'gender': forms.Select(
                choices=[('', 'Seleziona...'), ('M', 'Maschio'), ('F', 'Femmina')],
                attrs={'class': 'form-select'}
            ),
            # ✅ Select2 con AJAX
            'birth_place_code': Select2Widget(
                attrs={
                    'data-placeholder': 'Digita per cercare il comune...',
                    'data-minimum-input-length': 2,
                    'data-ajax--url': '/accounts/api/comuni/search/',
                    'data-ajax--delay': 250,
                    'data-theme': 'default',
                }
            ),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+39 123 456789'}),
            'firm_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome del tuo studio legale'}),
            'partita_iva': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IT12345678901'}),
        }

    def __init__(self, *args, **kwargs):
        role = kwargs.pop('role', None)
        super().__init__(*args, **kwargs)

        if not role and self.instance and hasattr(self.instance, 'role'):
            role = self.instance.role

        role = str(role).strip().lower().replace('_a', '').replace('_b', '') if role else ''

        logger.info(f"🔍 UserProfileForm: role = '{role}'")

        # ✅ RIMOSSO: Caricamento statico da JSON
        # Select2 ora usa AJAX per caricare dinamicamente dal DB

        # =========================
        # 👔 LOGICA PER RUOLO
        # =========================
        is_professional = role in ['lawyer', 'mediator', 'consultant']

        if is_professional:
            if 'birth_place' in self.fields:
                del self.fields['birth_place']

            self.fields['firm_name'].required = True
            self.fields['partita_iva'].required = True
            self.fields['phone'].required = True
            self.fields['address'].required = True

            self.fields['firm_name'].label = "Ragione sociale / Nome studio *"
            self.fields['partita_iva'].label = "Partita IVA *"
            self.fields['phone'].label = "Numero di telefono *"
            self.fields['address'].label = "Indirizzo *"

            self.fields['firm_name'].help_text = "Obbligatorio per fatturazione"
            self.fields['partita_iva'].help_text = "Formato: IT + 11 cifre"
            self.fields['phone'].help_text = "Per contatti urgenti con assistiti"

        else:
            if 'firm_name' in self.fields:
                del self.fields['firm_name']
            if 'partita_iva' in self.fields:
                del self.fields['partita_iva']

            if 'birth_place_code' in self.fields:
                self.fields['birth_place_code'].required = True
                self.fields['birth_place_code'].label = "Comune di nascita *"

            self.fields['phone'].required = True
            self.fields['address'].required = True

            if 'birth_place' in self.fields:
                del self.fields['birth_place']

        # =========================
        # 🎨 AGGIUNGI CLASSI CSS
        # =========================
        for name, field in self.fields.items():
            if isinstance(field.widget, Select2Widget):
                continue

            current_class = field.widget.attrs.get("class", "")
            if "form-control" not in current_class:
                field.widget.attrs["class"] = (current_class + " form-control").strip()

            value = self.initial.get(name) or (getattr(self.instance, name, None) if self.instance else None)
            if value:
                field.widget.attrs["class"] += " profile-complete"

    def clean_birth_place_code(self):
        value = self.cleaned_data.get("birth_place_code")

        if not value:
            raise forms.ValidationError("Comune di nascita obbligatorio")

        value = str(value).upper().strip()

        if len(value) != 4:
            raise forms.ValidationError("Codice catastale non valido")

        return value

    def clean(self):
        cleaned_data = super().clean()

        code = cleaned_data.get("birth_place_code")
        if not code:
            raise forms.ValidationError("Comune di nascita obbligatorio")

        cleaned_data["birth_place_code"] = code.upper().strip()

        return cleaned_data
