import profile

from django.contrib.auth import get_user_model

# accounts/forms.py
import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
# accounts/forms.py
import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from core.choices import RoleChoices
from .models import UserProfile

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # ✅ Aggiungi 'plan' alle eccezioni per non sovrascrivere la classe form-select
            if field_name not in ('password1', 'password2', 'role', 'plan'):
                field.widget.attrs.update({"class": "form-control"})

        if self.initial.get("email"):
            self.fields["email"].widget.attrs.update({
                "readonly": True,
                "class": "form-control bg-light"
            })
            self.fields["email"].help_text = "Email precompilata dall'invito (non modificabile)"

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
                self.fields[field].widget.attrs['readonly'] = True
                self.fields[field].help_text = "Non modificabile"


# =========================
# 🔹 PROFILO UTENTE (UserProfile)
# =========================
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['firm_name', 'address', 'phone', 'birth_place', 'partita_iva']
        widgets = {
            'firm_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome del tuo studio legale'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Indirizzo completo'}),
            'birth_place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Luogo di nascita'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+39 123 456789'}),
            'partita_iva': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IT12345678901'}),
        }

    def __init__(self, *args, role=None, **kwargs):
        # 1. Estrai role PRIMA di chiamare super()
        role = kwargs.pop('role', None)

        super().__init__(*args, **kwargs)

        # ✅ BLINDATURA: se role non è passato, prendilo dall'istanza
        if not role and self.instance and hasattr(self.instance, 'role'):
            role = self.instance.role

        # Normalizza il ruolo (rimuovi eventuali suffissi _a/_b)
        role = str(role).strip().lower().replace('_a', '').replace('_b', '') if role else ''

        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 UserProfileForm: role = '{role}'")

        # ✅ CORRETTO: Controlla se è un PROFESSIONISTA (lawyer, mediator, consultant)
        is_professional = role in ['lawyer', 'mediator', 'consultant']

        if is_professional:
            # PROFESSIONISTI (lawyer, mediator, consultant):
            # Mostra firm_name e partita_iva, nascondi birth_place
            if 'birth_place' in self.fields:
                del self.fields['birth_place']
                logger.info("🔍 birth_place RIMOSSO per professionista")

            # Rendi obbligatori i 4 campi professionali
            self.fields['firm_name'].required = True
            self.fields['partita_iva'].required = True
            self.fields['phone'].required = True
            self.fields['address'].required = True

            # Label con asterisco
            self.fields['firm_name'].label = "Ragione sociale / Nome studio *"
            self.fields['partita_iva'].label = "Partita IVA *"
            self.fields['phone'].label = "Numero di telefono *"
            self.fields['address'].label = "Indirizzo *"

            # Help text
            self.fields['firm_name'].help_text = "Obbligatorio per fatturazione"
            self.fields['partita_iva'].help_text = "Formato: IT + 11 cifre"
            self.fields['phone'].help_text = "Per contatti urgenti con assistiti"

        else:
            # GENITORI: nascondi firm_name e partita_iva, mostra birth_place
            if 'firm_name' in self.fields:
                del self.fields['firm_name']
            if 'partita_iva' in self.fields:
                del self.fields['partita_iva']

            # birth_place obbligatorio per genitori
            if 'birth_place' in self.fields:
                self.fields['birth_place'].required = True
                self.fields['birth_place'].label = "Luogo di nascita *"

            # phone e address obbligatori
            self.fields['phone'].required = True
            self.fields['address'].required = True

        # 4. Aggiungi classe CSS a tutti i campi
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"

            value = self.initial.get(name) or (getattr(self.instance, name, None) if self.instance else None)
            if value:
                field.widget.attrs["class"] += " profile-complete"
