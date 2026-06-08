from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.decorators import confirmed_required, first_login_required
from core.choices import RoleChoices
from core.plans import PLAN_FEATURES, PLAN_LEVELS


@login_required
@login_required
def home(request):
    """
    Home page: redirect in base al ruolo dell'utente.
    NON importa nulla da families o accounts.
    """
    user = request.user

    # ✅ FIX: Supporta sia 'profile' che 'userprofile'
    profile = getattr(user, 'userprofile', None) or getattr(user, 'profile', None)

    if not profile:
        return redirect('families:setup')

    # ✅ CRITICO: Normalizza il ruolo a stringa lowercase
    role_raw = profile.role
    role_str = str(role_raw).strip().lower() if role_raw else ''

    # Rimuovi eventuali suffissi _a, _b (es. 'lawyer_a' → 'lawyer')
    role_base = role_str.replace('_a', '').replace('_b', '')

    # Debug log (rimuovi in produzione)
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🏠 Home - Ruolo raw: '{role_raw}', normalizzato: '{role_base}'")

    # Professionisti → professional_dashboard
    if role_base in ['lawyer', 'mediator', 'consultant']:
        if not profile.setup_complete:
            return redirect('families:setup')
        return redirect('families:professional_dashboard')

    # Genitori → family_dashboard
    elif role_base in ['parent']:
        if not profile.setup_complete:
            return redirect('families:setup')
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


@login_required
def change_plan_view(request):
    """Permette all'utente di cambiare piano sfruttando la logica centralizzata di core/plans.py"""
    # ✅ Usa lo stesso pattern del tuo decoratore plan_required
    profile = getattr(request.user, 'profile', None)
    if not profile:
        messages.error(request, "⚠️ Profilo non trovato. Contatta il supporto.")
        return redirect("home")

    current_plan = getattr(profile, 'plan', 'starter')

    if request.method == "POST":
        new_plan = request.POST.get("plan")
        action = request.POST.get("action")

        # ✅ 1. Cancellazione
        if action == "cancel":
            profile.plan = "cancelled"
            profile.plan_cancelled_at = timezone.now()
            profile.save()
            messages.warning(request,
                             "⚠️ Abbonamento cancellato. Manterrai l'accesso fino alla fine del periodo corrente.")
            return redirect("accounts:subscription_cancelled")  # Adatta al tuo URL

        # ✅ 2. Cambio Piano
        elif new_plan in PLAN_LEVELS:
            old_plan = current_plan
            profile.plan = new_plan
            profile.plan_changed_at = timezone.now()
            profile.plan_cancelled_at = None
            profile.save()

            if new_plan != old_plan:
                messages.success(request, f"✅ Piano aggiornato a {new_plan.title()}!")
            else:
                messages.info(request, "ℹ️ Il piano selezionato è già attivo.")

            return redirect("families:setup")  # O dove preferisci
        else:
            messages.error(request, "❌ Piano non valido.")

    # ✅ 3. Costruzione dinamica dei piani (nessun dato hardcoded)
    plans = []
    for plan_id, level in sorted(PLAN_LEVELS.items(), key=lambda x: x[1]):
        plans.append({
            "id": plan_id,
            "name": plan_id.title(),
            "level": level,
            "features": PLAN_FEATURES.get(plan_id, {}),
            "is_current": current_plan == plan_id,
            'is_upgrade': (level > PLAN_LEVELS.get(current_plan, 1)),
            'is_downgrade': (level < PLAN_LEVELS.get(current_plan, 1)),
            "recommended": plan_id == "pro"
        })
    # Ordina per livello (starter -> pro -> enterprise)
    plans.sort(key=lambda x: x['level'])

    context = {
        'current_plan': current_plan,
        'plans': plans,
    }

    return render(request, "core/change_plan.html", context)