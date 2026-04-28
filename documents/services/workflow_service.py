from documents.models import DocumentApproval
from documents.services.audit_service import log_action
from documents.services.notification_service import notify_document_status


def approve_document(document, user, role):
    obj, created = DocumentApproval.objects.get_or_create(
        document=document,
        user=user,
        defaults={"role": role, "approved": True}
    )

    if not created:
        return document

    log_action(
        family=document.family,
        user=user,
        action="approve",
        document=document,
        description=f"Approvazione documento {document.title}"
    )

    # 🔥 IMPORTANTE: aggiorna stato workflow
    _update_workflow(document)

    return document

def _update_workflow(document):
    approvals = document.approvals.values_list("role", flat=True)

    required_parties = {"parent_a", "parent_b"}

    # STEP 1 → REVIEW
    if document.status == "draft":
        document.status = "review"
        document.save()
        return

    # STEP 2 → APPROVED (genitori)
    if required_parties.issubset(set(approvals)):
        document.status = "approved"
        document.save()

    # STEP 3 → SIGNED (firme complete)
    signed_roles = set(document.signatures.values_list("role", flat=True))

    if required_parties.issubset(signed_roles):
        document.status = "signed"
        document.save()

    # STEP 4 → LOCKED (finale)
    if document.status == "signed":
        document.status = "locked"
        document.save()

    if document.status == "review":
        notify_document_status(document, "Documento in revisione")

    if document.status == "approved":
        notify_document_status(document, "Documento approvato dai genitori")

    if document.status == "signed":
        notify_document_status(document, "Documento firmato")

    if document.status == "locked":
        notify_document_status(document, "Documento bloccato e definitivo")