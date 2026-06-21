# core/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from core.plans import PLAN_LEVELS

def plan_required(min_plan="pro"):
    """Blocca la view se il piano utente è inferiore a min_plan"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            profile = getattr(request.user, 'profile', None) or getattr(request.user, 'userprofile', None)
            user_plan = getattr(profile, 'plan', 'starter') if profile else 'starter'
            user_level = PLAN_LEVELS.get(user_plan, 1)
            required_level = PLAN_LEVELS.get(min_plan, 2)

            if user_level < required_level:
                messages.error(request, f"⚠️ Funzione riservata al piano {min_plan.title()}. Effettua l'upgrade.")
                return redirect('core:pricing')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator