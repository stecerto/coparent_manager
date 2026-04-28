from django import forms
from .models import Invitation


from django import forms
from .models import Invitation


class InvitationForm(forms.ModelForm):

    class Meta:
        model = Invitation
        fields = ["role", "channel", "email", "phone", "display_name"]

    display_name = forms.CharField(
        required=False,
        label="Nome del destinatario (opzionale)"
    )

    role = forms.ChoiceField(choices=[])
    channel = forms.ChoiceField(choices=[
        ("email", "Email"),
        ("whatsapp", "WhatsApp"),
    ])

    email = forms.EmailField(required=False)
    phone = forms.CharField(required=False)

    def __init__(self, *args, user_role=None, **kwargs):
        super().__init__(*args, **kwargs)

        # 🔥 FALLBACK SICURO (sempre visibile se user_role non arriva)
        self.fields["role"].choices = Invitation.ROLE_CHOICES

        if user_role == "parent_a":
            allowed = {"parent_b", "lawyer_a"}

            self.fields["role"].choices = [
                c for c in Invitation.ROLE_CHOICES
                if c[0] in allowed
            ]
            self.fields["role"].initial = "parent_b"

        elif user_role == "parent_b":
            self.fields["role"].choices = [
                ("lawyer_b", "Avvocato Genitore B"),
            ]
            self.fields["role"].initial = "lawyer_b"

    def clean(self):
        cleaned = super().clean()

        if cleaned.get("channel") == "email" and not cleaned.get("email"):
            self.add_error("email", "Obbligatoria per email")

        if cleaned.get("channel") == "whatsapp" and not cleaned.get("phone"):
            self.add_error("phone", "Obbligatorio per WhatsApp")

        return cleaned