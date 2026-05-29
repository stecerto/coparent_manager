# chat/views.py
import json
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse
from django.contrib import messages
from children.models import ChildProfile
from .models import FamilyMessage
from .services.message_service import send_message, delete_message
from families.models import FamilyMember
from families.utils import get_family_of_user
from core.choices import RoleChoices
from expenses.models import Expense
from documents.models import Document


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
        family = get_family_of_user(user)
        if not family:
            return render(request, "chat/no_family.html")
        membership = FamilyMember.objects.filter(family=family, user=user).first()

    # 🔐 2. CALCOLA CONTROPARTE PRIVATA (FAMILY-SCOPED & BLINDATA)
    private_with_user = None
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
            counterpart = FamilyMember.objects.filter(
                family=family, role=target_role
            ).select_related('user').first()
            if counterpart:
                private_with_user = counterpart.user

    # 🔍 3. RICERCA & CONTESTO RIFIUTO SPESA
    search_query = request.GET.get("q", "").strip()
    reject_expense_id = request.GET.get("reject_expense_id")
    reject_context = None
    if reject_expense_id:
        expense = Expense.objects.filter(id=reject_expense_id, family=family, is_active=True).select_related('created_by').first()
        if expense:
            reject_context = {
                "expense_id": expense.id, "amount": expense.amount,
                "category": expense.category_name_snapshot if expense.expense_type else "N/D",
                "date": expense.expense_date.strftime("%d/%m/%Y") if expense.expense_date else "-",
                "created_by": expense.created_by.display_name if hasattr(expense.created_by, 'display_name') else expense.created_by.username
            }

    # 📥 4. GESTIONE POST (INVIO MESSAGGI)
    if request.method == "POST":
        chat_type = request.POST.get("chat_type", "family")
        content = request.POST.get("message", "").strip()
        reply_id = request.POST.get("reply_to")
        reply_message = FamilyMessage.objects.filter(id=reply_id, family=family).first() if reply_id else None
        files = request.FILES.getlist("attachments")

        if not content and not files:
            return redirect(request.path)

        create_event_flag = (chat_type == "family" and request.POST.get("create_event") == "on")
        event_data = None
        if create_event_flag:
            now = timezone.now()
            # ✅ FIX 1: Dizionario STRICT per CalendarEvent (evita TypeError)
            event_data = {
                "title": (request.POST.get("event_title") or content[:50]).strip(),
                "start_time": request.POST.get("event_start") or now,
                "end_time": request.POST.get("event_end") or now,
                "description": (request.POST.get("event_description") or content).strip(),
                "source": "chat",
                "linked_id": None,
                "children_ids": request.POST.getlist("event_children"),
            }
            # Rimuovi chiavi extra che CalendarEvent non accetta
            for unwanted_key in ("amount", "expense_id", "category", "reject_expense_id",
                                 "chat_type", "message", "attachments", "reply_to", "create_event"):
                event_data.pop(unwanted_key, None)

        recipient = private_with_user if chat_type == "private" else None

        # ✅ FIX 2: Struttura if/else corretta (era duplicata)
        if chat_type == "private" and private_with_user:
            # Chat privata: crea messaggio diretto + allegati
            msg = FamilyMessage.objects.create(
                family=family, sender=user, recipient=private_with_user,
                content=content, reply_to=reply_message
            )
            for f in files:
                Document.objects.create(
                    family=family, uploaded_by=user, owner=user,
                    file=f, title=f.name[:100], is_private=True
                )

            # 🔔 FIX 3: Notifica per messaggi privati (qui chat_type è disponibile)
            try:
                from notifications.services import create_notification
                create_notification(
                    user=private_with_user,
                    notification_type="chat_private",
                    title=f"Nuovo messaggio da {user.first_name or user.email}",
                    message=content[:150] + ("..." if len(content) > 150 else ""),
                    target_url=f"/chat/?family_id={family.id}",
                    target_model="FamilyMessage",
                    target_id=msg.id,
                    metadata={"sender_id": user.id, "family_id": family.id},
                    send_email=True
                )
            except ImportError:
                # Fallback email se notifications non è pronta
                if private_with_user.email:
                    from django.core.mail import send_mail
                    from django.conf import settings
                    send_mail(
                        subject=f"🔔 Nuovo messaggio privato",
                        message=f"{user.first_name} ti ha scritto: {content[:200]}\n\nVedi: {settings.SITE_URL}/chat/",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[private_with_user.email],
                        fail_silently=True
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Errore notifica: {e}", exc_info=True)
                # Non bloccare il flusso se la notifica fallisce
        else:
            # Chat famiglia: usa il service esistente (mantiene tutta la logica originale)
            send_message(
                family=family, sender=user, content=content, recipient=None,
                files=files, create_calendar_event=create_event_flag,
                event_data=event_data, reply_to=reply_message
            )

        return redirect(request.path)

    # 📊 5. PREPARA I DUE CANALI
    family_messages = FamilyMessage.objects.filter(
        family=family, is_active=True, recipient__isnull=True
    ).order_by("created_at").select_related("sender", "reply_to")

    private_messages = []
    if private_with_user:
        private_messages = FamilyMessage.objects.filter(
            family=family, is_active=True,
            sender__in=[user, private_with_user],
            recipient__in=[user, private_with_user]
        ).order_by("created_at").select_related("sender", "recipient", "reply_to")

        if not private_messages.filter(content__startswith="🔒 *Chat privata avviata*").exists():
            FamilyMessage.objects.create(
                family=family, sender=user, recipient=private_with_user,
                content=f"🔒 *Chat privata avviata*. Visibile solo a te e {user.first_name}."
            )
            private_messages = FamilyMessage.objects.filter(
                family=family, is_active=True,
                sender__in=[user, private_with_user],
                recipient__in=[user, private_with_user]
            ).order_by("created_at")

    # 📎 DOCUMENTI & EXPENSES
    user_field = "owner"

    shared_docs = Document.objects.filter(
        family=family, is_active=True, is_private=False
    ).select_related(user_field).order_by("-created_at")[:10]

    private_docs = Document.objects.filter(
        family=family, is_active=True, is_private=True
    ).select_related(user_field).order_by("-created_at")[:10]

    expenses = []
    if membership and membership.role in RoleChoices.lawyer_roles():
        expenses = Expense.objects.filter(family=family, is_active=True).select_related('created_by', 'category').order_by('-expense_date')[:20]

    family_children = ChildProfile.objects.filter(family=family, is_active=True).order_by("surname", "name")

    # 🎯 6. CONTESTO
    context = {
        "family": family,
        "membership": membership,
        "family_children": family_children,
        "family_messages": family_messages,
        "private_messages": private_messages,
        "private_with_user": private_with_user,
        "search_query": search_query,
        "shared_docs": shared_docs,
        "private_docs": private_docs,
        "reject_context": reject_context,
        "expenses": expenses,
    }
    return render(request, "chat/chat_home.html", context)


@login_required
def message_history_view(request, pk):
    family = get_family_of_user(request.user)
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
    family = get_family_of_user(request.user)
    message = get_object_or_404(FamilyMessage, pk=pk, family=family, is_active=True)

    if request.method == "POST":
        delete_message(message, request.user)
        messages.success(request, "🗑️ Messaggio eliminato.")
        return redirect("chat:chat_home")

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

        expense = Expense.objects.get(pk=expense_id, family=get_family_of_user(request.user))

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
            reply_to=None
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