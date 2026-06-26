# expenses/views.py
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Sum, Q
from families.utils import get_family_of_user
from core.plans import PLAN_LEVELS
from children.models import ChildProfile
from .models import Expense

from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponseForbidden, FileResponse, JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.db import transaction
from core.choices import RoleChoices
from core.plans import PLAN_LEVELS
from documents.models import Document
from families.utils import get_family_of_user
from families.models import FamilyMember
from expenses.forms import ExpenseForm
from notifications.services import create_notification
from .models import Expense, ExpenseCategory
from expenses.pdf_utils import generate_expense_report_pdf
from expenses.services.expences_service import create_expense, update_expense, approve_expense
from .utils import get_expense_shares

PARENT_ROLES = [RoleChoices.PARENT_A, RoleChoices.PARENT_B]

@login_required
def expenses_dashboard(request):
    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    if not family:
        messages.error(request, "⚠️ Nessuna famiglia associata")
        return redirect('home')
    expenses = Expense.objects.filter(family=family, is_active=True).select_related(
        "child", "created_by", "expense_type"
    ).order_by("-expense_date")

    expenses, form, data, page_title = filter_expenses_with_metadata(request, expenses, family)

    total_expenses = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    parent_a_total = Decimal("0.00")
    parent_b_total = Decimal("0.00")
    # ✅ Escludi le ordinarie dal calcolo quote (non influenzano il mantenimento)
    for exp in expenses:
        if exp.child and exp.group_snapshot != "ordinarie":
            a, b = get_expense_shares(exp)
            parent_a_total += a
            parent_b_total += b

    category_summary = expenses.values("expense_type_id", "expense_type__display_name", "expense_type__color").annotate(
        total=Sum("amount")
    ).order_by("expense_type__display_name")

    # Conta spese pendenti (non ancora approvate/pagate)
    pending_count = Expense.objects.filter(
        family=family,
        is_active=True
    ).filter(
        # Spesa in stato "pending" (non ancora processata)
        Q(status='pending') |
        # OPPURE spesa "accepted" ma manca almeno un'approvazione
        Q(status='accepted', approved_by_parent_a__isnull=True) |
        Q(status='accepted', approved_by_parent_b__isnull=True)
    ).count()

    # ✅ CONTESTO PIANO (obbligatorio per sbloccare il calendario)
    profile = getattr(request.user, 'profile', None)
    plan = getattr(profile, 'plan', 'starter') if profile else 'starter'
    is_pro_or_higher = PLAN_LEVELS.get(plan, 1) >= 2

    return render(request, "expenses/expenses_dashboard.html", {
        "expenses": expenses[:5],
        "total_expenses": total_expenses,
        "parent_a_total": parent_a_total,
        "parent_b_total": parent_b_total,
        'pending_expenses_count': pending_count,
        "category_summary": category_summary,
        "page_title": page_title,
        "is_pro_or_higher": is_pro_or_higher,  # ✅ PASSA SEMPRE QUESTO
        "family": family,
    })


@login_required
def expenses_list(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)

    # ✅ NUOVO: Gestione professionisti con family_id
    family_id = request.GET.get('family_id') or request.session.get('active_family_id')
    is_professional = profile and profile.role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']

    if is_professional and family_id:
        family = get_object_or_404(Family, id=family_id)

        # Verifica accesso
        membership = FamilyMember.objects.filter(
            family=family,
            user=user,
            role__in=['lawyer_a', 'lawyer_b', 'mediator', 'consultant']
        ).first()

        if not membership:
            messages.error(request, "⚠️ Non hai accesso a questa famiglia")
            return redirect('families:lawyer_dashboard')
    else:
        # Logica esistente per genitori
        family = get_family_of_user(user, request=request)
        if not family:
            return redirect("families:setup")
        membership = FamilyMember.objects.filter(family=family, user=user).first()

    can_manage = membership and membership.role in ["parent_a", "parent_b"] if membership else False

    expenses = Expense.objects.filter(family=family, is_active=True).select_related(
        "child", "created_by", "expense_type"
    ).order_by("-expense_date")

    expenses, form, data, page_title = filter_expenses_with_metadata(request, expenses, family)
    total_expenses = expenses.aggregate(total=Sum("amount"))["total"] or 0

    expenses_with_editable = []
    for exp in expenses:
        if exp.status in ("pending", "rejected"):
            exp.is_editable_flag = True
        elif exp.status == "paid":
            exp.is_editable_flag = False
        elif exp.status == "accepted":
            exp.is_editable_flag = not (exp.approved_by_parent_a or exp.approved_by_parent_b)
        else:
            exp.is_editable_flag = False
        expenses_with_editable.append(exp)

    return render(request, "expenses/expenses_list.html", {
        "expenses": expenses_with_editable,
        "form": form,
        "total_expenses": total_expenses,
        "page_title": page_title,
        "can_manage_expenses": can_manage,
        "family": family,  # ✅ Aggiunto per il template
        "membership": membership,  # ✅ Aggiunto per il template
    })

from django.contrib import messages


@login_required
@transaction.atomic
def add_expense(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)

    # ✅ BLOCCO PROFESSIONISTI: Solo i genitori possono inserire spese
    if profile and profile.role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']:
        messages.error(request,
                       "⚠️ Solo i genitori possono inserire spese. I professionisti hanno accesso in sola lettura.")
        return redirect("expenses:expenses_list")

    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    if not family:
        messages.error(request, "⚠️ Nessuna famiglia associata")
        return redirect("expenses:expenses_list")

    membership = family.members.filter(user=request.user).first()
    if not membership or membership.role not in PARENT_ROLES:
        messages.error(request, "⚠️ Solo i genitori possono inserire spese")
        return redirect("expenses:expenses_list")

    user_role = str(membership.role).lower()
    is_parent = user_role in ['parent_a', 'parent_b']
    is_spouse = user_role == 'spouse'

    if not (is_parent or is_spouse):
        messages.error(request, "⚠️ Solo i genitori e il coniuge possono inserire spese")
        return redirect("expenses:expenses_list")

        # ✅ VALIDAZIONE CONIUGE: può inserire solo se ha mantenimento attivo
    if is_spouse:
        from children.models import ChildSupport
        from datetime import date

        today = date.today()

        # Controlla se ha mantenimento coniuge attivo
        spouse_support = ChildSupport.objects.filter(
            family=family,
            support_type='spouse',
            is_active=True,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).first()

        if not spouse_support:
            messages.error(request, "⚠️ Non puoi inserire spese perché non hai un mantenimento attivo")
            return redirect("expenses:expenses_list")

    # ✅ NUOVO: Leggi il parametro ?next= per il redirect alla chat
    next_url = request.GET.get('next') or request.POST.get('next')

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            cleaned = form.cleaned_data

            # ✅ Controlla se è spesa per coniuge
            is_for_spouse = cleaned.get('is_for_spouse', False)

            # ✅ Se è per coniuge, ignora il campo child
            child = None if is_for_spouse else cleaned.get("child")
            expense_date = cleaned["expense_date"]

            # ✅ VALIDAZIONE CONIUGE
            if is_spouse or is_for_spouse:
                from children.models import ChildSupport
                from datetime import date
                today = date.today()

                if child:
                    child_support = ChildSupport.objects.filter(
                        child=child,
                        support_type='child',
                        is_active=True,
                        start_date__lte=today
                    ).filter(
                        Q(end_date__isnull=True) | Q(end_date__gte=today)
                    ).first()

                    if child_support and child_support.end_date and expense_date > child_support.end_date:
                        messages.error(
                            request,
                            f"⚠️ Non puoi inserire spese per {child.name} dopo il {child_support.end_date.strftime('%d/%m/%Y')}"
                        )
                        return redirect("expenses:expenses_list")
                elif is_for_spouse:
                    spouse_support = ChildSupport.objects.filter(
                        family=family,
                        support_type='spouse',
                        is_active=True,
                        start_date__lte=today
                    ).filter(
                        Q(end_date__isnull=True) | Q(end_date__gte=today)
                    ).first()

                    if spouse_support and spouse_support.end_date and expense_date > spouse_support.end_date:
                        messages.error(
                            request,
                            f"⚠️ Non puoi inserire spese dopo il {spouse_support.end_date.strftime('%d/%m/%Y')}"
                        )
                        return redirect("expenses:expenses_list")

            expense = create_expense(
                family=family,
                user=request.user,
                child=child,
                expense_type=cleaned["expense_type"],
                amount=cleaned["amount"],
                description=cleaned.get("description", ""),
                expense_date=expense_date,
                membership=membership
            )

            # ✅ Se è per coniuge, aggiungi nota alla descrizione
            if is_for_spouse:
                expense.description = f"[Coniuge] {expense.description}" if expense.description else "[Coniuge]"
                expense.save(update_fields=['description'])

            if expense.group_snapshot.lower() != "ordinarie" and expense.status != "paid":
                approve_expense(expense, request.user, membership.role)

                import logging
                logger = logging.getLogger(__name__)

                other_parent_role = RoleChoices.PARENT_B if str(membership.role).lower() in ['parent_a',
                                                                                             'parent'] else RoleChoices.PARENT_A
                other_parent = FamilyMember.objects.filter(family=family, role=other_parent_role).select_related(
                    'user').first()

                if other_parent and other_parent.user != request.user:
                    try:
                        category_name = expense.expense_type.display_name if expense.expense_type else "Spesa"
                        beneficiary = "Coniuge" if is_for_spouse else (child.name if child else "Famiglia")
                        create_notification(
                            user=other_parent.user,
                            notification_type="expense_pending",
                            title=f"🆕 Nuova spesa da approvare",
                            message=f"{request.user.first_name or request.user.email} ha inserito una nuova spesa di €{expense.amount} per '{category_name}' ({beneficiary}).",
                            target_url=f"/expenses/list/",
                            target_model="Expense",
                            target_id=expense.id,
                            metadata={"amount": str(expense.amount), "category": category_name,
                                      "beneficiary": beneficiary}
                        )
                    except Exception as e:
                        logger.error(f"Errore invio notifica spesa a {other_parent.user.email}: {e}")

            if expense.group_snapshot.lower() == "ordinarie":
                messages.success(request,
                                 f"✅ Spesa ordinaria registrata e approvata automaticamente: €{expense.amount}")
            else:
                beneficiary = "coniuge" if is_for_spouse else (f"figlio {child.name}" if child else "famiglia")
                messages.success(request, f"✅ Spesa per {beneficiary} inserita. In attesa dell'altro genitore.")

            if is_spouse:
                parent_a = FamilyMember.objects.filter(family=family, role='parent_a').first()
                parent_b = FamilyMember.objects.filter(family=family, role='parent_b').first()

                if parent_a:
                    expense.approved_by_parent_a = parent_a.user
                if parent_b:
                    expense.approved_by_parent_b = parent_b.user

                expense.status = 'paid'
                expense.save(update_fields=['approved_by_parent_a', 'approved_by_parent_b', 'status'])

                messages.success(request, "✅ Spesa registrata e approvata automaticamente")
            else:
                for f in request.FILES.getlist('payment_proof'):
                    Document.objects.create(
                        family=family, owner=request.user, uploaded_by=request.user,
                        expense=expense, file=f,
                        title=f"Prova_pagamento_v{expense.version}_{f.name[:50]}",
                        category="payment_proof", scope="shared", status="approved", is_active=True
                    )

            if next_url:
                separator = '&' if '?' in next_url else '?'
                return redirect(f"{next_url}{separator}new_expense_id={expense.id}")

            return redirect("expenses:expenses_dashboard")
    else:
        form = ExpenseForm(user=request.user)

    return render(request, "expenses/expenses_form.html", {
        "form": form,
        "title": "Aggiungi Spesa",
        "next_url": next_url or ''
    })


@login_required
def expense_update(request, pk):
    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    original_expense = get_object_or_404(Expense, pk=pk, family=family, is_active=True)

    if original_expense.created_by != request.user:
        return HttpResponseForbidden("Non puoi modificare questa spesa")

    membership = family.members.filter(user=request.user).first()
    if not membership or membership.role not in ["parent_a", "parent_b"]:
        messages.error(request, "⚠️ Solo i genitori possono modificare spese")
        return redirect("expenses:expenses_list")

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, instance=original_expense, user=request.user)
        if form.is_valid():
            child = form.cleaned_data["child"]
            new_expense = update_expense(original_expense, request.user, form.cleaned_data, child, membership)
            approve_expense(new_expense, request.user, membership.role)

            for f in request.FILES.getlist('payment_proof'):
                Document.objects.create(
                    family=family, owner=request.user, uploaded_by=request.user,
                    expense=new_expense, file=f,
                    title=f"Prova_pagamento_v{new_expense.version}_{f.name[:50]}",
                    category="payment_proof", scope="shared", status="approved", is_active=True
                )

            messages.success(request, f"✅ Spesa aggiornata a v{new_expense.version}. In attesa di approvazione.")
            return redirect("expenses:expenses_list")
    else:
        form = ExpenseForm(instance=original_expense, user=request.user)

    return render(request, "expenses/expenses_form.html", {"form": form, "title": "Modifica Spesa"})


@login_required
def expense_history(request, pk):
    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    expense = get_object_or_404(Expense, pk=pk, family=family)

    versions = []
    curr = expense
    while curr:
        versions.append(curr)
        curr = curr.previous_version
    versions.reverse()

    return render(request, "expenses/expense_history.html", {
        "expense": expense,
        "expense_versions": versions
    })

@require_POST
@login_required
@transaction.atomic
def update_expense_status(request):
    import json
    try:
        data = json.loads(request.body)
        expense_id = data.get("expense_id")
        new_status = data.get("status")

        if new_status not in ["accepted", "rejected"]:
            return JsonResponse({"success": False, "error": "Stato non valido"}, status=400)

        # ✅ FIX: passa request=request
        family = get_family_of_user(request.user, request=request)
        expense = get_object_or_404(Expense, pk=expense_id, family=family)

        if expense.created_by == request.user:
            return JsonResponse({"success": False, "error": "Solo l'altro genitore può approvare o rifiutare"}, status=403)

        membership = family.members.filter(user=request.user).select_related('user').first()
        if not membership:
            return JsonResponse({"success": False, "error": "Membro famiglia non trovato"}, status=403)

        user_role = str(membership.role.value if hasattr(membership.role, 'value') else membership.role).lower()
        if user_role not in ['parent_a', 'parent_b']:
            return JsonResponse({"success": False, "error": "Solo i genitori possono gestire le approvazioni"},
                                status=403)
        if new_status == "accepted":
            approve_expense(expense, request.user, user_role)
            expense.status = "accepted"
        elif new_status == "rejected":
            approve_expense(expense, request.user, user_role)
            expense.status = "rejected"

        expense.save(update_fields=["status"])

        from notifications.services import create_notification
        create_notification(
            user=expense.created_by,
            notification_type=f"expense_{new_status}",
            title=f"Spesa {'approvata' if new_status == 'accepted' else 'rifiutata'}",
            message=f"La tua spesa di €{expense.amount} è stata {new_status} da {request.user.first_name or request.user.email}.",
            target_url=f"/expenses/list/",
            target_model="Expense",
            target_id=expense.id
            #send_email=True
        )

        return JsonResponse({"success": True, "new_status": new_status})

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Errore update_expense_status: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": "Errore interno del server"}, status=500)


@require_POST
@login_required
def upload_payment_proof(request):
    try:
        expense_id = request.POST.get("expense_id")
        # ✅ FIX: passa request=request
        family = get_family_of_user(request.user, request=request)
        expense = get_object_or_404(Expense, pk=expense_id, family=family)

        if expense.created_by == request.user:
            return JsonResponse({"success": False, "error": "Solo l'altro genitore può caricare la prova di pagamento"}, status=403)

        if expense.status == "paid":
            return JsonResponse({"success": False, "error": "Pagamento già completato"}, status=400)
        membership = family.members.filter(user=request.user).first()
        if not membership:
            return JsonResponse({"success": False, "error": "Membro non trovato"}, status=403)

        user_role = str(membership.role.value if hasattr(membership.role, 'value') else membership.role).lower()
        if user_role not in ['parent_a', 'parent_b']:
            return JsonResponse({"success": False, "error": "Solo i genitori possono confermare il pagamento"},
                                status=403)
        file = request.FILES.get("proof_file")
        if not file:
            return JsonResponse({"success": False, "error": "Nessun file ricevuto"}, status=400)

        Document.objects.create(
            family=expense.family,
            owner=request.user,
            uploaded_by=request.user,
            expense=expense,
            file=file,
            title=f"Prova_pagamento_{expense.id}_{file.name[:50]}",
            category="payment_proof",
            scope="shared",
            status="approved",
            is_active=True
        )

        if not expense.approved_by_parent_b:
            approve_expense(expense, request.user, "parent_b")

        expense.status = "paid"
        expense.save(update_fields=["status"])

        return JsonResponse({
            "success": True,
            "new_status": expense.status,
            "payment_state": expense.payment_state
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# chat/views.py
@require_POST
@login_required
def send_rejection_message(request):
    try:
        import json
        from expenses.models import Expense
        from chat.services.message_service import send_message

        data = json.loads(request.body)
        expense_id = data.get("expense_id")
        reason = data.get("reason", "").strip()
        notify = data.get("notify_sender", False)

        if not expense_id or not reason:
            return JsonResponse({"success": False, "error": "Dati mancanti"}, status=400)

        # ✅ FIX: passa request=request
        family = get_family_of_user(request.user, request=request)
        expense = Expense.objects.get(pk=expense_id, family=family)

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

        return JsonResponse({
            "success": True,
            "message_id": message.id,
            "chat_url": f"/chat/"
        })

    except Expense.DoesNotExist:
        return JsonResponse({"success": False, "error": "Spesa non trovata"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def expense_delete(request, pk):
    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    expense = get_object_or_404(Expense, pk=pk, family=family)
    if expense.created_by != request.user:
        return HttpResponseForbidden("Non puoi eliminare questa spesa")

    if request.method == "POST":
        expense.is_active = False
        expense.save()
        return redirect("expenses:expenses_list")
    return render(request, "expenses/expenses_confirm_delete.html", {"expense": expense})


@login_required
def download_expense_pdf(request):
    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    if not family:
        from django.contrib import messages
        messages.error(request, "⚠️ Nessuna famiglia associata")
        return redirect("expenses:expenses_list")

    expenses = Expense.objects.filter(family=family, is_active=True).select_related(
        "child", "expense_type"
    ).order_by("-expense_date")

    total_expenses = sum(exp.amount for exp in expenses) or Decimal("0.00")

    parent_a_total = Decimal("0.00")
    parent_b_total = Decimal("0.00")
    # ✅ Escludi le ordinarie dal calcolo quote (non influenzano il mantenimento)
    for exp in expenses:
        if exp.group_snapshot != "ordinarie":
            pct_raw = getattr(exp.child, 'contribution_pct_parent_a', None)
            pct_a = Decimal(str(pct_raw)) if pct_raw is not None else Decimal('50.00')
            share_a = exp.amount * (pct_a / Decimal('100'))
            share_b = exp.amount * ((Decimal('100') - pct_a) / Decimal('100'))
            parent_a_total += share_a
            parent_b_total += share_b

    pdf_bytes = generate_expense_report_pdf(
        request, family, expenses[:100],
        total_expenses, parent_a_total, parent_b_total
    )

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="report_spese_{family.id}_{datetime.now().strftime("%Y%m%d")}.pdf"'
    return response

@login_required
def expenses_calendar(request):
    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    expenses = Expense.objects.filter(family=family, is_active=True)
    data = []
    for e in expenses:
        data.append({
            "id": e.id,
            "title": f"{e.amount} €",
            "start": str(e.expense_date),
            "allDay": True,
            "extendedProps": {
                "status": e.status,
                "type": e.expense_type.display_name if e.expense_type else None,
                "color": e.expense_type.color if e.expense_type else None,
            }
        })
    return JsonResponse(data, safe=False)


@login_required
def expense_day_detail(request, date):
    # ✅ FIX: passa request=request
    family = get_family_of_user(request.user, request=request)
    expenses = Expense.objects.filter(family=family, expense_date=date, is_active=True).select_related("child", "created_by")
    return render(request, "expenses/day_detail.html", {"expenses": expenses, "date": date})




@login_required
def expenses_riepilogo_spese(request):
    """Riepilogo spese con grafici Pro-only, mantenimento figli e cronologia"""

    # 1️⃣ Recupera famiglia
    family = get_family_of_user(request.user, request=request)
    if not family:
        messages.error(request, "⚠️ Nessuna famiglia associata")
        return redirect('expenses:expenses_dashboard')

    # 2️⃣ Controllo piano (Pro vs Starter)
    profile = getattr(request.user, 'profile', None)
    plan = getattr(profile, 'plan', 'starter') if profile else 'starter'
    is_pro_or_higher = PLAN_LEVELS.get(plan, 1) >= 2

    # 3️⃣ ✅ FIX: Query spese per CRONOLOGIA (TUTTI gli stati, non solo accepted)
    expenses_qs = Expense.objects.filter(
        family=family,
        is_active=True
    ).select_related("expense_type", "created_by", "child").order_by("-expense_date")

    # 4️⃣ Totali e lista per tabella (tutte le spese)
    total_expenses = expenses_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    expenses_list = list(expenses_qs[:50])  # Limita a 50 per performance

    # 5️⃣ Dati PRO-ONLY (skip per starter)
    category_summary = []
    parent_a_total = Decimal("0.00")
    parent_b_total = Decimal("0.00")

    if is_pro_or_higher:
        # ✅ ✅ FIX CRUCIALE: Query SEPARATA per calcoli (solo accepted)
        # Le spese pending/rejected NON influenzano le statistiche
        accepted_expenses = expenses_qs.filter(status="accepted")

        # 📊 Breakdown per categoria (solo accepted)
        category_summary = accepted_expenses.values(
            "expense_type__display_name",
            "expense_type__color"
        ).annotate(total=Sum("amount")).order_by("-total")

        # ⚖️ Calcolo quote genitori (solo accepted)
        for exp in accepted_expenses:
            if exp.child:
                split_a = exp.child.effective_split_pct_parent_a or Decimal("50.00")
                quota_a = exp.amount * (split_a / Decimal("100"))
                quota_b = exp.amount - quota_a
            else:
                quota_a = exp.amount / Decimal("2")
                quota_b = exp.amount / Decimal("2")
            parent_a_total += quota_a
            parent_b_total += quota_b

    # 6️⃣ ✅ MANTENIMENTO FIGLI (ALLINEATO AL TUO MODELLO)
    maintenance_info = {}
    children = ChildProfile.objects.filter(family=family, is_active=True)

    for child in children:
        # ✅ Escludi le ordinarie dal calcolo spese condivise (non influenzano il mantenimento)
        child_expenses = expenses_qs.filter(child=child).exclude(
            group_snapshot="ordinarie"
        ).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        child_name = f"{child.name} {child.surname}" if child.surname else child.name

        # 🔒 USA LE TUE @PROPERTY (gestiscono automaticamente fallback e sentenze attive)
        split_a = child.effective_split_pct_parent_a or Decimal("50.00")
        split_b = Decimal("100.00") - split_a
        payer = "Genitore A" if split_a >= split_b else "Genitore B"

        # Property che controlla: 1. ChildSupport attivo → 2. Manuale → 3. None
        monthly_support = child.effective_maintenance_amount or Decimal("0.00")

        maintenance_info[child_name] = {
            "age": child.age,
            "payer": payer,
            "amount": monthly_support,
            "shared_expenses": child_expenses,
            "split_a": split_a,
            "split_b": split_b,
        }

    # 7️⃣ Media spese (per KPI) - calcolata su TUTTE le spese
    average_expense = total_expenses / len(expenses_list) if expenses_list else Decimal("0.00")

    # 8️⃣ Context finale
    context = {
        "family": family,
        "expenses": expenses_list,  # ✅ Ora contiene TUTTE le spese (pending, accepted, rejected, paid)
        "total_expenses": total_expenses,
        "average_expense": average_expense,  # ✅ Per KPI "Media per Spesa"
        "maintenance_info": maintenance_info,  # ✅ Per tabella mantenimento figli

        # Dati Pro-only
        "category_summary": category_summary,
        "parent_a_total": parent_a_total,
        "parent_b_total": parent_b_total,
        "is_pro_or_higher": is_pro_or_higher,
    }

    return render(request, "expenses/expenses_riepilogo_spese.html", context)

# ========================================================================
# UTILS
# ========================================================================
def filter_expenses_with_metadata(request, queryset, family):
    from .forms import ExpenseFilterForm

    form = ExpenseFilterForm(request.GET or None, family=family)
    data = {}
    title_parts = []

    if form.is_valid():
        data = form.cleaned_data

        if data.get("child"):
            queryset = queryset.filter(child=data["child"])
            title_parts.append(str(data["child"]))

        if data.get("status"):
            queryset = queryset.filter(status=data["status"])
            label = dict(Expense.STATUS_CHOICES).get(data["status"])
            if label:
                title_parts.append(label)

        if data.get("expense_type"):
            queryset = queryset.filter(expense_type=data["expense_type"])
            label = data["expense_type"].display_name
            if label:
                title_parts.insert(0, f"Spese filtrate per: {label.lower()}")

        if data.get("date_from"):
            queryset = queryset.filter(expense_date__gte=data["date_from"])
        if data.get("date_to"):
            queryset = queryset.filter(expense_date__lte=data["date_to"])

        date_from, date_to = data.get("date_from"), data.get("date_to")
        if date_from and date_to:
            title_parts.append(f"dal {date_from.strftime('%d.%m.%Y')} al {date_to.strftime('%d.%m.%Y')}")
        elif date_from:
            title_parts.append(f"dal {date_from.strftime('%d.%m.%Y')}")
        elif date_to:
            title_parts.append(f"fino al {date_to.strftime('%d.%m.%Y')}")

    page_title = "Spese filtrate per: " + " - ".join(
        p.capitalize() for p in title_parts) if title_parts else "Tutte le spese"

    return queryset, form, data, page_title


def calculate_parent_debt(expense_amount, child):
    pct_a = float(child.contribution_pct_parent_a) / 100
    pct_b = 1.0 - pct_a
    amount_a = expense_amount * pct_a
    amount_b = expense_amount * pct_b
    return amount_a, amount_b


#________________________GESTIONE CATEGORIE E SPESE SOLO ADMIN________________________________________

from django.contrib.admin.views.decorators import staff_member_required, user_passes_test
from django.shortcuts import render
from .models import ExpenseCategory

def superadmin_only(user):
    return user.is_superuser

def admin_required(view_func):
    return user_passes_test(lambda u: u.is_superuser)(view_func)

@admin_required
@staff_member_required
def categories_list(request):
    categories = ExpenseCategory.objects.select_related("group").all()
    return render(request, "expenses/categories/list.html", {"categories": categories})

from django.shortcuts import redirect
from .forms import ExpenseCategoryForm

@staff_member_required
def category_create(request):
    form = ExpenseCategoryForm(request.POST or None)
    if form.is_valid():
        category = form.save()
        return redirect("categories_list")
    return render(request, "expenses/categories/form.html", {"form": form})

from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import ExpenseCategoryHistory

@staff_member_required
def category_update(request, pk):
    old_category = get_object_or_404(ExpenseCategory, pk=pk)
    form = ExpenseCategoryForm(request.POST or None, instance=old_category)

    if form.is_valid():
        old_category.valid_to = timezone.now()
        old_category.is_active = False
        old_category.save()

        new_category = form.save(commit=False)
        new_category.pk = None
        new_category.version = old_category.version + 1
        new_category.previous_version = old_category
        new_category.valid_from = timezone.now()
        new_category.is_active = True
        new_category.save()

        ExpenseCategoryHistory.objects.create(
            category=new_category,
            action="updated",
            old_name=old_category.display_name,
            new_name=new_category.name,
            old_color=old_category.color,
            new_color=new_category.color,
            changed_by=request.user
        )
        return redirect("categories_list")

    return render(request, "expenses/categories/form.html", {"form": form, "category": old_category})

@staff_member_required
def category_delete(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    category.is_active = False
    category.valid_to = timezone.now()
    category.save()

    ExpenseCategoryHistory.objects.create(
        category=category,
        action="deleted",
        old_name=category.display_name,
        changed_by=request.user
    )
    return redirect("categories_list")


@login_required
def expenses_analytics_view(request):
    """Report avanzato spese: trend mensili, categorie, comparativo genitori (SOLO Pro+)"""
    family = get_family_of_user(request.user, request=request)
    if not family:
        messages.error(request, "⚠️ Nessuna famiglia associata")
        return redirect('expenses:expenses_dashboard')

    # 🔒 Controllo piano: solo Pro/Enterprise
    profile = getattr(request.user, 'profile', None)
    plan = getattr(profile, 'plan', 'starter') if profile else 'starter'
    if PLAN_LEVELS.get(plan, 1) < 2:  # < pro
        messages.info(request,
                      "📊 Funzione riservata al piano Pro. Effettua l'upgrade per sbloccare l'analisi avanzata.")
        return redirect('pricing')

    # 📅 Filtri data (ultimi 12 mesi di default)
    months_back = int(request.GET.get("months", 12))
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=months_back * 30)

    # 📦 Query base
    expenses_qs = Expense.objects.filter(
        family=family,
        is_active=True,
        status="accepted",  # Solo spese approvate
        expense_date__gte=start_date,
        expense_date__lte=end_date
    ).select_related("child", "expense_type", "created_by")

    # 📈 1. Trend mensile (line chart)
    monthly_trend = expenses_qs.annotate(
        month=TruncMonth("expense_date")
    ).values("month").annotate(
        total=Sum("amount"),
        count=Count("id")
    ).order_by("month")

    # 🥧 2. Breakdown per categoria (doughnut chart)
    category_breakdown = expenses_qs.values(
        "expense_type__display_name",
        "expense_type__color"
    ).annotate(
        total=Sum("amount"),
        count=Count("id")
    ).order_by("-total")

    # ⚖️ 3. Comparativo genitori (bar chart)
    parent_a_total = Decimal("0.00")
    parent_b_total = Decimal("0.00")

    # ✅ Escludi le ordinarie dal calcolo quote (non influenzano il mantenimento)
    for exp in expenses_qs:
        if exp.child and exp.child.split_percentage_a is not None and exp.group_snapshot != "ordinarie":
            quota_a = exp.amount * (exp.child.split_percentage_a / Decimal("100"))
            quota_b = exp.amount - quota_a
            parent_a_total += quota_a
            parent_b_total += quota_b

    # 📊 4. Top 5 spese (tabella)
    top_expenses = expenses_qs.order_by("-amount")[:5]

    # 💰 5. KPI card
    total_spent = expenses_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    avg_expense = total_spent / expenses_qs.count() if expenses_qs.exists() else Decimal("0.00")

    context = {
        "family": family,
        "months_back": months_back,
        "start_date": start_date,
        "end_date": end_date,
        # Dati grafici (serializzabili in JSON per Chart.js)
        "monthly_trend_json": [
            {"month": item["month"].strftime("%Y-%m"), "total": float(item["total"]), "count": item["count"]}
            for item in monthly_trend
        ],
        "category_breakdown_json": [
            {"label": item["expense_type__display_name"] or "Senza categoria",
             "value": float(item["total"]),
             "color": item["expense_type__color"] or "#6c757d",
             "count": item["count"]}
            for item in category_breakdown
        ],
        "parent_comparison": {
            "parent_a": float(parent_a_total),
            "parent_b": float(parent_b_total),
            "difference": float(abs(parent_a_total - parent_b_total)),
            "higher": "A" if parent_a_total > parent_b_total else "B" if parent_b_total > parent_a_total else "Pareggio"
        },
        "top_expenses": top_expenses,
        "kpi": {
            "total": float(total_spent),
            "average": float(avg_expense),
            "count": expenses_qs.count(),
            "trend": "up" if monthly_trend.last() and monthly_trend.first() and monthly_trend.last()["total"] >
                             monthly_trend.first()["total"] else "down"
        }
    }

    return render(request, "expenses/expenses_analytics.html", context)