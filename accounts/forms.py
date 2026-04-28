import uuid

from django import forms
from django.contrib.auth import get_user_model

from children.models import ChildProfile
from .models import UserProfile
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class RegisterForm(UserCreationForm):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)
    role= forms.ChoiceField(
        choices=[
            ("owner", "Genitore"),
            ("lawyer", "Avvocato",)
        ]
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "Esiste già un account con questa email."
            )
        else:
            self.fields["email"].widget.attrs["readonly"] = True

        return email

    def generate_username(self, email):
        while True:
            username = (
                    email.split('@')[0] # + str(uuid.uuid4())[:6]
            )
            if not User.objects.filter(username=username).exists():
                return username

            else:
                raise forms.ValidationError(
                    "Esiste già un account con questo username."
                )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])

        email = self.cleaned_data["email"]

        user.username = self.generate_username(email)


        if commit:
            user.save()
            # 🔥 CREA PROFILO
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
