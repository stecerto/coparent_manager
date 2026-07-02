# accounts/views.py
import logging
from urllib.parse import unquote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django_ratelimit.decorators import ratelimit

from accounts.forms import RegisterForm, UserForm, UserProfileForm
from accounts.models import UserProfile
from accounts.services import email_service
from accounts.services.email_service import send_activation_email
from config import settings
from core.choices import RoleChoices  # ✅ Importa le choices
from families.models import Family
from families.models import FamilyMember, Invitation



User = get_user_model()
logger = logging.getLogger(__name__)


def redirect_after_login(request):
    profile = request.user.userprofile
    if profile.role in RoleChoices.lawyer_roles():
        return redirect('lawyer_home')
    return redirect('home')


# =========================
# REGISTRAZIONE
# =========================

def register_view(request):
    # 1. Recupera invito dalla sessione
    invitation = None
    invitation_id = request.session.get("invitation_id")
    invite_token = request.session.get("pending_invite_token")

    # ✅ NUOVO: Leggi anche dalla URL (se passato come parametro)
    url_token = request.GET.get("invite_token")
    if url_token:
        invite_token = url_token
        request.session['pending_invite_token'] = url_token  # Salva in sessione

    if invite_token:
        invitation = Invitation.objects.filter(token=invite_token, status="pending").first()
        if invitation:
            invitation_id = invitation.id

    if invitation_id and not invitation:
        invitation = Invitation.objects.filter(id=invitation_id, status="pending").first()

    # 2. Parametri URL (pricing page)
    role_from_url = request.GET.get("role", "").strip().lower()
    plan_from_url = request.GET.get("plan", "").strip().lower()

    if plan_from_url:
        request.session["registration_plan"] = plan_from_url

    # 3. Pre-compila il form
    initial_data = {}

    if invitation:
        # Email dall'invito
        initial_data["email"] = invitation.email
        base_role = invitation.role.replace('_a', '').replace('_b', '')
        initial_data["role"] = base_role
    elif role_from_url in ["parent", "lawyer", "mediator", "consultant"]:
        initial_data["role"] = role_from_url

    # ✅ MIGLIORATO: Gestione piano con fallback più chiaro
    if plan_from_url in ["starter", "pro", "enterprise"]:
        initial_data["plan"] = plan_from_url
    elif request.session.get("registration_plan") in ["starter", "pro", "enterprise"]:
        initial_data["plan"] = request.session.get("registration_plan")
    else:
        # Default: Pro per professionisti, Starter per genitori
        if initial_data.get("role") in ["lawyer", "mediator", "consultant"]:
            initial_data["plan"] = "pro"
        else:
            initial_data["plan"] = "starter"

    form = RegisterForm(request.POST or None, initial=initial_data)

    # 4. Gestione POST (registrazione)
    if request.method == "POST" and form.is_valid():
        # Controllo privacy
        if not request.POST.get("privacy_accept"):
            messages.error(request, "Devi accettare la Privacy Policy per registrarti.")
            return render(request, "accounts/register.html", {"form": form})

        # Crea utente
        # ✅ CONTROLLO: Email già esistente ma account inattivo?
        existing_user = User.objects.filter(email=form.cleaned_data["email"], is_active=False).first()

        if existing_user:
            # Account inattivo trovato: reinvia email di attivazione
            logger.info(f"🔄 Reinvio attivazione per email esistente inattiva: {existing_user.email}")

            # Aggiorna password se diversa
            existing_user.set_password(form.cleaned_data['password1'])
            existing_user.first_name = form.cleaned_data.get('first_name', existing_user.first_name)
            existing_user.last_name = form.cleaned_data.get('last_name', existing_user.last_name)
            existing_user.save()

            # Aggiorna profilo se necessario
            profile, _ = UserProfile.objects.get_or_create(user=existing_user)
            profile.role = form.cleaned_data.get("role", profile.role)
            profile.save()

            # Reinvia email di attivazione
            send_activation_email(request, existing_user)

            messages.success(
                request,
                f"📧 Abbiamo trovato un account non attivato con questa email. "
                f"Ti abbiamo inviato un nuovo link di attivazione!"
            )

            return render(request, "accounts/confirm_email.html", {
                "email": existing_user.email,
                "invitation": invitation,
                "reactivated": True,
            })

        # Email esistente ma account ATTIVO → errore
        if User.objects.filter(email=form.cleaned_data["email"], is_active=True).exists():
            messages.error(
                request,
                "❌ Esiste già un account attivo con questa email. Effettua il login o recupera la password."
            )
            return render(request, "accounts/register.html", {"form": form})

        # Crea nuovo utente
        user = form.save(commit=False)
        user.is_active = False  # Attivazione via email
        user.save()

        # Recupera profilo
        profile, _ = UserProfile.objects.get_or_create(user=user)

        # ✅ GESTIONE RUOLO: Usa SEMPRE il ruolo generico
        form_role = form.cleaned_data.get("role", "parent")
        profile.role = form_role  # Es: 'parent', 'lawyer', 'mediator', 'consultant'

        # ✅ GESTIONE PIANO
        plan_from_form = form.cleaned_data.get("plan")
        plan_from_session = request.session.get("registration_plan", "")

        # Priorità: form > sessione > default
        if plan_from_form:
            plan_to_save = plan_from_form
        elif plan_from_session:
            plan_to_save = plan_from_session
        else:
            # Default in base al ruolo
            plan_to_save = "pro" if form_role in ["lawyer", "mediator", "consultant"] else "starter"

        # Salva il piano
        profile.plan = plan_to_save

        # Dati privacy
        profile.privacy_accepted_at = timezone.now()
        profile.privacy_version_accepted = getattr(settings, 'PRIVACY_VERSION', '1.0')

        profile.save()
        logger.info(f"💰 Piano scelto da {user.email}: {plan_to_save}")

        # Accetta invito (se presente)
        if invitation:
            #accept_invitation(invitation, user)
            logger.info(f"📧 Invito {invitation.id} in attesa di attivazione account per {user.email}")
            messages.info(request,
                          "📧 Riceverai un'email per attivare il tuo account. Dopo l'attivazione, sarai automaticamente aggiunto alla famiglia.")
            request.session.pop("invitation_id", None)
            request.session.pop("pending_invite_token", None)

        # Messaggio di successo
        if form_role in ["lawyer", "mediator", "consultant"]:
            messages.success(
                request,
                f"✅ Registrazione completata! Completa il setup del tuo profilo professionale."
            )
        else:
            messages.success(
                request,
                f"✅ Registrazione completata! Attiva il tuo account cliccando sul link nell'email."
            )

        # Email di attivazione
          # Assicurati che l'import sia corretto per il tuo progetto
        send_activation_email(request, user)
        # ✅ Reindirizza al login con un messaggio chiaro, senza pagina intermedia inutile
        messages.success(
            request,
            "✅ Registrazione completata! Controlla la tua email e clicca sul link per attivare l'account."
        )
        # ✅ NUOVO: Renderizza la pagina di conferma invece di fare redirect
        context = {
            "email": user.email,
            "invitation": invitation,  # Lo teniamo nel contesto nel caso il template ne avesse bisogno in futuro
        }

        return render(request, "accounts/confirm_email.html", context)

    # 5. Renderizza form (GET)
    return render(request, "accounts/register.html", {
        "form": form,
        "invitation": invitation,
        "selected_plan": plan_from_url or request.session.get("registration_plan", "starter"),
    })


# =========================
# ATTIVAZIONE ACCOUNT
# =========================
# accounts/views.py
from django.utils import timezone  # ← Assicurati che questo import sia in alto nel file


def activate_account(request):
    # =========================
    # 1. RECUPERO PARAMETRI LINK
    # =========================
    uidb64 = unquote(request.GET.get("uidb64", "")).strip()
    token = unquote(request.GET.get("token", "")).strip()

    if not uidb64 or not token:
        logger.warning("⚠️ Attivazione: parametri mancanti")
        return render(request, "accounts/activation_invalid.html")

    # =========================
    # 2. DECODIFICA USER ID
    # =========================
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
    except (TypeError, ValueError, OverflowError) as e:
        logger.error(f"❌ Errore decodifica UID: {e}")
        try:
            import base64
            padded = uidb64 + "=" * (4 - len(uidb64) % 4)
            uid = force_str(base64.urlsafe_b64decode(padded))
        except Exception:
            return render(request, "accounts/activation_invalid.html", {
                "error": "Link di attivazione non valido"
            })

    # =========================
    # 3. TROVA UTENTE
    # =========================
    user = User.objects.filter(pk=uid).first()
    if not user:
        logger.warning(f"⚠️ Utente con pk={uid} non trovato")
        return render(request, "accounts/activation_invalid.html")

    # =========================
    # 4. SE GIA ATTIVO → LOGIN PAGE
    # =========================
    if user.is_active:
        messages.info(request, "Il tuo account è già attivo. Effettua il login.")
        return redirect("accounts:login")

    # =========================
    # 5. VALIDAZIONE TOKEN E ATTIVA UTENTE
    # =========================
    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        #login(request, user)
        messages.success(request, "✅ Account attivato! Benvenuto.")

        # =========================
        # 6. RECUPERA PROFILO
        # =========================
        profile = getattr(user, 'userprofile', None)
        role = profile.role if profile else "parent_a"

        # =========================
        # 7. ✅ INTEGRAZIONE PRICING: Applica role/plan da sessione
        # =========================
       # saved_role = request.session.pop("registration_role", None)
        saved_plan = request.session.pop("registration_plan", None)



        if saved_plan and hasattr(profile, "plan"):
            profile.plan = saved_plan
            profile.plan_started_at = timezone.now()
            profile.save()

            # =========================
            # 8. SALVA TOKEN INVITO IN SESSIONE (per il segnale)
            # =========================
            # Il segnale user_activated (in families/signal_handlers.py) si occuperà di:
            # - Accettare eventuali inviti pendenti
            # - Creare la famiglia per i genitori senza inviti

            pending_token = request.session.get("pending_invite_token")
            if pending_token:
                logger.info(
                    f"📡 Token invito {pending_token} in sessione per {user.email}. Il segnale gestirà l'accettazione.")

            # Messaggio generico (il segnale farà il lavoro pesante)
            messages.success(request, "✅ Account attivato! Stiamo configurando il tuo profilo...")

        # =========================
        # 10. REDIRECT INTELLIGENTE
        # =========================
        messages.success(request, "✅ Account attivato con successo! Ora puoi effettuare il login.")
        return redirect("accounts:login")

    logger.warning(f"⚠️ Token non valido per utente {user.pk}")
    return render(request, "accounts/activation_invalid.html", {
        "error": "Link di attivazione non valido o scaduto."
    })

#🔐 DIRITTO ALL'OBLIO (GDPR Art. 17)
@login_required
def delete_account(request):
    """Cancellazione completa account - Diritto all'oblio GDPR"""
    if request.method == 'POST':
        user = request.user

        # 1. Rimuovi da tutte le famiglie
        user.family_memberships.all().delete()

        # 2. Elimina profilo utente
        if hasattr(user, 'profile'):
            user.profile.delete()

        # 3. Elimina notifiche
        user.notifications.all().delete()

        # 4. Elimina documenti caricati dall'utente
        user.documents.all().delete()

        # 5. Elimina messaggi inviati
        user.sent_messages.all().delete()

        # 6. Anonimizza dati rimanenti (spese, eventi)
        # Non eliminare per mantenere integrità dati famiglia
        user.expenses.update(uploaded_by=None)
        user.calendar_events.update(created_by=None)

        # 7. Elimina utente
        user.delete()

        messages.success(request, "Il tuo account è stato eliminato permanentemente.")
        return redirect('landing')

    return render(request, 'accounts/delete_account_confirm.html')

# =========================
# LOGIN
# =========================

# accounts/views.py

from django_ratelimit.decorators import ratelimit


@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def login_view(request):
    """
    View login con gestione completa:
    - Rate limiting (10 tentativi/minuto per IP)
    - Gestione account inattivi
    - Accettazione inviti pendenti
    - Controllo stato abbonamento
    - Redirect intelligente per ruolo
    """

    # ✅ Cattura parametri dalla URL (pricing page)
    url_token = request.GET.get("invite_token")
    if url_token:
        request.session['pending_invite_token'] = url_token

    role_from_url = request.GET.get("role", "").strip().lower()
    plan_from_url = request.GET.get("plan", "").strip().lower()

    if plan_from_url:
        request.session["registration_plan"] = plan_from_url
    if role_from_url and role_from_url in ["parent", "lawyer", "mediator", "consultant"]:
        request.session["registration_role"] = role_from_url

    # ✅ GET: Mostra form
    if request.method != "POST":
        form = AuthenticationForm()
        context = {
            "form": form,
            "failed_attempts": request.session.get('failed_login_attempts', 0)
        }
        return render(request, "accounts/login.html", context)

    # ✅ POST: Processa login
    form = AuthenticationForm(request, data=request.POST)

    # ❌ Login fallito
    if not form.is_valid():
        email = request.POST.get("username", "").strip()
        user = User.objects.filter(email=email).first()

        # Caso 1: Utente esiste ma non attivo
        if user and not user.is_active:
            request.session['inactive_user_email'] = user.email
            messages.warning(
                request,
                "⚠️ Il tuo account non è attivo. Controlla la tua email o richiedi nuovo link."
            )
            return redirect('accounts:account_inactive')

        # Caso 2: Credenziali sbagliate
        attempts = request.session.get('failed_login_attempts', 0) + 1
        request.session['failed_login_attempts'] = attempts
        messages.error(request, "Credenziali non valide. Riprova.")

        context = {
            "form": form,
            "failed_attempts": attempts
        }
        return render(request, "accounts/login.html", context)

    # ✅ Login riuscito
    user = form.get_user()
    login(request, user)

    # Resetta contatore tentativi falliti
    if 'failed_login_attempts' in request.session:
        del request.session['failed_login_attempts']

    # ✅ GESTIONE INVITO PENDENTE (priorità massima)
    pending_token = request.session.pop("pending_invite_token", None)
    if pending_token:
        from families.models import Invitation
        from families.services.invitation_service import accept_invitation

        try:
            invitation = Invitation.objects.select_related('family').get(
                token=pending_token,
                status="pending"
            )

            accept_invitation(invitation, user)

            if invitation.family:
                messages.success(
                    request,
                    f"✅ Sei stato aggiunto a '{invitation.family.name}' come {invitation.get_role_display()}"
                )
            else:
                messages.success(request, "✅ Invito accettato! La tua famiglia è stata creata.")

            # Redirect in base al ruolo
            profile = getattr(user, 'profile', None)
            if profile and profile.role in ['lawyer', 'mediator', 'consultant']:
                return redirect('lawyer_home')
            return redirect('home')

        except Invitation.DoesNotExist:
            messages.warning(request, "⚠️ Invito non valido o già utilizzato")
        except Exception as e:
            logger.error(f"Errore accettazione invito {pending_token}: {e}")
            messages.error(request, "⚠️ Si è verificato un errore tecnico. Contatta il supporto.")

    # ✅ CONTROLLO PROFILO
    profile = getattr(user, 'profile', None)
    if not profile:
        return redirect('families:setup')

    # ✅ APPLICA RUOLO/PIANO DA SESSIONE (se profilo incompleto)
    saved_role = request.session.pop("registration_role", None)
    saved_plan = request.session.pop("registration_plan", None)

    if saved_role and not profile.role:
        role_map = {
            "parent": "parent_a",
            "lawyer": "lawyer_a",
            "mediator": "mediator",
            "consultant": "consultant",
        }
        profile.role = role_map.get(saved_role, "parent_a")

    if saved_plan and hasattr(profile, "plan"):
        profile.plan = saved_plan
        profile.plan_started_at = timezone.now()
        profile.save()

    # ✅ REDIRECT IN BASE AL RUOLO
    # Professionisti
    if profile.role in ['lawyer', 'mediator', 'consultant']:
        if profile.setup_complete:
            return redirect('lawyer_home')
        return redirect('families:summary')

    # Genitori
    if not profile.setup_complete:
        return redirect('families:summary')

    # ✅ Tutto ok → home
    return redirect('home')


# =========================
# IMPOSTAZIONI PROFILO (CON PROTEZIONE CAMPI BLOCCATI)
# =========================
@login_required
def profile_settings_view(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        user_form = UserForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, instance=profile, role=profile.role)

        if user_form.is_valid() and profile_form.is_valid():
            # 🔐 PROTEZIONE ANTI-MANOMISSIONE: rimuovi campi bloccati dai dati validati
            user_data = user_form.cleaned_data.copy()
            profile_data = profile_form.cleaned_data.copy()

            # Se il profilo esiste già → ignora tentativi di modifica dei campi bloccati
            if user.pk:
                for field in ["first_name", "last_name", "email"]:
                    user_data.pop(field, None)
            if profile.pk and 'phone' in profile_data:
                profile_data.pop('phone', None)

            # Salva SOLO i campi rimanenti
            with transaction.atomic():
                if user_data:
                    User.objects.filter(pk=user.pk).update(**user_data)
                if profile_data:
                    UserProfile.objects.filter(pk=profile.pk).update(**profile_data)

            messages.success(request, "✅ Profilo aggiornato")
            return redirect("accounts:settings")
    else:
        user_form = UserForm(instance=user)
        profile_form = UserProfileForm(instance=profile, role=profile.role)

    return render(request, "accounts/settings.html", {
        "form_user": user_form,
        "form_profile": profile_form,
    })


# =========================
# RESEND ACTIVATION
# =========================
def resend_activation(request):
    """
    View per richiedere un nuovo link di attivazione.
    ✅ Cerca PRIMA tra gli utenti inattivi, POI tra gli inviti pendenti.
    """
    if request.method != "POST":
        return render(request, "accounts/resend_activation.html")

    email = request.POST.get("email", "").strip().lower()

    # 🔍 1. Cerca utente inattivo (già registrato ma non attivato)
    user = User.objects.filter(email=email, is_active=False).first()

    if user:
        if send_activation_email(request, user, subject_prefix="Nuovo "):
            messages.success(request, "✅ Nuova email di attivazione inviata!")
        else:
            messages.success(
                request,
                "✅ Se l'email esiste ed è inattiva, riceverai un nuovo link di attivazione."
            )
        return redirect("accounts:login")

    # 🔍 2. Cerca invito pendente (utente non ancora registrato)
    from families.models import Invitation
    from families.services.email_service import send_invitation_email, build_invitation_context

    pending_invitation = Invitation.objects.filter(
        email=email,
        status="pending"
    ).select_related('family', 'invited_by').first()

    if pending_invitation:
        try:
            # Costruisci il contesto per l'email di invito
            email_context = build_invitation_context(
                pending_invitation,
                pending_invitation.invited_by,
                pending_invitation.invited_by.userprofile
            )

            # Reinvia l'email di invito
            send_invitation_email(
                request,
                pending_invitation,
                template="emails/invitation_email.html",
                context_extra=email_context
            )

            # Incrementa il contatore di reinvii
            pending_invitation.increment_resend()

            messages.success(
                request,
                f"✅ Nuovo invito reinviato per la famiglia '{pending_invitation.family.name}'!"
            )
            logger.info(f"✅ Reinvio invito per {email} (Invito ID={pending_invitation.id})")

        except Exception as e:
            logger.error(f"❌ Errore reinvio invito per {email}: {e}")
            messages.success(
                request,
                "✅ Se l'email è associata a un invito pendente, riceverai un nuovo link."
            )

        return redirect("accounts:login")

    # ⚠️ 3. Nessun utente inattivo né invito pendente trovato
    messages.success(
        request,
        "✅ Se l'email esiste ed è inattiva, riceverai un nuovo link di attivazione."
    )
    logger.warning(f"⚠️ Tentativo resend per email non trovata: {email}")

    return redirect("accounts:login")

import traceback
# =========================
# ACCOUNT INATTIVO (Reinvio Token)
# =========================
def account_inactive_view(request):
    """Pagina per utenti non attivati"""

    email = request.session.get('inactive_user_email') or request.GET.get('email', '')
    email = (email or '').strip().lower()

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()

        if not email:
            messages.error(request, "Inserisci una email valida.")
            return render(request, "accounts/account_inactive.html", {"email": email})

        user = User.objects.filter(email=email, is_active=False).first()

        if user:
            try:
                send_activation_email(request, user)

                messages.success(
                    request,
                    f"✅ Nuovo link di attivazione inviato a {email}!"
                )

                return render(request, "accounts/confirm_email.html", {
                    "email": email,
                    "reactivated": True,
                })

            except Exception as e:
                logger.error(f"Errore invio email attivazione: {e}")
                messages.error(request, "Errore invio email. Riprova più tardi.")
                logger.error(traceback.format_exc())
        else:
            messages.error(
                request,
                "❌ Nessun account inattivo trovato con questa email."
            )

    return render(request, "accounts/account_inactive.html", {
        "email": email,
    })

import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from accounts.utils import generate_cf


@login_required
@require_POST
def calculate_cf_api(request):
    try:
        data = json.loads(request.body)

        cf = generate_cf(
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            birth_date=data.get("birth_date"),
            birth_place_code=data.get("birth_place_code"),
            gender=data.get("gender"),
        )

        if not cf:
            return JsonResponse({"success": False, "message": "Dati incompleti"})

        return JsonResponse({"success": True, "cf": cf})

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


# =========================
# LOGOUT
# =========================
def logout_view(request):
    logout(request)
    return redirect("accounts:login")



from accounts.utils import load_comuni_json


def get_comune_name(code):
    """
    Ritorna il nome del comune dato il codice catastale
    """
    comuni = load_comuni_json()

    code = (code or "").upper().strip()

    for c in comuni:
        if c.get("codice_catastale", "").upper() == code:
            return c.get("nome", "")

    return ""




# accounts/views.py - SOSTITUISCI la funzione search_comuni_ajax

from django.http import JsonResponse
from django.views.decorators.http import require_GET
import json
import os
from django.conf import settings
from pathlib import Path

# accounts/views.py - SOSTITUISCI la funzione

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from accounts.utils import search_comuni


@require_GET
def search_comuni_ajax(request):
    """Endpoint AJAX per ricerca comuni (usato da Select2)"""
    query = request.GET.get('q', '').strip()

    logger.info(f"🔍 Ricerca comuni: query='{query}'")

    results = search_comuni(query, limit=50)

    logger.info(f"✅ Trovati {len(results)} risultati per '{query}'")

    return JsonResponse({'results': results})


# accounts/views.py - AGGIUNGI queste funzioni

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from accounts.forms import ComuneForm, ComuneImportForm
from accounts.models import Comune
import json


@staff_member_required
def comuni_admin_view(request):
    """
    Pagina di gestione comuni (solo per admin).
    Visualizza, aggiunge, modifica e rimuove comuni.
    """
    # Ricerca
    query = request.GET.get('q', '').strip()

    if query:
        comuni = Comune.objects.filter(
            models.Q(nome__icontains=query) |
            models.Q(codice_catastale__icontains=query) |
            models.Q(provincia__icontains=query)
        ).order_by('nome')
    else:
        # Paginazione
        from django.core.paginator import Paginator
        comuni_list = Comune.objects.all().order_by('nome')
        paginator = Paginator(comuni_list, 100)  # 100 per pagina
        page = request.GET.get('page')
        comuni = paginator.get_page(page)

    # Form per nuovo comune
    form = ComuneForm() if request.method != 'POST' else ComuneForm(request.POST)

    context = {
        'comuni': comuni,
        'form': form,
        'query': query,
        'total_comuni': Comune.objects.count(),
    }

    return render(request, 'accounts/comuni_admin.html', context)


@staff_member_required
def comune_add_view(request):
    """Aggiungi nuovo comune"""
    if request.method == 'POST':
        form = ComuneForm(request.POST)
        if form.is_valid():
            comune = form.save()
            messages.success(request, f"✅ Comune '{comune.nome}' aggiunto con successo!")
            return redirect('accounts:comuni_admin')
        else:
            messages.error(request, "⚠️ Correggi gli errori nel form")
    return redirect('accounts:comuni_admin')


@staff_member_required
def comune_edit_view(request, pk):
    """Modifica comune esistente"""
    comune = get_object_or_404(Comune, pk=pk)

    if request.method == 'POST':
        form = ComuneForm(request.POST, instance=comune)
        if form.is_valid():
            form.save()
            messages.success(request, f"✅ Comune '{comune.nome}' aggiornato con successo!")
            return redirect('accounts:comuni_admin')
        else:
            messages.error(request, "⚠️ Correggi gli errori nel form")
    else:
        form = ComuneForm(instance=comune)

    return render(request, 'accounts/comune_edit.html', {
        'form': form,
        'comune': comune
    })


@staff_member_required
def comune_delete_view(request, pk):
    """Elimina comune"""
    comune = get_object_or_404(Comune, pk=pk)

    if request.method == 'POST':
        nome = comune.nome
        comune.delete()
        messages.success(request, f"🗑️ Comune '{nome}' eliminato con successo!")
        return redirect('accounts:comuni_admin')

    return render(request, 'accounts/comune_confirm_delete.html', {
        'comune': comune
    })


# accounts/views.py

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.contrib import messages
from accounts.forms import ComuneForm, ComuneImportForm
from accounts.models import Comune
from django.db import transaction
import json
import logging

logger = logging.getLogger(__name__)


@staff_member_required
def comuni_import_view(request):
    """Importa comuni da file JSON ottimizzato per Render"""
    if request.method == 'POST':
        form = ComuneImportForm(request.POST, request.FILES)
        if form.is_valid():
            json_file = request.FILES['json_file']

            try:
                # ✅ Leggi il file JSON
                data = json.load(json_file)

                if not isinstance(data, list):
                    messages.error(request, "❌ Il file JSON deve contenere una lista di comuni")
                    return redirect('accounts:comuni_admin')

                logger.info(f"📂 Inizio importazione: {len(data)} record nel file")

                # ✅ Statistiche
                total = len(data)
                created = 0
                updated = 0
                skipped = 0
                errors = 0

                # ✅ Usa transazione per performance e rollback automatico
                with transaction.atomic():
                    # Pre-fetch tutti i codici esistenti per evitare query multiple
                    existing_codes = set(
                        Comune.objects.values_list('codice_catastale', flat=True)
                    )

                    # Prepara liste per bulk operations
                    comuni_to_create = []
                    comuni_to_update = []

                    for idx, item in enumerate(data, 1):
                        try:
                            nome = item.get('nome', '').strip()
                            codice = item.get('codice_catastale', '').strip().upper()
                            provincia = item.get('provincia', '').strip().upper()

                            # Validazione
                            if not nome or not codice:
                                skipped += 1
                                continue

                            if len(codice) != 4:
                                logger.warning(f"⚠️ Record {idx} saltato: codice non valido ({codice})")
                                skipped += 1
                                continue

                            # ✅ Controlla se esiste già
                            if codice in existing_codes:
                                # Aggiorna
                                comuni_to_update.append({
                                    'codice_catastale': codice,
                                    'nome': nome,
                                    'provincia': provincia
                                })
                                updated += 1
                            else:
                                # Crea
                                comuni_to_create.append(
                                    Comune(
                                        nome=nome,
                                        codice_catastale=codice,
                                        provincia=provincia
                                    )
                                )
                                created += 1

                            # ✅ Progress logging ogni 1000 record
                            if idx % 1000 == 0:
                                logger.info(f"  ... processati {idx}/{total} record")

                        except Exception as e:
                            logger.error(f"❌ Errore record {idx}: {e}")
                            errors += 1

                    # ✅ Bulk create (molto più veloce di update_or_create)
                    if comuni_to_create:
                        logger.info(f"📝 Creazione di {len(comuni_to_create)} nuovi comuni...")
                        Comune.objects.bulk_create(
                            comuni_to_create,
                            ignore_conflicts=True,
                            batch_size=1000
                        )

                    # ✅ Bulk update
                    if comuni_to_update:
                        logger.info(f"📝 Aggiornamento di {len(comuni_to_update)} comuni esistenti...")
                        for comune_data in comuni_to_update:
                            Comune.objects.filter(
                                codice_catastale=comune_data['codice_catastale']
                            ).update(
                                nome=comune_data['nome'],
                                provincia=comune_data['provincia']
                            )

                # ✅ Report finale
                total_in_db = Comune.objects.count()

                logger.info("=" * 60)
                logger.info("📊 REPORT IMPORTAZIONE")
                logger.info("=" * 60)
                logger.info(f"✅ Totale record nel JSON: {total}")
                logger.info(f"✅ Nuovi comuni creati:    {created}")
                logger.info(f"✅ Comuni aggiornati:      {updated}")
                logger.info(f"⚠️  Record saltati:         {skipped}")
                logger.info(f"❌ Errori:                  {errors}")
                logger.info(f"✅ Totale comuni nel DB:   {total_in_db}")
                logger.info("=" * 60)

                # Messaggio di successo dettagliato
                messages.success(
                    request,
                    f"✅ Import completato! "
                    f"Creati: {created} | Aggiornati: {updated} | "
                    f"Saltati: {skipped} | Errori: {errors} | "
                    f"Totale nel DB: {total_in_db}"
                )

                # ✅ Verifica comuni noti
                test_comuni = ['H501', 'F205', 'F839', 'L219', 'A662', 'G273']
                missing = []
                for codice in test_comuni:
                    if not Comune.objects.filter(codice_catastale=codice).exists():
                        missing.append(codice)

                if missing:
                    logger.warning(f"⚠️ Comuni noti mancanti: {missing}")
                    messages.warning(
                        request,
                        f"⚠️ Alcuni comuni noti non sono stati importati: {', '.join(missing)}"
                    )
                else:
                    logger.info("✅ Tutti i comuni noti presenti")

            except json.JSONDecodeError as e:
                logger.error(f"❌ File JSON non valido: {e}")
                messages.error(request, f"❌ File JSON non valido: {e}")
            except Exception as e:
                logger.error(f"❌ Errore durante l'import: {e}", exc_info=True)
                messages.error(request, f"❌ Errore durante l'import: {e}")

        return redirect('accounts:comuni_admin')

    form = ComuneImportForm()
    return render(request, 'accounts/comuni_import.html', {'form': form})

