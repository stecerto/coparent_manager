from documents.models import AuditLog


def log_action(*, family, user, action, description, document=None):
    return AuditLog.objects.create(
        family=family,
        user=user,
        action=action,
        description=description,
        document=document
    )