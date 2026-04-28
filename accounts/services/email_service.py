from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from config import settings


def send_activation_email(request,user):
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    #current_site = get_current_site(request)
    #activation_link = f"http://127.0.0.1:8000/accounts/activate/?uidb64={uidb64}&token={token}"
    domain = request.get_host()
    activation_link = f"https://{domain}" + reverse("activate") + f"?uidb64={uidb64}&token={token}"

    html_message = render_to_string("emails/activation_email.html", {
        "user": user,
        "activation_link": activation_link,
    })

    send_mail(
        subject="Conferma email",
        message="Attiva il tuo account",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message
    )

    print(settings.DEFAULT_FROM_EMAIL)
