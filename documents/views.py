from django.shortcuts import render

from chat.models import FamilyMessage
from calendar_app.models import CalendarEvent
from .services.documents_checklist_service import get_essential_checklist
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from .services.documents_signature_service import sign_document
from .permissions import can_access_document
from .models import Document, DocumentAuditLog, DocumentVersion,DocumentSignature
from .forms import DocumentUploadForm
from .permissions import can_access_document
from families.utils import get_family_of_user
from pathlib import Path
from pathlib import Path
from django.db import transaction
from families.models import FamilyMember
from .services.workflow_service import approve_document


@login_required
def document_list_view(request):
    family = get_family_of_user(request.user)

    membership = FamilyMember.objects.filter(
        family=family,
        user=request.user
    ).first()

    role = membership.role if membership else None

    private_docs = Document.objects.none()

    if membership:
        if role in ["parent_a", "parent_b"]:
            private_docs = Document.objects.filter(
                family=family,
                owner=request.user,
                scope="private",
                is_active=True
            )

        elif role == "lawyer_a":
            assisted_user = family.memberships.filter(role="parent_a").first()
            if assisted_user:
                private_docs = Document.objects.filter(
                    family=family,
                    owner=assisted_user.user,
                    scope="private",
                    is_active=True
                )

        elif role == "lawyer_b":
            assisted_user = family.memberships.filter(role="parent_b").first()
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

    checklist = get_essential_checklist(request.user, family)

    # 🔥 PRELOAD FIRME UTENTE (IMPORTANTISSIMO)
    signed_docs = set(
        DocumentSignature.objects.filter(
            user=request.user,
            document__in=list(private_docs) + list(shared_docs)
        ).values_list("document_id", flat=True)
    )

    # annotiamo i documenti
    for doc in private_docs:
        doc.is_signed_by_user = doc.id in signed_docs

    for doc in shared_docs:
        doc.is_signed_by_user = doc.id in signed_docs

    return render(request, "documents/documents_list.html", {
        "private_docs": private_docs,
        "shared_docs": shared_docs,
        "checklist": checklist,
        "role": role,
    })

@login_required
def upload_document_view(request):
    family = get_family_of_user(request.user)

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            files = request.FILES.getlist("files")

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
                        # salva vecchia versione
                        DocumentVersion.objects.create(
                            document=existing_doc,
                            file=existing_doc.file,
                            version=existing_doc.version,
                            uploaded_by=request.user
                        )

                        # aggiorna documento principale
                        existing_doc.file = uploaded_file
                        existing_doc.version += 1
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

            return redirect("documents:documents_list")

    else:
        form = DocumentUploadForm()

    return render(request, "documents/documents_upload.html", {
        "form": form
    })

@login_required
def upload_shared_document_view(request):
    family = get_family_of_user(request.user)

    if request.method == "POST":
        files = request.FILES.getlist("files")
        category = request.POST.get("category", "chat")
        title_prefix = request.POST.get("title", "").strip()

        for index, uploaded_file in enumerate(files, start=1):
            from pathlib import Path

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

    versions = doc.version.all().order_by("-version")

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

    # firma
    sign_document(document, request.user, role)

    return redirect("documents:documents_list")

@login_required
def document_detail_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id)
    family = get_family_of_user(request.user)

    # sicurezza base
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
    family = get_family_of_user(request.user)

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

@login_required
def family_dossier_view(request):
    family = get_family_of_user(request.user)

    if not family:
        return HttpResponseForbidden()

    documents = Document.objects.filter(
        family=family,
        is_active=True
    ).select_related("family")

    messages = FamilyMessage.objects.filter(
        family=family,
        is_active=True
    ).order_by("-created_at")[:20]

    events = CalendarEvent.objects.filter(
        family=family
    ).order_by("-start_time")[:10]

    return render(
        request,
        "documents/dossier.html",
        {
            "family": family,
            "documents": documents,
            "messages": messages,
            "events": events
        }
    )