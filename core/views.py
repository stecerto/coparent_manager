from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils import timezone
from accounts.decorators import confirmed_required, first_login_required
from core.choices import RoleChoices
from core.plans import PLAN_LEVELS, PLAN_FEATURES
from core.pricing import get_plan_price, get_plan_currency, format_price
from core.pricing import get_role_plan_data
from families.models import PaymentSubscription


@login_required
def home(request):
    """Home page: mostra dashboard in base al ruolo dell'utente."""
    user = request.user
    profile = getattr(user, 'userprofile', None) or getattr(user, 'profile', None)

    if not profile:
        return redirect('families:setup')

    role_raw = getattr(profile, 'role', None)
    if not role_raw:
        return redirect('families:setup')

    role_str = str(role_raw).strip().lower()
    role_base = role_str.replace('_a', '').replace('_b', '')

    # ✅ PROFESSIONISTI → mostra home specifica
    if role_base in ['lawyer', 'mediator', 'consultant']:
        if not getattr(profile, 'setup_complete', False):
            return redirect('families:setup')

        # Renderizza la home per professionisti
        from families.models import FamilyMember
        memberships = FamilyMember.objects.filter(
            user=user,
            role__in=['lawyer_a', 'lawyer_b', 'mediator', 'consultant']
        ).select_related('family')

        context = {
            'profile': profile,
            'memberships': memberships,
            'total_families': memberships.count(),
            'role_label': profile.get_role_display() if hasattr(profile, 'get_role_display') else role_base.title(),
        }
        return render(request, 'core/lawyer_home.html', context)

    # ✅ GENITORI → mostra home specifica
    elif role_base in ['parent']:
        if not getattr(profile, 'setup_complete', False):
            return redirect('families:setup')

        # Renderizza la home per genitori
        from families.utils import get_family_of_user
        family = get_family_of_user(user, request=request)

        context = {
            'profile': profile,
            'family': family,
            'role_label': 'Genitore',
        }
        return render(request, 'core/home.html', context)

    # ✅ FALLBACK
    return redirect('families:setup')




@login_required
def lawyer_home_view(request):
    # 🔒 Sicurezza: solo avvocati possono accedere
    profile = getattr(request.user, 'profile', None)
    if not profile.is_professional:
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
    """Permette all'utente di cambiare piano con gestione scadenze"""
    subscription, created = PaymentSubscription.objects.get_or_create(
        user=request.user,
        defaults={
            'current_plan': 'starter',
            'status': 'active',
            'subscription_start': timezone.now(),
            'subscription_end': timezone.now() + timedelta(days=30),
        }
    )

    current_plan = subscription.current_plan

    # ✅ Determina il ruolo dell'utente
    user_role = 'parent'
    if hasattr(request.user, 'profile') and request.user.profile:
        user_role = str(request.user.profile.role).lower().replace('_a', '').replace('_b', '')

    if request.method == "POST":
        new_plan = request.POST.get("plan")
        action = request.POST.get("action")

        if action == "cancel":
            subscription.status = "cancelled"
            subscription.save()
            messages.warning(request,
                             "⚠️ Abbonamento cancellato. Manterrai l'accesso fino alla fine del periodo corrente.")
            return redirect("accounts:subscription_cancelled")

        elif new_plan in PLAN_LEVELS:
            old_plan = current_plan

            if new_plan != old_plan:
                if subscription.subscription_end > timezone.now():
                    subscription.pending_plan = new_plan
                    subscription.pending_plan_start = subscription.subscription_end
                    subscription.save()
                    messages.success(request,
                                     f"✅ Piano '{new_plan.title()}' pianificato. Il cambio avverrà il {subscription.subscription_end.strftime('%d/%m/%Y')}.")
                else:
                    subscription.pending_plan = new_plan
                    subscription.save()
                    messages.info(request,
                                  f"ℹ️ Piano '{new_plan.title()}' selezionato. Procedi al pagamento per attivarlo.")
                    return redirect('payment')
            else:
                messages.info(request, "ℹ️ Il piano selezionato è già attivo.")

            return redirect("families:setup")
        else:
            messages.error(request, "❌ Piano non valido.")

    # ✅ Usa get_role_plan_data per ottenere piani con features specifiche
    plans = get_role_plan_data(user_role)

    # Marca il piano attuale
    for plan in plans:
        plan['is_current'] = (plan['id'] == current_plan)
        plan['is_upgrade'] = PLAN_LEVELS.get(plan['id'], 1) > PLAN_LEVELS.get(current_plan, 1)
        plan['is_downgrade'] = PLAN_LEVELS.get(plan['id'], 1) < PLAN_LEVELS.get(current_plan, 1)

    days_remaining = None
    if subscription.subscription_end:
        delta = subscription.subscription_end - timezone.now()
        days_remaining = max(0, delta.days)

    context = {
        'current_plan': current_plan,
        'plans': plans,
        'days_remaining': days_remaining,
        'subscription': subscription,
        'is_expired': subscription.is_expired,
        'is_in_grace_period': subscription.is_in_grace_period,
        'pending_plan': subscription.pending_plan,
        'pending_plan_start': subscription.pending_plan_start,
    }

    return render(request, "core/change_plan.html", context)


def pricing_view(request):
    """Mostra la pagina dei prezzi con piani specifici per ogni ruolo"""
    # Determina il ruolo dell'utente (per marcare il piano attuale)
    user_role = 'parent'
    current_plan = 'starter'

    if hasattr(request.user, 'profile') and request.user.profile:
        user_role = str(request.user.profile.role).lower().replace('_a', '').replace('_b', '')
        current_plan = request.user.profile.plan or 'starter'

    # ✅ Calcola i piani per TUTTI i ruoli
    plans_by_role = {
        'parent': get_role_plan_data('parent'),
        'lawyer': get_role_plan_data('lawyer'),
        'mediator': get_role_plan_data('mediator'),
        'consultant': get_role_plan_data('consultant'),
    }

    # ✅ Marca quale piano è quello attuale per ogni ruolo
    for role_plans in plans_by_role.values():
        for plan in role_plans:
            plan['is_current'] = (plan['id'] == current_plan)

    return render(request, "core/pricing.html", {
        "user_role": user_role,
        "plans_by_role": plans_by_role,
        "current_plan": current_plan,
    })


@login_required
@transaction.atomic
def payment_page(request):
    """Gestisce il riepilogo e la conferma del pagamento/cambio piano"""
    profile = request.user.profile
    requested_plan = request.GET.get('plan')

    # 1. Se l'utente ha cliccato su un nuovo piano dalla URL
    if requested_plan and requested_plan in ['starter', 'pro', 'enterprise']:
        if requested_plan != profile.plan:
            profile.pending_plan = requested_plan

            # Se è un piano gratuito/scaduto, cambio immediato. Altrimenti alla scadenza.
            if profile.plan == 'starter' or (profile.plan_expires_at and profile.plan_expires_at <= timezone.now()):
                profile.pending_plan_start = timezone.now()
            else:
                profile.pending_plan_start = profile.plan_expires_at

            profile.save()

    # 2. Determina quale piano stiamo per attivare/pagare
    plan_to_process = profile.pending_plan or profile.plan

    # ✅ USA IL RUOLO DELL'UTENTE PER PRENDERE IL PREZZO GIUSTO!
    user_role = profile.role if hasattr(profile, 'role') else 'parent'
    amount = get_plan_price(user_role, plan_to_process)
    currency = get_plan_currency(user_role)

    # 3. Determina se il cambio è immediato o programmato
    is_immediate = (
                profile.plan == 'starter' or not profile.plan_expires_at or profile.plan_expires_at <= timezone.now())

    if request.method == "POST":
        # ✅ CONFERMA PAGAMENTO / MODIFICA

        if is_immediate:
            profile.plan = plan_to_process
            profile.pending_plan = None
            profile.pending_plan_start = None
            profile.plan_started_at = timezone.now()
            profile.plan_expires_at = timezone.now() + timedelta(days=30)
            profile.next_payment_date = profile.plan_expires_at
            profile.payment_status = "active"
            profile.last_payment_date = timezone.now()
            profile.save()

            # Registra il pagamento (decommenta se hai il modello Payment pronto)
            # Payment.objects.create(
            #     user=profile.user,
            #     amount=amount,
            #     currency=currency,
            #     status='completed',
            #     payment_method='manual',
            #     transaction_id=f"TXN_{int(timezone.now().timestamp())}"
            # )

            messages.success(
                request,
                f"✅ Piano {plan_to_process.title()} attivato con successo! Scadenza: {profile.plan_expires_at.strftime('%d/%m/%Y')}."
            )
        else:
            profile.save()

            # ✅ FIX: Gestione sicura della data per evitare AttributeError e errori di formattazione
            if profile.pending_plan_start:
                date_str = profile.pending_plan_start.strftime('%d/%m/%Y')
                success_msg = (
                    f"✅ Modifica salvata! Il tuo piano passerà a {plan_to_process.title()} il {date_str}. "
                    f"Verrai addebitato di {format_price(amount, currency)} a quella data."
                )
            else:
                success_msg = (
                    f"✅ Modifica salvata! Il tuo piano passerà a {plan_to_process.title()} immediatamente. "
                    f"Verrai addebitato di {format_price(amount, currency)} a breve."
                )

            messages.success(request, success_msg)

        return redirect('families:setup')  # O dove preferisci

    # 4. Preparazione del contesto per il template (GET)
    days_remaining = profile.days_until_expiration

    context = {
        'profile': profile,
        'plan_to_process': plan_to_process,
        'amount': amount,
        'amount_formatted': format_price(amount, currency),
        'currency': currency,
        'days_remaining': days_remaining,
        'is_immediate': is_immediate,
        'change_date': profile.pending_plan_start.strftime('%d/%m/%Y') if profile.pending_plan_start else None,
    }

    return render(request, 'core/payment.html', context)