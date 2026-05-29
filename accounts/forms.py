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
from .models import UserProfile

User = get_user_model()

# =========================
# 🔹 REGISTRAZIONE
# =========================
class RegisterForm(UserCreationForm):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Conferma Password"}))

    role = forms.ChoiceField(
        choices=[("parent", "Genitore"), ("lawyer", "Avvocato")],
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ('password1', 'password2', 'role'):
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
        fields = ['address', 'phone', 'birth_place', 'firm_name']
        widgets = {
            "address": forms.TextInput(attrs={
                "placeholder": "Via, numero civico, città"
            }),


            'birth_place': forms.TextInput(attrs={'placeholder': 'Luogo di nascita'}),
            'phone': forms.TextInput(attrs={"class": "form-control",'placeholder': '+39 123 456789'}),
        }

    def __init__(self, *args, role=None, **kwargs):
        # ✅ FIX 1: Estrai role PRIMA di super()
        role = kwargs.pop('role', None)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():

            field.widget.attrs["class"] = "form-control"

            value = self.initial.get(name)

            if value:
                field.widget.attrs["class"] += " profile-complete"


        # ✅ FIX 2: Spostato fuori da Meta + sintassi corretta per pop()
        if role != 'lawyer' and 'firm_name' in self.fields:
             del self.fields['firm_name']
#Validazione campo per avvocato phone obbligatorio
    def clean(self):
        cleaned_data = super().clean()
        # Esempio: telefono richiesto SOLO per avvocati
        role = getattr(self.instance, 'role', None) or self.data.get('role')
        if role == 'lawyer' and not cleaned_data.get('phone'):
            self.add_error('phone', "Il telefono è obbligatorio per gli avvocati")
        return cleaned_data

        # 🔒 Blocca telefono dopo la creazione
      #  if self.instance.pk and 'phone' in self.fields:
      #      self.fields['phone'].widget.attrs['readonly'] = True
      #      self.fields['phone'].help_text = "Non modificabile dopo la registrazione"

