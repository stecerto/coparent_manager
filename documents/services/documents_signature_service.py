from documents.models import DocumentSignature
from documents.services.audit_service import log_action


def sign_document(document, user, role):
    sig, created = DocumentSignature.objects.get_or_create(
        document=document,
        user=user,
        defaults={"role": role}
    )

    # evita doppia firma
    if not created:
        return document

    log_action(
        family=document.family,
        user=user,
        action="sign",
        document=document,
        description=f"Firma documento {document.title}"
    )

    # 🔥 LOGICA WORKFLOW (NON RIMUOVERLA)
    required_roles = ["parent_a", "parent_b"]

    signed_roles = set(
        document.signatures.values_list("role", flat=True)
    )

    if set(required_roles).issubset(signed_roles):
        document.status = "signed"
        document.save()

    return document

