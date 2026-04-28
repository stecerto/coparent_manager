from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect

from accounts.models import UserProfile


def email_confirmed(user):
    return user.is_authenticated and user.is_active

def confirmed_required(view_func):
    return user_passes_test(email_confirmed)(view_func)

def first_login_required(view_func):
    #blocca accesso se il primo setup non è completo
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        profile = UserProfile.objects.filter(user=request.user).first()
        if not request.user.is_authenticated:
            return redirect('login')
        # se i dati principali non sono ancora impostati
        if not profile or not profile.setup_complete:
            return redirect('families:setup')

        return view_func(request, *args, **kwargs)

    return _wrapped_view