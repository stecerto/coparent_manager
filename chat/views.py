# chat/views.py
import json
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.contrib.auth import get_user_model
from children.models import ChildProfile
from core.decorators import plan_required
from .models import FamilyMessage
from chat.services.message_service import send_message, delete_message
from families.models import FamilyMember
from families.utils import get_family_of_user
from core.choices import RoleChoices
from expenses.models import Expense
from documents.models import Document

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
def family_chat_view(request, family_id=None, user_id=None):
    user = request.user

    # 🎯 1. DETERMINA FAMIGLIA E MEMBERSHIP
    if family_id:
        membership = get_object_or_404(
            FamilyMember.objects.select_related('family', 'user__profile'),
            user=user, family_id=family_id,
            role__in=RoleChoices.lawyer_roles()
        )
        family = membership.family
    else:
        family = get_family_of_user(user, request=request)
        if not family:
            return render(request, "chat/no_family.html")
        membership = FamilyMember.objects.filter(family=family, user=user).first()

    if not membership:
        return HttpResponseForbidden("Non hai accesso a questa famiglia")

    role_val = membership.role.value if hasattr(membership.role, 'value') else str(membership.role)
    role_base = str(role_val).strip().lower().replace('_a', '').replace('_b', '')

    # 🔐 2. RECUPERA TUTTI I PROFESSIONISTI DELLA FAMIGLIA (IL BLOCCO CHE MANCAVA!)
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

        # ✅ STANDARDIZZA: usa sempre consultant_private (con la "i")
        if prof_role in ['lawyer_a', 'lawyer_b']:
            thread_type = f"legal_{prof_role.split('_')[1]}"
        elif prof_role == 'mediator':
            thread_type = 'mediation_private'
        elif prof_role == 'consultant':
            thread_type = 'consultant_private'  # ✅ CORRETTO: consultant_private
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

    # 🔍 3. DETERMINA CON CHI STA CHATTANDO ORA (dall'URL ?chat_with=<id>)
    chat_with_id = request.GET.get('chat_with') or user_id
    private_with_user = None
    current_thread_type = None

    if chat_with_id:
        try:
            private_with_user = User.objects.get(id=chat_with_id)
            for prof in available_professionals:
                if prof['user'].id == private_with_user.id:
                    current_thread_type = prof['thread_type']
                    break
        except User.DoesNotExist:
            pass



    # 🔍 4. RICERCA & CONTESTO RIFIUTO SPESA (MANTENUTO)
    search_query = request.GET.get("q", "").strip()
    reject_expense_id = request.GET.get("reject_expense_id")
    reject_context = None
    if reject_expense_id:
        expense = Expense.objects.filter(id=reject_expense_id, family=family, is_active=True).select_related(
            'created_by', 'category').first()
        if expense:
            # ✅ Cerca se questa spesa è collegata a un evento calendario
            from calendar_app.models import CalendarEvent
            linked_event = CalendarEvent.objects.filter(linked_expense=expense, is_active=True).first()

            reject_context = {
                "expense_id": expense.id,
                "amount": expense.amount,
                "category": expense.management.commands.category.name if expense.category else "N/D",
                "date": expense.expense_date.strftime("%d/%m/%Y") if expense.expense_date else "-",
                "created_by": expense.created_by.display_name if hasattr(expense.created_by,
                                                                         'display_name') else expense.created_by.username,
                "description": expense.description,
                "status": expense.get_status_display() if hasattr(expense, 'get_status_display') else expense.status,
            }

            # ✅ Se c'è un evento collegato, aggiungi le informazioni
            if linked_event:
                reject_context["linked_event"] = {
                    "id": linked_event.id,
                    "title": linked_event.title,
                    "event_type": linked_event.get_event_type_display() if hasattr(linked_event,
                                                                                   'get_event_type_display') else linked_event.event_type,
                    "date": linked_event.start_time.strftime("%d/%m/%Y %H:%M") if linked_event.start_time else "-",
                    "url": f"/calendar/event/{linked_event.id}/detail/",  # URL all'evento
                }

    # 📥 5. GESTIONE POST (INVIO MESSAGGI)
    if request.method == "POST":
        import logging
        logger = logging.getLogger(__name__)

        logger.info("=" * 60)
        logger.info("📨 POST CHAT - INIZIO")
        logger.info(f"📨 POST CHAT - URL: {request.path}")
        logger.info(f"📨 POST CHAT - GET params: {dict(request.GET)}")
        logger.info(f"📨 POST CHAT - POST data: {dict(request.POST)}")
        # Supporta sia 'chat_type' (legacy) che 'thread_type' (nuovo)
        raw_thread = request.POST.get("thread_type")
        legacy_chat_type = request.POST.get("chat_type")

        thread_type = raw_thread.strip() if raw_thread else (legacy_chat_type or "family")
        # ✅ DEBUG LOG
        logger.info(f"📨 POST CHAT - raw_thread_type: '{raw_thread}', legacy: '{legacy_chat_type}'")
        logger.info(f"📨 POST CHAT - thread_type finale: '{thread_type}'")
        #logger.info(f"📨 POST CHAT - active_thread nel context: '{active_thread}'")

        # Mappatura legacy per retrocompatibilità
        if thread_type == "private" and private_with_user:
            thread_type = 'legal_a' if role_val in ['parent_a', 'lawyer_a'] else 'legal_b'

        # Sicurezza: se per qualche motivo è ancora vuoto, forza "family"
        if not thread_type:
            thread_type = "family"

        content = request.POST.get("message", "").strip()
        reply_id = request.POST.get("reply_to")
        reply_message = FamilyMessage.objects.filter(id=reply_id, family=family).first() if reply_id else None
        files = request.FILES.getlist("attachments")

        if not content and not files:
            logger.warning("⚠️ POST CHAT - Nessun contenuto né allegati, redirect")
            return redirect(request.path)

        # Validazione sicurezza: l'utente può scrivere in questo thread?
        from chat.services.permissions import get_accessible_threads_for_user
        allowed_threads = get_accessible_threads_for_user(user, family)

        if thread_type not in allowed_threads:
            logger.error(f"🚫 POST CHAT - Permesso negato! thread_type='{thread_type}' non in {allowed_threads}")
            # ✅ Mostra un popup elegante invece della pagina bianca
            return render(request, "chat/permission_denied.html", {
                "message": "Non hai i permessi per scrivere in questa chat specifica.",
                "safe_redirect": f"/chat/?family_id={family.id}"  # Torna alla chat sicura
            })

        # Determina destinatario per chat private
        recipient = None
        if thread_type in ['legal_a', 'legal_b', 'mediation_private', 'consultant_private', 'lawyer_private',
                           'mediator_private']:
            recipient_id = request.POST.get('recipient_id')
            logger.info(f"📨 POST CHAT - Cercando recipient_id: {recipient_id}")
            if recipient_id:
                try:
                    recipient = User.objects.get(id=recipient_id)
                    logger.info(f"✅ POST CHAT - Recipient trovato: {recipient.email}")
                except User.DoesNotExist:
                    logger.error(f"❌ POST CHAT - User con id={recipient_id} non esiste")
            else:
                logger.warning(f"⚠️ POST CHAT - recipient_id NON fornito nel form!")

        create_event_flag = (thread_type in ['family', 'legal_a', 'legal_b', 'mediation_private', 'lawyer_private', 'mediator_private', 'consultant_private']
                             and request.POST.get("create_event") == "on")
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
            for unwanted_key in ("amount", "expense_id", "category", "reject_expense_id",
                                 "chat_type", "message", "attachments", "reply_to", "create_event", "thread_type"):
                event_data.pop(unwanted_key, None)

        # ✅ INVIO MESSAGGIO TRAMITE SERVICE
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
        logger.info(f"✅ POST CHAT - messaggio: {msg}")
        # Gestione allegati documenti privati (mantenuta dalla logica originale)
        if files and thread_type in ['legal_a', 'legal_b', 'mediation_private', 'consultant_private']:
            for f in files:
                Document.objects.create(
                    family=family, uploaded_by=user, owner=user,
                    file=f, title=f.name[:100], is_private=True
                )

        # 🔔 Notifica per messaggi privati (mantenuta dalla logica originale)
        if thread_type in ['legal_a', 'legal_b', 'mediation_private', 'consultant_private'] and recipient:
            try:
                from notifications.services import create_notification
                create_notification(
                    user=recipient,
                    notification_type="chat_private",
                    title=f"Nuovo messaggio da {user.first_name or user.email}",
                    message=content[:150] + ("..." if len(content) > 150 else ""),
                    target_url=f"/chat/?family_id={family.id}&thread={thread_type}",
                    target_model="FamilyMessage",
                    target_id=msg.id,
                    metadata={"sender_id": user.id, "family_id": family.id, "thread_type": thread_type},
                    send_email=False
                )
            except ImportError:
                if recipient.email:
                    from django.core.mail import send_mail
                    from django.conf import settings
                    send_mail(
                        subject=f"🔔 Nuovo messaggio privato",
                        message=f"{user.first_name} ti ha scritto: {content[:200]}\n\nVedi: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/chat/",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[recipient.email],
                        fail_silently=True
                    )
            except Exception as e:
                logger.error(f"Errore notifica: {e}", exc_info=True)

        # Redirect mantenendo la chat attiva
        redirect_url = request.path
        if recipient:
            redirect_url += f"?thread={thread_type}&chat_with={recipient.id}"
        elif thread_type != "family":
            redirect_url += f"?thread={thread_type}"

        return redirect(redirect_url)

    # 📊 6. PREPARA I DATI PER LA UI (GET)
    active_thread = request.GET.get("thread", "family")



    # 📊 COSTRUZIONE SIDEBAR DINAMICA
    available_chats = []

    # 1. Chat Famiglia (sempre presente)
    available_chats.append({
        "type": "family",
        "name": "💬 Chat Famiglia",
        "icon": "👨‍👩‍👧‍👦",
        "is_active": (active_thread == "family"),
        "url": "?thread=family",
        "is_private": False
    })


    # 2. Se l'utente è un PROFESSIONISTA → mostra chat private con i GENITORI
    if role_base in ['lawyer', 'mediator', 'consultant']:
        parents = FamilyMember.objects.filter(
            family=family,
            role__in=[RoleChoices.PARENT_A, RoleChoices.PARENT_B, 'parent_a', 'parent_b', 'parent']
        ).select_related('user').exclude(user=user)

        for p in parents:
            # ✅ STANDARDIZZA: usa sempre consultant_private (con la "i")
            thread_type = f"{role_base}ing_private" if role_base == 'consult' else f"{role_base}_private"
            # Oppure più semplice:
            if role_base == 'lawyer':
                thread_type = f"legal_{p.role.split('_')[1]}" if hasattr(p.role, 'split') else 'legal_a'
            elif role_base == 'mediator':
                thread_type = 'mediation_private'
            elif role_base == 'consultant':
                thread_type = 'consultant_private'  # ✅ CORRETTO
            else:
                thread_type = f"{role_base}_private"

            is_active = (active_thread == thread_type and private_with_user and private_with_user.id == p.user.id)

            # ✅ NOME PULITO PER LA UI (es: "Gen. A: Mario Rossi")
            parent_name = p.user.get_full_name() or p.user.email
            role_short = "Gen. A" if 'a' in str(p.role).lower() else "Gen. B" if 'b' in str(
                p.role).lower() else "Genitore"
            clean_name = f"{role_short}: {parent_name}"

            available_chats.append({
                "type": thread_type,
                "name": clean_name,
                "icon": "👤",
                "is_active": is_active,
                "url": f"?thread={thread_type}&chat_with={p.user.id}",
                "user_id": p.user.id,
                "is_private": True
            })

    # 3. Se l'utente è un GENITORE → mostra chat private con i PROFESSIONISTI
    if role_base == 'parent':
        for prof in available_professionals:
            is_active = (active_thread == prof['thread_type'] and private_with_user and private_with_user.id == prof['user'].id)
            icon = "⚖️" if 'lawyer' in prof['role'] else "🤝" if prof['role'] == 'mediator' else "💼"

            # ✅ Determina il prefisso in base al ruolo
            if 'lawyer' in prof['role']:
                prefix = "Avv."
            elif 'mediator' in prof['role']:
                prefix = "Med."
            elif 'consultant' in prof['role']:
                prefix = "Cons."
            else:
                prefix = "Prof."

            # Estrai solo il nome proprio (o la prima parte dell'email)
            prof_name = prof['user'].first_name or prof['user'].email.split('@')[0]

            # ✅ NOME COMPATTO PER L'UTENTE: "Avv. [Nome] di [Famiglia]"
            display_name = f"{prefix} {prof_name} di {family.name}"

            available_chats.append({
                "type": prof['thread_type'],
                "name": display_name,
                "icon": icon,
                "is_active": is_active,
                "url": f"?thread={prof['thread_type']}&chat_with={prof['user'].id}",
                "user_id": prof['user'].id,
                "is_private": True
            })

    # 4. Chat di gruppo Mediazione (visibile a genitori, mediatori e consulenti)
    if role_base in ['parent', 'mediator', 'consultant']:
        available_chats.append({
            "type": "mediation",
            "name": "🤝 Mediazione (Gruppo)",
            "icon": "🕊️",
            "is_active": (active_thread == "mediation"),
            "url": "?thread=mediation",
            "is_private": False
        })

    # 5. Chat di gruppo Consulenza (visibile a genitori e consulenti)
    if role_base in ['parent', 'consultant']:
        available_chats.append({
            "type": "consulting",
            "name": "💼 Consulenza (Gruppo)",
            "icon": "💡",
            "is_active": (active_thread == "consulting"),
            "url": "?thread=consulting",
            "is_private": False
        })



    # Recupera i messaggi VISIBILI per l'utente usando la nuova funzione centralizzata
    from chat.services.permissions import get_visible_messages
    all_visible_messages = get_visible_messages(user, family)

    # Applica filtro di ricerca se presente (MANTENUTO)
    if search_query:
        all_visible_messages = all_visible_messages.filter(content__icontains=search_query)

    # Filtra i messaggi in base alla chat selezionata nella sidebar
    if active_thread == "family":
        current_messages = all_visible_messages.filter(thread_type="family")
    elif active_thread in ["legal_a", "legal_b", "mediation_private", "consultant_private"] and private_with_user:
        from django.db.models import Q
        current_messages = all_visible_messages.filter(
            thread_type=active_thread,
        ).filter(
            Q(sender=user, recipient=private_with_user) |
            Q(sender=private_with_user, recipient=user) |
            Q(sender=user, recipient__isnull=True) |
            Q(sender=private_with_user, recipient__isnull=True)
        )
    else:
        # Chat di gruppo
        current_messages = all_visible_messages.filter(thread_type=active_thread)

    # Ordina messaggi
    current_messages = current_messages.order_by("created_at").select_related("sender", "recipient", "reply_to")

    # 📎 DOCUMENTI & EXPENSES (MANTENUTI)
    user_field = "owner"
    shared_docs = Document.objects.filter(
        family=family, is_active=True, is_private=False
    ).select_related(user_field).order_by("-created_at")[:10]

    private_docs = Document.objects.filter(
        family=family, is_active=True, is_private=True
    ).select_related(user_field).order_by("-created_at")[:10]

    expenses = []
    if membership and membership.role in RoleChoices.lawyer_roles():
        expenses = Expense.objects.filter(family=family, is_active=True).select_related('created_by',
                                                                                        'category').order_by(
            '-expense_date')[:20]

    family_children = ChildProfile.objects.filter(family=family, is_active=True).order_by("surname", "name")

    # 🎯 7. CONTESTO COMPLETO (NESSUNA OMISSIONE)
    context = {
        "family": family,
        "membership": membership,
        "family_children": family_children,
        "available_chats": available_chats,  # ✅ Per la sidebar
        "available_professionals": available_professionals,  # ✅ Lista professionisti
        "active_thread": active_thread,  # ✅ Per sapere quale chat evidenziare
        "current_messages": current_messages,  # ✅ I messaggi da mostrare al centro
        "private_with_user": private_with_user,
        "current_thread_type": current_thread_type,
        "search_query": search_query,
        "shared_docs": shared_docs,
        "private_docs": private_docs,
        "reject_context": reject_context,
        "expenses": expenses,
        "can_create_event": active_thread in [
            'family', 'legal_a', 'legal_b',
            'mediation_private', 'consultant_private',
            'lawyer_private', 'mediator_private'],
        # ✅ Flags per messaggi eliminati (mantenuti per pulsanti history/cronologia)
        "has_deleted_family": FamilyMessage.objects.filter(
            family=family, thread_type='family', is_active=False
        ).exists(),
        "has_deleted_private": FamilyMessage.objects.filter(
            family=family,
            thread_type__in=['legal_a', 'legal_b', 'mediation_private', 'consultant_private'],
            sender__in=[user, private_with_user] if private_with_user else [user],
            is_active=False
        ).exists() if private_with_user else False,
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