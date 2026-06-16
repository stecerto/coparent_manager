# core/plans.py
PLAN_LEVELS = {
    "starter": 1,
    "pro": 2,
    "enterprise": 3,
}

PLAN_FEATURES = {
    "starter": {
        "can_export_pdf": False,
        "can_view_history": False,
        "can_create_events": False,
        "can_upload_attachments": True,
    },
    "pro": {
        "can_export_pdf": True,
        "can_view_history": True,
        "can_create_events": True,
        "can_upload_attachments": True,
    },
    "enterprise": {
        "can_export_pdf": True,
        "can_view_history": True,
        "can_create_events": True,
        "can_upload_attachments": True,
    }
}
# =========================
# LIMITI PIANO PER PROFESSIONISTI
# =========================
PLAN_LIMITS = {
    "starter": {
        "families": 5,
        "mediators": 1,
        "consultants": 1,
    },
    "pro": {
        "families": 10,
        "mediators": 4,
        "consultants": 4,
    },
    "enterprise": {
        "families": 25,
        "mediators": 8,
        "consultants": 8,
    },
}


def has_feature(user, feature_key):
    """Helper Python/Template per verificare feature"""
    if not user or not user.is_authenticated:
        return False
    plan = getattr(getattr(user, 'profile', None), 'plan', 'starter')
    return PLAN_FEATURES.get(plan, PLAN_FEATURES["starter"]).get(feature_key, False)