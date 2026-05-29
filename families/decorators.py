from django.core.exceptions import PermissionDenied
from core.choices import RoleChoices


def role_required(*allowed_roles):
    """
    Decorator per proteggere view in base al ruolo dell'utente.
    Esempio: @role_required(RoleChoices.LAWYER_A, RoleChoices.LAWYER_B)
    """

    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not hasattr(request.user, 'profile'):
                raise PermissionDenied("Profilo non trovato")

            if request.user.profile.role not in allowed_roles:
                raise PermissionDenied("Accesso non consentito per il tuo ruolo")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator