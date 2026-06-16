from django.urls import resolve, Resolver404, reverse
from django.apps import apps

from core.plans import PLAN_FEATURES, PLAN_LEVELS
from .models import DashboardWidget  # ✅ NUOVO: Import per i widget

# 🔹 URL → label leggibile
LABEL_MAP = {
    "family_dashboard": "Generale",
    "children_list": "Figli",
    "child_detail": "Figlio",
    "child_edit": "Modifica",
    "child_confirm_delete": "Elimina",
    "expenses_dashboard": "Spese",
    "add_expense": "Aggiungi",
    "edit_expense": "Modifica",
    "chat_home": "Chat",
    "documents_list": "Documenti",
    "calendar_view": "Calendario",
    "summary": "Riepilogo",
    "setup": "Setup",
}

# 🔹 URL → modello per recuperare nome oggetto
MODEL_LABELS = {
    "child_detail": ("children.ChildProfile", "name"),
    "child_edit": ("children.ChildProfile", "name"),
    "child_confirm_delete": ("children.ChildProfile", "name"),
    "edit_expense": ("expenses.Expense", "expense_type"),
}

IGNORE_PARTS = ["families", "accounts", "calendar", "core", "config", ]


def get_object_label(model_path, field, pk):
    try:
        Model = apps.get_model(model_path)
        obj = Model.objects.filter(pk=pk).only(field).first()

        if not obj:
            return str(pk)

        # 👉 supporto choices (es. expense_type)
        display_method = f"get_{field}_display"
        if hasattr(obj, display_method):
            return getattr(obj, display_method)()

        return getattr(obj, field, str(pk))

    except Exception:
        return str(pk)


def breadcrumbs(request):
    crumbs = []

    try:
        path_parts = request.path.strip("/").split("/")
        accumulated = ""

        # 🔹 HOME
        crumbs.append({
            "name": "Home",
            "url": reverse("home")
        })

        for i, part in enumerate(path_parts):
            if not part or part in IGNORE_PARTS:
                continue

            # 🔥 salta numeri puri
            if part.isdigit():
                continue

            accumulated += f"/{part}"

            try:
                match = resolve(accumulated + "/")
                url_name = match.url_name
                kwargs = match.kwargs

                # 🔹 se la view contiene pk/id mostra il nome oggetto
                if ("pk" in kwargs or "id" in kwargs) and url_name in MODEL_LABELS:
                    pk = kwargs.get("pk") or kwargs.get("id")
                    model_path, field = MODEL_LABELS[url_name]

                    label = get_object_label(model_path, field, pk)

                else:
                    label = LABEL_MAP.get(
                        url_name,
                        part.replace("-", " ").replace("_", " ").title()
                    )

                crumbs.append({
                    "name": label,
                    "url": accumulated + "/" if i < len(path_parts) - 1 else None
                })

            except Resolver404:
                crumbs.append({
                    "name": part.replace("-", " ").title(),
                    "url": None
                })

    except Exception:
        pass

    return {"breadcrumbs": crumbs}


def subscription_context(request):
    if not request.user.is_authenticated:
        return {"current_plan": "starter", "plan_features": {}, "plan_level": 1}

    profile = getattr(request.user, 'profile', None)
    plan = getattr(profile, 'plan', 'starter') if profile else 'starter'
    level = PLAN_LEVELS.get(plan, 1)
    features = PLAN_FEATURES.get(plan, PLAN_FEATURES["starter"])

    return {
        "current_plan": plan,
        "plan_level": level,
        "plan_features": features,
        "is_pro_or_higher": level >= 2,
    }


# ==============================================================================
# ✅ NUOVO CONTEXT PROCESSOR AGGIUNTO: dashboard_context
# ==============================================================================
def dashboard_context(request):
    """
    Fornisce automaticamente i widget della dashboard attivi per il ruolo dell'utente.
    Disponibile in tutti i template come variabile {{ dashboard_widgets }}

    ✅ FILTRO ENTERPRISE: Restituisce lista vuota se l'utente non ha piano Enterprise.
    """
    if not request.user.is_authenticated:
        return {"dashboard_widgets": []}

    profile = getattr(request.user, 'profile', None)
    if not profile or not profile.role:
        return {"dashboard_widgets": []}

    # ✅ FILTRO PIANO: Solo Enterprise (level 3) vede i widget dinamici
    from core.plans import PLAN_LEVELS
    current_plan = getattr(profile, 'plan', 'starter')
    plan_level = PLAN_LEVELS.get(current_plan, 1)

    if plan_level < 3:  # 3 = Enterprise
        return {"dashboard_widgets": []}

    # Recupera i widget ordinati per posizione, specifici per il ruolo dell'utente
    from core.models import DashboardWidget
    widgets = DashboardWidget.get_active_for_role_and_plan(profile.role, plan_level)

    return {
        "dashboard_widgets": widgets
    }