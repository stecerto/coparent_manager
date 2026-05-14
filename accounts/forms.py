from django.contrib.auth import get_user_model

# accounts/forms.py
import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, UserProfile

#User = get_user_model()

class RegisterForm(UserCreationForm):
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password"}))
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Conferma Password"}))

    role = forms.ChoiceField(
        choices=[("parent", "Genitore"), ("lawyer", "Avvocato")],
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password1', 'password2']
        # ✅ username è escluso: viene generato automaticamente in save()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Applica classi Bootstrap ai campi standard
        for field_name, field in self.fields.items():
            if field_name not in ('password1', 'password2', 'role'):
                field.widget.attrs.update({"class": "form-control"})

        # ✅ CORRETTO: usa self.initial invece di request.method
        if self.initial.get("email"):
            self.fields["email"].widget.attrs.update({
                "readonly": True,
                "class": "form-control bg-light"  # ✅ Sfondo grigio per indicare che è bloccato
            })
            # Opzionale: nascondi l'helper text se presente
            self.fields["email"].help_text = "Email precompilata dall'invito (non modificabile)"

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Esiste già un account con questa email.")
        return email

    def generate_username(self, email):
        """
        Genera un username univoco partendo dall'email.
        Se 'mario' esiste, prova 'mario1', 'mario2', ecc.
        """
        base_username = email.split('@')[0]
        # ✅ Rimuovi caratteri non validi per Django username
        base_username = re.sub(r'[^\w.@+-]', '', base_username)
        if not base_username:
            base_username = "utente"

        username = base_username
        counter = 1
        # ✅ Loop finché non trova un username libero
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        email = self.cleaned_data["email"]

        # ✅ Assegna username generato dinamicamente
        user.username = self.generate_username(email)

        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data["role"]
            )
        return user


# =========================
# FORM PRIMO LOGIN / USER
# =========================

class FirstLoginForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

# =========================
# FORM PROFILO UTENTE
# =========================

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'address',
            'phone',
            'birth_place',
            'firm_name'
        ]
        widgets = {
            'birth_place': forms.TextInput(attrs={'placeholder': 'Luogo di nascita'}),
        }

        def __init__(self, *args, **kwargs):
            role = kwargs.pop('role', None)
            super().__init__(*args, **kwargs)
            if role != 'lawyer':
                self.fields.pop(-1)  #elimina firma_name per user
'''
# =========================
# FORM CHILD
# =========================

class ChildForm(forms.ModelForm):
    class Meta:
        model = ChildProfile
        fields = ['name', 'surname', 'birth_date']
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'})
        }

'''
