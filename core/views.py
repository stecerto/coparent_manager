from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from accounts.decorators import confirmed_required, first_login_required
from core.choices import RoleChoices


@login_required
def home(request):
    """
    Home page: redirect in base al ruolo dell'utente.
    NON importa nulla da families o accounts.
    """
    user = request.user

    # Controlla il ruolo dell'utente (da UserProfile)
    profile = getattr(user, 'userprofile', None)

    if profile:
        role = profile.role

        # Professionisti → professional_dashboard
        if role in ['lawyer', 'mediator', 'consultant']:
            return redirect('families:professional_dashboard')

        # Genitori → family_dashboard (che gestirà la logica di famiglia)
        elif role in ['parent', 'parent_a', 'parent_b']:
            return redirect('families:family_dashboard')

    # Fallback: setup page
    return redirect('families:setup')

def pricing_view(request):
    """Pagina pricing con piani differenziati per ruolo"""

    # Se l'utente è loggato e ha un ruolo legale, mostra solo piani avvocati
    if request.user.is_authenticated and request.user.profile.role in ['lawyer_a', 'lawyer_b']:
        show_lawyer_plans = True
    else:
        show_lawyer_plans = False

    return render(request, "core/pricing.html", {
        "show_lawyer_plans": show_lawyer_plans,
        "trial_days": 14,  # Passato al template per dinamicità
    })

@login_required
@confirmed_required
@first_login_required
def dashboard(request):
    return render(request, "families/family_dashboard.html")


@login_required
def lawyer_home_view(request):
    # 🔒 Sicurezza: solo avvocati possono accedere
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role not in RoleChoices.lawyer_roles():
        return redirect('home')  # O 'families:lawyer_dashboard' se preferisci

    context = {
        'user': request.user,
        'profile': profile,
    }
    return render(request, 'core/lawyer_home.html', context)



def privacy_policy_view(request):
    """Pagina Privacy Policy - accessibile anche senza login"""
    return render(request, "pages/privacy_policy.html")

