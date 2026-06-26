import base64
import logging
import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML
from django.contrib import messages
from core.plans import PLAN_LEVELS  # o il tuo import per i piani
from families.models import FamilyMember, Family
from families.utils import get_family_of_user
from .forms import DocumentUploadForm
from .models import Document, DocumentAuditLog, DocumentVersion, DocumentSignature
from .permissions import can_access_document
from .services.documents_checklist_service import get_essential_checklist
from .services.documents_signature_service import sign_document
from .services.workflow_service import approve_document
from .validators import check_file_sizes

logger = logging.getLogger(__name__)


@login_required
def document_list_view(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)

    # ✅ Gestione professionisti con family_id
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
        membership = FamilyMember.objects.filter(
            family=family,
            user=user
        ).first()

    role = membership.role if membership else None

    # ✅ Filtro per categoria
    category_filter = request.GET.get('category', 'all')

    # Query base per documenti privati
    private_docs = Document.objects.none()

    if membership:
        if role in ["parent_a", "parent_b"]:
            private_docs = Document.objects.filter(
                family=family,
                owner=user,
                scope="private",
                is_active=True
            )

        elif role == "lawyer_a":
            assisted_user = family.members.filter(role="parent_a").first()
            if assisted_user:
                private_docs = Document.objects.filter(
                    family=family,
                    owner=assisted_user.user,
                    scope="private",
                    is_active=True
                )

        elif role == "lawyer_b":
            assisted_user = family.members.filter(role="parent_b").first()
            if assisted_user:
                private_docs = Document.objects.filter(
                    family=family,
                    owner=assisted_user.user,
                    scope="private",
                    is_active=True
                )

    shared_docs = Document.objects.filter(
        family=family,
        scope="shared",
        is_active=True
    )
    # ✅ APPLICA FILTRO CATEGORIA
    if category_filter and category_filter != 'all':
        private_docs = private_docs.filter(category=category_filter)
        shared_docs = shared_docs.filter(category=category_filter)

    # ✅ Filtra documenti senza file fisico
    private_docs = [doc for doc in private_docs if doc.file_exists]
    shared_docs = [doc for doc in shared_docs if doc.file_exists]
    checklist = get_essential_checklist(user, family)

    # 🔥 PRELOAD FIRME UTENTE
    signed_docs = set(
        DocumentSignature.objects.filter(
            user=user,
            document__in=list(private_docs) + list(shared_docs)
        ).values_list("document_id", flat=True)
    )

    for doc in private_docs:
        doc.is_signed_by_user = doc.id in signed_docs

    for doc in shared_docs:
        doc.is_signed_by_user = doc.id in signed_docs

    # ✅ Statistiche per categoria
    all_docs = list(private_docs) + list(shared_docs)
    category_stats = {}
    for doc in all_docs:
        cat = doc.category
        if cat not in category_stats:
            category_stats[cat] = 0
        category_stats[cat] += 1

    # ✅ AGGIUNGI QUESTO: Calcola il totale
    total_docs_count = len(all_docs)

    return render(request, "documents/documents_list.html", {
        "private_docs": private_docs,
        "shared_docs": shared_docs,
        "checklist": checklist,
        "role": role,
        "family": family,
        "membership": membership,
        "category_filter": category_filter,
        "category_stats": category_stats,
        "category_choices": Document.CATEGORY_CHOICES,
        "total_docs_count": total_docs_count,  # ✅ AGGIUNGI QUESTO
    })


@login_required
def document_preview_view(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)

    if not can_access_document(request.user, doc, request=request):
        return HttpResponseForbidden("Permessi insufficienti.")

    try:
        # ✅ Usa esplicitamente lo storage del file
        file_storage = doc.file.storage
        file_name = doc.file.name

        # Verifica se il file esiste nello storage
        if not file_storage.exists(file_name):
            logger.error(f"File non trovato nello storage: {file_name}")
            messages.error(request, f"Il file '{doc.title}' non è stato trovato nel sistema di archiviazione.")
            return redirect('documents:documents_list')

        # Apre il file usando lo storage corretto
        file_obj = file_storage.open(file_name, 'rb')

        mime_type, _ = mimetypes.guess_type(file_name)
        content_type = mime_type or 'application/octet-stream'

        response = FileResponse(file_obj, content_type=content_type, as_attachment=False)
        response['Content-Disposition'] = f'inline; filename="{Path(file_name).name}"'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Access-Control-Allow-Origin'] = request.build_absolute_uri('/').rstrip('/')

        return response

    except Exception as e:
        logger.error(f"Errore apertura file {doc.id}: {e}", exc_info=True)

        messages.error(request, f"Errore durante l'apertura del file: {str(e)}")
        return redirect('documents:documents_list')



@login_required
def upload_document_view(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)
    from django.contrib import messages
    # ✅ BLOCCO PROFESSIONISTI: Solo i genitori possono caricare documenti
    if profile and profile.role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']:
        messages.error(request,
                       "⚠️ Solo i genitori possono caricare documenti. I professionisti hanno accesso in sola lettura.")
        return redirect("documents:documents_list")

    family = get_family_of_user(request.user, request=request)

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            files = request.FILES.getlist("files")
            category = form.cleaned_data["category"]

            # ✅ VALIDAZIONE DIMENSIONI (non tocca la logica esistente)
            size_error = check_file_sizes(files, category)
            if size_error:
                from django.contrib import messages
                messages.error(request, size_error)
                return render(request, "documents/documents_upload.html", {"form": form})

            custom_title = form.cleaned_data["title"]
            category = form.cleaned_data["category"]
            scope = form.cleaned_data["scope"]
            reference_year = form.cleaned_data["reference_year"]

            with transaction.atomic():
                for index, uploaded_file in enumerate(files, start=1):
                    original_name = Path(uploaded_file.name).stem

                    if custom_title:
                        title = (
                            f"{custom_title}_{index}"
                            if len(files) > 1
                            else custom_title
                        )
                    else:
                        title = original_name

                    # cerchiamo documento esistente
                    existing_doc = Document.objects.filter(
                        family=family,
                        owner=request.user,
                        title=title,
                        is_active=True
                    ).first()

                    if existing_doc:
                        # 💡 doc.version qui è un INTERO (es. 1)
                        # Salviamo lo STATO ATTUALE come versione archiviata
                        DocumentVersion.objects.create(
                            document=existing_doc,
                            file=existing_doc.file,
                            version=existing_doc.versions,  # ✅ Passa l'intero corrente
                            uploaded_by=request.user
                        )

                        # Aggiorna documento principale
                        existing_doc.file = uploaded_file
                        existing_doc.versions += 1  # ✅ Incrementa l'intero
                        existing_doc.category = category
                        existing_doc.scope = scope
                        existing_doc.reference_year = reference_year
                        existing_doc.save()

                        DocumentAuditLog.objects.create(
                            document=existing_doc,
                            user=request.user,
                            action="update"
                        )

                    else:
                        doc = Document.objects.create(
                            family=family,
                            owner=request.user,
                            uploaded_by=request.user,
                            title=title,
                            file=uploaded_file,
                            category=category,
                            scope=scope,
                            reference_year=reference_year,
                        )

                        DocumentAuditLog.objects.create(
                            document=doc,
                            user=request.user,
                            action="upload"
                        )
                        from django.contrib import messages
                        # ✅ FASE E: Trigger estrazione automatica per sentenze
                        if category == "ruling":
                            try:
                                from .services.sentence_extractor import extract_sentence_data

                                extracted = extract_sentence_data(doc)
                                if extracted:
                                    doc.extracted_data = extracted
                                    doc.save(update_fields=["extracted_data"])
                                    # ✅ Reindirizza alla pagina di revisione invece che alla lista
                                    return redirect("documents:sentence_data_review", doc_id=doc.id)
                                else:
                                    messages.info(request,
                                                  "📄 Sentenza caricata. Nessun dato strutturato è stato estratto automaticamente. Puoi inserirli manualmente nei dettagli.")
                            except Exception as e:
                                logger.error(f"Errore estrazione sentenza: {e}", exc_info=True)
                                messages.warning(request,
                                                 "⚠️ Sentenza caricata, ma l'estrazione automatica dei dati è fallita. Procedi manualmente.")

            return redirect("documents:documents_list")

    else:
        form = DocumentUploadForm()

    return render(request, "documents/documents_upload.html", {
        "form": form
    })


@login_required
def upload_shared_document_view(request):
    user = request.user
    profile = getattr(user, 'profile', None) or getattr(user, 'userprofile', None)
    from django.contrib import messages
    # ✅ BLOCCO PROFESSIONISTI: Solo i genitori possono caricare documenti
    if profile and profile.role in ['lawyer_a', 'lawyer_b', 'mediator', 'consultant']:
        messages.error(request,
                       "⚠️ Solo i genitori possono caricare documenti. I professionisti hanno accesso in sola lettura.")
        return redirect("documents:documents_list")

    family = get_family_of_user(request.user, request=request)

    if request.method == "POST":
        files = request.FILES.getlist("files")
        category = request.POST.get("category", "chat")

        # ✅ VALIDAZIONE DIMENSIONI
        size_error = check_file_sizes(files, category)
        if size_error:
            from django.contrib import messages
            messages.error(request, size_error)
            return render(request, "documents/documents_upload_shared.html", {})

        title_prefix = request.POST.get("title", "").strip()
        # 👇 IL TUO CODICE ORIGINALE CONTINUA ESATTAMENTE QUI
        for index, uploaded_file in enumerate(files, start=1):
            original_name = Path(uploaded_file.name).stem

            if title_prefix:
                title = (
                    f"{title_prefix}_{index}"
                    if len(files) > 1
                    else title_prefix
                )
            else:
                title = original_name

            doc = Document.objects.create(
                family=family,
                owner=request.user,
                uploaded_by=request.user,
                title=title,
                file=uploaded_file,
                category=category,
                scope="shared",
                is_active=True
            )

            DocumentAuditLog.objects.create(
                document=doc,
                user=request.user,
                action="upload"
            )


        return redirect("documents:documents_list")

    return render(
        request,
        "documents/documents_upload_shared.html"
    )


# documents/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


# documents/views.py
@login_required
def storage_usage_view(request):
    from documents.models import Document
    import logging

    logger = logging.getLogger(__name__)

    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect('documents:documents_list')

    profile = getattr(request.user, 'profile', None)
    plan = getattr(profile, 'plan', 'starter') if profile else 'starter'

    plan_limits = {'starter': 2 * 1024 ** 3, 'pro': 10 * 1024 ** 3, 'enterprise': 20 * 1024 ** 3}
    storage_limit = plan_limits.get(plan, plan_limits['starter'])

    # ✅ CALCOLO SICURO: ignora file mancanti/corrotti senza crash
    storage_used = 0
    doc_sizes = []
    docs = Document.objects.filter(family=family, is_active=True)

    for doc in docs:
        try:
            if doc.file and doc.file.name:
                size = doc.file.storage.size(doc.file.name)
                storage_used += size
                doc_sizes.append((doc, size))
        except (FileNotFoundError, OSError, TypeError) as e:
            logger.warning(f"[Storage] File mancante per doc #{doc.id}: {doc.file.name}")
            continue

    storage_available = max(0, storage_limit - storage_used)
    usage_percentage = (storage_used / storage_limit * 100) if storage_limit > 0 else 0

    # ✅ TOP 5: ordinamento sicuro (già calcolato sopra)
    doc_sizes.sort(key=lambda x: x[1], reverse=True)
    top_docs_with_size = doc_sizes[:5]
    total_docs = docs.count()
    # ✅ CALCOLI MATOMATICI (SPOSTATI DALLA VIEW AL TEMPLATE)
    danger_threshold = storage_limit / 10 if storage_limit > 0 else 0  # 10% del limite
    avg_doc_size = (storage_used / total_docs) if total_docs > 0 else 0  # Dimensione media

    context = {
        'family': family,
        'storage_used': storage_used,
        'storage_limit': storage_limit,
        'storage_available': storage_available,
        'danger_threshold': danger_threshold,
        'avg_doc_size': avg_doc_size,
        'usage_percentage': usage_percentage,
        'total_docs': docs.count(),
        'plan': plan,
        'top_large_docs': top_docs_with_size,  # ✅ Lista di tuple (doc, size)
    }
    return render(request, 'documents/storage_usage.html', context)

@login_required
def download_document_view(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)

    if not can_access_document(request.user, doc):
        return HttpResponseForbidden()

    DocumentAuditLog.objects.create(
        document=doc,
        user=request.user,
        action="download"
    )

    return FileResponse(doc.file.open("rb"), as_attachment=True)


@login_required
def document_versions_view(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)

    if not can_access_document(request.user, doc):
        return HttpResponseForbidden()

    # 🔍 CORRETTO: doc.versions è il RelatedManager (QuerySet) delle versioni storiche
    # doc.version sarebbe stato l'INTEGER della versione corrente (causava l'errore)
    versions = doc.version_history.all().order_by("-version")

    return render(request, "documents/documents_versions.html", {
        "document": doc,
        "versions": versions
    })


@login_required
def sign_document_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id)

    if not can_access_document(request.user, document):
        return HttpResponseForbidden()

    membership = FamilyMember.objects.filter(
        family=document.family,
        user=request.user
    ).first()

    if not membership:
        return HttpResponseForbidden()

    role = membership.role

    sign_document(document, request.user, role)

    return redirect("documents:documents_list")


@login_required
def document_detail_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id)
    family = get_family_of_user(request.user, request=request)

    if document.family != family:
        return HttpResponseForbidden()

    signatures = document.signatures.select_related("user").order_by("signed_at")

    return render(
        request,
        "documents/documents_detail.html",
        {
            "document": document,
            "signatures": signatures
        }
    )


@login_required
def approve_document_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id)
    family = get_family_of_user(request.user, request=request)

    if document.family != family:
        return HttpResponseForbidden()

    membership = FamilyMember.objects.filter(
        family=family,
        user=request.user
    ).first()

    if not membership:
        return HttpResponseForbidden()

    approve_document(document, request.user, membership.role)

    return redirect("documents:documents_detail", doc_id=doc_id)


from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from families.utils import get_family_of_user
from documents.models import Document
from calendar_app.models import CalendarEvent
from chat.models import FamilyMessage
from core.plans import PLAN_LEVELS  # Adatta l'import se il tuo è diverso


@login_required
def family_dossier_view(request):
    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect('documents:documents_list')

    # 1️⃣ Controllo piano (Pro vs Starter)
    profile = getattr(request.user, 'profile', None)
    plan = getattr(profile, 'plan', 'starter') if profile else 'starter'
    is_pro_or_higher = PLAN_LEVELS.get(plan, 1) >= 2

    # 2️⃣ Query Documenti (ultimi 5 recenti)
    documents = Document.objects.filter(
        family=family,
        is_active=True
    ).order_by('-created_at')[:5]

    # 3️⃣ Query Eventi (prossimi 5 eventi futuri)
    events = CalendarEvent.objects.filter(
        family=family,
        is_active=True,
        start_time__gte=timezone.now().date()
    ).order_by('start_time')[:5]

    # 4️⃣ Query Chat (ultimi 10 messaggi, invertiti per cronologia dal più vecchio al nuovo)
    recent_messages = FamilyMessage.objects.filter(
        family=family,
        is_active=True,
        recipient__isnull=True  # Solo chat famiglia, non private
    ).select_related('sender').order_by('-created_at')[:10]

    messages_list = list(reversed(recent_messages))

    # 5️⃣ Context completo
    context = {
        'family': family,
        'documents': documents,
        'events': events,
        'messages': messages_list,
        'is_pro_or_higher': is_pro_or_higher,  # ✅ Fondamentale per mostrare il blocco
    }

    return render(request, "documents/dossier.html", context)


def _get_logo_base64():
    """Helper sicuro per embeddare il logo nel PDF"""
    paths = [
        os.path.join(settings.BASE_DIR, 'static', 'images', 'logo-coparent.svg'),
        os.path.join(settings.BASE_DIR, 'static', 'images', 'logo_coparent.png'),
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
    return None

@login_required
def dossier_export_pdf(request):
    """Esporta il fascicolo familiare in PDF (Solo Pro/Enterprise)"""
    family = get_family_of_user(request.user, request=request)
    if not family:
        return redirect('documents:documents_list')

    # 🔒 Controllo piano manuale (se non usi il decorator)
    profile = getattr(request.user, 'profile', None)
    plan = getattr(profile, 'plan', 'starter') if profile else 'starter'
    if PLAN_LEVELS.get(plan, 1) < 2:
        from django.contrib import messages
        messages.error(request, "📊 Funzione riservata al piano Pro. Effettua l'upgrade.")
        return redirect('pricing')

    # 📦 Dati identici al dossier view
    from documents.models import Document
    from chat.models import FamilyMessage
    from calendar_app.models import CalendarEvent

    docs = Document.objects.filter(family=family, is_active=True).order_by('-created_at')[:20]
    recent_msgs = FamilyMessage.objects.filter(
        family=family, is_active=True, recipient__isnull=True
    ).select_related('sender').order_by('-created_at')[:15]
    events = CalendarEvent.objects.filter(
        family=family, is_active=True, start_time__gte=timezone.now().date()
    ).order_by('start_time')[:10]

    context = {
        'family': family,
        'documents': docs,
        'messages': list(reversed(recent_msgs)),  # Ordine cronologico
        'events': events,
        'generated_at': timezone.now(),
        'user': request.user,
        'logo_base64': _get_logo_base64(),
    }

    html_string = render_to_string('documents/dossier_pdf.html', context)
    pdf_bytes = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"Fascicolo_{family.name.replace(' ', '_')}_{timezone.now().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def sentence_data_review_view(request, doc_id):
    """
    ✅ FASE E: Permette all'utente di rivedere e correggere i dati estratti automaticamente dalla sentenza.
    """
    doc = get_object_or_404(Document, id=doc_id)

    # 1. Controllo permessi
    if not can_access_document(request.user, doc):
        return HttpResponseForbidden("Permessi insufficienti per accedere a questo documento.")

    # 2. Controllo che sia effettivamente una sentenza
    if doc.category != "ruling":
        messages.warning(request, "Questo documento non è una sentenza.")
        return redirect("documents:document_detail", doc_id=doc.id)

    if request.method == "POST":
        # 3. Salvataggio dei dati corretti dall'utente
        doc.extracted_data = {
            "maintenance_amount": request.POST.get("maintenance_amount", "").strip(),
            "custody_type": request.POST.get("custody_type", "").strip(),
            "house_assigned_to": request.POST.get("house_assigned_to", "").strip(),
            "vehicle_assignment": request.POST.get("vehicle_assignment", "").strip(),
            "parent_quotas": request.POST.get("parent_quotas", "").strip(),
            "ruling_date": request.POST.get("ruling_date", "").strip(),
            "rg_number": request.POST.get("rg_number", "").strip(),
        }

        # Pulisce le chiavi vuote per mantenere il JSON pulito
        doc.extracted_data = {k: v for k, v in doc.extracted_data.items() if v}
        doc.save(update_fields=["extracted_data"])

        messages.success(request, "✅ Dati della sentenza aggiornati e salvati con successo.")
        return redirect("documents:document_detail", doc_id=doc.id)

    # 4. GET: Prepara i dati per il template
    data = doc.extracted_data or {}

    context = {
        "document": doc,
        "maintenance_amount": data.get("maintenance_amount", ""),
        "custody_type": data.get("custody_type", ""),
        "house_assigned_to": data.get("house_assigned_to", ""),
        "vehicle_assignment": data.get("vehicle_assignment", ""),
        "parent_quotas": data.get("parent_quotas", ""),
        "ruling_date": data.get("ruling_date", ""),
        "rg_number": data.get("rg_number", ""),
    }

    return render(request, "documents/sentence_data_review.html", context)