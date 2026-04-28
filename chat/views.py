from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import render, redirect
from django.utils import timezone

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


    messages = get_family_messages(family)

    return render(
        request,
        "chat/chat_home.html",
        {
            "messages": messages,
            "family": family
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
