from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from families.utils import get_family_of_user  # ← così funziona ora
from .models import FamilyMessage
from .services.message_service import (
    send_message,
    update_message,
    delete_message,
    get_family_messages
)


@login_required
def family_chat_view(request):
    family = get_family_of_user(request.user)

    if not family:
        return render(request, "chat/no_family.html")

    # 🔍 RICERCA: estrai query string
    search_query = request.GET.get("q", "").strip()

    # 🎯 RILEVA CONTESTO RIFIUTO SPESA
    reject_expense_id = request.GET.get("reject_expense_id")
    reject_context = None
    if reject_expense_id:
        from expenses.models import Expense
        expense = Expense.objects.filter(
            id=reject_expense_id,
            family=family,
            is_active=True
        ).first()
        if expense:
            reject_context = {
                "expense_id": expense.id,
                "amount": expense.amount,
                "category": expense.expense_type.display_name if expense.expense_type else "N/D",
                "date": expense.expense_date.strftime("%d/%m/%Y") if expense.expense_date else "-",
                "created_by": expense.created_by.username
            }

    if request.method == "POST":
        message_id = request.POST.get("message_id")
        content = request.POST.get("message", "").strip()
        recipient_id = request.POST.get("recipient")
        reply_id = request.POST.get("reply_to")
        reply_message = None

        if reply_id:
            reply_message = FamilyMessage.objects.filter(
                id=reply_id,
                family=family
            ).first()

        files = request.FILES.getlist("attachments")
        # evita messaggi completamente vuoti
        if not content and not files:
            return redirect("caht:chat_home")

        create_event_flag = request.POST.get("create_event") == "on"

        event_data = None

        # crea evento solo se date presenti
        if create_event_flag:
            now = timezone.now()
            start_time = request.POST.get("event_start") or now
            end_time = request.POST.get("event_end") or now

            event_data = {
                "title": request.POST.get("event_title") or content[:50],
                "start_time": start_time or now,
                "end_time": end_time or now,
                "description": request.POST.get("event_description") or content
            }

        recipient = None

        if recipient_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            recipient = User.objects.filter(id=recipient_id).first()

        # modifica messaggio
        if message_id:
            msg = FamilyMessage.objects.get(
                id=message_id,
                family=family
            )
            update_message(
                msg,
                request.user,
                content,
                files,
                create_event_flag,
                event_data
            )
        # nuovo messaggio
        else:
            send_message(
                family=family,
                sender=request.user,
                content=content,
                recipient=recipient,
                files=files,
                create_calendar_event=create_event_flag,
                event_data=event_data,
                reply_to=reply_message
            )
        # IMPORTANTISSIMO
        return redirect("chat:chat_home")





    # ✅ FILTRA MESSAGGI SE C'È RICERCA
    if search_query:
        messages = FamilyMessage.objects.filter(
            family=family,
            is_active=True,
            content__icontains=search_query  # 🔍 Filtro case-insensitive
        ).order_by("created_at").select_related("sender", "reply_to")
    else:
        # Fallback alla funzione esistente
        messages = get_family_messages(family)

    # 📎 DOCUMENTI CONDIVISI (ultimi 10, attivi)
    from documents.models import Document
    shared_docs = Document.objects.filter(
        family=family,
        is_active=True,
        scope="shared"
    ).select_related("uploaded_by").order_by("-created_at")[:10]

    messages = get_family_messages(family)
    return render(
        request,
        "chat/chat_home.html",
        {
            "messages": messages,
            "family": family,
            "reject_context": reject_context,
            "search_query": search_query , # ✅ Passa al template per highlight
            "shared_docs": shared_docs  # ✅ Nuovo contesto
        }
)


@login_required
def message_history_view(request, pk):
    family = get_family_of_user(request.user)

    message = get_object_or_404(
        FamilyMessage,
        pk=pk,
        family=family
    )

    history = []
    current = message

    while current:
        history.append(current)
        current = current.previous_version

    history.reverse()

    return render(
        request,
        "chat/message_history.html",
        {
            "message": message,
            "history": history
        }
    )


@login_required
def delete_message_view(request, pk):
    family = get_family_of_user(request.user)

    message = get_object_or_404(
        FamilyMessage,
        pk=pk,
        family=family,
        is_active=True
    )

    if request.method == "POST":
        delete_message(message, request.user)
        return redirect("chat:chat_home")

    return render(
        request,
        "chat/confirm_chat_delete.html",
        {"message": message}
    )

import json
from expenses.models import Expense
from .services.message_service import send_message
# chat/views.py
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

        # Costruisci messaggio strutturato
        content = (
            f"🔴 *Rifiuto spesa*\n\n"
            f"📅 Data: {expense.expense_date.strftime('%d/%m/%Y')}\n"
            f"🏷️ Categoria: {expense.expense_type.display_name if expense.expense_type else 'N/D'}\n"
            f"💰 Importo: € {expense.amount}\n"
            f"👤 Inserita da: {expense.created_by.display_name}\n\n"
            f"❌ Motivazione: {reason}"
        )

        # Invia in chat familiare
        message = send_message(
            family=expense.family,
            sender=request.user,
            content=content,
            reply_to=None
        )

        # Notifica email opzionale al creatore
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

        return JsonResponse({
            "success": True,
            "message_id": message.id,
            "chat_url": f"/chat/"
        })

    except Expense.DoesNotExist:
        return JsonResponse({"success": False, "error": "Spesa non trovata"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)