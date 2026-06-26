# chat/views.py
# chat/views.py
import json
import logging
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q

from children.models import ChildProfile
from core.decorators import plan_required
from chat.services.message_service import delete_message, send_message
from .models import FamilyMessage, ProfessionalAttachment

from families.models import FamilyMember
from families.utils import get_family_of_user
from core.choices import RoleChoices
from expenses.models import Expense
from documents.models import Document

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
def family_chat_view(request, family_id=None, user_id=None):
    """
    View principale per la chat familiare.
    Gestisce chat di gruppo (famiglia) e chat private (1-a-1).

    Funzionalità:
    - Chat famiglia (gruppo) - solo lettura per professionisti
    - Chat private (1-a-1) tra genitori e professionisti
    - Chat di gruppo (mediazione, consulenza) per genitori
    - Invio messaggi con allegati
    - Creazione eventi dal chat
    - Rifiuto spese con contesto
    - Ricerca nei messaggi
    """
    user = request.user

    # ============================================
    # 🎯 1. DETERMINA FAMIGLIA E MEMBERSHIP
    # ============================================

    # ✅ FIX: Leggi family_id dalla querystring (non dal path parameter)
    # Priorità: 1. Path parameter URL, 2. Querystring ?family_id=, 3. Sessione
    family_id_from_get = request.GET.get('family_id')
    if not family_id:
        family_id = family_id_from_get or request.session.get('active_family_id')

    if family_id:
        # ✅ FIX: Accetta TUTTI i ruoli validi (genitori + professionisti)
        membership = FamilyMember.objects.filter(
            user=user,
            family_id=family_id
        ).select_related('family', 'user__profile').first()

        if not membership:
            messages.error(request, "⚠️ Non hai accesso a questa chat")
            return redirect('families:professional_dashboard')

        family = membership.family
    else:
        family = get_family_of_user(user, request=request)
        if not family:
            return render(request, "chat/no_family.html")
        membership = FamilyMember.objects.filter(family=family, user=user).first()

    if not membership:
        return HttpResponseForbidden("Non hai accesso a questa famiglia")

    # ✅ Normalizza il ruolo dell'utente
    role_val = membership.role.value if hasattr(membership.role, 'value') else str(membership.role)
    role_base = str(role_val).strip().lower().replace('_a', '').replace('_b', '')

    # ✅ Determina se l'utente è un professionista
    is_professional = role_base in ['lawyer', 'mediator', 'consultant']

    # ============================================
    # 🔐 2. RECUPERA TUTTI I PROFESSIONISTI DELLA FAMIGLIA
    # ============================================

    professional_members = FamilyMember.objects.filter(
        family=family,
        role__in=[
            RoleChoices.LAWYER_A, RoleChoices.LAWYER_B,
            RoleChoices.MEDIATOR, RoleChoices.CONSULTANT
        ]
    ).select_related('user').exclude(user=user)

    available_professionals = []
    for prof_member in professional_members:
        prof_role = prof_member.role.value if hasattr(prof_member.role, 'value') else str(prof_member.role)

        if prof_role in ['lawyer_a', 'lawyer_b']:
            thread_type = f"legal_{prof_role.split('_')[1]}"
        elif prof_role == 'mediator':
            thread_type = 'mediation_private'
        elif prof_role == 'consultant':
            thread_type = 'consultant_private'
        else:
            continue

        available_professionals.append({
            'user': prof_member.user,
            'membership': prof_member,
            'role': prof_role,
            'role_label': prof_member.get_role_display() if hasattr(prof_member, 'get_role_display') else prof_role,
            'thread_type': thread_type,
            'name': prof_member.user.get_full_name() or prof_member.user.email,
        })

    # ============================================
    # 🔍 3. DETERMINA CON CHI STA CHATTANDO ORA
    # ============================================

    chat_with_id = request.GET.get('chat_with') or user_id
    private_with_user = None
    current_thread_type = None

    if chat_with_id:
        try:
            private_with_user = User.objects.get(id=chat_with_id)
            # Cerca il thread_type corretto per questo utente
            for prof in available_professionals:
                if prof['user'].id == private_with_user.id:
                    current_thread_type = prof['thread_type']
                    break
        except User.DoesNotExist:
            pass

    # ============================================
    # 🔍 4. RICERCA & CONTESTO RIFIUTO SPESA
    # ============================================

    search_query = request.GET.get("q", "").strip()
    reject_expense_id = request.GET.get("reject_expense_id")
    reject_context = None

    if reject_expense_id:
        expense = Expense.objects.filter(id=reject_expense_id, family=family, is_active=True).select_related(
            'created_by', 'category').first()
        if expense:
            reject_context = {
                "expense_id": expense.id,
                "amount": expense.amount,
                "category": expense.category.name if expense.category else "N/D",
                "date": expense.expense_date.strftime("%d/%m/%Y") if expense.expense_date else "-",
                "created_by": expense.created_by.display_name if hasattr(expense.created_by,
                                                                         'display_name') else expense.created_by.username,
                "description": expense.description,
                "status": expense.get_status_display() if hasattr(expense, 'get_status_display') else expense.status,
            }

    # ============================================
    # 📥 5. GESTIONE POST (INVIO MESSAGGI)
    # ============================================

    if request.method == "POST":
        logger.info("=" * 60)
        logger.info("📨 POST CHAT - INIZIO")

        raw_thread = request.POST.get("thread_type")
        legacy_chat_type = request.POST.get("chat_type")
        thread_type = raw_thread.strip() if raw_thread else (legacy_chat_type or "family")

        if thread_type == "private" and private_with_user:
            thread_type = 'legal_a' if role_val in ['parent_a', 'lawyer_a'] else 'legal_b'

        if not thread_type:
            thread_type = "family"

        # ✅ BLOCCO PROFESSIONISTI: Non possono scrivere nella chat famiglia
        if is_professional and thread_type == 'family':
            messages.error(request,
                           "⚠️ I professionisti non possono scrivere nella chat famiglia. Usa la chat privata con il tuo assistito.")
            return redirect(f"{request.path}?family_id={family.id}&thread=family")
        # ✅ MEDIATORE: Può scrivere SOLO nella chat mediazione (gruppo)
        if role_base == 'mediator' and thread_type not in ['mediation']:
            messages.error(request,
                           "⚠️ Come mediatore puoi comunicare solo nella chat di mediazione di gruppo.")
            return redirect(f"{request.path}?family_id={family.id}&thread=mediation")

        # 3. AVVOCATO: solo chat private con genitori (legal_a/legal_b)
        if role_base == 'lawyer' and thread_type not in ['legal_a', 'legal_b']:
            messages.error(request,
                           "⚠️ Come avvocato puoi comunicare solo nelle chat private con i tuoi assistiti.")
            return redirect(f"{request.path}?family_id={family.id}")

        # 4. CONSULENTE: chat private (consultant_private) O chat gruppo (consulting)
        if role_base == 'consultant' and thread_type not in ['consultant_private', 'consulting']:
            messages.error(request,
                           "⚠️ Come consulente puoi comunicare nelle chat private con gli assistiti o nella chat di consulenza.")
            return redirect(f"{request.path}?family_id={family.id}")

        content = request.POST.get("message", "").strip()
        reply_id = request.POST.get("reply_to")
        reply_message = FamilyMessage.objects.filter(id=reply_id, family=family).first() if reply_id else None
        files = request.FILES.getlist("attachments")

        if not content and not files:
            return redirect(request.path)

        # ✅ Verifica permessi thread
        from chat.services.permissions import get_accessible_threads_for_user
        allowed_threads = get_accessible_threads_for_user(user, family)

        if thread_type not in allowed_threads:
            return render(request, "chat/permission_denied.html", {
                "message": "Non hai i permessi per scrivere in questa chat specifica.",
                "safe_redirect": f"/chat/?family_id={family.id}"
            })

        # ✅ Determina il destinatario per chat private
        recipient = None
        if thread_type in ['legal_a', 'legal_b', 'consultant_private']:
            recipient_id = request.POST.get('recipient_id')
            if recipient_id:
                try:
                    recipient = User.objects.get(id=recipient_id)
                except User.DoesNotExist:
                    pass

        # ✅ Gestione creazione evento dal chat
        create_event_flag = (thread_type in [
            'family',
            'legal_a',
            'legal_b',
            'consultant_private',  # ✅ AGGIUNTO
            'mediation',  # ✅ AGGIUNTO (chat gruppo mediazione)
            'consulting',  # ✅ AGGIUNTO (chat gruppo consulenza)
        ]) and request.POST.get("create_event") == "on"

        event_data = None
        if create_event_flag:
            now = timezone.now()
            event_data = {
                "title": (request.POST.get("event_title") or content[:50]).strip(),
                "start_time": request.POST.get("event_start") or now,
                "end_time": request.POST.get("event_end") or now,
                "description": (request.POST.get("event_description") or content).strip(),
                "source": "chat",
                "linked_id": None,
                "children_ids": request.POST.getlist("event_children"),
            }
            # Rimuovi chiavi non volute
            for unwanted_key in ("amount", "expense_id", "category", "reject_expense_id",
                                 "chat_type", "message", "attachments", "reply_to", "create_event", "thread_type"):
                event_data.pop(unwanted_key, None)

        # ✅ Invia il messaggio
        msg = send_message(
            family=family,
            sender=user,
            content=content,
            recipient=recipient,
            files=files,
            create_calendar_event=create_event_flag,
            event_data=event_data,
            reply_to=reply_message,
            thread_type=thread_type
        )

        # ✅ Salva allegati come documenti privati (per chat private)
        if files and thread_type in ['legal_a', 'legal_b', 'mediation_private', 'consultant_private']:
            for f in files:
                Document.objects.create(
                    family=family, uploaded_by=user, owner=user,
                    file=f, title=f.name[:100], is_private=True
                )

        # ============================================
        # ✅ NOTIFICA PER CHAT PRIVATE
        # ============================================
        if thread_type in ['legal_a', 'legal_b', 'consultant_private'] and recipient:  # ✅ AGGIUNTO consultant_private
            try:
                from notifications.services import create_notification
                create_notification(
                    user=recipient,
                    notification_type="chat_private",
                    title=f"Nuovo messaggio da {user.first_name or user.email}",
                    message=content[:150] + ("..." if len(content) > 150 else ""),
                    target_url=f"/chat/?family_id={family.id}&thread={thread_type}&chat_with={user.id}",
                    target_model="FamilyMessage",
                    target_id=msg.id,
                    metadata={"sender_id": user.id, "family_id": family.id, "thread_type": thread_type}
                )
            except Exception as e:
                logger.error(f"Errore notifica: {e}", exc_info=True)

        # ✅ Redirect alla chat corretta
        # ============================================
        # ✅ REDIRECT ALLA CHAT CORRETTA
        # ============================================
        redirect_url = request.path
        if recipient:
            # Chat privata: mantieni thread e chat_with
            redirect_url += f"?family_id={family.id}&thread={thread_type}&chat_with={recipient.id}"
        elif thread_type != "family":
            # Chat di gruppo: mantieni solo thread
            redirect_url += f"?family_id={family.id}&thread={thread_type}"
        else:
            # Chat famiglia
            redirect_url += f"?family_id={family.id}&thread=family"

        return redirect(redirect_url)

    # ============================================
    # 📊 6. PREPARA I DATI PER LA UI (GET)
    # ============================================

    active_thread = request.GET.get("thread", "family")

    # ✅ Gestione del ritorno dall'app Expenses dopo aver creato una spesa
    new_expense_id = request.GET.get("new_expense_id")
    new_expense = None
    prefill_message = ""

    if new_expense_id:
        new_expense = Expense.objects.filter(id=new_expense_id, family=family, is_active=True).first()
        if new_expense:
            expense_desc = new_expense.description or "Nuova spesa"
            prefill_message = f"📎 Ho appena registrato una spesa: {expense_desc} (€ {new_expense.amount})"

    # ✅ Costruisci l'URL per il pulsante "Aggiungi Spesa"
    current_chat_path = request.get_full_path()
    add_expense_redirect_url = f"/expenses/add/?next={quote(current_chat_path)}"

    # ============================================
    # 📊 7. COSTRUZIONE SIDEBAR DINAMICA CON SEZIONI
    # ============================================

    available_chats = []
    base_url = request.path

    # ✅ SEZIONE 1: CHAT FAMIGLIA (solo lettura per professionisti)
    available_chats.append({
        "type": "family",
        "name": "💬 Chat Famiglia",
        "icon": "👨‍👩‍👧‍👦",
        "is_active": (active_thread == "family"),
        "url": f"{base_url}?thread=family",
        "is_private": False,
        "section": "family",  # ✅ Identifica la sezione
        "readonly": is_professional,  # ✅ Solo lettura per professionisti
    })

    # ============================================
    # 📊 SEZIONE 2: CHAT PRIVATE
    # ============================================

    # ✅ Professionisti con chat private: avvocato E consulente
    if role_base in ['lawyer', 'consultant']:
        parents = FamilyMember.objects.filter(
            family=family,
            role__in=[RoleChoices.PARENT_A, RoleChoices.PARENT_B, 'parent_a', 'parent_b', 'parent']
        ).select_related('user').exclude(user=user)

        for p in parents:
            # ✅ Determina il thread_type corretto
            if role_base == 'lawyer':
                thread_type = f"legal_{p.role.split('_')[1]}" if hasattr(p.role, 'split') else 'legal_a'
            elif role_base == 'consultant':
                thread_type = 'consultant_private'  # ✅ Consulente usa consultant_private
            else:
                thread_type = f"{role_base}_private"

            # ✅ Verifica se questa chat è attiva
            is_active = (active_thread == thread_type and private_with_user and private_with_user.id == p.user.id)

            # ✅ Costruisci il nome visualizzato
            parent_name = p.user.get_full_name() or p.user.email
            role_short = "Gen. A" if 'a' in str(p.role).lower() else "Gen. B" if 'b' in str(
                p.role).lower() else "Genitore"
            clean_name = f"{role_short}: {parent_name}"

            available_chats.append({
                "type": thread_type,
                "name": clean_name,
                "icon": "🔒",
                "is_active": is_active,
                "url": f"{base_url}?thread={thread_type}&chat_with={p.user.id}",
                "user_id": p.user.id,
                "is_private": True,
                "section": "private",
                "readonly": False,
            })

    else:
        # Genitori: chat private con i professionisti
        for prof in available_professionals:
            is_active = (active_thread == prof['thread_type'] and private_with_user and private_with_user.id == prof[
                'user'].id)
            icon = "⚖️" if 'lawyer' in prof['role'] else "🤝" if prof['role'] == 'mediator' else "💼"
            prefix = "Avv." if 'lawyer' in prof['role'] else "Med." if prof[
                                                                           'role'] == 'mediator' else "Cons." if 'consultant' in \
                                                                                                                 prof[
                                                                                                                     'role'] else "Prof."
            prof_name = prof['user'].first_name or prof['user'].email.split('@')[0]
            display_name = f"{prefix} {prof_name}"

            available_chats.append({
                "type": prof['thread_type'],
                "name": display_name,
                "icon": icon,
                "is_active": is_active,
                "url": f"{base_url}?thread={prof['thread_type']}&chat_with={prof['user'].id}",
                "user_id": prof['user'].id,
                "is_private": True,
                "section": "private",  # ✅ Sezione privata
                "readonly": False,  # ✅ Le chat private sono sempre scrivibili
            })

    # ✅ SEZIONE 3: CHAT DI GRUPPO (solo per genitori)
    if role_base in ['parent', 'mediator', 'consultant']:
        available_chats.append({
            "type": "mediation",
            "name": "🤝 Mediazione (Gruppo)",
            "icon": "🕊️",
            "is_active": (active_thread == "mediation"),
            "url": f"{base_url}?thread=mediation",
            "is_private": False,
            "section": "group",  # ✅ Sezione gruppo
            "readonly": False,
        })

    if role_base in ['parent', 'consultant']:
        available_chats.append({
            "type": "consulting",
            "name": "💼 Consulenza (Gruppo)",
            "icon": "💡",
            "is_active": (active_thread == "consulting"),
            "url": f"{base_url}?thread=consulting",
            "is_private": False,
            "section": "group",  # ✅ Sezione gruppo
            "readonly": False,
        })

    # ============================================
    # 📊 8. RECUPERA MESSAGGI VISIBILI
    # ============================================

    from chat.services.permissions import get_visible_messages
    all_visible_messages = get_visible_messages(user, family)

    if search_query:
        all_visible_messages = all_visible_messages.filter(content__icontains=search_query)

    # ============================================
    # 📊 FILTRA MESSAGGI IN BASE AL THREAD ATTIVO
    # ============================================

    if active_thread == "family":
        current_messages = all_visible_messages.filter(thread_type="family")

    elif active_thread in ["legal_a", "legal_b", "consultant_private"] and private_with_user:
        # ✅ AGGIUNTO consultant_private alla lista
        current_messages = all_visible_messages.filter(thread_type=active_thread).filter(
            Q(sender=user, recipient=private_with_user) |
            Q(sender=private_with_user, recipient=user) |
            Q(sender=user, recipient__isnull=True) |
            Q(sender=private_with_user, recipient__isnull=True)
        )

    elif active_thread in ["mediation", "consulting"]:
        # ✅ Chat di gruppo
        current_messages = all_visible_messages.filter(thread_type=active_thread)

    else:
        current_messages = all_visible_messages.filter(thread_type=active_thread)

    current_messages = current_messages.order_by("created_at").select_related("sender", "recipient", "reply_to")

    # ============================================
    # 📊 9. DATI AGGIUNTIVI (DOCUMENTI, SPESE, FIGLI)
    # ============================================

    user_field = "owner"
    shared_docs = Document.objects.filter(family=family, is_active=True, is_private=False).select_related(
        user_field).order_by("-created_at")[:10]
    private_docs = Document.objects.filter(family=family, is_active=True, is_private=True).select_related(
        user_field).order_by("-created_at")[:10]

    expenses = []
    if membership and membership.role in RoleChoices.lawyer_roles():
        expenses = Expense.objects.filter(family=family, is_active=True).select_related('created_by',
                                                                                        'category').order_by(
            '-expense_date')[:20]

    family_children = ChildProfile.objects.filter(family=family, is_active=True).order_by("surname", "name")

    # ============================================
    # 🎯 10. CONTESTO COMPLETO
    # ============================================

    # ✅ Determina se l'utente è un professionista nella chat di famiglia (solo lettura)
    is_professional_in_family_chat = is_professional and active_thread == 'family'

    context = {
        "family": family,
        "membership": membership,
        "family_children": family_children,
        "available_chats": available_chats,
        "available_professionals": available_professionals,
        "active_thread": active_thread,
        "current_messages": current_messages,
        "private_with_user": private_with_user,
        "current_thread_type": current_thread_type,
        "search_query": search_query,
        "shared_docs": shared_docs,
        "private_docs": private_docs,
        "reject_context": reject_context,
        "expenses": expenses,
        # ✅ NUOVI: Per il flusso Expenses -> Chat
        "new_expense": new_expense,
        "prefill_message": prefill_message,
        "add_expense_redirect_url": add_expense_redirect_url,
        "can_create_event": active_thread in [
            'family', 'legal_a', 'legal_b', 'mediation_private', 'consultant_private', 'lawyer_private',
            'mediator_private'],
        "has_deleted_family": FamilyMessage.objects.filter(family=family, thread_type='family',
                                                           is_active=False).exists(),
        "has_deleted_private": FamilyMessage.objects.filter(
            family=family, thread_type__in=['legal_a', 'legal_b', 'mediation_private', 'consultant_private'],
            sender__in=[user, private_with_user] if private_with_user else [user], is_active=False
        ).exists() if private_with_user else False,
        # ✅ NUOVO: Indica se il professionista è nella chat famiglia (solo lettura)
        "is_professional_in_family_chat": is_professional_in_family_chat,
    }

    return render(request, "chat/chat_home.html", context)

@login_required
def message_history_view(request, pk):
    family = get_family_of_user(request.user, request=request)
    message = get_object_or_404(FamilyMessage, pk=pk, family=family)

    history = []
    current = message
    while current:
        history.append(current)
        current = current.previous_version
    history.reverse()

    return render(request, "chat/message_history.html", {"message": message, "history": history})


@login_required
def delete_message_view(request, pk):
    """Elimina messaggio: GET mostra conferma, POST esegue delete"""
    import logging
    logger = logging.getLogger(__name__)

    # ✅ DEBUG LOG
    logger.info(f"🗑️ DELETE MESSAGE - pk={pk}")
    logger.info(f"🗑️ DELETE MESSAGE - POST data: {dict(request.POST)}")
    logger.info(f"🗑️ DELETE MESSAGE - HTTP_REFERER: {request.META.get('HTTP_REFERER')}")


    # 1️⃣ Recupera famiglia
    family = get_family_of_user(request.user, request=request)
    if not family:
        logger.error("❌ DELETE MESSAGE - Nessuna famiglia trovata")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"error": "Nessuna famiglia"}, status=400)
        return redirect('chat:chat_home')

    # 2️⃣ Recupera messaggio
    message = get_object_or_404(FamilyMessage, pk=pk, family=family)

    # 3️⃣ Permessi: solo il mittente può cancellare
    if message.sender != request.user:
        logger.warning(f"⚠️ DELETE MESSAGE - Utente {request.user.email} non è il mittente")
        return HttpResponseForbidden("Puoi cancellare solo i tuoi messaggi")

    # 4️⃣ Se è già stato cancellato, redirect gentile
    if not message.is_active:
        messages.info(request, "ℹ️ Messaggio già eliminato.")
        return redirect('chat:chat_home')

    # 5️⃣ POST = esegui delete
    if request.method == "POST":
        # Chiama la tua funzione di soft delete
        if 'delete_message' in globals():
            delete_message(message, request.user)
        else:
            message.is_active = False
            message.save(update_fields=['is_active'])
        logger.info(f"✅ DELETE MESSAGE - Messaggio {pk} eliminato")
        messages.success(request, "🗑️ Messaggio eliminato.")

        # ✅ NUOVA LOGICA DI REDIRECT: Leggi dove tornare
        return_thread = request.POST.get("return_thread", "family")
        return_chat_with = request.POST.get("return_chat_with")
        logger.info(f"🗑️ DELETE MESSAGE - return_thread: {return_thread}")
        logger.info(f"🗑️ DELETE MESSAGE - return_chat_with: {return_chat_with}")


        # Costruisci l'URL di ritorno
        redirect_url = f"/chat/?thread={return_thread}"
        if return_chat_with:
            redirect_url += f"&chat_with={return_chat_with}"
        logger.info(f"🗑️ DELETE MESSAGE - Redirect URL (da POST): {redirect_url}")

        referer = request.META.get('HTTP_REFERER', '/chat/')
        if '/chat/' in referer:
            redirect_url = referer
        else:
            redirect_url = '/chat/'
        logger.info(f"🗑️ DELETE MESSAGE - Redirect URL (da REFERER): {redirect_url}")

        # Supporta AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"success": True, "redirect_url": redirect_url})
        logger.info(f"🗑️ DELETE MESSAGE - support AJAX: {redirect_url}")

        # Redirect all'URL corretto
        return redirect(redirect_url)

    # 6️⃣ GET = mostra pagina di conferma
    return render(request, "chat/confirm_chat_delete.html", {"message": message})


@require_POST
@login_required
def send_rejection_message(request):
    """AJAX: Invia messaggio di giustificazione rifiuto in chat"""
    try:
        data = json.loads(request.body)
        expense_id = data.get("expense_id")
        reason = data.get("reason", "").strip()
        notify = data.get("notify_sender", False)

        if not expense_id or not reason:
            return JsonResponse({"success": False, "error": "Dati mancanti"}, status=400)

        expense = Expense.objects.get(pk=expense_id, family=get_family_of_user(request.user, request=request))

        content = (
            f"🔴 *Rifiuto spesa*\n\n"
            f"📅 Data: {expense.expense_date.strftime('%d/%m/%Y')}\n"
            f"🏷️ Categoria: {expense.category_name_snapshot if expense.expense_type else 'N/D'}\n"
            f"💰 Importo: € {expense.amount}\n"
            f"👤 Inserita da: {expense.created_by.display_name}\n\n"
            f"❌ Motivazione: {reason}"
        )

        message = send_message(
            family=expense.family,
            sender=request.user,
            content=content,
            reply_to=None,
            thread_type="family"
        )

        if notify and expense.created_by != request.user:
            from django.core.mail import send_mail
            from django.conf import settings
            send_mail(
                subject=f"🔴 Spesa rifiutata: {expense.expense_type}",
                message=f"{request.user.display_name} ha rifiutato la tua spesa.\n\nMotivo:\n{reason}\n\nVedi la chat per dettagli: {request.build_absolute_uri('/chat/')}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[expense.created_by.email],
                fail_silently=True
            )

        return JsonResponse({"success": True, "message_id": message.id, "chat_url": "/chat/"})

    except Expense.DoesNotExist:
        return JsonResponse({"success": False, "error": "Spesa non trovata"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# chat/views.py (in fondo al file, prima di eventuali import finali)
from django.template.loader import render_to_string
from weasyprint import HTML
from django.http import HttpResponse


@login_required
def chat_history_view(request):
    """Mostra TUTTI i messaggi (attivi + eliminati) per cronologia"""
    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect("chat:chat_home")

    chat_type = request.GET.get("type", "family")

    if chat_type == "private":
        # Chat privata: messaggi tra user e counterpart
        private_with_user = None
        membership = FamilyMember.objects.filter(family=family, user=request.user).first()
        if membership:
            role_val = membership.role.value if hasattr(membership.role, 'value') else membership.role
            target_role = None
            if role_val in (RoleChoices.LAWYER_A, 'lawyer_a'):
                target_role = RoleChoices.PARENT_A
            elif role_val in (RoleChoices.LAWYER_B, 'lawyer_b'):
                target_role = RoleChoices.PARENT_B
            elif role_val in (RoleChoices.PARENT_A, 'parent_a'):
                target_role = RoleChoices.LAWYER_A
            elif role_val in (RoleChoices.PARENT_B, 'parent_b'):
                target_role = RoleChoices.LAWYER_B

            if target_role:
                counterpart = FamilyMember.objects.filter(family=family, role=target_role).select_related(
                    'user').first()
                if counterpart: private_with_user = counterpart.user

        messages = FamilyMessage.objects.filter(
            family=family,
            thread_type__in=['legal_a', 'legal_b'],
            sender__in=[request.user, private_with_user] if private_with_user else [request.user],
            recipient__in=[request.user, private_with_user] if private_with_user else [None]
        ).order_by("created_at").select_related("sender", "recipient", "reply_to", "deleted_by")
        title = "Cronologia Chat Privata"
    else:
        # Chat famiglia: tutti i messaggi pubblici
        messages = FamilyMessage.objects.filter(
            family=family,
            thread_type='family'  # Solo messaggi di famiglia
        ).order_by("created_at").select_related("sender", "reply_to", "deleted_by")
        title = "Cronologia Chat Famiglia"

    return render(request, "chat/chat_history.html", {
        "family": family,
        "messages": messages,
        "chat_type": chat_type,
        "page_title": title,
    })


@login_required
@plan_required("pro")  # ✅ Blocca automaticamente gli starter
def chat_export_pdf(request):
    """Esporta chat in PDF (solo messaggi attivi) + LOGO SEMPRE VISIBILE"""
    import os, base64
    from django.conf import settings

    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect("chat:chat_home")

    # ✅ CARICA LOGO BASE64 (fallback a percorso assoluto se fallisce)
    logo_base64 = None
    logo_path = None
    possible_paths = [
        os.path.join(settings.BASE_DIR, 'static', 'img', 'logo_coparent.png'),
        os.path.join(settings.BASE_DIR, 'static', 'images', 'logo-coparent.svg'),
        os.path.join(settings.BASE_DIR, 'static', 'images', 'logo_coparent.png'),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, "rb") as f:
                logo_base64 = base64.b64encode(f.read()).decode('utf-8')
            break
    if not logo_base64:
        # Fallback: usa percorso assoluto per WeasyPrint
        for path in possible_paths:
            if os.path.exists(path):
                logo_path = request.build_absolute_uri(f"/static/{path.split('static/')[-1]}")
                break

    chat_type = request.GET.get("type", "family")

    if chat_type == "private":
        private_with_user = None
        membership = FamilyMember.objects.filter(family=family, user=request.user).first()
        if membership:
            role_val = membership.role.value if hasattr(membership.role, 'value') else membership.role
            target_role = None
            if role_val in (RoleChoices.LAWYER_A, 'lawyer_a'):
                target_role = RoleChoices.PARENT_A
            elif role_val in (RoleChoices.LAWYER_B, 'lawyer_b'):
                target_role = RoleChoices.PARENT_B
            elif role_val in (RoleChoices.PARENT_A, 'parent_a'):
                target_role = RoleChoices.LAWYER_A
            elif role_val in (RoleChoices.PARENT_B, 'parent_b'):
                target_role = RoleChoices.LAWYER_B

            if target_role:
                counterpart = FamilyMember.objects.filter(family=family, role=target_role).select_related(
                    'user').first()
                if counterpart: private_with_user = counterpart.user

        qs = FamilyMessage.objects.filter(
            family=family,
            is_active=True,
            sender__in=[request.user, private_with_user] if private_with_user else [request.user],
            thread_type__in=['legal_a', 'legal_b']
        ).order_by("created_at").select_related("sender", "recipient")
        title = f"Chat Privata - {family.name}"
    else:
        qs = FamilyMessage.objects.filter(
            family=family,
            is_active=True,
            thread_type='family'
        ).order_by("created_at").select_related("sender")
        title = f"Chat Famiglia - {family.name}"

    context = {
        "messages": qs,
        "family": family,
        "title": title,
        "generated_at": timezone.now(),
        "user": request.user,
        "logo_base64": logo_base64,  # ✅ PASSA IL LOGO
        "logo_path": logo_path,
    }
    html_string = render_to_string("chat/chat_pdf.html", context, request=request)
    pdf_bytes = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = title.replace(" ", "_").replace(":", "").replace("/", "-")
    response["Content-Disposition"] = f'attachment; filename="{filename}_{family.id}.pdf"'
    return response


from django.db.models import Q
from chat.models import ProfessionalMessage, ProfessionalThread
from accounts.models import User


@login_required
def professional_chat_view(request):
    """
    Chat tra professionisti dello studio.
    Supporta chat generale e chat private 1-a-1.
    """
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)

    # ✅ Verifica che sia un professionista
    if not profile or not profile.is_professional:
        messages.error(request, "⚠️ Accesso riservato ai professionisti")
        return redirect('families:professional_dashboard')

    # ✅ Recupera tutti i colleghi professionisti
    colleagues = User.objects.filter(
        profile__role__in=['lawyer_a', 'lawyer_b', 'mediator', 'consultant'],
        is_active=True
    ).exclude(id=user.id).select_related('profile')

    # ✅ Determina quale thread mostrare
    thread_id = request.GET.get('thread_id')
    with_user_id = request.GET.get('with_user_id')
    active_thread = None

    # CASO 1: Richiesta di chat privata con utente specifico
    if with_user_id:
        other_user = get_object_or_404(User, id=with_user_id)

        # Cerca se esiste già una chat privata tra questi due utenti
        existing_thread = ProfessionalThread.objects.filter(
            thread_type='private',
            participants=user
        ).filter(
            participants=other_user
        ).first()

        if existing_thread:
            active_thread = existing_thread
        else:
            # Crea nuova chat privata
            active_thread = ProfessionalThread.objects.create(
                name=f"Chat privata",
                thread_type='private',
                created_by=user
            )
            active_thread.participants.add(user, other_user)

    # CASO 2: Thread ID specifico
    elif thread_id:
        active_thread = get_object_or_404(ProfessionalThread, id=thread_id)

        # Verifica permessi
        if active_thread.thread_type == 'private':
            if user not in active_thread.participants.all():
                messages.error(request, "⚠️ Non hai accesso a questa chat")
                return redirect('chat:professional_chat')

    # CASO 3: Chat generale (default)
    else:
        active_thread, created = ProfessionalThread.objects.get_or_create(
            thread_type='studio_general',
            defaults={'name': 'Chat Generale Studio'}
        )

    # ✅ Recupera i messaggi del thread attivo
    messages_list = ProfessionalMessage.objects.filter(
        thread=active_thread,
        is_active=True
    ).select_related('sender').order_by('-created_at')[:100]

    # Inverti per ordine cronologico
    messages_list = list(messages_list)
    messages_list.reverse()

    # ✅ Recupera tutti i thread a cui l'utente può accedere
    user_threads = ProfessionalThread.objects.filter(
        Q(thread_type='studio_general') |
        Q(thread_type='private', participants=user)
    ).distinct()

    # ✅ CALCOLA I NOMI VISUALIZZATI PER OGNI THREAD
    # Questo evita di chiamare metodi con parametri nel template
    threads_with_names = []
    for thread in user_threads:
        # Calcola il nome visualizzato per questo thread
        if thread.thread_type == 'private':
            # Per chat private: nomi degli altri partecipanti
            others = thread.participants.exclude(id=user.id)
            names = []
            for p in others:
                name = p.get_full_name() if p.get_full_name() else p.email
                names.append(name)
            display_name = ', '.join(names) if names else 'Chat privata'
        else:
            # Per chat generale: nome del thread
            display_name = thread.name

        # Aggiungi il thread con il nome calcolato
        threads_with_names.append({
            'thread': thread,
            'display_name': display_name
        })

    # ✅ Calcola il nome del thread attivo
    if active_thread.thread_type == 'private':
        others = active_thread.participants.exclude(id=user.id)
        names = []
        for p in others:
            name = p.get_full_name() if p.get_full_name() else p.email
            names.append(name)
        active_thread_display_name = ', '.join(names) if names else 'Chat privata'
    else:
        active_thread_display_name = active_thread.name

    # ✅ Gestione POST (invio messaggio)
    if request.method == 'POST':
        content = request.POST.get('message', '').strip()
        files = request.FILES.getlist('attachments')

        if content or files:
            # Crea il messaggio (il contenuto viene criptato automaticamente)
            msg = ProfessionalMessage.objects.create(
                thread=active_thread,
                sender=user,
                content=content,  # ✅ Viene criptato dal campo EncryptedTextField
            )

            # ✅ Gestisci allegati (vengono criptati automaticamente nel save())
            if files:
                for f in files:
                    ProfessionalAttachment.objects.create(
                        message=msg,
                        encrypted_file=f,  # ✅ Il file verrà criptato nel save()
                        original_filename=f.name,  # Salva il nome originale
                        file_size=f.size,
                        content_type=f.content_type or 'application/octet-stream',
                        uploaded_by=user
                    )

            messages.success(request, "✅ Messaggio inviato")
            return redirect(f"{reverse('chat:professional_chat')}?thread_id={active_thread.id}")

    # ✅ Context per il template
    context = {
        'colleagues': colleagues,
        'messages_list': messages_list,
        'active_thread': active_thread,
        'active_thread_display_name': active_thread_display_name,  # ✅ Nome già calcolato
        'threads_with_names': threads_with_names,  # ✅ Lista con nomi già calcolati
        'user': user,
        'is_private_chat': active_thread.thread_type == 'private',
    }

    return render(request, 'chat/professional_chat.html', context)


import logging
from django.http import HttpResponse, Http404
from chat.models import ProfessionalAttachment

logger = logging.getLogger(__name__)


@login_required
def download_professional_attachment(request, attachment_id):
    """
    Scarica un allegato decriptato.
    Verifica i permessi in modo robusto prima di servire il file.
    """
    user = request.user

    # ✅ DEBUG: Log dell'utente che richiede il download
    logger.info(f"📥 Download allegato ID {attachment_id} richiesto da {user.email}")

    # ✅ Recupera l'allegato
    attachment = get_object_or_404(ProfessionalAttachment, id=attachment_id)
    thread = attachment.message.thread

    # ✅ DEBUG: Log del thread
    logger.info(f"📋 Thread: {thread.name} (tipo: {thread.thread_type})")

    # ✅ Recupera il profilo in modo sicuro (gestisce sia 'profile' che 'userprofile')
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)

    # ✅ VERIFICA PERMESSI in base al tipo di thread
    if thread.thread_type == 'private':
        # Chat privata: verifica che l'utente sia tra i partecipanti
        participants = list(thread.participants.all())
        participant_ids = [p.id for p in participants]

        logger.info(f"👥 Partecipanti thread: {participant_ids}")
        logger.info(f"👤 User ID: {user.id}")

        if user not in participants:
            logger.warning(f"⚠️ Utente {user.email} NON è nei partecipanti del thread privato")
            messages.error(request, "⚠️ Non hai accesso a questo allegato")
            return redirect('chat:professional_chat')

    else:
        # Chat generale: verifica che sia un professionista
        is_prof = getattr(profile, 'is_professional', False) if profile else False

        logger.info(f"👔 Profilo: {profile}, is_professional: {is_prof}")

        if not is_prof:
            logger.warning(f"⚠️ Utente {user.email} NON è un professionista")
            messages.error(request, "⚠️ Accesso negato: solo professionisti")
            return redirect('chat:professional_chat')

    # ✅ Decripta il file
    decrypted_content = attachment.get_decrypted_file()

    if decrypted_content is None:
        logger.error(f"❌ Errore decriptazione allegato ID {attachment.id}")
        messages.error(request, "⚠️ Errore nel leggere l'allegato")
        return redirect('chat:professional_chat')

    # ✅ Prepara la response HTTP con il file decriptato
    response = HttpResponse(
        decrypted_content,
        content_type=attachment.content_type or 'application/octet-stream'
    )

    # ✅ Imposta il nome del file per il download
    filename = attachment.get_download_filename()
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    logger.info(f"✅ Allegato {filename} servito correttamente a {user.email}")

    return response


# chat/views.py

@login_required
def preview_professional_attachment(request, attachment_id):
    """
    Mostra l'anteprima di un allegato nel browser (inline).
    Funziona per PDF, immagini, testo.
    """
    attachment = get_object_or_404(ProfessionalAttachment, id=attachment_id)

    # ✅ Verifica permessi
    if not _user_can_access_attachment(request.user, attachment):
        messages.error(request, "⚠️ Non hai accesso a questo allegato")
        return redirect('chat:professional_chat')

    # ✅ Decripta il file
    decrypted_content = attachment.get_decrypted_file()
    if decrypted_content is None:
        messages.error(request, "⚠️ Errore nel leggere l'allegato")
        return redirect('chat:professional_chat')

    # ✅ Response inline (visualizza nel browser)
    response = HttpResponse(
        decrypted_content,
        content_type=attachment.content_type or 'application/octet-stream'
    )
    response['Content-Disposition'] = 'inline'  # ← Mostra nel browser

    return response


@login_required
def download_professional_attachment(request, attachment_id):
    """
    Scarica un allegato (attachment).
    """
    attachment = get_object_or_404(ProfessionalAttachment, id=attachment_id)

    # ✅ Verifica permessi
    if not _user_can_access_attachment(request.user, attachment):
        messages.error(request, "⚠️ Non hai accesso a questo allegato")
        return redirect('chat:professional_chat')

    # ✅ Decripta il file
    decrypted_content = attachment.get_decrypted_file()
    if decrypted_content is None:
        messages.error(request, "⚠️ Errore nel leggere l'allegato")
        return redirect('chat:professional_chat')

    # ✅ Response attachment (download)
    response = HttpResponse(
        decrypted_content,
        content_type=attachment.content_type or 'application/octet-stream'
    )
    filename = attachment.get_download_filename()
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


def _user_can_access_attachment(user, attachment):
    """
    Helper: verifica se l'utente può accedere all'allegato.
    Ritorna True/False.
    """
    thread = attachment.message.thread
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)

    if thread.thread_type == 'private':
        return user in thread.participants.all()
    else:
        # Chat generale: solo professionisti
        return getattr(profile, 'is_professional', False) if profile else False