from documents.models import Document
from documents.services.audit_service import log_action


def upload_document(*, family, user, file, title, document_type=None):
    doc = Document.objects.create(
        family=family,
        uploaded_by=user,
        file=file,
        title=title,
        document_type=document_type
    )

    log_action(
        family=family,
        user=user,
        action="upload",
        document=doc,
        description=f"Upload documento {doc.title}"
    )

    return doc